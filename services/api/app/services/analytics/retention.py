"""Task 3: unified analytics PII retention sweep.

Generalises the ``search_query_log`` 30-day ``user_id`` trim
(``search_log.trim_search_pii``) to *every* analytics table that links an event
to a person. Past the retention window it NULLs the person-link columns while
keeping the anonymized aggregates (event counts, terms, funnel stages, money):

- ``search_query_log.user_id``           → NULL   (reuses ``trim_search_pii``)
- ``funnel_events.customer_id``          → NULL   + ``snapshot`` loses ``customer_id``
- ``analytics_events.user_id``/``session_id`` → NULL

Idempotent (a second run touches nothing) and service-role only. Run on a daily
schedule via ``POST /internal/analytics/retention-tick`` (n8n). DPA-aligned: the
30-day window matches the documented search-log window; nothing tax-bound lives in
these tables (orders/payments/invoices keep their own 7-year retention elsewhere).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.services.analytics.reporting_day import reporting_today
from app.services.analytics.search_log import PII_RETENTION_DAYS, trim_search_pii
from app.services.orders.audit import run_sql_script, sql_literal


@dataclass(frozen=True, slots=True)
class RetentionSweepResult:
    """Rows whose person-link was cleared, per table."""

    search_query_log: int
    funnel_events: int
    analytics_events: int


def _cutoff_iso_sql(now: datetime | None) -> str:
    cutoff = (now or datetime.now(UTC)) - timedelta(days=PII_RETENTION_DAYS)
    return f"{sql_literal(cutoff.isoformat())}::timestamptz"


def _count_trim(update_sql: str) -> int:
    """Run a person-link-clearing UPDATE, returning the number of rows changed."""
    script = f"""
WITH trimmed AS (
{update_sql}
  RETURNING 1
)
SELECT count(*)::text FROM trimmed;
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        raise RuntimeError(f"analytics retention sweep failed: {result.error}")
    return int(result.rows[0])


def _trim_funnel_events(cutoff_sql: str) -> int:
    return _count_trim(
        f"""
  UPDATE public.funnel_events
  SET customer_id = NULL,
      snapshot = snapshot - 'customer_id'
  WHERE (customer_id IS NOT NULL OR snapshot ? 'customer_id')
    AND created_at < {cutoff_sql}
"""
    )


def _trim_analytics_events(cutoff_sql: str) -> int:
    return _count_trim(
        f"""
  UPDATE public.analytics_events
  SET user_id = NULL,
      session_id = NULL
  WHERE (user_id IS NOT NULL OR session_id IS NOT NULL)
    AND created_at < {cutoff_sql}
"""
    )


def sweep_analytics_retention(now: datetime | None = None) -> RetentionSweepResult:
    """Clear person-links on analytics rows older than the retention window.

    Idempotent and service-role. Returns the per-table count of rows trimmed.
    """
    cutoff_sql = _cutoff_iso_sql(now)
    return RetentionSweepResult(
        search_query_log=trim_search_pii(now),
        funnel_events=_trim_funnel_events(cutoff_sql),
        analytics_events=_trim_analytics_events(cutoff_sql),
    )


# ---------------------------------------------------------------------------
# analytics_v2 retention (Convergeo Intelligence 1A-07, plan §R-E/§R-G).
# Gated by feature flag ``analytics_v2_rollups`` — OFF = nothing below runs and the
# v1 sweep above is unchanged. Every step is batched (bounded statement size, short
# locks) and idempotent; a second run touches nothing.
# ---------------------------------------------------------------------------

#: Raw v2 events are hard-deleted (not NULLed) after this many days.
EVENT_LOG_RETENTION_DAYS = 30
#: listing_view_dedup rows only matter on their own UTC day; keep yesterday as slack.
LISTING_DEDUP_RETENTION_DAYS = 2
#: After the DPA window the raw search term collapses to its normalized form.
SEARCH_TERM_SCRUB_DAYS = PII_RETENTION_DAYS
V2_BATCH_SIZE = 5_000
V2_MAX_BATCHES = 40


@dataclass(frozen=True, slots=True)
class V2RetentionResult:
    event_log_deleted: int
    listing_dedup_purged: int
    search_terms_scrubbed: int
    complete: bool  # False when a step hit V2_MAX_BATCHES (the next tick continues)
    #: analytics_search_daily rows removed by the OD-10 rule (below-k > 30 days,
    #: met-k > 13 whole months) — ``public.analytics_search_daily_purge``.
    search_daily_purged: int = 0


def _batched(statement: str, *, batch_size: int, max_batches: int) -> tuple[int, bool]:
    """Run a ``… LIMIT {batch}`` statement returning its row count until it drains."""
    total = 0
    for _ in range(max_batches):
        script = f"""
BEGIN;
SET LOCAL statement_timeout = '15s';
SET LOCAL lock_timeout = '2s';
WITH done AS (
{statement.format(batch=batch_size)}
  RETURNING 1
)
SELECT count(*)::text FROM done;
COMMIT;
"""
        result = run_sql_script(script)
        if not result.ok or not result.rows:
            raise RuntimeError(f"analytics v2 retention step failed: {result.error}")
        changed = int(result.rows[-1])
        total += changed
        if changed < batch_size:
            return total, True
    return total, False


def purge_search_daily(
    now: datetime | None = None,
    *,
    batch_size: int = V2_BATCH_SIZE,
    max_batches: int = V2_MAX_BATCHES,
) -> tuple[int, bool]:
    """OD-10 retention for ``analytics_search_daily`` (Lusaka reporting days)."""
    today = reporting_today(now)
    total = 0
    for _ in range(max_batches):
        result = run_sql_script(
            "BEGIN;\n"
            "SET LOCAL statement_timeout = '15s';\n"
            "SET LOCAL lock_timeout = '2s';\n"
            "SELECT public.analytics_search_daily_purge("
            f"{sql_literal(today.isoformat())}::date, {int(batch_size)})::text;\n"
            "COMMIT;\n"
        )
        if not result.ok or not result.rows:
            raise RuntimeError(f"analytics search_daily purge failed: {result.error}")
        changed = int(result.rows[-1])
        total += changed
        if changed < batch_size:
            return total, True
    return total, False


def sweep_v2_retention(
    now: datetime | None = None,
    *,
    batch_size: int = V2_BATCH_SIZE,
    max_batches: int = V2_MAX_BATCHES,
) -> V2RetentionResult:
    """Delete expired v2 raw events, purge stale listing-view dedup keys, scrub old raw
    search terms and apply the OD-10 ``analytics_search_daily`` retention. Caller is
    responsible for the ``analytics_v2_rollups`` gate."""
    current = now or datetime.now(UTC)
    log_cutoff = current - timedelta(days=EVENT_LOG_RETENTION_DAYS)
    term_cutoff = current - timedelta(days=SEARCH_TERM_SCRUB_DAYS)
    dedup_cutoff = (current - timedelta(days=LISTING_DEDUP_RETENTION_DAYS)).date()

    deleted, ok_log = _batched(
        f"""
  DELETE FROM public.analytics_event_log l
  USING (
    SELECT event_id FROM public.analytics_event_log
    WHERE received_at < {sql_literal(log_cutoff.isoformat())}::timestamptz
    LIMIT {{batch}}
  ) doomed
  WHERE l.event_id = doomed.event_id""",
        batch_size=batch_size,
        max_batches=max_batches,
    )
    purged, ok_dedup = _batched(
        f"""
  DELETE FROM public.listing_view_dedup
  WHERE ctid IN (
    SELECT ctid FROM public.listing_view_dedup
    WHERE day < {sql_literal(dedup_cutoff.isoformat())}::date
    LIMIT {{batch}}
  )""",
        batch_size=batch_size,
        max_batches=max_batches,
    )
    scrubbed, ok_terms = _batched(
        f"""
  UPDATE public.search_query_log q
  SET term = q.normalized_term
  FROM (
    SELECT id FROM public.search_query_log
    WHERE created_at < {sql_literal(term_cutoff.isoformat())}::timestamptz
      AND term IS DISTINCT FROM normalized_term
    LIMIT {{batch}}
  ) stale
  WHERE q.id = stale.id""",
        batch_size=batch_size,
        max_batches=max_batches,
    )
    search_daily, ok_daily = purge_search_daily(
        current, batch_size=batch_size, max_batches=max_batches
    )
    return V2RetentionResult(
        event_log_deleted=deleted,
        listing_dedup_purged=purged,
        search_terms_scrubbed=scrubbed,
        complete=ok_log and ok_dedup and ok_terms and ok_daily,
        search_daily_purged=search_daily,
    )


#: Tables whose size the storage endpoint reports (plan §F.3 DB-impact monitoring).
ANALYTICS_TABLES: tuple[str, ...] = (
    "analytics_event_log",
    "analytics_events",
    "funnel_events",
    "search_query_log",
    "listing_view_dedup",
    "listing_analytics",
    "rate_counters",
)


def analytics_storage_report() -> dict[str, object]:
    """Total size (heap + indexes + TOAST) and row estimate per analytics table."""
    names = ", ".join(sql_literal(name) for name in ANALYTICS_TABLES)
    result = run_sql_script(
        f"""
SELECT c.relname,
       pg_total_relation_size(c.oid)::text,
       greatest(c.reltuples, 0)::bigint::text
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND c.relname IN ({names})
ORDER BY c.relname;
SELECT 'database|' || pg_database_size(current_database())::text || '|0';
"""
    )
    if not result.ok:
        raise RuntimeError(f"analytics storage report failed: {result.error}")
    tables: dict[str, dict[str, int]] = {}
    database_bytes = 0
    for line in result.rows:
        parts = line.split("|")
        if len(parts) != 3 or not parts[1].isdigit():
            continue
        if parts[0] == "database":
            database_bytes = int(parts[1])
            continue
        tables[parts[0]] = {
            "total_bytes": int(parts[1]),
            "row_estimate": int(parts[2]) if parts[2].isdigit() else 0,
        }
    return {
        "database_bytes": database_bytes,
        "analytics_total_bytes": sum(t["total_bytes"] for t in tables.values()),
        "tables": tables,
    }
