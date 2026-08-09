"""Privacy-hardened popular search terms for customer recovery surfaces.

Never publish rare / PII-shaped / prohibited queries. Aggregates must clear a
minimum *distinct contributor* threshold (with a per-contributor cap) over a
minimum time window before surfacing.

Five repeated searches by one actor must not create a popular query. Anonymous
rows (null ``user_id``) are excluded from the contributor set so a single guest
cannot inflate popularity via raw row counts. No raw IP is persisted or read.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.schemas.base import StrictModel
from app.services.analytics.search_log import normalize_term
from app.services.moderation.prohibited import screen_listing
from app.services.orders.audit import run_sql_script

logger = logging.getLogger(__name__)

# Privacy floors — rare / single-actor queries must never leak via the public rail.
MIN_DISTINCT_CONTRIBUTORS = 5
# Cap how much any one authenticated actor can contribute toward a term's score.
PER_CONTRIBUTOR_CAP = 1
MIN_WINDOW_DAYS = 7
DEFAULT_WINDOW_DAYS = 30
MAX_WINDOW_DAYS = 90
DEFAULT_LIMIT = 8
MAX_LIMIT = 20

# Back-compat alias used by older tests / callers.
MIN_AGGREGATION_COUNT = MIN_DISTINCT_CONTRIBUTORS

# Over-fetch so post-filters (PII / prohibited) can still fill the requested limit.
_OVERFETCH_FACTOR = 4

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# Zambia E.164 / local mobile, plus spaced/dashed variants reduced via digits check.
_PHONE_CANDIDATE_RE = re.compile(r"(?<![A-Za-z0-9])\+?\d(?:[\s.\-]{0,3}\d){5,}")


class PopularSearchItem(StrictModel):
    term: str
    count: int


@dataclass(frozen=True, slots=True)
class _RawTermCount:
    normalized_term: str
    sample_term: str
    count: int


def _clamp_limit(limit: int) -> int:
    return max(1, min(int(limit), MAX_LIMIT))


def _clamp_window_days(days: int) -> int:
    """Enforce the privacy minimum window; clamp the upper bound."""
    if days < MIN_WINDOW_DAYS:
        return MIN_WINDOW_DAYS
    if days > MAX_WINDOW_DAYS:
        return MAX_WINDOW_DAYS
    return int(days)


def _digits_only(raw: str) -> str:
    return re.sub(r"\D", "", raw)


def _is_zambian_phone(digits: str) -> bool:
    if digits.startswith("260"):
        rest = digits[3:]
        return len(rest) == 9 and rest[0] in "79"
    if digits.startswith("0"):
        return len(digits) == 10 and digits[1] in "79"
    if len(digits) == 9 and digits[0] in "79":
        return True
    return False


def looks_like_pii(term: str) -> bool:
    """True when a search term embeds email or Zambian phone patterns."""
    haystack = term.strip()
    if not haystack:
        return True
    if _EMAIL_RE.search(haystack):
        return True
    for match in _PHONE_CANDIDATE_RE.finditer(haystack):
        if _is_zambian_phone(_digits_only(match.group())):
            return True
    return False


def is_prohibited_term(term: str) -> bool:
    """Reuse the listing prohibited keyword screen against the search term."""
    verdict = screen_listing(title=term, description=None, category=None)
    return not verdict.allowed


def is_publishable_popular_term(term: str, *, count: int) -> bool:
    """Single gate used by the public endpoint and privacy regression tests.

    ``count`` is the distinct-contributor score (already capped per actor in SQL).
    """
    normalized = normalize_term(term)
    if not normalized or len(normalized) < 2:
        return False
    if count < MIN_DISTINCT_CONTRIBUTORS:
        return False
    if looks_like_pii(normalized) or looks_like_pii(term):
        return False
    if is_prohibited_term(normalized):
        return False
    return True


def _parse_row(line: str) -> _RawTermCount | None:
    parts = line.split("|")
    if len(parts) < 3:
        return None
    normalized, sample, count_raw = parts[0], parts[1], parts[2]
    try:
        count = int(count_raw)
    except ValueError:
        return None
    if not normalized:
        return None
    return _RawTermCount(
        normalized_term=normalized,
        sample_term=sample or normalized,
        count=count,
    )


def _fetch_aggregated_terms(*, days: int, limit: int) -> list[_RawTermCount]:
    """SQL aggregate: distinct authenticated contributors, capped per actor.

    Anonymous rows (``user_id IS NULL``) are excluded — without a stable
    non-IP actor key they cannot safely contribute to a public popularity rail.
    """
    safe_days = _clamp_window_days(days)
    # Pull extra rows so PII/prohibited post-filters can still fill `limit`.
    fetch_limit = max(1, min(limit * _OVERFETCH_FACTOR, 80))
    script = f"""
WITH per_contributor AS (
  SELECT
    normalized_term,
    user_id,
    least(count(*)::int, {PER_CONTRIBUTOR_CAP}) AS capped_count,
    min(term) AS sample_term
  FROM public.search_query_log
  WHERE kind = 'search'
    AND user_id IS NOT NULL
    AND created_at >= timezone('utc', now()) - (interval '1 day' * {safe_days})
  GROUP BY normalized_term, user_id
),
agg AS (
  SELECT
    normalized_term,
    min(sample_term) AS sample_term,
    count(*)::int AS distinct_contributors,
    sum(capped_count)::int AS score
  FROM per_contributor
  GROUP BY normalized_term
  HAVING count(*) >= {MIN_DISTINCT_CONTRIBUTORS}
)
SELECT normalized_term, sample_term, distinct_contributors::text
FROM agg
ORDER BY score DESC, distinct_contributors DESC, normalized_term ASC
LIMIT {fetch_limit};
"""
    result = run_sql_script(script)
    if not result.ok:
        logger.warning("popular_searches aggregate failed: %s", result.error)
        return []
    return [row for row in (_parse_row(line) for line in result.rows) if row is not None]


def fetch_popular_searches(
    *,
    limit: int = DEFAULT_LIMIT,
    days: int = DEFAULT_WINDOW_DAYS,
) -> list[PopularSearchItem]:
    """Return privacy-safe popular terms; empty when confidence is insufficient."""
    safe_limit = _clamp_limit(limit)
    safe_days = _clamp_window_days(days)
    rows = _fetch_aggregated_terms(days=safe_days, limit=safe_limit)
    items: list[PopularSearchItem] = []
    seen: set[str] = set()
    for row in rows:
        display = (row.sample_term or row.normalized_term).strip()
        normalized = normalize_term(display) or row.normalized_term
        if normalized in seen:
            continue
        if not is_publishable_popular_term(display, count=row.count):
            continue
        seen.add(normalized)
        items.append(PopularSearchItem(term=display, count=row.count))
        if len(items) >= safe_limit:
            break
    return items
