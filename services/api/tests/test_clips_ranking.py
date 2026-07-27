"""M17-P03 — the feed ranking formula (spec §3, "deterministic SQL, no ML").

The properties defended here are the ones a vendor would complain about if they
broke: the same feed twice in a row, one vendor not owning the page, and a score
you can take apart and explain.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.services.clips import ranking

NOW = datetime(2026, 7, 27, 12, 0, 0, tzinfo=UTC)


def _clip(
    clip_id: str,
    *,
    vendor: str = "v1",
    hours_old: float = 0.0,
    likes: int = 0,
    orders: int = 0,
    category: str | None = None,
) -> dict[str, Any]:
    return {
        "id": clip_id,
        "vendor_id": vendor,
        "published_at": (NOW - timedelta(hours=hours_old)).isoformat(),
        "like_count": likes,
        "orders_attributed": orders,
        "category_id": category,
    }


# --- Determinism ------------------------------------------------------------
def test_identical_inputs_produce_identical_order_across_runs() -> None:
    clips = [
        _clip("c1", vendor="a", hours_old=1, likes=5),
        _clip("c2", vendor="b", hours_old=2, likes=9),
        _clip("c3", vendor="c", hours_old=0.5, likes=1),
        _clip("c4", vendor="d", hours_old=10, likes=40, orders=2),
    ]
    first = [c["id"] for c in ranking.rank(list(clips), now=NOW)]
    for _ in range(5):
        assert [c["id"] for c in ranking.rank(list(clips), now=NOW)] == first


def test_ties_break_on_clip_id_so_the_order_is_total() -> None:
    """Two identical scores must not swap places — a cursor would skip an item."""
    tied = [
        _clip("bbb", vendor="a", hours_old=3, likes=2),
        _clip("aaa", vendor="b", hours_old=3, likes=2),
    ]
    assert [c["id"] for c in ranking.rank(tied, now=NOW)] == ["aaa", "bbb"]
    assert [c["id"] for c in ranking.rank(list(reversed(tied)), now=NOW)] == [
        "aaa",
        "bbb",
    ]


def test_input_order_does_not_change_the_result() -> None:
    clips = [
        _clip("c1", vendor="a", hours_old=1, likes=5),
        _clip("c2", vendor="b", hours_old=8, likes=50),
        _clip("c3", vendor="c", hours_old=30, likes=2),
    ]
    forward = [c["id"] for c in ranking.rank(list(clips), now=NOW)]
    backward = [c["id"] for c in ranking.rank(list(reversed(clips)), now=NOW)]
    assert forward == backward


# --- Per-vendor diversity cap ----------------------------------------------
def test_one_vendor_with_ten_clips_contributes_at_most_two_per_page() -> None:
    hog = [_clip(f"hog{i}", vendor="hog", hours_old=i * 0.1, likes=100) for i in range(10)]
    others = [_clip(f"other{i}", vendor=f"v{i}", hours_old=i) for i in range(18)]

    page = ranking.rank(hog + others, now=NOW)[: ranking.PAGE_SIZE]

    assert sum(1 for c in page if c["vendor_id"] == "hog") <= 2


def test_the_capped_clips_are_deferred_not_discarded() -> None:
    """A vendor's third clip still ranks — it just does not crowd this page."""
    hog = [_clip(f"hog{i}", vendor="hog", hours_old=i * 0.1) for i in range(5)]
    ordered = ranking.rank(hog, now=NOW)
    assert len(ordered) == 5
    assert {c["id"] for c in ordered} == {c["id"] for c in hog}


def test_the_cap_applies_per_page_not_globally() -> None:
    hog = [_clip(f"hog{i}", vendor="hog", hours_old=i * 0.1) for i in range(4)]
    page = ranking.rank(hog, now=NOW, page_size=2)
    assert [c["id"] for c in page[:2]] == ["hog0", "hog1"]


# --- Score components move in the expected direction ------------------------
def test_freshness_decays_with_age() -> None:
    fresh = ranking.score(_clip("a", hours_old=0), now=NOW)
    day_old = ranking.score(_clip("b", hours_old=24), now=NOW)
    week_old = ranking.score(_clip("c", hours_old=168), now=NOW)
    assert fresh > day_old > week_old


def test_freshness_halves_at_the_half_life() -> None:
    full = ranking.freshness_decay((NOW).isoformat(), now=NOW)
    half = ranking.freshness_decay(
        (NOW - timedelta(hours=ranking.FRESHNESS_HALF_LIFE_HOURS)).isoformat(), now=NOW
    )
    assert full == 1.0
    assert abs(half - 0.5) < 1e-9


def test_more_likes_scores_higher_at_the_same_age() -> None:
    quiet = ranking.score(_clip("a", hours_old=5, likes=0), now=NOW)
    loud = ranking.score(_clip("b", hours_old=5, likes=100), now=NOW)
    assert loud > quiet


def test_orders_are_weighted_double_the_like_term() -> None:
    """A clip that sells beats a clip that is merely popular, at equal counts."""
    liked = ranking.explain(_clip("a", hours_old=1, likes=10), now=NOW)
    sold = ranking.explain(_clip("b", hours_old=1, orders=10), now=NOW)
    assert abs(sold.order_term - 2 * liked.like_term) < 1e-9
    assert sold.score > liked.score


def test_an_unpublished_clip_scores_zero() -> None:
    assert ranking.score({"id": "x", "published_at": None}) == 0.0


def test_a_future_timestamp_does_not_exceed_full_freshness() -> None:
    """Clock skew must not become a ranking exploit."""
    assert ranking.freshness_decay((NOW + timedelta(hours=10)).isoformat(), now=NOW) == 1.0


def test_a_malformed_timestamp_scores_zero_rather_than_raising() -> None:
    assert ranking.score({"id": "x", "published_at": "not-a-date"}, now=NOW) == 0.0


# --- Explainability ---------------------------------------------------------
def test_explain_returns_every_component_of_the_score() -> None:
    breakdown = ranking.explain(_clip("c1", hours_old=24, likes=7, orders=3), now=NOW)
    payload = breakdown.as_dict()

    for key in (
        "clip_id",
        "freshness",
        "like_term",
        "order_term",
        "engagement",
        "score",
        "age_hours",
    ):
        assert key in payload

    assert payload["clip_id"] == "c1"
    assert abs(payload["age_hours"] - 24.0) < 1e-6


def test_the_breakdown_multiplies_back_to_the_score() -> None:
    breakdown = ranking.explain(_clip("c1", hours_old=12, likes=4, orders=1), now=NOW)
    assert abs(breakdown.freshness * breakdown.engagement - breakdown.score) < 1e-9


def test_engagement_is_one_plus_the_two_terms() -> None:
    breakdown = ranking.explain(_clip("c1", hours_old=2, likes=5, orders=2), now=NOW)
    assert abs(breakdown.engagement - (1 + breakdown.like_term + breakdown.order_term)) < 1e-9


# --- No personalization -----------------------------------------------------
def test_ranking_takes_no_user_argument() -> None:
    """A per-user signal would mean a per-user cache key on a 3G feed."""
    import inspect

    for fn in (ranking.rank, ranking.score, ranking.explain):
        params = set(inspect.signature(fn).parameters)
        assert not params & {"user", "user_id", "viewer", "viewer_id"}


# --- Category spread --------------------------------------------------------
def test_a_run_of_one_category_gets_broken_up_when_scores_are_close() -> None:
    clips = [
        _clip("a1", vendor="a", hours_old=1.0, category="cat-x"),
        _clip("a2", vendor="b", hours_old=1.1, category="cat-x"),
        _clip("b1", vendor="c", hours_old=1.2, category="cat-y"),
    ]
    page = ranking.rank(clips, now=NOW, page_size=3)
    categories = [c["category_id"] for c in page]
    assert categories[0] == "cat-x"
    # The second slot is not another cat-x when a near-scoring cat-y exists.
    assert categories[1] == "cat-y"
    assert len(page) == 3
    assert {c["id"] for c in page} == {"a1", "a2", "b1"}


def test_the_category_nudge_never_duplicates_or_drops_a_clip() -> None:
    """Regression: an early draft emitted the swapped-in clip twice.

    A duplicate in a cursor-paginated feed is worse than a bad order — the client
    renders the same card twice and the page boundary stops meaning anything.
    """
    clips = [
        _clip(f"c{i}", vendor=f"v{i}", hours_old=i * 0.05, category=f"cat-{i % 2}")
        for i in range(12)
    ]
    ordered = ranking.rank(clips, now=NOW, page_size=5)
    ids = [c["id"] for c in ordered]

    assert len(ids) == len(set(ids))
    assert set(ids) == {c["id"] for c in clips}


def test_clips_without_a_category_are_not_penalised() -> None:
    clips = [_clip(f"c{i}", vendor=f"v{i}", hours_old=i * 0.1) for i in range(5)]
    page = ranking.rank(clips, now=NOW, page_size=5)
    assert [c["id"] for c in page] == ["c0", "c1", "c2", "c3", "c4"]
