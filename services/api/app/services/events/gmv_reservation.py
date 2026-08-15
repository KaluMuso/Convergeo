"""Transactional Tier-1 organiser GMV reservations (EVT-GMV-ATOMIC).

Paid-ticket checkouts reserve GMV headroom until payment succeeds (captured) or the
checkout expires / is released. Concurrent pending checkouts cannot collectively exceed
the configured per-event cap.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.errors import AppError
from app.services.events.gmv_cap import (
    CONFIG_KEY,
    _resolve_cap_tier,
    _write_cap_reject_audit,
    event_paid_gmv_ngwee,
    load_organiser_t1_event_gmv_cap_ngwee,
)
from app.services.stock.claim import run_sql_script, sql_int, sql_uuid


def _expires_literal(*, ttl_minutes: int, now: datetime | None = None) -> str:
    anchor = now or datetime.now(UTC)
    expires = anchor + timedelta(minutes=ttl_minutes)
    return expires.strftime("%Y-%m-%d %H:%M:%S+00")


def _cap_exceeded_error(
    *,
    organiser_vendor_id: str,
    event_id: str,
    current_gmv_ngwee: int,
    reserved_gmv_ngwee: int,
    additional_ngwee: int,
    cap_ngwee: int,
    cap_tier: int,
) -> AppError:
    projected = current_gmv_ngwee + reserved_gmv_ngwee + additional_ngwee
    return AppError(
        code="organiser_gmv_cap_exceeded",
        message="Tier-1 organiser per-event ticket GMV cap exceeded",
        http_status=403,
        details={
            "message_key": "events.ticketPurchase.errors.organiserGmvCapExceeded",
            "event_id": event_id,
            "organiser_vendor_id": organiser_vendor_id,
            "current_gmv_ngwee": current_gmv_ngwee,
            "reserved_gmv_ngwee": reserved_gmv_ngwee,
            "additional_ngwee": additional_ngwee,
            "projected_gmv_ngwee": projected,
            "cap_ngwee": cap_ngwee,
            "cap_tier": cap_tier,
            "config_key": CONFIG_KEY,
        },
    )


def event_active_reserved_gmv_ngwee(event_id: str) -> int:
    """Sum non-expired reserved GMV for an event (excludes captured/released rows)."""
    event_sql = sql_uuid(event_id, "event_id")
    result = run_sql_script(
        f"""
SELECT coalesce(sum(amount_ngwee), 0)::text
FROM public.event_gmv_reservations
WHERE event_id = {event_sql}
  AND status = 'reserved'
  AND expires_at > timezone('utc', now());
"""
    )
    if not result.ok or not result.rows:
        raise RuntimeError(f"event reserved GMV query failed: {result.error}")
    return int(result.rows[0])


def build_atomic_gmv_reserve_sql(
    *,
    checkout_group_id: str,
    organiser_vendor_id: str,
    event_id: str,
    amount_ngwee: int,
    expires_at_literal: str,
) -> str:
    """SQL fragment (no BEGIN/COMMIT) that inserts a reservation or returns zero rows."""
    group_sql = sql_uuid(checkout_group_id, "checkout_group_id")
    vendor_sql = sql_uuid(organiser_vendor_id, "organiser_vendor_id")
    event_sql = sql_uuid(event_id, "event_id")
    amount_sql = sql_int(amount_ngwee, "amount_ngwee")
    key_sql = "'" + CONFIG_KEY.replace("'", "''") + "'"
    return f"""
SELECT pg_advisory_xact_lock(hashtext('event_gmv:' || {event_sql}::text));
WITH cap_row AS (
  SELECT coalesce(
    (
      SELECT CASE
        WHEN jsonb_typeof(value) = 'number' AND (value #>> '{{}}') ~ '^[0-9]+$'
          THEN (value #>> '{{}}')::bigint
        WHEN jsonb_typeof(value) = 'string' AND trim(both '"' from value::text) ~ '^[0-9]+$'
          THEN trim(both '"' from value::text)::bigint
        ELSE NULL
      END
      FROM public.platform_config
      WHERE key = {key_sql}
      LIMIT 1
    ),
    2000000
  ) AS cap_ngwee
),
usage AS (
  SELECT
    (
      SELECT coalesce(sum(oi.qty * oi.unit_price_ngwee), 0)::bigint
      FROM public.order_items oi
      INNER JOIN public.order_item_tickets oit ON oit.order_item_id = oi.id
      INNER JOIN public.ticket_types tt ON tt.id = oit.ticket_type_id
      INNER JOIN public.orders o ON o.id = oi.order_id
      WHERE tt.event_id = {event_sql}
        AND oi.item_kind = 'ticket'
        AND tt.kind <> 'free_rsvp'
        AND EXISTS (
          SELECT 1
          FROM public.payments p
          WHERE p.checkout_group_id = o.checkout_group_id
            AND p.status = 'success'
        )
    ) AS paid_ngwee,
    (
      SELECT coalesce(sum(r.amount_ngwee), 0)::bigint
      FROM public.event_gmv_reservations r
      WHERE r.event_id = {event_sql}
        AND r.status = 'reserved'
        AND r.expires_at > timezone('utc', now())
    ) AS reserved_ngwee
),
allowed AS (
  SELECT 1
  FROM cap_row, usage
  WHERE usage.paid_ngwee + usage.reserved_ngwee + {amount_sql} <= cap_row.cap_ngwee
),
inserted AS (
  INSERT INTO public.event_gmv_reservations (
    checkout_group_id, event_id, organiser_vendor_id, amount_ngwee, status, expires_at
  )
  SELECT
    {group_sql}, {event_sql}, {vendor_sql}, {amount_sql}, 'reserved',
    '{expires_at_literal}'::timestamptz
  FROM allowed
  RETURNING checkout_group_id
)
SELECT coalesce((SELECT count(*)::text FROM inserted), '0');
"""


def reserve_organiser_t1_gmv_for_checkout(
    service: Any,
    *,
    checkout_group_id: str,
    organiser_vendor_id: str,
    event_id: str,
    amount_ngwee: int,
    ttl_minutes: int,
    now: datetime | None = None,
) -> None:
    """Atomically reserve GMV headroom for a pending checkout (Tier-1 only)."""
    if amount_ngwee <= 0:
        return

    tier = _resolve_cap_tier(service, organiser_vendor_id)
    if tier >= 2:
        return

    cap_ngwee = load_organiser_t1_event_gmv_cap_ngwee()
    expires_literal = _expires_literal(ttl_minutes=ttl_minutes, now=now)
    reserve_sql = build_atomic_gmv_reserve_sql(
        checkout_group_id=checkout_group_id,
        organiser_vendor_id=organiser_vendor_id,
        event_id=event_id,
        amount_ngwee=amount_ngwee,
        expires_at_literal=expires_literal,
    )
    script = f"""
BEGIN;
{reserve_sql}
COMMIT;
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        raise RuntimeError(f"GMV reservation failed: {result.error}")
    if result.rows[0] != "1":
        paid = event_paid_gmv_ngwee(event_id)
        reserved = event_active_reserved_gmv_ngwee(event_id)
        _write_cap_reject_audit(
            service,
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


def capture_gmv_reservation(checkout_group_id: str) -> bool:
    """Mark a reserved GMV row captured after successful payment."""
    group_sql = sql_uuid(checkout_group_id, "checkout_group_id")
    result = run_sql_script(
        f"""
UPDATE public.event_gmv_reservations
SET status = 'captured',
    captured_at = timezone('utc', now()),
    updated_at = timezone('utc', now())
WHERE checkout_group_id = {group_sql}
  AND status = 'reserved'
RETURNING checkout_group_id::text;
"""
    )
    if not result.ok:
        raise RuntimeError(f"capture GMV reservation failed: {result.error}")
    return bool(result.rows)


def release_gmv_reservation(checkout_group_id: str) -> bool:
    """Release a pending GMV reservation (checkout cancelled / expired)."""
    group_sql = sql_uuid(checkout_group_id, "checkout_group_id")
    result = run_sql_script(
        f"""
UPDATE public.event_gmv_reservations
SET status = 'released',
    released_at = timezone('utc', now()),
    updated_at = timezone('utc', now())
WHERE checkout_group_id = {group_sql}
  AND status = 'reserved'
RETURNING checkout_group_id::text;
"""
    )
    if not result.ok:
        raise RuntimeError(f"release GMV reservation failed: {result.error}")
    return bool(result.rows)


def release_expired_gmv_reservations() -> int:
    """Release reserved GMV rows past expiry (capacity recovery)."""
    result = run_sql_script(
        """
UPDATE public.event_gmv_reservations
SET status = 'released',
    released_at = timezone('utc', now()),
    updated_at = timezone('utc', now())
WHERE status = 'reserved'
  AND expires_at <= timezone('utc', now())
RETURNING checkout_group_id::text;
"""
    )
    if not result.ok:
        raise RuntimeError(f"release expired GMV reservations failed: {result.error}")
    return len(result.rows)
