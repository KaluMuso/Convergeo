"""CR-G: proximity-first re-rank in run_search (Python candidate re-rank)."""

from __future__ import annotations

import asyncio
from typing import Any

from app.services.search import run_search
from tests.test_search import FakeSupabaseClient

# Lusaka CBD and Kitwe are ~320 km apart.
LUSAKA = (-15.4167, 28.2833)
KITWE = (-12.8024, 28.2132)

NEAR_ID = "00000000-0000-4000-8000-000000000001"
FAR_ID = "00000000-0000-4000-8000-000000000002"
NULL_ID = "00000000-0000-4000-8000-000000000003"


def _hit(
    entity_id: str, title: str, *, lat: float | None, lng: float | None, rrf: float
) -> dict[str, Any]:
    return {
        "id": entity_id,
        "entity_kind": "product",
        "entity_id": entity_id,
        "title": title,
        "body": None,
        "category_path": "electronics/phones",
        "price_min_ngwee": 450000,
        "price_max_ngwee": 450000,
        "lat": lat,
        "lng": lng,
        "locale_terms": None,
        "boost_signals": {},
        "rrf_score": rrf,
    }


async def _none_embedding(_query: str) -> list[float] | None:
    return None


def _handler(rows: list[dict[str, Any]]) -> Any:
    def handler(name: str, params: dict[str, Any]) -> list[Any]:
        if name == "expand_search_terms":
            return [str(params.get("p_query", ""))]
        if name == "search_rrf":
            return rows
        return []

    return handler


def _run(rows: list[dict[str, Any]], **kwargs: Any) -> Any:
    client = FakeSupabaseClient(_handler(rows))
    return asyncio.run(
        run_search(client, query="phone", embedding_fetcher=_none_embedding, **kwargs)
    )


def test_geo_rerank_near_outranks_far_for_equal_relevance() -> None:
    rows = [
        _hit(FAR_ID, "Far Phone", lat=KITWE[0], lng=KITWE[1], rrf=1.0),
        _hit(NEAR_ID, "Near Phone", lat=LUSAKA[0], lng=LUSAKA[1], rrf=1.0),
    ]
    result = _run(rows, user_lat=LUSAKA[0], user_lng=LUSAKA[1])

    assert result.results[0].entity_id == NEAR_ID  # nearer wins on equal relevance
    near = next(h for h in result.results if h.entity_id == NEAR_ID)
    far = next(h for h in result.results if h.entity_id == FAR_ID)
    assert near.distance_km is not None and near.distance_km < 1.0
    assert far.distance_km is not None and far.distance_km > 200.0


def test_ranking_unchanged_without_location() -> None:
    rows = [
        _hit(FAR_ID, "Far Phone", lat=KITWE[0], lng=KITWE[1], rrf=1.0),
        _hit(NEAR_ID, "Near Phone", lat=LUSAKA[0], lng=LUSAKA[1], rrf=1.0),
    ]
    result = _run(rows)  # no user location supplied

    assert [h.entity_id for h in result.results] == [FAR_ID, NEAR_ID]  # original order
    assert all(h.distance_km is None for h in result.results)


def test_far_strong_relevance_still_beats_near_weak() -> None:
    # Distance is a bounded nudge — it must not let a near, weakly-relevant hit
    # overtake a far, strongly-relevant one.
    rows = [
        _hit(FAR_ID, "Far Strong", lat=KITWE[0], lng=KITWE[1], rrf=5.0),
        _hit(NEAR_ID, "Near Weak", lat=LUSAKA[0], lng=LUSAKA[1], rrf=1.0),
    ]
    result = _run(rows, user_lat=LUSAKA[0], user_lng=LUSAKA[1])

    assert result.results[0].entity_id == FAR_ID


def test_null_geo_hit_is_kept_and_unboosted() -> None:
    rows = [
        _hit(NEAR_ID, "Near Phone", lat=LUSAKA[0], lng=LUSAKA[1], rrf=1.0),
        _hit(NULL_ID, "No Geo Phone", lat=None, lng=None, rrf=1.0),
    ]
    result = _run(rows, user_lat=LUSAKA[0], user_lng=LUSAKA[1])

    ids = {h.entity_id for h in result.results}
    assert NULL_ID in ids  # never dropped for missing coordinates
    null_hit = next(h for h in result.results if h.entity_id == NULL_ID)
    assert null_hit.distance_km is None
    assert result.results[0].entity_id == NEAR_ID  # boosted near hit leads
