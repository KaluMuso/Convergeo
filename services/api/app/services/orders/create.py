"""Atomic checkout → order creation in a single database transaction."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from app.errors import AppError
from app.services.cart.totals import cart_subtotal_ngwee, line_total_ngwee
from app.services.notifications.dedupe import build_dedupe_key
from app.services.orders.audit import sql_literal
from app.services.orders.state import OrderStatus
from app.services.stock.claim import run_sql_script, sql_uuid

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

Fulfilment = Literal["delivery", "pickup"]
PaymentMethod = Literal["momo", "card", "cod"]
DEFAULT_COMMISSION_KEY = "default"
OUTBOX_CHANNEL = "whatsapp"
OUTBOX_TEMPLATE = "order_placed"


@dataclass(frozen=True, slots=True)
class CartLineInput:
    cart_item_id: str
    listing_id: str
    vendor_id: str
    qty: int
    unit_price_ngwee: int
    title_snapshot: str | None


@dataclass(frozen=True, slots=True)
class VendorFulfilmentInput:
    vendor_id: str
    fulfilment: Fulfilment
    delivery_zone: str | None
    delivery_fee_ngwee: int
    subtotal_ngwee: int


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


def _consume_reservations_sql(checkout_group_id: str) -> str:
    """Delete held reservations without restocking (stock already decremented at claim)."""
    group_sql = sql_uuid(checkout_group_id, "checkout_group_id")
    return f"DELETE FROM public.stock_reservations WHERE checkout_group_id = {group_sql};"


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
    data = response.data
    return data if isinstance(data, dict) else None


def _fetch_checkout_session(
    client: Any, *, session_id: str, customer_id: str
) -> dict[str, Any]:
    response = (
        client.table("checkout_groups")
        .select("*")
        .eq("id", session_id)
        .eq("customer_id", customer_id)
        .maybe_single()
        .execute()
    )
    row = response.data
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


def _result_from_group(
    group: dict[str, Any], *, client: Any, replayed: bool
) -> CreateOrdersResult:
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


def _validate_vendor_groups(
    *,
    vendor_groups: list[VendorFulfilmentInput],
    cart_lines: list[CartLineInput],
    session_subtotal: int,
    session_delivery_fee: int,
    session_total: int,
) -> dict[str, VendorFulfilmentInput]:
    by_vendor = {group.vendor_id: group for group in vendor_groups}
    cart_vendors = {line.vendor_id for line in cart_lines}
    if set(by_vendor) != cart_vendors:
        raise AppError(
            code="orders.invalid_vendor_groups",
            message="Fulfilment groups must cover every vendor in the cart exactly once",
            http_status=422,
        )

    computed_subtotal = cart_subtotal_ngwee(
        [(line.qty, line.unit_price_ngwee) for line in cart_lines]
    )
    if computed_subtotal != session_subtotal:
        raise AppError(
            code="orders.totals_mismatch",
            message="Cart subtotal does not match checkout session",
            http_status=409,
            details={"expected": session_subtotal, "actual": computed_subtotal},
        )

    group_subtotal_sum = sum(group.subtotal_ngwee for group in vendor_groups)
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

    if session_subtotal + session_delivery_fee != session_total:
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
) -> CreateOrdersResult:
    """Create per-vendor orders from a validated checkout session in one transaction."""
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
    if existing is not None and str(existing.get("status")) == "completed":
        return _result_from_group(existing, client=client, replayed=True)

    session = _fetch_checkout_session(client, session_id=session_id, customer_id=customer_id)
    session_status = str(session.get("status") or "")
    if session_status == "completed":
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
        client.table("checkout_groups").update({"status": "expired"}).eq("id", session_id).execute()
        raise AppError(
            code="checkout.reservation_expired",
            message="Your reservation has expired",
            http_status=410,
            details={"session_id": session_id},
        )

    session_subtotal = int(session.get("subtotal_ngwee", 0))
    session_delivery_fee = int(session.get("delivery_fee_ngwee", 0))
    session_total = int(session.get("total_ngwee", 0))
    groups_by_vendor = _validate_vendor_groups(
        vendor_groups=vendor_groups,
        cart_lines=cart_lines,
        session_subtotal=session_subtotal,
        session_delivery_fee=session_delivery_fee,
        session_total=session_total,
    )

    commission_rates = _load_commission_rates(client)
    listing_ids = sorted({line.listing_id for line in cart_lines})
    commission_keys = _load_listing_commission_keys(client, listing_ids)
    product_ids = _load_product_ids(client, listing_ids)

    cod = payment_method == "cod"
    planned_orders: list[tuple[CreatedOrder, list[CartLineInput]]] = []
    for vendor_id in sorted(groups_by_vendor):
        group = groups_by_vendor[vendor_id]
        vendor_lines = [line for line in cart_lines if line.vendor_id == vendor_id]
        snapshot = _build_commission_snapshot(
            lines=vendor_lines,
            commission_keys=commission_keys,
            commission_rates=commission_rates,
        )
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
                ),
                vendor_lines,
            )
        )

    session_sql = sql_uuid(session_id, "session_id")
    customer_sql = sql_uuid(customer_id, "customer_id")
    idem_sql = sql_literal(idempotency_key)
    status_placed = OrderStatus.PLACED.value

    statements: list[str] = ["BEGIN;"]
    statements.append(
        f"""
SELECT id::text FROM public.checkout_groups
WHERE id = {session_sql} AND customer_id = {customer_sql}
FOR UPDATE;
"""
    )

    for order, vendor_lines in planned_orders:
        order_sql = sql_uuid(order.order_id, "order_id")
        vendor_sql = sql_uuid(order.vendor_id, "vendor_id")
        zone_sql = (
            sql_literal(order.delivery_zone) if order.delivery_zone is not None else "NULL"
        )
        address_sql = sql_uuid(address_id, "address_id") if address_id is not None else "NULL"
        snapshot_sql = _sql_json(order.commission_snapshot)
        statements.append(
            f"""
INSERT INTO public.orders (
  id, checkout_group_id, vendor_id, customer_id, status, fulfilment,
  delivery_zone, address_id, delivery_fee_ngwee, cod, commission_snapshot
) VALUES (
  {order_sql}, {session_sql}, {vendor_sql}, {customer_sql}, '{status_placed}',
  '{order.fulfilment}', {zone_sql}, {address_sql}, {order.delivery_fee_ngwee},
  {'true' if order.cod else 'false'}, {snapshot_sql}::jsonb
);
"""
        )
        for item, line in zip(order.items, vendor_lines, strict=True):
            item_sql = sql_uuid(item.order_item_id, "order_item_id")
            title_sql = (
                sql_literal(line.title_snapshot)
                if line.title_snapshot is not None
                else "NULL"
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
            statements.append(
                f"""
INSERT INTO public.order_items (
  id, order_id, item_kind, qty, unit_price_ngwee, title_snapshot
) VALUES (
  {item_sql}, {order_sql}, 'product', {item.qty}, {item.unit_price_ngwee}, {title_sql}
);
INSERT INTO public.order_item_products (order_item_id, listing_id{product_columns})
VALUES ({item_sql}, {listing_sql}{product_values});
"""
            )

        dedupe_key = build_dedupe_key("order.placed", order.order_id, OUTBOX_CHANNEL)
        payload = {
            "order_id": order.order_id,
            "checkout_group_id": session_id,
            "vendor_id": order.vendor_id,
            "customer_id": customer_id,
        }
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

    statements.append(_consume_reservations_sql(session_id))
    statements.append(
        f"""
UPDATE public.checkout_groups
SET status = 'completed',
    idempotency_key = {idem_sql},
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
        if inject_failure == "before_commit":
            raise RuntimeError(f"order creation failed: {result.error}")
        if "duplicate key value violates unique constraint" in (result.error or ""):
            replay = _fetch_existing_by_idempotency_key(
                client, idempotency_key=idempotency_key, customer_id=customer_id
            )
            if replay is not None and str(replay.get("status")) == "completed":
                return _result_from_group(replay, client=client, replayed=True)
        raise RuntimeError(f"order creation failed: {result.error}")

    completed = _fetch_checkout_session(client, session_id=session_id, customer_id=customer_id)
    return _result_from_group(completed, client=client, replayed=False)


def _load_product_ids(client: Any, listing_ids: list[str]) -> dict[str, str]:
    if not listing_ids:
        return {}
    response = (
        client.table("vendor_listings")
        .select("id, product_id")
        .in_("id", listing_ids)
        .execute()
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
