"""Checkout funnel event recorder and abandonment sweeper."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from app.services.notifications.dedupe import build_dedupe_key
from app.services.stock.claim import run_sql_script, sql_uuid

logger = logging.getLogger(__name__)

FunnelStage = Literal[
    "cart_add",
    "checkout_start",
    "step_complete",
    "payment_start",
    "order_placed",
    "abandoned",
]

FUNNEL_STAGES: tuple[FunnelStage, ...] = (
    "cart_add",
    "checkout_start",
    "step_complete",
    "payment_start",
    "order_placed",
    "abandoned",
)

_ABANDONED_CHECKOUT_FLAG = "abandoned_cart"
_ABANDONED_OUTBOX_EVENT = "abandoned_checkout"
_ABANDONED_OUTBOX_TEMPLATE = "abandoned_cart_recovery"
_OUTBOX_CHANNEL = "whatsapp"

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class AbandonSweepResult:
    scanned: int
    abandoned: int
    notifications_enqueued: int


def _validate_uuid(value: str, field: str) -> None:
    if not _UUID_RE.match(value):
        raise ValueError(f"Invalid UUID for {field}")
    UUID(value)


def _sql_json(value: dict[str, Any]) -> str:
    payload = json.dumps(value, separators=(",", ":"), sort_keys=True)
    return "'" + payload.replace("'", "''") + "'::jsonb"


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _is_feature_flag_enabled(flag: str) -> bool:
    result = run_sql_script(
        f"""
SELECT coalesce(enabled, false)::text
FROM public.feature_flags
WHERE flag = {_sql_literal(flag)}
LIMIT 1;
"""
    )
    if not result.ok or not result.rows:
        return False
    return result.rows[0] in {"t", "true"}


def _load_customer_contact(customer_id: str) -> dict[str, str]:
    customer_sql = sql_uuid(customer_id, "customer_id")
    result = run_sql_script(
        f"""
SELECT coalesce(phone, ''), coalesce(locale, 'en')
FROM public.profiles
WHERE id = {customer_sql};
"""
    )
    if not result.ok or not result.rows:
        return {}
    parts = result.rows[0].split("|")
    if len(parts) != 2:
        return {}
    return {"phone": parts[0], "locale": parts[1]}


def _enqueue_abandoned_checkout_sql(
    *,
    checkout_group_id: str,
    payload: dict[str, Any],
) -> bool:
    dedupe_key = build_dedupe_key(_ABANDONED_OUTBOX_EVENT, checkout_group_id, _OUTBOX_CHANNEL)
    result = run_sql_script(
        f"""
INSERT INTO public.notification_outbox (dedupe_key, channel, template, payload, status)
VALUES (
  {_sql_literal(dedupe_key)},
  {_sql_literal(_OUTBOX_CHANNEL)},
  {_sql_literal(_ABANDONED_OUTBOX_TEMPLATE)},
  {_sql_json(payload)},
  'pending'
)
ON CONFLICT (dedupe_key) DO NOTHING
RETURNING id::text;
"""
    )
    if not result.ok:
        raise RuntimeError(f"enqueue abandoned_checkout failed: {result.error}")
    return bool(result.rows)


def record_event(
    *,
    stage: FunnelStage,
    checkout_group_id: str | None,
    snapshot: dict[str, Any],
    customer_id: str | None = None,
) -> dict[str, Any] | None:
    """Insert a funnel row; idempotent per (checkout_group_id, stage).

    Returns the inserted row, or None when the stage was already recorded.
    """
    if checkout_group_id is not None:
        _validate_uuid(checkout_group_id, "checkout_group_id")
    if customer_id is not None:
        _validate_uuid(customer_id, "customer_id")

    group_sql = (
        "null"
        if checkout_group_id is None
        else sql_uuid(checkout_group_id, "checkout_group_id")
    )
    customer_sql = "null" if customer_id is None else sql_uuid(customer_id, "customer_id")
    snapshot_sql = _sql_json(snapshot)

    if checkout_group_id is None:
        insert_sql = f"""
INSERT INTO public.funnel_events (stage, checkout_group_id, customer_id, snapshot)
VALUES ('{stage}', null, {customer_sql}, {snapshot_sql})
RETURNING id::text, stage, created_at::text;
"""
    else:
        insert_sql = f"""
INSERT INTO public.funnel_events (stage, checkout_group_id, customer_id, snapshot)
VALUES ('{stage}', {group_sql}, {customer_sql}, {snapshot_sql})
ON CONFLICT (checkout_group_id, stage) WHERE checkout_group_id IS NOT NULL
DO NOTHING
RETURNING id::text, stage, created_at::text;
"""
    result = run_sql_script(insert_sql)
    if not result.ok:
        raise RuntimeError(f"funnel record_event failed: {result.error}")
    if not result.rows:
        return None
    parts = result.rows[0].split("|")
    if len(parts) < 3:
        return None
    return {"id": parts[0], "stage": parts[1], "created_at": parts[2]}


def record_event_best_effort(
    *,
    stage: FunnelStage,
    checkout_group_id: str | None,
    snapshot: dict[str, Any],
    customer_id: str | None = None,
) -> dict[str, Any] | None:
    """Fire-and-forget ``record_event``: swallow every error so a funnel emit on a
    live request path (cart/checkout/payment/order) can never break that request.

    Returns the inserted row, or ``None`` when the stage was already recorded OR the
    write failed. Server operational analytics — written regardless of consent.
    """
    try:
        return record_event(
            stage=stage,
            checkout_group_id=checkout_group_id,
            snapshot=snapshot,
            customer_id=customer_id,
        )
    except Exception:  # noqa: BLE001 — analytics must never break the caller.
        logger.debug("funnel emit swallowed for stage=%s", stage, exc_info=True)
        return None


def _fetch_abandon_candidates() -> list[str]:
    """Checkout groups with expired reservations and no order_placed or prior abandoned event."""
    result = run_sql_script(
        """
SELECT DISTINCT sr.checkout_group_id::text
FROM public.stock_reservations sr
WHERE sr.expires_at < timezone('utc', now())
  AND NOT EXISTS (
    SELECT 1 FROM public.funnel_events fe
    WHERE fe.checkout_group_id = sr.checkout_group_id
      AND fe.stage = 'order_placed'
  )
  AND NOT EXISTS (
    SELECT 1 FROM public.funnel_events fe
    WHERE fe.checkout_group_id = sr.checkout_group_id
      AND fe.stage = 'abandoned'
  )
  AND NOT EXISTS (
    SELECT 1 FROM public.orders o
    WHERE o.checkout_group_id = sr.checkout_group_id
  );
"""
    )
    if not result.ok:
        raise RuntimeError(f"fetch abandon candidates failed: {result.error}")
    return [row for row in result.rows if row]


def _build_cart_snapshot(checkout_group_id: str) -> dict[str, Any]:
    group_sql = sql_uuid(checkout_group_id, "checkout_group_id")
    group_result = run_sql_script(
        f"""
SELECT
  cg.id::text,
  cg.customer_id::text,
  cg.status,
  cg.subtotal_ngwee::text,
  cg.delivery_fee_ngwee::text,
  cg.total_ngwee::text
FROM public.checkout_groups cg
WHERE cg.id = {group_sql};
"""
    )
    if not group_result.ok or not group_result.rows:
        return {"checkout_group_id": checkout_group_id, "lines": []}

    parts = group_result.rows[0].split("|")
    snapshot: dict[str, Any] = {
        "checkout_group_id": parts[0] if len(parts) > 0 else checkout_group_id,
        "customer_id": parts[1] if len(parts) > 1 else None,
        "status": parts[2] if len(parts) > 2 else "pending",
        "subtotal_ngwee": int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0,
        "delivery_fee_ngwee": int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 0,
        "total_ngwee": int(parts[5]) if len(parts) > 5 and parts[5].isdigit() else 0,
        "lines": [],
    }

    lines_result = run_sql_script(
        f"""
SELECT listing_id::text, qty::text
FROM public.stock_reservations
WHERE checkout_group_id = {group_sql};
"""
    )
    if lines_result.ok:
        for row in lines_result.rows:
            line_parts = row.split("|")
            if len(line_parts) == 2:
                snapshot["lines"].append(
                    {"listing_id": line_parts[0], "qty": int(line_parts[1])}
                )
    return snapshot


def _maybe_enqueue_abandoned_checkout(
    *,
    checkout_group_id: str,
    snapshot: dict[str, Any],
) -> bool:
    if not _is_feature_flag_enabled(_ABANDONED_CHECKOUT_FLAG):
        return False

    customer_id = snapshot.get("customer_id")
    if not isinstance(customer_id, str) or not customer_id:
        return False

    contact = _load_customer_contact(customer_id)
    phone = contact.get("phone")
    if not isinstance(phone, str) or not phone.strip():
        return False

    payload: dict[str, Any] = {
        "checkout_group_id": checkout_group_id,
        "recipient_id": customer_id,
        "phone_e164": phone.strip(),
        "locale": str(contact.get("locale", "en")),
        "total_ngwee": snapshot.get("total_ngwee"),
        "lines": snapshot.get("lines", []),
        "abandoned_at": datetime.now(UTC).isoformat(),
    }
    return _enqueue_abandoned_checkout_sql(
        checkout_group_id=checkout_group_id,
        payload=payload,
    )


def sweep_abandoned(now: datetime | None = None) -> AbandonSweepResult:
    """Detect checkout abandonment on reservation expiry; optionally enqueue recovery outbox."""
    _ = now  # reserved for deterministic tests; queries use DB clock
    candidates = _fetch_abandon_candidates()
    abandoned = 0
    notifications_enqueued = 0

    for checkout_group_id in candidates:
        snapshot = _build_cart_snapshot(checkout_group_id)
        recorded = record_event(
            stage="abandoned",
            checkout_group_id=checkout_group_id,
            snapshot=snapshot,
            customer_id=snapshot.get("customer_id")
            if isinstance(snapshot.get("customer_id"), str)
            else None,
        )
        if recorded is None:
            continue
        abandoned += 1
        if _maybe_enqueue_abandoned_checkout(
            checkout_group_id=checkout_group_id,
            snapshot=snapshot,
        ):
            notifications_enqueued += 1

    return AbandonSweepResult(
        scanned=len(candidates),
        abandoned=abandoned,
        notifications_enqueued=notifications_enqueued,
    )
