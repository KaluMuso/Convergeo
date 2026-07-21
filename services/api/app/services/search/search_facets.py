from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal, Protocol

from app.schemas.base import StrictModel
from app.services.search.embedding_client import format_vector_for_rpc

PriceBucket = Literal["under_50k", "50k_200k", "200k_500k", "over_500k"]

_PRODUCT_ENTITY_KINDS = frozenset({"product", "listing"})


class FacetHit(Protocol):
    entity_kind: str
    category_path: str | None
    price_min_ngwee: int | None
    price_max_ngwee: int | None


class SearchFacetBucket(StrictModel):
    value: str
    count: int


class SearchFacets(StrictModel):
    categories: list[SearchFacetBucket]
    price: list[SearchFacetBucket]


def _price_bucket(price_ngwee: int | None) -> PriceBucket:
    price = price_ngwee or 0
    if price < 50_000:
        return "under_50k"
    if price < 200_000:
        return "50k_200k"
    if price < 500_000:
        return "200k_500k"
    return "over_500k"


def _matches_category(hit: FacetHit, category_path: str | None) -> bool:
    if not category_path:
        return True
    path = hit.category_path or ""
    return path == category_path or path.startswith(f"{category_path}/")


def _matches_price(
    hit: FacetHit,
    *,
    price_min_ngwee: int | None,
    price_max_ngwee: int | None,
) -> bool:
    if price_min_ngwee is not None:
        max_price = hit.price_max_ngwee
        if max_price is not None and max_price < price_min_ngwee:
            return False
    if price_max_ngwee is not None:
        min_price = hit.price_min_ngwee
        if min_price is not None and min_price > price_max_ngwee:
            return False
    return True


def _product_hits[T: FacetHit](hits: Sequence[T]) -> list[T]:
    return [hit for hit in hits if hit.entity_kind in _PRODUCT_ENTITY_KINDS]


def _parse_facet_buckets(raw: Any) -> list[SearchFacetBucket]:
    if not isinstance(raw, list):
        return []
    buckets: list[SearchFacetBucket] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        value = entry.get("value")
        count = entry.get("count")
        if isinstance(value, str) and isinstance(count, int):
            buckets.append(SearchFacetBucket(value=value, count=count))
    return buckets


def _parse_facets_payload(payload: Any) -> SearchFacets | None:
    if not isinstance(payload, dict):
        return None
    return SearchFacets(
        categories=_parse_facet_buckets(payload.get("categories")),
        price=_parse_facet_buckets(payload.get("price")),
    )


def call_search_query_facets(
    client: Any,
    *,
    query: str,
    embedding: list[float] | None,
    filters: dict[str, Any],
) -> SearchFacets | None:
    """Full-corpus facet counts via ``search_query_facets`` RPC (not RRF top-N)."""
    rpc_args: dict[str, Any] = {
        "query": query,
        "filters": filters,
    }
    if embedding is not None:
        rpc_args["query_embedding"] = format_vector_for_rpc(embedding)

    try:
        response = client.rpc("search_query_facets", rpc_args).execute()
    except Exception:
        return None

    data = getattr(response, "data", None)
    if data is None:
        return None
    if isinstance(data, list):
        if not data:
            return None
        return _parse_facets_payload(data[0])
    return _parse_facets_payload(data)


def compute_search_facets[T: FacetHit](
    hits: Sequence[T],
    *,
    category_path: str | None = None,
    price_min_ngwee: int | None = None,
    price_max_ngwee: int | None = None,
) -> SearchFacets:
    """Disjunctive facet counts from the RRF hit pool (top ~300 matches)."""
    product_hits = _product_hits(hits)
    category_counts: dict[str, int] = {}
    price_counts: dict[str, int] = {
        "under_50k": 0,
        "50k_200k": 0,
        "200k_500k": 0,
        "over_500k": 0,
    }

    for hit in product_hits:
        if not _matches_price(
            hit,
            price_min_ngwee=price_min_ngwee,
            price_max_ngwee=price_max_ngwee,
        ):
            continue
        path = hit.category_path
        if path:
            category_counts[path] = category_counts.get(path, 0) + 1

    for hit in product_hits:
        if not _matches_category(hit, category_path):
            continue
        bucket = _price_bucket(hit.price_min_ngwee)
        price_counts[bucket] += 1

    return SearchFacets(
        categories=[
            SearchFacetBucket(value=value, count=count)
            for value, count in sorted(category_counts.items())
        ],
        price=[
            SearchFacetBucket(value=value, count=price_counts[value])
            for value in ("under_50k", "50k_200k", "200k_500k", "over_500k")
        ],
    )


def filter_search_hits[T: FacetHit](
    hits: list[T],
    *,
    category_path: str | None = None,
    price_min_ngwee: int | None = None,
    price_max_ngwee: int | None = None,
) -> list[T]:
    """Apply product filters in Python (mirrors search_rrf JSON filter semantics)."""
    filtered: list[T] = []
    for hit in hits:
        if hit.entity_kind in _PRODUCT_ENTITY_KINDS:
            if not _matches_category(hit, category_path):
                continue
            if not _matches_price(
                hit,
                price_min_ngwee=price_min_ngwee,
                price_max_ngwee=price_max_ngwee,
            ):
                continue
        filtered.append(hit)
    return filtered
