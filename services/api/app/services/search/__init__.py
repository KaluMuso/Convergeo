from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Awaitable, Callable
from typing import Any, cast

from app.schemas.base import NgweeInt, StrictModel
from app.services.analytics.search_log import log_search_query
from app.services.search.embedding_client import fetch_query_embedding, format_vector_for_rpc
from app.services.search.query_builder import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    SearchKind,
    build_filters,
    paginate,
)
from app.services.search.synonyms import expand_query
from pydantic import Field

logger = logging.getLogger(__name__)

EmbeddingFetcher = Callable[[str], Awaitable[list[float] | None]]


class SearchHit(StrictModel):
    id: str
    entity_kind: str
    entity_id: str
    title: str
    body: str | None = None
    category_path: str | None = None
    price_min_ngwee: NgweeInt | None = None
    price_max_ngwee: NgweeInt | None = None
    lat: float | None = None
    lng: float | None = None
    locale_terms: list[str] | None = None
    boost_signals: dict[str, Any] = Field(default_factory=dict)
    rrf_score: float


class SearchResponse(StrictModel):
    query: str
    expanded_query: str
    page: int
    page_size: int
    total: int
    results: list[SearchHit]
    degraded: bool = False


class SuggestItem(StrictModel):
    title: str
    entity_kind: str
    entity_id: str


class SuggestResponse(StrictModel):
    query: str
    suggestions: list[SuggestItem]


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [cast(dict[str, Any], row) for row in data if isinstance(row, dict)]
    return []


def _parse_hit(row: dict[str, Any]) -> SearchHit | None:
    try:
        return SearchHit.model_validate(row)
    except Exception:
        logger.warning("Skipping malformed search_rrf row", extra={"row_keys": sorted(row)})
        return None


def call_search_rrf(
    client: Any,
    *,
    query: str,
    embedding: list[float] | None,
    filters: dict[str, Any],
) -> list[SearchHit]:
    rpc_args: dict[str, Any] = {
        "query": query,
        "filters": filters,
    }
    if embedding is not None:
        rpc_args["query_embedding"] = format_vector_for_rpc(embedding)

    response = client.rpc("search_rrf", rpc_args).execute()
    hits: list[SearchHit] = []
    for row in _rows(response):
        hit = _parse_hit(row)
        if hit is not None:
            hits.append(hit)
    return hits


def drop_wholesale_listing_hits(client: Any, hits: list[SearchHit]) -> list[SearchHit]:
    """Remove wholesale (B2B) listing hits from a consumer result set.

    Every active listing is indexed as ``entity_kind='listing'`` regardless of the
    wholesale flag (see ``search_upsert_listing``), so search would otherwise leak
    wholesale supplies into consumer results. Only verified business buyers may see
    them; callers gate this via ``include_wholesale`` (BusinessAccess.eligible).
    """
    listing_ids = [hit.entity_id for hit in hits if hit.entity_kind == "listing"]
    if not listing_ids:
        return hits
    response = (
        client.table("vendor_listings")
        .select("id")
        .in_("id", listing_ids)
        .eq("wholesale", True)
        .execute()
    )
    wholesale_ids = {str(row["id"]) for row in _rows(response) if row.get("id")}
    if not wholesale_ids:
        return hits
    return [
        hit
        for hit in hits
        if not (hit.entity_kind == "listing" and hit.entity_id in wholesale_ids)
    ]


def log_zero_result(*, query: str, filters: dict[str, Any], kind: SearchKind | None) -> None:
    logger.info(
        "search_zero_result",
        extra={
            "query": query,
            "filters": filters,
            "kind": kind,
            "zero_result": True,
        },
    )


async def run_search(
    client: Any,
    *,
    query: str,
    kind: SearchKind | None = None,
    category_path: str | None = None,
    price_min_ngwee: int | None = None,
    price_max_ngwee: int | None = None,
    page: int = DEFAULT_PAGE,
    page_size: int = DEFAULT_PAGE_SIZE,
    embedding_fetcher: EmbeddingFetcher | None = None,
    include_wholesale: bool = False,
    user_id: str | None = None,
) -> SearchResponse:
    trimmed = query.strip()
    expanded_query = expand_query(client, trimmed)
    filters = build_filters(
        kind=kind,
        category_path=category_path,
        price_min_ngwee=price_min_ngwee,
        price_max_ngwee=price_max_ngwee,
    )

    fetcher = embedding_fetcher or fetch_query_embedding
    try:
        embedding = await fetcher(trimmed)
    except Exception:
        logger.warning(
            "Query embedding fetcher raised; degrading to keyword search",
            exc_info=True,
            extra={"query_length": len(trimmed)},
        )
        embedding = None
    degraded = embedding is None and bool(trimmed)

    hits = call_search_rrf(
        client,
        query=trimmed,
        embedding=embedding,
        filters=filters,
    )
    if not include_wholesale:
        hits = drop_wholesale_listing_hits(client, hits)
    page_items, total = paginate(hits, page=page, page_size=page_size)

    if trimmed:
        # Fire-and-forget analytics: server operational log, written regardless of
        # consent, anonymized (normalized term only). Never breaks the search.
        log_search_query(
            term=trimmed,
            entity_counts=dict(Counter(hit.entity_kind for hit in hits)),
            zero_result=total == 0,
            user_id=user_id,
        )

    if total == 0 and trimmed:
        log_zero_result(query=trimmed, filters=filters, kind=kind)

    return SearchResponse(
        query=trimmed,
        expanded_query=expanded_query,
        page=page,
        page_size=page_size,
        total=total,
        results=page_items,
        degraded=degraded,
    )


def run_suggest(
    client: Any,
    *,
    query: str,
    kind: SearchKind | None = None,
    limit: int = 8,
    include_wholesale: bool = False,
) -> SuggestResponse:
    prefix = query.strip()
    if not prefix:
        return SuggestResponse(query=prefix, suggestions=[])

    expanded_prefix = expand_query(client, prefix)
    filters = build_filters(kind=kind)
    hits = call_search_rrf(
        client,
        query=expanded_prefix,
        embedding=None,
        filters=filters,
    )
    if not include_wholesale:
        hits = drop_wholesale_listing_hits(client, hits)

    suggestions: list[SuggestItem] = []
    seen_titles: set[str] = set()
    for hit in hits:
        normalized_title = hit.title.strip().lower()
        if not normalized_title or normalized_title in seen_titles:
            continue
        seen_titles.add(normalized_title)
        suggestions.append(
            SuggestItem(
                title=hit.title,
                entity_kind=hit.entity_kind,
                entity_id=hit.entity_id,
            )
        )
        if len(suggestions) >= limit:
            break

    return SuggestResponse(query=prefix, suggestions=suggestions)
