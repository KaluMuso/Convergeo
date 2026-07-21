from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Awaitable, Callable
from typing import Any, cast

from app.schemas.base import NgweeInt, StrictModel
from app.services.analytics.search_log import log_search_query
from app.services.listings.demo import drop_demo_listing_hits
from app.services.search.embedding_client import fetch_query_embedding, format_vector_for_rpc
from app.services.search.query_builder import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    SearchKind,
    build_filters,
    paginate,
)
from app.services.search.search_facets import (
    SearchFacets,
    call_search_query_facets,
    compute_search_facets,
    filter_search_hits,
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
    # Public route slug for customer deep-links (product/listing → PDP slug,
    # vendor/event slug, service UUID). Absent when unresolved.
    slug: str | None = None


class SearchResponse(StrictModel):
    query: str
    expanded_query: str
    page: int
    page_size: int
    total: int
    results: list[SearchHit]
    degraded: bool = False
    facets: SearchFacets | None = None


class SuggestItem(StrictModel):
    title: str
    entity_kind: str
    entity_id: str
    slug: str | None = None


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


def _nested_slug(value: Any) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        slug = value.get("slug")
        if isinstance(slug, str) and slug.strip():
            return slug.strip()
    return None


def attach_route_slugs(client: Any, hits: list[SearchHit]) -> list[SearchHit]:
    """Enrich hits with the public slug customers need for deep-links.

    ``search_documents`` stores UUID ``entity_id`` only. PDP/vendor/event routes
    resolve by slug, so without this enrichment the customer app historically
    linked ``/p/{uuid}`` and soft-404'd every search result.
    """
    if not hits:
        return hits

    product_ids = [hit.entity_id for hit in hits if hit.entity_kind == "product"]
    listing_ids = [hit.entity_id for hit in hits if hit.entity_kind == "listing"]
    vendor_ids = [hit.entity_id for hit in hits if hit.entity_kind == "vendor"]
    event_ids = [hit.entity_id for hit in hits if hit.entity_kind == "event"]

    product_slugs: dict[str, str] = {}
    listing_slugs: dict[str, str] = {}
    vendor_slugs: dict[str, str] = {}
    event_slugs: dict[str, str] = {}

    if product_ids:
        response = (
            client.table("products").select("id, slug").in_("id", product_ids).execute()
        )
        for row in _rows(response):
            entity_id = row.get("id")
            row_slug = row.get("slug")
            if entity_id and isinstance(row_slug, str) and row_slug.strip():
                product_slugs[str(entity_id)] = row_slug.strip()

    if listing_ids:
        response = (
            client.table("vendor_listings")
            .select("id, products!inner(slug)")
            .in_("id", listing_ids)
            .execute()
        )
        for row in _rows(response):
            entity_id = row.get("id")
            row_slug = _nested_slug(row.get("products"))
            if entity_id and row_slug:
                listing_slugs[str(entity_id)] = row_slug

    if vendor_ids:
        response = (
            client.table("vendors").select("id, slug").in_("id", vendor_ids).execute()
        )
        for row in _rows(response):
            entity_id = row.get("id")
            row_slug = row.get("slug")
            if entity_id and isinstance(row_slug, str) and row_slug.strip():
                vendor_slugs[str(entity_id)] = row_slug.strip()

    if event_ids:
        response = (
            client.table("events").select("id, slug").in_("id", event_ids).execute()
        )
        for row in _rows(response):
            entity_id = row.get("id")
            row_slug = row.get("slug")
            if entity_id and isinstance(row_slug, str) and row_slug.strip():
                event_slugs[str(entity_id)] = row_slug.strip()

    enriched: list[SearchHit] = []
    for hit in hits:
        route_slug: str | None
        if hit.entity_kind == "product":
            route_slug = product_slugs.get(hit.entity_id)
        elif hit.entity_kind == "listing":
            route_slug = listing_slugs.get(hit.entity_id)
        elif hit.entity_kind == "vendor":
            route_slug = vendor_slugs.get(hit.entity_id)
        elif hit.entity_kind == "event":
            route_slug = event_slugs.get(hit.entity_id)
        elif hit.entity_kind == "service":
            # Services have no separate slug column — UUID is the public slug.
            route_slug = hit.entity_id
        else:
            route_slug = None
        enriched.append(hit.model_copy(update={"slug": route_slug}))
    return enriched


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
    base_filters = build_filters(kind=kind)
    display_filters = build_filters(
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
        filters=base_filters,
    )
    if not include_wholesale:
        hits = drop_wholesale_listing_hits(client, hits)
    # D25 / VC-P06: demo seed inventory never appears in public discovery.
    hits = drop_demo_listing_hits(client, hits)

    facets: SearchFacets | None = None
    if trimmed and (kind is None or kind == "products"):
        facet_filters: dict[str, Any] = {}
        if category_path:
            facet_filters["category_path"] = category_path
        if price_min_ngwee is not None:
            facet_filters["price_min_ngwee"] = price_min_ngwee
        if price_max_ngwee is not None:
            facet_filters["price_max_ngwee"] = price_max_ngwee

        facets = call_search_query_facets(
            client,
            query=trimmed,
            embedding=embedding,
            filters=facet_filters,
        )
        if facets is None:
            facets = compute_search_facets(
                hits,
                category_path=category_path,
                price_min_ngwee=price_min_ngwee,
                price_max_ngwee=price_max_ngwee,
            )

    display_hits = filter_search_hits(
        hits,
        category_path=category_path,
        price_min_ngwee=price_min_ngwee,
        price_max_ngwee=price_max_ngwee,
    )
    page_items, total = paginate(display_hits, page=page, page_size=page_size)
    page_items = attach_route_slugs(client, page_items)

    if trimmed:
        # Fire-and-forget analytics: server operational log, written regardless of
        # consent, anonymized (normalized term only). Never breaks the search.
        log_search_query(
            term=trimmed,
            entity_counts=dict(Counter(hit.entity_kind for hit in display_hits)),
            zero_result=total == 0,
            user_id=user_id,
        )

    if total == 0 and trimmed:
        log_zero_result(query=trimmed, filters=display_filters, kind=kind)

    return SearchResponse(
        query=trimmed,
        expanded_query=expanded_query,
        page=page,
        page_size=page_size,
        total=total,
        results=page_items,
        degraded=degraded,
        facets=facets,
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
    hits = drop_demo_listing_hits(client, hits)
    hits = attach_route_slugs(client, hits)

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
                slug=hit.slug,
            )
        )
        if len(suggestions) >= limit:
            break

    return SuggestResponse(query=prefix, suggestions=suggestions)
