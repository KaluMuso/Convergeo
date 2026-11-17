"""Event tickets in the unified cart (unified checkout, slice 1).

A ticket line lives in ``cart_ticket_items`` next to the product lines in
``cart_items``. Nothing here re-implements ticketing: adding a line runs the
same checks as ``POST /tickets/checkout`` (``tickets.purchase``: event
published, organiser active, instance belongs to the type's event, private
event proof, attendee names, no free RSVP); the price is resolved by the same
``resolve_unit_price`` (base / early bird / group tiers) on every read; and
capacity is claimed with the same oversell-safe ``claim_ticket_or_raise`` when
the checkout session starts. Order placement then builds a normal ticket order
(``orders.create``), which the existing issuance, escrow and refund paths own.

Money: integer ngwee only. One event instance per cart (one GMV reservation
and one settlement anchor per checkout group).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from app.errors import AppError
from app.services.cart.totals import line_total_ngwee
from app.services.commissions.engine import FREE_EVENTS_CATEGORY
from app.services.events.fees import (
    commission_rate_bps,
    normalize_fee_payer,
    platform_fee_ngwee,
)
from app.services.orders.audit import sql_literal
from app.services.stock.claim import run_sql_script, sql_int, sql_uuid
from app.services.tickets.inventory import claim_ticket_or_raise
from app.services.tickets.purchase import (
    EVENT_TICKETS_CATEGORY,
    _load_ticket_context,
    _parse_dt,
    _require_private_event_access,
    _validate_attendee_names,
    resolve_unit_price,
)

MAX_TICKET_QTY = 20
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)
_ONE_EVENT_MARKER = "CART_TICKETS_ONE_EVENT"


@dataclass(frozen=True, slots=True)
class TicketCartLine:
    """One ticket line, priced now (list price before any offer)."""

    id: str
    ticket_type_id: str
    instance_id: str
    event_id: str
    vendor_id: str
    qty: int
    unit_price_ngwee: int
    event_title: str
    type_name: str
    kind: str
    fee_payer: str
    event_slug: str | None = None
    starts_at: str | None = None
    attendee_names: tuple[str, ...] | None = None
    available: bool = True
    unavailable_reason: str | None = None
    #: Set by offer pricing: what this line costs after the offer (None = list).
    line_total_ngwee: int | None = None
    offer_id: str | None = None
    offer_snapshot: dict[str, Any] | None = None

    @property
    def list_total_ngwee(self) -> int:
        return line_total_ngwee(self.qty, self.unit_price_ngwee)

    @property
    def total_ngwee(self) -> int:
        return self.line_total_ngwee if self.line_total_ngwee is not None else self.list_total_ngwee

    @property
    def title(self) -> str:
        return f"{self.event_title} · {self.type_name}" if self.type_name else self.event_title


@dataclass(frozen=True, slots=True)
class TicketHold:
    cart_ticket_item_id: str
    ticket_type_id: str
    instance_id: str
    event_id: str
    vendor_id: str
    qty: int
    ticket_ids: tuple[str, ...]


def _require_uuid(value: str, field: str) -> None:
    if not _UUID_RE.match(value or ""):
        raise AppError(
            code="validation_error",
            message=f"Invalid UUID for {field}",
            http_status=422,
            details={"field": field},
        )


def _json_rows(script: str, what: str) -> list[dict[str, Any]]:
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"{what} failed: {result.error}")
    rows: list[dict[str, Any]] = []
    for raw in result.rows:
        if raw.strip():
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                rows.append(parsed)
    return rows


def _int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _line_from_row(row: dict[str, Any], *, now: datetime) -> TicketCartLine:
    qty = _int(row.get("qty")) or 0
    tiers = [
        (int(pair[0]), int(pair[1]))
        for pair in (row.get("tiers") or [])
        if isinstance(pair, list) and len(pair) == 2
    ]
    base = _int(row.get("price_ngwee")) or 0
    early = _int(row.get("early_bird_price_ngwee"))
    early_until = _parse_dt(str(row.get("early_bird_until") or ""))
    unit = resolve_unit_price(
        base_price_ngwee=base,
        early_bird_price_ngwee=early,
        early_bird_until=early_until,
        tiers=tiers,
        qty=max(qty, 1),
        now=now,
    )
    kind = str(row.get("kind") or "")
    reason: str | None = None
    if row.get("event_status") != "published":
        reason = "event_unavailable"
    elif row.get("vendor_status") != "active":
        reason = "organiser_unavailable"
    elif kind == "free_rsvp" or unit <= 0:
        reason = "free_use_rsvp"
    elif qty < 1 or qty > MAX_TICKET_QTY:
        reason = "invalid_qty"
    names_raw = row.get("attendee_names")
    names = (
        tuple(str(name) for name in names_raw) if isinstance(names_raw, list) else None
    )
    return TicketCartLine(
        id=str(row["id"]),
        ticket_type_id=str(row["ticket_type_id"]),
        instance_id=str(row["instance_id"]),
        event_id=str(row["event_id"]),
        vendor_id=str(row["vendor_id"]),
        qty=qty,
        unit_price_ngwee=max(unit, 1),
        event_title=str(row.get("event_title") or ""),
        type_name=str(row.get("type_name") or ""),
        kind=kind,
        fee_payer=normalize_fee_payer(row.get("fee_payer")),
        event_slug=row.get("event_slug") if isinstance(row.get("event_slug"), str) else None,
        starts_at=row.get("starts_at") if isinstance(row.get("starts_at"), str) else None,
        attendee_names=names,
        available=reason is None,
        unavailable_reason=reason,
    )


def cart_has_ticket_lines(client: Any, cart_id: str) -> bool:
    """Cheap PostgREST probe so product-only carts never pay for the ticket read."""
    response = (
        client.table("cart_ticket_items").select("id").eq("cart_id", cart_id).limit(1).execute()
    )
    data = getattr(response, "data", None)
    return isinstance(data, list) and len(data) > 0


def load_cart_ticket_lines(
    cart_id: str, *, now: datetime | None = None, client: Any | None = None
) -> list[TicketCartLine]:
    """Ticket lines of a cart with their live price and availability.

    With ``client`` (service role), an empty cart is answered by a cheap probe.
    """
    _require_uuid(cart_id, "cart_id")
    if client is not None and not cart_has_ticket_lines(client, cart_id):
        return []
    moment = now or datetime.now(UTC)
    rows = _json_rows(
        f"""
SELECT json_build_object(
  'id', c.id, 'ticket_type_id', tt.id, 'instance_id', ei.id, 'event_id', e.id,
  'vendor_id', e.organiser_vendor_id, 'qty', c.qty, 'attendee_names', c.attendee_names,
  'type_name', tt.name, 'kind', tt.kind, 'price_ngwee', tt.price_ngwee,
  'early_bird_price_ngwee', tt.early_bird_price_ngwee,
  'early_bird_until', tt.early_bird_until,
  'event_title', e.title, 'event_slug', e.slug, 'event_status', e.status,
  'vendor_status', v.status, 'fee_payer', e.platform_fee_payer,
  'starts_at', ei.starts_at,
  'tiers', (
    SELECT json_agg(json_build_array(p.min_qty, p.price_ngwee) ORDER BY p.min_qty)
    FROM public.ticket_type_price_tiers p WHERE p.ticket_type_id = tt.id
  )
)::text
FROM public.cart_ticket_items c
JOIN public.ticket_types tt ON tt.id = c.ticket_type_id
JOIN public.event_instances ei ON ei.id = c.instance_id
JOIN public.events e ON e.id = c.event_id
JOIN public.vendors v ON v.id = e.organiser_vendor_id
WHERE c.cart_id = {sql_uuid(cart_id, "cart_id")}
ORDER BY c.created_at, c.id;
""",
        "load cart ticket lines",
    )
    return [_line_from_row(row, now=moment) for row in rows]


def require_purchasable(lines: list[TicketCartLine]) -> None:
    """Checkout gate: every ticket line must still be purchasable as priced."""
    for line in lines:
        if not line.available:
            raise AppError(
                code="cart.ticket_unavailable",
                message="A ticket in your cart is no longer available",
                http_status=409,
                details={
                    "message_key": "checkout.tickets.unavailable",
                    "cart_ticket_item_id": line.id,
                    "reason": line.unavailable_reason,
                    "redirect_to": "cart",
                },
            )


def put_ticket_line(
    service_client: Any,
    *,
    customer_id: str,
    cart_id: str,
    instance_id: str,
    ticket_type_id: str,
    qty: int,
    attendee_names: list[str] | None = None,
    event_access_proof: str | None = None,
) -> str:
    """Add (or set the quantity of) a ticket line, with the direct-purchase checks."""
    for value, field in (
        (customer_id, "customer_id"),
        (cart_id, "cart_id"),
        (instance_id, "instance_id"),
        (ticket_type_id, "ticket_type_id"),
    ):
        _require_uuid(value, field)
    if not 1 <= qty <= MAX_TICKET_QTY:
        raise AppError(
            code="validation_error",
            message="qty must be between 1 and 20",
            http_status=422,
            details={"field": "qty"},
        )
    ctx = _load_ticket_context(
        service_client, instance_id=instance_id, ticket_type_id=ticket_type_id
    )
    _require_private_event_access(
        service_client,
        event_id=str(ctx["event"]["id"]),
        visibility=str(ctx["event"].get("visibility") or "public"),
        access_proof=event_access_proof,
    )
    if str(ctx["ticket_type"].get("kind") or "") == "free_rsvp":
        raise AppError(
            code="tickets.free_use_rsvp",
            message="Free events must use the RSVP flow",
            http_status=422,
            details={"message_key": "events.ticketPurchase.errors.freeUseRsvp"},
        )
    names = _validate_attendee_names(
        attendee_names,
        qty=qty,
        attendee_named=bool(ctx["ticket_type"].get("attendee_named")),
    )
    names_sql = (
        f"{sql_literal(json.dumps(names, separators=(',', ':')))}::jsonb" if names else "NULL"
    )
    result = run_sql_script(
        f"""
INSERT INTO public.cart_ticket_items (cart_id, ticket_type_id, instance_id, event_id, qty,
                                      attendee_names)
SELECT c.id, {sql_uuid(ticket_type_id, "ticket_type_id")}, {sql_uuid(instance_id, "instance_id")},
       {sql_uuid(str(ctx["event"]["id"]), "event_id")}, {sql_int(qty, "qty")}, {names_sql}
FROM public.carts c
WHERE c.id = {sql_uuid(cart_id, "cart_id")} AND c.user_id = {sql_uuid(customer_id, "customer_id")}
ON CONFLICT (cart_id, ticket_type_id, instance_id)
DO UPDATE SET qty = EXCLUDED.qty, attendee_names = EXCLUDED.attendee_names
RETURNING id::text;
"""
    )
    if not result.ok:
        if _ONE_EVENT_MARKER in (result.error or ""):
            raise AppError(
                code="cart.tickets_one_event",
                message="Your cart already has tickets for another event or date",
                http_status=409,
                details={"message_key": "cart.tickets.oneEvent"},
            )
        raise RuntimeError(f"cart ticket upsert failed: {result.error}")
    if not result.rows:
        raise AppError(
            code="cart.not_found", message="Cart not found", http_status=404, details={}
        )
    return result.rows[0].strip()


def remove_ticket_line(*, customer_id: str, cart_id: str, line_id: str) -> bool:
    for value, field in ((customer_id, "customer_id"), (cart_id, "cart_id"), (line_id, "id")):
        _require_uuid(value, field)
    result = run_sql_script(
        f"""
DELETE FROM public.cart_ticket_items ti
USING public.carts c
WHERE ti.id = {sql_uuid(line_id, "id")}
  AND ti.cart_id = {sql_uuid(cart_id, "cart_id")}
  AND c.id = ti.cart_id AND c.user_id = {sql_uuid(customer_id, "customer_id")}
RETURNING ti.id::text;
"""
    )
    if not result.ok:
        raise RuntimeError(f"cart ticket delete failed: {result.error}")
    return bool(result.rows)


# ---------------------------------------------------------------------------
# Money helpers shared by session, fulfilment step and placement
# ---------------------------------------------------------------------------


def ticket_subtotal_ngwee(lines: list[TicketCartLine]) -> int:
    return sum(line.total_ngwee for line in lines)


def ticket_platform_fee_ngwee(lines: list[TicketCartLine]) -> int:
    """Buyer-paid platform fee on what is charged for tickets (after offers).

    Same rule as a ticket bought alone (events.fees): only when the organiser
    passes the fee to the buyer; computed on the charged ticket total of the
    order (one event per cart, so one fee payer).
    """
    if not lines:
        return 0
    payer = normalize_fee_payer(lines[0].fee_payer)
    return platform_fee_ngwee(
        line_total_ngwee=ticket_subtotal_ngwee(lines), fee_payer=payer, is_free=False
    )


def build_ticket_commission_snapshot(
    *,
    lines: list[tuple[TicketCartLine, int, int]],
    claim_ids: list[str],
    platform_fee: int,
) -> dict[str, Any]:
    """Commission snapshot for the ticket order: ``(line, qty, unit_price)`` per order line.

    Mirrors ``tickets.purchase._build_ticket_commission_snapshot`` (event_tickets
    category, fee-payer rate, platform fee, claim ids) for several lines; the
    rate applies to the discounted unit price actually charged.
    """
    if not lines:
        raise ValueError("ticket snapshot needs at least one line")
    payer = normalize_fee_payer(lines[0][0].fee_payer)
    rate_bps = commission_rate_bps(fee_payer=payer, is_free=False)
    snapshot_lines: list[dict[str, Any]] = []
    for line, qty, unit in lines:
        snapshot_lines.append(
            {
                "ticket_type_id": line.ticket_type_id,
                "instance_id": line.instance_id,
                "category_key": EVENT_TICKETS_CATEGORY,
                "rate_bps": rate_bps,
                "qty": qty,
                "unit_price_ngwee": unit,
                "line_total_ngwee": line_total_ngwee(qty, unit),
                "title_snapshot": line.type_name or line.event_title,
            }
        )
    return {
        "lines": snapshot_lines,
        "rate_bps": rate_bps,
        "category_key": EVENT_TICKETS_CATEGORY,
        "fee_payer": payer,
        "platform_fee_ngwee": platform_fee,
        "ticket_claim_ids": list(claim_ids),
        "unified_checkout": True,
    }


assert EVENT_TICKETS_CATEGORY != FREE_EVENTS_CATEGORY  # free RSVPs never enter the cart


# ---------------------------------------------------------------------------
# Capacity holds for a checkout session
# ---------------------------------------------------------------------------


def claim_session_holds(
    service_client: Any,
    *,
    checkout_group_id: str,
    customer_id: str,
    lines: list[TicketCartLine],
    claim: Callable[..., Any] = claim_ticket_or_raise,
) -> list[TicketHold]:
    """Claim capacity for every ticket line and record it on the session.

    A failed claim voids the claims taken so far and re-raises
    (``tickets.oversell`` 409) — no partial hold survives.
    """
    holds: list[TicketHold] = []
    try:
        for line in lines:
            result = claim(
                service_client,
                instance_id=line.instance_id,
                ticket_type_id=line.ticket_type_id,
                holder_user_id=customer_id,
                qty=line.qty,
            )
            holds.append(
                TicketHold(
                    cart_ticket_item_id=line.id,
                    ticket_type_id=line.ticket_type_id,
                    instance_id=line.instance_id,
                    event_id=line.event_id,
                    vendor_id=line.vendor_id,
                    qty=line.qty,
                    ticket_ids=tuple(result.ticket_ids),
                )
            )
        if holds:
            _insert_holds(checkout_group_id, holds)
    except Exception:
        void_ticket_ids([tid for hold in holds for tid in hold.ticket_ids])
        raise
    return holds


def _insert_holds(checkout_group_id: str, holds: list[TicketHold]) -> None:
    values = ",\n".join(
        "({group}, {item}, {tt}, {inst}, {event}, {vendor}, {qty}, ARRAY[{ids}]::uuid[])".format(
            group=sql_uuid(checkout_group_id, "checkout_group_id"),
            item=sql_uuid(hold.cart_ticket_item_id, "cart_ticket_item_id"),
            tt=sql_uuid(hold.ticket_type_id, "ticket_type_id"),
            inst=sql_uuid(hold.instance_id, "instance_id"),
            event=sql_uuid(hold.event_id, "event_id"),
            vendor=sql_uuid(hold.vendor_id, "vendor_id"),
            qty=sql_int(hold.qty, "qty"),
            ids=", ".join(sql_uuid(tid, "ticket_id") for tid in hold.ticket_ids),
        )
        for hold in holds
    )
    result = run_sql_script(
        f"""
INSERT INTO public.checkout_ticket_holds (
  checkout_group_id, cart_ticket_item_id, ticket_type_id, instance_id, event_id,
  organiser_vendor_id, qty, ticket_ids
) VALUES
{values};
"""
    )
    if not result.ok:
        raise RuntimeError(f"insert ticket holds failed: {result.error}")


def void_ticket_ids(ticket_ids: list[str]) -> int:
    """Void unlinked claims (never an issued ticket that belongs to an order)."""
    if not ticket_ids:
        return 0
    ids = ", ".join(sql_uuid(tid, "ticket_id") for tid in ticket_ids)
    result = run_sql_script(
        f"""
WITH voided AS (
  UPDATE public.tickets SET status = 'void'
  WHERE id IN ({ids}) AND order_item_id IS NULL AND status <> 'void'
  RETURNING id
)
SELECT count(*)::text FROM voided;
"""
    )
    if not result.ok:
        raise RuntimeError(f"void ticket claims failed: {result.error}")
    return int(result.rows[0]) if result.rows else 0


def release_session_holds(checkout_group_id: str) -> int:
    """Void a session's unconsumed holds (supersede / abandon); idempotent."""
    _require_uuid(checkout_group_id, "checkout_group_id")
    group_sql = sql_uuid(checkout_group_id, "checkout_group_id")
    result = run_sql_script(
        f"""
WITH released AS (
  UPDATE public.checkout_ticket_holds SET status = 'released'
  WHERE checkout_group_id = {group_sql} AND status = 'held'
  RETURNING ticket_ids
),
voided AS (
  UPDATE public.tickets t SET status = 'void'
  FROM (SELECT unnest(ticket_ids) AS id FROM released) r
  WHERE t.id = r.id AND t.order_item_id IS NULL AND t.status <> 'void'
  RETURNING t.id
)
SELECT count(*)::text FROM voided;
"""
    )
    if not result.ok:
        raise RuntimeError(f"release ticket holds failed: {result.error}")
    return int(result.rows[0]) if result.rows else 0


def load_session_holds(checkout_group_id: str) -> list[TicketHold]:
    _require_uuid(checkout_group_id, "checkout_group_id")
    rows = _json_rows(
        f"""
SELECT json_build_object(
  'cart_ticket_item_id', h.cart_ticket_item_id, 'ticket_type_id', h.ticket_type_id,
  'instance_id', h.instance_id, 'event_id', h.event_id, 'vendor_id', h.organiser_vendor_id,
  'qty', h.qty, 'ticket_ids', to_json(h.ticket_ids)
)::text
FROM public.checkout_ticket_holds h
WHERE h.checkout_group_id = {sql_uuid(checkout_group_id, "checkout_group_id")}
  AND h.status = 'held'
ORDER BY h.ticket_type_id, h.instance_id;
""",
        "load ticket holds",
    )
    return [
        TicketHold(
            cart_ticket_item_id=str(row["cart_ticket_item_id"]),
            ticket_type_id=str(row["ticket_type_id"]),
            instance_id=str(row["instance_id"]),
            event_id=str(row["event_id"]),
            vendor_id=str(row["vendor_id"]),
            qty=int(row["qty"]),
            ticket_ids=tuple(str(tid) for tid in row.get("ticket_ids") or []),
        )
        for row in rows
    ]


def match_holds(lines: list[TicketCartLine], holds: list[TicketHold]) -> dict[str, TicketHold]:
    """Each cart ticket line must be exactly covered by the session's hold.

    The holds were claimed when the session started; a line changed or added
    since (qty, type, date) is not covered, so placement refuses with 410 and
    the buyer restarts checkout (fresh claim) — never an order without capacity.
    """
    by_key = {(h.ticket_type_id, h.instance_id): h for h in holds}
    matched: dict[str, TicketHold] = {}
    for line in lines:
        hold = by_key.get((line.ticket_type_id, line.instance_id))
        if hold is None or hold.qty != line.qty or len(hold.ticket_ids) != line.qty:
            raise AppError(
                code="checkout.reservation_expired",
                message="Your ticket reservation no longer matches your cart",
                http_status=410,
                details={"redirect_to": "cart", "cart_ticket_item_id": line.id},
            )
        matched[line.id] = hold
    if len(matched) != len(holds):
        raise AppError(
            code="checkout.reservation_expired",
            message="Your ticket reservation no longer matches your cart",
            http_status=410,
            details={"redirect_to": "cart"},
        )
    return matched


def with_pricing(
    line: TicketCartLine,
    *,
    line_total_ngwee: int,
    offer_id: str,
    offer_snapshot: dict[str, Any],
) -> TicketCartLine:
    return replace(
        line,
        line_total_ngwee=line_total_ngwee,
        offer_id=offer_id,
        offer_snapshot=offer_snapshot,
    )


def reserve_ticket_gmv(
    service_client: Any,
    *,
    checkout_group_id: str,
    organiser_vendor_id: str,
    event_id: str,
    amount_ngwee: int,
    ttl_minutes: int,
) -> None:
    """Tier-1 organiser GMV headroom for the session's tickets (EVT-GMV-ATOMIC).

    Same reservation, cap and audit as a ticket bought alone
    (``tickets.purchase._insert_checkout_spine``); one per checkout group.
    Raises ``organiser_gmv_cap_exceeded`` (403) when the cap would be passed.
    """
    from app.services.events.gmv_cap import (
        _resolve_cap_tier,
        _write_cap_reject_audit,
        event_paid_gmv_ngwee,
        load_organiser_t1_event_gmv_cap_ngwee,
    )
    from app.services.events.gmv_reservation import (
        _cap_exceeded_error,
        _expires_literal,
        build_atomic_gmv_reserve_sql,
        event_active_reserved_gmv_ngwee,
    )

    if amount_ngwee <= 0:
        return
    tier = _resolve_cap_tier(service_client, organiser_vendor_id)
    if tier >= 2:
        return
    reserve_sql = build_atomic_gmv_reserve_sql(
        checkout_group_id=checkout_group_id,
        organiser_vendor_id=organiser_vendor_id,
        event_id=event_id,
        amount_ngwee=amount_ngwee,
        expires_at_literal=_expires_literal(ttl_minutes=ttl_minutes),
    )
    result = run_sql_script(
        f"""
BEGIN;
{reserve_sql}
DO $$ BEGIN
  IF current_setting('app.gmv_reservation_accepted', true) IS DISTINCT FROM '1' THEN
    RAISE EXCEPTION 'organiser_gmv_cap_exceeded';
  END IF;
END $$;
COMMIT;
"""
    )
    if result.ok:
        return
    if "organiser_gmv_cap_exceeded" not in (result.error or ""):
        raise RuntimeError(f"ticket GMV reservation failed: {result.error}")
    cap_ngwee = load_organiser_t1_event_gmv_cap_ngwee()
    paid = event_paid_gmv_ngwee(event_id)
    reserved = event_active_reserved_gmv_ngwee(event_id)
    _write_cap_reject_audit(
        service_client,
        organiser_vendor_id=organiser_vendor_id,
        event_id=event_id,
        current_gmv_ngwee=paid + reserved,
        additional_ngwee=amount_ngwee,
        cap_ngwee=cap_ngwee,
        cap_tier=tier,
    )
    raise _cap_exceeded_error(
        organiser_vendor_id=organiser_vendor_id,
        event_id=event_id,
        current_gmv_ngwee=paid,
        reserved_gmv_ngwee=reserved,
        additional_ngwee=amount_ngwee,
        cap_ngwee=cap_ngwee,
        cap_tier=tier,
    )
