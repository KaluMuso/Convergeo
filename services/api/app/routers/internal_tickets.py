from __future__ import annotations

from datetime import timedelta
from typing import Annotated, Any

from app.core.auth import CurrentUser, get_current_user
from app.core.internal_token import InternalTokenMisconfigured, resolve_internal_token, tokens_match
from app.core.ratelimit import bump_rate_counter, get_client_ip, raise_rate_limited
from app.deps import get_supabase_client
from app.errors import AppError
from app.services.tickets.purchase import (
    TicketCheckoutResult,
    add_ticket_to_checkout,
    find_orders_pending_ticket_issue,
    issue_tickets_for_paid_order,
    release_stale_ticket_claims,
    rsvp,
)
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator

router = APIRouter(tags=["tickets"])

_INTERNAL_TOKEN_ENV = "INTERNAL_TICKETS_ISSUE_TOKEN"
_DEFAULT_INTERNAL_TOKEN = "dev-internal-tickets-issue"


class TicketPurchaseRequest(BaseModel):
    instance_id: str
    ticket_type_id: str
    qty: int = Field(default=1, ge=1, le=20)
    # Optional per-attendee names (Wave A/M10-P11). Required only when the ticket
    # type is attendee_named; enforced server-side in purchase._validate_attendee_names.
    attendee_names: list[str] | None = Field(default=None, max_length=20)
    # Returned only by POST /events/{slug}/access/unlock. It is deliberately a
    # request body value, never a query parameter that can reach access logs.
    event_access_proof: str | None = Field(default=None, max_length=2048)
    promo_code: str | None = Field(default=None, max_length=40)
    affiliate_code: str | None = Field(default=None, max_length=40)

    @field_validator("attendee_names")
    @classmethod
    def _cap_name_lengths(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return [str(name).strip()[:120] for name in value]


class TicketCheckoutResponse(BaseModel):
    checkout_group_id: str
    order_id: str
    order_item_id: str
    subtotal_ngwee: int
    platform_fee_ngwee: int = 0
    total_ngwee: int = 0
    redirect_to: str


class RsvpResponse(BaseModel):
    checkout_group_id: str
    order_id: str
    order_item_id: str
    ticket_count: int
    redirect_to: str
    replayed: bool = False


def _expected_internal_token() -> str:
    try:
        return resolve_internal_token(
            _INTERNAL_TOKEN_ENV,
            dev_default=_DEFAULT_INTERNAL_TOKEN,
        )
    except InternalTokenMisconfigured as exc:
        raise AppError(
            code="configuration_error",
            message=str(exc),
            http_status=503,
        ) from exc


async def require_internal_tickets_token(request: Request) -> None:
    expected = _expected_internal_token()
    provided = request.headers.get("X-Internal-Token")
    if not tokens_match(provided, expected):
        raise AppError(
            code="unauthorized",
            message="Invalid or missing internal tickets token",
            http_status=401,
        )


def _to_checkout_response(result: TicketCheckoutResult) -> TicketCheckoutResponse:
    return TicketCheckoutResponse(
        checkout_group_id=result.checkout_group_id,
        order_id=result.order_id,
        order_item_id=result.order_item_id,
        subtotal_ngwee=result.subtotal_ngwee,
        platform_fee_ngwee=result.platform_fee_ngwee,
        total_ngwee=result.total_ngwee or result.subtotal_ngwee,
        redirect_to=f"/checkout?group={result.checkout_group_id}",
    )


@router.post("/tickets/checkout", response_model=TicketCheckoutResponse)
async def ticket_checkout(
    body: TicketPurchaseRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[Any, Depends(get_supabase_client)],
) -> TicketCheckoutResponse:
    result = add_ticket_to_checkout(
        service,
        customer_id=current_user.id,
        instance_id=body.instance_id,
        ticket_type_id=body.ticket_type_id,
        qty=body.qty,
        attendee_names=body.attendee_names,
        event_access_proof=body.event_access_proof,
        promo_code=body.promo_code,
        affiliate_code=body.affiliate_code,
    )
    return _to_checkout_response(result)


def _rate_limit_rsvp(request: Request, user_id: str, service: Any) -> None:
    """Free RSVPs cost nothing, so throttle them per IP and per user."""
    for scope, key, limit in (
        ("ticket_rsvp_ip", get_client_ip(request), 20),
        ("ticket_rsvp_user", user_id, 10),
    ):
        allowed, retry = bump_rate_counter(
            scope=scope,
            key=key,
            window=timedelta(minutes=10),
            limit=limit,
            client=service.client,
        )
        if not allowed:
            raise_rate_limited(
                retry_after=retry,
                message_key="events.ticketPurchase.errors.rateLimited",
                message="Too many RSVP requests",
            )


@router.post("/tickets/rsvp", response_model=RsvpResponse)
async def ticket_rsvp(
    body: TicketPurchaseRequest,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[Any, Depends(get_supabase_client)],
) -> RsvpResponse:
    _rate_limit_rsvp(request, current_user.id, service)
    result = rsvp(
        service,
        customer_id=current_user.id,
        instance_id=body.instance_id,
        ticket_type_id=body.ticket_type_id,
        qty=body.qty,
        attendee_names=body.attendee_names,
        event_access_proof=body.event_access_proof,
    )
    return RsvpResponse(
        checkout_group_id=result.checkout_group_id,
        order_id=result.order_id,
        order_item_id=result.order_item_id,
        ticket_count=len(result.ticket_ids),
        redirect_to=f"/account/orders/{result.order_id}",
        replayed=result.replayed,
    )


@router.post(
    "/internal/tickets/issue-tick",
    dependencies=[Depends(require_internal_tickets_token)],
)
async def tickets_issue_tick(
    service: Annotated[Any, Depends(get_supabase_client)],
) -> dict[str, int]:
    """Scan SUCCESS-paid orders with unissued ticket items and fulfil idempotently."""
    pending = find_orders_pending_ticket_issue(service)
    issued_orders = 0
    tickets_issued = 0
    for order_id in pending:
        outcome = issue_tickets_for_paid_order(service, order_id)
        if outcome.issued_count > 0:
            issued_orders += 1
            tickets_issued += outcome.issued_count
    return {
        "scanned": len(pending),
        "issued_orders": issued_orders,
        "tickets_issued": tickets_issued,
    }


@router.post(
    "/internal/tickets/release-tick",
    dependencies=[Depends(require_internal_tickets_token)],
)
async def tickets_release_tick(
    service: Annotated[Any, Depends(get_supabase_client)],
) -> dict[str, int]:
    """Void stale unpaid ticket holds past the reservation TTL (capacity recovery)."""
    outcome = release_stale_ticket_claims(service)
    return {
        "voided": outcome.voided_count,
        "ttl_minutes": outcome.ttl_minutes,
    }
