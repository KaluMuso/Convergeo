"""Atomic checkout → order creation in a single database transaction."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from app.errors import AppError
from app.services.cart.totals import cart_subtotal_ngwee, line_total_ngwee
from app.services.coupons.rules import scale_snapshot_for_vendor_discount
from app.services.coupons.store import map_reservation_error
from app.services.notifications.dedupe import build_dedupe_key
from app.services.orders.audit import sql_literal
from app.services.orders.state import OrderStatus
from app.services.payments.state import expire_checkout_group_if_unpaid
from app.services.stock.claim import run_sql_script, sql_uuid

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

Fulfilment = Literal["delivery", "pickup"]
PaymentMethod = Literal["momo", "card", "cod"]
DEFAULT_COMMISSION_KEY = "default"
OUTBOX_CHANNEL = "whatsapp"
# Registry maps order_placed → vendor_new_order. Use the concrete template name so
# the WhatsApp adapter can render. Prepaid vendor notify is deferred until payment
# SUCCESS (fulfilment-valid); COD notifies at create (collection-at-delivery).
OUTBOX_TEMPLATE = "vendor_new_order"


@dataclass(frozen=True, slots=True)
class CartLineInput:
    cart_item_id: str
    listing_id: str
    vendor_id: str
    qty: int
    unit_price_ngwee: int
    title_snapshot: str | None
    #: Chosen colour/size variant (validated against the listing upstream; the
    #: DB trigger re-checks it belongs to the listing) and its immutable label.
    listing_variant_id: str | None = None
    variant_snapshot: dict[str, Any] | None = None
    #: W8 offers. A cart line an offer priced may be split into two order lines
    #: with integral unit prices; only the first consumes the checkout hold
    #: (for ``reservation_qty`` units, the whole cart line). Gift lines are
    #: price 0, never consume a hold, and reserve from the offer's gift pool.
    consumes_reservation: bool = True
    reservation_qty: int | None = None
    offer_id: str | None = None
    offer_snapshot: dict[str, Any] | None = None
    list_unit_price_ngwee: int | None = None
    offer_discount_ngwee: int = 0
    is_offer_gift: bool = False
    offer_parent_cart_item_id: str | None = None

    @property
    def hold_qty(self) -> int:
        return self.reservation_qty if self.reservation_qty is not None else self.qty


@dataclass(frozen=True, slots=True)
class TicketOrderLineInput:
    """One ticket order line (a ticket cart line may split into two at an offer).

    ``ticket_ids`` are the capacity claims this line consumes (len == qty),
    taken from the checkout session's hold; the order transaction re-checks
    them under row lock before the order exists.
    """

    cart_ticket_item_id: str
    ticket_type_id: str
    instance_id: str
    qty: int
    unit_price_ngwee: int
    title_snapshot: str
    ticket_ids: tuple[str, ...]
    attendee_names: tuple[str, ...] | None = None
    offer_id: str | None = None
    offer_snapshot: dict[str, Any] | None = None
    list_unit_price_ngwee: int | None = None
    offer_discount_ngwee: int = 0


@dataclass(frozen=True, slots=True)
class TicketOrderInput:
    """The organiser's ticket order in a unified checkout (lane ``ticket``)."""

    vendor_id: str
    lines: tuple[TicketOrderLineInput, ...]
    platform_fee_ngwee: int
    commission_snapshot: dict[str, Any]

    @property
    def subtotal_ngwee(self) -> int:
        return sum(line_total_ngwee(line.qty, line.unit_price_ngwee) for line in self.lines)


@dataclass(frozen=True, slots=True)
class VendorFulfilmentInput:
    vendor_id: str
    fulfilment: Fulfilment
    delivery_zone: str | None
    delivery_fee_ngwee: int
    subtotal_ngwee: int
    #: Who pays delivery (logistics phase 1): customer | vendor | vendor_self | platform.
    delivery_funding: str = "customer"
    #: Fee booked to delivery_revenue from the vendor payable / commission (ngwee).
    delivery_funded_ngwee: int = 0


@dataclass(frozen=True, slots=True)
class CouponOrderPlan:
    """Server-recomputed coupon for this checkout (reserved inside the order tx)."""

    coupon_id: str
    funder: Literal["platform", "vendor"]
    discount_ngwee: int
    #: listing_id → discount on that cart line (sums exactly to discount_ngwee).
    line_discounts: dict[str, int]


@dataclass(frozen=True, slots=True)
class CreatedOrderItem:
    order_item_id: str
    listing_id: str
    qty: int
    unit_price_ngwee: int
    line_total_ngwee: int


@dataclass(frozen=True, slots=True)
class CreatedOrder:
    order_id: str
    vendor_id: str
    fulfilment: Fulfilment
    delivery_zone: str | None
    delivery_fee_ngwee: int
    subtotal_ngwee: int
    cod: bool
    commission_snapshot: dict[str, Any]
    items: tuple[CreatedOrderItem, ...]
    coupon_discount_ngwee: int = 0


@dataclass(frozen=True, slots=True)
class CreateOrdersResult:
    checkout_group_id: str
    idempotency_key: str
    status: str
    subtotal_ngwee: int
    delivery_fee_ngwee: int
    total_ngwee: int
    orders: tuple[CreatedOrder, ...]
    replayed: bool = False


def _validate_uuid(value: str, field: str) -> None:
    if not _UUID_RE.match(value):
        raise AppError(
            code="validation_error",
            message=f"Invalid UUID for {field}",
            http_status=422,
            details={"field": field},
        )
    UUID(value)


def _sql_json(value: dict[str, Any]) -> str:
    return sql_literal(json.dumps(value, separators=(",", ":"), sort_keys=True))


# Marker raised inside the locked transaction when the checkout group is no longer
# `pending` (a concurrent submit already completed it) — Python maps it to an
# idempotent replay instead of a hard failure.
_ALREADY_COMPLETED_MARKER = "FIXA_CHECKOUT_ALREADY_COMPLETED"
# Marker raised when the delivery address is not one of the buyer's own.
_ADDRESS_NOT_OWNED_MARKER = "FIXA_ADDRESS_NOT_OWNED"
# Marker raised when a tracked hold vanished or no longer covers the ordered qty
# between the pre-transaction check and the in-tx consumption (#4 oversell guard).
_HOLD_INVALID_MARKER = "FIXA_HOLD_INVALID"
# Marker raised after serializing on a Class-E listing when accepting this cart
# would exceed the vendor's current UTC-week capacity. Its payload is intentionally
# machine-readable so the Python boundary can return a stable customer-facing 409.
_CLASS_E_CAPACITY_MARKER = "FIXA_CLASS_E_CAPACITY_EXCEEDED"
# Raised by public.consume_listing_variant_stock (migration 20261107120000).
_VARIANT_STOCK_ERROR_RE = re.compile(
    r"VARIANT_(?P<kind>OUT_OF_STOCK|UNAVAILABLE):"
    r"(?P<variant_id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)
_CLASS_E_CAPACITY_ERROR_RE = re.compile(
    rf"{_CLASS_E_CAPACITY_MARKER}:"
    r"(?P<listing_id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12}):"
    r"(?P<remaining>\d+):(?P<requested>\d+)",
    re.IGNORECASE,
)


# W8 offers: raised inside the order tx when an offer that priced the cart is no
# longer live, or its gift pool cannot cover the gift line.
_OFFER_EXPIRED_MARKER = "FIXA_OFFER_EXPIRED"
_OFFER_GIFT_MARKER = "FIXA_OFFER_GIFT_UNAVAILABLE"
_OFFER_LIMIT_MARKER = "FIXA_OFFER_LIMIT_REACHED"
_OFFER_ERROR_RE = re.compile(
    r"FIXA_OFFER_(?P<kind>EXPIRED|GIFT_UNAVAILABLE|LIMIT_REACHED):"
    r"(?P<offer_id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)


def _offer_item_columns_sql(line: CartLineInput, *, parent_item_id: str | None) -> tuple[str, str]:
    """Extra order_items columns that freeze the offer pricing on the line."""
    if line.offer_id is None:
        return "", ""
    columns = ", offer_id, offer_snapshot, offer_discount_ngwee, is_offer_gift"
    values = (
        f", {sql_uuid(line.offer_id, 'offer_id')}"
        f", {_sql_json(line.offer_snapshot or {})}::jsonb"
        f", {int(line.offer_discount_ngwee)}"
        f", {'true' if line.is_offer_gift else 'false'}"
    )
    if line.list_unit_price_ngwee is not None:
        columns += ", list_unit_price_ngwee"
        values += f", {int(line.list_unit_price_ngwee)}"
    if parent_item_id is not None:
        columns += ", offer_parent_item_id"
        values += f", {sql_uuid(parent_item_id, 'offer_parent_item_id')}"
    return columns, values


def _lock_live_offers_sql(offer_id_values: Iterable[str], customer_sql: str) -> list[str]:
    """Row-lock (id order) every offer that priced this cart; abort if one is not live.

    FOR UPDATE rather than FOR SHARE: a gift pool is updated later in the same
    tx, and two share-holders upgrading would deadlock.

    The per-customer limit is enforced here, under that lock: a second order of
    the same customer for the same offer blocks on the row lock until the first
    commits, and the redemption count (a later statement, so a fresh READ
    COMMITTED snapshot) then sees the first order. Two simultaneous orders can
    never both pass. A redemption = a distinct checkout of this customer with an
    order carrying the offer (a product + ticket bundle places two orders in one
    checkout: one redemption), not cancelled, whose checkout did not expire
    unpaid / get abandoned (the same rule ``store.customer_offer_use_counts``).
    """
    offer_ids = sorted({str(offer_id) for offer_id in offer_id_values if offer_id})
    statements: list[str] = []
    for offer_id in offer_ids:
        offer_sql = sql_uuid(offer_id, "offer_id")
        statements.append(
            f"""
DO $offer$
DECLARE
  v_limit integer;
  v_used integer;
BEGIN
  SELECT o.per_customer_limit INTO v_limit FROM public.offers o
  WHERE o.id = {offer_sql}
    AND o.status = 'active'
    AND NOT o.paused_by_admin
    AND o.starts_at <= timezone('utc', now())
    AND (o.ends_at IS NULL OR o.ends_at > timezone('utc', now()))
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION '{_OFFER_EXPIRED_MARKER}:%', {sql_literal(offer_id)};
  END IF;
  IF v_limit IS NOT NULL THEN
    SELECT count(DISTINCT ord.checkout_group_id)::integer INTO v_used
    FROM public.order_items oi
    JOIN public.orders ord ON ord.id = oi.order_id
    LEFT JOIN public.checkout_groups cg ON cg.id = ord.checkout_group_id
    WHERE oi.offer_id = {offer_sql}
      AND ord.customer_id = {customer_sql}
      AND ord.status <> 'cancelled'
      AND coalesce(cg.status, '') NOT IN ('expired', 'abandoned');
    IF v_used >= v_limit THEN
      RAISE EXCEPTION '{_OFFER_LIMIT_MARKER}:%', {sql_literal(offer_id)};
    END IF;
  END IF;
END
$offer$;
"""
        )
    return statements


def _reserve_offer_gift_sql(*, offer_id: str, order_id: str, order_item_id: str, qty: int) -> str:
    offer_sql = sql_uuid(offer_id, "offer_id")
    qty_sql = str(int(qty))
    return f"""
DO $gift$
DECLARE
  v_updated int;
BEGIN
  UPDATE public.offers
  SET gift_stock_reserved = gift_stock_reserved + {qty_sql}
  WHERE id = {offer_sql}
    AND gift_stock_total IS NOT NULL
    AND gift_stock_reserved + {qty_sql} <= gift_stock_total;
  GET DIAGNOSTICS v_updated = ROW_COUNT;
  IF v_updated = 0 THEN
    RAISE EXCEPTION '{_OFFER_GIFT_MARKER}:%', {sql_literal(offer_id)};
  END IF;
  INSERT INTO public.offer_gift_reservations (offer_id, order_id, order_item_id, qty)
  VALUES ({offer_sql}, {sql_uuid(order_id, "order_id")},
          {sql_uuid(order_item_id, "order_item_id")}, {qty_sql});
END
$gift$;
"""


def _ticket_claims_valid_sql(*, customer_sql: str, line: TicketOrderLineInput) -> str:
    """Abort unless every claim of the line is still a live, unlinked claim of this
    buyer for this type and instance (row-locked, so issuance / the stale sweeper
    cannot race it). A voided or reused claim -> FIXA_HOLD_INVALID (410)."""
    ids = ", ".join(sql_uuid(tid, "ticket_id") for tid in line.ticket_ids)
    return f"""
DO $tk$
DECLARE
  v_n integer;
BEGIN
  SELECT count(*)::integer INTO v_n FROM (
    SELECT t.id FROM public.tickets t
    WHERE t.id IN ({ids})
      AND t.status = 'issued'
      AND t.order_item_id IS NULL
      AND t.holder_user_id = {customer_sql}
      AND t.ticket_type_id = {sql_uuid(line.ticket_type_id, "ticket_type_id")}
      AND t.instance_id = {sql_uuid(line.instance_id, "instance_id")}
    ORDER BY t.id
    FOR UPDATE
  ) claims;
  IF v_n <> {int(len(line.ticket_ids))} OR v_n <> {int(line.qty)} THEN
    RAISE EXCEPTION '{_HOLD_INVALID_MARKER}:%', {sql_literal(line.ticket_type_id)};
  END IF;
END
$tk$;
"""


def _consume_ticket_holds_sql(*, session_sql: str, order_sql: str, expected: int) -> str:
    return f"""
DO $th$
DECLARE
  v_n integer;
BEGIN
  UPDATE public.checkout_ticket_holds
  SET status = 'consumed', order_id = {order_sql}
  WHERE checkout_group_id = {session_sql} AND status = 'held';
  GET DIAGNOSTICS v_n = ROW_COUNT;
  IF v_n <> {int(expected)} THEN
    RAISE EXCEPTION '{_HOLD_INVALID_MARKER}:holds';
  END IF;
END
$th$;
"""


def _ticket_order_sql(
    *,
    ticket_order: TicketOrderInput,
    order_id: str,
    item_ids: list[str],
    session_sql: str,
    customer_sql: str,
    hold_count: int,
) -> list[str]:
    order_sql = sql_uuid(order_id, "order_id")
    statements = [
        _ticket_claims_valid_sql(customer_sql=customer_sql, line=line)
        for line in sorted(ticket_order.lines, key=lambda ln: (ln.ticket_type_id, ln.instance_id))
    ]
    statements.append(
        f"""
INSERT INTO public.orders (
  id, checkout_group_id, vendor_id, customer_id, status, fulfilment,
  delivery_fee_ngwee, platform_fee_ngwee, cod, commission_snapshot, order_lane
) VALUES (
  {order_sql}, {session_sql}, {sql_uuid(ticket_order.vendor_id, "vendor_id")}, {customer_sql},
  '{OrderStatus.PLACED.value}', 'pickup', 0, {int(ticket_order.platform_fee_ngwee)}, false,
  {_sql_json(ticket_order.commission_snapshot)}::jsonb, 'ticket'
);
"""
    )
    for line, item_id in zip(ticket_order.lines, item_ids, strict=True):
        item_sql = sql_uuid(item_id, "order_item_id")
        offer_columns = ""
        offer_values = ""
        if line.offer_id is not None:
            offer_columns = ", offer_id, offer_snapshot, offer_discount_ngwee"
            offer_values = (
                f", {sql_uuid(line.offer_id, 'offer_id')}"
                f", {_sql_json(line.offer_snapshot or {})}::jsonb"
                f", {int(line.offer_discount_ngwee)}"
            )
            if line.list_unit_price_ngwee is not None:
                offer_columns += ", list_unit_price_ngwee"
                offer_values += f", {int(line.list_unit_price_ngwee)}"
        names_sql = (
            f"{sql_literal(json.dumps(list(line.attendee_names), separators=(',', ':')))}::jsonb"
            if line.attendee_names
            else "NULL"
        )
        statements.append(
            f"""
INSERT INTO public.order_items (
  id, order_id, item_kind, qty, unit_price_ngwee, title_snapshot{offer_columns}
) VALUES (
  {item_sql}, {order_sql}, 'ticket', {int(line.qty)}, {int(line.unit_price_ngwee)},
  {sql_literal(line.title_snapshot)}{offer_values}
);
INSERT INTO public.order_item_tickets (order_item_id, ticket_type_id, instance_id, attendee_names)
VALUES ({item_sql}, {sql_uuid(line.ticket_type_id, "ticket_type_id")},
        {sql_uuid(line.instance_id, "instance_id")}, {names_sql});
"""
        )
    statements.append(
        _consume_ticket_holds_sql(session_sql=session_sql, order_sql=order_sql, expected=hold_count)
    )
    return statements


def _lock_and_recheck_sql(session_sql: str, customer_sql: str) -> str:
    """Lock the checkout group and re-verify status='pending' INSIDE the transaction.

    This lock + recheck is the real serialization for #2: a second concurrent
    submit blocks on the row lock, then observes the now-`completed` status the
    first submit committed and aborts via ``_ALREADY_COMPLETED_MARKER`` — so only
    one order set is ever created. The UNIQUE index (migration 0031) is the DB
    backstop behind it.
    """
    return f"""
DO $lock$
DECLARE
  v_status text;
BEGIN
  SELECT status INTO v_status
  FROM public.checkout_groups
  WHERE id = {session_sql} AND customer_id = {customer_sql}
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'checkout group not found';
  END IF;
  IF v_status <> 'pending' THEN
    RAISE EXCEPTION '{_ALREADY_COMPLETED_MARKER}:%', v_status;
  END IF;
  -- A prepaid group stays 'pending' after its orders are placed (it completes on
  -- payment success), so 'pending' alone no longer means "no orders yet".
  IF EXISTS (
    SELECT 1 FROM public.orders WHERE checkout_group_id = {session_sql}
  ) THEN
    RAISE EXCEPTION '{_ALREADY_COMPLETED_MARKER}:placed';
  END IF;
END
$lock$;
"""


def _require_own_address_sql(address_sql: str, customer_sql: str) -> str:
    """Abort unless the delivery address belongs to the buyer placing the order.

    ``address_id`` arrives from the client. Without this check an order could be
    attached to any address row, sending a courier to (and showing the buyer the
    landmark and phone of) somebody else.
    """
    return f"""
DO $address$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM public.addresses
    WHERE id = {address_sql} AND user_id = {customer_sql}
  ) THEN
    RAISE EXCEPTION '{_ADDRESS_NOT_OWNED_MARKER}';
  END IF;
END
$address$;
"""


def _consume_reservation_conditional_sql(
    *,
    checkout_group_id: str,
    listing_id: str,
    qty: int,
    order_id: str,
    order_item_id: str,
    listing_variant_id: str | None = None,
) -> str:
    """Consume one tracked hold, aborting the tx if it is gone or too small (#4).

    Stock is decremented at claim time; consuming the hold just deletes its row.
    A conditional DELETE that must return a row proves the hold still existed and
    still covered the ordered qty. If a sweeper reclaimed (restocked) the hold in
    the meantime, no row matches and we abort the whole transaction — no partial
    order, no oversell. Non-tracked and made-to-order listings never create stock
    holds, so they are skipped here as well.

    In the same transaction it records what this order line took from stock —
    the hold's quantity and branch, and the variant quantity decremented by
    ``consume_listing_variant_stock`` (which runs earlier in the script) — so a
    pre-dispatch cancellation can put back exactly that, once
    (``public.release_cancelled_order_stock``).
    """
    group_sql = sql_uuid(checkout_group_id, "checkout_group_id")
    listing_sql = sql_uuid(listing_id, "listing_id")
    listing_literal = sql_literal(listing_id)
    order_sql = sql_uuid(order_id, "order_id")
    item_sql = sql_uuid(order_item_id, "order_item_id")
    variant_sql = (
        sql_uuid(listing_variant_id, "listing_variant_id")
        if listing_variant_id is not None
        else "NULL::uuid"
    )
    qty_sql = str(int(qty))
    return f"""
DO $consume$
DECLARE
  v_mode text;
  v_product_class text;
  v_fulfilment_mode text;
  v_deleted int;
  v_location uuid;
  v_listing_qty int := 0;
  v_variant_qty int := 0;
BEGIN
  SELECT stock_mode, product_class, fulfilment_mode
  INTO v_mode, v_product_class, v_fulfilment_mode
  FROM public.vendor_listings
  WHERE id = {listing_sql};
  IF v_mode = 'tracked'
     AND v_product_class IS DISTINCT FROM 'E'
     AND v_fulfilment_mode IS DISTINCT FROM 'made_to_order' THEN
    DELETE FROM public.stock_reservations
    WHERE checkout_group_id = {group_sql}
      AND listing_id = {listing_sql}
      AND qty >= {qty_sql}
    RETURNING location_id INTO v_location;
    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    IF v_deleted = 0 THEN
      RAISE EXCEPTION '{_HOLD_INVALID_MARKER}:%', {listing_literal};
    END IF;
    v_listing_qty := {qty_sql};
  END IF;
  IF {variant_sql} IS NOT NULL AND EXISTS (
    SELECT 1 FROM public.vendor_listing_variants
    WHERE id = {variant_sql} AND stock_qty IS NOT NULL
  ) THEN
    v_variant_qty := {qty_sql};
  END IF;
  IF v_listing_qty > 0 OR v_variant_qty > 0 THEN
    INSERT INTO public.order_item_stock_consumption (
      order_item_id, order_id, listing_id, listing_qty, location_id,
      listing_variant_id, variant_qty
    ) VALUES (
      {item_sql}, {order_sql}, {listing_sql}, v_listing_qty, v_location,
      {variant_sql}, v_variant_qty
    );
  END IF;
END
$consume$;
"""


def _aggregate_listing_quantities(cart_lines: list[CartLineInput]) -> dict[str, int]:
    """Return one requested quantity per listing in deterministic UUID order."""
    quantities: dict[str, int] = {}
    for line in cart_lines:
        quantities[line.listing_id] = quantities.get(line.listing_id, 0) + line.qty
    return dict(sorted(quantities.items()))


def _lock_and_check_class_e_capacity_sql(
    requested_by_listing: dict[str, int],
) -> str:
    """Serialize Class-E acceptance and enforce the current UTC-week capacity.

    Every requested listing is locked in UUID order before any capacity is read.
    That makes overlapping checkouts use one consistent lock order and ensures a
    waiter sees order items committed by the transaction that held the lock first.
    Only explicit Class E is capacity-governed; legacy non-E made-to-order listings
    intentionally retain their existing uncapped behaviour.
    """
    if not requested_by_listing:
        return ""

    requested_values = ",\n    ".join(
        f"({sql_uuid(listing_id, 'listing_id')}, {int(qty)})"
        for listing_id, qty in sorted(requested_by_listing.items())
    )
    return f"""
DO $capacity$
DECLARE
  v_listing_id uuid;
  v_product_class text;
  v_capacity integer;
  v_requested integer;
  v_committed bigint;
  v_remaining bigint;
  v_week_start timestamptz :=
    date_trunc('week', timezone('UTC', now())) AT TIME ZONE 'UTC';
BEGIN
  -- Lock all requested listings before checking any of them. Stable UUID order
  -- prevents deadlocks when carts overlap on more than one listing.
  PERFORM vl.id
  FROM public.vendor_listings AS vl
  JOIN (VALUES
    {requested_values}
  ) AS requested(listing_id, qty) ON requested.listing_id = vl.id
  ORDER BY vl.id
  FOR UPDATE OF vl;

  FOR v_listing_id, v_product_class, v_capacity, v_requested IN
    SELECT
      vl.id,
      vl.product_class::text,
      vl.vendor_capacity_per_week,
      requested.qty
    FROM public.vendor_listings AS vl
    JOIN (VALUES
      {requested_values}
    ) AS requested(listing_id, qty) ON requested.listing_id = vl.id
    ORDER BY vl.id
  LOOP
    IF v_product_class = 'E' THEN
      SELECT coalesce(sum(oi.qty), 0)
      INTO v_committed
      FROM public.order_item_products AS oip
      JOIN public.order_items AS oi ON oi.id = oip.order_item_id
      JOIN public.orders AS o ON o.id = oi.order_id
      WHERE oip.listing_id = v_listing_id
        AND o.status NOT IN ('cancelled', 'refunded')
        AND o.created_at >= v_week_start
        AND o.created_at < v_week_start + interval '1 week';

      IF v_capacity IS NULL OR v_committed + v_requested > v_capacity THEN
        v_remaining := greatest(coalesce(v_capacity, 0) - v_committed, 0);
        RAISE EXCEPTION '{_CLASS_E_CAPACITY_MARKER}:%:%:%',
          v_listing_id, v_remaining, v_requested;
      END IF;
    END IF;
  END LOOP;
END
$capacity$;
"""


def _consume_reservations_sql(checkout_group_id: str) -> str:
    """Delete any leftover reservations for the group (cleanup after conditional
    consumption; stock already decremented at claim, so no restock)."""
    group_sql = sql_uuid(checkout_group_id, "checkout_group_id")
    return f"DELETE FROM public.stock_reservations WHERE checkout_group_id = {group_sql};"


def _clear_ordered_cart_lines_sql(cart_lines: list[CartLineInput], customer_sql: str) -> str:
    """Take the lines that just became a COD order out of the buyer's cart.

    A cash-on-delivery order is final the moment it is placed, so leaving its
    lines in the cart let the buyer check the same goods out a second time.
    Only the exact ordered rows go, and only from the buyer's own cart: a line
    added in another tab after checkout started was never ordered and stays.
    Prepaid checkouts keep their cart until the payment outcome is known.
    """
    # Offer gift lines have no cart row; a split offer line shares one cart row.
    cart_item_ids = list(
        dict.fromkeys(line.cart_item_id for line in cart_lines if not line.is_offer_gift)
    )
    if not cart_item_ids:
        return ""
    item_ids = ", ".join(sql_uuid(item_id, "cart_item_id") for item_id in cart_item_ids)
    return f"""
DELETE FROM public.cart_items ci
USING public.carts c
WHERE ci.id IN ({item_ids})
  AND c.id = ci.cart_id
  AND c.user_id = {customer_sql};
"""


def _fetch_existing_by_idempotency_key(
    client: Any, *, idempotency_key: str, customer_id: str
) -> dict[str, Any] | None:
    response = (
        client.table("checkout_groups")
        .select("*")
        .eq("idempotency_key", idempotency_key)
        .eq("customer_id", customer_id)
        .maybe_single()
        .execute()
    )
    # PostgREST's maybe_single() returns None when the idempotency key has no
    # row. That is the normal first-order path, not a failed read.
    data = response.data if response is not None else None
    return data if isinstance(data, dict) else None


def _fetch_checkout_session(client: Any, *, session_id: str, customer_id: str) -> dict[str, Any]:
    response = (
        client.table("checkout_groups")
        .select("*")
        .eq("id", session_id)
        .eq("customer_id", customer_id)
        .maybe_single()
        .execute()
    )
    row = response.data if response is not None else None
    if not isinstance(row, dict):
        raise AppError(
            code="checkout.session_not_found",
            message="Checkout session not found",
            http_status=404,
            details={"session_id": session_id},
        )
    return row


def _session_expired(client: Any, session_id: str) -> bool:
    response = (
        client.table("stock_reservations")
        .select("expires_at")
        .eq("checkout_group_id", session_id)
        .order("expires_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = response.data if isinstance(response.data, list) else []
    if not rows or not isinstance(rows[0], dict):
        return False
    raw = rows[0].get("expires_at")
    if not isinstance(raw, str):
        return False
    expires_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return expires_at <= datetime.now(UTC)


def _load_commission_rates(client: Any) -> dict[str, int]:
    response = client.table("commission_rates").select("category_key, rate_bps").execute()
    rows = response.data if isinstance(response.data, list) else []
    rates: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = row.get("category_key")
        bps = row.get("rate_bps")
        if isinstance(key, str) and isinstance(bps, int):
            rates[key] = bps
    return rates


def _load_listing_commission_keys(client: Any, listing_ids: list[str]) -> dict[str, str]:
    if not listing_ids:
        return {}
    response = (
        client.table("vendor_listings")
        .select("id, product_id, products(category_id, categories(commission_key))")
        .in_("id", listing_ids)
        .execute()
    )
    rows = response.data if isinstance(response.data, list) else []
    keys: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            continue
        listing_id = str(row["id"])
        product = row.get("products")
        if not isinstance(product, dict):
            keys[listing_id] = DEFAULT_COMMISSION_KEY
            continue
        category = product.get("categories")
        if isinstance(category, dict) and isinstance(category.get("commission_key"), str):
            keys[listing_id] = category["commission_key"]
        else:
            keys[listing_id] = DEFAULT_COMMISSION_KEY
    return keys


def _build_commission_snapshot(
    *,
    lines: list[CartLineInput],
    commission_keys: dict[str, str],
    commission_rates: dict[str, int],
) -> dict[str, Any]:
    snapshot_lines: list[dict[str, Any]] = []
    for line in lines:
        category_key = commission_keys.get(line.listing_id, DEFAULT_COMMISSION_KEY)
        rate_bps = commission_rates.get(
            category_key, commission_rates.get(DEFAULT_COMMISSION_KEY, 0)
        )
        snapshot_lines.append(
            {
                "listing_id": line.listing_id,
                "category_key": category_key,
                "rate_bps": rate_bps,
                "qty": line.qty,
                "unit_price_ngwee": line.unit_price_ngwee,
                "line_total_ngwee": line_total_ngwee(line.qty, line.unit_price_ngwee),
            }
        )
    primary_rate = snapshot_lines[0]["rate_bps"] if len(snapshot_lines) == 1 else None
    payload: dict[str, Any] = {"lines": snapshot_lines}
    if primary_rate is not None:
        payload["rate_bps"] = primary_rate
    return payload


def _load_vendor_owner_ids(client: Any, vendor_ids: list[str]) -> dict[str, str]:
    """Owner account per vendor — the recipient of that vendor's notifications."""
    if not vendor_ids:
        return {}
    response = client.table("vendors").select("id, owner_user_id").in_("id", vendor_ids).execute()
    rows = response.data if isinstance(response.data, list) else []
    owners: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        vendor_id = row.get("id")
        owner_id = row.get("owner_user_id")
        if isinstance(vendor_id, str) and isinstance(owner_id, str) and owner_id:
            owners[vendor_id] = owner_id
    return owners


def _load_product_names(client: Any, product_ids: list[str]) -> dict[str, str]:
    if not product_ids:
        return {}
    response = client.table("products").select("id, name").in_("id", product_ids).execute()
    rows = response.data if isinstance(response.data, list) else []
    names: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        product_id = row.get("id")
        name = row.get("name")
        if isinstance(product_id, str) and isinstance(name, str) and name.strip():
            names[product_id] = name.strip()
    return names


def order_display_reference(order_id: str) -> str:
    """The short order number the vendor and customer apps show (``1A2B3C4D``)."""
    return order_id.replace("-", "")[:8].upper()


def _vendor_new_order_payload(
    *,
    order: CreatedOrder,
    lines: list[CartLineInput],
    session_id: str,
    customer_id: str,
    owner_user_id: str | None,
    product_ids: dict[str, str],
    product_names: dict[str, str],
) -> dict[str, Any]:
    """Outbox payload the ``vendor_new_order`` templates can actually render.

    The dispatcher addresses a row only through ``recipient_id`` and the WhatsApp
    template requires ``order_reference``, ``product_title`` and ``quantity``. The
    COD row used to carry none of them, so a vendor was never told about a new
    cash-on-delivery order on any channel.
    """
    titles: list[str] = []
    for line in lines:
        title = (line.title_snapshot or "").strip()
        if not title:
            title = product_names.get(product_ids.get(line.listing_id, ""), "")
        if title:
            titles.append(title)
    if not titles:
        product_title = order_display_reference(order.order_id)
    elif len(lines) > 1:
        product_title = f"{titles[0]} +{len(lines) - 1}"
    else:
        product_title = titles[0]
    payload: dict[str, Any] = {
        "order_id": order.order_id,
        "checkout_group_id": session_id,
        "vendor_id": order.vendor_id,
        "customer_id": customer_id,
        "order_reference": order_display_reference(order.order_id),
        "product_title": product_title,
        "quantity": sum(line.qty for line in lines),
    }
    if owner_user_id:
        payload["recipient_id"] = owner_user_id
    return payload


def _load_orders_for_group(client: Any, checkout_group_id: str) -> tuple[CreatedOrder, ...]:
    group_sql = sql_uuid(checkout_group_id, "checkout_group_id")
    script = f"""
SELECT
  o.id::text,
  o.vendor_id::text,
  o.fulfilment,
  coalesce(o.delivery_zone, ''),
  o.delivery_fee_ngwee::text,
  o.cod::text,
  o.commission_snapshot::text
FROM public.orders o
WHERE o.checkout_group_id = {group_sql}
ORDER BY o.vendor_id;
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"load orders failed: {result.error}")

    created: list[CreatedOrder] = []
    for row in result.rows:
        parts = row.split("|")
        if len(parts) != 7:
            continue
        order_id = parts[0]
        items_script = f"""
SELECT
  oi.id::text,
  oi.qty::text,
  oi.unit_price_ngwee::text,
  coalesce(oip.listing_id::text, '')
FROM public.order_items oi
LEFT JOIN public.order_item_products oip ON oip.order_item_id = oi.id
WHERE oi.order_id = '{order_id}'::uuid
ORDER BY oi.id;
"""
        items_result = run_sql_script(items_script)
        if not items_result.ok:
            raise RuntimeError(f"load order items failed: {items_result.error}")
        items: list[CreatedOrderItem] = []
        subtotal = 0
        for item_row in items_result.rows:
            item_parts = item_row.split("|")
            if len(item_parts) != 4:
                continue
            qty = int(item_parts[1])
            unit_price = int(item_parts[2])
            line_total = line_total_ngwee(qty, unit_price)
            subtotal += line_total
            items.append(
                CreatedOrderItem(
                    order_item_id=item_parts[0],
                    listing_id=item_parts[3],
                    qty=qty,
                    unit_price_ngwee=unit_price,
                    line_total_ngwee=line_total,
                )
            )
        commission_snapshot = json.loads(parts[6]) if parts[6] else {}
        created.append(
            CreatedOrder(
                order_id=order_id,
                vendor_id=parts[1],
                fulfilment=parts[2],  # type: ignore[arg-type]
                delivery_zone=parts[3] or None,
                delivery_fee_ngwee=int(parts[4]),
                subtotal_ngwee=subtotal,
                cod=parts[5] in ("t", "true"),
                commission_snapshot=commission_snapshot,
                items=tuple(items),
            )
        )
    return tuple(created)


def _result_from_group(group: dict[str, Any], *, client: Any, replayed: bool) -> CreateOrdersResult:
    group_id = str(group["id"])
    orders = _load_orders_for_group(client, group_id)
    return CreateOrdersResult(
        checkout_group_id=group_id,
        idempotency_key=str(group["idempotency_key"]),
        status=str(group.get("status") or "completed"),
        subtotal_ngwee=int(group.get("subtotal_ngwee", 0)),
        delivery_fee_ngwee=int(group.get("delivery_fee_ngwee", 0)),
        total_ngwee=int(group.get("total_ngwee", 0)),
        orders=orders,
        replayed=replayed,
    )


def checkout_has_orders(client: Any, *, checkout_group_id: str) -> bool:
    """True once orders exist for the checkout group.

    A COD checkout is marked ``completed`` when its orders are placed, but a
    prepaid (mobile money / card) checkout stays ``pending`` until the payment
    succeeds, because ``claim_payable_payment`` only claims a ``pending`` group.
    So "has this session been ordered" is answered by the orders themselves, not
    by ``checkout_groups.status`` alone.
    """
    response = (
        client.table("orders")
        .select("id")
        .eq("checkout_group_id", checkout_group_id)
        .limit(1)
        .execute()
    )
    data = getattr(response, "data", None)
    return isinstance(data, list) and len(data) > 0


def _is_ordered(client: Any, group: dict[str, Any]) -> bool:
    """The group's orders are placed: ``completed`` (COD / paid) or ``pending`` with orders."""
    status = str(group.get("status"))
    if status == "completed":
        return True
    if status != "pending":
        return False
    return checkout_has_orders(client, checkout_group_id=str(group["id"]))


def _resolve_completed_after_race(
    client: Any,
    *,
    session_id: str,
    customer_id: str,
    idempotency_key: str,
) -> CreateOrdersResult:
    """Return the idempotent result after a concurrent submit placed the orders.

    Applies the same rule as the pre-transaction guard: a submit replaying its own
    idempotency_key gets the existing order set back; a distinct key hitting an
    already-ordered session is a conflict.
    """
    completed = _fetch_checkout_session(client, session_id=session_id, customer_id=customer_id)
    if _is_ordered(client, completed) and (
        str(completed.get("idempotency_key")) == idempotency_key
    ):
        return _result_from_group(completed, client=client, replayed=True)
    raise AppError(
        code="orders.session_already_completed",
        message="Checkout session already completed",
        http_status=409,
        details={"session_id": session_id},
    )


def replay_if_completed(
    client: Any,
    *,
    session_id: str,
    customer_id: str,
    idempotency_key: str,
) -> CreateOrdersResult | None:
    """Return the existing order set when this session has already been ordered.

    ``None`` means the session has no orders yet and the caller should carry on.
    An ordered session replayed with its own idempotency key returns the same
    orders; any other key is a conflict. "Ordered" is ``completed`` (COD, or a
    paid prepaid checkout) or ``pending`` with orders (prepaid awaiting payment).
    Callers use this before they read the cart, because a placed COD order has
    already taken its lines out of it.
    """
    response = (
        client.table("checkout_groups")
        .select("*")
        .eq("id", session_id)
        .eq("customer_id", customer_id)
        .maybe_single()
        .execute()
    )
    row = response.data if response is not None else None
    if not isinstance(row, dict) or not _is_ordered(client, row):
        return None
    if str(row.get("idempotency_key")) == idempotency_key:
        return _result_from_group(row, client=client, replayed=True)
    raise AppError(
        code="orders.session_already_completed",
        message="Checkout session already completed",
        http_status=409,
        details={"session_id": session_id},
    )


def _validate_vendor_groups(
    *,
    vendor_groups: list[VendorFulfilmentInput],
    cart_lines: list[CartLineInput],
    session_subtotal: int,
    session_delivery_fee: int,
    session_total: int,
    session_discount: int = 0,
    ticket_subtotal: int = 0,
    platform_fee: int = 0,
) -> dict[str, VendorFulfilmentInput]:
    by_vendor = {group.vendor_id: group for group in vendor_groups}
    cart_vendors = {line.vendor_id for line in cart_lines}
    if set(by_vendor) != cart_vendors:
        raise AppError(
            code="orders.invalid_vendor_groups",
            message="Fulfilment groups must cover every vendor in the cart exactly once",
            http_status=422,
        )

    computed_subtotal = (
        cart_subtotal_ngwee([(line.qty, line.unit_price_ngwee) for line in cart_lines])
        + ticket_subtotal
    )
    if computed_subtotal != session_subtotal:
        raise AppError(
            code="orders.totals_mismatch",
            message="Cart subtotal does not match checkout session",
            http_status=409,
            details={"expected": session_subtotal, "actual": computed_subtotal},
        )

    group_subtotal_sum = sum(group.subtotal_ngwee for group in vendor_groups) + ticket_subtotal
    if group_subtotal_sum != session_subtotal:
        raise AppError(
            code="orders.totals_mismatch",
            message="Vendor subtotals do not match checkout session",
            http_status=409,
            details={"expected": session_subtotal, "actual": group_subtotal_sum},
        )

    delivery_sum = sum(group.delivery_fee_ngwee for group in vendor_groups)
    if delivery_sum != session_delivery_fee:
        raise AppError(
            code="orders.totals_mismatch",
            message="Delivery fees do not match checkout session",
            http_status=409,
            details={"expected": session_delivery_fee, "actual": delivery_sum},
        )

    if session_subtotal + session_delivery_fee + platform_fee - session_discount != session_total:
        raise AppError(
            code="orders.totals_mismatch",
            message="Checkout session total is inconsistent",
            http_status=409,
        )

    for group in vendor_groups:
        vendor_lines = [line for line in cart_lines if line.vendor_id == group.vendor_id]
        vendor_subtotal = sum(
            line_total_ngwee(line.qty, line.unit_price_ngwee) for line in vendor_lines
        )
        if vendor_subtotal != group.subtotal_ngwee:
            raise AppError(
                code="orders.totals_mismatch",
                message="Vendor group subtotal mismatch",
                http_status=409,
                details={"vendor_id": group.vendor_id},
            )

    return by_vendor


_DELIVERY_FUNDINGS = frozenset({"customer", "vendor", "vendor_self", "platform"})


def _delivery_funding_for(group: VendorFulfilmentInput) -> tuple[str, int]:
    """Validated (funding, funded_ngwee) for one vendor order (fail closed)."""
    funding = group.delivery_funding
    funded = group.delivery_funded_ngwee
    if funding not in _DELIVERY_FUNDINGS:
        raise ValueError("unknown delivery funding")
    if isinstance(funded, bool) or not isinstance(funded, int) or funded < 0:
        raise TypeError("delivery_funded_ngwee must be non-negative integer ngwee")
    if group.fulfilment != "delivery":
        return "customer", 0
    if funding != "customer" and group.delivery_fee_ngwee != 0:
        raise ValueError("a vendor- or platform-funded delivery charges the customer nothing")
    if funding not in {"vendor", "platform"} and funded != 0:
        raise ValueError("only vendor or platform funding books an amount")
    return funding, funded


def _validate_coupon_plan(
    coupon: CouponOrderPlan, *, session_discount: int, cart_lines: list[CartLineInput]
) -> None:
    listing_ids = {line.listing_id for line in cart_lines}
    if (
        coupon.discount_ngwee <= 0
        or coupon.discount_ngwee != session_discount
        or sum(coupon.line_discounts.values()) != coupon.discount_ngwee
        or any(amount < 0 for amount in coupon.line_discounts.values())
        or not set(coupon.line_discounts) <= listing_ids
    ):
        raise AppError(
            code="coupon.changed",
            message="The coupon amount changed; apply it again",
            http_status=409,
            details={"message_key": "checkout.coupon.errors.changed"},
        )
    for line in cart_lines:
        if coupon.line_discounts.get(line.listing_id, 0) > line_total_ngwee(
            line.qty, line.unit_price_ngwee
        ):
            raise AppError(
                code="coupon.changed",
                message="The coupon amount changed; apply it again",
                http_status=409,
                details={"message_key": "checkout.coupon.errors.changed"},
            )


def create_orders_atomic(
    *,
    client: Any,
    customer_id: str,
    session_id: str,
    idempotency_key: str,
    payment_method: PaymentMethod,
    cart_lines: list[CartLineInput],
    vendor_groups: list[VendorFulfilmentInput],
    address_id: str | None = None,
    inject_failure: str | None = None,
    coupon: CouponOrderPlan | None = None,
    is_gift: bool = False,
    ticket_order: TicketOrderInput | None = None,
) -> CreateOrdersResult:
    """Create per-vendor orders from a validated checkout session in one transaction.

    ``ticket_order`` (unified checkout): the organiser's event tickets, placed
    as a separate ``ticket``-lane order in the same transaction, consuming the
    session's capacity holds. Tickets are prepaid only (never COD).
    """
    _validate_uuid(customer_id, "customer_id")
    _validate_uuid(session_id, "session_id")
    if not idempotency_key.strip():
        raise AppError(
            code="validation_error",
            message="Idempotency key is required",
            http_status=422,
            details={"field": "idempotency_key"},
        )
    if address_id is not None:
        _validate_uuid(address_id, "address_id")

    existing = _fetch_existing_by_idempotency_key(
        client, idempotency_key=idempotency_key, customer_id=customer_id
    )
    if existing is not None and _is_ordered(client, existing):
        return _result_from_group(existing, client=client, replayed=True)

    session = _fetch_checkout_session(client, session_id=session_id, customer_id=customer_id)
    session_status = str(session.get("status") or "")
    if _is_ordered(client, session):
        if str(session.get("idempotency_key")) == idempotency_key:
            return _result_from_group(session, client=client, replayed=True)
        raise AppError(
            code="orders.session_already_completed",
            message="Checkout session already completed",
            http_status=409,
            details={"session_id": session_id},
        )
    if session_status in {"expired", "abandoned"}:
        raise AppError(
            code="checkout.reservation_expired",
            message="Your reservation has expired",
            http_status=410,
            details={"session_id": session_id},
        )
    if _session_expired(client, session_id):
        expire_checkout_group_if_unpaid(
            client, checkout_group_id=session_id, terminal_status="expired"
        )
        raise AppError(
            code="checkout.reservation_expired",
            message="Your reservation has expired",
            http_status=410,
            details={"session_id": session_id},
        )

    if ticket_order is not None and payment_method == "cod":
        raise AppError(
            code="checkout.cod_not_allowed",
            message="Event tickets must be paid online",
            http_status=422,
            details={"message_key": "checkout.payment.codNotForTickets", "field": "method"},
        )
    if ticket_order is not None and not ticket_order.lines:
        ticket_order = None
    session_subtotal = int(session.get("subtotal_ngwee", 0))
    session_delivery_fee = int(session.get("delivery_fee_ngwee", 0))
    session_total = int(session.get("total_ngwee", 0))
    session_discount = int(session.get("discount_ngwee") or 0)
    if coupon is not None:
        _validate_coupon_plan(coupon, session_discount=session_discount, cart_lines=cart_lines)
        if payment_method == "cod":
            raise AppError(
                code="coupon.cod_not_allowed",
                message="Coupons need mobile money or card payment",
                http_status=422,
                details={"message_key": "checkout.coupon.errors.cod_not_allowed"},
            )
    elif session_discount != 0:
        raise AppError(
            code="coupon.changed",
            message="The coupon on this checkout is no longer valid",
            http_status=409,
            details={"message_key": "checkout.coupon.errors.changed"},
        )
    if is_gift and payment_method == "cod":
        raise AppError(
            code="gift.cod_not_allowed",
            message="Gifts need mobile money or card payment",
            http_status=422,
            details={"message_key": "checkout.gift.errors.codNotAllowed"},
        )
    session_platform_fee = int(session.get("platform_fee_ngwee") or 0)
    ticket_fee = ticket_order.platform_fee_ngwee if ticket_order is not None else 0
    if session_platform_fee != ticket_fee:
        raise AppError(
            code="orders.totals_mismatch",
            message="Platform fee does not match checkout session",
            http_status=409,
            details={"expected": session_platform_fee, "actual": ticket_fee},
        )
    groups_by_vendor = _validate_vendor_groups(
        vendor_groups=vendor_groups,
        cart_lines=cart_lines,
        session_subtotal=session_subtotal,
        session_delivery_fee=session_delivery_fee,
        session_total=session_total,
        session_discount=session_discount,
        ticket_subtotal=ticket_order.subtotal_ngwee if ticket_order is not None else 0,
        platform_fee=ticket_fee,
    )

    commission_rates = _load_commission_rates(client)
    requested_by_listing = _aggregate_listing_quantities(cart_lines)
    listing_ids = list(requested_by_listing)
    commission_keys = _load_listing_commission_keys(client, listing_ids)
    product_ids = _load_product_ids(client, listing_ids)

    cod = payment_method == "cod"
    vendor_owner_ids = _load_vendor_owner_ids(client, sorted(groups_by_vendor)) if cod else {}
    product_names = _load_product_names(client, sorted(set(product_ids.values()))) if cod else {}
    planned_orders: list[tuple[CreatedOrder, list[CartLineInput]]] = []
    for vendor_id in sorted(groups_by_vendor):
        group = groups_by_vendor[vendor_id]
        vendor_lines = [line for line in cart_lines if line.vendor_id == vendor_id]
        snapshot = _build_commission_snapshot(
            lines=vendor_lines,
            commission_keys=commission_keys,
            commission_rates=commission_rates,
        )
        order_discount = (
            sum(coupon.line_discounts.get(line.listing_id, 0) for line in vendor_lines)
            if coupon is not None
            else 0
        )
        if coupon is not None and coupon.funder == "vendor" and order_discount > 0:
            # Vendor-funded: commission is charged on the discounted price.
            snapshot = scale_snapshot_for_vendor_discount(snapshot, coupon.line_discounts)
        order_id = str(uuid4())
        planned_items = tuple(
            CreatedOrderItem(
                order_item_id=str(uuid4()),
                listing_id=line.listing_id,
                qty=line.qty,
                unit_price_ngwee=line.unit_price_ngwee,
                line_total_ngwee=line_total_ngwee(line.qty, line.unit_price_ngwee),
            )
            for line in vendor_lines
        )
        planned_orders.append(
            (
                CreatedOrder(
                    order_id=order_id,
                    vendor_id=vendor_id,
                    fulfilment=group.fulfilment,
                    delivery_zone=group.delivery_zone,
                    delivery_fee_ngwee=group.delivery_fee_ngwee,
                    subtotal_ngwee=group.subtotal_ngwee,
                    cod=cod,
                    commission_snapshot=snapshot,
                    items=planned_items,
                    coupon_discount_ngwee=order_discount,
                ),
                vendor_lines,
            )
        )

    session_sql = sql_uuid(session_id, "session_id")
    customer_sql = sql_uuid(customer_id, "customer_id")
    idem_sql = sql_literal(idempotency_key)
    status_placed = OrderStatus.PLACED.value

    statements: list[str] = ["BEGIN;"]
    statements.append(_lock_and_recheck_sql(session_sql, customer_sql))
    if address_id is not None:
        statements.append(
            _require_own_address_sql(sql_uuid(address_id, "address_id"), customer_sql)
        )
    statements.append(_lock_and_check_class_e_capacity_sql(requested_by_listing))
    redemption_sql = "NULL"
    if coupon is not None:
        coupon_sql = sql_uuid(coupon.coupon_id, "coupon_id")
        # Atomic reservation under the coupon row lock; raises COUPON_* markers.
        statements.append(
            f"SELECT public.reserve_coupon_redemption({coupon_sql}, {customer_sql}, "
            f"{session_sql}, {int(coupon.discount_ngwee)});"
        )
        redemption_sql = (
            "(SELECT id FROM public.coupon_redemptions "
            f"WHERE coupon_id = {coupon_sql} AND checkout_group_id = {session_sql})"
        )

    parent_item_by_cart_line: dict[str, str] = {}
    statements.extend(
        _lock_live_offers_sql(
            [str(line.offer_id) for line in cart_lines if line.offer_id]
            + (
                [str(line.offer_id) for line in ticket_order.lines if line.offer_id]
                if ticket_order is not None
                else []
            ),
            customer_sql,
        )
    )
    for order, vendor_lines in planned_orders:
        order_sql = sql_uuid(order.order_id, "order_id")
        vendor_sql = sql_uuid(order.vendor_id, "vendor_id")
        zone_sql = sql_literal(order.delivery_zone) if order.delivery_zone is not None else "NULL"
        address_sql = sql_uuid(address_id, "address_id") if address_id is not None else "NULL"
        snapshot_sql = _sql_json(order.commission_snapshot)
        funding, funded_ngwee = _delivery_funding_for(groups_by_vendor[order.vendor_id])
        statements.append(
            f"""
INSERT INTO public.orders (
  id, checkout_group_id, vendor_id, customer_id, status, fulfilment,
  delivery_zone, address_id, delivery_fee_ngwee, cod, commission_snapshot,
  delivery_funding, delivery_funded_ngwee,
  coupon_redemption_id, coupon_discount_ngwee, coupon_funder, is_gift
) VALUES (
  {order_sql}, {session_sql}, {vendor_sql}, {customer_sql}, '{status_placed}',
  '{order.fulfilment}', {zone_sql}, {address_sql}, {order.delivery_fee_ngwee},
  {"true" if order.cod else "false"}, {snapshot_sql}::jsonb,
  '{funding}', {funded_ngwee},
  {redemption_sql if order.coupon_discount_ngwee > 0 else "NULL"},
  {int(order.coupon_discount_ngwee)},
  {
                sql_literal(coupon.funder)
                if coupon is not None and order.coupon_discount_ngwee > 0
                else "NULL"
            },
  {"true" if is_gift else "false"}
);
"""
        )
        for item, line in zip(order.items, vendor_lines, strict=True):
            item_sql = sql_uuid(item.order_item_id, "order_item_id")
            title_sql = (
                sql_literal(line.title_snapshot) if line.title_snapshot is not None else "NULL"
            )
            listing_sql = sql_uuid(line.listing_id, "listing_id")
            product_id = product_ids.get(line.listing_id)
            if product_id is not None:
                product_sql = sql_uuid(product_id, "product_id")
                product_columns = ", product_id"
                product_values = f", {product_sql}"
            else:
                product_columns = ""
                product_values = ""
            if line.listing_variant_id is not None:
                product_columns += ", listing_variant_id, variant_snapshot"
                product_values += (
                    f", {sql_uuid(line.listing_variant_id, 'listing_variant_id')}"
                    f", {_sql_json(line.variant_snapshot or {})}::jsonb"
                )
            offer_columns, offer_values = _offer_item_columns_sql(
                line,
                parent_item_id=parent_item_by_cart_line.get(line.offer_parent_cart_item_id or ""),
            )
            if not line.is_offer_gift:
                parent_item_by_cart_line.setdefault(line.cart_item_id, item.order_item_id)
            statements.append(
                f"""
INSERT INTO public.order_items (
  id, order_id, item_kind, qty, unit_price_ngwee, title_snapshot{offer_columns}
) VALUES (
  {item_sql}, {order_sql}, 'product', {item.qty}, {item.unit_price_ngwee}, {title_sql}{offer_values}
);
INSERT INTO public.order_item_products (order_item_id, listing_id{product_columns})
VALUES ({item_sql}, {listing_sql}{product_values});
"""
            )

        # Prepaid: do not notify vendor until payment SUCCESS (see apply_payment_status).
        # COD: fulfilment-valid at place — notify immediately.
        if order.cod:
            dedupe_key = build_dedupe_key("order.placed", order.order_id, OUTBOX_CHANNEL)
            payload = _vendor_new_order_payload(
                order=order,
                lines=vendor_lines,
                session_id=session_id,
                customer_id=customer_id,
                owner_user_id=vendor_owner_ids.get(order.vendor_id),
                product_ids=product_ids,
                product_names=product_names,
            )
            statements.append(
                f"""
INSERT INTO public.notification_outbox (
  dedupe_key, channel, template, payload, status
) VALUES (
  {sql_literal(dedupe_key)}, '{OUTBOX_CHANNEL}', '{OUTBOX_TEMPLATE}',
  {_sql_json(payload)}::jsonb, 'pending'
) ON CONFLICT (dedupe_key) DO NOTHING;
"""
            )

    if ticket_order is not None:
        statements.extend(
            _ticket_order_sql(
                ticket_order=ticket_order,
                order_id=str(uuid4()),
                item_ids=[str(uuid4()) for _ in ticket_order.lines],
                session_sql=session_sql,
                customer_sql=customer_sql,
                hold_count=len({(ln.ticket_type_id, ln.instance_id) for ln in ticket_order.lines}),
            )
        )

    # Per-variant stock: lock + decrement each chosen variant in UUID order (no
    # deadlocks across overlapping carts); a sold-out variant aborts the tx.
    for line in sorted(
        (
            line
            for line in cart_lines
            if line.listing_variant_id is not None and line.consumes_reservation
        ),
        key=lambda line: str(line.listing_variant_id),
    ):
        variant_sql = sql_uuid(str(line.listing_variant_id), "listing_variant_id")
        statements.append(
            f"SELECT public.consume_listing_variant_stock({variant_sql}, {int(line.hold_qty)});"
        )

    placed_lines: list[tuple[CartLineInput, str, str]] = [
        (line, order.order_id, item.order_item_id)
        for order, vendor_lines in planned_orders
        for item, line in zip(order.items, vendor_lines, strict=True)
    ]
    for line, placed_order_id, placed_item_id in placed_lines:
        if not line.consumes_reservation:
            continue
        statements.append(
            _consume_reservation_conditional_sql(
                checkout_group_id=session_id,
                listing_id=line.listing_id,
                qty=line.hold_qty,
                order_id=placed_order_id,
                order_item_id=placed_item_id,
                listing_variant_id=line.listing_variant_id,
            )
        )
    # Gift pools: conditional UPDATE in offer-id order (same order as the cancel
    # trigger) — a pool can never be reserved past its total, even under races.
    for line, placed_order_id, placed_item_id in sorted(
        (entry for entry in placed_lines if entry[0].is_offer_gift),
        key=lambda entry: (str(entry[0].offer_id), entry[2]),
    ):
        statements.append(
            _reserve_offer_gift_sql(
                offer_id=str(line.offer_id),
                order_id=placed_order_id,
                order_item_id=placed_item_id,
                qty=line.qty,
            )
        )
    statements.append(_consume_reservations_sql(session_id))
    if cod:
        statements.append(_clear_ordered_cart_lines_sql(cart_lines, customer_sql))
    # COD is final once placed, so its group completes here. A prepaid group must
    # stay 'pending': claim_payable_payment only claims a pending group, and
    # apply_prepaid_collection_success completes it when the payment succeeds.
    # The idempotency key is persisted either way so a retried POST /orders
    # replays the placed orders.
    complete_sql = "status = 'completed',\n    " if cod else ""
    statements.append(
        f"""
UPDATE public.checkout_groups
SET {complete_sql}idempotency_key = {idem_sql},
    updated_at = timezone('utc', now())
WHERE id = {session_sql};
"""
    )

    if inject_failure == "before_commit":
        statements.append("SELECT pg_catalog.pg_sleep(0);")
        statements.append(
            "DO $fail$ BEGIN RAISE EXCEPTION 'injected order creation failure'; END $fail$;"
        )

    statements.append("COMMIT;")

    result = run_sql_script("\n".join(statements))
    if not result.ok:
        error = result.error or ""
        if inject_failure == "before_commit":
            raise RuntimeError(f"order creation failed: {error}")
        coupon_error = map_reservation_error(error)
        if coupon_error is not None:
            raise coupon_error
        if _ADDRESS_NOT_OWNED_MARKER in error:
            raise AppError(
                code="checkout.address_invalid",
                message="Delivery address was not found for this account",
                http_status=422,
                details={"field": "address_id"},
            )
        offer_match = _OFFER_ERROR_RE.search(error)
        if offer_match is not None:
            kind = offer_match.group("kind").upper()
            code, message = {
                "GIFT_UNAVAILABLE": (
                    "offers.gift_out_of_stock",
                    "The free gift for an offer in your cart has run out",
                ),
                "LIMIT_REACHED": (
                    "offers.limit_reached",
                    "You have already used this offer the maximum number of times",
                ),
            }.get(kind, ("offers.expired", "An offer in your cart is no longer available"))
            raise AppError(
                code=code,
                message=message,
                http_status=409,
                details={
                    "message_key": code,
                    "offer_id": offer_match.group("offer_id"),
                    "redirect_to": "cart",
                    "retry": False,
                },
            )
        variant_match = _VARIANT_STOCK_ERROR_RE.search(error)
        if variant_match is not None:
            kind = variant_match.group("kind").upper()
            code = (
                "cart.variant_out_of_stock"
                if kind == "OUT_OF_STOCK"
                else "cart.variant_unavailable"
            )
            raise AppError(
                code=code,
                message="An option in your cart is no longer available in that quantity",
                http_status=409,
                details={
                    "message_key": code,
                    "listing_variant_id": variant_match.group("variant_id"),
                    "redirect_to": "cart",
                    "retry": False,
                },
            )
        capacity_match = _CLASS_E_CAPACITY_ERROR_RE.search(error)
        if capacity_match is not None:
            requested_qty = int(capacity_match.group("requested"))
            raise AppError(
                code="cart.class_e_capacity_exceeded",
                message="Weekly made-to-order capacity exceeded",
                http_status=409,
                details={
                    "message_key": "cart.class_e_capacity_exceeded",
                    "listing_id": capacity_match.group("listing_id"),
                    "remaining": int(capacity_match.group("remaining")),
                    "requested_qty": requested_qty,
                    "retry": True,
                },
            )
        # A concurrent submit won the row lock and completed the group first (#2):
        # our in-tx recheck aborted. Resolve to the same idempotent result the
        # pre-transaction guard would have returned — never a second order set.
        if _ALREADY_COMPLETED_MARKER in error or (
            "duplicate key value violates unique constraint" in error
        ):
            return _resolve_completed_after_race(
                client,
                session_id=session_id,
                customer_id=customer_id,
                idempotency_key=idempotency_key,
            )
        # A tracked hold vanished / no longer covers the qty between pre-check and
        # tx (#4). The whole tx rolled back: no partial order, no oversell.
        if _HOLD_INVALID_MARKER in error:
            raise AppError(
                code="checkout.reservation_expired",
                message="Your reservation has expired",
                http_status=410,
                details={"session_id": session_id},
            )
        raise RuntimeError(f"order creation failed: {error}")

    completed = _fetch_checkout_session(client, session_id=session_id, customer_id=customer_id)
    return _result_from_group(completed, client=client, replayed=False)


def _load_product_ids(client: Any, listing_ids: list[str]) -> dict[str, str]:
    if not listing_ids:
        return {}
    response = (
        client.table("vendor_listings").select("id, product_id").in_("id", listing_ids).execute()
    )
    rows = response.data if isinstance(response.data, list) else []
    product_ids: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        listing_id = row.get("id")
        product_id = row.get("product_id")
        if isinstance(listing_id, str) and isinstance(product_id, str):
            product_ids[listing_id] = product_id
    return product_ids
