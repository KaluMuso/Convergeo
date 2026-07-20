from __future__ import annotations

import base64
import math
from typing import Annotated, Any, Literal, cast

from app.deps import get_supabase_client
from app.errors import AppError
from app.services.business.access import (
    BusinessAccess,
    get_business_access,
    require_wholesale_access,
)
from app.services.flags import is_public_launch
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/catalog", tags=["catalog"])

DEFAULT_PAGE_SIZE = 24
MAX_PAGE_SIZE = 48
EARTH_RADIUS_M = 6_371_000

CatalogSort = Literal["relevance", "cheapest", "nearest", "newest"]
ConditionFilter = Literal["new", "refurbished"]
AvailabilityFilter = Literal["in_stock", "out_of_stock"]


class FacetBucket(BaseModel):
    value: str
    count: int


class FacetCounts(BaseModel):
    condition: list[FacetBucket] = Field(default_factory=list)
    availability: list[FacetBucket] = Field(default_factory=list)
    rating: list[FacetBucket] = Field(default_factory=list)
    price: list[FacetBucket] = Field(default_factory=list)


class CatalogListingItem(BaseModel):
    id: str
    title: str
    product_slug: str | None = None
    vendor_name: str
    vendor_slug: str | None = None
    price_ngwee: int
    condition: str
    in_stock: bool
    image_public_id: str | None = None
    rating: float = 0.0
    review_count: int = 0
    lat: float | None = None
    lng: float | None = None
    distance_m: float | None = None
    landmark: str | None = None
    # B2B wholesale fields — populated only on the gated wholesale/supplies feed.
    wholesale: bool | None = None
    moq: int | None = None
    price_tiers: list[dict[str, Any]] | None = None


class CatalogListResponse(BaseModel):
    items: list[CatalogListingItem]
    facets: FacetCounts
    total: int
    next_cursor: str | None = None


class PlpFilterState(BaseModel):
    category_path: str | None = None
    sort: CatalogSort = "relevance"
    price_min_ngwee: int | None = None
    price_max_ngwee: int | None = None
    condition: list[ConditionFilter] = Field(default_factory=list)
    availability: list[AvailabilityFilter] = Field(default_factory=list)
    min_rating: int | None = Field(default=None, ge=1, le=5)
    lat: float | None = None
    lng: float | None = None
    radius_km: float | None = Field(default=None, gt=0, le=500)
    cursor: int = Field(default=0, ge=0)
    limit: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)


# Documented SQL fragments (executed via PostgREST + Python enrichment; bound params only).
FACET_COUNT_SQL = """
WITH scoped AS (
  SELECT sd.entity_id,
         vl.condition,
         CASE
           WHEN vl.stock_mode = 'always_available' OR coalesce(vl.stock_qty, 0) > 0 THEN 'in_stock'
           ELSE 'out_of_stock'
         END AS availability,
         coalesce(vr.avg_rating, 0) AS avg_rating,
         sd.price_min_ngwee
  FROM public.search_documents sd
  JOIN public.vendor_listings vl ON vl.id = sd.entity_id AND vl.status = 'active'
  JOIN public.vendors v ON v.id = vl.vendor_id AND v.status = 'active'
  LEFT JOIN LATERAL (
    SELECT avg(r.rating)::float AS avg_rating
    FROM public.order_item_products oip
    JOIN public.reviews r ON r.order_item_id = oip.order_item_id AND r.status = 'published'
    WHERE oip.listing_id = vl.id
  ) vr ON true
  WHERE sd.entity_kind = 'listing'
    AND sd.is_public = true
    AND ($1::text IS NULL OR sd.category_path LIKE $1 || '%')
)
SELECT 'condition' AS facet, condition AS value, count(*)::int AS count
FROM scoped
GROUP BY condition
UNION ALL
SELECT 'availability', availability, count(*)::int
FROM scoped
GROUP BY availability;
"""

DISTANCE_SORT_SQL = """
SELECT sd.entity_id,
       (
         6371000 * acos(
           least(1.0, greatest(-1.0,
             cos(radians($1)) * cos(radians(sd.lat))
             * cos(radians(sd.lng) - radians($2))
             + sin(radians($1)) * sin(radians(sd.lat))
           ))
         )
       ) AS distance_m
FROM public.search_documents sd
WHERE sd.entity_kind = 'listing'
  AND sd.is_public = true
  AND sd.lat IS NOT NULL
  AND sd.lng IS NOT NULL
ORDER BY distance_m ASC, sd.updated_at DESC;
"""


class _SearchDocRow(BaseModel):
    entity_id: str
    title: str
    category_path: str | None = None
    price_min_ngwee: int | None = None
    lat: float | None = None
    lng: float | None = None
    boost_signals: dict[str, Any] = Field(default_factory=dict)
    updated_at: str | None = None


class _ListingRow(BaseModel):
    id: str
    vendor_id: str
    product_id: str | None = None
    condition: str
    stock_mode: str
    stock_qty: int | None = None
    created_at: str | None = None
    wholesale: bool = False
    demo: bool = False


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    return (
        EARTH_RADIUS_M
        * math.acos(
            min(
                1.0,
                max(
                    -1.0,
                    math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
                    * math.cos(math.radians(lng2) - math.radians(lng1))
                    + math.sin(math.radians(lat1)) * math.sin(math.radians(lat2)),
                ),
            )
        )
    )


def encode_plp_cursor(offset: int) -> str:
    payload = str(offset).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_plp_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    padding = "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(cursor + padding)
        return max(0, int(raw.decode("utf-8")))
    except (ValueError, UnicodeDecodeError) as exc:
        raise AppError("invalid_cursor", "Invalid pagination cursor", 400) from exc


def encode_plp_filters(state: PlpFilterState) -> dict[str, str]:
    params: dict[str, str] = {}
    if state.category_path:
        params["category_path"] = state.category_path
    if state.sort != "relevance":
        params["sort"] = state.sort
    if state.price_min_ngwee is not None:
        params["min_price"] = str(state.price_min_ngwee)
    if state.price_max_ngwee is not None:
        params["max_price"] = str(state.price_max_ngwee)
    if state.condition:
        params["condition"] = ",".join(state.condition)
    if state.availability:
        params["availability"] = ",".join(state.availability)
    if state.min_rating is not None:
        params["min_rating"] = str(state.min_rating)
    if state.lat is not None:
        params["lat"] = str(state.lat)
    if state.lng is not None:
        params["lng"] = str(state.lng)
    if state.radius_km is not None:
        params["radius_km"] = str(state.radius_km)
    if state.cursor > 0:
        params["cursor"] = encode_plp_cursor(state.cursor)
    if state.limit != DEFAULT_PAGE_SIZE:
        params["limit"] = str(state.limit)
    return params


def decode_plp_filters(params: dict[str, str | list[str] | None]) -> PlpFilterState:
    def _one(key: str) -> str | None:
        raw = params.get(key)
        if raw is None:
            return None
        if isinstance(raw, list):
            return raw[0] if raw else None
        return raw

    condition_raw = _one("condition")
    availability_raw = _one("availability")
    sort_raw = _one("sort") or "relevance"
    if sort_raw not in ("relevance", "cheapest", "nearest", "newest"):
        raise AppError("invalid_sort", "Unsupported sort value", 400)

    condition: list[ConditionFilter] = []
    if condition_raw:
        for part in condition_raw.split(","):
            token = part.strip()
            if token in ("new", "refurbished"):
                condition.append(token)  # type: ignore[arg-type]

    availability: list[AvailabilityFilter] = []
    if availability_raw:
        for part in availability_raw.split(","):
            token = part.strip()
            if token in ("in_stock", "out_of_stock"):
                availability.append(token)  # type: ignore[arg-type]

    min_rating: int | None = None
    min_rating_raw = _one("min_rating")
    if min_rating_raw is not None:
        min_rating = int(min_rating_raw)

    price_min_raw = _one("min_price")
    price_max_raw = _one("max_price")
    lat_raw = _one("lat")
    lng_raw = _one("lng")
    radius_raw = _one("radius_km")
    limit_raw = _one("limit")

    return PlpFilterState(
        category_path=_one("category_path"),
        sort=sort_raw,  # type: ignore[arg-type]
        price_min_ngwee=int(price_min_raw) if price_min_raw is not None else None,
        price_max_ngwee=int(price_max_raw) if price_max_raw is not None else None,
        condition=condition,
        availability=availability,
        min_rating=min_rating,
        lat=float(lat_raw) if lat_raw is not None else None,
        lng=float(lng_raw) if lng_raw is not None else None,
        radius_km=float(radius_raw) if radius_raw is not None else None,
        cursor=decode_plp_cursor(_one("cursor")),
        limit=int(limit_raw) if limit_raw is not None else DEFAULT_PAGE_SIZE,
    )


def _listing_in_stock(stock_mode: str, stock_qty: int | None) -> bool:
    return stock_mode == "always_available" or (stock_qty is not None and stock_qty > 0)


def _relevance_score(boost: dict[str, Any], updated_at: str | None) -> tuple[int, int, str]:
    verified = 1 if boost.get("verified") else 0
    in_stock = 1 if boost.get("in_stock") else 0
    return (verified, in_stock, updated_at or "")


def _response_rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None) or []
    return cast(list[dict[str, Any]], data)


def _fetch_search_documents(client: Any, category_path: str | None) -> list[_SearchDocRow]:
    query = (
        client.table("search_documents")
        .select(
            "entity_id,title,category_path,price_min_ngwee,lat,lng,boost_signals,updated_at"
        )
        .eq("entity_kind", "listing")
        .eq("is_public", True)
    )
    if category_path:
        escaped = category_path.replace("%", r"\%").replace("_", r"\_")
        query = query.like("category_path", f"{escaped}%")

    response = query.execute()
    rows = _response_rows(response)
    return [_SearchDocRow.model_validate(row) for row in rows]


def _fetch_listings(client: Any, listing_ids: list[str]) -> dict[str, _ListingRow]:
    if not listing_ids:
        return {}
    response = (
        client.table("vendor_listings")
        .select(
            "id,vendor_id,product_id,condition,stock_mode,stock_qty,created_at,status,wholesale,demo"
        )
        .in_("id", listing_ids)
        .eq("status", "active")
        .execute()
    )
    return {
        str(row["id"]): _ListingRow.model_validate(row) for row in _response_rows(response)
    }


def _fetch_vendors(client: Any, vendor_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not vendor_ids:
        return {}
    response = (
        client.table("vendors")
        .select("id,slug,display_name,status")
        .in_("id", vendor_ids)
        .eq("status", "active")
        .execute()
    )
    return {str(row["id"]): row for row in _response_rows(response)}


def _fetch_products(client: Any, product_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not product_ids:
        return {}
    response = (
        client.table("products")
        .select("id,slug,name,status")
        .in_("id", product_ids)
        .eq("status", "active")
        .execute()
    )
    return {str(row["id"]): row for row in _response_rows(response)}


def _fetch_landmarks(client: Any, vendor_ids: list[str]) -> dict[str, str]:
    if not vendor_ids:
        return {}
    response = (
        client.table("vendor_locations")
        .select("vendor_id,landmark,created_at")
        .in_("vendor_id", vendor_ids)
        .order("created_at")
        .execute()
    )
    landmarks: dict[str, str] = {}
    for row in _response_rows(response):
        vendor_id = str(row["vendor_id"])
        if vendor_id not in landmarks:
            landmarks[vendor_id] = str(row["landmark"])
    return landmarks


def _fetch_images(client: Any, listing_ids: list[str]) -> dict[str, str]:
    if not listing_ids:
        return {}
    response = (
        client.table("listing_images")
        .select("listing_id,cloudinary_public_id,position")
        .in_("listing_id", listing_ids)
        .order("position")
        .execute()
    )
    images: dict[str, str] = {}
    for row in _response_rows(response):
        listing_id = str(row["listing_id"])
        if listing_id not in images:
            images[listing_id] = str(row["cloudinary_public_id"])
    return images


def _fetch_listing_ratings(client: Any, listing_ids: list[str]) -> dict[str, tuple[float, int]]:
    if not listing_ids:
        return {}
    oip_response = (
        client.table("order_item_products")
        .select("listing_id,order_item_id")
        .in_("listing_id", listing_ids)
        .execute()
    )
    oip_rows = _response_rows(oip_response)
    if not oip_rows:
        return {}

    order_item_ids = [str(row["order_item_id"]) for row in oip_rows]
    reviews_response = (
        client.table("reviews")
        .select("order_item_id,rating")
        .in_("order_item_id", order_item_ids)
        .eq("status", "published")
        .execute()
    )
    rating_by_order_item = {
        str(row["order_item_id"]): int(row["rating"]) for row in _response_rows(reviews_response)
    }

    totals: dict[str, list[int]] = {}
    for row in oip_rows:
        listing_id = str(row["listing_id"])
        order_item_id = str(row["order_item_id"])
        rating = rating_by_order_item.get(order_item_id)
        if rating is None:
            continue
        totals.setdefault(listing_id, []).append(rating)

    return {
        listing_id: (sum(values) / len(values), len(values))
        for listing_id, values in totals.items()
    }


class _CatalogCandidate(BaseModel):
    search_doc: _SearchDocRow
    listing: _ListingRow
    vendor: dict[str, Any]
    product: dict[str, Any] | None
    image_public_id: str | None
    landmark: str | None
    rating: float
    review_count: int
    in_stock: bool
    distance_m: float | None = None


def _matches_filters(
    candidate: _CatalogCandidate,
    *,
    filters: PlpFilterState,
    ignore: set[str] | None = None,
) -> bool:
    ignore = ignore or set()
    price = candidate.search_doc.price_min_ngwee or 0

    if "price" not in ignore:
        if filters.price_min_ngwee is not None and price < filters.price_min_ngwee:
            return False
        if filters.price_max_ngwee is not None and price > filters.price_max_ngwee:
            return False

    if "condition" not in ignore and filters.condition:
        if candidate.listing.condition not in filters.condition:
            return False

    if "availability" not in ignore and filters.availability:
        availability = "in_stock" if candidate.in_stock else "out_of_stock"
        if availability not in filters.availability:
            return False

    if "rating" not in ignore and filters.min_rating is not None:
        if candidate.rating < filters.min_rating:
            return False

    if "location" not in ignore and filters.radius_km is not None:
        if filters.lat is None or filters.lng is None:
            return False
        if candidate.search_doc.lat is None or candidate.search_doc.lng is None:
            return False
        distance_m = haversine_m(
            filters.lat,
            filters.lng,
            candidate.search_doc.lat,
            candidate.search_doc.lng,
        )
        if distance_m > filters.radius_km * 1000:
            return False

    return True


def _build_candidates(client: Any, category_path: str | None) -> list[_CatalogCandidate]:
    search_docs = _fetch_search_documents(client, category_path)
    listing_ids = [doc.entity_id for doc in search_docs]
    listings = _fetch_listings(client, listing_ids)
    vendor_ids = sorted({listing.vendor_id for listing in listings.values()})
    product_ids = sorted(
        {listing.product_id for listing in listings.values() if listing.product_id is not None}
    )
    vendors = _fetch_vendors(client, vendor_ids)
    products = _fetch_products(client, product_ids)
    images = _fetch_images(client, listing_ids)
    landmarks = _fetch_landmarks(client, vendor_ids)
    ratings = _fetch_listing_ratings(client, listing_ids)

    candidates: list[_CatalogCandidate] = []
    for doc in search_docs:
        listing = listings.get(doc.entity_id)
        if listing is None:
            continue
        vendor = vendors.get(listing.vendor_id)
        if vendor is None:
            continue
        product = products.get(listing.product_id) if listing.product_id else None
        rating, review_count = ratings.get(doc.entity_id, (0.0, 0))
        in_stock = _listing_in_stock(listing.stock_mode, listing.stock_qty)
        candidates.append(
            _CatalogCandidate(
                search_doc=doc,
                listing=listing,
                vendor=vendor,
                product=product,
                image_public_id=images.get(doc.entity_id),
                landmark=landmarks.get(listing.vendor_id),
                rating=rating,
                review_count=review_count,
                in_stock=in_stock,
            )
        )
    return candidates


def compute_facet_counts(
    candidates: list[_CatalogCandidate],
    filters: PlpFilterState,
) -> FacetCounts:
    condition_counts: dict[str, int] = {"new": 0, "refurbished": 0}
    availability_counts: dict[str, int] = {"in_stock": 0, "out_of_stock": 0}
    rating_counts: dict[str, int] = {
        "4_plus": 0,
        "3_plus": 0,
        "2_plus": 0,
        "1_plus": 0,
    }
    price_buckets: dict[str, int] = {
        "under_50k": 0,
        "50k_200k": 0,
        "200k_500k": 0,
        "over_500k": 0,
    }

    for candidate in candidates:
        if not _matches_filters(candidate, filters=filters, ignore={"condition"}):
            continue
        condition_counts[candidate.listing.condition] = (
            condition_counts.get(candidate.listing.condition, 0) + 1
        )

    for candidate in candidates:
        if not _matches_filters(candidate, filters=filters, ignore={"availability"}):
            continue
        key = "in_stock" if candidate.in_stock else "out_of_stock"
        availability_counts[key] += 1

    for candidate in candidates:
        if not _matches_filters(candidate, filters=filters, ignore={"rating"}):
            continue
        if candidate.rating >= 4:
            rating_counts["4_plus"] += 1
        if candidate.rating >= 3:
            rating_counts["3_plus"] += 1
        if candidate.rating >= 2:
            rating_counts["2_plus"] += 1
        if candidate.rating >= 1:
            rating_counts["1_plus"] += 1

    for candidate in candidates:
        if not _matches_filters(candidate, filters=filters, ignore={"price"}):
            continue
        price = candidate.search_doc.price_min_ngwee or 0
        if price < 50_000:
            price_buckets["under_50k"] += 1
        elif price < 200_000:
            price_buckets["50k_200k"] += 1
        elif price < 500_000:
            price_buckets["200k_500k"] += 1
        else:
            price_buckets["over_500k"] += 1

    return FacetCounts(
        condition=[FacetBucket(value=k, count=v) for k, v in condition_counts.items()],
        availability=[FacetBucket(value=k, count=v) for k, v in availability_counts.items()],
        rating=[FacetBucket(value=k, count=v) for k, v in rating_counts.items()],
        price=[FacetBucket(value=k, count=v) for k, v in price_buckets.items()],
    )


def _sort_candidates(
    candidates: list[_CatalogCandidate],
    *,
    sort: CatalogSort,
    lat: float | None,
    lng: float | None,
) -> list[_CatalogCandidate]:
    if sort == "cheapest":
        return sorted(
            candidates,
            key=lambda row: (row.search_doc.price_min_ngwee or 0, row.search_doc.title),
        )

    if sort == "newest":
        return sorted(
            candidates,
            key=lambda row: (row.listing.created_at or "", row.search_doc.title),
            reverse=True,
        )

    if sort == "nearest":
        if lat is None or lng is None:
            raise AppError(
                "location_required",
                "lat and lng are required for nearest sort",
                400,
            )

        enriched: list[_CatalogCandidate] = []
        for candidate in candidates:
            if candidate.search_doc.lat is None or candidate.search_doc.lng is None:
                distance_m = None
            else:
                distance_m = haversine_m(
                    lat,
                    lng,
                    candidate.search_doc.lat,
                    candidate.search_doc.lng,
                )
            enriched.append(candidate.model_copy(update={"distance_m": distance_m}))

        return sorted(
            enriched,
            key=lambda row: (
                row.distance_m is None,
                row.distance_m if row.distance_m is not None else math.inf,
                row.search_doc.title,
            ),
        )

    return sorted(
        candidates,
        key=lambda row: (
            _relevance_score(row.search_doc.boost_signals, row.search_doc.updated_at),
            row.search_doc.title,
        ),
        reverse=True,
    )


class _WholesaleRow(BaseModel):
    id: str
    vendor_id: str
    product_id: str | None = None
    title_override: str | None = None
    condition: str = "new"
    price_ngwee: int
    moq: int = 1
    price_tiers: list[dict[str, Any]] | None = None


def _fetch_wholesale_listings(client: Any, limit: int) -> list[_WholesaleRow]:
    response = (
        client.table("vendor_listings")
        .select(
            "id, vendor_id, product_id, title_override, condition, "
            "price_ngwee, moq, price_tiers, status, wholesale"
        )
        .eq("status", "active")
        .eq("wholesale", True)
        .limit(limit)
        .execute()
    )
    rows = _response_rows(response)
    return [_WholesaleRow.model_validate(row) for row in rows]


def list_wholesale_supplies(client: Any, *, limit: int) -> CatalogListResponse:
    """Wholesale/supplies feed. Callers MUST gate this behind verified-business access;
    the endpoint enforces that, this function assumes it and returns B2B pricing."""
    listings = _fetch_wholesale_listings(client, limit)
    vendor_ids = sorted({row.vendor_id for row in listings})
    product_ids = sorted({row.product_id for row in listings if row.product_id is not None})
    vendors = _fetch_vendors(client, vendor_ids)
    products = _fetch_products(client, product_ids)
    images = _fetch_images(client, [row.id for row in listings])

    items: list[CatalogListingItem] = []
    for row in listings:
        vendor = vendors.get(row.vendor_id)
        if vendor is None:
            continue  # vendor storefront not active
        product = products.get(row.product_id) if row.product_id else None
        title = str(product["name"]) if product else (row.title_override or "")
        items.append(
            CatalogListingItem(
                id=row.id,
                title=title,
                product_slug=str(product["slug"]) if product else None,
                vendor_name=str(vendor["display_name"]),
                vendor_slug=str(vendor.get("slug")) if vendor.get("slug") else None,
                price_ngwee=row.price_ngwee,
                condition=row.condition,
                in_stock=True,
                image_public_id=images.get(row.id),
                wholesale=True,
                moq=row.moq,
                price_tiers=row.price_tiers,
            )
        )

    return CatalogListResponse(
        items=items,
        facets=FacetCounts(),
        total=len(items),
        next_cursor=None,
    )


def list_catalog(
    client: Any,
    filters: PlpFilterState,
    *,
    include_wholesale: bool = False,
    exclude_demo: bool = False,
) -> CatalogListResponse:
    candidates = _build_candidates(client, filters.category_path)
    if not include_wholesale:
        # Wholesale-only listings are B2B supplies: hidden from the consumer PLP
        # (and its facet counts) unless the caller is a verified business buyer.
        candidates = [row for row in candidates if not row.listing.wholesale]
    if exclude_demo:
        # FD-04 / G11: once `public_launch` is ON the demo-seeded catalogue must
        # not surface on public browse; during invite-only beta it stays visible
        # with the honest demo label.
        candidates = [row for row in candidates if not row.listing.demo]
    facets = compute_facet_counts(candidates, filters)

    filtered = [row for row in candidates if _matches_filters(row, filters=filters)]
    sorted_rows = _sort_candidates(
        filtered,
        sort=filters.sort,
        lat=filters.lat,
        lng=filters.lng,
    )

    total = len(sorted_rows)
    start = filters.cursor
    end = start + filters.limit
    page_rows = sorted_rows[start:end]

    items = [
        CatalogListingItem(
            id=row.listing.id,
            title=row.search_doc.title,
            product_slug=str(row.product["slug"]) if row.product else None,
            vendor_name=str(row.vendor["display_name"]),
            vendor_slug=str(row.vendor.get("slug")) if row.vendor.get("slug") else None,
            price_ngwee=row.search_doc.price_min_ngwee or 0,
            condition=row.listing.condition,
            in_stock=row.in_stock,
            image_public_id=row.image_public_id,
            rating=row.rating,
            review_count=row.review_count,
            lat=row.search_doc.lat,
            lng=row.search_doc.lng,
            distance_m=row.distance_m,
            landmark=row.landmark,
        )
        for row in page_rows
    ]

    next_cursor = encode_plp_cursor(end) if end < total else None
    return CatalogListResponse(items=items, facets=facets, total=total, next_cursor=next_cursor)


@router.get("/listings", response_model=CatalogListResponse)
async def catalog_listings(
    supabase: Annotated[Any, Depends(get_supabase_client)],
    access: Annotated[BusinessAccess, Depends(get_business_access)],
    category_path: Annotated[str | None, Query(max_length=200)] = None,
    sort: Annotated[CatalogSort, Query()] = "relevance",
    wholesale: Annotated[bool, Query()] = False,
    min_price: Annotated[int | None, Query(ge=0, alias="min_price")] = None,
    max_price: Annotated[int | None, Query(ge=0, alias="max_price")] = None,
    condition: Annotated[str | None, Query(max_length=40)] = None,
    availability: Annotated[str | None, Query(max_length=40)] = None,
    min_rating: Annotated[int | None, Query(ge=1, le=5)] = None,
    lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    lng: Annotated[float | None, Query(ge=-180, le=180)] = None,
    radius_km: Annotated[float | None, Query(gt=0, le=500)] = None,
    cursor: Annotated[str | None, Query(max_length=32)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> CatalogListResponse:
    if wholesale:
        # B2B supplies feed: hidden from consumers/guests — verified businesses only.
        require_wholesale_access(access)
        return list_wholesale_supplies(supabase.client, limit=limit)

    raw_params: dict[str, str | list[str] | None] = {
        "category_path": category_path,
        "sort": sort,
        "min_price": str(min_price) if min_price is not None else None,
        "max_price": str(max_price) if max_price is not None else None,
        "condition": condition,
        "availability": availability,
        "min_rating": str(min_rating) if min_rating is not None else None,
        "lat": str(lat) if lat is not None else None,
        "lng": str(lng) if lng is not None else None,
        "radius_km": str(radius_km) if radius_km is not None else None,
        "cursor": cursor,
        "limit": str(limit),
    }
    filters = decode_plp_filters(raw_params)
    return list_catalog(
        supabase.client,
        filters,
        include_wholesale=access.eligible,
        exclude_demo=is_public_launch(supabase.client),
    )
