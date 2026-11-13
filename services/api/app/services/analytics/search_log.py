"""M06-P06: fire-and-forget search/ask query logging + insight aggregates.

Writes go through the service-role psql seam (same pattern as the funnel
recorder). Logging is best-effort: every failure is swallowed so an analytics
write can never break the search or ask request that triggered it.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.services.orders.audit import run_sql_script, sql_literal

logger = logging.getLogger(__name__)

# Zambia DPA-aligned: no query is tied to a user beyond this window.
PII_RETENTION_DAYS = 30

DEFAULT_INSIGHT_WINDOW_DAYS = 30
DEFAULT_TOP_TERMS_LIMIT = 20

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class TermCount:
    normalized_term: str
    sample_term: str
    count: int


@dataclass(frozen=True, slots=True)
class DailyAskCost:
    day: str
    usd_micros: int
    query_count: int


def normalize_term(term: str) -> str:
    """Lowercase + whitespace-collapse so variants group together."""
    return _WHITESPACE_RE.sub(" ", term.strip().lower())


def _sql_json(value: dict[str, Any]) -> str:
    payload = json.dumps(value, separators=(",", ":"), sort_keys=True)
    return "'" + payload.replace("'", "''") + "'::jsonb"


def _user_id_sql(user_id: str | None) -> str:
    if user_id is None:
        return "null"
    if not _UUID_RE.match(user_id):
        # Drop malformed ids rather than raise — logging must not fail the request.
        return "null"
    return f"{sql_literal(user_id)}::uuid"


def _clamp_window_days(days: int) -> int:
    if days < 1:
        return 1
    if days > 365:
        return 365
    return days


def _insert_query_log(
    *,
    kind: str,
    term: str,
    normalized: str,
    entity_counts: dict[str, Any],
    zero_result: bool,
    usd_micros: int,
    user_id: str | None,
) -> None:
    """Best-effort insert; never raises."""
    script = f"""
INSERT INTO public.search_query_log (
  kind, term, normalized_term, entity_counts, zero_result, usd_micros, user_id
) VALUES (
  {sql_literal(kind)},
  {sql_literal(term)},
  {sql_literal(normalized)},
  {_sql_json(entity_counts)},
  {'true' if zero_result else 'false'},
  {max(0, int(usd_micros))},
  {_user_id_sql(user_id)}
);
"""
    result = run_sql_script(script)
    if not result.ok:
        logger.debug("search_query_log insert failed (swallowed): %s", result.error)


def log_search_query(
    *,
    term: str,
    entity_counts: dict[str, Any] | None = None,
    zero_result: bool,
    user_id: str | None = None,
    normalized_term: str | None = None,
) -> None:
    """Fire-and-forget log of a search query. Swallows all errors."""
    try:
        normalized = normalized_term if normalized_term is not None else normalize_term(term)
        _insert_query_log(
            kind="search",
            term=term,
            normalized=normalized,
            entity_counts=entity_counts or {},
            zero_result=zero_result,
            usd_micros=0,
            user_id=user_id,
        )
    except Exception as exc:  # noqa: BLE001 — logging must never break the caller.
        logger.debug("log_search_query swallowed error: %s", exc)


def log_ask_query(
    *,
    term: str,
    usd_micros: int = 0,
    entity_counts: dict[str, Any] | None = None,
    zero_result: bool = False,
    user_id: str | None = None,
    normalized_term: str | None = None,
) -> None:
    """Fire-and-forget log of an Ask query + its model spend. Swallows all errors."""
    try:
        normalized = normalized_term if normalized_term is not None else normalize_term(term)
        _insert_query_log(
            kind="ask",
            term=term,
            normalized=normalized,
            entity_counts=entity_counts or {},
            zero_result=zero_result,
            usd_micros=usd_micros,
            user_id=user_id,
        )
    except Exception as exc:  # noqa: BLE001 — logging must never break the caller.
        logger.debug("log_ask_query swallowed error: %s", exc)


def trim_search_pii(now: datetime | None = None) -> int:
    """NULL user_id on rows older than the retention window. Returns rows trimmed."""
    cutoff = (now or datetime.now(UTC)) - timedelta(days=PII_RETENTION_DAYS)
    script = f"""
WITH trimmed AS (
  UPDATE public.search_query_log
  SET user_id = NULL
  WHERE user_id IS NOT NULL
    AND created_at < {sql_literal(cutoff.isoformat())}::timestamptz
  RETURNING 1
)
SELECT count(*)::text FROM trimmed;
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        raise RuntimeError(f"trim_search_pii failed: {result.error}")
    return int(result.rows[0])


def _window_predicate(days: int) -> str:
    return (
        "created_at >= timezone('utc', now()) - "
        f"(interval '1 day' * {_clamp_window_days(days)})"
    )


def top_terms(
    days: int = DEFAULT_INSIGHT_WINDOW_DAYS,
    limit: int = DEFAULT_TOP_TERMS_LIMIT,
) -> list[TermCount]:
    """Most frequent normalized terms (search + ask) within the window."""
    safe_limit = max(1, min(int(limit), 200))
    script = f"""
SELECT normalized_term, min(term) AS sample_term, count(*)::text
FROM public.search_query_log
WHERE {_window_predicate(days)}
GROUP BY normalized_term
ORDER BY count(*) DESC, normalized_term ASC
LIMIT {safe_limit};
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"top_terms failed: {result.error}")
    return [row for row in (_parse_term_count(line) for line in result.rows) if row is not None]


def zero_result_terms(
    days: int = DEFAULT_INSIGHT_WINDOW_DAYS,
    limit: int = DEFAULT_TOP_TERMS_LIMIT,
) -> list[TermCount]:
    """Most frequent zero-result terms within the window (merchandising gap mining)."""
    safe_limit = max(1, min(int(limit), 200))
    script = f"""
SELECT normalized_term, min(term) AS sample_term, count(*)::text
FROM public.search_query_log
WHERE zero_result AND {_window_predicate(days)}
GROUP BY normalized_term
ORDER BY count(*) DESC, normalized_term ASC
LIMIT {safe_limit};
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"zero_result_terms failed: {result.error}")
    return [row for row in (_parse_term_count(line) for line in result.rows) if row is not None]


def ask_cost_by_day(days: int = DEFAULT_INSIGHT_WINDOW_DAYS) -> list[DailyAskCost]:
    """Ask model spend (micro-dollars) grouped by UTC day, newest first."""
    script = f"""
SELECT
  to_char(date_trunc('day', created_at), 'YYYY-MM-DD') AS day,
  coalesce(sum(usd_micros), 0)::text AS usd_micros,
  count(*)::text AS query_count
FROM public.search_query_log
WHERE kind = 'ask' AND {_window_predicate(days)}
GROUP BY 1
ORDER BY 1 DESC;
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"ask_cost_by_day failed: {result.error}")
    return [row for row in (_parse_daily_cost(line) for line in result.rows) if row is not None]


def _parse_term_count(line: str) -> TermCount | None:
    parts = line.split("|")
    if len(parts) != 3 or not parts[2].isdigit():
        return None
    return TermCount(normalized_term=parts[0], sample_term=parts[1], count=int(parts[2]))


def _parse_daily_cost(line: str) -> DailyAskCost | None:
    parts = line.split("|")
    if len(parts) != 3 or not parts[1].lstrip("-").isdigit() or not parts[2].isdigit():
        return None
    return DailyAskCost(day=parts[0], usd_micros=int(parts[1]), query_count=int(parts[2]))
