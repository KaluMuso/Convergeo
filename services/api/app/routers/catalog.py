from __future__ import annotations

import base64
import hashlib
import logging
import math
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from app.core.ttl_cache import get_cached_json, set_cached_json
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.comparison import is_lusaka_delivery_available
from app.schemas.offers import OfferBadgeOut
from app.services.categories.public import list_public_categories
from app.services.db_chunk import POSTGREST_PAGE_SIZE, chunked_in_query
from app.services.listings.availability import is_listing_available
from app.services.listings.demo import fetch_demo_listing_ids
from app.services.signals import ListingSignals
from app.services.signals.loader import (
    facts_for_inputs,
    load_approved_tiers,
    load_made_in_zambia_approved,
)
from app.services.signals.models import SignalFacts, SignalInput
from app.services.signals.rules import parse_timestamp
from app.services.vendor_plans.canonical_photos import load_canonical_images
from app.services.vendor_plans.resolver import shared_photos_enabled
from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/catalog", tags=["catalog"])

DEFAULT_PAGE_SIZE = 24
MAX_PAGE_SIZE = 50
EARTH_RADIUS_M = 6_371_000

CATALOG_CANDIDATES_CACHE_TTL_SECONDS = 45
CATALOG_CANDIDATES_CACHE_PREFIX = "catalog:candidates:v1:"
PUBLIC_CATALOG_LISTINGS_CACHE_CONTROL = (
    "public, s-maxage=30, stale-while-revalidate=120"
)

CatalogSort = Literal[
    "relevance", "cheapest", "nearest", "newest", "price_asc", "verified", "bundle", "best"
]
ConditionFilter = Literal["new", "refurbished", "used"]
AvailabilityFilter = Literal["in_stock", "out_of_stock"]
ProductClass = Literal["A", "B", "C", "D", "E"]
ListingCondition = Literal["new", "refurbished", "used"]
SaleUnit = Literal["each", "metre", "kg", "litre", "bag", "sqm"]
FulfilmentMode = Literal["stocked", "made_to_order"]
StockMode = Literal["tracked", "always_available"]


class FacetBucket(BaseModel):
    value: str
    count: int


class FacetCounts(BaseModel):
    condition: list[FacetBucket] = Field(default_factory=list)
    availability: list[FacetBucket] = Field(default_factory=list)
    rating: list[FacetBucket] = Field(default_factory=list)
    price: list[FacetBucket] = Field(default_factory=list)
    #: Signal filter boxes: ``verified`` / ``deals`` / ``made_in_zambia`` counts
    #: (``made_in_zambia`` omitted until approved claims exist).
    signals: list[FacetBucket] = Field(default_factory=list)


class CatalogListingItem(BaseModel):
    id: str
    title: str
    product_slug: str | None = None
    vendor_name: str
    vendor_slug: str | None = None
    price_ngwee: int
    compare_at_ngwee: int | None = None
    condition: str
    product_class: ProductClass = "A"
    sale_unit: SaleUnit = "each"
    unit_step_milli: int = Field(default=1000, ge=1)
    min_steps: int = Field(default=1, ge=1)
    fulfilment_mode: FulfilmentMode = "stocked"
    lead_time_days: int | None = None
    in_stock: bool
    image_public_id: str | None = None
    rating: float = 0.0
    review_count: int = 0
    lat: float | None = None
    lng: float | None = None
    distance_m: float | None = None
    landmark: str | None = None
    below_median: bool = False
    delivery_available: bool = False
    pickup_available: bool = False
    #: W8 live offer this listing takes part in (flag `bundles`); attached
    #: server-side by surfaces that render cards (home feed, stream).
    offer_badge: OfferBadgeOut | None = None
    #: Badges / ribbon / market facts (docs/plan/product-signals.md); null when unavailable.
    signals: ListingSignals | None = None


class CatalogListResponse(BaseModel):
    items: list[CatalogListingItem]
    facets: FacetCounts
    total: int
    next_cursor: str | None = None


class StandaloneListingVendor(BaseModel):
    id: str
    name: str
    slug: str | None = None


class StandaloneListingLocation(BaseModel):
    landmark: str | None = None
    lat: float | None = None
    lng: float | None = None


class StandaloneListingImage(BaseModel):
    cloudinary_public_id: str
    position: int = Field(ge=1, le=8)


class StandaloneListingResponse(BaseModel):
    """Public detail contract for a listing without a canonical product."""

    id: str
    title: str
    product_class: ProductClass
    condition: ListingCondition
    defect_notes: str | None = None
    price_ngwee: int
    compare_at_ngwee: int | None = None
    sale_unit: SaleUnit
    unit_step_milli: int = Field(ge=1)
    min_steps: int = Field(ge=1)
    fulfilment_mode: FulfilmentMode
    lead_time_days: int | None = None
    vendor_capacity_per_week: int | None = None
    stock_mode: StockMode
    stock_qty: int | None = Field(default=None, ge=0)
    moq: int = Field(default=1, ge=1)
    wholesale: bool = False
    in_stock: bool
    vendor: StandaloneListingVendor
    location: StandaloneListingLocation | None = None
    images: list[StandaloneListingImage] = Field(default_factory=list)


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
    #: Signal filter boxes (all default off; see docs/plan/product-signals.md).
    verified: bool = False
    deals: bool = False
    made_in_zambia: bool = False
    cursor: int = Field(default=0, ge=0)
    limit: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)


# Documented SQL fragments (executed via PostgREST + Python enrichment; bound params only).
FACET_COUNT_SQL = """
WITH scoped AS (
  SELECT sd.entity_id,
         vl.condition,
         CASE
           WHEN (vl.product_class = 'E' OR vl.fulfilment_mode = 'made_to_order')
                AND coalesce(vl.vendor_capacity_per_week, 0) >= greatest(vl.min_steps, vl.moq)
             THEN 'in_stock'
           WHEN vl.stock_mode = 'always_available' THEN 'in_stock'
           WHEN coalesce(vl.stock_qty, 0) >= greatest(vl.min_steps, vl.moq)
             THEN 'in_stock'
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
    product_class: ProductClass = "A"
    sale_unit: SaleUnit = "each"
    unit_step_milli: int = Field(default=1000, ge=1)
    min_steps: int = Field(default=1, ge=1)
    fulfilment_mode: FulfilmentMode = "stocked"
    lead_time_days: int | None = None
    vendor_capacity_per_week: int | None = None
    stock_mode: str
    stock_qty: int | None = None
    moq: int = Field(default=1, ge=1)
    created_at: str | None = None
    wholesale: bool = False
    compare_at_ngwee: int | None = None


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    return EARTH_RADIUS_M * math.acos(
        min(
            1.0,
            max(
                -1.0,
                math.cos(math.radians(lat1))
                * math.cos(math.radians(lat2))
                * math.cos(math.radians(lng2) - math.radians(lng1))
                + math.sin(math.radians(lat1)) * math.sin(math.radians(lat2)),
            ),
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
    if state.verified:
        params["verified"] = "1"
    if state.deals:
        params["deals"] = "1"
    if state.made_in_zambia:
        params["made_in_zambia"] = "1"
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
            if token in ("new", "refurbished", "used"):
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

    def _flag(key: str) -> bool:
        return (_one(key) or "").strip().lower() in ("1", "true", "yes")

    parsed_limit = int(limit_raw) if limit_raw is not None else DEFAULT_PAGE_SIZE
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
        verified=_flag("verified"),
        deals=_flag("deals"),
        made_in_zambia=_flag("made_in_zambia"),
        cursor=decode_plp_cursor(_one("cursor")),
        limit=min(max(parsed_limit, 1), MAX_PAGE_SIZE),
    )


def _relevance_score(boost: dict[str, Any], updated_at: str | None) -> tuple[int, int, str]:
    verified = 1 if boost.get("verified") else 0
    in_stock = 1 if boost.get("in_stock") else 0
    return (verified, in_stock, updated_at or "")


def _response_rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None) or []
    return cast(list[dict[str, Any]], data)


def _search_documents_base_query(client: Any, category_path: str | None) -> Any:
    query = (
        client.table("search_documents")
        .select("entity_id,title,category_path,price_min_ngwee,lat,lng,boost_signals,updated_at")
        .eq("entity_kind", "listing")
        .eq("is_public", True)
    )
    if category_path:
        escaped = category_path.replace("%", r"\%").replace("_", r"\_")
        query = query.like("category_path", f"{escaped}%")
    return query


def _fetch_search_documents(client: Any, category_path: str | None) -> list[_SearchDocRow]:
    all_rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        response = (
            _search_documents_base_query(client, category_path)
            .order("entity_id")
            .range(offset, offset + POSTGREST_PAGE_SIZE - 1)
            .execute()
        )
        batch = _response_rows(response)
        if not batch:
            break
        all_rows.extend(batch)
        if len(batch) < POSTGREST_PAGE_SIZE:
            break
        offset += POSTGREST_PAGE_SIZE
    return [_SearchDocRow.model_validate(row) for row in all_rows]


def _nested_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def _first_image_public_id(images: list[dict[str, Any]]) -> str | None:
    if not images:
        return None
    ordered = sorted(images, key=lambda row: int(row.get("position") or 0))
    for row in ordered:
        public_id = row.get("cloudinary_public_id")
        if isinstance(public_id, str) and public_id:
            return public_id
    return None


def _first_landmark(locations: list[dict[str, Any]]) -> str | None:
    if not locations:
        return None
    ordered = sorted(locations, key=lambda row: str(row.get("created_at") or ""))
    for row in ordered:
        landmark = row.get("landmark")
        if isinstance(landmark, str) and landmark:
            return landmark
    return None


_STANDALONE_LISTING_SELECT = (
    "id,product_id,title_override,price_ngwee,compare_at_ngwee,condition,product_class,"
    "sale_unit,unit_step_milli,min_steps,fulfilment_mode,lead_time_days,"
    "vendor_capacity_per_week,defect_notes,stock_mode,stock_qty,moq,wholesale,status,"
    "vendors!inner("
    "id,slug,display_name,status,vendor_locations(landmark,lat,lng,created_at)"
    "),"
    "listing_images(cloudinary_public_id,position)"
)


def _standalone_listing_not_found() -> AppError:
    # One response for absent and deliberately hidden records prevents callers
    # from enumerating canonical, wholesale-only, demo, or inactive inventory.
    return AppError("listing.not_found", "Listing not found", 404)


def _standalone_listing_in_stock(row: dict[str, Any]) -> bool:
    stock_qty_raw = row.get("stock_qty")
    stock_qty = int(stock_qty_raw) if stock_qty_raw is not None else None
    capacity_raw = row.get("vendor_capacity_per_week")
    capacity = int(capacity_raw) if capacity_raw is not None else None
    return is_listing_available(
        str(row.get("stock_mode") or "tracked"),
        stock_qty,
        min_steps=int(row.get("min_steps") or 1),
        moq=int(row.get("moq") or 1),
        product_class=str(row.get("product_class") or "A"),
        fulfilment_mode=str(row.get("fulfilment_mode") or "stocked"),
        vendor_capacity_per_week=capacity,
    )


def _standalone_listing_location(
    vendor: dict[str, Any],
) -> StandaloneListingLocation | None:
    locations = sorted(
        _nested_rows(vendor.get("vendor_locations")),
        key=lambda row: str(row.get("created_at") or ""),
    )
    if not locations:
        return None

    location = locations[0]
    lat_raw = location.get("lat")
    lng_raw = location.get("lng")
    landmark_raw = location.get("landmark")
    return StandaloneListingLocation(
        landmark=(
            str(landmark_raw).strip()
            if isinstance(landmark_raw, str) and landmark_raw.strip()
            else None
        ),
        lat=float(lat_raw) if lat_raw is not None else None,
        lng=float(lng_raw) if lng_raw is not None else None,
    )


def get_standalone_listing(
    client: Any,
    listing_id: str,
) -> StandaloneListingResponse:
    """Fetch one public standalone listing through the server-only client.

    The service-role client bypasses RLS, so every public visibility predicate
    is repeated here and only an explicit allowlist of public columns is selected.
    """
    response = (
        client.table("vendor_listings")
        .select(_STANDALONE_LISTING_SELECT)
        .eq("id", listing_id)
        .eq("status", "active")
        .eq("vendors.status", "active")
        .limit(1)
        .execute()
    )
    rows = _response_rows(response)
    if not rows:
        raise _standalone_listing_not_found()

    row = rows[0]
    # Canonical-attached inventory belongs on /products/{slug}; keeping this
    # endpoint standalone-only avoids duplicate public detail URLs.
    if row.get("product_id") is not None:
        raise _standalone_listing_not_found()
    if str(row.get("product_class") or "A") not in _customer_released_product_classes(client):
        raise _standalone_listing_not_found()
    if bool(row.get("wholesale")):
        raise _standalone_listing_not_found()
    if listing_id in fetch_demo_listing_ids(client, [listing_id]):
        raise _standalone_listing_not_found()

    vendors = _nested_rows(row.get("vendors"))
    vendor = vendors[0] if vendors else None
    title_raw = row.get("title_override")
    title = title_raw.strip() if isinstance(title_raw, str) else ""
    vendor_name_raw = vendor.get("display_name") if vendor is not None else None
    vendor_name = vendor_name_raw.strip() if isinstance(vendor_name_raw, str) else ""
    if vendor is None or not title or not vendor_name:
        raise _standalone_listing_not_found()

    images: list[StandaloneListingImage] = []
    for image_row in sorted(
        _nested_rows(row.get("listing_images")),
        key=lambda item: int(item.get("position") or 0),
    ):
        public_id = image_row.get("cloudinary_public_id")
        if not isinstance(public_id, str) or not public_id.strip():
            continue
        images.append(
            StandaloneListingImage(
                cloudinary_public_id=public_id.strip(),
                position=int(image_row.get("position") or 1),
            )
        )

    stock_qty_raw = row.get("stock_qty")
    compare_at_raw = row.get("compare_at_ngwee")
    lead_time_raw = row.get("lead_time_days")
    capacity_raw = row.get("vendor_capacity_per_week")
    defect_notes_raw = row.get("defect_notes")
    vendor_slug_raw = vendor.get("slug")
    return StandaloneListingResponse(
        id=str(row["id"]),
        title=title,
        product_class=str(row.get("product_class") or "A"),  # type: ignore[arg-type]
        condition=str(row.get("condition") or "new"),  # type: ignore[arg-type]
        defect_notes=(
            defect_notes_raw.strip()
            if isinstance(defect_notes_raw, str) and defect_notes_raw.strip()
            else None
        ),
        price_ngwee=int(row["price_ngwee"]),
        compare_at_ngwee=int(compare_at_raw) if compare_at_raw is not None else None,
        sale_unit=str(row.get("sale_unit") or "each"),  # type: ignore[arg-type]
        unit_step_milli=int(row.get("unit_step_milli") or 1000),
        min_steps=int(row.get("min_steps") or 1),
        fulfilment_mode=str(  # type: ignore[arg-type]
            row.get("fulfilment_mode") or "stocked"
        ),
        lead_time_days=int(lead_time_raw) if lead_time_raw is not None else None,
        vendor_capacity_per_week=(int(capacity_raw) if capacity_raw is not None else None),
        stock_mode=str(row.get("stock_mode") or "tracked"),  # type: ignore[arg-type]
        stock_qty=int(stock_qty_raw) if stock_qty_raw is not None else None,
        moq=int(row.get("moq") or 1),
        wholesale=bool(row.get("wholesale")),
        in_stock=_standalone_listing_in_stock(row),
        vendor=StandaloneListingVendor(
            id=str(vendor["id"]),
            name=vendor_name,
            slug=(
                str(vendor_slug_raw).strip()
                if isinstance(vendor_slug_raw, str) and vendor_slug_raw.strip()
                else None
            ),
        ),
        location=_standalone_listing_location(vendor),
        images=images,
    )


_LISTING_ENRICHED_SELECT = (
    "id,vendor_id,product_id,condition,product_class,sale_unit,unit_step_milli,min_steps,"
    "fulfilment_mode,lead_time_days,vendor_capacity_per_week,stock_mode,stock_qty,moq,"
    "created_at,status,wholesale,compare_at_ngwee,"
    "vendors!inner(id,slug,display_name,status,kyc_tier,preferred_badge,"
    "vendor_locations(landmark,created_at)),"
    "products(id,slug,name,status),"
    "listing_images(cloudinary_public_id,position)"
)


def _customer_released_product_classes(client: Any) -> set[str]:
    """Return classes intentionally released to customer discovery.

    A failed/missing flag query is not a reason to expose a partially launched
    class.  A and B are the launch contract; C/D/E are opt-in release gates.
    """
    flags = {
        "product_class_c_customer_release",
        "product_class_d_customer_release",
        "product_class_d_operations_approved",
        "product_class_e_customer_release",
    }
    try:
        response = (
            client.table("feature_flags").select("flag,enabled").in_("flag", list(flags)).execute()
        )
        rows = _response_rows(response)
    except Exception:  # pragma: no cover - defensive fail-closed boundary
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


def _fetch_listings_enriched(
    client: Any,
    listing_ids: list[str],
) -> dict[str, dict[str, Any]]:
    """Batch-fetch listings with vendor, product, image, and landmark data embedded."""
    if not listing_ids:
        return {}
    rows = chunked_in_query(
        listing_ids,
        run=lambda chunk: (
            client.table("vendor_listings")
            .select(_LISTING_ENRICHED_SELECT)
            .in_("id", chunk)
            .eq("status", "active")
            .eq("vendors.status", "active")
            .execute()
        ),
    )
    enriched: dict[str, dict[str, Any]] = {}
    for row in rows:
        listing_id = row.get("id")
        if not listing_id:
            continue
        vendors = _nested_rows(row.get("vendors"))
        vendor = vendors[0] if vendors else None
        if vendor is None:
            continue
        vendor_locations = _nested_rows(vendor.get("vendor_locations"))
        products = _nested_rows(row.get("products"))
        product = products[0] if products else None
        # A canonical-attached listing must never fall through to the
        # standalone `/l/{id}` route. If its canonical product is absent or no
        # longer active, omit the listing; only product_id=NULL is standalone.
        if row.get("product_id") is not None:
            if product is None or str(product.get("status") or "") != "active":
                continue
        else:
            title_override = row.get("title_override")
            if not isinstance(title_override, str) or not title_override.strip():
                continue
        images = _nested_rows(row.get("listing_images"))
        enriched[str(listing_id)] = {
            "listing": row,
            "vendor": vendor,
            "product": product,
            "image_public_id": _first_image_public_id(images),
            "landmark": _first_landmark(vendor_locations),
        }
    _fill_canonical_card_images(client, enriched)
    return enriched


def _fill_canonical_card_images(client: Any, enriched: dict[str, dict[str, Any]]) -> None:
    """Cards for attached listings without own photos show the product's photo.

    Zero extra queries in the common case (every card already has an image);
    flag-gated (`shared_canonical_photos`) and fail-soft.
    """
    missing = {
        listing_id: str(bundle["product"]["id"])
        for listing_id, bundle in enriched.items()
        if bundle.get("image_public_id") is None
        and isinstance(bundle.get("product"), dict)
        and bundle["product"].get("id")
    }
    if not missing or not shared_photos_enabled(client):
        return
    try:
        canonical = load_canonical_images(client, missing.values())
    except Exception:
        logger.warning("canonical card photos unavailable", exc_info=True)
        return
    for listing_id, product_id in missing.items():
        photos = canonical.get(product_id)
        if photos:
            enriched[listing_id]["image_public_id"] = photos[0]


def _fetch_listing_ratings(client: Any, listing_ids: list[str]) -> dict[str, tuple[float, int]]:
    if not listing_ids:
        return {}
    oip_rows = chunked_in_query(
        listing_ids,
        run=lambda chunk: (
            client.table("order_item_products")
            .select("listing_id,order_item_id")
            .in_("listing_id", chunk)
            .execute()
        ),
    )
    if not oip_rows:
        return {}

    order_item_ids = [str(row["order_item_id"]) for row in oip_rows]
    review_rows = chunked_in_query(
        order_item_ids,
        run=lambda chunk: (
            client.table("reviews")
            .select("order_item_id,rating")
            .in_("order_item_id", chunk)
            .eq("status", "published")
            .execute()
        ),
    )
    rating_by_order_item = {
        str(row["order_item_id"]): int(row["rating"]) for row in review_rows
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
    #: Highest approved KYC tier (kyc_records), never the bare ``vendors.kyc_tier``.
    vendor_tier: int | None = None
    made_in_zambia: bool = False


CatalogCandidate = _CatalogCandidate


def _candidate_verified(candidate: _CatalogCandidate) -> bool:
    return bool(candidate.vendor.get("preferred_badge")) or candidate.vendor_tier is not None


def _candidate_is_deal(candidate: _CatalogCandidate) -> bool:
    from app.services.signals.rules import deal_percent

    return (
        deal_percent(
            candidate.search_doc.price_min_ngwee or 0,
            candidate.listing.compare_at_ngwee,
            in_stock=candidate.in_stock,
        )
        is not None
    )


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

    if "verified" not in ignore and filters.verified and not _candidate_verified(candidate):
        return False

    if "deals" not in ignore and filters.deals and not _candidate_is_deal(candidate):
        return False

    if "made_in_zambia" not in ignore and filters.made_in_zambia and not candidate.made_in_zambia:
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
    # D25 / VC-P06: drop demo seed listings before facets / pagination / totals.
    demo_listing_ids = fetch_demo_listing_ids(client, listing_ids)
    if demo_listing_ids:
        search_docs = [doc for doc in search_docs if doc.entity_id not in demo_listing_ids]
        listing_ids = [doc.entity_id for doc in search_docs]
    enriched = _fetch_listings_enriched(client, listing_ids)
    ratings = _fetch_listing_ratings(client, listing_ids)
    released_classes = _customer_released_product_classes(client)
    vendor_tiers = load_approved_tiers(
        client,
        [str(b["vendor"]["id"]) for b in enriched.values() if b.get("vendor", {}).get("id")],
    )
    miz_listing_ids = load_made_in_zambia_approved(client, list(enriched))

    candidates: list[_CatalogCandidate] = []
    for doc in search_docs:
        bundle = enriched.get(doc.entity_id)
        if bundle is None:
            continue
        listing_row = bundle["listing"]
        vendor = bundle["vendor"]
        product = bundle.get("product")
        listing = _ListingRow.model_validate(listing_row)
        if listing.product_class not in released_classes:
            continue
        rating, review_count = ratings.get(doc.entity_id, (0.0, 0))
        in_stock = is_listing_available(
            listing.stock_mode,
            listing.stock_qty,
            min_steps=listing.min_steps,
            moq=listing.moq,
            product_class=listing.product_class,
            fulfilment_mode=listing.fulfilment_mode,
            vendor_capacity_per_week=listing.vendor_capacity_per_week,
        )
        candidates.append(
            _CatalogCandidate(
                search_doc=doc,
                listing=listing,
                vendor=vendor,
                product=product,
                image_public_id=bundle.get("image_public_id"),
                landmark=bundle.get("landmark"),
                rating=rating,
                review_count=review_count,
                in_stock=in_stock,
                vendor_tier=vendor_tiers.get(str(vendor.get("id"))),
                made_in_zambia=doc.entity_id in miz_listing_ids,
            )
        )
    return candidates


def _is_cacheable_category_path(client: Any, category_path: str | None) -> bool:
    if category_path is None:
        return True
    normalized = category_path.strip().strip("/")
    if not normalized:
        return True
    try:
        categories = list_public_categories(client, use_cache=True)
    except Exception:
        logger.warning("catalog_category_lookup_failed", exc_info=True)
        return False
    for category in categories:
        path = category.path.strip("/")
        if (
            path == normalized
            or path.startswith(f"{normalized}/")
            or normalized.startswith(f"{path}/")
        ):
            return True
    return False


def _catalog_candidates_cache_key(client: Any, category_path: str | None) -> str | None:
    if not _is_cacheable_category_path(client, category_path):
        return None
    normalized = (category_path or "__all__").strip().strip("/") or "__all__"
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]
    return f"{CATALOG_CANDIDATES_CACHE_PREFIX}{digest}"


def _build_candidates_cached(client: Any, category_path: str | None) -> list[_CatalogCandidate]:
    cache_key = _catalog_candidates_cache_key(client, category_path)
    cached = get_cached_json(cache_key) if cache_key else None
    if isinstance(cached, list):
        restored: list[_CatalogCandidate] = []
        try:
            for item in cached:
                if isinstance(item, dict):
                    restored.append(_CatalogCandidate.model_validate(item))
            if restored or cached == []:
                return restored
        except Exception:
            logger.warning("catalog_candidates_cache_invalid", exc_info=True)

    built = _build_candidates(client, category_path)
    if cache_key:
        try:
            payload = [row.model_dump(mode="json") for row in built]
            set_cached_json(cache_key, payload, ttl_seconds=CATALOG_CANDIDATES_CACHE_TTL_SECONDS)
        except Exception:
            logger.warning("catalog_candidates_cache_set_failed", exc_info=True)
    return built


def compute_facet_counts(
    candidates: list[_CatalogCandidate],
    filters: PlpFilterState,
) -> FacetCounts:
    condition_counts: dict[str, int] = {"new": 0, "refurbished": 0, "used": 0}
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

    signal_counts = {"verified": 0, "deals": 0, "made_in_zambia": 0}
    for key, check in (
        ("verified", _candidate_verified),
        ("deals", _candidate_is_deal),
        ("made_in_zambia", lambda c: c.made_in_zambia),
    ):
        for candidate in candidates:
            if _matches_filters(candidate, filters=filters, ignore={key}) and check(candidate):
                signal_counts[key] += 1
    signal_buckets = [
        FacetBucket(value=k, count=v)
        for k, v in signal_counts.items()
        # Made in Zambia is hidden entirely until at least one approved claim exists.
        if k != "made_in_zambia" or v > 0 or filters.made_in_zambia
    ]

    return FacetCounts(
        signals=signal_buckets,
        condition=[FacetBucket(value=k, count=v) for k, v in condition_counts.items()],
        availability=[FacetBucket(value=k, count=v) for k, v in availability_counts.items()],
        rating=[FacetBucket(value=k, count=v) for k, v in rating_counts.items()],
        price=[FacetBucket(value=k, count=v) for k, v in price_buckets.items()],
    )


def is_bundle_candidate(row: _CatalogCandidate) -> bool:
    listing = row.listing
    return (
        bool(listing.wholesale)
        or listing.moq > 1
        or listing.min_steps > 1
        or listing.sale_unit != "each"
    )


def best_score(row: _CatalogCandidate) -> tuple[float, int, int, str]:
    """Relevance/rating blend: Bayesian-damped rating + trust + stock signals.

    ``(rating * reviews + 3.5 * 5) / (reviews + 5)`` keeps one 5-star review from
    outranking an established 4.6 — no floats ever touch money here.
    """
    damped = (row.rating * row.review_count + 3.5 * 5) / (row.review_count + 5)
    boost = row.search_doc.boost_signals
    trust = (1 if boost.get("verified") else 0) + (1 if row.vendor.get("preferred_badge") else 0)
    return (round(damped, 4), trust, 1 if row.in_stock else 0, row.search_doc.updated_at or "")


def _sort_candidates(
    candidates: list[_CatalogCandidate],
    *,
    sort: CatalogSort,
    lat: float | None,
    lng: float | None,
) -> list[_CatalogCandidate]:
    if sort in ("cheapest", "price_asc"):
        return sorted(
            candidates,
            key=lambda row: (row.search_doc.price_min_ngwee or 0, row.search_doc.title),
        )

    if sort == "verified":
        # Preferred badge, then KYC tier, then the regular relevance order.
        return sorted(
            candidates,
            key=lambda row: (
                1 if row.vendor.get("preferred_badge") else 0,
                int(row.vendor.get("kyc_tier") or 0),
                _relevance_score(row.search_doc.boost_signals, row.search_doc.updated_at),
                row.search_doc.title,
            ),
            reverse=True,
        )

    if sort == "bundle":
        # Multi-unit / pack listings (MOQ or min steps > 1, non-"each" units) first,
        # cheapest within each group.
        return sorted(
            candidates,
            key=lambda row: (
                0 if is_bundle_candidate(row) else 1,
                row.search_doc.price_min_ngwee or 0,
                row.search_doc.title,
            ),
        )

    if sort == "best":
        return sorted(candidates, key=best_score, reverse=True)

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


def _with_distance(
    candidate: _CatalogCandidate,
    *,
    lat: float | None,
    lng: float | None,
) -> _CatalogCandidate:
    if candidate.distance_m is not None or lat is None or lng is None:
        return candidate
    if candidate.search_doc.lat is None or candidate.search_doc.lng is None:
        return candidate
    return candidate.model_copy(
        update={
            "distance_m": haversine_m(
                lat,
                lng,
                candidate.search_doc.lat,
                candidate.search_doc.lng,
            )
        }
    )


def _listing_logistics_fields(
    candidate: _CatalogCandidate,
) -> dict[str, bool]:
    lat = candidate.search_doc.lat
    lng = candidate.search_doc.lng
    boost = candidate.search_doc.boost_signals
    return {
        "below_median": bool(boost.get("below_median")),
        "delivery_available": is_lusaka_delivery_available(lat, lng),
        "pickup_available": lat is not None and lng is not None,
    }


def catalog_item_from_candidate(row: _CatalogCandidate) -> CatalogListingItem:
    """Project an enriched catalogue candidate onto the public wire item."""
    logistics = _listing_logistics_fields(row)
    vendor = row.vendor if isinstance(row.vendor, dict) else {}
    display_name = vendor.get("display_name")
    vendor_slug_raw = vendor.get("slug")
    return CatalogListingItem(
        id=row.listing.id,
        title=row.search_doc.title,
        product_slug=str(row.product["slug"]) if row.product else None,
        vendor_name=str(display_name).strip() if display_name else "Seller",
        vendor_slug=str(vendor_slug_raw).strip() if vendor_slug_raw else None,
        price_ngwee=row.search_doc.price_min_ngwee or 0,
        compare_at_ngwee=row.listing.compare_at_ngwee,
        condition=row.listing.condition,
        product_class=row.listing.product_class,
        sale_unit=row.listing.sale_unit,
        unit_step_milli=row.listing.unit_step_milli,
        min_steps=row.listing.min_steps,
        fulfilment_mode=row.listing.fulfilment_mode,
        lead_time_days=row.listing.lead_time_days,
        in_stock=row.in_stock,
        image_public_id=row.image_public_id,
        rating=row.rating,
        review_count=row.review_count,
        lat=row.search_doc.lat,
        lng=row.search_doc.lng,
        distance_m=row.distance_m,
        landmark=row.landmark,
        below_median=logistics["below_median"],
        delivery_available=logistics["delivery_available"],
        pickup_available=logistics["pickup_available"],
    )


def build_catalog_candidates(
    client: Any,
    category_path: str | None = None,
) -> list[_CatalogCandidate]:
    """Public seam for discovery surfaces (home feed, recommendations)."""
    candidates = _build_candidates_cached(client, category_path)
    return [row for row in candidates if not row.listing.wholesale]


def signal_input_from_candidate(row: _CatalogCandidate) -> SignalInput:
    logistics = _listing_logistics_fields(row)
    return SignalInput(
        listing_id=row.listing.id,
        product_id=row.listing.product_id,
        vendor_id=row.listing.vendor_id,
        price_ngwee=row.search_doc.price_min_ngwee or 0,
        compare_at_ngwee=row.listing.compare_at_ngwee,
        in_stock=row.in_stock,
        stock_mode=row.listing.stock_mode,
        stock_qty=row.listing.stock_qty,
        fulfilment_mode=row.listing.fulfilment_mode,
        lead_time_days=row.listing.lead_time_days,
        created_at=parse_timestamp(row.listing.created_at),
        rating=row.rating,
        review_count=row.review_count,
        lat=row.search_doc.lat,
        lng=row.search_doc.lng,
        delivery_available=logistics["delivery_available"],
        vendor_preferred=bool(row.vendor.get("preferred_badge")),
        vendor_tier=row.vendor_tier,
        made_in_zambia=row.made_in_zambia,
    )


def candidate_signal_facts(
    client: Any,
    rows: list[_CatalogCandidate],
    *,
    lat: float | None = None,
    lng: float | None = None,
) -> dict[str, SignalFacts]:
    """Fail-soft signal facts for catalogue candidates (zero listing re-reads)."""
    try:
        return facts_for_inputs(
            client,
            [signal_input_from_candidate(r) for r in rows],
            user_lat=lat,
            user_lng=lng,
        )
    except Exception:
        logger.warning("catalog_signals_failed", exc_info=True)
        return {}


def _attach_candidate_signals(
    client: Any,
    rows: list[_CatalogCandidate],
    items: list[CatalogListingItem],
    filters: PlpFilterState,
) -> None:
    facts = candidate_signal_facts(client, rows, lat=filters.lat, lng=filters.lng)
    for item in items:
        fact = facts.get(item.id)
        item.signals = fact.to_wire() if fact is not None else None


def list_catalog(
    client: Any,
    filters: PlpFilterState,
) -> CatalogListResponse:
    candidates = _build_candidates_cached(client, filters.category_path)
    # Wholesale prices live only in the vendor app: wholesale listings never
    # appear in the customer PLP or its facet counts, for any caller.
    candidates = [row for row in candidates if not row.listing.wholesale]
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
    if filters.lat is not None and filters.lng is not None:
        page_rows = [_with_distance(row, lat=filters.lat, lng=filters.lng) for row in page_rows]

    items = [catalog_item_from_candidate(row) for row in page_rows]
    _attach_candidate_signals(client, page_rows, items, filters)

    next_cursor = encode_plp_cursor(end) if end < total else None
    return CatalogListResponse(items=items, facets=facets, total=total, next_cursor=next_cursor)


@router.get("/listings", response_model=CatalogListResponse)
async def catalog_listings(
    request: Request,
    response: Response,
    supabase: Annotated[Any, Depends(get_supabase_client)],
    category_path: Annotated[str | None, Query(max_length=200)] = None,
    sort: Annotated[CatalogSort, Query()] = "relevance",
    min_price: Annotated[int | None, Query(ge=0, alias="min_price")] = None,
    max_price: Annotated[int | None, Query(ge=0, alias="max_price")] = None,
    condition: Annotated[str | None, Query(max_length=40)] = None,
    availability: Annotated[str | None, Query(max_length=40)] = None,
    min_rating: Annotated[int | None, Query(ge=1, le=5)] = None,
    lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    lng: Annotated[float | None, Query(ge=-180, le=180)] = None,
    radius_km: Annotated[float | None, Query(gt=0, le=500)] = None,
    verified: Annotated[bool, Query()] = False,
    deals: Annotated[bool, Query()] = False,
    made_in_zambia: Annotated[bool, Query()] = False,
    cursor: Annotated[str | None, Query(max_length=32)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> CatalogListResponse:
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
        "verified": "1" if verified else None,
        "deals": "1" if deals else None,
        "made_in_zambia": "1" if made_in_zambia else None,
        "cursor": cursor,
        "limit": str(limit),
    }
    filters = decode_plp_filters(raw_params)
    payload = list_catalog(supabase.client, filters)
    response.headers["Vary"] = "Authorization"
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        response.headers["Cache-Control"] = "private, no-store"
    else:
        response.headers["Cache-Control"] = PUBLIC_CATALOG_LISTINGS_CACHE_CONTROL
    return payload


@router.get("/listings/{listing_id}", response_model=StandaloneListingResponse)
async def catalog_listing_detail(
    listing_id: UUID,
    supabase: Annotated[Any, Depends(get_supabase_client)],
) -> StandaloneListingResponse:
    return get_standalone_listing(supabase.client, str(listing_id))
