from __future__ import annotations

import math
import re
from typing import Annotated, Any, Literal, Protocol, cast

from app.deps import get_supabase_client
from app.errors import AppError
from app.services.business.access import BusinessAccess, get_business_access
from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/directory", tags=["directory"])

DEFAULT_PAGE_SIZE = 24
MAX_PAGE_SIZE = 48
EARTH_RADIUS_M = 6_371_000

DirectoryBadge = Literal["preferred", "verified"]


class _ServiceClient(Protocol):
    @property
    def client(self) -> Any: ...


class FacetBucket(BaseModel):
    value: str
    count: int


class DirectoryFacets(BaseModel):
    categories: list[FacetBucket] = Field(default_factory=list)
    locations: list[FacetBucket] = Field(default_factory=list)
    badges: list[FacetBucket] = Field(default_factory=list)


class DirectoryVendorItem(BaseModel):
    id: str
    slug: str
    display_name: str
    description: str | None = None
    logo_url: str | None = None
    preferred_badge: bool = False
    kyc_tier: int | None = None
    verified: bool = False
    landmark: str | None = None
    lat: float | None = None
    lng: float | None = None
    categories: list[str] = Field(default_factory=list)
    rating_avg: float | None = None
    rating_count: int = 0
    listing_count: int = 0


class DirectoryListResponse(BaseModel):
    items: list[DirectoryVendorItem]
    facets: DirectoryFacets
    total: int
    page: int
    page_size: int


class VendorLocationDetail(BaseModel):
    landmark: str
    lat: float
    lng: float
    hours: dict[str, Any] = Field(default_factory=dict)


class DirectoryListingItem(BaseModel):
    id: str
    title: str
    product_slug: str | None = None
    price_ngwee: int
    condition: str
    in_stock: bool
    image_public_id: str | None = None


class ReviewsSummary(BaseModel):
    rating_avg: float | None = None
    rating_count: int = 0


class VendorProfileDetail(BaseModel):
    id: str
    slug: str
    display_name: str
    description: str | None = None
    logo_url: str | None = None
    preferred_badge: bool = False
    kyc_tier: int | None = None
    verified: bool = False
    location: VendorLocationDetail | None = None
    created_at: str | None = None


class VendorProfileResponse(BaseModel):
    vendor: VendorProfileDetail
    listings: list[DirectoryListingItem] = Field(default_factory=list)
    reviews_summary: ReviewsSummary


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


def _is_verified(kyc_tier: int | None, preferred_badge: bool) -> bool:
    return bool(preferred_badge or (kyc_tier is not None and kyc_tier >= 2))


def _sanitize_query(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"[%_\\]", "", value.strip())
    return cleaned or None


def _parse_badges(raw: str | None) -> list[DirectoryBadge]:
    if not raw:
        return []
    allowed: set[str] = {"preferred", "verified"}
    badges: list[DirectoryBadge] = []
    for part in raw.split(","):
        token = part.strip().lower()
        if token in allowed and token not in badges:
            badges.append(cast(DirectoryBadge, token))
    return badges


def _first_location(row: dict[str, Any]) -> dict[str, Any] | None:
    locations = row.get("vendor_locations")
    if isinstance(locations, list) and locations:
        first = locations[0]
        if isinstance(first, dict):
            return first
    return None


def _aggregate_vendor_ratings(
    client: Any,
    vendor_ids: list[str],
) -> dict[str, tuple[float | None, int]]:
    if not vendor_ids:
        return {}

    listings_response = (
        client.table("vendor_listings")
        .select("id, vendor_id")
        .in_("vendor_id", vendor_ids)
        .eq("status", "active")
        .execute()
    )
    listing_rows = listings_response.data or []
    listing_ids = [str(row["id"]) for row in listing_rows if row.get("id")]
    listing_vendor = {
        str(row["id"]): str(row["vendor_id"]) for row in listing_rows if row.get("id")
    }

    if not listing_ids:
        return {vendor_id: (None, 0) for vendor_id in vendor_ids}

    order_items_response = (
        client.table("order_item_products")
        .select("order_item_id, listing_id")
        .in_("listing_id", listing_ids)
        .execute()
    )
    order_item_rows = order_items_response.data or []
    order_item_ids = [
        str(row["order_item_id"]) for row in order_item_rows if row.get("order_item_id")
    ]
    order_item_vendor: dict[str, str] = {}
    for row in order_item_rows:
        listing_id = row.get("listing_id")
        order_item_id = row.get("order_item_id")
        if listing_id and order_item_id:
            vendor_id = listing_vendor.get(str(listing_id))
            if vendor_id:
                order_item_vendor[str(order_item_id)] = vendor_id

    if not order_item_ids:
        return {vendor_id: (None, 0) for vendor_id in vendor_ids}

    reviews_response = (
        client.table("reviews")
        .select("order_item_id, rating")
        .in_("order_item_id", order_item_ids)
        .eq("status", "published")
        .execute()
    )
    review_rows = reviews_response.data or []

    totals: dict[str, list[int]] = {vendor_id: [] for vendor_id in vendor_ids}
    for review in review_rows:
        order_item_id = review.get("order_item_id")
        rating = review.get("rating")
        if order_item_id is None or rating is None:
            continue
        vendor_id = order_item_vendor.get(str(order_item_id))
        if vendor_id and vendor_id in totals:
            totals[vendor_id].append(int(rating))

    result: dict[str, tuple[float | None, int]] = {}
    for vendor_id in vendor_ids:
        ratings = totals.get(vendor_id, [])
        if not ratings:
            result[vendor_id] = (None, 0)
        else:
            result[vendor_id] = (round(sum(ratings) / len(ratings), 1), len(ratings))
    return result


def _vendor_category_paths(client: Any, vendor_ids: list[str]) -> dict[str, set[str]]:
    if not vendor_ids:
        return {}

    listings_response = (
        client.table("vendor_listings")
        .select("vendor_id, products(category_id, categories(path))")
        .in_("vendor_id", vendor_ids)
        .eq("status", "active")
        .execute()
    )
    listing_rows = listings_response.data or []

    category_paths: dict[str, set[str]] = {vendor_id: set() for vendor_id in vendor_ids}
    for row in listing_rows:
        vendor_id = str(row.get("vendor_id") or "")
        if vendor_id not in category_paths:
            continue
        product = row.get("products")
        if not isinstance(product, dict):
            continue
        categories = product.get("categories")
        if isinstance(categories, dict):
            path = categories.get("path")
            if isinstance(path, str) and path:
                category_paths[vendor_id].add(path)
    return category_paths


def _vendor_listing_counts(client: Any, vendor_ids: list[str]) -> dict[str, int]:
    if not vendor_ids:
        return {}

    listings_response = (
        client.table("vendor_listings")
        .select("vendor_id")
        .in_("vendor_id", vendor_ids)
        .eq("status", "active")
        .execute()
    )
    counts: dict[str, int] = {vendor_id: 0 for vendor_id in vendor_ids}
    for row in listings_response.data or []:
        vendor_id = str(row.get("vendor_id") or "")
        if vendor_id in counts:
            counts[vendor_id] += 1
    return counts


def _matches_category(category_paths: set[str], category_filter: str) -> bool:
    prefix = category_filter.strip().strip("/")
    if not prefix:
        return True
    return any(path == prefix or path.startswith(f"{prefix}/") for path in category_paths)


def _matches_query(row: dict[str, Any], query: str) -> bool:
    needle = query.casefold()
    display_name = str(row.get("display_name") or "").casefold()
    description = str(row.get("description") or "").casefold()
    return needle in display_name or needle in description


def _matches_location(
    location_row: dict[str, Any] | None,
    *,
    location: str | None,
    lat: float | None,
    lng: float | None,
    radius_km: float | None,
) -> bool:
    if location_row is None:
        return location is None and lat is None and lng is None

    landmark = str(location_row.get("landmark") or "")
    if location:
        if location.casefold() not in landmark.casefold():
            return False

    if lat is not None and lng is not None and radius_km is not None:
        row_lat = location_row.get("lat")
        row_lng = location_row.get("lng")
        if row_lat is None or row_lng is None:
            return False
        distance_m = haversine_m(lat, lng, float(row_lat), float(row_lng))
        if distance_m > radius_km * 1000:
            return False

    return True


def _matches_badges(
    row: dict[str, Any],
    badges: list[DirectoryBadge],
) -> bool:
    if not badges:
        return True
    preferred = bool(row.get("preferred_badge"))
    kyc_tier = row.get("kyc_tier")
    verified = _is_verified(int(kyc_tier) if kyc_tier is not None else None, preferred)
    for badge in badges:
        if badge == "preferred" and not preferred:
            return False
        if badge == "verified" and not verified:
            return False
    return True


def _build_directory_item(
    row: dict[str, Any],
    *,
    location_row: dict[str, Any] | None,
    category_paths: set[str],
    rating_avg: float | None,
    rating_count: int,
    listing_count: int,
) -> DirectoryVendorItem:
    kyc_tier = row.get("kyc_tier")
    preferred_badge = bool(row.get("preferred_badge"))
    parsed_tier = int(kyc_tier) if kyc_tier is not None else None
    top_categories = sorted({path.split("/")[0] for path in category_paths if path})

    return DirectoryVendorItem(
        id=str(row["id"]),
        slug=str(row["slug"]),
        display_name=str(row["display_name"]),
        description=row.get("description"),
        logo_url=row.get("logo_url"),
        preferred_badge=preferred_badge,
        kyc_tier=parsed_tier,
        verified=_is_verified(parsed_tier, preferred_badge),
        landmark=str(location_row.get("landmark")) if location_row else None,
        lat=(
            float(location_row["lat"])
            if location_row and location_row.get("lat") is not None
            else None
        ),
        lng=(
            float(location_row["lng"])
            if location_row and location_row.get("lng") is not None
            else None
        ),
        categories=top_categories,
        rating_avg=rating_avg,
        rating_count=rating_count,
        listing_count=listing_count,
    )


def _compute_facets(items: list[DirectoryVendorItem]) -> DirectoryFacets:
    category_counts: dict[str, int] = {}
    location_counts: dict[str, int] = {}
    badge_counts = {"preferred": 0, "verified": 0}

    for item in items:
        for category in item.categories:
            category_counts[category] = category_counts.get(category, 0) + 1
        if item.landmark:
            location_counts[item.landmark] = location_counts.get(item.landmark, 0) + 1
        if item.preferred_badge:
            badge_counts["preferred"] += 1
        if item.verified:
            badge_counts["verified"] += 1

    return DirectoryFacets(
        categories=[
            FacetBucket(value=value, count=count)
            for value, count in sorted(category_counts.items())
        ],
        locations=[
            FacetBucket(value=value, count=count)
            for value, count in sorted(location_counts.items())
        ],
        badges=[
            FacetBucket(value=value, count=count)
            for value, count in badge_counts.items()
            if count > 0
        ],
    )


def list_directory_vendors(
    client: Any,
    *,
    q: str | None = None,
    category: str | None = None,
    location: str | None = None,
    badges: list[DirectoryBadge] | None = None,
    lat: float | None = None,
    lng: float | None = None,
    radius_km: float | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> DirectoryListResponse:
    vendors_response = (
        client.table("vendors")
        .select(
            "id, slug, display_name, description, logo_url, status, kyc_tier, preferred_badge, "
            "vendor_locations(landmark, lat, lng, hours)"
        )
        .eq("status", "active")
        .order("display_name")
        .execute()
    )
    vendor_rows = vendors_response.data or []
    vendor_ids = [str(row["id"]) for row in vendor_rows if row.get("id")]

    ratings = _aggregate_vendor_ratings(client, vendor_ids)
    category_map = _vendor_category_paths(client, vendor_ids)
    listing_counts = _vendor_listing_counts(client, vendor_ids)

    filtered_items: list[DirectoryVendorItem] = []
    for row in vendor_rows:
        vendor_id = str(row.get("id") or "")
        location_row = _first_location(row)
        category_paths = category_map.get(vendor_id, set())

        if q and not _matches_query(row, q):
            continue
        if category and not _matches_category(category_paths, category):
            continue
        if not _matches_location(
            location_row,
            location=location,
            lat=lat,
            lng=lng,
            radius_km=radius_km,
        ):
            continue
        if not _matches_badges(row, badges or []):
            continue

        rating_avg, rating_count = ratings.get(vendor_id, (None, 0))
        filtered_items.append(
            _build_directory_item(
                row,
                location_row=location_row,
                category_paths=category_paths,
                rating_avg=rating_avg,
                rating_count=rating_count,
                listing_count=listing_counts.get(vendor_id, 0),
            )
        )

    total = len(filtered_items)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = filtered_items[start:end]

    all_items = [
        _build_directory_item(
            row,
            location_row=_first_location(row),
            category_paths=category_map.get(str(row.get("id") or ""), set()),
            rating_avg=ratings.get(str(row.get("id") or ""), (None, 0))[0],
            rating_count=ratings.get(str(row.get("id") or ""), (None, 0))[1],
            listing_count=listing_counts.get(str(row.get("id") or ""), 0),
        )
        for row in vendor_rows
    ]

    return DirectoryListResponse(
        items=page_items,
        facets=_compute_facets(all_items),
        total=total,
        page=page,
        page_size=page_size,
    )


def _listing_title(row: dict[str, Any], product_name: str) -> str:
    override = row.get("title_override")
    if isinstance(override, str) and override.strip():
        return override.strip()
    return product_name


def _is_in_stock(stock_mode: str, stock_qty: int | None) -> bool:
    if stock_mode == "always_available":
        return True
    if stock_mode == "tracked":
        return stock_qty is not None and stock_qty > 0
    return False


def _resolve_previous_slug(client: Any, slug: str) -> str | None:
    """A vendor may change its slug once (M12-P09), which records the old slug in
    ``caps_snapshot.previous_slug``. Map an old slug to the vendor's current slug so
    a stale link 301s instead of 404ing."""
    response = (
        client.table("vendors")
        .select("slug, status, caps_snapshot")
        .eq("caps_snapshot->>previous_slug", slug)
        .eq("status", "active")
        .limit(1)
        .execute()
    )
    data = getattr(response, "data", None)
    if isinstance(data, list) and data and isinstance(data[0], dict):
        current = data[0].get("slug")
        if isinstance(current, str) and current and current != slug:
            return current
    return None


def get_vendor_profile(
    client: Any,
    slug: str,
    *,
    include_wholesale: bool = False,
) -> VendorProfileResponse | RedirectResponse:
    vendor_response = (
        client.table("vendors")
        .select(
            "id, slug, display_name, description, logo_url, status, "
            "kyc_tier, preferred_badge, created_at, "
            "vendor_locations(landmark, lat, lng, hours)"
        )
        .eq("slug", slug)
        .maybe_single()
        .execute()
    )
    row = vendor_response.data
    if not isinstance(row, dict):
        redirect_slug = _resolve_previous_slug(client, slug)
        if redirect_slug:
            return RedirectResponse(url=f"/directory/{redirect_slug}", status_code=301)
        raise AppError("vendor.not_found", "Vendor not found", 404)

    status = str(row.get("status") or "")
    if status != "active":
        raise AppError("vendor.not_found", "Vendor not found", 404)

    vendor_id = str(row["id"])
    location_row = _first_location(row)
    kyc_tier = row.get("kyc_tier")
    parsed_tier = int(kyc_tier) if kyc_tier is not None else None
    preferred_badge = bool(row.get("preferred_badge"))

    location: VendorLocationDetail | None = None
    if location_row is not None:
        hours = location_row.get("hours")
        location = VendorLocationDetail(
            landmark=str(location_row.get("landmark") or ""),
            lat=float(location_row.get("lat") or 0),
            lng=float(location_row.get("lng") or 0),
            hours=hours if isinstance(hours, dict) else {},
        )

    listings_response = (
        client.table("vendor_listings")
        .select(
            "id, title_override, price_ngwee, condition, stock_mode, stock_qty, "
            "status, wholesale, "
            "products(name, slug, status)"
        )
        .eq("vendor_id", vendor_id)
        .eq("status", "active")
        .order("price_ngwee")
        .execute()
    )
    listing_rows = listings_response.data or []
    if not include_wholesale:
        # Wholesale-only listings are B2B supplies: hidden from the vendor's
        # public storefront unless the caller is a verified business buyer.
        listing_rows = [row for row in listing_rows if not row.get("wholesale")]
    listing_ids = [str(item["id"]) for item in listing_rows if item.get("id")]

    images_by_listing: dict[str, str | None] = {listing_id: None for listing_id in listing_ids}
    if listing_ids:
        images_response = (
            client.table("listing_images")
            .select("listing_id, cloudinary_public_id, position")
            .in_("listing_id", listing_ids)
            .order("position")
            .execute()
        )
        for image_row in images_response.data or []:
            listing_id = str(image_row.get("listing_id") or "")
            if listing_id in images_by_listing and images_by_listing[listing_id] is None:
                public_id = image_row.get("cloudinary_public_id")
                if isinstance(public_id, str) and public_id:
                    images_by_listing[listing_id] = public_id

    listings: list[DirectoryListingItem] = []
    for listing_row in listing_rows:
        product = listing_row.get("products")
        if not isinstance(product, dict):
            continue
        if str(product.get("status") or "") != "active":
            continue
        product_name = str(product.get("name") or "Listing")
        product_slug = product.get("slug")
        listings.append(
            DirectoryListingItem(
                id=str(listing_row["id"]),
                title=_listing_title(listing_row, product_name),
                product_slug=str(product_slug) if product_slug else None,
                price_ngwee=int(listing_row.get("price_ngwee") or 0),
                condition=str(listing_row.get("condition") or "new"),
                in_stock=_is_in_stock(
                    str(listing_row.get("stock_mode") or ""),
                    listing_row.get("stock_qty"),
                ),
                image_public_id=images_by_listing.get(str(listing_row["id"])),
            )
        )

    rating_avg, rating_count = _aggregate_vendor_ratings(client, [vendor_id]).get(
        vendor_id, (None, 0)
    )

    return VendorProfileResponse(
        vendor=VendorProfileDetail(
            id=vendor_id,
            slug=str(row["slug"]),
            display_name=str(row["display_name"]),
            description=row.get("description"),
            logo_url=row.get("logo_url"),
            preferred_badge=preferred_badge,
            kyc_tier=parsed_tier,
            verified=_is_verified(parsed_tier, preferred_badge),
            location=location,
            created_at=row.get("created_at"),
        ),
        listings=listings,
        reviews_summary=ReviewsSummary(rating_avg=rating_avg, rating_count=rating_count),
    )


@router.get("", response_model=DirectoryListResponse)
async def list_directory(
    supabase: Annotated[_ServiceClient, Depends(get_supabase_client)],
    q: Annotated[str | None, Query(max_length=200)] = None,
    category: Annotated[str | None, Query(max_length=200)] = None,
    location: Annotated[str | None, Query(max_length=200)] = None,
    badges: Annotated[str | None, Query(max_length=50)] = None,
    lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    lng: Annotated[float | None, Query(ge=-180, le=180)] = None,
    radius_km: Annotated[float | None, Query(gt=0, le=500)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> DirectoryListResponse:
    if (lat is None) ^ (lng is None):
        raise AppError("invalid_location", "Both lat and lng are required for geo filters", 400)
    if radius_km is not None and (lat is None or lng is None):
        raise AppError("invalid_location", "radius_km requires lat and lng", 400)

    return list_directory_vendors(
        supabase.client,
        q=_sanitize_query(q),
        category=_sanitize_query(category),
        location=_sanitize_query(location),
        badges=_parse_badges(badges),
        lat=lat,
        lng=lng,
        radius_km=radius_km,
        page=page,
        page_size=page_size,
    )


@router.get("/{slug}", response_model=VendorProfileResponse)
async def get_directory_vendor(
    slug: str,
    supabase: Annotated[_ServiceClient, Depends(get_supabase_client)],
    access: Annotated[BusinessAccess, Depends(get_business_access)],
) -> VendorProfileResponse | RedirectResponse:
    cleaned = _sanitize_query(slug)
    if not cleaned:
        raise AppError("vendor.not_found", "Vendor not found", 404)
    return get_vendor_profile(supabase.client, cleaned, include_wholesale=access.eligible)
