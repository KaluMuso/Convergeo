from __future__ import annotations

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
