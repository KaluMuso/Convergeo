from __future__ import annotations

import pytest
from app.services.search import SearchHit
from app.services.search.search_facets import (
    SearchFacetBucket,
    call_search_query_facets,
    compute_search_facets,
    filter_search_hits,
)


def test_compute_search_facets_counts_categories_and_price_buckets() -> None:
    hits = [
        SearchHit(
            id="1",
            entity_kind="product",
            entity_id="1",
            title="Phone A",
            category_path="electronics/phones",
            price_min_ngwee=40_000,
            price_max_ngwee=40_000,
            rrf_score=1.0,
        ),
        SearchHit(
            id="2",
            entity_kind="product",
            entity_id="2",
            title="Phone B",
            category_path="electronics/phones",
            price_min_ngwee=120_000,
            price_max_ngwee=120_000,
            rrf_score=0.9,
        ),
        SearchHit(
            id="3",
            entity_kind="product",
            entity_id="3",
            title="Chitenge",
            category_path="fashion/chitenge",
            price_min_ngwee=25_000,
            price_max_ngwee=25_000,
            rrf_score=0.8,
        ),
    ]

    facets = compute_search_facets(hits)
    assert {bucket.value: bucket.count for bucket in facets.categories} == {
        "electronics/phones": 2,
        "fashion/chitenge": 1,
    }
    assert {bucket.value: bucket.count for bucket in facets.price} == {
        "under_50k": 2,
        "50k_200k": 1,
        "200k_500k": 0,
        "over_500k": 0,
    }


def test_filter_search_hits_applies_category_and_price() -> None:
    hits = [
        SearchHit(
            id="1",
            entity_kind="product",
            entity_id="1",
            title="Phone",
            category_path="electronics/phones",
            price_min_ngwee=40_000,
            price_max_ngwee=40_000,
            rrf_score=1.0,
        ),
        SearchHit(
            id="2",
            entity_kind="vendor",
            entity_id="2",
            title="Vendor",
            rrf_score=0.5,
        ),
    ]

    filtered = filter_search_hits(
        hits,
        category_path="electronics",
        price_min_ngwee=30_000,
        price_max_ngwee=50_000,
    )
    assert [hit.entity_kind for hit in filtered] == ["product"]


def test_call_search_query_facets_parses_rpc_payload() -> None:
    class _RpcResponse:
        def __init__(self, data: object) -> None:
            self.data = data

    class _FacetRpc:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def execute(self) -> _RpcResponse:
            return _RpcResponse([self._payload])

    class _Client:
        def rpc(self, name: str, _params: dict[str, object]) -> _FacetRpc:
            assert name == "search_query_facets"
            return _FacetRpc(
                {
                    "categories": [{"value": "electronics/phones", "count": 2}],
                    "price": [{"value": "under_50k", "count": 1}],
                }
            )

    facets = call_search_query_facets(
        _Client(),
        query="phone",
        embedding=None,
        filters={},
    )
    assert facets is not None
    assert facets.categories == [
        SearchFacetBucket(value="electronics/phones", count=2),
    ]
    assert facets.price[0].value == "under_50k"


@pytest.mark.parametrize("entity_kind", ["product", "listing"])
@pytest.mark.parametrize("omit_price", [False, True])
def test_unknown_min_price_is_not_a_numeric_price_facet(entity_kind: str, omit_price: bool) -> None:
    payload: dict[str, object] = {
        "id": "unknown",
        "entity_id": "unknown",
        "entity_kind": entity_kind,
        "title": "Rice",
        "category_path": "food/rice",
        "rrf_score": 1.0,
        "price_max_ngwee": 80_000,
    }
    if not omit_price:
        payload["price_min_ngwee"] = None
    unknown = SearchHit.model_validate(payload)
    assert unknown.price_min_ngwee is None
    facets = compute_search_facets([unknown])
    assert all(bucket.count == 0 for bucket in facets.price)
    assert facets.categories == [SearchFacetBucket(value="food/rice", count=1)]


@pytest.mark.parametrize("entity_kind", ["product", "listing"])
@pytest.mark.parametrize(
    ("price", "expected_bucket"),
    [
        (0, "under_50k"),
        (49_999, "under_50k"),
        (50_000, "50k_200k"),
        (199_999, "50k_200k"),
        (200_000, "200k_500k"),
        (499_999, "200k_500k"),
        (500_000, "over_500k"),
    ],
)
def test_known_prices_keep_zero_and_existing_bucket_boundaries(
    entity_kind: str, price: int, expected_bucket: str
) -> None:
    hit = SearchHit(
        id="known",
        entity_id="known",
        entity_kind=entity_kind,
        title="Rice",
        category_path="food/rice",
        price_min_ngwee=price,
        price_max_ngwee=price,
        rrf_score=1.0,
    )
    facets = compute_search_facets([hit])
    assert {bucket.value: bucket.count for bucket in facets.price if bucket.count} == {
        expected_bucket: 1
    }


def test_mixed_unknown_and_free_prices_preserve_disjunctive_facets() -> None:
    unknown = SearchHit(
        id="unknown",
        entity_id="unknown",
        entity_kind="product",
        title="Rice",
        category_path="food/rice",
        rrf_score=1.0,
    )
    free = unknown.model_copy(
        update={
            "id": "free",
            "entity_id": "free",
            "price_min_ngwee": 0,
            "price_max_ngwee": 0,
        }
    )
    other = free.model_copy(
        update={
            "id": "other",
            "entity_id": "other",
            "category_path": "other",
        }
    )
    service = free.model_copy(
        update={
            "id": "service",
            "entity_id": "service",
            "entity_kind": "service",
        }
    )
    facets = compute_search_facets(
        [unknown, free, other, service],
        category_path="food/rice",
        price_min_ngwee=1,
    )
    # Price facet removes its own price filter but still applies category/kind.
    assert {b.value: b.count for b in facets.price if b.count} == {"under_50k": 1}
    # Category and unknown-price budget admission are deliberately unchanged.
    assert facets.categories == [SearchFacetBucket(value="food/rice", count=2)]
    assert filter_search_hits([unknown], price_min_ngwee=1) == [unknown]
