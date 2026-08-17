from __future__ import annotations

import asyncio
import logging
import math
from collections import Counter
from collections.abc import Awaitable, Callable
from typing import Any, cast

from app.schemas.base import NgweeInt, StrictModel
from app.services.analytics.search_log import log_search_query
from app.services.listings.demo import drop_demo_listing_hits
from app.services.search.embedding_client import (
    fetch_query_embedding,
    format_vector_for_rpc,
    get_embedding_timeout_seconds,
)
from app.services.search.kind_totals import compute_kind_totals, filter_hits_by_kind
from app.services.search.open_now import attach_open_now
from app.services.search.query_builder import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    SearchKind,
    build_facet_rpc_filters,
    build_filters,
    normalize_page,
    normalize_page_size,
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

_FACET_TAB_KINDS = frozenset({None, "products", "services", "events", "vendors"})


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
    # Great-circle km from the searcher when a user location is supplied and the
    # hit has coordinates; null otherwise (never dropped for missing geo).
    distance_km: float | None = None
    # Whether any branch of the resolved vendor is open now (Africa/Lusaka clock).
    # ``None`` when hours are not published — never treated as closed.
    is_open_now: bool | None = None
    # Listing/product class used for Class-C proximity weighting. Absent on
    # non-catalogue hits.
    product_class: str | None = None


class SearchKindTotals(StrictModel):
    """Per-tab result counts from a single unkinded search candidate set."""

    all: int
    products: int
    services: int
    events: int
    vendors: int


class SearchResponse(StrictModel):
    query: str
    expanded_query: str
    page: int
    page_size: int
    total: int
    results: list[SearchHit]
    degraded: bool = False
    facets: SearchFacets | None = None
    kind_totals: SearchKindTotals | None = None


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


def _call_search_rrf_with_fallback(
    client: Any,
    *,
    query: str,
    embedding: list[float] | None,
    filters: dict[str, Any],
) -> tuple[list[SearchHit], bool]:
    """Run ``search_rrf``, retrying FTS+trgm-only when the vector leg fails."""
    try:
        return call_search_rrf(
            client,
            query=query,
            embedding=embedding,
            filters=filters,
        ), False
    except Exception:
        if embedding is None:
            raise
        logger.warning(
            "search_rrf vector leg failed; retrying keyword-only",
            exc_info=True,
            extra={"query_length": len(query)},
        )
        return call_search_rrf(
            client,
            query=query,
            embedding=None,
            filters=filters,
        ), True


async def _resolve_query_embedding(
    fetcher: EmbeddingFetcher,
    query: str,
) -> tuple[list[float] | None, str | None]:
    """Fetch a query vector with a bounded wait; never raises."""
    trimmed = query.strip()
    if not trimmed:
        return None, None

    timeout = get_embedding_timeout_seconds()
    try:
        embedding = await asyncio.wait_for(fetcher(trimmed), timeout=timeout)
    except TimeoutError:
        return None, "embedding_timeout"
    except Exception:
        logger.warning(
            "Query embedding fetcher raised; degrading to keyword search",
            exc_info=True,
            extra={"query_length": len(trimmed)},
        )
        return None, "embedding_error"

    if embedding is None:
        return None, "embedding_unavailable"
    return embedding, None


def _log_search_degradation(*, query: str, reason: str) -> None:
    logger.info(
        "search_degraded",
        extra={
            "query_length": len(query),
            "degradation_reason": reason,
            "degraded": True,
        },
    )


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


def _nested_row(value: Any) -> dict[str, Any] | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        return value
    return None


def _customer_released_listing_classes(client: Any) -> set[str]:
    """Resolve the public discovery gates, failing closed for phased classes."""
    required = {
        "product_class_c_customer_release",
        "product_class_d_customer_release",
        "product_class_d_operations_approved",
        "product_class_e_customer_release",
    }
    try:
        response = (
            client.table("feature_flags")
            .select("flag,enabled")
            .in_("flag", list(required))
            .execute()
        )
        rows = _rows(response)
    except Exception:  # pragma: no cover - an unavailable gate cannot expose inventory
        return {"A", "B"}
    enabled = {str(row.get("flag")) for row in rows if row.get("enabled") is True}
    released = {"A", "B"}
    if "product_class_c_customer_release" in enabled:
        released.add("C")
    if {
        "product_class_d_customer_release",
        "product_class_d_operations_approved",
    } <= enabled:
        released.add("D")
    if "product_class_e_customer_release" in enabled:
        released.add("E")
    return released


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
    product_classes: dict[str, str] = {}
    listing_slugs: dict[str, str] = {}
    listing_classes: dict[str, str] = {}
    routable_listing_ids: set[str] = set()
    vendor_slugs: dict[str, str] = {}
    event_slugs: dict[str, str] = {}

    if product_ids:
        response = (
            client.table("products").select("id, slug, product_class").in_("id", product_ids).execute()
        )
        for row in _rows(response):
            entity_id = row.get("id")
            row_slug = row.get("slug")
            if entity_id and isinstance(row_slug, str) and row_slug.strip():
                product_slugs[str(entity_id)] = row_slug.strip()
            product_class = row.get("product_class")
            if entity_id and isinstance(product_class, str) and product_class.strip():
                product_classes[str(entity_id)] = product_class.strip()

    if listing_ids:
        released_listing_classes = _customer_released_listing_classes(client)
        response = (
            client.table("vendor_listings")
            .select(
                "id, product_id, product_class, title_override, status, "
                "vendors!inner(status), products(slug, status)"
            )
            .in_("id", listing_ids)
            .eq("status", "active")
            .eq("vendors.status", "active")
            .execute()
        )
        for row in _rows(response):
            entity_id = row.get("id")
            if not entity_id:
                continue
            if str(row.get("product_class") or "A") not in released_listing_classes:
                continue
            listing_id = str(entity_id)
            listing_classes[listing_id] = str(row.get("product_class") or "A")
            if row.get("product_id") is None:
                # A true standalone listing deliberately has no canonical slug;
                # the customer routes it by listing UUID at /l/{id}. The
                # standalone detail endpoint requires a nonblank title.
                title_override = row.get("title_override")
                if isinstance(title_override, str) and title_override.strip():
                    routable_listing_ids.add(listing_id)
                continue

            product = _nested_row(row.get("products"))
            if product is None or str(product.get("status") or "") != "active":
                continue
            row_slug = product.get("slug")
            if isinstance(row_slug, str) and row_slug.strip():
                routable_listing_ids.add(listing_id)
                listing_slugs[listing_id] = row_slug.strip()

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
        if hit.entity_kind == "listing" and hit.entity_id not in routable_listing_ids:
            # Stale search documents must not produce a canonical-looking hit
            # that falls through to the standalone route and then 404s.
            continue
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
        product_class = None
        if hit.entity_kind == "listing":
            product_class = listing_classes.get(hit.entity_id)
        elif hit.entity_kind == "product":
            product_class = product_classes.get(hit.entity_id)
        enriched.append(hit.model_copy(update={"slug": route_slug, "product_class": product_class}))
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


# Proximity re-rank tuning. The boost is bounded and multiplicative on rrf_score:
# a co-located hit gains at most _GEO_WEIGHT of its score, decaying with distance,
# so it nudges equally-relevant hits nearer the top but never lets a far, weakly
# relevant hit outrank a near, strongly relevant one.
_GEO_DECAY_KM = 12.0  # distance at which the proximity factor falls to ~1/e
_GEO_WEIGHT = 0.5  # max fractional uplift for a co-located hit
_GEO_CLASS_C_WEIGHT_MULTIPLIER = 2.5  # strategy: 2–3× Class C proximity
_EARTH_RADIUS_KM = 6371.0088


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def _geo_rerank(
    hits: list[SearchHit], *, user_lat: float, user_lng: float
) -> list[SearchHit]:
    """Stamp ``distance_km`` and re-sort by an rrf_score blended with a bounded
    proximity boost. Hits without coordinates get no boost and are never dropped;
    the stable sort preserves original RRF order among ties."""
    scored: list[tuple[float, int, SearchHit]] = []
    for idx, hit in enumerate(hits):
        if hit.lat is None or hit.lng is None:
            hit.distance_km = None
            blended = hit.rrf_score
        else:
            distance = _haversine_km(user_lat, user_lng, hit.lat, hit.lng)
            hit.distance_km = round(distance, 3)
            geo_factor = math.exp(-distance / _GEO_DECAY_KM)  # (0, 1]
            geo_weight = _GEO_WEIGHT
            if hit.product_class == "C":
                geo_weight *= _GEO_CLASS_C_WEIGHT_MULTIPLIER
            blended = hit.rrf_score * (1.0 + geo_weight * geo_factor)
        scored.append((blended, idx, hit))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [hit for _blended, _idx, hit in scored]


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
    user_lat: float | None = None,
    user_lng: float | None = None,
    include_kind_totals: bool = False,
) -> SearchResponse:
    trimmed = query.strip()
    expanded_query = expand_query(client, trimmed)
    normalized_page = normalize_page(page)
    normalized_page_size = normalize_page_size(page_size)
    # When tab totals are requested, fetch all kinds once and filter in-process
    # instead of fanning out five extra /search calls from the customer app.
    rpc_kind = None if include_kind_totals else kind
    base_filters = build_filters(kind=rpc_kind)
    display_filters = build_filters(
        kind=kind,
        category_path=category_path,
        price_min_ngwee=price_min_ngwee,
        price_max_ngwee=price_max_ngwee,
    )

    fetcher = embedding_fetcher or fetch_query_embedding
    embedding, embed_reason = await _resolve_query_embedding(fetcher, trimmed)
    degraded = embed_reason is not None

    hits, rpc_degraded = _call_search_rrf_with_fallback(
        client,
        query=trimmed,
        embedding=embedding,
        filters=base_filters,
    )
    if rpc_degraded:
        degraded = True
        embedding = None

    if degraded and trimmed:
        reason = "vector_rpc_fallback" if rpc_degraded else (embed_reason or "unknown")
        _log_search_degradation(query=trimmed, reason=reason)
    if not include_wholesale:
        hits = drop_wholesale_listing_hits(client, hits)
    # D25 / VC-P06: demo seed inventory never appears in public discovery.
    hits = drop_demo_listing_hits(client, hits)
    # Resolve/filter before totals and pagination so stale listing documents do
    # not inflate counts or leave a short page after enrichment.
    hits = attach_route_slugs(client, hits)

    kind_totals: SearchKindTotals | None = None
    if include_kind_totals and trimmed:
        totals = compute_kind_totals(hits)
        kind_totals = SearchKindTotals.model_validate(totals)
        hits = filter_hits_by_kind(hits, kind)

    facets: SearchFacets | None = None
    if trimmed and kind in _FACET_TAB_KINDS:
        facet_filters = build_facet_rpc_filters(
            kind=kind,
            category_path=category_path,
            price_min_ngwee=price_min_ngwee,
            price_max_ngwee=price_max_ngwee,
            include_wholesale=include_wholesale,
        )

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
    # Proximity-first discovery: when the searcher shares a location, re-rank the
    # whole filtered candidate window by relevance blended with distance before
    # paginating. Ranking is byte-identical when no location is supplied.
    if user_lat is not None and user_lng is not None:
        display_hits = _geo_rerank(display_hits, user_lat=user_lat, user_lng=user_lng)
    page_items, total = paginate(
        display_hits,
        page=normalized_page,
        page_size=normalized_page_size,
    )
    page_items = attach_open_now(client, page_items)

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
        page=normalized_page,
        page_size=normalized_page_size,
        total=total,
        results=page_items,
        degraded=degraded,
        facets=facets,
        kind_totals=kind_totals,
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
