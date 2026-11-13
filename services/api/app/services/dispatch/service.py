"""Courier dispatch v1 — create, transition, notify, verify handover, views.

All writes go through service-role SQL (``run_sql_script``) in single
transactions with row locks; status changes go through
``app.services.dispatch.state.apply_dispatch_transition`` (CAS + guard trigger +
audit trigger) and the order is moved only through ``transition_order``.

Delivery chain-of-custody v1: a 6-digit handover code is minted with the
dispatch, shown ONLY to the order's customer, and entered by ops when the rider
reports it. A correct code atomically marks the dispatch delivered (single use)
and then delivers the order via the order state machine. Wrong codes are
counted per dispatch; ``HANDOVER_MAX_ATTEMPTS`` consecutive failures lock the
code for ``HANDOVER_LOCKOUT_MINUTES`` — on top of the per-actor request rate
limit applied by the router.
"""

from __future__ import annotations

import hmac
import json
import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from app.errors import AppError
from app.services.dispatch.message import (
    CourierMessage,
    build_courier_message,
    context_from_row,
    order_reference,
)
from app.services.dispatch.state import (
    ACTIVE_STATUSES,
    FAILURE_CODES,
    DispatchRow,
    DispatchStatus,
    DispatchTransitionError,
    DispatchTransitionOutcome,
    apply_dispatch_transition,
    assert_transition,
    audit_context_sql,
    dispatch_row_from_json,
    fetch_dispatch,
    fetch_latest_dispatch_for_order,
    json_rows,
    validate_pod_public_id,
)
from app.services.notifications.dedupe import enqueue_outbox_row
from app.services.orders.audit import run_sql_script, sql_literal
from app.services.orders.state import (
    ActorRole,
    OrderEvent,
    OrderStatus,
    check_order_transition,
    sql_uuid,
    transition_order,
)

logger = logging.getLogger(__name__)

COURIER_DISPATCH_FLAG = "courier_dispatch"
HANDOVER_CODE_LENGTH = 6
HANDOVER_MAX_ATTEMPTS = 5
HANDOVER_LOCKOUT_MINUTES = 15
DISPATCHABLE_ORDER_STATUSES = frozenset({"confirmed", "processing", "ready"})
#: A second delivery attempt (or a return) is created on a shipped order whose
#: last delivery attempt failed after pickup.
REDISPATCH_ORDER_STATUSES = frozenset({"shipped"})
MAX_DELIVERY_ATTEMPTS = 2
DEFAULT_COURIER_CASH_CAP_NGWEE = 150_000  # K1,500
STALE_REQUESTED_MINUTES_DEFAULT = 45
COURIER_TEMPLATE = "courier_dispatch_request"
STALE_ALERT_TEMPLATE = "dispatch_stale_alert"

NotifyChannel = Literal["whatsapp", "email"]
AdminTargetStatus = Literal["accepted", "picked_up", "delivered", "failed", "cancelled"]


# ---------------------------------------------------------------------------
# Flag
# ---------------------------------------------------------------------------


def is_courier_dispatch_enabled() -> bool:
    """Kill switch (``feature_flags.courier_dispatch``, default OFF). Fails closed."""
    result = run_sql_script(
        "SELECT enabled::text FROM public.feature_flags "
        f"WHERE flag = {sql_literal(COURIER_DISPATCH_FLAG)};"
    )
    if not result.ok or not result.rows:
        return False
    return result.rows[0].lower() in {"t", "true"}


def require_courier_dispatch_enabled() -> None:
    if not is_courier_dispatch_enabled():
        raise AppError(
            code="feature_disabled",
            message="Courier dispatch is disabled",
            http_status=409,
            details={"flag": COURIER_DISPATCH_FLAG, "message_key": "admin.dispatch.disabled"},
        )


def generate_handover_code() -> str:
    return f"{secrets.randbelow(10**HANDOVER_CODE_LENGTH):0{HANDOVER_CODE_LENGTH}d}"


# ---------------------------------------------------------------------------
# Context loaders
# ---------------------------------------------------------------------------


def load_order_dispatch_context(order_id: str) -> dict[str, Any]:
    """Order + vendor pickup point + customer drop-off + COD amount (ngwee)."""
    order_sql = sql_uuid(order_id, "order_id")
    rows = json_rows(
        f"""
SELECT json_build_object(
  'order_id', o.id,
  'status', o.status,
  'fulfilment', o.fulfilment,
  'cod', o.cod,
  'customer_id', o.customer_id,
  'vendor_id', o.vendor_id,
  'delivery_zone', o.delivery_zone,
  'delivery_fee_ngwee', o.delivery_fee_ngwee,
  'subtotal_ngwee', coalesce((
    SELECT sum(oi.qty * oi.unit_price_ngwee) FROM public.order_items oi WHERE oi.order_id = o.id
  ), 0)::bigint,
  'paid', EXISTS (
    SELECT 1 FROM public.payments p
    WHERE p.checkout_group_id = o.checkout_group_id AND p.status = 'success'
  ),
  'items', coalesce((
    SELECT json_agg(json_build_object('title', coalesce(oi.title_snapshot, 'Item'), 'qty', oi.qty)
                    ORDER BY oi.created_at, oi.id)
    FROM public.order_items oi WHERE oi.order_id = o.id
  ), '[]'::json),
  'vendor_name', v.display_name,
  'vendor_whatsapp', v.whatsapp_msisdn,
  'checkout_group_id', o.checkout_group_id,
  'delivery_funding', o.delivery_funding,
  'pickup_location_id', pick.location_id,
  'pickup_branch_count', (
    SELECT count(DISTINCT c.location_id) FROM public.order_item_stock_consumption c
    WHERE c.order_id = o.id AND c.location_id IS NOT NULL
  ),
  'pickup', (
    SELECT json_build_object('landmark', vl.landmark, 'lat', vl.lat, 'lng', vl.lng,
                             'phone', vl.phone_e164, 'label', vl.label, 'area', vl.area)
    FROM public.vendor_locations vl
    WHERE vl.id = pick.location_id
  ),
  'dropoff', (
    SELECT json_build_object('landmark', a.landmark, 'lat', a.lat, 'lng', a.lng, 'phone', a.phone)
    FROM public.addresses a WHERE a.id = o.address_id
  ),
  'customer_phone', pr.phone,
  'customer_name', pr.display_name
)::text
FROM public.orders o
JOIN public.vendors v ON v.id = o.vendor_id
LEFT JOIN public.profiles pr ON pr.id = o.customer_id
-- Logistics phase 1: collect from the branch that actually holds the stock
-- (the one most units were consumed from), else the recorded pickup branch,
-- else the vendor's primary active location.
LEFT JOIN LATERAL (
  SELECT coalesce(
    o.pickup_location_id,
    (SELECT c.location_id FROM public.order_item_stock_consumption c
     WHERE c.order_id = o.id AND c.location_id IS NOT NULL
     GROUP BY c.location_id
     ORDER BY sum(c.listing_qty) DESC, c.location_id
     LIMIT 1),
    (SELECT vl.id FROM public.vendor_locations vl
     WHERE vl.vendor_id = o.vendor_id AND coalesce(vl.status, 'active') = 'active'
     ORDER BY vl.is_primary DESC, vl.created_at ASC
     LIMIT 1)
  ) AS location_id
) pick ON true
WHERE o.id = {order_sql};
""",
        context="order dispatch context",
    )
    if not rows:
        raise AppError(code="not_found", message="Order not found", http_status=404)
    row = rows[0]
    row["cod_amount_ngwee"] = compute_cod_amount_ngwee(row)
    return row


def compute_cod_amount_ngwee(order_ctx: dict[str, Any]) -> int:
    """Amount the rider collects: subtotal + delivery fee for COD, else 0 (ngwee)."""
    if not bool(order_ctx.get("cod")):
        return 0
    subtotal = order_ctx.get("subtotal_ngwee")
    fee = order_ctx.get("delivery_fee_ngwee")
    for value in (subtotal, fee):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise TypeError("order money fields must be non-negative integer ngwee")
    assert isinstance(subtotal, int) and isinstance(fee, int)
    return subtotal + fee


def load_courier(courier_partner_id: str) -> dict[str, Any]:
    courier_sql = sql_uuid(courier_partner_id, "courier_partner_id")
    rows = json_rows(
        f"""
SELECT json_build_object(
  'id', c.id, 'name', c.name, 'active', c.active, 'integration_kind', c.integration_kind,
  'contact_whatsapp_e164', c.contact_whatsapp_e164, 'contact_email', c.contact_email,
  'zones', coalesce((
    SELECT json_agg(json_build_object('zone_key', z.zone_key, 'price_ngwee', z.price_ngwee)
                    ORDER BY z.zone_key)
    FROM public.courier_partner_zones z WHERE z.courier_partner_id = c.id
  ), '[]'::json)
)::text
FROM public.courier_partners c WHERE c.id = {courier_sql};
""",
        context="courier lookup",
    )
    if not rows:
        raise AppError(code="not_found", message="Courier not found", http_status=404)
    return rows[0]


def _zone_price(courier: dict[str, Any], zone_key: str | None) -> tuple[bool, int | None]:
    zones = courier.get("zones") or []
    if not zones:
        return True, None  # no service areas configured = serves all zones, quote per job
    for zone in zones:
        if isinstance(zone, dict) and zone.get("zone_key") == zone_key:
            price = zone.get("price_ngwee")
            return True, price if isinstance(price, int) and not isinstance(price, bool) else None
    return zone_key is None, None


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CreateDispatchResult:
    dispatch: DispatchRow
    courier_name: str


@dataclass(frozen=True, slots=True)
class _AttemptHistory:
    delivery_attempts: int
    last_delivery_status: str | None
    has_return: bool
    has_active: bool = False


def _attempt_history(order_id: str) -> _AttemptHistory:
    order_sql = sql_uuid(order_id, "order_id")
    rows = json_rows(
        f"""
SELECT json_build_object(
  'attempts', count(*) FILTER (WHERE d.direction = 'delivery' AND d.picked_up_at IS NOT NULL),
  'last_status', (
    SELECT d2.status FROM public.dispatch_requests d2
    WHERE d2.order_id = {order_sql} AND d2.direction = 'delivery'
    ORDER BY d2.created_at DESC, d2.id DESC LIMIT 1
  ),
  'has_return', bool_or(d.direction = 'return' AND d.status NOT IN ('cancelled', 'failed')),
  'has_active', bool_or(d.status IN ('requested', 'accepted', 'picked_up'))
)::text
FROM public.dispatch_requests d
WHERE d.order_id = {order_sql};
""",
        context="dispatch attempt history",
    )
    row = rows[0] if rows else {}
    return _AttemptHistory(
        delivery_attempts=int(row.get("attempts") or 0),
        last_delivery_status=row.get("last_status"),
        has_return=bool(row.get("has_return")),
        has_active=bool(row.get("has_active")),
    )


def courier_cash_cap_ngwee() -> int:
    result = run_sql_script(
        "SELECT value::text FROM public.platform_config WHERE key = 'courier_cash_cap_ngwee';"
    )
    if result.ok and result.rows and result.rows[0].isdigit():
        return int(result.rows[0])
    return DEFAULT_COURIER_CASH_CAP_NGWEE


def courier_cash_exposure_ngwee(courier_partner_id: str) -> dict[str, int]:
    """Cash a courier holds (collected, not remitted) + cash on active jobs (ngwee)."""
    courier_sql = sql_uuid(courier_partner_id, "courier_partner_id")
    rows = json_rows(
        f"""
SELECT json_build_object(
  'held', coalesce(sum(d.cod_collected_ngwee)
                   FILTER (WHERE d.cod_collected_ngwee IS NOT NULL AND d.remittance_id IS NULL), 0),
  'in_flight', coalesce(sum(d.cod_amount_ngwee)
                   FILTER (WHERE d.status IN ('requested', 'accepted', 'picked_up')), 0)
)::text
FROM public.dispatch_requests d
WHERE d.courier_partner_id = {courier_sql};
""",
        context="courier cash exposure",
    )
    row = rows[0] if rows else {}
    return {"held": int(row.get("held") or 0), "in_flight": int(row.get("in_flight") or 0)}


def assert_within_cash_cap(courier_partner_id: str, new_cod_ngwee: int) -> None:
    """Rule 6.3.3: a courier never carries more cash than the cap."""
    if new_cod_ngwee <= 0:
        return
    cap = courier_cash_cap_ngwee()
    exposure = courier_cash_exposure_ngwee(courier_partner_id)
    total = exposure["held"] + exposure["in_flight"] + new_cod_ngwee
    if total > cap:
        raise AppError(
            code="courier_cash_cap_exceeded",
            message="This courier would carry more cash than the cap; record a remittance first",
            http_status=409,
            details={
                "cap_ngwee": cap,
                "held_ngwee": exposure["held"],
                "in_flight_ngwee": exposure["in_flight"],
                "requested_ngwee": new_cod_ngwee,
                "message_key": "admin.dispatch.errors.cashCap",
            },
        )


def create_dispatch(
    *,
    order_id: str,
    courier_partner_id: str,
    actor_id: str,
    note: str = "Dispatch requested",
    direction: Literal["delivery", "return"] = "delivery",
) -> CreateDispatchResult:
    order = load_order_dispatch_context(order_id)
    if order.get("fulfilment") != "delivery":
        raise AppError(
            code="dispatch_not_applicable",
            message="Courier dispatch applies only to delivery orders",
            http_status=409,
        )
    if order.get("delivery_funding") == "vendor_self":
        raise AppError(
            code="dispatch_vendor_self_delivery",
            message="The vendor delivers this order itself (free delivery, own rider)",
            http_status=409,
        )
    history = _attempt_history(order_id)
    if history.has_active:
        raise AppError(
            code="dispatch_already_active",
            message="Order already has an active or delivered dispatch",
            http_status=409,
        )
    status = order.get("status")
    attempt_no = 1
    if direction == "return":
        if status not in REDISPATCH_ORDER_STATUSES or history.last_delivery_status != "failed":
            raise AppError(
                code="dispatch_return_not_allowed",
                message="A return is only for a shipped order whose delivery attempt failed",
                http_status=409,
                details={"status": status, "last_delivery_status": history.last_delivery_status},
            )
        if history.has_return:
            raise AppError(
                code="dispatch_already_active",
                message="Order already has a return dispatch",
                http_status=409,
            )
    elif status in REDISPATCH_ORDER_STATUSES:
        if history.last_delivery_status != "failed" or history.has_return:
            raise AppError(
                code="dispatch_order_not_ready",
                message="Only a shipped order whose last attempt failed can be re-sent",
                http_status=409,
                details={"status": status, "last_delivery_status": history.last_delivery_status},
            )
        if history.delivery_attempts >= MAX_DELIVERY_ATTEMPTS:
            raise AppError(
                code="dispatch_attempts_exhausted",
                message="Two delivery attempts failed; return the parcel to the shop",
                http_status=409,
                details={"attempts": history.delivery_attempts, "max": MAX_DELIVERY_ATTEMPTS},
            )
        attempt_no = history.delivery_attempts + 1
    elif status not in DISPATCHABLE_ORDER_STATUSES:
        raise AppError(
            code="dispatch_order_not_ready",
            message="Order is not ready for courier dispatch",
            http_status=409,
            details={"status": status, "allowed": sorted(DISPATCHABLE_ORDER_STATUSES)},
        )
    if not bool(order.get("cod")) and not bool(order.get("paid")):
        raise AppError(
            code="order_payment_required",
            message="Prepaid order requires successful payment before dispatch",
            http_status=409,
        )

    courier = load_courier(courier_partner_id)
    if not courier.get("active"):
        raise AppError(code="courier_inactive", message="Courier is inactive", http_status=409)
    if courier.get("integration_kind") != "manual":
        raise AppError(
            code="courier_integration_unavailable",
            message="API courier integrations are reserved and not yet available",
            http_status=409,
        )
    zone_key = order.get("delivery_zone")
    serves, price = _zone_price(courier, zone_key if isinstance(zone_key, str) else None)
    if not serves:
        raise AppError(
            code="courier_zone_not_served",
            message="Courier does not serve this delivery zone",
            http_status=422,
            details={"zone_key": zone_key},
        )

    # A return carries goods back to the shop: no cash, no customer code.
    cod_amount = int(order["cod_amount_ngwee"]) if direction == "delivery" else 0
    assert_within_cash_cap(courier_partner_id, cod_amount)
    code = generate_handover_code()
    order_sql = sql_uuid(order_id, "order_id")
    courier_sql = sql_uuid(courier_partner_id, "courier_partner_id")
    actor_sql = sql_uuid(actor_id, "actor_id")
    price_sql = str(price) if price is not None else "NULL"
    location = order.get("pickup_location_id")
    location_sql = (
        sql_uuid(str(location), "pickup_location_id") if isinstance(location, str) else "NULL"
    )
    code_sql = (
        f"""INSERT INTO public.dispatch_handover_codes (dispatch_request_id, code)
SELECT id, {sql_literal(code)} FROM ins
RETURNING json_build_object('id', dispatch_request_id)::text;"""
        if direction == "delivery"
        else "SELECT json_build_object('id', id)::text FROM ins;"
    )
    script = f"""
BEGIN;
{audit_context_sql(actor_id=actor_id, note=note)}
UPDATE public.orders SET pickup_location_id = {location_sql}
WHERE id = {order_sql} AND pickup_location_id IS NULL AND {location_sql} IS NOT NULL;
WITH ins AS (
  INSERT INTO public.dispatch_requests (
    order_id, courier_partner_id, status, cod_amount_ngwee, quoted_price_ngwee, created_by,
    direction, attempt_no, pickup_location_id
  ) VALUES (
    {order_sql}, {courier_sql}, 'requested', {cod_amount}, {price_sql}, {actor_sql},
    {sql_literal(direction)}, {attempt_no}, {location_sql}
  )
  RETURNING id
)
{code_sql}
COMMIT;
"""
    result = run_sql_script(script)
    if not result.ok:
        if any(
            index in (result.error or "")
            for index in (
                "dispatch_requests_one_active_per_order",
                "dispatch_requests_one_delivered_per_order",
                "dispatch_requests_one_return_per_order",
            )
        ):
            raise AppError(
                code="dispatch_already_active",
                message="Order already has an active or delivered dispatch",
                http_status=409,
            )
        raise RuntimeError(f"create dispatch failed: {result.error}")
    created = json_rows_from(result.rows)
    if not created:
        raise RuntimeError("create dispatch returned no row")
    return CreateDispatchResult(
        dispatch=fetch_dispatch(str(created[-1]["id"])),
        courier_name=str(courier.get("name") or ""),
    )


def json_rows_from(rows: list[str]) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    for raw in rows:
        if raw.strip().startswith("{"):
            value = json.loads(raw)
            if isinstance(value, dict):
                parsed.append(value)
    return parsed


# ---------------------------------------------------------------------------
# Order coupling
# ---------------------------------------------------------------------------


def _order_status(order_id: str) -> str:
    order_sql = sql_uuid(order_id, "order_id")
    result = run_sql_script(f"SELECT status FROM public.orders WHERE id = {order_sql};")
    if not result.ok or not result.rows:
        raise AppError(code="not_found", message="Order not found", http_status=404)
    return result.rows[0]


def _order_event_for(target: DispatchStatus, order_status: str) -> OrderEvent | None:
    """Which order event (if any) a dispatch transition drives from ``order_status``."""
    if target is DispatchStatus.PICKED_UP:
        if order_status in {OrderStatus.PROCESSING.value, OrderStatus.READY.value}:
            return OrderEvent.SHIP
        if order_status == OrderStatus.SHIPPED.value:
            return None
        raise AppError(
            code="dispatch_order_not_ready",
            message="Order must be packed (processing) or shipped before pickup",
            http_status=409,
            details={"order_status": order_status},
        )
    if target is DispatchStatus.DELIVERED:
        if order_status == OrderStatus.SHIPPED.value:
            return OrderEvent.MARK_DELIVERED
        if order_status in {OrderStatus.DELIVERED.value, OrderStatus.COMPLETED.value}:
            return None
        raise AppError(
            code="dispatch_order_not_ready",
            message="Order must be shipped before it can be delivered",
            http_status=409,
            details={"order_status": order_status},
        )
    return None


def _preflight_order(
    order_id: str, target: DispatchStatus, *, direction: str = "delivery"
) -> OrderEvent | None:
    if direction != "delivery":
        return None  # a return job never moves the order until the shop acknowledges it
    event = _order_event_for(target, _order_status(order_id))
    if event is not None:
        check_order_transition(order_id=order_id, event=event, actor_role=ActorRole.ADMIN)
    return event


def _apply_order_event(
    *, order_id: str, event: OrderEvent | None, actor_id: str, note: str
) -> str | None:
    if event is None:
        return None
    outcome = transition_order(
        order_id=order_id,
        event=event,
        actor_role=ActorRole.ADMIN,
        actor_id=actor_id,
        note=note,
    )
    return outcome.to_status.value


def custody_fields(
    dispatch: DispatchRow,
    *,
    cod_collected_ngwee: int | None,
    cod_collected_method: str | None,
) -> dict[str, str | int | None]:
    """Validate the cash the rider says they collected at delivery (ngwee).

    A cash job must record exactly the snapshot amount: a short or over
    collection is never booked by an operator (a person resolves it as a
    shortfall). A prepaid job must not record cash.
    """
    expected = dispatch.cod_amount_ngwee
    if expected <= 0:
        if cod_collected_ngwee not in (None, 0):
            raise AppError(
                code="dispatch_cod_not_expected",
                message="This delivery is prepaid; no cash should be collected",
                http_status=422,
            )
        return {}
    if cod_collected_ngwee is None:
        raise AppError(
            code="dispatch_cod_required",
            message="Record the cash the rider collected for this cash-on-delivery order",
            http_status=422,
            details={
                "expected_ngwee": expected,
                "message_key": "admin.dispatch.errors.codRequired",
            },
        )
    if isinstance(cod_collected_ngwee, bool) or not isinstance(cod_collected_ngwee, int):
        raise AppError(
            code="validation_error", message="cod must be integer ngwee", http_status=422
        )
    if cod_collected_ngwee != expected:
        raise AppError(
            code="dispatch_cod_mismatch",
            message="Collected cash differs from the amount due; escalate as a shortfall",
            http_status=422,
            details={
                "expected_ngwee": expected,
                "collected_ngwee": cod_collected_ngwee,
                "message_key": "admin.dispatch.errors.codMismatch",
            },
        )
    method = (cod_collected_method or "cash").strip()
    if method not in {"cash", "mobile_money"}:
        raise AppError(code="validation_error", message="Unknown cash method", http_status=422)
    return {"cod_collected_ngwee": expected, "cod_collected_method": method}


@dataclass(frozen=True, slots=True)
class AdminTransitionResult:
    transition: DispatchTransitionOutcome
    order_status: str | None


def transition_dispatch_admin(
    *,
    dispatch_id: str,
    to_status: DispatchStatus,
    actor_id: str,
    note: str | None = None,
    courier_reference: str | None = None,
    failure_reason: str | None = None,
    pod_photo_public_id: str | None = None,
    failure_code: str | None = None,
    cod_collected_ngwee: int | None = None,
    cod_collected_method: str | None = None,
    refund_authority: bool = False,
) -> AdminTransitionResult:
    dispatch = fetch_dispatch(dispatch_id)
    assert_transition(dispatch.status, to_status)
    if dispatch.direction == "return" and to_status is DispatchStatus.DELIVERED:
        raise AppError(
            code="dispatch_return_ack_required",
            message="A return is closed when the shop acknowledges the goods",
            http_status=409,
        )
    del refund_authority  # reserved: pickup/delivery never cancel the order

    fields: dict[str, str | int | None] = {}
    if courier_reference is not None and courier_reference.strip():
        fields["courier_reference"] = courier_reference.strip()[:120]

    if to_status is DispatchStatus.FAILED:
        if not (failure_reason and failure_reason.strip()):
            raise AppError(
                code="validation_error",
                message="failure_reason is required to fail a dispatch",
                http_status=422,
            )
        fields["failure_reason"] = failure_reason.strip()[:500]
        code = (failure_code or "other").strip()
        if code not in FAILURE_CODES:
            raise AppError(
                code="validation_error",
                message="Unknown failure_code",
                http_status=422,
                details={"allowed": sorted(FAILURE_CODES)},
            )
        fields["failure_code"] = code
    if to_status is DispatchStatus.DELIVERED:
        # Ops-confirmed delivery without the customer's code needs photo proof.
        if not pod_photo_public_id:
            raise AppError(
                code="dispatch_pod_required",
                message="Proof-of-delivery photo is required (or verify the handover code)",
                http_status=422,
            )
        fields["pod_photo_public_id"] = validate_pod_public_id(pod_photo_public_id)
        fields["delivered_via"] = "pod_photo"
        if cod_collected_ngwee is not None:
            # The combined /complete action always records cash; the legacy
            # transition records it when given (else the custody board shows
            # the delivered cash job as unrecorded).
            fields.update(
                custody_fields(
                    dispatch,
                    cod_collected_ngwee=cod_collected_ngwee,
                    cod_collected_method=cod_collected_method,
                )
            )

    order_event = (
        _preflight_order(dispatch.order_id, to_status, direction=dispatch.direction)
        if to_status in {DispatchStatus.PICKED_UP, DispatchStatus.DELIVERED}
        else None
    )
    text = (note or "").strip() or f"Dispatch {to_status.value}"
    outcome = apply_dispatch_transition(
        dispatch_id=dispatch_id,
        from_status=dispatch.status,
        to_status=to_status,
        actor_id=actor_id,
        note=text,
        set_fields=fields,
    )
    order_status = _apply_order_event(
        order_id=dispatch.order_id,
        event=order_event,
        actor_id=actor_id,
        note=f"[courier-dispatch] {to_status.value} ({dispatch_id})",
    )
    return AdminTransitionResult(transition=outcome, order_status=order_status)


# ---------------------------------------------------------------------------
# Handover code verification (chain of custody v1)
# ---------------------------------------------------------------------------


class HandoverLockedError(AppError):
    def __init__(self, *, retry_after: int) -> None:
        super().__init__(
            code="dispatch_handover_locked",
            message="Too many wrong handover codes; verification is temporarily locked",
            http_status=429,
            details={
                "retry_after": max(retry_after, 1),
                "message_key": "admin.dispatch.errors.handoverLocked",
            },
        )


class HandoverInvalidError(AppError):
    def __init__(self, *, attempts_remaining: int) -> None:
        super().__init__(
            code="dispatch_handover_invalid",
            message="Handover code does not match",
            http_status=422,
            details={
                "attempts_remaining": attempts_remaining,
                "message_key": "admin.dispatch.errors.handoverInvalid",
            },
        )


def _handover_state(dispatch_id: str) -> dict[str, Any]:
    dispatch_sql = sql_uuid(dispatch_id, "dispatch_id")
    rows = json_rows(
        f"""
SELECT json_build_object(
  'status', d.status,
  'order_id', d.order_id,
  'code', h.code,
  'failed_attempts', h.failed_attempts,
  'verified', h.verified_at IS NOT NULL,
  'locked_seconds', CASE
     WHEN h.locked_until IS NOT NULL AND h.locked_until > timezone('utc', now())
     THEN ceil(extract(epoch FROM (h.locked_until - timezone('utc', now()))))::int
     ELSE 0 END
)::text
FROM public.dispatch_requests d
LEFT JOIN public.dispatch_handover_codes h ON h.dispatch_request_id = d.id
WHERE d.id = {dispatch_sql};
""",
        context="handover lookup",
    )
    if not rows:
        raise AppError(code="not_found", message="Dispatch not found", http_status=404)
    return rows[0]


def _record_failed_attempt(dispatch_id: str) -> tuple[int, int]:
    """Atomically count a wrong code; lock when the threshold is reached.

    Returns ``(attempts_remaining, locked_seconds)``.
    """
    dispatch_sql = sql_uuid(dispatch_id, "dispatch_id")
    rows = json_rows(
        f"""
BEGIN;
UPDATE public.dispatch_handover_codes h
SET failed_attempts = CASE
      WHEN h.failed_attempts + 1 >= {HANDOVER_MAX_ATTEMPTS} THEN 0
      ELSE h.failed_attempts + 1 END,
    locked_until = CASE
      WHEN h.failed_attempts + 1 >= {HANDOVER_MAX_ATTEMPTS}
      THEN timezone('utc', now()) + interval '{HANDOVER_LOCKOUT_MINUTES} minutes'
      ELSE h.locked_until END
WHERE h.dispatch_request_id = {dispatch_sql}
  AND h.verified_at IS NULL
  AND (h.locked_until IS NULL OR h.locked_until <= timezone('utc', now()))
RETURNING json_build_object(
  'failed_attempts', h.failed_attempts,
  'locked', h.locked_until IS NOT NULL AND h.locked_until > timezone('utc', now())
)::text;
COMMIT;
""",
        context="handover failure record",
    )
    if not rows:
        # Raced into a lock (or verification) by a concurrent request.
        return 0, HANDOVER_LOCKOUT_MINUTES * 60
    if rows[-1].get("locked"):
        return 0, HANDOVER_LOCKOUT_MINUTES * 60
    failed = int(rows[-1].get("failed_attempts") or 0)
    return max(HANDOVER_MAX_ATTEMPTS - failed, 0), 0


def _claim_handover(
    dispatch_id: str,
    *,
    actor_id: str,
    custody: dict[str, str | int | None] | None = None,
) -> bool:
    """Single-use claim: code verified + dispatch delivered (+ cash custody) in ONE txn."""
    dispatch_sql = sql_uuid(dispatch_id, "dispatch_id")
    custody_sql = ""
    if custody:
        amount = custody["cod_collected_ngwee"]
        if isinstance(amount, bool) or not isinstance(amount, int):
            raise TypeError("cod_collected_ngwee must be integer ngwee")
        custody_sql = (
            f", cod_collected_ngwee = {amount}"
            f", cod_collected_method = {sql_literal(str(custody['cod_collected_method']))}"
            ", cod_collected_at = timezone('utc', now())"
        )
    rows = json_rows(
        f"""
BEGIN;
{audit_context_sql(actor_id=actor_id, note="Handover code verified")}
WITH locked AS (
  SELECT d.id
  FROM public.dispatch_requests d
  JOIN public.dispatch_handover_codes h ON h.dispatch_request_id = d.id
  WHERE d.id = {dispatch_sql}
    AND d.status = 'picked_up'
    AND h.verified_at IS NULL
    AND (h.locked_until IS NULL OR h.locked_until <= timezone('utc', now()))
  FOR UPDATE
),
claimed AS (
  UPDATE public.dispatch_handover_codes h
  SET verified_at = timezone('utc', now()), failed_attempts = 0
  FROM locked l
  WHERE h.dispatch_request_id = l.id
  RETURNING h.dispatch_request_id
)
UPDATE public.dispatch_requests d
SET status = 'delivered', delivered_via = 'handover_code'{custody_sql}
FROM claimed c
WHERE d.id = c.dispatch_request_id
RETURNING json_build_object('id', d.id)::text;
COMMIT;
""",
        context="handover claim",
    )
    return bool(rows)


@dataclass(frozen=True, slots=True)
class HandoverResult:
    dispatch_id: str
    order_id: str
    order_status: str | None


def verify_handover_code(
    *,
    dispatch_id: str,
    code: str,
    actor_id: str,
    rate_limiter: Callable[[str], None] | None = None,
    cod_collected_ngwee: int | None = None,
    cod_collected_method: str | None = None,
    require_custody: bool = False,
) -> HandoverResult:
    """Verify the customer's handover code; on match deliver dispatch + order.

    ``rate_limiter(actor_id)`` (router-supplied) throttles requests per actor
    BEFORE any comparison; the per-dispatch lockout below bounds guesses even
    across many actors.
    """
    cleaned = (code or "").strip()
    if len(cleaned) != HANDOVER_CODE_LENGTH or not cleaned.isdigit():
        raise AppError(
            code="validation_error",
            message="Handover code must be 6 digits",
            http_status=422,
        )
    if rate_limiter is not None:
        rate_limiter(actor_id)

    state = _handover_state(dispatch_id)
    if not isinstance(state.get("code"), str):
        raise AppError(
            code="dispatch_handover_missing",
            message="No handover code was issued for this dispatch",
            http_status=409,
        )
    locked_seconds = int(state.get("locked_seconds") or 0)
    if locked_seconds > 0:
        raise HandoverLockedError(retry_after=locked_seconds)
    if state.get("verified"):
        raise AppError(
            code="dispatch_handover_used",
            message="Handover code was already verified",
            http_status=409,
        )
    status = DispatchStatus(str(state["status"]))
    if status is not DispatchStatus.PICKED_UP:
        raise AppError(
            code="dispatch_invalid_transition",
            message="Handover can only be verified once the courier has picked up",
            http_status=409,
            details={"from_status": status.value, "to_status": DispatchStatus.DELIVERED.value},
        )

    if not hmac.compare_digest(cleaned.encode(), str(state["code"]).encode()):
        remaining, locked_for = _record_failed_attempt(dispatch_id)
        if locked_for > 0:
            raise HandoverLockedError(retry_after=locked_for)
        raise HandoverInvalidError(attempts_remaining=remaining)

    order_id = str(state["order_id"])
    custody: dict[str, str | int | None] | None = None
    if require_custody:
        custody = custody_fields(
            fetch_dispatch(dispatch_id),
            cod_collected_ngwee=cod_collected_ngwee,
            cod_collected_method=cod_collected_method,
        )
    order_event = _preflight_order(order_id, DispatchStatus.DELIVERED)
    if not _claim_handover(dispatch_id, actor_id=actor_id, custody=custody):
        raise AppError(
            code="dispatch_handover_used",
            message="Handover was already verified or the dispatch changed",
            http_status=409,
        )
    order_status = _apply_order_event(
        order_id=order_id,
        event=order_event,
        actor_id=actor_id,
        note=f"[courier-dispatch] handover code verified ({dispatch_id})",
    )
    return HandoverResult(dispatch_id=dispatch_id, order_id=order_id, order_status=order_status)


# ---------------------------------------------------------------------------
# Notify courier (outbox) + copy message
# ---------------------------------------------------------------------------


def build_dispatch_message(dispatch_id: str) -> tuple[DispatchRow, dict[str, Any], CourierMessage]:
    dispatch = fetch_dispatch(dispatch_id)
    courier = load_courier(dispatch.courier_partner_id)
    order_ctx = load_order_dispatch_context(dispatch.order_id)
    # The COD figure on the message is the dispatch snapshot, not a recompute.
    order_ctx["cod_amount_ngwee"] = dispatch.cod_amount_ngwee
    order_ctx["courier_reference"] = dispatch.courier_reference
    message = build_courier_message(
        context_from_row(order_ctx, courier_name=str(courier.get("name") or ""))
    )
    return dispatch, courier, message


@dataclass(frozen=True, slots=True)
class NotifyResult:
    dispatch_id: str
    channel: NotifyChannel
    enqueued: bool
    notify_count: int
    message: CourierMessage


def _bump_notify_count(dispatch_id: str) -> int:
    dispatch_sql = sql_uuid(dispatch_id, "dispatch_id")
    rows = json_rows(
        f"""
BEGIN;
UPDATE public.dispatch_requests
SET notify_count = notify_count + 1, last_notified_at = timezone('utc', now())
WHERE id = {dispatch_sql} AND status IN ('requested', 'accepted')
RETURNING json_build_object('notify_count', notify_count)::text;
COMMIT;
""",
        context="dispatch notify count",
    )
    if not rows:
        raise AppError(
            code="dispatch_invalid_transition",
            message="Only requested or accepted dispatches can be (re)notified",
            http_status=409,
        )
    return int(rows[-1]["notify_count"])


def notify_courier(
    outbox_client: Any,
    *,
    dispatch_id: str,
    channel: NotifyChannel,
) -> NotifyResult:
    """Enqueue the courier pickup message on the notification outbox.

    Delivery happens via the existing Notification Dispatch Tick (WhatsApp Cloud
    API template ``courier_dispatch_request`` / Resend email). Nothing is sent
    synchronously from this request.
    """
    dispatch, courier, message = build_dispatch_message(dispatch_id)
    if dispatch.status not in {DispatchStatus.REQUESTED, DispatchStatus.ACCEPTED}:
        raise AppError(
            code="dispatch_invalid_transition",
            message="Only requested or accepted dispatches can be (re)notified",
            http_status=409,
        )
    destination: dict[str, str] = {}
    if channel == "whatsapp":
        phone = courier.get("contact_whatsapp_e164")
        if not isinstance(phone, str) or not phone:
            raise AppError(
                code="courier_contact_missing",
                message="Courier has no WhatsApp number",
                http_status=422,
            )
        destination["to"] = phone
    else:
        email = courier.get("contact_email")
        if not isinstance(email, str) or not email:
            raise AppError(
                code="courier_contact_missing",
                message="Courier has no email address",
                http_status=422,
            )
        destination["email"] = email

    count = _bump_notify_count(dispatch_id)
    row = enqueue_outbox_row(
        outbox_client,
        event_type=COURIER_TEMPLATE,
        entity_id=f"{dispatch_id}:{count}",
        channel=channel,
        template=COURIER_TEMPLATE,
        payload={
            **destination,
            "locale": "en",
            "dispatch_id": dispatch_id,
            "order_id": dispatch.order_id,
            "courier_partner_id": dispatch.courier_partner_id,
            "cod_amount_ngwee": dispatch.cod_amount_ngwee,
            "dispatch_message": message.text,
            **message.whatsapp_params(),
        },
    )
    return NotifyResult(
        dispatch_id=dispatch_id,
        channel=channel,
        enqueued=row is not None,
        notify_count=count,
        message=message,
    )


# ---------------------------------------------------------------------------
# Read models
# ---------------------------------------------------------------------------


def _courier_name(courier_partner_id: str) -> str:
    try:
        return str(load_courier(courier_partner_id).get("name") or "")
    except AppError:
        return ""


def _timeline_from_row(dispatch: DispatchRow) -> list[dict[str, str]]:
    steps: list[tuple[str, str | None]] = [
        ("requested", dispatch.requested_at),
        ("accepted", dispatch.accepted_at),
        ("picked_up", dispatch.picked_up_at),
        ("delivered", dispatch.delivered_at),
        ("failed", dispatch.failed_at),
        ("cancelled", dispatch.cancelled_at),
    ]
    return [{"status": key, "at": at} for key, at in steps if at]


def party_dispatch_view(order_id: str, *, include_handover_code: bool) -> dict[str, Any] | None:
    """Latest dispatch for an order as the customer/vendor may see it.

    Callers MUST have already proven the requester is the order's customer
    (``include_handover_code=True`` is only ever passed on that path) or its
    vendor. Courier contacts, COD internals and POD ids are never projected.
    """
    dispatch = fetch_latest_dispatch_for_order(order_id)
    if dispatch is None:
        return None
    view: dict[str, Any] = {
        "dispatch_id": dispatch.id,
        "status": dispatch.status.value,
        "courier_name": _courier_name(dispatch.courier_partner_id),
        "courier_reference": dispatch.courier_reference,
        "cod_amount_ngwee": dispatch.cod_amount_ngwee,
        "timeline": _timeline_from_row(dispatch),
        "handover_code": None,
    }
    if include_handover_code and dispatch.status in ACTIVE_STATUSES:
        dispatch_sql = sql_uuid(dispatch.id, "dispatch_id")
        result = run_sql_script(
            "SELECT code FROM public.dispatch_handover_codes "
            f"WHERE dispatch_request_id = {dispatch_sql} AND verified_at IS NULL;"
        )
        if result.ok and result.rows:
            view["handover_code"] = result.rows[0]
    return view


def order_owner_and_vendor(order_id: str) -> tuple[str, str, str] | None:
    """(customer_id, vendor_id, vendor_owner_user_id) or None when unknown."""
    order_sql = sql_uuid(order_id, "order_id")
    rows = json_rows(
        f"""
SELECT json_build_object(
  'customer_id', o.customer_id, 'vendor_id', o.vendor_id, 'owner', v.owner_user_id
)::text
FROM public.orders o JOIN public.vendors v ON v.id = o.vendor_id
WHERE o.id = {order_sql};
""",
        context="order ownership lookup",
    )
    if not rows:
        return None
    row = rows[0]
    return str(row["customer_id"]), str(row["vendor_id"]), str(row.get("owner") or "")


def board_snapshot(*, recent_hours: int = 48, limit: int = 100) -> dict[str, Any]:
    """Admin dispatch board: delivery orders awaiting a courier + live dispatches."""
    ready = json_rows(
        f"""
SELECT json_build_object(
  'order_id', o.id,
  'status', o.status,
  'cod', o.cod,
  'delivery_zone', o.delivery_zone,
  'delivery_fee_ngwee', o.delivery_fee_ngwee,
  'subtotal_ngwee', coalesce((
    SELECT sum(oi.qty * oi.unit_price_ngwee) FROM public.order_items oi WHERE oi.order_id = o.id
  ), 0)::bigint,
  'item_count', coalesce((
    SELECT sum(oi.qty) FROM public.order_items oi WHERE oi.order_id = o.id
  ), 0),
  'vendor_name', v.display_name,
  'created_at', o.created_at,
  'last_failed_reason', (
    SELECT d.failure_reason FROM public.dispatch_requests d
    WHERE d.order_id = o.id AND d.status = 'failed'
    ORDER BY d.failed_at DESC NULLS LAST LIMIT 1
  ),
  'checkout_group_id', o.checkout_group_id,
  'address_id', o.address_id,
  'dropoff_landmark', a.landmark,
  'dropoff_area', ar.name,
  'dropoff_lat', coalesce(a.lat, ar.lat),
  'dropoff_lng', coalesce(a.lng, ar.lng),
  'address_type', a.address_type,
  'pickup_lat', pl.lat,
  'pickup_lng', pl.lng,
  'ready_at', o.ready_at,
  'deliver_together', o.deliver_together,
  'delivery_funding', o.delivery_funding,
  'pickup_label', pl.label,
  'pickup_area', coalesce(pl.area, pl.landmark),
  'pickup_branch_count', (
    SELECT count(DISTINCT c.location_id) FROM public.order_item_stock_consumption c
    WHERE c.order_id = o.id AND c.location_id IS NOT NULL
  ),
  'delivery_attempts', (
    SELECT count(*) FROM public.dispatch_requests d
    WHERE d.order_id = o.id AND d.direction = 'delivery' AND d.picked_up_at IS NOT NULL
  )
)::text
FROM public.orders o
JOIN public.vendors v ON v.id = o.vendor_id
LEFT JOIN public.addresses a ON a.id = o.address_id
LEFT JOIN public.areas ar ON ar.slug = a.area_slug
LEFT JOIN LATERAL (
  SELECT vl.label, vl.area, vl.landmark, vl.lat, vl.lng
  FROM public.vendor_locations vl
  WHERE vl.id = coalesce(
    o.pickup_location_id,
    (SELECT c.location_id FROM public.order_item_stock_consumption c
     WHERE c.order_id = o.id AND c.location_id IS NOT NULL
     GROUP BY c.location_id ORDER BY sum(c.listing_qty) DESC, c.location_id LIMIT 1),
    (SELECT vl2.id FROM public.vendor_locations vl2
     WHERE vl2.vendor_id = o.vendor_id AND coalesce(vl2.status, 'active') = 'active'
     ORDER BY vl2.is_primary DESC, vl2.created_at ASC LIMIT 1))
) pl ON true
WHERE o.fulfilment = 'delivery'
  AND o.delivery_funding <> 'vendor_self'
  AND (
    (o.status IN ('confirmed', 'processing', 'ready')
     AND NOT EXISTS (
       SELECT 1 FROM public.dispatch_requests d
       WHERE d.order_id = o.id AND d.status IN ('requested', 'accepted', 'picked_up', 'delivered')
     ))
    -- Logistics phase 1: a shipped order whose last attempt failed waits for a
    -- second attempt or a return to the shop.
    OR (o.status = 'shipped'
        AND NOT EXISTS (
          SELECT 1 FROM public.dispatch_requests d
          WHERE d.order_id = o.id
            AND d.status IN ('requested', 'accepted', 'picked_up', 'delivered')
        )
        AND (SELECT d.status FROM public.dispatch_requests d
             WHERE d.order_id = o.id AND d.direction = 'delivery'
             ORDER BY d.created_at DESC, d.id DESC LIMIT 1) = 'failed')
  )
-- Grouped by checkout + address so one rider can take a multi-shop checkout.
ORDER BY o.checkout_group_id, o.address_id NULLS LAST,
         (o.status = 'ready') DESC, o.created_at ASC
LIMIT {int(limit)};
""",
        context="dispatch board ready orders",
    )
    for row in ready:
        row["cod_amount_ngwee"] = compute_cod_amount_ngwee(row)
        row["order_reference"] = order_reference(str(row["order_id"]))

    dispatches = json_rows(
        f"""
SELECT json_build_object(
  'dispatch', json_build_object(
    'id', d.id, 'order_id', d.order_id, 'courier_partner_id', d.courier_partner_id,
    'status', d.status, 'courier_reference', d.courier_reference,
    'cod_amount_ngwee', d.cod_amount_ngwee, 'quoted_price_ngwee', d.quoted_price_ngwee,
    'pod_photo_public_id', d.pod_photo_public_id, 'delivered_via', d.delivered_via,
    'failure_reason', d.failure_reason, 'notify_count', d.notify_count,
    'last_notified_at', d.last_notified_at, 'requested_at', d.requested_at,
    'accepted_at', d.accepted_at, 'picked_up_at', d.picked_up_at,
    'delivered_at', d.delivered_at, 'failed_at', d.failed_at, 'cancelled_at', d.cancelled_at
  ),
  'courier_name', c.name,
  'vendor_name', v.display_name,
  'order_status', o.status,
  'delivery_zone', o.delivery_zone,
  'handover_locked', coalesce(h.locked_until > timezone('utc', now()), false)
)::text
FROM public.dispatch_requests d
JOIN public.courier_partners c ON c.id = d.courier_partner_id
JOIN public.orders o ON o.id = d.order_id
JOIN public.vendors v ON v.id = o.vendor_id
LEFT JOIN public.dispatch_handover_codes h ON h.dispatch_request_id = d.id
WHERE d.status IN ('requested', 'accepted', 'picked_up')
   OR d.updated_at >= timezone('utc', now()) - interval '{int(recent_hours)} hours'
ORDER BY d.requested_at DESC
LIMIT {int(limit)};
""",
        context="dispatch board dispatches",
    )
    items: list[dict[str, Any]] = []
    for row in dispatches:
        raw = row.get("dispatch")
        if not isinstance(raw, dict):
            continue
        dispatch = dispatch_row_from_json(raw)
        items.append(
            {
                "dispatch": dispatch,
                "courier_name": str(row.get("courier_name") or ""),
                "vendor_name": str(row.get("vendor_name") or ""),
                "order_status": str(row.get("order_status") or ""),
                "delivery_zone": row.get("delivery_zone"),
                "handover_locked": bool(row.get("handover_locked")),
                "order_reference": order_reference(dispatch.order_id),
            }
        )
    zones = json_rows(
        "SELECT json_build_object('zone_key', zone_key, 'label', label, "
        "'fee_ngwee', fee_ngwee)::text FROM public.delivery_zones "
        "WHERE active ORDER BY zone_key;",
        context="delivery zones",
    )
    return {"ready_orders": ready, "dispatches": items, "zones": zones}


def list_stale_requested(*, minutes: int = STALE_REQUESTED_MINUTES_DEFAULT) -> list[dict[str, Any]]:
    """Dispatches stuck in ``requested`` (no courier acceptance) beyond ``minutes``."""
    if minutes < 1:
        raise ValueError("minutes must be positive")
    rows = json_rows(
        f"""
SELECT json_build_object(
  'dispatch_id', d.id,
  'order_id', d.order_id,
  'courier_name', c.name,
  'requested_at', d.requested_at,
  'minutes_waiting', floor(extract(epoch FROM (timezone('utc', now()) - d.requested_at)) / 60)::int
)::text
FROM public.dispatch_requests d
JOIN public.courier_partners c ON c.id = d.courier_partner_id
WHERE d.status = 'requested'
  AND d.requested_at <= timezone('utc', now()) - interval '{int(minutes)} minutes'
ORDER BY d.requested_at ASC
LIMIT 100;
""",
        context="stale dispatch lookup",
    )
    for row in rows:
        row["order_reference"] = order_reference(str(row["order_id"]))
    return rows


# ---------------------------------------------------------------------------
# Logistics phase 1: one combined "handed over + cash recorded" action
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CompleteResult:
    dispatch_id: str
    order_id: str
    order_status: str | None
    delivered_via: str
    cod_collected_ngwee: int | None


def complete_delivery(
    *,
    dispatch_id: str,
    actor_id: str,
    handover_code: str | None,
    pod_photo_public_id: str | None,
    cod_collected_ngwee: int | None,
    cod_collected_method: str | None,
    rate_limiter: Callable[[str], None] | None = None,
) -> CompleteResult:
    """Deliver a picked-up job AND record the rider's cash in one step.

    Proof is the customer's handover code (preferred) or a POD photo. For a
    cash job the collected amount must equal the dispatch snapshot; it is
    written in the same transaction as the delivery (write-once custody).
    """
    if bool(handover_code) == bool(pod_photo_public_id):
        raise AppError(
            code="validation_error",
            message="Give either the customer's handover code or a delivery photo",
            http_status=422,
        )
    dispatch = fetch_dispatch(dispatch_id)
    if dispatch.direction != "delivery":
        raise AppError(
            code="dispatch_return_ack_required",
            message="A return is closed when the shop acknowledges the goods",
            http_status=409,
        )
    # Validate the cash before any proof is consumed.
    custody_fields(
        dispatch,
        cod_collected_ngwee=cod_collected_ngwee,
        cod_collected_method=cod_collected_method,
    )
    if handover_code:
        handover = verify_handover_code(
            dispatch_id=dispatch_id,
            code=handover_code,
            actor_id=actor_id,
            rate_limiter=rate_limiter,
            cod_collected_ngwee=cod_collected_ngwee,
            cod_collected_method=cod_collected_method,
            require_custody=True,
        )
        return CompleteResult(
            dispatch_id=dispatch_id,
            order_id=handover.order_id,
            order_status=handover.order_status,
            delivered_via="handover_code",
            cod_collected_ngwee=cod_collected_ngwee if dispatch.cod_amount_ngwee > 0 else None,
        )
    result = transition_dispatch_admin(
        dispatch_id=dispatch_id,
        to_status=DispatchStatus.DELIVERED,
        actor_id=actor_id,
        note="Delivered (photo) and cash recorded",
        pod_photo_public_id=pod_photo_public_id,
        cod_collected_ngwee=cod_collected_ngwee,
        cod_collected_method=cod_collected_method,
    )
    return CompleteResult(
        dispatch_id=dispatch_id,
        order_id=dispatch.order_id,
        order_status=result.order_status,
        delivered_via="pod_photo",
        cod_collected_ngwee=cod_collected_ngwee if dispatch.cod_amount_ngwee > 0 else None,
    )


# ---------------------------------------------------------------------------
# Return to vendor: the shop acknowledges the goods -> cancel + restock
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ReturnAckResult:
    dispatch_id: str
    order_id: str
    order_status: str


def acknowledge_return(
    *,
    dispatch_id: str,
    actor_id: str,
    note: str,
    full_admin: bool,
) -> ReturnAckResult:
    """Close a return job and cancel the shipped order with its stock put back.

    The order is cancelled through the order state machine with
    ``return_restock`` (the stock-release trigger restocks shipped orders only
    on this path). A prepaid order also needs refund authority, which only a
    full admin holds: a logistics-only operator gets ``order_refund_path_required``
    and finance completes it.
    """
    dispatch = fetch_dispatch(dispatch_id)
    if dispatch.direction != "return":
        raise AppError(
            code="dispatch_not_return",
            message="Only a return job can be acknowledged by the shop",
            http_status=409,
        )
    if dispatch.status not in {DispatchStatus.ACCEPTED, DispatchStatus.PICKED_UP}:
        raise DispatchTransitionError(
            "Return must be accepted or picked up before the shop acknowledges it",
            from_status=dispatch.status.value,
            to_status=DispatchStatus.DELIVERED.value,
        )
    text = note.strip() or "Returned goods acknowledged by the shop"
    snapshot, _ = check_order_transition(
        order_id=dispatch.order_id,
        event=OrderEvent.CANCEL,
        actor_role=ActorRole.ADMIN,
        refund_path=full_admin,
    )
    if snapshot.status is not OrderStatus.SHIPPED:
        raise AppError(
            code="dispatch_order_not_ready",
            message="Only a shipped order can be returned to the shop",
            http_status=409,
            details={"order_status": snapshot.status.value},
        )
    if dispatch.status is DispatchStatus.ACCEPTED:
        apply_dispatch_transition(
            dispatch_id=dispatch_id,
            from_status=DispatchStatus.ACCEPTED,
            to_status=DispatchStatus.PICKED_UP,
            actor_id=actor_id,
            note="Return collected from the customer",
        )
    outcome = transition_order(
        order_id=dispatch.order_id,
        event=OrderEvent.CANCEL,
        actor_role=ActorRole.ADMIN,
        actor_id=actor_id,
        note=f"[courier-dispatch] returned to shop ({dispatch_id}): {text}"[:500],
        refund_path=full_admin,
        return_restock=True,
    )
    apply_dispatch_transition(
        dispatch_id=dispatch_id,
        from_status=DispatchStatus.PICKED_UP,
        to_status=DispatchStatus.DELIVERED,
        actor_id=actor_id,
        note=text,
        set_fields={"delivered_via": "vendor_ack"},
    )
    return ReturnAckResult(
        dispatch_id=dispatch_id,
        order_id=dispatch.order_id,
        order_status=outcome.to_status.value,
    )


# ---------------------------------------------------------------------------
# Actual courier cost (margin reporting)
# ---------------------------------------------------------------------------


def record_actual_cost(*, dispatch_id: str, cost_ngwee: int, actor_id: str) -> DispatchRow:
    """Record what the courier actually charged for this job (integer ngwee)."""
    if isinstance(cost_ngwee, bool) or not isinstance(cost_ngwee, int) or cost_ngwee < 0:
        raise AppError(
            code="validation_error",
            message="cost must be non-negative integer ngwee",
            http_status=422,
        )
    if cost_ngwee > 5_000_000:
        raise AppError(
            code="validation_error",
            message="cost is implausibly high (over K50,000)",
            http_status=422,
        )
    dispatch_sql = sql_uuid(dispatch_id, "dispatch_id")
    actor_sql = sql_uuid(actor_id, "actor_id")
    rows = json_rows(
        f"""
BEGIN;
UPDATE public.dispatch_requests
SET actual_cost_ngwee = {cost_ngwee},
    cost_recorded_at = timezone('utc', now()),
    cost_recorded_by = {actor_sql}
WHERE id = {dispatch_sql}
  AND status IN ('picked_up', 'delivered', 'failed', 'cancelled')
RETURNING json_build_object('id', id)::text;
COMMIT;
""",
        context="record dispatch cost",
    )
    if not rows:
        raise AppError(
            code="dispatch_cost_not_allowed",
            message="Record the cost once the courier has collected (or the job ended)",
            http_status=409,
        )
    return fetch_dispatch(dispatch_id)


# ---------------------------------------------------------------------------
# Stale jobs (accepted not collected, picked up not delivered)
# ---------------------------------------------------------------------------


def _config_minutes(key: str, default: int) -> int:
    result = run_sql_script(f"SELECT value::text FROM public.platform_config WHERE key = '{key}';")
    if result.ok and result.rows and result.rows[0].isdigit() and int(result.rows[0]) > 0:
        return int(result.rows[0])
    return default


def list_stale_active() -> list[dict[str, Any]]:
    """Accepted > N min (not collected) and picked up > M min (not delivered)."""
    accepted = _config_minutes("dispatch_stale_accepted_minutes", 45)
    picked = _config_minutes("dispatch_stale_picked_up_minutes", 120)
    rows = json_rows(
        f"""
SELECT json_build_object(
  'dispatch_id', d.id,
  'order_id', d.order_id,
  'status', d.status,
  'courier_name', c.name,
  'since', CASE d.status WHEN 'accepted' THEN d.accepted_at ELSE d.picked_up_at END,
  'minutes_waiting', floor(extract(epoch FROM (timezone('utc', now()) -
      CASE d.status WHEN 'accepted' THEN d.accepted_at ELSE d.picked_up_at END)) / 60)::int
)::text
FROM public.dispatch_requests d
JOIN public.courier_partners c ON c.id = d.courier_partner_id
WHERE (d.status = 'accepted'
       AND d.accepted_at <= timezone('utc', now()) - interval '{int(accepted)} minutes')
   OR (d.status = 'picked_up'
       AND d.picked_up_at <= timezone('utc', now()) - interval '{int(picked)} minutes')
ORDER BY CASE d.status WHEN 'accepted' THEN d.accepted_at ELSE d.picked_up_at END ASC
LIMIT 100;
""",
        context="stale active dispatch lookup",
    )
    for row in rows:
        row["order_reference"] = order_reference(str(row["order_id"]))
    return rows
