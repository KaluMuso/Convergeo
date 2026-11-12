"""Convergeo Intelligence 1B-04: admin analytics read API (plan §1B).

Mounted under the audited ``/admin`` router and additionally restricted to
``admin``/``superadmin`` (moderators are excluded). Every route reads **aggregates only**:
the daily rollup tables (1B-01) and the authoritative commercial function (1B-03). No
route reads raw events, ids or raw search terms.

* Gated by ``analytics_v2_rollups``: with the flag OFF every data route answers 404
  ``analytics_disabled`` and ``/status`` reports ``enabled: false`` — nothing else changes.
* Privacy: a search term is returned only when it was searched in at least k DISTINCT
  anonymous sessions (k >= 5, ``platform_config.analytics_term_k_min``; OD-6/OD-8) in the
  window; below-k terms are folded into an "other" bucket inside SQL so they never leave
  the database. Session-less searches count as at most one session.
* Rates are integers in basis points and are ``null`` below the minimum sample
  (``platform_config.analytics_min_sample_n``, default 20). Money is integer ngwee.
* Reads run in a worker thread with a short statement timeout and are cached for 60 s
  per worker — admin traffic never recomputes rollups.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Final

from anyio import to_thread
from app.core.auth import require_role
from app.errors import AppError
from app.routers.admin_base import router as admin_router
from app.services.analytics import flags as analytics_flags
from app.services.analytics.metrics import (
    CommercialSummary,
    commercial_summary,
    previous_period,
)
from app.services.orders.audit import run_sql_script, sql_literal
from fastapi import APIRouter, Depends, Query

analytics_router = APIRouter(
    prefix="/analytics",
    tags=["admin-analytics"],
    dependencies=[Depends(require_role("admin", "superadmin"))],
)

K_FLOOR: Final = 5
DEFAULT_MIN_SAMPLE_N: Final = 20
DEFAULT_WINDOW_DAYS: Final = 7
MAX_WINDOW_DAYS: Final = 92
TOP_LIMIT: Final = 20
CACHE_TTL_SECONDS: Final = 60.0
STATEMENT_TIMEOUT: Final = "5s"

#: Distinct-session k measure for a term over a window (OD-6/OD-8). Session-less rows
#: (no client session id, or legacy rows whose ``sessions`` is NULL) count as at most ONE
#: session across the whole window, so one person repeating a term never reaches k.
#: Mirrored by ``public.analytics_search_daily_purge`` (retention, OD-10).
SEARCH_K_MEASURE_SQL: Final = (
    "greatest(coalesce(sum(sessions), 0), "
    "max(CASE WHEN sessions IS NULL OR unsessioned_searches > 0 THEN 1 ELSE 0 END))"
)

_cache: dict[tuple[str, str, str], tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()

FromQuery = Annotated[date | None, Query(alias="from", description="First UTC day (inclusive).")]
ToQuery = Annotated[date | None, Query(alias="to", description="Last UTC day (inclusive).")]


def clear_analytics_cache() -> None:
    """Test helper."""
    with _cache_lock:
        _cache.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _today() -> date:
    return datetime.now(UTC).date()


def _resolve_window(start: date | None, end: date | None) -> tuple[date, date]:
    today = _today()
    end = end or (today - timedelta(days=1))
    start = start or (end - timedelta(days=DEFAULT_WINDOW_DAYS - 1))
    if end > today:
        raise AppError("invalid_range", "to must not be in the future", 422)
    if start > end:
        raise AppError("invalid_range", "from must not be after to", 422)
    if (end - start).days + 1 > MAX_WINDOW_DAYS:
        raise AppError("invalid_range", f"range exceeds {MAX_WINDOW_DAYS} days", 422)
    return start, end


def _rows(sql: str) -> list[list[str]]:
    script = f"BEGIN;\nSET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}';\n{sql}\nCOMMIT;\n"
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"analytics read failed: {result.error}")
    return [row.split("|") for row in result.rows if row.strip()]


def _day(value: date) -> str:
    return f"{sql_literal(value.isoformat())}::date"


def _thresholds() -> tuple[int, int]:
    """(k, min_n) from platform_config; k never below the K_FLOOR of 5."""
    rows = _rows(
        "SELECT key || '|' || (value #>> '{}') FROM public.platform_config "
        "WHERE key IN ('analytics_term_k_min', 'analytics_min_sample_n');"
    )
    values: dict[str, int] = {}
    for key, *rest in rows:
        raw = rest[0] if rest else ""
        if raw.strip().isdigit():
            values[key] = int(raw.strip())
    k = max(K_FLOOR, values.get("analytics_term_k_min", K_FLOOR))
    min_n = max(1, values.get("analytics_min_sample_n", DEFAULT_MIN_SAMPLE_N))
    return k, min_n


def rate_bps(numerator: int, denominator: int, min_n: int) -> int | None:
    """Integer basis points (half-up), or ``None`` below the minimum sample."""
    if denominator <= 0 or denominator < min_n:
        return None
    return (20_000 * numerator + denominator) // (2 * denominator)


def _data_through() -> str | None:
    rows = _rows(
        "SELECT coalesce(max(day)::text, '') FROM public.analytics_rollup_runs WHERE status = 'ok';"
    )
    value = rows[0][0] if rows else ""
    return value or None


def _rollup_totals(start: date, end: date) -> dict[str, tuple[int, int]]:
    rows = _rows(
        "SELECT metric || '|' || sum(value) || '|' || sum(sample_n) "
        "FROM public.analytics_daily_rollup "
        f"WHERE day BETWEEN {_day(start)} AND {_day(end)} AND dim_key = '' "
        "GROUP BY metric;"
    )
    return {r[0]: (int(r[1]), int(r[2])) for r in rows if len(r) == 3}


def _rollup_dim(start: date, end: date, metric: str, limit: int = TOP_LIMIT) -> list[list[str]]:
    return _rows(
        "SELECT dim_value || '|' || sum(value) || '|' || sum(sample_n) "
        "FROM public.analytics_daily_rollup "
        f"WHERE day BETWEEN {_day(start)} AND {_day(end)} AND metric = {sql_literal(metric)} "
        "GROUP BY dim_value ORDER BY sum(value) DESC, dim_value ASC "
        f"LIMIT {int(limit)};"
    )


def _commercial_block(summary: CommercialSummary) -> dict[str, Any]:
    return {
        "checkouts_started": summary.checkouts_started,
        "orders_placed": summary.orders_placed,
        "orders_cancelled": summary.orders_cancelled,
        "orders_paid": summary.orders_paid,
        "paid_checkouts": summary.paid_checkouts,
        "gmv_paid_ngwee": summary.gmv_paid_ngwee,
        "aov_ngwee": summary.aov_ngwee,
        "payments_reconciled": summary.reconciled,
        "payment_mismatch_days": [d.isoformat() for d in summary.mismatch_days],
    }


def _behaviour_block(totals: dict[str, tuple[int, int]], min_n: int) -> dict[str, Any]:
    sessions = totals.get("sessions", (0, 0))[0]
    bounced = totals.get("bounced_sessions", (0, 0))[0]
    span_total = totals.get("active_span_seconds_total", (0, 0))[0]
    searches = totals.get("searches", (0, 0))[0]
    zero = totals.get("zero_result_searches", (0, 0))[0]
    return {
        "sessions": sessions,
        "visitor_days": totals.get("visitors", (0, 0))[0],
        "bounce_rate_bps": rate_bps(bounced, sessions, min_n),
        "avg_active_span_seconds": (span_total // sessions) if sessions >= min_n else None,
        "searches": searches,
        "zero_result_share_bps": rate_bps(zero, searches, min_n),
    }


# ---------------------------------------------------------------------------
# Builders (sync; run in a worker thread)
# ---------------------------------------------------------------------------


def build_overview(start: date, end: date) -> dict[str, Any]:
    _k, min_n = _thresholds()
    prev_start, prev_end = previous_period(start, end)
    current = commercial_summary(start, end)
    previous = commercial_summary(prev_start, prev_end)
    sessions_by_day = {
        r[0]: int(r[1])
        for r in _rows(
            "SELECT day::text || '|' || value FROM public.analytics_daily_rollup "
            f"WHERE day BETWEEN {_day(start)} AND {_day(end)} AND metric = 'sessions' "
            "AND dim_key = '';"
        )
        if len(r) == 2
    }
    return {
        "range": {"from": start.isoformat(), "to": end.isoformat()},
        "previous_range": {"from": prev_start.isoformat(), "to": prev_end.isoformat()},
        "data_through": _data_through(),
        "min_sample_n": min_n,
        "behaviour": _behaviour_block(_rollup_totals(start, end), min_n),
        "previous_behaviour": _behaviour_block(_rollup_totals(prev_start, prev_end), min_n),
        "commercial": _commercial_block(current),
        "previous_commercial": _commercial_block(previous),
        "daily": [
            {
                "day": d.day.isoformat(),
                "sessions": sessions_by_day.get(d.day.isoformat()),
                "orders_paid": d.orders_paid,
                "gmv_paid_ngwee": d.gmv_paid_ngwee,
            }
            for d in current.days
        ],
    }


def build_search_demand(start: date, end: date) -> dict[str, Any]:
    k, min_n = _thresholds()
    window = f"day BETWEEN {_day(start)} AND {_day(end)}"
    # k-threshold applied IN SQL: below-k terms never leave the database.
    k_measure = SEARCH_K_MEASURE_SQL
    top = _rows(
        "SELECT normalized_term || '|' || sum(searches) || '|' || sum(zero_results) "
        f"FROM public.analytics_search_daily WHERE {window} "
        f"GROUP BY normalized_term HAVING {k_measure} >= {k} "
        f"ORDER BY sum(searches) DESC, normalized_term ASC LIMIT {TOP_LIMIT};"
    )
    zero = _rows(
        "SELECT normalized_term || '|' || sum(searches) || '|' || sum(zero_results) "
        f"FROM public.analytics_search_daily WHERE {window} "
        f"GROUP BY normalized_term HAVING {k_measure} >= {k} AND sum(zero_results) >= {k} "
        f"ORDER BY sum(zero_results) DESC, normalized_term ASC LIMIT {TOP_LIMIT};"
    )
    other = _rows(
        "SELECT count(*) || '|' || coalesce(sum(s), 0) || '|' || coalesce(sum(z), 0) FROM ("
        "SELECT sum(searches) AS s, sum(zero_results) AS z "
        f"FROM public.analytics_search_daily WHERE {window} "
        f"GROUP BY normalized_term HAVING {k_measure} < {k}) below_k;"
    )
    totals = _rows(
        "SELECT coalesce(sum(searches), 0) || '|' || coalesce(sum(zero_results), 0) "
        f"FROM public.analytics_search_daily WHERE {window};"
    )
    searches, zero_results = (int(totals[0][0]), int(totals[0][1])) if totals else (0, 0)
    other_terms, other_searches, other_zero = (
        (int(other[0][0]), int(other[0][1]), int(other[0][2])) if other else (0, 0, 0)
    )

    def _term(row: list[str]) -> dict[str, Any]:
        # Parse from the right: a normalized term may itself contain "|".
        return {
            "normalized_term": "|".join(row[:-2]),
            "searches": int(row[-2]),
            "zero_results": int(row[-1]),
        }

    return {
        "range": {"from": start.isoformat(), "to": end.isoformat()},
        "data_through": _data_through(),
        "k": k,
        "min_sample_n": min_n,
        "totals": {
            "searches": searches,
            "zero_results": zero_results,
            "zero_result_share_bps": rate_bps(zero_results, searches, min_n),
        },
        "top_terms": [_term(r) for r in top if len(r) >= 3],
        "zero_result_terms": [_term(r) for r in zero if len(r) >= 3],
        "other": {
            "terms": other_terms,
            "searches": other_searches,
            "zero_results": other_zero,
        },
    }


def build_products_funnel(start: date, end: date) -> dict[str, Any]:
    _k, min_n = _thresholds()
    steps = {
        r[0]: int(r[1]) for r in _rollup_dim(start, end, "funnel_sessions", limit=10) if len(r) == 3
    }
    totals = _rollup_totals(start, end)
    commercial = commercial_summary(start, end)
    funnel = [
        ("sessions", steps.get("session", 0)),
        ("search_sessions", steps.get("search", 0)),
        ("product_view_sessions", steps.get("product_view", 0)),
        ("cart_adds", totals.get("funnel_cart_adds", (0, 0))[0]),
        ("checkouts_started", commercial.checkouts_started),
        ("orders_placed", commercial.orders_placed),
        ("orders_paid", commercial.orders_paid),
    ]
    top_products = _rows(
        "SELECT r.dim_value || '|' || coalesce(p.name, '') || '|' || sum(r.value) || '|' || "
        "sum(r.sample_n) FROM public.analytics_daily_rollup r "
        "LEFT JOIN public.products p ON p.id::text = r.dim_value "
        f"WHERE r.day BETWEEN {_day(start)} AND {_day(end)} AND r.metric = 'product_views' "
        "GROUP BY r.dim_value, p.name ORDER BY sum(r.value) DESC, r.dim_value ASC "
        f"LIMIT {TOP_LIMIT};"
    )
    base = funnel[0][1]
    return {
        "range": {"from": start.isoformat(), "to": end.isoformat()},
        "data_through": _data_through(),
        "min_sample_n": min_n,
        "funnel": [
            {"step": step, "value": value, "share_of_sessions_bps": rate_bps(value, base, min_n)}
            for step, value in funnel
        ],
        "top_products": [
            {
                "product_id": r[0],
                "name": "|".join(r[1:-2]) or None,
                "views": int(r[-2]),
                "sessions": int(r[-1]),
            }
            for r in top_products
            if len(r) >= 4
        ],
        "page_views": [
            {"page_key": r[0], "views": int(r[1])}
            for r in _rollup_dim(start, end, "page_views")
            if len(r) == 3
        ],
        "entry_pages": [
            {"page_key": r[0], "sessions": int(r[1])}
            for r in _rollup_dim(start, end, "session_entries")
            if len(r) == 3
        ],
    }


def build_insights(start: date, end: date) -> dict[str, Any]:
    """Placeholder list for 1C. Today: deterministic data-quality items only."""
    items: list[dict[str, Any]] = []
    commercial = commercial_summary(start, end)
    for day in commercial.mismatch_days:
        items.append({"kind": "payment_mismatch", "severity": "high", "day": day.isoformat()})
    failed = _rows(
        "SELECT r.day::text FROM public.analytics_rollup_runs r "
        f"WHERE r.day BETWEEN {_day(start)} AND {_day(end)} AND r.status = 'error' "
        "AND NOT EXISTS (SELECT 1 FROM public.analytics_rollup_runs ok WHERE ok.day = r.day "
        "AND ok.status = 'ok' AND ok.started_at > r.started_at) "
        "GROUP BY r.day ORDER BY r.day;"
    )
    for row in failed:
        items.append({"kind": "rollup_failed", "severity": "medium", "day": row[0]})
    data_through = _data_through()
    if data_through is None or date.fromisoformat(data_through) < _today() - timedelta(days=1):
        items.append({"kind": "rollup_stale", "severity": "medium", "day": data_through})
    return {
        "range": {"from": start.isoformat(), "to": end.isoformat()},
        "data_through": data_through,
        "items": items,
        "generated": "deterministic",
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


async def _require_enabled() -> None:
    if not await analytics_flags.flag_enabled_async(analytics_flags.ROLLUPS_FLAG):
        raise AppError(
            code="analytics_disabled",
            message="Analytics is not enabled",
            http_status=404,
            details={"message_key": "admin.analytics.disabled"},
        )


async def _cached(
    name: str,
    start: date | None,
    end: date | None,
    builder: Callable[[date, date], dict[str, Any]],
) -> dict[str, Any]:
    await _require_enabled()
    window_start, window_end = _resolve_window(start, end)
    key = (name, window_start.isoformat(), window_end.isoformat())
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
    if hit is not None and hit[0] > now:
        return hit[1]
    try:
        payload = await to_thread.run_sync(lambda: builder(window_start, window_end))
    except RuntimeError as exc:
        raise AppError(
            code="analytics_unavailable",
            message="Analytics data is temporarily unavailable",
            http_status=503,
        ) from exc
    with _cache_lock:
        _cache[key] = (now + CACHE_TTL_SECONDS, payload)
    return payload


@analytics_router.get("/status")
async def get_analytics_status() -> dict[str, Any]:
    """Whether the analytics screens are enabled (drives the admin nav). No data."""
    enabled = await analytics_flags.flag_enabled_async(analytics_flags.ROLLUPS_FLAG)
    if not enabled:
        return {"enabled": False, "data_through": None}
    try:
        data_through = await to_thread.run_sync(_data_through)
    except RuntimeError:
        data_through = None
    return {"enabled": True, "data_through": data_through}


@analytics_router.get("/overview")
async def get_analytics_overview(start: FromQuery = None, end: ToQuery = None) -> dict[str, Any]:
    return await _cached("overview", start, end, build_overview)


@analytics_router.get("/search-demand")
async def get_analytics_search_demand(
    start: FromQuery = None, end: ToQuery = None
) -> dict[str, Any]:
    return await _cached("search-demand", start, end, build_search_demand)


@analytics_router.get("/products-funnel")
async def get_analytics_products_funnel(
    start: FromQuery = None, end: ToQuery = None
) -> dict[str, Any]:
    return await _cached("products-funnel", start, end, build_products_funnel)


@analytics_router.get("/insights")
async def get_analytics_insights(start: FromQuery = None, end: ToQuery = None) -> dict[str, Any]:
    return await _cached("insights", start, end, build_insights)


admin_router.include_router(analytics_router)
