"""Convergeo Intelligence 1B-01: daily analytics rollup tick.

``POST /internal/analytics/rollup-tick`` (n8n, daily 02:15 UTC) calls :func:`run_rollup_tick`
when the ``analytics_v2_rollups`` flag is ON. For every UTC day that has no successful run
in the last :data:`CATCH_UP_DAYS` days — plus yesterday, which is always recomputed so
late beacons are folded in — it runs ``public.analytics_rollup_day(day)``.

Guarantees:

* **Idempotent.** The SQL function deletes and re-inserts the day under a per-day advisory
  lock, so running a day twice yields identical totals.
* **Bounded.** Each day runs in its own transaction with ``SET LOCAL statement_timeout``
  (60 s) and ``lock_timeout``; one slow day cannot hold a connection indefinitely.
* **Off the request path.** Only the internal tick (a worker thread) runs it; admin reads
  never compute rollups. A process-local single-flight lock stops overlapping ticks.
* **Recorded.** Successful runs are logged by the SQL function in the same transaction;
  failures are logged here as ``status='error'`` rows (truncated message, no data).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Final

from app.services.orders.audit import run_sql_script, sql_literal

logger = logging.getLogger(__name__)

CATCH_UP_DAYS: Final = 7
STATEMENT_TIMEOUT: Final = "60s"
LOCK_TIMEOUT: Final = "5s"
SESSION_IDLE_MINUTES: Final = 30

_tick_lock = threading.Lock()


@dataclass(slots=True)
class RollupDayResult:
    day: date
    ok: bool
    rows: int = 0
    error: str | None = None


@dataclass(slots=True)
class RollupTickResult:
    busy: bool = False
    days: list[RollupDayResult] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        if self.busy:
            return {"skipped": "busy"}
        return {
            "days": [
                {
                    "day": r.day.isoformat(),
                    "ok": r.ok,
                    "rows": r.rows,
                    **({"error": r.error} if r.error else {}),
                }
                for r in self.days
            ],
            "ok": all(r.ok for r in self.days),
        }


def _utc_today(now: datetime | None) -> date:
    return (now or datetime.now(UTC)).astimezone(UTC).date()


def _successful_days(since: date) -> set[date]:
    result = run_sql_script(
        "SELECT DISTINCT day::text FROM public.analytics_rollup_runs "
        f"WHERE status = 'ok' AND day >= {sql_literal(since.isoformat())}::date;"
    )
    if not result.ok:
        raise RuntimeError(f"analytics rollup run lookup failed: {result.error}")
    return {date.fromisoformat(row.strip()) for row in result.rows if row.strip()}


def days_to_roll(now: datetime | None = None) -> list[date]:
    """Missing days in the catch-up window, plus yesterday (always), oldest first."""
    today = _utc_today(now)
    yesterday = today - timedelta(days=1)
    window = [today - timedelta(days=offset) for offset in range(CATCH_UP_DAYS, 0, -1)]
    done = _successful_days(window[0])
    return [day for day in window if day not in done or day == yesterday]


def rollup_day(day: date) -> RollupDayResult:
    """Recompute one day. Never raises; a failure is returned and recorded."""
    script = (
        "BEGIN;\n"
        f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}';\n"
        f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}';\n"
        "SET LOCAL client_min_messages = warning;\n"
        f"SELECT public.analytics_rollup_day({sql_literal(day.isoformat())}::date, "
        f"{SESSION_IDLE_MINUTES})::text;\n"
        "COMMIT;\n"
    )
    result = run_sql_script(script)
    if result.ok and result.rows:
        return RollupDayResult(day=day, ok=True, rows=int(result.rows[-1].strip() or 0))
    error = (result.error or "no result")[:500]
    logger.warning("analytics rollup failed for %s: %s", day.isoformat(), error)
    _record_error(day, error)
    return RollupDayResult(day=day, ok=False, error=error)


def _record_error(day: date, error: str) -> None:
    recorded = run_sql_script(
        "INSERT INTO public.analytics_rollup_runs (day, finished_at, status, rows, error) "
        f"VALUES ({sql_literal(day.isoformat())}::date, clock_timestamp(), 'error', 0, "
        f"{sql_literal(error)});"
    )
    if not recorded.ok:
        logger.warning("analytics rollup error row not recorded: %s", recorded.error)


def run_rollup_tick(
    *,
    now: datetime | None = None,
    day: date | None = None,
) -> RollupTickResult:
    """Run the catch-up tick (or one explicit ``day``). Single-flight per process."""
    if not _tick_lock.acquire(blocking=False):
        return RollupTickResult(busy=True)
    try:
        if day is not None:
            if day > _utc_today(now):
                raise ValueError("cannot roll up a future day")
            targets = [day]
        else:
            targets = days_to_roll(now)
        return RollupTickResult(days=[rollup_day(target) for target in targets])
    finally:
        _tick_lock.release()
