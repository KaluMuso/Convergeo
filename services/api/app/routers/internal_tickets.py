from __future__ import annotations

import os
from typing import Annotated, Any

from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.errors import AppError
from app.services.tickets.purchase import (
    TicketCheckoutResult,
    add_ticket_to_checkout,
    find_orders_pending_ticket_issue,
    issue_tickets_for_paid_order,
    rsvp,
)
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["tickets"])

_INTERNAL_TOKEN_ENV = "INTERNAL_TICKETS_ISSUE_TOKEN"
_DEFAULT_INTERNAL_TOKEN = "dev-internal-tickets-issue"


class TicketPurchaseRequest(BaseModel):
    instance_id: str
    ticket_type_id: str
    qty: int = Field(default=1, ge=1, le=20)


class TicketCheckoutResponse(BaseModel):
    checkout_group_id: str
    order_id: str
    order_item_id: str
    subtotal_ngwee: int
    redirect_to: str


class RsvpResponse(BaseModel):
    checkout_group_id: str
    order_id: str
    order_item_id: str
    ticket_count: int
    redirect_to: str


def _expected_internal_token() -> str:
    return os.environ.get(_INTERNAL_TOKEN_ENV, _DEFAULT_INTERNAL_TOKEN)


async def require_internal_tickets_token(request: Request) -> None:
    expected = _expected_internal_token()
    provided = request.headers.get("X-Internal-Token")
    if not provided or provided != expected:
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
    )
    return _to_checkout_response(result)


@router.post("/tickets/rsvp", response_model=RsvpResponse)
async def ticket_rsvp(
    body: TicketPurchaseRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[Any, Depends(get_supabase_client)],
) -> RsvpResponse:
    result = rsvp(
        service,
        customer_id=current_user.id,
        instance_id=body.instance_id,
        ticket_type_id=body.ticket_type_id,
        qty=body.qty,
    )
    return RsvpResponse(
        checkout_group_id=result.checkout_group_id,
        order_id=result.order_id,
        order_item_id=result.order_item_id,
        ticket_count=len(result.ticket_ids),
        redirect_to=f"/account/orders/{result.order_id}",
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
