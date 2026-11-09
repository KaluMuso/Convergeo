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
    DispatchRow,
    DispatchStatus,
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
DISPATCHABLE_ORDER_STATUSES = frozenset({"confirmed", "processing"})
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
  'pickup', (
    SELECT json_build_object('landmark', vl.landmark, 'lat', vl.lat, 'lng', vl.lng,
                             'phone', vl.phone_e164)
    FROM public.vendor_locations vl
    WHERE vl.vendor_id = o.vendor_id AND coalesce(vl.status, 'active') = 'active'
    ORDER BY vl.is_primary DESC, vl.created_at ASC
    LIMIT 1
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


def create_dispatch(
    *,
    order_id: str,
    courier_partner_id: str,
    actor_id: str,
    note: str = "Dispatch requested",
) -> CreateDispatchResult:
    order = load_order_dispatch_context(order_id)
    if order.get("fulfilment") != "delivery":
        raise AppError(
            code="dispatch_not_applicable",
            message="Courier dispatch applies only to delivery orders",
            http_status=409,
        )
    if order.get("status") not in DISPATCHABLE_ORDER_STATUSES:
        raise AppError(
            code="dispatch_order_not_ready",
            message="Order is not ready for courier dispatch",
            http_status=409,
            details={"status": order.get("status"), "allowed": sorted(DISPATCHABLE_ORDER_STATUSES)},
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

    cod_amount = int(order["cod_amount_ngwee"])
    code = generate_handover_code()
    order_sql = sql_uuid(order_id, "order_id")
    courier_sql = sql_uuid(courier_partner_id, "courier_partner_id")
    actor_sql = sql_uuid(actor_id, "actor_id")
    price_sql = str(price) if price is not None else "NULL"
    script = f"""
BEGIN;
{audit_context_sql(actor_id=actor_id, note=note)}
WITH ins AS (
  INSERT INTO public.dispatch_requests (
    order_id, courier_partner_id, status, cod_amount_ngwee, quoted_price_ngwee, created_by
  ) VALUES (
    {order_sql}, {courier_sql}, 'requested', {cod_amount}, {price_sql}, {actor_sql}
  )
  RETURNING id
)
INSERT INTO public.dispatch_handover_codes (dispatch_request_id, code)
SELECT id, {sql_literal(code)} FROM ins
RETURNING json_build_object('id', dispatch_request_id)::text;
COMMIT;
"""
    result = run_sql_script(script)
    if not result.ok:
        if "dispatch_requests_one_active_per_order" in (result.error or "") or (
            "dispatch_requests_one_delivered_per_order" in (result.error or "")
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
        if order_status == OrderStatus.PROCESSING.value:
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


def _preflight_order(order_id: str, target: DispatchStatus) -> OrderEvent | None:
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
) -> AdminTransitionResult:
    dispatch = fetch_dispatch(dispatch_id)
    assert_transition(dispatch.status, to_status)

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

    order_event = (
        _preflight_order(dispatch.order_id, to_status)
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


def _claim_handover(dispatch_id: str, *, actor_id: str) -> bool:
    """Single-use claim: code verified + dispatch delivered in ONE transaction."""
    dispatch_sql = sql_uuid(dispatch_id, "dispatch_id")
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
SET status = 'delivered', delivered_via = 'handover_code'
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
    order_event = _preflight_order(order_id, DispatchStatus.DELIVERED)
    if not _claim_handover(dispatch_id, actor_id=actor_id):
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
  )
)::text
FROM public.orders o
JOIN public.vendors v ON v.id = o.vendor_id
WHERE o.fulfilment = 'delivery'
  AND o.status IN ('confirmed', 'processing')
  AND NOT EXISTS (
    SELECT 1 FROM public.dispatch_requests d
    WHERE d.order_id = o.id AND d.status IN ('requested', 'accepted', 'picked_up', 'delivered')
  )
ORDER BY (o.status = 'processing') DESC, o.created_at ASC
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
