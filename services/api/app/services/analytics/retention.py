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
