from __future__ import annotations

import math
from typing import Annotated, Any, Protocol

from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.products import _aggregate_vendor_ratings, _parse_vendor_row
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

router = APIRouter(prefix="/products", tags=["comparison"])

EARTH_RADIUS_M = 6_371_000
LUSAKA_DELIVERY_RADIUS_M = 35_000

# Documented SQL (executed via PostgREST; bound params only).
# Hot path: active listings for a canonical product_id — uses partial index
# vendor_listings_product_id_active_idx (product_id) WHERE status = 'active'.
COMPARISON_LISTINGS_SQL = """
-- vendor_listings_product_id_active_idx: product_id partial index for active listings
SELECT
  vl.id,
  vl.price_ngwee,
  vl.condition,
  v.id AS vendor_id,
  v.slug AS vendor_slug,
  v.display_name,
  v.preferred_badge,
  vl_loc.landmark,
  vl_loc.lat,
  vl_loc.lng
FROM public.vendor_listings vl
JOIN public.vendors v
  ON v.id = vl.vendor_id
 AND v.status = 'active'
LEFT JOIN LATERAL (
  SELECT landmark, lat, lng
  FROM public.vendor_locations
  WHERE vendor_id = v.id
  ORDER BY created_at
  LIMIT 1
) vl_loc ON true
WHERE vl.product_id = $1::uuid
  AND vl.status = 'active'
ORDER BY vl.price_ngwee ASC, vl.id ASC;
"""


class _ServiceClient(Protocol):
    """Structural type for the service-role client provided by get_supabase_client."""

    @property
    def client(self) -> Any: ...


class ComparisonVendorResponse(BaseModel):
    id: str
    slug: str
    display_name: str
    preferred_badge: bool
    rating_avg: float | None = None
    rating_count: int = 0
    lat: float | None = None
    lng: float | None = None
    landmark: str | None = None


class ComparisonListingItem(BaseModel):
    id: str
    price_ngwee: int
    condition: str
    vendor: ComparisonVendorResponse
    delivery_available: bool
    pickup_available: bool


class ComparisonResponse(BaseModel):
    product_id: str
    product_slug: str
    listing_count: int
    listings: list[ComparisonListingItem] = Field(default_factory=list)


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return EARTH_RADIUS_M * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def is_lusaka_delivery_available(lat: float | None, lng: float | None) -> bool:
    if lat is None or lng is None:
        return False
    # Lusaka CBD fallback reference for metro delivery eligibility (D16).
    return haversine_m(lat, lng, -15.4167, 28.2833) <= LUSAKA_DELIVERY_RADIUS_M


def _fetch_product_by_slug(client: Any, slug: str) -> dict[str, Any] | None:
    response = (
        client.table("products")
        .select("id, slug, status, merged_into_id")
        .eq("slug", slug)
        .maybe_single()
        .execute()
    )
    row = response.data
    return row if isinstance(row, dict) else None


def build_comparison(client: Any, slug: str) -> ComparisonResponse:
    product = _fetch_product_by_slug(client, slug)
    if product is None:
        raise AppError("product.not_found", "Product not found", 404)

    status = str(product.get("status") or "")
    if status != "active":
        raise AppError("product.not_found", "Product not found", 404)

    product_id = str(product["id"])

    listings_response = (
        client.table("vendor_listings")
        .select(
            "id, price_ngwee, condition, "
            "vendors!inner("
            "id, slug, display_name, preferred_badge, status, "
            "vendor_locations(landmark, lat, lng)"
            ")"
        )
        .eq("product_id", product_id)
        .eq("status", "active")
        .eq("vendors.status", "active")
        .order("price_ngwee")
        .order("id")
        .execute()
    )
    listing_rows = listings_response.data or []

    vendor_ids: list[str] = []
    for row in listing_rows:
        vendor = row.get("vendors")
        if isinstance(vendor, dict) and vendor.get("id"):
            vendor_ids.append(str(vendor["id"]))
    vendor_ratings = _aggregate_vendor_ratings(client, list(dict.fromkeys(vendor_ids)))

    listings: list[ComparisonListingItem] = []
    for row in listing_rows:
        vendor_raw = row.get("vendors")
        if not isinstance(vendor_raw, dict):
            continue

        vendor_id = str(vendor_raw["id"])
        rating_avg, rating_count = vendor_ratings.get(vendor_id, (None, 0))
        vendor_summary = _parse_vendor_row(
            vendor_raw,
            rating_avg=rating_avg,
            rating_count=rating_count,
        )

        lat = vendor_summary.location.lat if vendor_summary.location else None
        lng = vendor_summary.location.lng if vendor_summary.location else None
        landmark = vendor_summary.location.landmark if vendor_summary.location else None
        pickup_available = lat is not None and lng is not None

        listings.append(
            ComparisonListingItem(
                id=str(row["id"]),
                price_ngwee=int(row["price_ngwee"]),
                condition=str(row.get("condition") or "new"),
                vendor=ComparisonVendorResponse(
                    id=vendor_summary.id,
                    slug=vendor_summary.slug,
                    display_name=vendor_summary.display_name,
                    preferred_badge=vendor_summary.preferred_badge,
                    rating_avg=vendor_summary.rating_avg,
                    rating_count=vendor_summary.rating_count,
                    lat=lat,
                    lng=lng,
                    landmark=landmark or None,
                ),
                delivery_available=is_lusaka_delivery_available(lat, lng),
                pickup_available=pickup_available,
            )
        )

    return ComparisonResponse(
        product_id=product_id,
        product_slug=str(product["slug"]),
        listing_count=len(listings),
        listings=listings,
    )


@router.get("/{slug}/comparison", response_model=ComparisonResponse)
async def get_product_comparison(
    slug: str,
    supabase: Annotated[_ServiceClient, Depends(get_supabase_client)],
) -> ComparisonResponse:
    return build_comparison(supabase.client, slug)
