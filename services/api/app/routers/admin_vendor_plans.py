"""Admin: vendor plan catalogue, per-vendor assignment + overrides, canonical photos.

Mounted on the shared ``/admin`` router, so ``require_admin_scope`` and the
audited route class apply: every mutation records exactly one ``audit_log`` row
(and the DB ``config_audit`` trigger records the row diff on the plan tables).
Plan and assignment routes are not in the RBAC permission map, so only
``admin``/``superadmin`` reach them (prices are money-adjacent). Canonical
product photo routes map to ``products.manage``.

Every mutation: admin authz (router dependency) + Pydantic validation + an
in-router ``ADMIN_WRITE`` rate limit keyed by the acting admin.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.core.auth import CurrentUser, get_current_user
from app.core.ratelimit import bump_rate_counter, raise_rate_limited
from app.core.ratelimit_policies import ADMIN_WRITE
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.admin_base import router as admin_router
from app.schemas.base import NgweeInt, StrictModel
from app.services.kyc.caps import _count_vendor_listings
from app.services.kyc.state_machine import ServiceRoleClient
from app.services.vendor_plans.canonical_photos import normalize_sha256
from app.services.vendor_plans.resolver import (
    PLAN_COLUMNS,
    load_assignment,
    load_override,
    override_is_live,
    plan_from_row,
    resolve_plan_for_vendor,
    shared_photos_enabled,
    vendor_plans_enabled,
)
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

plans_router = APIRouter(prefix="/vendor-plans", tags=["admin-vendor-plans"])
vendor_plan_router = APIRouter(prefix="/vendors/{vendor_id}/plan", tags=["admin-vendor-plans"])
product_images_router = APIRouter(
    prefix="/products/{product_id}/images", tags=["admin-product-images"]
)

MAX_PRICE_NGWEE = 100_000_000  # K1,000,000 / month — a typo guard, not a business rule.
MAX_LISTING_LIMIT = 1_000_000
MAX_OVERRIDE_DAYS = 366
PLAN_KEY_PATTERN = r"^[a-z][a-z0-9_]{1,31}$"
AnalyticsDepth = Literal["basic", "standard", "advanced"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _limit(client: Any, actor_id: str) -> None:
    allowed, retry_after = bump_rate_counter(
        scope=ADMIN_WRITE.scope,
        key=actor_id,
        window=ADMIN_WRITE.window,
        limit=ADMIN_WRITE.limit,
        client=client,
    )
    if not allowed:
        raise_rate_limited(retry_after=retry_after, message_key="admin.common.rateLimited")


def _conflict(message: str, message_key: str, **details: Any) -> AppError:
    return AppError(
        code="conflict",
        message=message,
        http_status=409,
        details={"message_key": message_key, **details},
    )


def _not_found(entity: str) -> AppError:
    return AppError(code="not_found", message=f"{entity} not found", http_status=404)


def _load_plan_row(client: Any, plan_key: str) -> dict[str, Any]:
    rows = _rows(client.table("vendor_plans").select(PLAN_COLUMNS).eq("key", plan_key).execute())
    if not rows:
        raise _not_found("Vendor plan")
    return rows[0]


def _require_vendor(client: Any, vendor_id: str) -> dict[str, Any]:
    rows = _rows(client.table("vendors").select("id, status").eq("id", vendor_id).execute())
    if not rows:
        raise _not_found("Vendor")
    return rows[0]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class PlanOut(BaseModel):
    key: str
    name: str
    price_ngwee: int
    max_listings: int | None
    max_images_per_listing: int
    featured_slots: int
    analytics_depth: str
    wholesale_tools: bool
    is_default: bool
    active: bool
    position: int
    vendor_count: int = 0


class PlanCreate(StrictModel):
    key: str = Field(pattern=PLAN_KEY_PATTERN)
    name: str = Field(min_length=1, max_length=60)
    price_ngwee: NgweeInt = Field(le=MAX_PRICE_NGWEE)
    max_listings: int | None = Field(default=None, ge=0, le=MAX_LISTING_LIMIT)
    max_images_per_listing: int = Field(default=8, ge=1, le=8)
    featured_slots: int = Field(default=0, ge=0, le=100)
    analytics_depth: AnalyticsDepth = "basic"
    wholesale_tools: bool = False
    active: bool = True
    position: int = Field(default=0, ge=0, le=1000)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be blank")
        return stripped


class PlanUpdate(StrictModel):
    """Partial update. Send ``max_listings: null`` explicitly for unlimited."""

    name: str | None = Field(default=None, min_length=1, max_length=60)
    price_ngwee: NgweeInt | None = Field(default=None, le=MAX_PRICE_NGWEE)
    max_listings: int | None = Field(default=None, ge=0, le=MAX_LISTING_LIMIT)
    max_images_per_listing: int | None = Field(default=None, ge=1, le=8)
    featured_slots: int | None = Field(default=None, ge=0, le=100)
    analytics_depth: AnalyticsDepth | None = None
    wholesale_tools: bool | None = None
    active: bool | None = None
    is_default: Literal[True] | None = None
    position: int | None = Field(default=None, ge=0, le=1000)

    @model_validator(mode="after")
    def at_least_one_field(self) -> PlanUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        nullable = {"max_listings"}
        for field in self.model_fields_set - nullable:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        if self.name is not None and not self.name.strip():
            raise ValueError("name must not be blank")
        return self


class AssignPlanRequest(StrictModel):
    plan_key: str = Field(pattern=PLAN_KEY_PATTERN)
    note: str | None = Field(default=None, max_length=500)


class OverrideRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_listings: int | None = Field(default=None, ge=0, le=MAX_LISTING_LIMIT)
    unlimited_listings: bool = False
    max_images_per_listing: int | None = Field(default=None, ge=1, le=8)
    expires_at: datetime
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_shape(self) -> OverrideRequest:
        if self.unlimited_listings and self.max_listings is not None:
            raise ValueError("set either unlimited_listings or max_listings, not both")
        if (
            not self.unlimited_listings
            and self.max_listings is None
            and self.max_images_per_listing is None
        ):
            raise ValueError("an override must change at least one limit")
        if not self.reason.strip():
            raise ValueError("reason must not be blank")
        expires = self.expires_at
        if expires.tzinfo is None:
            raise ValueError("expires_at must include a timezone")
        now = datetime.now(UTC)
        if expires <= now:
            raise ValueError("expires_at must be in the future")
        if expires > now + timedelta(days=MAX_OVERRIDE_DAYS):
            raise ValueError(f"expires_at must be within {MAX_OVERRIDE_DAYS} days")
        return self


class AssignmentOut(BaseModel):
    plan_key: str
    source: str
    billing_status: str
    paid_through: str | None = None
    note: str | None = None
    assigned_by: str | None = None
    assigned_at: str | None = None


class OverrideOut(BaseModel):
    max_listings: int | None
    unlimited_listings: bool
    max_images_per_listing: int | None
    expires_at: str
    reason: str
    live: bool


class VendorPlanDetail(BaseModel):
    vendor_id: str
    flag_enabled: bool
    assignment: AssignmentOut | None
    override: OverrideOut | None
    effective_plan_key: str | None
    effective_max_listings: int | None
    effective_max_images_per_listing: int | None
    listing_count: int


def _plan_out(row: dict[str, Any], vendor_count: int = 0) -> PlanOut:
    plan = plan_from_row(row)
    return PlanOut(
        key=plan.key,
        name=plan.name,
        price_ngwee=plan.price_ngwee,
        max_listings=plan.max_listings,
        max_images_per_listing=plan.max_images_per_listing,
        featured_slots=plan.featured_slots,
        analytics_depth=plan.analytics_depth,
        wholesale_tools=plan.wholesale_tools,
        is_default=plan.is_default,
        active=plan.active,
        position=plan.position,
        vendor_count=vendor_count,
    )


def _assignment_out(row: dict[str, Any] | None) -> AssignmentOut | None:
    if row is None:
        return None
    return AssignmentOut(
        plan_key=str(row.get("plan_key")),
        source=str(row.get("source") or "admin"),
        billing_status=str(row.get("billing_status") or "not_billed"),
        paid_through=str(row["paid_through"]) if row.get("paid_through") else None,
        note=row.get("note"),
        assigned_by=str(row["assigned_by"]) if row.get("assigned_by") else None,
        assigned_at=str(row["assigned_at"]) if row.get("assigned_at") else None,
    )


def _override_out(row: dict[str, Any] | None) -> OverrideOut | None:
    if row is None:
        return None
    return OverrideOut(
        max_listings=row.get("max_listings"),
        unlimited_listings=row.get("unlimited_listings") is True,
        max_images_per_listing=row.get("max_images_per_listing"),
        expires_at=str(row.get("expires_at")),
        reason=str(row.get("reason") or ""),
        live=override_is_live(row),
    )


def _override_snapshot(row: dict[str, Any] | None) -> dict[str, Any] | None:
    out = _override_out(row)
    return out.model_dump(mode="json") if out is not None else None


def _vendor_counts(client: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in _rows(client.table("vendor_plan_assignments").select("plan_key").execute()):
        key = str(row.get("plan_key"))
        counts[key] = counts.get(key, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Plan catalogue CRUD
# ---------------------------------------------------------------------------
@plans_router.get("", response_model=list[PlanOut])
async def list_vendor_plans(
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> list[PlanOut]:
    client: Any = service_client.client
    rows = _rows(client.table("vendor_plans").select(PLAN_COLUMNS).order("position").execute())
    counts = _vendor_counts(client)
    return [_plan_out(row, counts.get(str(row.get("key")), 0)) for row in rows]


@plans_router.post("", response_model=PlanOut, status_code=201)
async def create_vendor_plan(
    body: PlanCreate,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> PlanOut:
    client: Any = service_client.client
    _limit(client, user.id)
    if _rows(client.table("vendor_plans").select("key").eq("key", body.key).execute()):
        raise _conflict(
            "Plan key already exists", "admin.vendorPlans.errors.keyTaken", key=body.key
        )
    created = _rows(
        client.table("vendor_plans").insert({**body.model_dump(), "is_default": False}).execute()
    )
    if not created:
        raise AppError(code="internal_error", message="Failed to create plan", http_status=500)
    out = _plan_out(created[0])
    recorder.record(
        action="vendor_plans.create",
        entity_type="vendor_plan",
        entity_id=out.key,
        before=None,
        after=out.model_dump(mode="json"),
    )
    return out


@plans_router.patch("/{plan_key}", response_model=PlanOut)
async def update_vendor_plan(
    plan_key: str,
    body: PlanUpdate,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> PlanOut:
    client: Any = service_client.client
    _limit(client, user.id)
    before = _load_plan_row(client, plan_key)
    changes = {field: getattr(body, field) for field in body.model_fields_set}
    if isinstance(changes.get("name"), str):
        changes["name"] = changes["name"].strip()
    if before.get("is_default") is True and changes.get("active") is False:
        raise _conflict(
            "The default plan cannot be deactivated",
            "admin.vendorPlans.errors.defaultInactive",
        )
    make_default = changes.pop("is_default", None) is True and before.get("is_default") is not True
    if make_default and (changes.get("active") is False or before.get("active") is False):
        raise _conflict(
            "An inactive plan cannot be the default",
            "admin.vendorPlans.errors.defaultInactive",
        )
    if make_default:
        # One default at a time (partial unique index): clear the old one first.
        client.table("vendor_plans").update({"is_default": False}).eq("is_default", True).execute()
        changes["is_default"] = True
    updated = before
    if changes:
        rows = _rows(client.table("vendor_plans").update(changes).eq("key", plan_key).execute())
        updated = rows[0] if rows else _load_plan_row(client, plan_key)
    out = _plan_out(updated)
    recorder.record(
        action="vendor_plans.update",
        entity_type="vendor_plan",
        entity_id=plan_key,
        before=_plan_out(before).model_dump(mode="json"),
        after=out.model_dump(mode="json"),
    )
    return out


@plans_router.delete("/{plan_key}", status_code=204)
async def delete_vendor_plan(
    plan_key: str,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> None:
    client: Any = service_client.client
    _limit(client, user.id)
    before = _load_plan_row(client, plan_key)
    if before.get("is_default") is True:
        raise _conflict(
            "The default plan cannot be deleted", "admin.vendorPlans.errors.defaultDelete"
        )
    in_use = _rows(
        client.table("vendor_plan_assignments").select("id").eq("plan_key", plan_key).execute()
    )
    if in_use:
        # Never strand vendors: deactivate instead, or move them first.
        raise _conflict(
            "Plan has vendors assigned; deactivate it instead",
            "admin.vendorPlans.errors.inUse",
            vendor_count=len(in_use),
        )
    client.table("vendor_plans").delete().eq("key", plan_key).execute()
    recorder.record(
        action="vendor_plans.delete",
        entity_type="vendor_plan",
        entity_id=plan_key,
        before=_plan_out(before).model_dump(mode="json"),
        after=None,
    )


# ---------------------------------------------------------------------------
# Per-vendor assignment + override
# ---------------------------------------------------------------------------
def _vendor_detail(service_client: ServiceRoleClient, vendor_id: str) -> VendorPlanDetail:
    client: Any = service_client.client
    assignment = load_assignment(client, vendor_id)
    override = load_override(client, vendor_id)
    effective = resolve_plan_for_vendor(client, vendor_id)
    return VendorPlanDetail(
        vendor_id=vendor_id,
        flag_enabled=vendor_plans_enabled(client),
        assignment=_assignment_out(assignment),
        override=_override_out(override),
        effective_plan_key=effective.plan.key if effective else None,
        effective_max_listings=effective.max_listings if effective else None,
        effective_max_images_per_listing=effective.max_images_per_listing if effective else None,
        listing_count=_count_vendor_listings(service_client, vendor_id),
    )


@vendor_plan_router.get("", response_model=VendorPlanDetail)
async def get_vendor_plan_detail(
    vendor_id: UUID,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> VendorPlanDetail:
    client: Any = service_client.client
    _require_vendor(client, str(vendor_id))
    return _vendor_detail(service_client, str(vendor_id))


@vendor_plan_router.put("", response_model=VendorPlanDetail)
async def assign_vendor_plan(
    vendor_id: UUID,
    body: AssignPlanRequest,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> VendorPlanDetail:
    client: Any = service_client.client
    _limit(client, user.id)
    vendor_key = str(vendor_id)
    _require_vendor(client, vendor_key)
    plan = _load_plan_row(client, body.plan_key)
    if plan.get("active") is not True:
        raise _conflict("Plan is not active", "admin.vendorPlans.errors.planInactive")
    before = load_assignment(client, vendor_key)
    # Record only: no charge is made (billing seam: services/vendor_plans/billing.py).
    client.table("vendor_plan_assignments").upsert(
        {
            "vendor_id": vendor_key,
            "plan_key": body.plan_key,
            "source": "admin",
            "note": body.note.strip() if body.note else None,
            "assigned_by": user.id,
            "assigned_at": datetime.now(UTC).isoformat(),
        },
        on_conflict="vendor_id",
    ).execute()
    detail = _vendor_detail(service_client, vendor_key)
    recorder.record(
        action="vendor_plans.assign",
        entity_type="vendor",
        entity_id=vendor_key,
        before={"plan_key": before.get("plan_key") if before else None},
        after={"plan_key": body.plan_key, "note": body.note},
    )
    return detail


@vendor_plan_router.put("/override", response_model=VendorPlanDetail)
async def set_vendor_plan_override(
    vendor_id: UUID,
    body: OverrideRequest,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> VendorPlanDetail:
    client: Any = service_client.client
    _limit(client, user.id)
    vendor_key = str(vendor_id)
    _require_vendor(client, vendor_key)
    before = load_override(client, vendor_key)
    payload = {
        "vendor_id": vendor_key,
        "max_listings": body.max_listings,
        "unlimited_listings": body.unlimited_listings,
        "max_images_per_listing": body.max_images_per_listing,
        "expires_at": body.expires_at.astimezone(UTC).isoformat(),
        "reason": body.reason.strip(),
        "created_by": user.id,
    }
    client.table("vendor_plan_overrides").upsert(payload, on_conflict="vendor_id").execute()
    detail = _vendor_detail(service_client, vendor_key)
    recorder.record(
        action="vendor_plans.override.set",
        entity_type="vendor",
        entity_id=vendor_key,
        before=_override_snapshot(before),
        after={key: value for key, value in payload.items() if key != "vendor_id"},
    )
    return detail


@vendor_plan_router.delete("/override", response_model=VendorPlanDetail)
async def clear_vendor_plan_override(
    vendor_id: UUID,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> VendorPlanDetail:
    client: Any = service_client.client
    _limit(client, user.id)
    vendor_key = str(vendor_id)
    _require_vendor(client, vendor_key)
    before = load_override(client, vendor_key)
    if before is None:
        raise _not_found("Override")
    client.table("vendor_plan_overrides").delete().eq("vendor_id", vendor_key).execute()
    detail = _vendor_detail(service_client, vendor_key)
    recorder.record(
        action="vendor_plans.override.clear",
        entity_type="vendor",
        entity_id=vendor_key,
        before=_override_snapshot(before),
        after=None,
    )
    return detail


# ---------------------------------------------------------------------------
# Canonical product photos (curation works while the flag is off, so photos
# can be prepared before customers see them; customer reads stay gated).
# ---------------------------------------------------------------------------
class ProductImageOut(BaseModel):
    id: str
    product_id: str
    cloudinary_public_id: str
    position: int
    content_sha256: str | None = None


class ProductImageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    listing_image_id: UUID | None = None
    cloudinary_public_id: str | None = Field(default=None, min_length=1, max_length=500)
    content_sha256: str | None = Field(default=None, min_length=64, max_length=64)

    @field_validator("cloudinary_public_id")
    @classmethod
    def validate_public_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed or ".." in trimmed or trimmed.startswith("/"):
            raise ValueError("cloudinary_public_id is invalid")
        return trimmed

    @field_validator("content_sha256")
    @classmethod
    def validate_sha(cls, value: str | None) -> str | None:
        return normalize_sha256(value) if value is not None else None

    @model_validator(mode="after")
    def exactly_one_source(self) -> ProductImageCreate:
        if (self.listing_image_id is None) == (self.cloudinary_public_id is None):
            raise ValueError("provide exactly one of listing_image_id or cloudinary_public_id")
        return self


class ProductImagesPage(BaseModel):
    flag_enabled: bool
    images: list[ProductImageOut]


def _product_image_out(row: dict[str, Any]) -> ProductImageOut:
    return ProductImageOut(
        id=str(row["id"]),
        product_id=str(row["product_id"]),
        cloudinary_public_id=str(row["cloudinary_public_id"]),
        position=int(row.get("position") or 1),
        content_sha256=row.get("content_sha256"),
    )


def _product_images(client: Any, product_id: str) -> list[dict[str, Any]]:
    return _rows(
        client.table("product_images")
        .select("id, product_id, cloudinary_public_id, position, content_sha256")
        .eq("product_id", product_id)
        .order("position")
        .execute()
    )


def _require_product(client: Any, product_id: str) -> None:
    if not _rows(client.table("products").select("id").eq("id", product_id).execute()):
        raise _not_found("Product")


@product_images_router.get("", response_model=ProductImagesPage)
async def list_product_images(
    product_id: UUID,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ProductImagesPage:
    client: Any = service_client.client
    _require_product(client, str(product_id))
    return ProductImagesPage(
        flag_enabled=shared_photos_enabled(client),
        images=[_product_image_out(row) for row in _product_images(client, str(product_id))],
    )


@product_images_router.post("", response_model=ProductImageOut, status_code=201)
async def add_product_image(
    product_id: UUID,
    body: ProductImageCreate,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ProductImageOut:
    client: Any = service_client.client
    _limit(client, user.id)
    product_key = str(product_id)
    _require_product(client, product_key)
    public_id = body.cloudinary_public_id
    sha = body.content_sha256
    source_id: str | None = None
    if body.listing_image_id is not None:
        source = _rows(
            client.table("listing_images")
            .select("id, cloudinary_public_id, content_sha256, vendor_listings!inner(product_id)")
            .eq("id", str(body.listing_image_id))
            .eq("vendor_listings.product_id", product_key)
            .execute()
        )
        if not source:
            raise AppError(
                code="validation_error",
                message="Listing image does not belong to a listing of this product",
                http_status=422,
                details={"listing_image_id": str(body.listing_image_id)},
            )
        public_id = str(source[0]["cloudinary_public_id"])
        sha = source[0].get("content_sha256")
        source_id = str(source[0]["id"])
    existing = _product_images(client, product_key)
    if len(existing) >= 8:
        raise _conflict("A product can have at most 8 photos", "admin.productImages.errors.full")
    if any(row.get("cloudinary_public_id") == public_id for row in existing):
        raise _conflict("Photo already on this product", "admin.productImages.errors.duplicate")
    taken = {int(row.get("position") or 0) for row in existing}
    position = next(slot for slot in range(1, 9) if slot not in taken)
    created = _rows(
        client.table("product_images")
        .insert(
            {
                "product_id": product_key,
                "cloudinary_public_id": public_id,
                "position": position,
                "content_sha256": sha,
                "source_listing_image_id": source_id,
                "created_by": user.id,
            }
        )
        .execute()
    )
    if not created:
        raise AppError(code="internal_error", message="Failed to add photo", http_status=500)
    out = _product_image_out(created[0])
    recorder.record(
        action="products.images.add",
        entity_type="product",
        entity_id=product_key,
        before=None,
        after=out.model_dump(mode="json"),
    )
    return out


@product_images_router.delete("/{image_id}", status_code=204)
async def remove_product_image(
    product_id: UUID,
    image_id: UUID,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> None:
    client: Any = service_client.client
    _limit(client, user.id)
    product_key = str(product_id)
    existing = _product_images(client, product_key)
    target = next((row for row in existing if str(row.get("id")) == str(image_id)), None)
    if target is None:
        raise _not_found("Product image")
    (
        client.table("product_images")
        .delete()
        .eq("id", str(image_id))
        .eq("product_id", product_key)
        .execute()
    )
    recorder.record(
        action="products.images.remove",
        entity_type="product",
        entity_id=product_key,
        before=_product_image_out(target).model_dump(mode="json"),
        after=None,
    )


admin_router.include_router(plans_router)
admin_router.include_router(vendor_plan_router)
admin_router.include_router(product_images_router)
