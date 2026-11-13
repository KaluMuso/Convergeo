from __future__ import annotations

import os
from datetime import date
from typing import Annotated, Any

from anyio import to_thread
from app.core.internal_token import InternalTokenMisconfigured, resolve_internal_token
from app.errors import AppError
from app.services.analytics import flags as analytics_flags
from app.services.analytics.retention import (
    RetentionSweepResult,
    analytics_storage_report,
    sweep_analytics_retention,
    sweep_v2_retention,
)
from app.services.analytics.rollup import run_rollup_tick
from app.services.analytics.writer import get_writer
from fastapi import APIRouter, Depends, Query, Request

router = APIRouter(prefix="/internal/analytics", tags=["internal-analytics"])

_INTERNAL_TOKEN_ENV = "INTERNAL_ANALYTICS_TOKEN"
_DEFAULT_INTERNAL_TOKEN = "dev-internal-analytics"


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


async def require_internal_analytics_token(request: Request) -> None:
    """Guard the retention tick — machine-to-machine, shared internal token only."""
    expected = _expected_internal_token()
    provided = request.headers.get("X-Internal-Token")
    if not provided or provided != expected:
        raise AppError(
            code="unauthorized",
            message="Invalid or missing internal analytics token",
            http_status=401,
        )


@router.post(
    "/retention-tick",
    dependencies=[Depends(require_internal_analytics_token)],
)
async def analytics_retention_tick() -> dict[str, int]:
    """Clear person-links on analytics rows past the retention window (daily n8n tick)."""
    result: RetentionSweepResult = sweep_analytics_retention()
    return {
        "search_query_log": result.search_query_log,
        "funnel_events": result.funnel_events,
        "analytics_events": result.analytics_events,
    }


@router.get(
    "/ingest-stats",
    dependencies=[Depends(require_internal_analytics_token)],
)
async def analytics_ingest_stats() -> dict[str, Any]:
    """analytics_v2 ingest health for THIS worker (plan §F.3). Read-only, no DB I/O.

    The API runs several workers behind one port; a poller samples repeatedly and keys
    the result on ``pid``. Counters reset when a worker restarts.
    """
    # Imported lazily: the collect router owns the counters and the limiter.
    from app.routers.analytics_collect import ingest_counters, v2_limiter_keys

    return {
        "pid": os.getpid(),
        "flags": analytics_flags.snapshot(),
        "ingest": ingest_counters(),
        "limiter_tracked_keys": v2_limiter_keys(),
        "writer": get_writer().stats(),
    }


@router.post(
    "/v2-retention-tick",
    dependencies=[Depends(require_internal_analytics_token)],
)
async def analytics_v2_retention_tick() -> dict[str, Any]:
    """analytics_v2 retention (1A-07): no-op unless ``analytics_v2_rollups`` is ON.

    Deletes raw v2 events past 30 days, purges stale listing-view dedup keys (2 days)
    and collapses raw search terms past 30 days to their normalized form. Batched and
    idempotent; ``complete=false`` means the next tick continues. Also applies the
    OD-10 ``analytics_search_daily`` retention (below-k terms 30 days, met-k 13 months).
    """
    if not await analytics_flags.flag_enabled_async(analytics_flags.ROLLUPS_FLAG):
        return {"skipped": "flag_off"}
    result = await to_thread.run_sync(sweep_v2_retention)
    return {
        "event_log_deleted": result.event_log_deleted,
        "listing_dedup_purged": result.listing_dedup_purged,
        "search_terms_scrubbed": result.search_terms_scrubbed,
        "search_daily_purged": result.search_daily_purged,
        "complete": result.complete,
    }


@router.get(
    "/storage",
    dependencies=[Depends(require_internal_analytics_token)],
)
async def analytics_storage() -> dict[str, Any]:
    """DB-impact monitoring (plan §F.3): bytes and row estimates per analytics table."""
    try:
        return await to_thread.run_sync(analytics_storage_report)
    except RuntimeError as exc:
        raise AppError(
            code="analytics_storage_unavailable",
            message="Analytics storage report failed",
            http_status=503,
        ) from exc


@router.post(
    "/rollup-tick",
    dependencies=[Depends(require_internal_analytics_token)],
)
async def analytics_rollup_tick(
    day: Annotated[
        date | None, Query(description="Recompute one Lusaka reporting day (YYYY-MM-DD).")
    ] = None,
) -> dict[str, Any]:
    """Daily rollups (1B-01): no-op unless ``analytics_v2_rollups`` is ON.

    Without ``day``: recomputes every day of the last 7 with no successful run, plus
    yesterday. Idempotent (delete + insert per day); runs in a worker thread with a
    60 s statement timeout per day — never on a customer request path.
    """
    if not await analytics_flags.flag_enabled_async(analytics_flags.ROLLUPS_FLAG):
        return {"skipped": "flag_off"}
    try:
        result = await to_thread.run_sync(lambda: run_rollup_tick(day=day))
    except ValueError as exc:
        raise AppError(
            code="invalid_rollup_day",
            message=str(exc),
            http_status=422,
        ) from exc
    except RuntimeError as exc:
        raise AppError(
            code="analytics_rollup_unavailable",
            message="Analytics rollup tick failed",
            http_status=503,
        ) from exc
    return result.as_dict()
