"""Founder analytics dashboards: read API and CSV export (admin app ``/analytics``).

Routes (all under the audited ``/admin`` router, permissions in ``app.core.auth``):

* ``GET /admin/analytics/users`` · ``/growth`` · ``/vendors`` · ``/services-events`` —
  ``analytics.read``. Counts only; vendor sales value is withheld unless the caller also
  holds ``finance.read`` or ``finance.operate`` (founder decision D3).
* ``GET /admin/analytics/performance`` — ``analytics.read``. What to boost and what to
  uproot: category/product/vendor/clip funnels (views -> carts -> paid orders),
  conversion and repeat rate; item sales and per-order contribution only with
  ``finance.read`` / ``finance.operate``.
* ``GET /admin/analytics/revenue`` — ``finance.read`` / ``finance.operate`` only.
* ``GET /admin/analytics/export?report=…`` — CSV of one report; the report's own
  permission is re-checked, and every export (and every refused export) writes an
  ``audit_log`` row.

Window: ``period=today|7d|30d|custom`` (``custom`` takes ``from``/``to``), Africa/Lusaka
reporting days. These reports read authoritative tables and are not behind the
analytics_v2 flags; only the session-based activity block (DAU/WAU/MAU) is, because it
reads the v2 event log.
"""

from __future__ import annotations

import csv
import io
import threading
import time
from collections.abc import Callable, Iterable
from datetime import date
from typing import Annotated, Any, Final, Literal

from anyio import to_thread
from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.core.auth import (
    DASHBOARD_FINANCE_PERMISSIONS,
    CurrentUser,
    get_current_user,
    load_admin_permissions,
    record_denied_admin_attempt,
)
from app.errors import AppError
from app.routers.admin_base import router as admin_router
from app.services.analytics import dashboards, performance
from app.services.analytics import flags as analytics_flags
from app.supabase_client import get_supabase_service_client
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

# Not named ``router``: app.main auto-mounts module-level ``router`` objects at the root,
# and these routes must exist only under the audited ``/admin`` router.
dashboards_router = APIRouter(prefix="/analytics", tags=["admin-analytics-dashboards"])

CACHE_TTL_SECONDS: Final = 60.0
ANALYTICS_PERMISSIONS: Final = frozenset({"analytics.read"})

Report = Literal["users", "growth", "revenue", "vendors", "services-events", "performance"]
REPORT_PERMISSIONS: Final[dict[str, frozenset[str]]] = {
    "users": ANALYTICS_PERMISSIONS,
    "growth": ANALYTICS_PERMISSIONS,
    "vendors": ANALYTICS_PERMISSIONS,
    "services-events": ANALYTICS_PERMISSIONS,
    "performance": ANALYTICS_PERMISSIONS,
    "revenue": DASHBOARD_FINANCE_PERMISSIONS,
}

PeriodQuery = Annotated[
    Literal["today", "7d", "30d", "custom"] | None,
    Query(description="today, 7d or 30d (ending today, Lusaka), or custom with from/to."),
]
FromQuery = Annotated[
    date | None, Query(alias="from", description="First Lusaka day (custom only).")
]
ToQuery = Annotated[date | None, Query(alias="to", description="Last Lusaka day (custom only).")]

_cache: dict[tuple[str, ...], tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()


def clear_dashboards_cache() -> None:
    """Test helper."""
    with _cache_lock:
        _cache.clear()


def _window(period: str | None, start: date | None, end: date | None) -> dashboards.Window:
    try:
        return dashboards.resolve_window(period, start, end)
    except dashboards.RangeError as exc:
        raise AppError("invalid_range", str(exc), 422) from exc


def _granted(user: CurrentUser) -> frozenset[str]:
    return load_admin_permissions(user, get_supabase_service_client())


async def _build(
    report: str,
    window: dashboards.Window,
    *,
    finance: bool,
    builder: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    key = (report, window.period, window.start.isoformat(), window.end.isoformat(), str(finance))
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
    if hit is not None and hit[0] > now:
        return hit[1]
    try:
        payload = await to_thread.run_sync(builder)
    except RuntimeError as exc:
        raise AppError(
            code="analytics_unavailable",
            message="Analytics data is temporarily unavailable",
            http_status=503,
        ) from exc
    with _cache_lock:
        _cache[key] = (now + CACHE_TTL_SECONDS, payload)
    return payload


async def _report(
    report: str, window: dashboards.Window, granted: frozenset[str]
) -> dict[str, Any]:
    finance = bool(DASHBOARD_FINANCE_PERMISSIONS & granted)
    if report == "users":
        activity_on = await analytics_flags.flag_enabled_async(analytics_flags.ROLLUPS_FLAG)
        return await _build(
            report,
            window,
            finance=activity_on,  # cache key only: the payload differs by flag state
            builder=lambda: dashboards.build_users(window, activity_enabled=activity_on),
        )
    if report == "growth":
        return await _build(
            report, window, finance=False, builder=lambda: dashboards.build_growth(window)
        )
    if report == "revenue":
        return await _build(
            report, window, finance=True, builder=lambda: dashboards.build_revenue(window)
        )
    if report == "vendors":
        return await _build(
            report,
            window,
            finance=finance,
            builder=lambda: dashboards.build_vendors(window, include_money=finance),
        )
    if report == "performance":
        return await _build(
            report,
            window,
            finance=finance,
            builder=lambda: performance.build_performance(window, include_money=finance),
        )
    return await _build(
        report, window, finance=False, builder=lambda: dashboards.build_services_events(window)
    )


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


@dashboards_router.get("/users")
async def get_users(
    user: CurrentUserDep, period: PeriodQuery = None, start: FromQuery = None, end: ToQuery = None
) -> dict[str, Any]:
    return await _report("users", _window(period, start, end), _granted(user))


@dashboards_router.get("/growth")
async def get_growth(
    user: CurrentUserDep, period: PeriodQuery = None, start: FromQuery = None, end: ToQuery = None
) -> dict[str, Any]:
    return await _report("growth", _window(period, start, end), _granted(user))


@dashboards_router.get("/revenue")
async def get_revenue(
    user: CurrentUserDep, period: PeriodQuery = None, start: FromQuery = None, end: ToQuery = None
) -> dict[str, Any]:
    return await _report("revenue", _window(period, start, end), _granted(user))


@dashboards_router.get("/vendors")
async def get_vendors(
    user: CurrentUserDep, period: PeriodQuery = None, start: FromQuery = None, end: ToQuery = None
) -> dict[str, Any]:
    return await _report("vendors", _window(period, start, end), _granted(user))


@dashboards_router.get("/services-events")
async def get_services_events(
    user: CurrentUserDep, period: PeriodQuery = None, start: FromQuery = None, end: ToQuery = None
) -> dict[str, Any]:
    return await _report("services-events", _window(period, start, end), _granted(user))


@dashboards_router.get("/performance")
async def get_performance(
    user: CurrentUserDep, period: PeriodQuery = None, start: FromQuery = None, end: ToQuery = None
) -> dict[str, Any]:
    return await _report("performance", _window(period, start, end), _granted(user))


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

CSV_HEADER: Final = ("report", "section", "day", "dimension", "metric", "value")
_FORMULA_PREFIXES: Final = ("=", "+", "-", "@", "\t", "\r")


def _cell(value: Any) -> str:
    """Render a CSV cell; text that a spreadsheet would run as a formula is quoted out."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    text = str(value)
    if text.startswith(_FORMULA_PREFIXES):
        return "'" + text
    return text


def _flatten(
    report: str, section: str, value: Any, *, day: str = "", dimension: str = "", prefix: str = ""
) -> Iterable[tuple[Any, ...]]:
    if isinstance(value, dict):
        for key, inner in value.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            yield from _flatten(report, section, inner, day=day, dimension=dimension, prefix=name)
    elif isinstance(value, list):
        for index, inner in enumerate(value):
            yield from _flatten(
                report, section, inner, day=day, dimension=dimension, prefix=f"{prefix}[{index}]"
            )
    else:
        yield (report, section, day, dimension, prefix, value)


def report_rows(report: str, payload: dict[str, Any]) -> list[tuple[Any, ...]]:
    """Long-format rows: one metric per row; per-day series keep their day column."""
    rows: list[tuple[Any, ...]] = []
    for section, value in payload.items():
        if section in ("range", "previous_range"):
            continue
        if section == "daily" and isinstance(value, list):
            for item in value:
                day = str(item.get("day", ""))
                for metric, metric_value in item.items():
                    if metric != "day":
                        rows.append((report, "daily", day, "", metric, metric_value))
            continue
        if section == "top" and isinstance(value, list):
            for item in value:
                dimension = f"{item.get('vendor_id', '')} {item.get('name', '')}".strip()
                for metric, metric_value in item.items():
                    if metric not in ("vendor_id", "name"):
                        rows.append((report, "top", "", dimension, metric, metric_value))
            continue
        if section in performance.GRAINS and isinstance(value, dict):
            for ranking, items in value.items():
                if not isinstance(items, list):
                    rows.append((report, section, "", "", ranking, items))
                    continue
                for item in items:
                    dimension = f"{item.get('id', '')} {item.get('name', '')}".strip()
                    for metric, metric_value in item.items():
                        if metric not in ("id", "name"):
                            rows.append(
                                (
                                    report,
                                    f"{section}.{ranking}",
                                    "",
                                    dimension,
                                    metric,
                                    metric_value,
                                )
                            )
            continue
        if section == "cohorts" and isinstance(value, list):
            for item in value:
                for metric, metric_value in item.items():
                    if metric != "cohort":
                        rows.extend(
                            _flatten(
                                report,
                                "cohorts",
                                metric_value,
                                dimension=item["cohort"],
                                prefix=metric,
                            )
                        )
            continue
        if section == "activity" and isinstance(value, dict) and "daily_visitors" in value:
            for item in value["daily_visitors"]:
                rows.append((report, "activity", item["day"], "", "visitors", item["visitors"]))
            value = {k: v for k, v in value.items() if k != "daily_visitors"}
        rows.extend(_flatten(report, section, value))
    return rows


def render_csv(window: dashboards.Window, rows: list[tuple[Any, ...]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            "# vergeo5 analytics export",
            f"period={window.period}",
            f"from={window.start}",
            f"to={window.end}",
            "tz=Africa/Lusaka",
            "",
        ]
    )
    writer.writerow(CSV_HEADER)
    for row in rows:
        writer.writerow([_cell(cell) for cell in row])
    return buffer.getvalue()


@dashboards_router.get("/export")
async def export_report(
    request: Request,
    user: CurrentUserDep,
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    report: Annotated[Report, Query(description="Which dashboard to export.")],
    period: PeriodQuery = None,
    start: FromQuery = None,
    end: ToQuery = None,
) -> Response:
    granted = _granted(user)
    if not (REPORT_PERMISSIONS[report] & granted):
        record_denied_admin_attempt(request, user)
        raise AppError(code="forbidden", message="Insufficient admin permissions", http_status=403)
    window = _window(period, start, end)
    payload = await _report(report, window, granted)
    rows = report_rows(report, payload)
    body = render_csv(window, rows)
    recorder.record(
        action="analytics.export",
        entity_type="analytics_report",
        entity_id=None,
        before=None,
        after={
            "report": report,
            "period": window.period,
            "from": window.start.isoformat(),
            "to": window.end.isoformat(),
            "rows": len(rows),
            "finance_visible": bool(DASHBOARD_FINANCE_PERMISSIONS & granted),
        },
    )
    filename = f"vergeo5-{report}-{window.start.isoformat()}-{window.end.isoformat()}.csv"
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


admin_router.include_router(dashboards_router)
