"""Internal batch jobs for order auto-confirm and auto-release (M09-P10)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.internal_token import InternalTokenMisconfigured, resolve_internal_token
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.escrow.release import (
    DEFAULT_RELEASE_AFTER_DELIVERED_HOURS,
    DEFAULT_RELEASE_AFTER_SHIPPED_DAYS,
    OPEN_DISPUTE_STATUSES,
    ReleaseResult,
    evaluate_and_release,
)
from app.services.orders.audit import run_sql_script, sql_literal
from app.services.orders.state import (
    SYSTEM_ACTOR_ID,
    ActorRole,
    OrderEvent,
    OrderTransitionError,
    transition_order,
)
from fastapi import APIRouter, Depends, Request
from pydantic import Field

router = APIRouter(prefix="/internal/order-jobs", tags=["internal-order-jobs"])

_INTERNAL_TOKEN_ENV = "INTERNAL_ORDER_JOBS_TOKEN"
_DEFAULT_INTERNAL_TOKEN = "dev-internal-order-jobs"

DEFAULT_BATCH_LIMIT = 50
MAX_BATCH_LIMIT = 200


class BatchJobRequest(StrictModel):
    limit: int = Field(default=DEFAULT_BATCH_LIMIT, ge=1, le=MAX_BATCH_LIMIT)
    cursor: str | None = None


class AutoConfirmJobResponse(StrictModel):
    scanned: int
    processed: int
    skipped: int
    confirmed: int
    next_cursor: str | None = None


class AutoReleaseJobResponse(StrictModel):
    scanned: int
    processed: int
    skipped: int
    released: int
    held: int
    already_released: int
    not_eligible: int
    next_cursor: str | None = None


def _expected_internal_token() -> str:
    try:
        return resolve_internal_token(
            _INTERNAL_TOKEN_ENV,
            dev_default=_DEFAULT_INTERNAL_TOKEN,
        )
    except InternalTokenMisconfigured as exc:
        raise AppError(
            code="configuration_error",
            message=str(exc),
            http_status=503,
        ) from exc


async def require_internal_order_jobs_token(request: Request) -> None:
    """Guard cron ticks — not publicly callable without the shared internal token."""
    expected = _expected_internal_token()
    provided = request.headers.get("X-Internal-Token")
    if not provided or provided != expected:
        raise AppError(
            code="unauthorized",
            message="Invalid or missing internal order jobs token",
            http_status=401,
        )


def _read_config_int(key: str, default: int) -> int:
    key_sql = sql_literal(key)
    script = f"""
SELECT value::text
FROM public.platform_config
WHERE key = {key_sql}
LIMIT 1;
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        return default
    raw = result.rows[0].strip()
    if raw.isdigit():
        return int(raw)
    if raw.startswith('"') and raw.endswith('"') and raw[1:-1].isdigit():
        return int(raw[1:-1])
    return default


def _open_dispute_filter_sql() -> str:
    statuses_sql = ", ".join(sql_literal(status) for status in sorted(OPEN_DISPUTE_STATUSES))
    return f"""
NOT EXISTS (
  SELECT 1
  FROM public.disputes d
  WHERE d.order_id = o.id
    AND d.status IN ({statuses_sql})
)
"""


def _cursor_filter_sql(cursor: str | None) -> str:
    if not cursor:
        return ""
    cursor_sql = sql_literal(cursor)
    return f"AND o.id > {cursor_sql}::uuid"


def _list_auto_confirm_candidates(
    *,
    limit: int,
    cursor: str | None,
    now: datetime,
) -> list[str]:
    confirm_hours = _read_config_int(
        "release_after_delivered_hours",
        DEFAULT_RELEASE_AFTER_DELIVERED_HOURS,
    )
    deadline = now - timedelta(hours=confirm_hours)
    deadline_sql = sql_literal(deadline.isoformat())
    dispute_filter = _open_dispute_filter_sql()
    cursor_filter = _cursor_filter_sql(cursor)
    script = f"""
SELECT o.id::text
FROM public.orders o
INNER JOIN LATERAL (
  SELECT e.created_at
  FROM public.order_events e
  WHERE e.order_id = o.id
    AND e.to_status = 'delivered'
  ORDER BY e.created_at ASC
  LIMIT 1
) delivered ON true
WHERE o.status = 'delivered'
  AND delivered.created_at <= {deadline_sql}::timestamptz
  AND {dispute_filter}
  {cursor_filter}
ORDER BY o.id ASC
LIMIT {int(limit)};
"""
    result = run_sql_script(script)
    if not result.ok:
        return []
    return result.rows


def _list_auto_release_candidates(
    *,
    limit: int,
    cursor: str | None,
    now: datetime,
) -> list[str]:
    release_days = _read_config_int(
        "release_after_shipped_days",
        DEFAULT_RELEASE_AFTER_SHIPPED_DAYS,
    )
    deadline = now - timedelta(days=release_days)
    deadline_sql = sql_literal(deadline.isoformat())
    dispute_filter = _open_dispute_filter_sql()
    cursor_filter = _cursor_filter_sql(cursor)
    release_key_prefix = sql_literal("release-")
    script = f"""
SELECT o.id::text
FROM public.orders o
INNER JOIN LATERAL (
  SELECT e.created_at
  FROM public.order_events e
  WHERE e.order_id = o.id
    AND e.to_status = 'shipped'
  ORDER BY e.created_at ASC
  LIMIT 1
) shipped ON true
WHERE o.status = 'shipped'
  AND shipped.created_at <= {deadline_sql}::timestamptz
  AND {dispute_filter}
  AND NOT EXISTS (
    SELECT 1
    FROM public.ledger_transactions lt
    WHERE lt.idempotency_key = ({release_key_prefix} || o.id::text)
  )
  {cursor_filter}
ORDER BY o.id ASC
LIMIT {int(limit)};
"""
    result = run_sql_script(script)
    if not result.ok:
        return []
    return result.rows


def _process_auto_confirm(
    service_client: Any,
    order_ids: list[str],
) -> tuple[int, int, int]:
    confirmed = 0
    skipped = 0
    for order_id in order_ids:
        try:
            transition_order(
                order_id=order_id,
                event=OrderEvent.AUTO_CONFIRM,
                actor_role=ActorRole.SYSTEM,
                actor_id=SYSTEM_ACTOR_ID,
                note="Auto-confirmed after delivery window",
            )
        except OrderTransitionError:
            skipped += 1
            continue

        evaluate_and_release(service_client, order_id)
        confirmed += 1
    return confirmed, skipped, len(order_ids)


def _process_auto_release(
    service_client: Any,
    order_ids: list[str],
) -> tuple[int, int, int, int, int]:
    released = 0
    held = 0
    already_released = 0
    not_eligible = 0
    skipped = 0

    for order_id in order_ids:
        result: ReleaseResult = evaluate_and_release(service_client, order_id)
        if result.outcome == "released":
            released += 1
        elif result.outcome == "held":
            held += 1
            skipped += 1
        elif result.outcome == "already_released":
            already_released += 1
            skipped += 1
        else:
            not_eligible += 1
            skipped += 1

    return released, held, already_released, not_eligible, skipped


def _next_cursor(order_ids: list[str], limit: int) -> str | None:
    if len(order_ids) < limit:
        return None
    return order_ids[-1] if order_ids else None


@router.post(
    "/auto-confirm",
    response_model=AutoConfirmJobResponse,
    dependencies=[Depends(require_internal_order_jobs_token)],
)
async def auto_confirm_batch(
    body: BatchJobRequest | None = None,
) -> AutoConfirmJobResponse:
    from app.deps import get_supabase_client

    service = next(get_supabase_client())
    request = body or BatchJobRequest()
    now = datetime.now(UTC)
    order_ids = _list_auto_confirm_candidates(
        limit=request.limit,
        cursor=request.cursor,
        now=now,
    )
    confirmed, skipped, scanned = _process_auto_confirm(service, order_ids)
    return AutoConfirmJobResponse(
        scanned=scanned,
        processed=confirmed,
        skipped=skipped,
        confirmed=confirmed,
        next_cursor=_next_cursor(order_ids, request.limit),
    )


@router.post(
    "/auto-release",
    response_model=AutoReleaseJobResponse,
    dependencies=[Depends(require_internal_order_jobs_token)],
)
async def auto_release_batch(
    body: BatchJobRequest | None = None,
) -> AutoReleaseJobResponse:
    from app.deps import get_supabase_client

    service = next(get_supabase_client())
    request = body or BatchJobRequest()
    now = datetime.now(UTC)
    order_ids = _list_auto_release_candidates(
        limit=request.limit,
        cursor=request.cursor,
        now=now,
    )
    released, held, already_released, not_eligible, skipped = _process_auto_release(
        service,
        order_ids,
    )
    return AutoReleaseJobResponse(
        scanned=len(order_ids),
        processed=released,
        skipped=skipped,
        released=released,
        held=held,
        already_released=already_released,
        not_eligible=not_eligible,
        next_cursor=_next_cursor(order_ids, request.limit),
    )
