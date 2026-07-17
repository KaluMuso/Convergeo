from __future__ import annotations

from datetime import UTC, datetime
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


class AllocationInput(StrictModel):
    instance_id: str = Field(min_length=1)
    allocation: int = Field(ge=0)


class AllocationPutRequest(StrictModel):
    # Full desired allocation set for the type. An instance present here is capped
    # to `allocation`; any instance omitted has its cap (if any) removed.
    allocations: list[AllocationInput] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def unique_instances(self) -> AllocationPutRequest:
        seen = {a.instance_id for a in self.allocations}
        if len(seen) != len(self.allocations):
            raise ValueError("duplicate instance_id in allocations")
        return self


class AllocationRow(StrictModel):
    instance_id: str
    starts_at: str
    allocation: int | None = None  # None = no per-instance cap for this type
    sold: int = 0


# --- M10-P15: organiser ticket-pricing write API (early-bird + group tiers) ---
# Schema + server-side resolution shipped in M10-P12 (migration 0049); this adds
# the organiser-facing write surface. Discounts are only ever *lower* than the base
# price — enforced here — and resolution stays server-side in tickets/purchase.py.


class PriceTierRow(StrictModel):
    min_qty: int
    price_ngwee: int


class PricingConfigResponse(StrictModel):
    ticket_type_id: str
    base_price_ngwee: int
    early_bird_price_ngwee: int | None = None
    early_bird_until: str | None = None
    tiers: list[PriceTierRow]


class EarlyBirdPutRequest(StrictModel):
    # Both fields set = configure early-bird; both null = clear it. A price without a
    # cutoff (or vice versa) is meaningless — the DB enforces the same pairing.
    early_bird_price_ngwee: NgweeInt | None = None
    early_bird_until: str | None = None

    @model_validator(mode="after")
    def both_or_neither(self) -> EarlyBirdPutRequest:
        has_price = self.early_bird_price_ngwee is not None
        has_until = self.early_bird_until is not None
        if has_price != has_until:
            raise ValueError(
                "early_bird_price_ngwee and early_bird_until must be set together or both null"
            )
        return self


class PriceTierInput(StrictModel):
    min_qty: int = Field(ge=2)  # qty 1 is always the base price
    price_ngwee: NgweeInt


class PriceTiersPutRequest(StrictModel):
    # Full desired tier set for the type — replaces whatever exists (upsert desired,
    # delete the rest), mirroring the allocations PUT.
    tiers: list[PriceTierInput] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def unique_min_qty(self) -> PriceTiersPutRequest:
        seen = {tier.min_qty for tier in self.tiers}
        if len(seen) != len(self.tiers):
            raise ValueError("duplicate min_qty in tiers")
        return self


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
        .select(
            "id, event_id, kind, name, price_ngwee, qty_cap, per_customer_cap, "
            "early_bird_price_ngwee, early_bird_until"
        )
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


def _load_event_instances(
    service_client: ServiceRoleClient,
    event_id: str,
) -> list[dict[str, Any]]:
    return _rows(
        service_client.client.table("event_instances")
        .select("id, starts_at")
        .eq("event_id", event_id)
        .order("starts_at")
        .execute()
    )


def _sold_by_instance(
    service_client: ServiceRoleClient,
    ticket_type_id: str,
) -> dict[str, int]:
    """Live count of non-void tickets for this type, grouped by instance."""
    rows = _rows(
        service_client.client.table("tickets")
        .select("instance_id")
        .eq("ticket_type_id", ticket_type_id)
        .neq("status", "void")
        .execute()
    )
    counts: dict[str, int] = {}
    for row in rows:
        instance_id = str(row.get("instance_id") or "")
        if instance_id:
            counts[instance_id] = counts.get(instance_id, 0) + 1
    return counts


def _load_allocations(
    service_client: ServiceRoleClient,
    ticket_type_id: str,
) -> dict[str, int]:
    rows = _rows(
        service_client.client.table("ticket_type_instances")
        .select("instance_id, allocation")
        .eq("ticket_type_id", ticket_type_id)
        .execute()
    )
    result: dict[str, int] = {}
    for row in rows:
        instance_id = str(row.get("instance_id") or "")
        allocation = row.get("allocation")
        if instance_id and allocation is not None:
            result[instance_id] = int(allocation)
    return result


def _build_allocation_rows(
    service_client: ServiceRoleClient,
    *,
    event_id: str,
    ticket_type_id: str,
) -> list[AllocationRow]:
    instances = _load_event_instances(service_client, event_id)
    allocations = _load_allocations(service_client, ticket_type_id)
    sold = _sold_by_instance(service_client, ticket_type_id)
    return [
        AllocationRow(
            instance_id=str(instance["id"]),
            starts_at=str(instance.get("starts_at") or ""),
            allocation=allocations.get(str(instance["id"])),
            sold=sold.get(str(instance["id"]), 0),
        )
        for instance in instances
    ]


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


@router.get(
    "/ticket-types/{ticket_type_id}/allocations",
    response_model=list[AllocationRow],
)
def list_allocations(
    ticket_type_id: str,
    user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> list[AllocationRow]:
    vendor = _load_vendor_for_owner(service_client, user.id)
    ticket_type = _load_ticket_type(service_client, ticket_type_id)
    event_id = str(ticket_type["event_id"])
    event = _load_event(service_client, event_id)
    _assert_event_owned(event, str(vendor["id"]), event_id=event_id)
    return _build_allocation_rows(
        service_client, event_id=event_id, ticket_type_id=ticket_type_id
    )


@router.put(
    "/ticket-types/{ticket_type_id}/allocations",
    response_model=list[AllocationRow],
)
def set_allocations(
    ticket_type_id: str,
    body: AllocationPutRequest,
    user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> list[AllocationRow]:
    vendor = _load_vendor_for_owner(service_client, user.id)
    ticket_type = _load_ticket_type(service_client, ticket_type_id)
    event_id = str(ticket_type["event_id"])
    event = _load_event(service_client, event_id)
    _assert_event_owned(event, str(vendor["id"]), event_id=event_id)

    valid_instance_ids = {
        str(instance["id"]) for instance in _load_event_instances(service_client, event_id)
    }
    for entry in body.allocations:
        if entry.instance_id not in valid_instance_ids:
            raise AppError(
                code="invalid_instance",
                message="Instance does not belong to this event",
                http_status=422,
                details={
                    "instance_id": entry.instance_id,
                    "message_key": "vendor.tickets.errors.allocationInstanceInvalid",
                },
            )

    # An allocation may never be set below what has already been sold for that
    # (type, instance) — that would strand issued tickets.
    sold = _sold_by_instance(service_client, ticket_type_id)
    for entry in body.allocations:
        already = sold.get(entry.instance_id, 0)
        if entry.allocation < already:
            raise AppError(
                code="allocation_below_sold",
                message="Allocation is below the number of tickets already sold",
                http_status=422,
                details={
                    "instance_id": entry.instance_id,
                    "allocation": entry.allocation,
                    "sold": already,
                    "message_key": "vendor.tickets.errors.allocationBelowSold",
                },
            )

    kept = {entry.instance_id for entry in body.allocations}
    existing = set(_load_allocations(service_client, ticket_type_id))
    to_delete = sorted(existing - kept)

    # Upsert desired rows first so a cap that should remain is never transiently
    # dropped, then remove the rows for instances no longer capped.
    if body.allocations:
        payload = [
            {
                "ticket_type_id": ticket_type_id,
                "instance_id": entry.instance_id,
                "allocation": entry.allocation,
            }
            for entry in body.allocations
        ]
        service_client.client.table("ticket_type_instances").upsert(
            payload, on_conflict="ticket_type_id,instance_id"
        ).execute()
    if to_delete:
        service_client.client.table("ticket_type_instances").delete().eq(
            "ticket_type_id", ticket_type_id
        ).in_("instance_id", to_delete).execute()

    return _build_allocation_rows(
        service_client, event_id=event_id, ticket_type_id=ticket_type_id
    )


# --- M10-P15: pricing-write helpers + endpoints -----------------------------


def _parse_future_cutoff(raw: str) -> str:
    """Validate an early-bird cutoff: a parseable timestamp strictly in the future.

    Returns the original string to store verbatim (Postgres timestamptz accepts
    ISO-8601). A past cutoff is rejected — it would make the early-bird a silent
    no-op that only confuses the organiser.
    """
    text = raw.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise AppError(
            code="invalid_early_bird_cutoff",
            message="early_bird_until must be a valid ISO-8601 timestamp",
            http_status=422,
            details={"message_key": "vendor.tickets.errors.earlyBirdBadDate"},
        ) from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    if parsed <= datetime.now(UTC):
        raise AppError(
            code="early_bird_cutoff_in_past",
            message="early_bird_until must be in the future",
            http_status=422,
            details={"message_key": "vendor.tickets.errors.earlyBirdPast"},
        )
    return text


def _load_price_tiers(
    service_client: ServiceRoleClient,
    ticket_type_id: str,
) -> list[PriceTierRow]:
    rows = _rows(
        service_client.client.table("ticket_type_price_tiers")
        .select("min_qty, price_ngwee")
        .eq("ticket_type_id", ticket_type_id)
        .order("min_qty")
        .execute()
    )
    return [
        PriceTierRow(min_qty=int(row["min_qty"]), price_ngwee=int(row["price_ngwee"]))
        for row in rows
        if row.get("min_qty") is not None and row.get("price_ngwee") is not None
    ]


def _build_pricing_response(
    service_client: ServiceRoleClient,
    ticket_type: dict[str, Any],
) -> PricingConfigResponse:
    eb_price = ticket_type.get("early_bird_price_ngwee")
    eb_until = ticket_type.get("early_bird_until")
    return PricingConfigResponse(
        ticket_type_id=str(ticket_type["id"]),
        base_price_ngwee=int(ticket_type["price_ngwee"]),
        early_bird_price_ngwee=int(eb_price) if eb_price is not None else None,
        early_bird_until=str(eb_until) if eb_until is not None else None,
        tiers=_load_price_tiers(service_client, str(ticket_type["id"])),
    )


def _assert_discountable(ticket_type: dict[str, Any]) -> int:
    """Discounts only apply to paid ticket types; returns the base price (ngwee)."""
    base_price = int(ticket_type["price_ngwee"])
    if str(ticket_type.get("kind")) == "free_rsvp" or base_price <= 0:
        raise AppError(
            code="pricing_not_allowed_on_free",
            message="Early-bird and group pricing are only allowed on paid ticket types",
            http_status=422,
            details={"message_key": "vendor.tickets.errors.pricingOnFree"},
        )
    return base_price


def _resolve_owned_ticket_type(
    service_client: ServiceRoleClient,
    *,
    ticket_type_id: str,
    owner_user_id: str,
) -> dict[str, Any]:
    """Load a ticket type and assert the authenticated organiser owns its event."""
    vendor = _load_vendor_for_owner(service_client, owner_user_id)
    ticket_type = _load_ticket_type(service_client, ticket_type_id)
    event = _load_event(service_client, str(ticket_type["event_id"]))
    _assert_event_owned(event, str(vendor["id"]), event_id=str(ticket_type["event_id"]))
    return ticket_type


@router.get(
    "/ticket-types/{ticket_type_id}/pricing",
    response_model=PricingConfigResponse,
)
def get_pricing(
    ticket_type_id: str,
    user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> PricingConfigResponse:
    ticket_type = _resolve_owned_ticket_type(
        service_client, ticket_type_id=ticket_type_id, owner_user_id=user.id
    )
    return _build_pricing_response(service_client, ticket_type)


@router.put(
    "/ticket-types/{ticket_type_id}/early-bird",
    response_model=PricingConfigResponse,
)
def set_early_bird(
    ticket_type_id: str,
    body: EarlyBirdPutRequest,
    user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> PricingConfigResponse:
    ticket_type = _resolve_owned_ticket_type(
        service_client, ticket_type_id=ticket_type_id, owner_user_id=user.id
    )

    if body.early_bird_price_ngwee is not None and body.early_bird_until is not None:
        base_price = _assert_discountable(ticket_type)
        if body.early_bird_price_ngwee >= base_price:
            raise AppError(
                code="early_bird_not_a_discount",
                message="The early-bird price must be below the base price",
                http_status=422,
                details={
                    "base_price_ngwee": base_price,
                    "early_bird_price_ngwee": body.early_bird_price_ngwee,
                    "message_key": "vendor.tickets.errors.earlyBirdNotDiscount",
                },
            )
        cutoff = _parse_future_cutoff(body.early_bird_until)
        update: dict[str, Any] = {
            "early_bird_price_ngwee": body.early_bird_price_ngwee,
            "early_bird_until": cutoff,
        }
    else:
        # Clear: both columns back to NULL (satisfies the both-or-neither constraint).
        update = {"early_bird_price_ngwee": None, "early_bird_until": None}

    service_client.client.table("ticket_types").update(update).eq(
        "id", ticket_type_id
    ).execute()

    refreshed = _load_ticket_type(service_client, ticket_type_id)
    return _build_pricing_response(service_client, refreshed)


@router.put(
    "/ticket-types/{ticket_type_id}/price-tiers",
    response_model=PricingConfigResponse,
)
def set_price_tiers(
    ticket_type_id: str,
    body: PriceTiersPutRequest,
    user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> PricingConfigResponse:
    ticket_type = _resolve_owned_ticket_type(
        service_client, ticket_type_id=ticket_type_id, owner_user_id=user.id
    )

    if body.tiers:
        base_price = _assert_discountable(ticket_type)
        for tier in body.tiers:
            if tier.price_ngwee >= base_price:
                raise AppError(
                    code="tier_not_a_discount",
                    message="Each group-tier price must be below the base price",
                    http_status=422,
                    details={
                        "base_price_ngwee": base_price,
                        "min_qty": tier.min_qty,
                        "price_ngwee": tier.price_ngwee,
                        "message_key": "vendor.tickets.errors.tierNotDiscount",
                    },
                )

    kept = {tier.min_qty for tier in body.tiers}
    existing = {row.min_qty for row in _load_price_tiers(service_client, ticket_type_id)}
    to_delete = sorted(existing - kept)

    # Upsert desired rows first so a tier that should stay is never transiently
    # dropped, then remove the min_qty rows no longer wanted.
    if body.tiers:
        payload = [
            {
                "ticket_type_id": ticket_type_id,
                "min_qty": tier.min_qty,
                "price_ngwee": tier.price_ngwee,
            }
            for tier in body.tiers
        ]
        service_client.client.table("ticket_type_price_tiers").upsert(
            payload, on_conflict="ticket_type_id,min_qty"
        ).execute()
    if to_delete:
        service_client.client.table("ticket_type_price_tiers").delete().eq(
            "ticket_type_id", ticket_type_id
        ).in_("min_qty", to_delete).execute()

    refreshed = _load_ticket_type(service_client, ticket_type_id)
    return _build_pricing_response(service_client, refreshed)
