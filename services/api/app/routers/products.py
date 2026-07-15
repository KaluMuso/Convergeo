from __future__ import annotations

from typing import Annotated, Any, Protocol

from app.deps import get_supabase_client
from app.errors import AppError
from app.services.business.access import BusinessAccess, get_business_access
from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/products", tags=["products"])


class _ServiceClient(Protocol):
    """Structural type for the service-role client provided by get_supabase_client.

    Declared locally so this module stays outside the service-role import
    allowlist (get_supabase_client / app.deps owns that import).
    """

    @property
    def client(self) -> Any: ...


MAX_GALLERY_IMAGES = 8


class ProductImageResponse(BaseModel):
    public_id: str
    position: int
    listing_id: str


class VendorLocationResponse(BaseModel):
    landmark: str
    lat: float
    lng: float


class VendorSummaryResponse(BaseModel):
    id: str
    slug: str
    display_name: str
    preferred_badge: bool
    rating_avg: float | None = None
    rating_count: int = 0
    location: VendorLocationResponse | None = None


class ListingResponse(BaseModel):
    id: str
    title: str
    price_ngwee: int
    condition: str
    stock_mode: str
    stock_qty: int | None = None
    moq: int = 1
    wholesale: bool = False
    in_stock: bool
    vendor: VendorSummaryResponse
    images: list[ProductImageResponse] = Field(default_factory=list)


class ProductDetailResponse(BaseModel):
    id: str
    name: str
    slug: str
    brand: str | None = None
    spec: dict[str, Any] = Field(default_factory=dict)
    category_id: str
    images: list[ProductImageResponse] = Field(default_factory=list)
    listings: list[ListingResponse] = Field(default_factory=list)
    listing_count: int = 0


def _parse_spec(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


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


def _parse_vendor_row(
    row: dict[str, Any],
    *,
    rating_avg: float | None,
    rating_count: int,
) -> VendorSummaryResponse:
    locations = row.get("vendor_locations")
    location_row: dict[str, Any] | None = None
    if isinstance(locations, list) and locations:
        first = locations[0]
        if isinstance(first, dict):
            location_row = first

    location: VendorLocationResponse | None = None
    if location_row is not None:
        location = VendorLocationResponse(
            landmark=str(location_row.get("landmark") or ""),
            lat=float(location_row.get("lat") or 0),
            lng=float(location_row.get("lng") or 0),
        )

    return VendorSummaryResponse(
        id=str(row["id"]),
        slug=str(row["slug"]),
        display_name=str(row["display_name"]),
        preferred_badge=bool(row.get("preferred_badge")),
        rating_avg=rating_avg,
        rating_count=rating_count,
        location=location,
    )


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


def _collect_images(
    listing_rows: list[dict[str, Any]],
    images_by_listing: dict[str, list[dict[str, Any]]],
    *,
    primary_listing_id: str | None,
) -> list[ProductImageResponse]:
    ordered_listing_ids: list[str] = []
    if primary_listing_id:
        ordered_listing_ids.append(primary_listing_id)
    for row in sorted(listing_rows, key=lambda item: int(item.get("price_ngwee") or 0)):
        listing_id = str(row["id"])
        if listing_id not in ordered_listing_ids:
            ordered_listing_ids.append(listing_id)

    seen: set[str] = set()
    images: list[ProductImageResponse] = []
    for listing_id in ordered_listing_ids:
        for image_row in sorted(
            images_by_listing.get(listing_id, []),
            key=lambda item: int(item.get("position") or 0),
        ):
            public_id = str(image_row.get("cloudinary_public_id") or "")
            if not public_id or public_id in seen:
                continue
            seen.add(public_id)
            images.append(
                ProductImageResponse(
                    public_id=public_id,
                    position=int(image_row.get("position") or len(images) + 1),
                    listing_id=listing_id,
                )
            )
            if len(images) >= MAX_GALLERY_IMAGES:
                return images
    return images


def _fetch_product_by_slug(client: Any, slug: str) -> dict[str, Any] | None:
    response = (
        client.table("products")
        .select("id, name, slug, brand, spec, category_id, status, merged_into_id")
        .eq("slug", slug)
        .maybe_single()
        .execute()
    )
    row = response.data
    return row if isinstance(row, dict) else None


def _fetch_canonical_slug(client: Any, product_id: str) -> str | None:
    response = (
        client.table("products")
        .select("slug")
        .eq("id", product_id)
        .eq("status", "active")
        .maybe_single()
        .execute()
    )
    row = response.data
    if isinstance(row, dict) and row.get("slug"):
        return str(row["slug"])
    return None


def build_product_detail(
    client: Any,
    slug: str,
    *,
    include_wholesale: bool = False,
) -> ProductDetailResponse | RedirectResponse:
    product = _fetch_product_by_slug(client, slug)
    if product is None:
        raise AppError("product.not_found", "Product not found", 404)

    status = str(product.get("status") or "")
    if status == "merged":
        merged_into_id = product.get("merged_into_id")
        if merged_into_id:
            canonical_slug = _fetch_canonical_slug(client, str(merged_into_id))
            if canonical_slug:
                return RedirectResponse(
                    url=f"/products/{canonical_slug}",
                    status_code=301,
                )
        raise AppError("product.not_found", "Product not found", 404)

    if status != "active":
        raise AppError("product.not_found", "Product not found", 404)

    product_id = str(product["id"])
    product_name = str(product["name"])

    listings_response = (
        client.table("vendor_listings")
        .select(
            "id, title_override, price_ngwee, condition, stock_mode, stock_qty, "
            "moq, wholesale, status, "
            "vendors!inner("
            "id, slug, display_name, preferred_badge, status, "
            "vendor_locations(landmark, lat, lng)"
            ")"
        )
        .eq("product_id", product_id)
        .eq("status", "active")
        .eq("vendors.status", "active")
        .order("price_ngwee")
        .execute()
    )
    listing_rows = listings_response.data or []
    if not include_wholesale:
        # Wholesale-only listings are B2B supplies: hidden from the consumer
        # product page (gallery, vendor comparison, count) unless the caller is
        # a verified business buyer.
        listing_rows = [row for row in listing_rows if not row.get("wholesale")]

    listing_ids = [str(row["id"]) for row in listing_rows if row.get("id")]
    images_by_listing: dict[str, list[dict[str, Any]]] = {
        listing_id: [] for listing_id in listing_ids
    }

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
            if listing_id in images_by_listing:
                images_by_listing[listing_id].append(image_row)

    vendor_ids = []
    for row in listing_rows:
        vendor = row.get("vendors")
        if isinstance(vendor, dict) and vendor.get("id"):
            vendor_ids.append(str(vendor["id"]))
    vendor_ratings = _aggregate_vendor_ratings(client, list(dict.fromkeys(vendor_ids)))

    primary_listing_id = str(listing_rows[0]["id"]) if listing_rows else None
    gallery_images = _collect_images(
        listing_rows,
        images_by_listing,
        primary_listing_id=primary_listing_id,
    )

    listings: list[ListingResponse] = []
    for row in listing_rows:
        listing_id = str(row["id"])
        vendor_raw = row.get("vendors")
        if not isinstance(vendor_raw, dict):
            continue

        vendor_id = str(vendor_raw["id"])
        rating_avg, rating_count = vendor_ratings.get(vendor_id, (None, 0))
        stock_mode = str(row.get("stock_mode") or "tracked")
        stock_qty = row.get("stock_qty")
        parsed_stock_qty = int(stock_qty) if stock_qty is not None else None

        listing_images = [
            ProductImageResponse(
                public_id=str(image_row["cloudinary_public_id"]),
                position=int(image_row.get("position") or 1),
                listing_id=listing_id,
            )
            for image_row in sorted(
                images_by_listing.get(listing_id, []),
                key=lambda item: int(item.get("position") or 0),
            )
            if image_row.get("cloudinary_public_id")
        ][:MAX_GALLERY_IMAGES]

        listings.append(
            ListingResponse(
                id=listing_id,
                title=_listing_title(row, product_name),
                price_ngwee=int(row["price_ngwee"]),
                condition=str(row.get("condition") or "new"),
                stock_mode=stock_mode,
                stock_qty=parsed_stock_qty,
                moq=int(row.get("moq") or 1),
                wholesale=bool(row.get("wholesale")),
                in_stock=_is_in_stock(stock_mode, parsed_stock_qty),
                vendor=_parse_vendor_row(
                    vendor_raw,
                    rating_avg=rating_avg,
                    rating_count=rating_count,
                ),
                images=listing_images,
            )
        )

    return ProductDetailResponse(
        id=product_id,
        name=product_name,
        slug=str(product["slug"]),
        brand=product.get("brand"),
        spec=_parse_spec(product.get("spec")),
        category_id=str(product["category_id"]),
        images=gallery_images,
        listings=listings,
        listing_count=len(listings),
    )


@router.get("/{slug}", response_model=ProductDetailResponse)
async def get_product(
    slug: str,
    supabase: Annotated[_ServiceClient, Depends(get_supabase_client)],
    access: Annotated[BusinessAccess, Depends(get_business_access)],
) -> ProductDetailResponse | RedirectResponse:
    result = build_product_detail(
        supabase.client, slug, include_wholesale=access.eligible
    )
    if isinstance(result, RedirectResponse):
        return result
    return result
