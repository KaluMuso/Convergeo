from __future__ import annotations

import re
import uuid
from typing import Annotated, Any, Literal

from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import NgweeInt, StrictModel
from app.services.kyc.caps import VendorCapLimits, require_listing_cap
from app.services.kyc.state_machine import ServiceRoleClient
from app.services.moderation.prohibited import screen_listing
from fastapi import APIRouter, Depends
from pydantic import Field, field_validator, model_validator

router = APIRouter(prefix="/vendor/listings", tags=["vendor-listings"])

ListingMode = Literal["attach", "new_canonical", "quick_list"]
ListingCondition = Literal["new", "refurbished"]
StockMode = Literal["tracked", "always_available"]
ListingStatus = Literal["draft", "active"]


class PriceTierInput(StrictModel):
    min_qty: int = Field(ge=1)
    price_ngwee: NgweeInt


class ListingCreateRequest(StrictModel):
    mode: ListingMode
    product_id: str | None = None
    product_name: str | None = None
    brand: str | None = None
    spec: dict[str, Any] | None = None
    category_id: str | None = None
    aliases: list[str] = Field(default_factory=list)
    title_override: str | None = None
    price_ngwee: NgweeInt
    condition: ListingCondition
    stock_mode: StockMode
    stock_qty: int | None = None
    wholesale: bool = False
    price_tiers: list[PriceTierInput] | None = None
    moq: int = Field(default=1, ge=1)
    returnable: bool = False
    return_window_hours: int | None = None
    publish: bool = True

    @field_validator("price_ngwee")
    @classmethod
    def price_must_be_positive(cls, value: int) -> int:
        if value <= 0:
            msg = "price_ngwee must be greater than zero"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def validate_mode_fields(self) -> ListingCreateRequest:
        if self.mode == "attach" and not self.product_id:
            raise ValueError("product_id is required for attach mode")
        if self.mode == "new_canonical":
            if not self.product_name or not self.product_name.strip():
                raise ValueError("product_name is required for new_canonical mode")
            if not self.category_id:
                raise ValueError("category_id is required for new_canonical mode")
        if self.mode == "quick_list":
            if not self.title_override or not self.title_override.strip():
                raise ValueError("title_override is required for quick_list mode")
        if self.stock_mode == "tracked" and self.stock_qty is None:
            raise ValueError("stock_qty is required when stock_mode is tracked")
        if self.returnable and self.return_window_hours is None:
            raise ValueError("return_window_hours is required when returnable is true")
        return self


class CommissionPreview(StrictModel):
    category_key: str
    rate_bps: int
    rate_percent: float


class CategoryOption(StrictModel):
    id: str
    name: str
    commission_key: str
    commission: CommissionPreview


class CanonicalPreviewResponse(StrictModel):
    product_id: str
    name: str
    brand: str | None
    spec: dict[str, Any]
    category_id: str
    category_name: str
    commission: CommissionPreview


class ListingCreateResponse(StrictModel):
    listing_id: str
    mode: ListingMode
    status: str
    product_id: str | None
    product_status: str | None
    commission: CommissionPreview | None


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def _load_vendor_for_owner(
    service_client: ServiceRoleClient,
    owner_user_id: str,
) -> dict[str, Any]:
    response = (
        service_client.client.table("vendors")
        .select("id, owner_user_id, status, kyc_tier")
        .eq("owner_user_id", owner_user_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(
            code="forbidden",
            message="Authenticated user does not own a vendor profile",
            http_status=403,
            details={"message_key": "vendor.errors.not_found"},
        )
    return row


def _slugify(name: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", name.lower())
    slug = re.sub(r"[-\s]+", "-", slug).strip("-")
    return slug[:80] or "product"


def _unique_product_slug(service_client: ServiceRoleClient, base_name: str) -> str:
    base = _slugify(base_name)
    client = service_client.client
    for suffix in range(0, 100):
        candidate = base if suffix == 0 else f"{base}-{suffix}"
        existing = (
            client.table("products")
            .select("id")
            .eq("slug", candidate)
            .maybe_single()
            .execute()
        )
        if _single_row(existing) is None:
            return candidate
    return f"{base}-{uuid.uuid4().hex[:8]}"


def _validate_price_tiers_ordered(tiers: list[PriceTierInput]) -> None:
    if not tiers:
        return
    ordered = sorted(tiers, key=lambda tier: tier.min_qty)
    prev_qty = 0
    prev_price: int | None = None
    for tier in ordered:
        if tier.min_qty <= prev_qty:
            raise AppError(
                code="invalid_price_tiers",
                message="Price tiers must have strictly ascending min_qty",
                http_status=422,
                details={"message_key": "vendor.listings.errors.invalid_tiers"},
            )
        if prev_price is not None and tier.price_ngwee >= prev_price:
            raise AppError(
                code="invalid_price_tiers",
                message="Price tiers must have strictly descending unit prices",
                http_status=422,
                details={"message_key": "vendor.listings.errors.invalid_tiers"},
            )
        prev_qty = tier.min_qty
        prev_price = tier.price_ngwee


def _enforce_wholesale_tier(
    service_client: ServiceRoleClient,
    vendor: dict[str, Any],
    body: ListingCreateRequest,
) -> None:
    if not body.wholesale:
        return
    from app.services.kyc.eligibility import (
        require_wholesale_eligible,
        resolve_vendor_eligibility,
    )

    eligibility = resolve_vendor_eligibility(
        service_client,
        str(vendor["id"]),
        vendor_row=vendor,
    )
    require_wholesale_eligible(eligibility)
    if not body.price_tiers:
        raise AppError(
            code="validation_error",
            message="Wholesale listings require price_tiers",
            http_status=422,
            details={"message_key": "vendor.listings.errors.wholesale_tiers_required"},
        )


def _load_commission(
    service_client: ServiceRoleClient,
    commission_key: str,
) -> CommissionPreview:
    response = (
        service_client.client.table("commission_rates")
        .select("category_key, rate_bps")
        .eq("category_key", commission_key)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        rate_bps = 800
        commission_key = "default"
    else:
        rate_bps = int(row["rate_bps"])
    return CommissionPreview(
        category_key=commission_key,
        rate_bps=rate_bps,
        rate_percent=rate_bps / 100,
    )


def _load_product_with_category(
    service_client: ServiceRoleClient,
    product_id: str,
) -> dict[str, Any]:
    response = (
        service_client.client.table("products")
        .select("id, name, brand, spec, category_id, status, categories(name, commission_key)")
        .eq("id", product_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(
            code="not_found",
            message="Product not found",
            http_status=404,
            details={"message_key": "vendor.listings.errors.product_not_found"},
        )
    return row


def _load_category_commission_key(
    service_client: ServiceRoleClient,
    category_id: str,
) -> tuple[str, str]:
    response = (
        service_client.client.table("categories")
        .select("id, name, commission_key, prohibited")
        .eq("id", category_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(
            code="not_found",
            message="Category not found",
            http_status=404,
            details={"message_key": "vendor.listings.errors.category_not_found"},
        )
    if bool(row.get("prohibited")):
        # D8 geo-fence: a category flagged prohibited may never be listed.
        raise AppError(
            code="prohibited_listing",
            message="Listing contains a prohibited category or keyword",
            http_status=422,
            details={
                "message_key": "vendor.listings.errors.submitFailed",
                "reason": "category",
                "matched": str(row.get("name", "")),
            },
        )
    return str(row["name"]), str(row["commission_key"])


def _serialize_price_tiers(tiers: list[PriceTierInput] | None) -> list[dict[str, int]] | None:
    if not tiers:
        return None
    return [{"min_qty": tier.min_qty, "price_ngwee": tier.price_ngwee} for tier in tiers]


def _resolve_listing_status(mode: ListingMode, publish: bool) -> str:
    if mode == "new_canonical":
        return "draft"
    return "active" if publish else "draft"


@router.get("/categories", response_model=list[CategoryOption])
async def list_listing_categories(
    _current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> list[CategoryOption]:
    response = (
        service_client.client.table("categories")
        .select("id, name, commission_key, prohibited, position")
        .eq("prohibited", False)
        .order("position")
        .execute()
    )
    data = getattr(response, "data", None)
    rows = data if isinstance(data, list) else []
    options: list[CategoryOption] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        commission_key = str(row.get("commission_key", "default"))
        options.append(
            CategoryOption(
                id=str(row["id"]),
                name=str(row["name"]),
                commission_key=commission_key,
                commission=_load_commission(service_client, commission_key),
            )
        )
    return options


@router.get("/canonical/{product_id}", response_model=CanonicalPreviewResponse)
async def get_canonical_preview(
    product_id: str,
    _current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> CanonicalPreviewResponse:
    product = _load_product_with_category(service_client, product_id)
    if product.get("status") != "active":
        raise AppError(
            code="product_not_attachable",
            message="Only active canonical products can be attached",
            http_status=422,
            details={"message_key": "vendor.listings.errors.product_not_active"},
        )

    categories = product.get("categories")
    if not isinstance(categories, dict):
        raise AppError(
            code="internal_error",
            message="Product category data is missing",
            http_status=500,
        )

    commission_key = str(categories.get("commission_key", "default"))
    commission = _load_commission(service_client, commission_key)
    spec = product.get("spec")
    if not isinstance(spec, dict):
        spec = {}

    return CanonicalPreviewResponse(
        product_id=str(product["id"]),
        name=str(product["name"]),
        brand=str(product["brand"]) if product.get("brand") else None,
        spec=spec,
        category_id=str(product["category_id"]),
        category_name=str(categories.get("name", "")),
        commission=commission,
    )


@router.post("", response_model=ListingCreateResponse)
async def create_listing(
    body: ListingCreateRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    _limits: Annotated[VendorCapLimits, Depends(require_listing_cap)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ListingCreateResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    vendor_id = str(vendor["id"])

    # Resolve the vendor-supplied category up front so the moderation screen's
    # category-block layer runs and DB-flagged prohibited categories are rejected
    # (D8) before anything is written.
    category_name: str | None = None
    resolved_commission_key: str | None = None
    if body.mode == "new_canonical" and body.category_id:
        category_name, resolved_commission_key = _load_category_commission_key(
            service_client,
            body.category_id,
        )

    guard = screen_listing(
        title=body.title_override or body.product_name,
        description=body.brand,
        category=category_name,
    )
    if not guard.allowed:
        raise AppError(
            code="prohibited_listing",
            message="Listing contains a prohibited category or keyword",
            http_status=422,
            details={
                "message_key": "vendor.listings.errors.submitFailed",
                "reason": guard.reason,
                "matched": guard.matched,
            },
        )

    _enforce_wholesale_tier(service_client, vendor, body)
    if body.price_tiers:
        _validate_price_tiers_ordered(body.price_tiers)

    client = service_client.client
    product_id: str | None = None
    product_status: str | None = None
    commission: CommissionPreview | None = None

    if body.mode == "attach":
        assert body.product_id is not None
        product = _load_product_with_category(service_client, body.product_id)
        if product.get("status") != "active":
            raise AppError(
                code="product_not_attachable",
                message="Only active canonical products can be attached",
                http_status=422,
                details={"message_key": "vendor.listings.errors.product_not_active"},
            )
        product_id = str(product["id"])
        product_status = str(product["status"])
        categories = product.get("categories")
        commission_key = "default"
        if isinstance(categories, dict):
            commission_key = str(categories.get("commission_key", "default"))
        commission = _load_commission(service_client, commission_key)

    elif body.mode == "new_canonical":
        assert body.product_name is not None
        assert body.category_id is not None
        assert resolved_commission_key is not None
        commission = _load_commission(service_client, resolved_commission_key)
        slug = _unique_product_slug(service_client, body.product_name)
        product_insert = (
            client.table("products")
            .insert(
                {
                    "name": body.product_name.strip(),
                    "slug": slug,
                    "brand": body.brand.strip() if body.brand else None,
                    "spec": body.spec or {},
                    "category_id": body.category_id,
                    "aliases": body.aliases,
                    "status": "pending_moderation",
                }
            )
            .execute()
        )
        created_product = _single_row(product_insert)
        if created_product is None:
            raise AppError(
                code="internal_error",
                message="Failed to create canonical product",
                http_status=500,
            )
        product_id = str(created_product["id"])
        product_status = "pending_moderation"

    listing_payload: dict[str, Any] = {
        "vendor_id": vendor_id,
        "product_id": product_id,
        "title_override": body.title_override.strip() if body.title_override else None,
        "price_ngwee": body.price_ngwee,
        "condition": body.condition,
        "stock_mode": body.stock_mode,
        "stock_qty": body.stock_qty,
        "wholesale": body.wholesale,
        "price_tiers": _serialize_price_tiers(body.price_tiers),
        "moq": body.moq,
        "returnable": body.returnable,
        "return_window_hours": body.return_window_hours,
        "status": _resolve_listing_status(body.mode, body.publish),
    }

    if body.mode == "quick_list":
        listing_payload["product_id"] = None

    listing_insert = client.table("vendor_listings").insert(listing_payload).execute()
    created_listing = _single_row(listing_insert)
    if created_listing is None:
        raise AppError(
            code="internal_error",
            message="Failed to create listing",
            http_status=500,
        )

    return ListingCreateResponse(
        listing_id=str(created_listing["id"]),
        mode=body.mode,
        status=str(created_listing["status"]),
        product_id=product_id,
        product_status=product_status,
        commission=commission,
    )
