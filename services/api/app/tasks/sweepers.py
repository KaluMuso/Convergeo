"""Automated background sweepers — escrow release, cart expiry, daily n8n reporting.

Invoked by n8n schedule triggers via ``/internal/sweepers/*`` ticks. Each sweep
logs the exact row count affected and wraps per-row mutations in atomic DB
transactions (via the underlying service helpers).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol

from app.services.escrow.release import ReleaseResult, evaluate_and_release
from app.services.escrow.release_accounting import OPEN_DISPUTE_STATUSES
from app.services.orders.audit import run_sql_script, sql_literal
from app.services.stock.release import ReleaseResult as StockReleaseResult
from app.services.stock.release import release_reservation
from app.services.webhooks.n8n_dispatch import build_n8n_payload, post_n8n_webhook
from app.settings import Settings, get_settings

logger = logging.getLogger(__name__)

ESCROW_HOLD_MIN_AGE_HOURS = 48
CART_RESERVATION_MAX_AGE_MINUTES = 15


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


@dataclass(frozen=True, slots=True)
class EscrowSweepResult:
    scanned: int
    released: int
    held: int
    already_released: int
    not_eligible: int
    payout_vendors_queued: int


@dataclass(frozen=True, slots=True)
class CartReservationSweepResult:
    scanned: int
    released: int
    restocked_qty: int


@dataclass(frozen=True, slots=True)
class DailySummaryResult:
    report_date: date
    gmv_ngwee: int
    total_orders: int
    new_users: int
    dispatched: bool


def _open_dispute_filter_sql(*, order_alias: str = "o") -> str:
    statuses_sql = ", ".join(sql_literal(status) for status in sorted(OPEN_DISPUTE_STATUSES))
    return f"""
NOT EXISTS (
  SELECT 1
  FROM public.disputes d
  WHERE d.order_id = {order_alias}.id
    AND d.status IN ({statuses_sql})
)
"""


def _list_held_escrow_order_ids(
    *,
    min_age_hours: int,
    now: datetime,
) -> list[str]:
    """Return order IDs whose ``escrow_hold`` is still held and older than *min_age_hours*."""
    deadline = now - timedelta(hours=min_age_hours)
    deadline_sql = sql_literal(deadline.isoformat())
    dispute_filter = _open_dispute_filter_sql(order_alias="o")
    release_prefix = sql_literal("release-")
    script = f"""
SELECT DISTINCT lt.order_id::text
FROM public.ledger_transactions lt
INNER JOIN public.orders o ON o.id = lt.order_id
WHERE lt.kind = 'escrow_hold'
  AND lt.order_id IS NOT NULL
  AND lt.created_at <= {deadline_sql}::timestamptz
  AND o.cod = false
  AND {dispute_filter}
  AND NOT EXISTS (
    SELECT 1
    FROM public.ledger_transactions rel
    WHERE rel.order_id = lt.order_id
      AND rel.kind = 'release_to_vendor'
  )
  AND NOT EXISTS (
    SELECT 1
    FROM public.ledger_transactions rel
    WHERE rel.idempotency_key = ({release_prefix} || lt.order_id::text)
  )
ORDER BY lt.order_id ASC;
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"list held escrows failed: {result.error}")
    return result.rows


def _fetch_expired_cart_reservations() -> list[tuple[str, str]]:
    """Reservations older than the cart TTL (15 minutes) that have not yet expired."""
    script = f"""
SELECT listing_id::text, checkout_group_id::text
FROM public.stock_reservations
WHERE created_at < timezone('utc', now()) - interval '{CART_RESERVATION_MAX_AGE_MINUTES} minutes';
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"fetch expired cart reservations failed: {result.error}")

    expired: list[tuple[str, str]] = []
    for row in result.rows:
        parts = row.split("|")
        if len(parts) == 2:
            expired.append((parts[0], parts[1]))
    return expired


def _utc_day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return start, start + timedelta(days=1)


def _count_daily_orders(*, day_start: datetime, day_end: datetime) -> int:
    start_sql = sql_literal(day_start.isoformat())
    end_sql = sql_literal(day_end.isoformat())
    script = f"""
SELECT count(*)::text
FROM public.orders
WHERE created_at >= {start_sql}::timestamptz
  AND created_at < {end_sql}::timestamptz;
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        raise RuntimeError(f"daily orders count failed: {result.error}")
    return int(result.rows[0])


def _compute_daily_gmv_ngwee(*, day_start: datetime, day_end: datetime) -> int:
    start_sql = sql_literal(day_start.isoformat())
    end_sql = sql_literal(day_end.isoformat())
    script = f"""
SELECT coalesce(sum(item_totals.item_total + o.delivery_fee_ngwee), 0)::text
FROM public.orders o
JOIN (
  SELECT order_id, coalesce(sum(qty * unit_price_ngwee), 0) AS item_total
  FROM public.order_items
  GROUP BY order_id
) item_totals ON item_totals.order_id = o.id
WHERE o.created_at >= {start_sql}::timestamptz
  AND o.created_at < {end_sql}::timestamptz
  AND o.status <> 'cancelled';
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        raise RuntimeError(f"daily GMV query failed: {result.error}")
    return int(result.rows[0])


def _count_daily_new_users(*, day_start: datetime, day_end: datetime) -> int:
    start_sql = sql_literal(day_start.isoformat())
    end_sql = sql_literal(day_end.isoformat())
    script = f"""
SELECT count(*)::text
FROM public.profiles
WHERE created_at >= {start_sql}::timestamptz
  AND created_at < {end_sql}::timestamptz
  AND deleted_at IS NULL;
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        raise RuntimeError(f"daily new users count failed: {result.error}")
    return int(result.rows[0])


def sweep_expired_escrows(
    service_client: ServiceRoleClient,
    *,
    now: datetime | None = None,
    min_age_hours: int = ESCROW_HOLD_MIN_AGE_HOURS,
) -> EscrowSweepResult:
    """Release escrow holds older than *min_age_hours* with no open dispute.

    Each release posts ledger entries atomically via ``evaluate_and_release``.
    Vendors with newly released balances are counted for the payout queue.
    """
    effective_now = now or datetime.now(UTC)
    if effective_now.tzinfo is None:
        effective_now = effective_now.replace(tzinfo=UTC)

    order_ids = _list_held_escrow_order_ids(
        min_age_hours=min_age_hours,
        now=effective_now,
    )

    released = 0
    held = 0
    already_released = 0
    not_eligible = 0
    released_vendor_ids: set[str] = set()

    for order_id in order_ids:
        result: ReleaseResult = evaluate_and_release(
            service_client,
            order_id,
            now=effective_now,
        )
        if result.outcome == "released":
            released += 1
            vendor_id = _vendor_id_for_order(order_id)
            if vendor_id is not None:
                released_vendor_ids.add(vendor_id)
        elif result.outcome == "held":
            held += 1
        elif result.outcome == "already_released":
            already_released += 1
        else:
            not_eligible += 1

    payout_vendors_queued = len(released_vendor_ids)

    logger.info(
        "sweep_expired_escrows complete",
        extra={
            "scanned": len(order_ids),
            "released": released,
            "held": held,
            "already_released": already_released,
            "not_eligible": not_eligible,
            "payout_vendors_queued": payout_vendors_queued,
        },
    )

    return EscrowSweepResult(
        scanned=len(order_ids),
        released=released,
        held=held,
        already_released=already_released,
        not_eligible=not_eligible,
        payout_vendors_queued=payout_vendors_queued,
    )


def _vendor_id_for_order(order_id: str) -> str | None:
    order_sql = sql_literal(order_id)
    script = f"""
SELECT vendor_id::text
FROM public.orders
WHERE id = {order_sql}::uuid
LIMIT 1;
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        return None
    return result.rows[0] or None


def sweep_expired_cart_reservations() -> CartReservationSweepResult:
    """Delete cart reservations older than 15 minutes and restock branch inventory."""
    expired = _fetch_expired_cart_reservations()
    released = 0
    restocked_qty = 0

    for listing_id, checkout_group_id in expired:
        result: StockReleaseResult = release_reservation(
            listing_id=listing_id,
            checkout_group_id=checkout_group_id,
        )
        if result.released:
            released += 1
            restocked_qty += result.qty

    logger.info(
        "sweep_expired_cart_reservations complete",
        extra={
            "scanned": len(expired),
            "released": released,
            "restocked_qty": restocked_qty,
        },
    )

    return CartReservationSweepResult(
        scanned=len(expired),
        released=released,
        restocked_qty=restocked_qty,
    )


def dispatch_daily_summary(
    service_client: ServiceRoleClient,
    *,
    report_date: date | None = None,
    settings: Settings | None = None,
) -> DailySummaryResult:
    """Compute daily GMV/orders/new-users and POST to ``N8N_WEBHOOK_URL``."""
    _ = service_client
    day = report_date or datetime.now(UTC).date()
    day_start, day_end = _utc_day_bounds(day)

    gmv_ngwee = _compute_daily_gmv_ngwee(day_start=day_start, day_end=day_end)
    total_orders = _count_daily_orders(day_start=day_start, day_end=day_end)
    new_users = _count_daily_new_users(day_start=day_start, day_end=day_end)

    cfg = settings or get_settings()
    dispatched = bool(cfg.n8n_webhook_url.strip())
    payload = build_n8n_payload(
        event="daily.summary",
        data={
            "report_date": day.isoformat(),
            "gmv_ngwee": gmv_ngwee,
            "total_orders": total_orders,
            "new_users": new_users,
        },
    )
    post_n8n_webhook(payload, settings=cfg)

    logger.info(
        "dispatch_daily_summary complete",
        extra={
            "report_date": day.isoformat(),
            "gmv_ngwee": gmv_ngwee,
            "total_orders": total_orders,
            "new_users": new_users,
            "dispatched": dispatched,
        },
    )

    return DailySummaryResult(
        report_date=day,
        gmv_ngwee=gmv_ngwee,
        total_orders=total_orders,
        new_users=new_users,
        dispatched=dispatched,
    )
