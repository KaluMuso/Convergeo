"""Ticket purchase, RSVP, issuance-on-payment, and claim release."""

from __future__ import annotations

import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.errors import AppError
from app.services.cart.totals import line_total_ngwee
from app.services.commissions.engine import FREE_EVENTS_CATEGORY
from app.services.stock.claim import (
    get_reservation_ttl_minutes,
    run_sql_script,
    sql_int,
    sql_uuid,
)
from app.services.tickets.inventory import claim_ticket_or_raise
from app.services.tickets.qr import generate_pin, generate_qr_secret, seal_pin_storage

EVENT_TICKETS_CATEGORY = "event_tickets"
EVENT_TICKETS_RATE_BPS = 500
FREE_EVENTS_RATE_BPS = 0

_UUID_RE = __import__("re").compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    __import__("re").IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class TicketCheckoutResult:
    checkout_group_id: str
    order_id: str
    order_item_id: str
    claimed_ticket_ids: tuple[str, ...]
    subtotal_ngwee: int
    commission_snapshot: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RsvpResult:
    checkout_group_id: str
    order_id: str
    order_item_id: str
    ticket_ids: tuple[str, ...]
    commission_snapshot: dict[str, Any]


@dataclass(frozen=True, slots=True)
class IssueTicketsResult:
    order_id: str
    issued_count: int
    skipped: bool


@dataclass(frozen=True, slots=True)
class ReleaseClaimResult:
    checkout_group_id: str
    voided_count: int


@dataclass(frozen=True, slots=True)
class ReleaseStaleClaimsResult:
    voided_count: int
    ttl_minutes: int


def _validate_uuid(value: str, field: str) -> None:
    if not _UUID_RE.match(value):
        raise AppError(
            code="validation_error",
            message=f"Invalid UUID for {field}",
            http_status=422,
            details={"field": field},
        )
    UUID(value)


def _validate_attendee_names(
    attendee_names: list[str] | None,
    *,
    qty: int,
    attendee_named: bool,
) -> list[str] | None:
    """Clean/validate per-attendee names against qty and the type's named flag.

    - attendee_named type ⇒ names required: exactly ``qty``, each non-empty.
    - otherwise ⇒ names optional; if supplied, still exactly ``qty`` non-empty.
    Returns the cleaned names, or None when none were supplied for a non-named type.
    """
    if attendee_names is None:
        if attendee_named:
            raise AppError(
                code="tickets.attendee_names_required",
                message="An attendee name is required for each ticket",
                http_status=422,
                details={"message_key": "events.ticketPurchase.errors.attendeeNamesRequired"},
            )
        return None
    cleaned = [name.strip() for name in attendee_names]
    if len(cleaned) != qty or any(not name for name in cleaned):
        raise AppError(
            code="tickets.attendee_names_mismatch",
            message="Provide exactly one non-empty attendee name per ticket",
            http_status=422,
            details={
                "message_key": "events.ticketPurchase.errors.attendeeNamesMismatch",
                "expected": qty,
            },
        )
    return cleaned


def _sql_json(value: dict[str, Any]) -> str:
    payload = json.dumps(value, separators=(",", ":"), sort_keys=True).replace("'", "''")
    return f"'{payload}'::jsonb"


def _sql_json_names(names: list[str] | None) -> str:
    """jsonb literal (or NULL) for order_item_tickets.attendee_names."""
    if not names:
        return "NULL"
    payload = json.dumps(names, separators=(",", ":")).replace("'", "''")
    return f"'{payload}'::jsonb"


def _sql_text_array(names: list[str]) -> str:
    escaped = ", ".join("'" + name.replace("'", "''") + "'" for name in names)
    return f"ARRAY[{escaped}]::text[]"


def _parse_dt(raw: str) -> datetime | None:
    """Parse a Postgres timestamptz text into an aware UTC datetime (None if empty)."""
    text = raw.strip()
    if not text:
        return None
    # Postgres renders '2026-08-01 18:00:00+00'; normalise the space + trailing Z.
    normalized = text.replace(" ", "T", 1).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _load_price_tiers(ticket_type_id: str) -> list[tuple[int, int]]:
    """Return (min_qty, price_ngwee) group-pricing tiers for a ticket type.

    Own single-purpose query (both columns are integers, so the pipe split is
    unambiguous). Empty when the type has no group pricing configured.
    """
    type_sql = sql_uuid(ticket_type_id, "ticket_type_id")
    result = run_sql_script(
        f"""
SELECT min_qty::text, price_ngwee::text
FROM public.ticket_type_price_tiers
WHERE ticket_type_id = {type_sql}
ORDER BY min_qty;
"""
    )
    if not result.ok:
        raise RuntimeError(f"load price tiers failed: {result.error}")
    tiers: list[tuple[int, int]] = []
    for row in result.rows:
        cells = row.split("|")
        if len(cells) != 2:
            continue
        tiers.append((int(cells[0]), int(cells[1])))
    return tiers


def resolve_unit_price(
    *,
    base_price_ngwee: int,
    early_bird_price_ngwee: int | None,
    early_bird_until: datetime | None,
    tiers: list[tuple[int, int]],
    qty: int,
    now: datetime,
) -> int:
    """Server-side per-unit price (M10-P12): the lowest applicable price.

    Candidates are the base price, the early-bird price while ``now`` is before
    its cutoff, and every group tier whose ``min_qty <= qty``. The minimum wins,
    so a buyer always gets the best configured discount and the price can never be
    manipulated from the client. With no early-bird/tier config this returns the
    base price unchanged.
    """
    candidates = [base_price_ngwee]
    if (
        early_bird_price_ngwee is not None
        and early_bird_until is not None
        and now < early_bird_until
    ):
        candidates.append(early_bird_price_ngwee)
    candidates.extend(price for min_qty, price in tiers if qty >= min_qty)
    return min(candidates)


def _load_ticket_context(
    service_client: Any,
    *,
    instance_id: str,
    ticket_type_id: str,
) -> dict[str, Any]:
    del service_client
    instance_sql = sql_uuid(instance_id, "instance_id")
    type_sql = sql_uuid(ticket_type_id, "ticket_type_id")
    script = f"""
SELECT
  tt.id::text,
  tt.event_id::text,
  tt.kind,
  tt.name,
  tt.price_ngwee::text,
  ei.id::text,
  ei.event_id::text,
  ei.capacity::text,
  e.organiser_vendor_id::text,
  e.title,
  e.status,
  tt.attendee_named::text,
  coalesce(tt.early_bird_price_ngwee::text, ''),
  coalesce(tt.early_bird_until::text, ''),
  v.status
FROM public.ticket_types tt
INNER JOIN public.events e ON e.id = tt.event_id
INNER JOIN public.vendors v ON v.id = e.organiser_vendor_id
INNER JOIN public.event_instances ei ON ei.id = {instance_sql}
WHERE tt.id = {type_sql};
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"load ticket context failed: {result.error}")
    if not result.rows:
        raise AppError(
            code="tickets.type_not_found",
            message="Ticket type not found",
            http_status=404,
            details={"ticket_type_id": ticket_type_id},
        )

    parts = result.rows[0].split("|")
    if len(parts) != 15:
        raise RuntimeError("unexpected ticket context row shape")

    if parts[6] != parts[1]:
        raise AppError(
            code="tickets.instance_mismatch",
            message="Ticket type does not belong to this event instance",
            http_status=422,
            details={"instance_id": instance_id, "ticket_type_id": ticket_type_id},
        )
    if parts[10] != "published":
        raise AppError(
            code="tickets.event_not_published",
            message="Event is not available for purchase",
            http_status=409,
            details={"event_id": parts[1]},
        )
    if parts[14] != "active":
        raise AppError(
            code="tickets.organiser_not_active",
            message="Event organiser is not available for purchase",
            http_status=409,
            details={"event_id": parts[1], "organiser_vendor_id": parts[8]},
        )

    return {
        "ticket_type": {
            "id": parts[0],
            "event_id": parts[1],
            "kind": parts[2],
            "name": parts[3],
            "price_ngwee": int(parts[4]),
            "attendee_named": parts[11] == "true",
            "early_bird_price_ngwee": int(parts[12]) if parts[12].strip() else None,
            "early_bird_until": _parse_dt(parts[13]),
        },
        "instance": {
            "id": parts[5],
            "event_id": parts[6],
            "capacity": int(parts[7]),
        },
        "event": {
            "id": parts[1],
            "organiser_vendor_id": parts[8],
            "title": parts[9],
            "status": parts[10],
        },
        "organiser_vendor_id": parts[8],
    }


def _build_ticket_commission_snapshot(
    *,
    ticket_type_id: str,
    instance_id: str,
    ticket_name: str,
    kind: str,
    qty: int,
    unit_price_ngwee: int,
    claimed_ticket_ids: tuple[str, ...] = (),
) -> dict[str, Any]:
    is_free = kind == "free_rsvp"
    category_key = FREE_EVENTS_CATEGORY if is_free else EVENT_TICKETS_CATEGORY
    rate_bps = FREE_EVENTS_RATE_BPS if is_free else EVENT_TICKETS_RATE_BPS
    line_total = line_total_ngwee(qty, unit_price_ngwee)
    snapshot: dict[str, Any] = {
        "lines": [
            {
                "ticket_type_id": ticket_type_id,
                "instance_id": instance_id,
                "category_key": category_key,
                "rate_bps": rate_bps,
                "qty": qty,
                "unit_price_ngwee": unit_price_ngwee,
                "line_total_ngwee": line_total,
                "title_snapshot": ticket_name,
            }
        ],
        "rate_bps": rate_bps,
        "category_key": category_key,
    }
    if claimed_ticket_ids:
        snapshot["ticket_claim_ids"] = list(claimed_ticket_ids)
    return snapshot


def _insert_checkout_spine(
    *,
    customer_id: str,
    organiser_vendor_id: str,
    qty: int,
    unit_price_ngwee: int,
    title_snapshot: str,
    instance_id: str,
    ticket_type_id: str,
    commission_snapshot: dict[str, Any],
    checkout_status: str,
    order_status: str,
    attendee_names: list[str] | None = None,
) -> tuple[str, str, str]:
    checkout_group_id = str(uuid.uuid4())
    order_id = str(uuid.uuid4())
    order_item_id = str(uuid.uuid4())
    subtotal = line_total_ngwee(qty, unit_price_ngwee)
    idempotency_key = f"tkt-{secrets.token_urlsafe(16)}"

    customer_sql = sql_uuid(customer_id, "customer_id")
    group_sql = sql_uuid(checkout_group_id, "checkout_group_id")
    order_sql = sql_uuid(order_id, "order_id")
    item_sql = sql_uuid(order_item_id, "order_item_id")
    vendor_sql = sql_uuid(organiser_vendor_id, "vendor_id")
    instance_sql = sql_uuid(instance_id, "instance_id")
    type_sql = sql_uuid(ticket_type_id, "ticket_type_id")
    qty_sql = sql_int(qty, "qty")
    snapshot_sql = _sql_json(commission_snapshot)
    title_sql = title_snapshot.replace("'", "''")
    names_sql = _sql_json_names(attendee_names)

    script = f"""
BEGIN;
INSERT INTO public.checkout_groups (
  id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee, total_ngwee, status
) VALUES (
  {group_sql}, {customer_sql}, '{idempotency_key}', {subtotal}, 0, {subtotal}, '{checkout_status}'
);
INSERT INTO public.orders (
  id, checkout_group_id, vendor_id, customer_id, status, fulfilment,
  delivery_fee_ngwee, cod, commission_snapshot
) VALUES (
  {order_sql}, {group_sql}, {vendor_sql}, {customer_sql}, '{order_status}', 'pickup',
  0, false, {snapshot_sql}
);
INSERT INTO public.order_items (
  id, order_id, item_kind, qty, unit_price_ngwee, title_snapshot
) VALUES (
  {item_sql}, {order_sql}, 'ticket', {qty_sql}, {unit_price_ngwee}, '{title_sql}'
);
INSERT INTO public.order_item_tickets (order_item_id, ticket_type_id, instance_id, attendee_names)
VALUES ({item_sql}, {type_sql}, {instance_sql}, {names_sql});
COMMIT;
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"ticket checkout spine insert failed: {result.error}")
    return checkout_group_id, order_id, order_item_id


def _update_commission_snapshot(order_id: str, snapshot: dict[str, Any]) -> None:
    order_sql = sql_uuid(order_id, "order_id")
    snapshot_sql = _sql_json(snapshot)
    result = run_sql_script(
        f"UPDATE public.orders SET commission_snapshot = {snapshot_sql} WHERE id = {order_sql};"
    )
    if not result.ok:
        raise RuntimeError(f"commission snapshot update failed: {result.error}")


def add_ticket_to_checkout(
    service_client: Any,
    *,
    customer_id: str,
    instance_id: str,
    ticket_type_id: str,
    qty: int = 1,
    attendee_names: list[str] | None = None,
    now: datetime | None = None,
) -> TicketCheckoutResult:
    """Claim ticket capacity and create a pending checkout order for paid tickets."""
    _validate_uuid(customer_id, "customer_id")
    _validate_uuid(instance_id, "instance_id")
    _validate_uuid(ticket_type_id, "ticket_type_id")
    if qty <= 0:
        raise AppError(
            code="validation_error",
            message="qty must be positive",
            http_status=422,
            details={"field": "qty"},
        )

    ctx = _load_ticket_context(
        service_client, instance_id=instance_id, ticket_type_id=ticket_type_id
    )
    ticket_type = ctx["ticket_type"]
    kind = str(ticket_type.get("kind") or "")
    if kind == "free_rsvp":
        raise AppError(
            code="tickets.free_use_rsvp",
            message="Free events must use the RSVP flow",
            http_status=422,
            details={"message_key": "events.ticketPurchase.errors.freeUseRsvp"},
        )

    names = _validate_attendee_names(
        attendee_names,
        qty=qty,
        attendee_named=bool(ticket_type.get("attendee_named")),
    )
    # Server resolves the per-unit price (M10-P12): base, active early-bird, and
    # qualifying group tiers — lowest wins. The client never supplies a price.
    unit_price = resolve_unit_price(
        base_price_ngwee=int(ticket_type["price_ngwee"]),
        early_bird_price_ngwee=ticket_type.get("early_bird_price_ngwee"),
        early_bird_until=ticket_type.get("early_bird_until"),
        tiers=_load_price_tiers(ticket_type_id),
        qty=qty,
        now=now or datetime.now(UTC),
    )
    title = str(ticket_type.get("name") or "Ticket")
    provisional_snapshot = _build_ticket_commission_snapshot(
        ticket_type_id=ticket_type_id,
        instance_id=instance_id,
        ticket_name=title,
        kind=kind,
        qty=qty,
        unit_price_ngwee=unit_price,
    )

    checkout_group_id, order_id, order_item_id = _insert_checkout_spine(
        customer_id=customer_id,
        organiser_vendor_id=ctx["organiser_vendor_id"],
        qty=qty,
        unit_price_ngwee=unit_price,
        title_snapshot=title,
        instance_id=instance_id,
        ticket_type_id=ticket_type_id,
        commission_snapshot=provisional_snapshot,
        checkout_status="pending",
        order_status="placed",
        attendee_names=names,
    )

    claim = claim_ticket_or_raise(
        service_client,
        instance_id=instance_id,
        ticket_type_id=ticket_type_id,
        holder_user_id=customer_id,
        qty=qty,
    )

    final_snapshot = _build_ticket_commission_snapshot(
        ticket_type_id=ticket_type_id,
        instance_id=instance_id,
        ticket_name=title,
        kind=kind,
        qty=qty,
        unit_price_ngwee=unit_price,
        claimed_ticket_ids=claim.ticket_ids,
    )
    _update_commission_snapshot(order_id, final_snapshot)

    return TicketCheckoutResult(
        checkout_group_id=checkout_group_id,
        order_id=order_id,
        order_item_id=order_item_id,
        claimed_ticket_ids=claim.ticket_ids,
        subtotal_ngwee=line_total_ngwee(qty, unit_price),
        commission_snapshot=final_snapshot,
    )


def _count_issued_for_item(order_item_id: str) -> int:
    item_sql = sql_uuid(order_item_id, "order_item_id")
    result = run_sql_script(
        f"""
SELECT count(*)::text FROM public.tickets
WHERE order_item_id = {item_sql} AND status <> 'void';
"""
    )
    if not result.ok or not result.rows:
        raise RuntimeError(f"ticket count failed: {result.error}")
    return int(result.rows[0])


def _sql_text(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _ticket_secrets(ticket_id: str) -> tuple[str, str]:
    qr_secret = generate_qr_secret()
    pin_hash = seal_pin_storage(pin=generate_pin(), ticket_id=ticket_id)
    return qr_secret, pin_hash


def _link_claimed_tickets(order_item_id: str, ticket_ids: tuple[str, ...]) -> int:
    if not ticket_ids:
        return 0
    item_sql = sql_uuid(order_item_id, "order_item_id")
    linked = 0
    for ticket_id in ticket_ids:
        tid_sql = sql_uuid(ticket_id, "ticket_id")
        qr_secret, pin_hash = _ticket_secrets(ticket_id)
        result = run_sql_script(
            f"""
UPDATE public.tickets
SET
  order_item_id = {item_sql},
  qr_secret = {_sql_text(qr_secret)},
  pin_hash = {_sql_text(pin_hash)}
WHERE id = {tid_sql}
  AND order_item_id IS NULL
  AND status <> 'void'
RETURNING id::text;
"""
        )
        if not result.ok:
            raise RuntimeError(f"link claimed tickets failed: {result.error}")
        if result.rows:
            linked += 1
    return linked


def _load_attendee_names(order_item_id: str) -> list[str] | None:
    """Read an order item's captured attendee names.

    Single-column query so free-text names never collide with the ``|`` row
    separator used by the pipe-split issuance queries.
    """
    item_sql = sql_uuid(order_item_id, "order_item_id")
    result = run_sql_script(
        f"SELECT coalesce(attendee_names::text, '') FROM public.order_item_tickets "
        f"WHERE order_item_id = {item_sql};"
    )
    if not result.ok:
        raise RuntimeError(f"load attendee names failed: {result.error}")
    if not result.rows:
        return None
    raw = result.rows[0].strip()
    if not raw:
        return None
    parsed = json.loads(raw)
    if not isinstance(parsed, list) or not parsed:
        return None
    return [str(name) for name in parsed]


def _assign_holder_names(order_item_id: str, names: list[str]) -> None:
    """Assign attendee names to an item's tickets by creation order (idempotent)."""
    if not names:
        return
    item_sql = sql_uuid(order_item_id, "order_item_id")
    array_sql = _sql_text_array(names)
    script = f"""
WITH src AS (
  SELECT name, ord FROM unnest({array_sql}) WITH ORDINALITY AS n(name, ord)
),
ordered AS (
  SELECT id, row_number() OVER (ORDER BY created_at, id) AS rn
  FROM public.tickets
  WHERE order_item_id = {item_sql} AND status <> 'void'
)
UPDATE public.tickets t
SET holder_name = src.name
FROM ordered o
JOIN src ON src.ord = o.rn
WHERE t.id = o.id;
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"assign holder names failed: {result.error}")


def _insert_issued_tickets(
    *,
    order_item_id: str,
    instance_id: str,
    ticket_type_id: str,
    holder_user_id: str,
    qty: int,
) -> int:
    if qty <= 0:
        return 0
    item_sql = sql_uuid(order_item_id, "order_item_id")
    instance_sql = sql_uuid(instance_id, "instance_id")
    type_sql = sql_uuid(ticket_type_id, "ticket_type_id")
    holder_sql = sql_uuid(holder_user_id, "holder_user_id")
    value_rows: list[str] = []
    for _ in range(qty):
        ticket_id = str(uuid.uuid4())
        tid_sql = sql_uuid(ticket_id, "ticket_id")
        qr_secret, pin_hash = _ticket_secrets(ticket_id)
        value_rows.append(
            f"({tid_sql}, {instance_sql}, {type_sql}, {holder_sql}, {item_sql}, "
            f"'issued', {_sql_text(qr_secret)}, {_sql_text(pin_hash)})"
        )
    values_sql = ",\n".join(value_rows)
    script = f"""
INSERT INTO public.tickets (
  id, instance_id, ticket_type_id, holder_user_id, order_item_id, status,
  qr_secret, pin_hash
)
VALUES
{values_sql};
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"insert issued tickets failed: {result.error}")
    return qty


def issue_tickets_for_paid_order(
    service_client: Any,
    order_id: str,
) -> IssueTicketsResult:
    """Idempotently issue tickets for paid ticket line items (order_item is the idempotency key)."""
    _validate_uuid(order_id, "order_id")
    del service_client

    order_sql = sql_uuid(order_id, "order_id")
    order_result = run_sql_script(
        f"""
SELECT customer_id::text, checkout_group_id::text, commission_snapshot::text
FROM public.orders
WHERE id = {order_sql};
"""
    )
    if not order_result.ok or not order_result.rows:
        raise AppError(
            code="orders.not_found",
            message="Order not found",
            http_status=404,
            details={"order_id": order_id},
        )
    order_parts = order_result.rows[0].split("|")
    customer_id = order_parts[0]
    snapshot = json.loads(order_parts[2]) if order_parts[2] else {}

    items_result = run_sql_script(
        f"""
SELECT
  oi.id::text,
  oi.qty::text,
  oit.instance_id::text,
  oit.ticket_type_id::text
FROM public.order_items oi
INNER JOIN public.order_item_tickets oit ON oit.order_item_id = oi.id
WHERE oi.order_id = {order_sql}
  AND oi.item_kind = 'ticket';
"""
    )
    if not items_result.ok:
        raise RuntimeError(f"load ticket order items failed: {items_result.error}")
    if not items_result.rows:
        return IssueTicketsResult(order_id=order_id, issued_count=0, skipped=True)

    claim_ids: tuple[str, ...] = ()
    raw_claims = snapshot.get("ticket_claim_ids")
    if isinstance(raw_claims, list):
        claim_ids = tuple(str(tid) for tid in raw_claims)

    total_issued = 0
    any_work = False

    for row in items_result.rows:
        parts = row.split("|")
        if len(parts) != 4:
            continue
        order_item_id, qty_raw, instance_id, ticket_type_id = (
            parts[0],
            int(parts[1]),
            parts[2],
            parts[3],
        )
        existing = _count_issued_for_item(order_item_id)
        if existing >= qty_raw:
            continue

        any_work = True
        needed = qty_raw - existing

        linked = 0
        if claim_ids:
            linked = _link_claimed_tickets(order_item_id, claim_ids)
            existing += linked
            needed = max(0, qty_raw - existing)

        if needed > 0:
            inserted = _insert_issued_tickets(
                order_item_id=order_item_id,
                instance_id=instance_id,
                ticket_type_id=ticket_type_id,
                holder_user_id=customer_id,
                qty=needed,
            )
            total_issued += inserted
        else:
            total_issued += linked

        names = _load_attendee_names(order_item_id)
        if names:
            _assign_holder_names(order_item_id, names)

    return IssueTicketsResult(
        order_id=order_id,
        issued_count=total_issued,
        skipped=not any_work,
    )


def release_ticket_claim(
    service_client: Any,
    *,
    checkout_group_id: str,
) -> ReleaseClaimResult:
    """Void unissued ticket claims when payment fails or checkout expires."""
    _validate_uuid(checkout_group_id, "checkout_group_id")
    del service_client

    group_sql = sql_uuid(checkout_group_id, "checkout_group_id")
    script = f"""
WITH order_claims AS (
  SELECT
    o.customer_id,
    o.commission_snapshot -> 'ticket_claim_ids' AS claim_ids
  FROM public.orders o
  WHERE o.checkout_group_id = {group_sql}
),
claim_ids AS (
  SELECT jsonb_array_elements_text(oc.claim_ids)::uuid AS ticket_id
  FROM order_claims oc
  WHERE jsonb_typeof(oc.claim_ids) = 'array'
),
voided AS (
  UPDATE public.tickets t
  SET status = 'void'
  FROM claim_ids c
  WHERE t.id = c.ticket_id
    AND t.order_item_id IS NULL
    AND t.status <> 'void'
  RETURNING t.id
)
SELECT count(*)::text FROM voided;
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"release_ticket_claim failed: {result.error}")
    voided = int(result.rows[0]) if result.rows else 0
    return ReleaseClaimResult(checkout_group_id=checkout_group_id, voided_count=voided)


def rsvp(
    service_client: Any,
    *,
    customer_id: str,
    instance_id: str,
    ticket_type_id: str,
    qty: int = 1,
    attendee_names: list[str] | None = None,
) -> RsvpResult:
    """Free RSVP: claim + issue immediately with 0% commission (no payment)."""
    _validate_uuid(customer_id, "customer_id")
    _validate_uuid(instance_id, "instance_id")
    _validate_uuid(ticket_type_id, "ticket_type_id")
    if qty <= 0:
        raise AppError(
            code="validation_error",
            message="qty must be positive",
            http_status=422,
            details={"field": "qty"},
        )

    ctx = _load_ticket_context(
        service_client, instance_id=instance_id, ticket_type_id=ticket_type_id
    )
    ticket_type = ctx["ticket_type"]
    kind = str(ticket_type.get("kind") or "")
    if kind != "free_rsvp":
        raise AppError(
            code="tickets.paid_use_checkout",
            message="Paid tickets must use checkout",
            http_status=422,
            details={"message_key": "events.ticketPurchase.errors.paidUseCheckout"},
        )

    names = _validate_attendee_names(
        attendee_names,
        qty=qty,
        attendee_named=bool(ticket_type.get("attendee_named")),
    )
    title = str(ticket_type.get("name") or "RSVP")
    unit_price = 1  # schema requires order_items.unit_price_ngwee > 0

    claim = claim_ticket_or_raise(
        service_client,
        instance_id=instance_id,
        ticket_type_id=ticket_type_id,
        holder_user_id=customer_id,
        qty=qty,
    )

    snapshot = _build_ticket_commission_snapshot(
        ticket_type_id=ticket_type_id,
        instance_id=instance_id,
        ticket_name=title,
        kind=kind,
        qty=qty,
        unit_price_ngwee=unit_price,
        claimed_ticket_ids=claim.ticket_ids,
    )

    checkout_group_id, order_id, order_item_id = _insert_checkout_spine(
        customer_id=customer_id,
        organiser_vendor_id=ctx["organiser_vendor_id"],
        qty=qty,
        unit_price_ngwee=unit_price,
        title_snapshot=title,
        instance_id=instance_id,
        ticket_type_id=ticket_type_id,
        commission_snapshot=snapshot,
        checkout_status="completed",
        order_status="completed",
        attendee_names=names,
    )

    _link_claimed_tickets(order_item_id, claim.ticket_ids)
    issued = _count_issued_for_item(order_item_id)
    if issued < qty:
        _insert_issued_tickets(
            order_item_id=order_item_id,
            instance_id=instance_id,
            ticket_type_id=ticket_type_id,
            holder_user_id=customer_id,
            qty=qty - issued,
        )

    if names:
        _assign_holder_names(order_item_id, names)

    final_ids = claim.ticket_ids
    return RsvpResult(
        checkout_group_id=checkout_group_id,
        order_id=order_id,
        order_item_id=order_item_id,
        ticket_ids=final_ids,
        commission_snapshot=snapshot,
    )


def release_stale_ticket_claims(
    service_client: Any,
    *,
    ttl_minutes: int | None = None,
) -> ReleaseStaleClaimsResult:
    """Void unpaid ticket holds older than the reservation TTL (capacity recovery)."""
    del service_client
    ttl = ttl_minutes if ttl_minutes is not None else get_reservation_ttl_minutes()
    if ttl <= 0:
        raise ValueError("ttl_minutes must be positive")
    script = f"""
WITH stale AS (
  SELECT id
  FROM public.tickets
  WHERE order_item_id IS NULL
    AND status = 'issued'
    AND created_at < timezone('utc', now()) - interval '{ttl} minutes'
),
voided AS (
  UPDATE public.tickets t
  SET status = 'void'
  FROM stale s
  WHERE t.id = s.id
  RETURNING t.id
)
SELECT count(*)::text FROM voided;
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"release_stale_ticket_claims failed: {result.error}")
    voided = int(result.rows[0]) if result.rows else 0
    return ReleaseStaleClaimsResult(voided_count=voided, ttl_minutes=ttl)


def find_orders_pending_ticket_issue(service_client: Any) -> list[str]:
    """Orders with successful payment and ticket items not fully issued."""
    script = """
SELECT o.id::text
FROM public.orders o
INNER JOIN public.checkout_groups cg ON cg.id = o.checkout_group_id
INNER JOIN public.payments p ON p.checkout_group_id = cg.id AND p.status = 'success'
INNER JOIN public.order_items oi ON oi.order_id = o.id AND oi.item_kind = 'ticket'
LEFT JOIN LATERAL (
  SELECT count(*)::int AS issued
  FROM public.tickets t
  WHERE t.order_item_id = oi.id AND t.status <> 'void'
) counts ON true
WHERE coalesce(counts.issued, 0) < oi.qty
GROUP BY o.id
ORDER BY o.id;
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"find_orders_pending_ticket_issue failed: {result.error}")
    return list(result.rows)
