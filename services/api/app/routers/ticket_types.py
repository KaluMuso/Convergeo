from __future__ import annotations

from typing import Annotated, Any, Literal

from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import NgweeInt, StrictModel
from app.services.kyc.state_machine import ServiceRoleClient
from fastapi import APIRouter, Depends
from pydantic import Field, field_validator, model_validator

router = APIRouter(prefix="/organiser", tags=["ticket-types"])

TicketKind = Literal["fixed", "tier", "free_rsvp"]


class TicketTypeResponse(StrictModel):
    id: str
    event_id: str
    kind: TicketKind
    name: str
    price_ngwee: int
    qty_cap: int | None = None
    per_customer_cap: int | None = None
    tickets_sold: int = 0


class TicketTypeCreateRequest(StrictModel):
    kind: TicketKind
    name: str = Field(min_length=1, max_length=120)
    price_ngwee: NgweeInt
    qty_cap: int | None = Field(default=None, gt=0)
    per_customer_cap: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_price_for_kind(self) -> TicketTypeCreateRequest:
        if self.kind == "free_rsvp":
            if self.price_ngwee != 0:
                raise ValueError("free_rsvp ticket types must have price_ngwee = 0")
        elif self.price_ngwee <= 0:
            raise ValueError("fixed and tier ticket types must have price_ngwee > 0")
        return self


class TicketTypeUpdateRequest(StrictModel):
    kind: TicketKind | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    price_ngwee: NgweeInt | None = None
    qty_cap: int | None = Field(default=None, gt=0)
    per_customer_cap: int | None = Field(default=None, gt=0)

    @field_validator("qty_cap", "per_customer_cap", mode="before")
    @classmethod
    def allow_null_caps(cls, value: object) -> object:
        if value is None:
            return None
        return value

    @model_validator(mode="after")
    def validate_price_for_kind(self) -> TicketTypeUpdateRequest:
        kind = self.kind
        price = self.price_ngwee
        if kind is None or price is None:
            return self
        if kind == "free_rsvp" and price != 0:
            raise ValueError("free_rsvp ticket types must have price_ngwee = 0")
        if kind != "free_rsvp" and price <= 0:
            raise ValueError("fixed and tier ticket types must have price_ngwee > 0")
        return self


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def _load_vendor_for_owner(
    service_client: ServiceRoleClient,
    owner_user_id: str,
) -> dict[str, Any]:
    response = (
        service_client.client.table("vendors")
        .select("id, owner_user_id, status, kyc_tier")
        .eq("owner_user_id", owner_user_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(
            code="forbidden",
            message="Authenticated user does not own a vendor profile",
            http_status=403,
            details={"message_key": "vendor.errors.not_found"},
        )
    return row


def _load_event(
    service_client: ServiceRoleClient,
    event_id: str,
) -> dict[str, Any]:
    response = (
        service_client.client.table("events")
        .select("id, organiser_vendor_id, status")
        .eq("id", event_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(
            code="not_found",
            message="Event not found",
            http_status=404,
            details={"event_id": event_id},
        )
    return row


def _assert_event_owned(event: dict[str, Any], vendor_id: str, *, event_id: str) -> None:
    if str(event.get("organiser_vendor_id")) != vendor_id:
        raise AppError(
            code="forbidden",
            message="Event does not belong to the authenticated organiser",
            http_status=403,
            details={"event_id": event_id, "vendor_id": vendor_id},
        )


def _load_ticket_type(
    service_client: ServiceRoleClient,
    ticket_type_id: str,
) -> dict[str, Any]:
    response = (
        service_client.client.table("ticket_types")
        .select("id, event_id, kind, name, price_ngwee, qty_cap, per_customer_cap")
        .eq("id", ticket_type_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(
            code="not_found",
            message="Ticket type not found",
            http_status=404,
            details={"ticket_type_id": ticket_type_id},
        )
    return row


def _count_tickets_sold(service_client: ServiceRoleClient, ticket_type_id: str) -> int:
    response = (
        service_client.client.table("tickets")
        .select("id", count="exact")
        .eq("ticket_type_id", ticket_type_id)
        .neq("status", "void")
        .execute()
    )
    count = getattr(response, "count", None)
    return int(count) if isinstance(count, int) else 0


def _validate_kind_price(kind: str, price_ngwee: int) -> None:
    if kind == "free_rsvp":
        if price_ngwee != 0:
            raise AppError(
                code="invalid_ticket_price",
                message="free_rsvp ticket types must have price_ngwee = 0",
                http_status=422,
                details={"message_key": "vendor.tickets.errors.freeMustBeZero"},
            )
    elif price_ngwee <= 0:
        raise AppError(
            code="invalid_ticket_price",
            message="fixed and tier ticket types must have price_ngwee > 0",
            http_status=422,
            details={"message_key": "vendor.tickets.errors.paidMustBePositive"},
        )


def _validate_tier_config(
    service_client: ServiceRoleClient,
    event_id: str,
    *,
    kind: str,
    name: str,
    exclude_type_id: str | None = None,
) -> None:
    if kind != "tier":
        return
    query = (
        service_client.client.table("ticket_types")
        .select("id, name")
        .eq("event_id", event_id)
        .eq("kind", "tier")
    )
    if exclude_type_id is not None:
        query = query.neq("id", exclude_type_id)
    rows = _rows(query.execute())
    normalized = name.strip().casefold()
    for row in rows:
        existing = str(row.get("name", "")).strip().casefold()
        if existing == normalized:
            raise AppError(
                code="duplicate_tier_name",
                message="A tier with this name already exists for the event",
                http_status=422,
                details={"message_key": "vendor.tickets.errors.duplicateTier"},
            )


def _to_ticket_type_response(
    row: dict[str, Any],
    *,
    tickets_sold: int,
) -> TicketTypeResponse:
    return TicketTypeResponse(
        id=str(row["id"]),
        event_id=str(row["event_id"]),
        kind=str(row["kind"]),  # type: ignore[arg-type]
        name=str(row["name"]),
        price_ngwee=int(row["price_ngwee"]),
        qty_cap=int(row["qty_cap"]) if row.get("qty_cap") is not None else None,
        per_customer_cap=(
            int(row["per_customer_cap"]) if row.get("per_customer_cap") is not None else None
        ),
        tickets_sold=tickets_sold,
    )


@router.get("/events/{event_id}/ticket-types", response_model=list[TicketTypeResponse])
def list_ticket_types(
    event_id: str,
    user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> list[TicketTypeResponse]:
    vendor = _load_vendor_for_owner(service_client, user.id)
    event = _load_event(service_client, event_id)
    _assert_event_owned(event, str(vendor["id"]), event_id=event_id)

    rows = _rows(
        service_client.client.table("ticket_types")
        .select("id, event_id, kind, name, price_ngwee, qty_cap, per_customer_cap")
        .eq("event_id", event_id)
        .order("created_at")
        .execute()
    )
    return [
        _to_ticket_type_response(
            row,
            tickets_sold=_count_tickets_sold(service_client, str(row["id"])),
        )
        for row in rows
    ]


@router.post(
    "/events/{event_id}/ticket-types",
    response_model=TicketTypeResponse,
    status_code=201,
)
def create_ticket_type(
    event_id: str,
    body: TicketTypeCreateRequest,
    user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> TicketTypeResponse:
    vendor = _load_vendor_for_owner(service_client, user.id)
    event = _load_event(service_client, event_id)
    _assert_event_owned(event, str(vendor["id"]), event_id=event_id)

    _validate_kind_price(body.kind, body.price_ngwee)
    _validate_tier_config(
        service_client,
        event_id,
        kind=body.kind,
        name=body.name,
    )

    if body.kind == "fixed":
        existing_fixed = _rows(
            service_client.client.table("ticket_types")
            .select("id")
            .eq("event_id", event_id)
            .eq("kind", "fixed")
            .limit(1)
            .execute()
        )
        if existing_fixed:
            raise AppError(
                code="duplicate_fixed_type",
                message="This event already has a fixed-price ticket type",
                http_status=422,
                details={"message_key": "vendor.tickets.errors.duplicateFixed"},
            )

    payload: dict[str, Any] = {
        "event_id": event_id,
        "kind": body.kind,
        "name": body.name.strip(),
        "price_ngwee": body.price_ngwee,
        "qty_cap": body.qty_cap,
        "per_customer_cap": body.per_customer_cap,
    }
    response = service_client.client.table("ticket_types").insert(payload).execute()
    row = _single_row(response)
    if row is None:
        raise AppError(
            code="create_failed",
            message="Failed to create ticket type",
            http_status=500,
        )
    return _to_ticket_type_response(row, tickets_sold=0)


@router.patch("/ticket-types/{ticket_type_id}", response_model=TicketTypeResponse)
def update_ticket_type(
    ticket_type_id: str,
    body: TicketTypeUpdateRequest,
    user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> TicketTypeResponse:
    vendor = _load_vendor_for_owner(service_client, user.id)
    existing = _load_ticket_type(service_client, ticket_type_id)
    event = _load_event(service_client, str(existing["event_id"]))
    _assert_event_owned(event, str(vendor["id"]), event_id=str(existing["event_id"]))

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return _to_ticket_type_response(
            existing,
            tickets_sold=_count_tickets_sold(service_client, ticket_type_id),
        )

    next_kind = str(updates.get("kind", existing["kind"]))
    next_price = int(updates.get("price_ngwee", existing["price_ngwee"]))
    next_name = str(updates.get("name", existing["name"])).strip()

    _validate_kind_price(next_kind, next_price)
    _validate_tier_config(
        service_client,
        str(existing["event_id"]),
        kind=next_kind,
        name=next_name,
        exclude_type_id=ticket_type_id,
    )

    if "name" in updates:
        updates["name"] = next_name

    response = (
        service_client.client.table("ticket_types")
        .update(updates)
        .eq("id", ticket_type_id)
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(
            code="update_failed",
            message="Failed to update ticket type",
            http_status=500,
        )
    return _to_ticket_type_response(
        row,
        tickets_sold=_count_tickets_sold(service_client, ticket_type_id),
    )


@router.delete("/ticket-types/{ticket_type_id}", status_code=204)
def delete_ticket_type(
    ticket_type_id: str,
    user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> None:
    vendor = _load_vendor_for_owner(service_client, user.id)
    existing = _load_ticket_type(service_client, ticket_type_id)
    event = _load_event(service_client, str(existing["event_id"]))
    _assert_event_owned(event, str(vendor["id"]), event_id=str(existing["event_id"]))

    sold = _count_tickets_sold(service_client, ticket_type_id)
    if sold > 0:
        raise AppError(
            code="ticket_type_has_sales",
            message="Cannot delete a ticket type with issued tickets",
            http_status=409,
            details={"ticket_type_id": ticket_type_id, "tickets_sold": sold},
        )

    service_client.client.table("ticket_types").delete().eq("id", ticket_type_id).execute()
