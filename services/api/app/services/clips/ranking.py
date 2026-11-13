"""M17-P03 — deterministic feed ranking (spec §3, "no ML").

The score is a formula, not a model:

    score = freshness_decay(published_at) x (1 + log(1+likes) + 2*log(1+orders))

Three properties follow from choosing a formula over a model, and all three are
what a marketplace this size actually needs:

* **Deterministic.** Same inputs, same order, every time — so the feed is
  cacheable at the edge and two vendors comparing notes see the same thing.
* **Explainable.** :func:`explain` returns the per-component breakdown, so
  "why is my clip below theirs?" has an answer that is not "the model decided".
* **No personalization**, therefore no per-user cache key and no cold-start
  problem on a feed that will launch with ~50 clips.

``orders_attributed`` is weighted double the like term deliberately: a clip that
sells is worth more to the marketplace than a clip that is merely popular, and
weighting it visibly is how that priority stays a decision rather than a drift.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

#: A clip loses about half its freshness weight every three days. Short enough
#: that the feed keeps moving on a small catalogue, long enough that a good clip
#: posted on a quiet day is not buried by morning.
FRESHNESS_HALF_LIFE_HOURS: Final = 72.0

#: Spec §3: at most 2 clips per vendor per 20-item page. Without this one prolific
#: vendor owns the feed on a small catalogue, which is exactly the failure mode a
#: cold-start marketplace cannot afford.
MAX_PER_VENDOR_PER_PAGE: Final = 2

PAGE_SIZE: Final = 20

#: A small nudge, not a re-rank: enough to break up a run of one category without
#: overriding genuine engagement.
CATEGORY_SPREAD_PENALTY: Final = 0.85


@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    """Every term that produced a score, for the explainability path."""

    clip_id: str
    freshness: float
    like_term: float
    order_term: float
    engagement: float
    score: float
    age_hours: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "clip_id": self.clip_id,
            "freshness": round(self.freshness, 6),
            "like_term": round(self.like_term, 6),
            "order_term": round(self.order_term, 6),
            "engagement": round(self.engagement, 6),
            "score": round(self.score, 6),
            "age_hours": round(self.age_hours, 3),
        }


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def freshness_decay(published_at: Any, *, now: datetime | None = None) -> float:
    """Exponential half-life decay in [0, 1]. An unpublished clip scores 0."""
    reference = now or datetime.now(UTC)
    stamp = _parse_timestamp(published_at)
    if stamp is None:
        return 0.0
    age_hours = max(0.0, (reference - stamp).total_seconds() / 3600.0)
    return float(2.0 ** (-age_hours / FRESHNESS_HALF_LIFE_HOURS))


def explain(clip: dict[str, Any], *, now: datetime | None = None) -> ScoreBreakdown:
    """Score one clip and show the working."""
    reference = now or datetime.now(UTC)
    stamp = _parse_timestamp(clip.get("published_at"))
    age_hours = (
        max(0.0, (reference - stamp).total_seconds() / 3600.0) if stamp else float("inf")
    )

    likes = max(0, int(clip.get("like_count") or 0))
    orders = max(0, int(clip.get("orders_attributed") or 0))

    freshness = freshness_decay(clip.get("published_at"), now=reference)
    like_term = math.log1p(likes)
    order_term = 2.0 * math.log1p(orders)
    engagement = 1.0 + like_term + order_term

    return ScoreBreakdown(
        clip_id=str(clip.get("id") or ""),
        freshness=freshness,
        like_term=like_term,
        order_term=order_term,
        engagement=engagement,
        score=freshness * engagement,
        age_hours=age_hours if age_hours != float("inf") else -1.0,
    )


def score(clip: dict[str, Any], *, now: datetime | None = None) -> float:
    return explain(clip, now=now).score


def rank(
    clips: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    page_size: int = PAGE_SIZE,
    max_per_vendor: int = MAX_PER_VENDOR_PER_PAGE,
) -> list[dict[str, Any]]:
    """Order clips by score, then apply the diversity cap and category nudge.

    The cap is applied **after** scoring rather than as a SQL window, so a
    vendor's third clip is *deferred* to a later page rather than dropped — it
    still ranks, it just does not crowd this page.

    Ties break on clip id so the order is total and therefore stable: two clips
    with identical scores must not swap places between two requests, or the
    cursor would skip or repeat an item.
    """
    reference = now or datetime.now(UTC)

    scored = sorted(
        ((explain(clip, now=reference), clip) for clip in clips),
        key=lambda pair: (-pair[0].score, pair[0].clip_id),
    )
    scores = {breakdown.clip_id: breakdown.score for breakdown, _clip in scored}

    page: list[dict[str, Any]] = []
    taken: set[str] = set()
    per_vendor: dict[str, int] = {}
    last_category: str | None = None

    while len(page) < page_size:
        chosen = _next_eligible(scored, taken, per_vendor, max_per_vendor)
        if chosen is None:
            break

        category = _category_of(chosen)
        if category is not None and category == last_category:
            # Nudge, not a re-rank: take the next eligible clip from a different
            # category, but only if it is genuinely close in score.
            alternative = _next_eligible(
                scored, taken, per_vendor, max_per_vendor, avoid_category=category
            )
            if alternative is not None and scores.get(
                str(alternative.get("id") or ""), 0.0
            ) >= scores.get(str(chosen.get("id") or ""), 0.0) * CATEGORY_SPREAD_PENALTY:
                chosen = alternative
                category = _category_of(chosen)

        page.append(chosen)
        taken.add(str(chosen.get("id") or ""))
        vendor_id = str(chosen.get("vendor_id") or "")
        per_vendor[vendor_id] = per_vendor.get(vendor_id, 0) + 1
        last_category = category

    # Everything not placed on this page follows, still in score order. Nothing is
    # discarded and nothing appears twice: a vendor's third clip is *deferred*,
    # and a clip skipped by the category nudge is picked up on the next pass.
    return page + [
        clip for _breakdown, clip in scored if str(clip.get("id") or "") not in taken
    ]


def _category_of(clip: dict[str, Any]) -> str | None:
    category = clip.get("category_id")
    return str(category) if category else None


def _next_eligible(
    scored: list[tuple[ScoreBreakdown, dict[str, Any]]],
    taken: set[str],
    per_vendor: dict[str, int],
    max_per_vendor: int,
    *,
    avoid_category: str | None = None,
) -> dict[str, Any] | None:
    """The highest-scoring clip still eligible for a slot on this page."""
    for _breakdown, candidate in scored:
        if str(candidate.get("id") or "") in taken:
            continue
        if per_vendor.get(str(candidate.get("vendor_id") or ""), 0) >= max_per_vendor:
            continue
        if avoid_category is not None and _category_of(candidate) == avoid_category:
            continue
        return candidate
    return None
