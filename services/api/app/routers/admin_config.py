from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.admin_base import router as admin_router
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Validation bounds (API stricter than DB where noted)
# ---------------------------------------------------------------------------
MAX_RATE_BPS = 2000
MIN_RELEASE_DELIVERED_HOURS = 1
MAX_RELEASE_DELIVERED_HOURS = 168
MIN_RELEASE_SHIPPED_DAYS = 1
MAX_RELEASE_SHIPPED_DAYS = 90
MIN_RESERVATION_TTL_MIN = 1
MAX_RESERVATION_TTL_MIN = 120
MIN_AI_GUEST_QUOTA = 1
MAX_AI_GUEST_QUOTA = 100
MIN_AI_FREE_MONTHLY_QUOTA = 1
MAX_AI_FREE_MONTHLY_QUOTA = 1000
MIN_AI_MONTHLY_CAP_USD = 1
MAX_AI_MONTHLY_CAP_USD = 100

NGWEE_PLATFORM_KEYS = frozenset({"cod_cap_ngwee", "free_delivery_threshold_ngwee"})
INT_PLATFORM_KEYS = frozenset(
    {
        "reservation_ttl_min",
        "ai_guest_quota",
        "ai_free_monthly_quota",
        "ai_monthly_cap_usd",
        "release_after_delivered_hours",
        "release_after_shipped_days",
    }
)
EDITABLE_PLATFORM_KEYS = NGWEE_PLATFORM_KEYS | INT_PLATFORM_KEYS

config_router = APIRouter(prefix="/config", tags=["admin-config"])


# ---------------------------------------------------------------------------
# Per-key validation
# ---------------------------------------------------------------------------
def validate_rate_bps(rate_bps: int) -> None:
    if rate_bps < 0 or rate_bps > MAX_RATE_BPS:
        raise AppError(
            code="validation_error",
            message="rate_bps out of bounds",
            http_status=422,
            details={"rate_bps": f"must be between 0 and {MAX_RATE_BPS}"},
        )


def validate_ngwee(value: int, *, field: str) -> None:
    if value < 0:
        raise AppError(
            code="validation_error",
            message=f"{field} must be non-negative",
            http_status=422,
            details={field: "must be >= 0"},
        )


def validate_platform_value(key: str, value: int) -> None:
    if key in NGWEE_PLATFORM_KEYS:
        validate_ngwee(value, field=key)
        return

    if key == "reservation_ttl_min":
        if value < MIN_RESERVATION_TTL_MIN or value > MAX_RESERVATION_TTL_MIN:
            raise AppError(
                code="validation_error",
                message="reservation_ttl_min out of bounds",
                http_status=422,
                details={
                    "reservation_ttl_min": (
                        f"must be between {MIN_RESERVATION_TTL_MIN} and {MAX_RESERVATION_TTL_MIN}"
                    )
                },
            )
        return

    if key == "ai_guest_quota":
        if value < MIN_AI_GUEST_QUOTA or value > MAX_AI_GUEST_QUOTA:
            raise AppError(
                code="validation_error",
                message="ai_guest_quota out of bounds",
                http_status=422,
                details={
                    "ai_guest_quota": (
                        f"must be between {MIN_AI_GUEST_QUOTA} and {MAX_AI_GUEST_QUOTA}"
                    )
                },
            )
        return

    if key == "ai_free_monthly_quota":
        if value < MIN_AI_FREE_MONTHLY_QUOTA or value > MAX_AI_FREE_MONTHLY_QUOTA:
            raise AppError(
                code="validation_error",
                message="ai_free_monthly_quota out of bounds",
                http_status=422,
                details={
                    "ai_free_monthly_quota": (
                        f"must be between {MIN_AI_FREE_MONTHLY_QUOTA} "
                        f"and {MAX_AI_FREE_MONTHLY_QUOTA}"
                    )
                },
            )
        return

    if key == "ai_monthly_cap_usd":
        if value < MIN_AI_MONTHLY_CAP_USD or value > MAX_AI_MONTHLY_CAP_USD:
            raise AppError(
                code="validation_error",
                message="ai_monthly_cap_usd out of bounds",
                http_status=422,
                details={
                    "ai_monthly_cap_usd": (
                        f"must be between {MIN_AI_MONTHLY_CAP_USD} and {MAX_AI_MONTHLY_CAP_USD}"
                    )
                },
            )
        return

    if key == "release_after_delivered_hours":
        if value < MIN_RELEASE_DELIVERED_HOURS or value > MAX_RELEASE_DELIVERED_HOURS:
            raise AppError(
                code="validation_error",
                message="release_after_delivered_hours out of bounds",
                http_status=422,
                details={
                    "release_after_delivered_hours": (
                        f"must be between {MIN_RELEASE_DELIVERED_HOURS} "
                        f"and {MAX_RELEASE_DELIVERED_HOURS}"
                    )
                },
            )
        return

    if key == "release_after_shipped_days":
        if value < MIN_RELEASE_SHIPPED_DAYS or value > MAX_RELEASE_SHIPPED_DAYS:
            raise AppError(
                code="validation_error",
                message="release_after_shipped_days out of bounds",
                http_status=422,
                details={
                    "release_after_shipped_days": (
                        f"must be between {MIN_RELEASE_SHIPPED_DAYS} and {MAX_RELEASE_SHIPPED_DAYS}"
                    )
                },
            )
        return

    raise AppError(
        code="validation_error",
        message="platform config key is not editable",
        http_status=400,
        details={"key": key},
    )


def validate_zone_fee_ngwee(fee_ngwee: int) -> None:
    validate_ngwee(fee_ngwee, field="fee_ngwee")


def _extract_json_int(value: Any) -> int:
    if isinstance(value, bool):
        raise AppError(
            code="validation_error",
            message="value must be an integer",
            http_status=422,
            details={"value": "boolean not allowed"},
        )
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    raise AppError(
        code="validation_error",
        message="value must be an integer",
        http_status=422,
        details={"value": str(value)},
    )


def _table(client: Any, name: str) -> Any:
    return client.client.table(name)


def _single_row(data: Any, *, entity: str, key: str) -> dict[str, Any]:
    if not isinstance(data, list) or not data:
        raise AppError(
            code="not_found",
            message=f"{entity} not found",
            http_status=404,
            details={"key": key},
        )
    row = data[0]
    if not isinstance(row, dict):
        raise AppError(
            code="internal_error",
            message=f"Unexpected {entity} payload",
            http_status=500,
        )
    return row


def _audit_mutation(
    recorder: AdminAuditRecorder,
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    recorder.record(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
    )


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class CommissionRateOut(BaseModel):
    category_key: str
    rate_bps: int


class CommissionRateUpdate(BaseModel):
    rate_bps: int


class DeliveryZoneOut(BaseModel):
    zone_key: str
    label: str
    fee_ngwee: int
    active: bool


class DeliveryZoneUpdate(BaseModel):
    label: str | None = None
    fee_ngwee: int | None = None
    active: bool | None = None


class PlatformConfigOut(BaseModel):
    key: str
    value: int
    description: str | None = None


class PlatformConfigUpdate(BaseModel):
    value: int


class FeatureFlagOut(BaseModel):
    flag: str
    enabled: bool
    description: str | None = None


class FeatureFlagUpdate(BaseModel):
    enabled: bool


class CategoryOut(BaseModel):
    id: UUID
    parent_id: UUID | None
    name: str
    slug: str
    path: str
    commission_key: str
    prohibited: bool
    position: int


class CategoryUpdate(BaseModel):
    prohibited: bool | None = None
    position: int | None = None
    parent_id: UUID | None = Field(default=None)
    move_children: bool = False


class CategoryReorderItem(BaseModel):
    id: UUID
    parent_id: UUID | None = None
    position: int
    move_children: bool = False


class CategoryReorderRequest(BaseModel):
    moves: list[CategoryReorderItem] = Field(min_length=1)


# ---------------------------------------------------------------------------
# Commission rates
# ---------------------------------------------------------------------------
@config_router.get("/commissions", response_model=list[CommissionRateOut])
async def list_commission_rates(
    service_client: Annotated[Any, Depends(get_supabase_client)],
) -> list[CommissionRateOut]:
    response = (
        _table(service_client, "commission_rates")
        .select("*")
        .order("category_key")
        .execute()
    )
    rows = response.data if isinstance(response.data, list) else []
    return [CommissionRateOut.model_validate(row) for row in rows]


@config_router.patch("/commissions/{category_key}", response_model=CommissionRateOut)
async def update_commission_rate(
    category_key: str,
    body: CommissionRateUpdate,
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    service_client: Annotated[Any, Depends(get_supabase_client)],
) -> CommissionRateOut:
    validate_rate_bps(body.rate_bps)

    before_row = _single_row(
        _table(service_client, "commission_rates")
        .select("*")
        .eq("category_key", category_key)
        .execute()
        .data,
        entity="commission_rate",
        key=category_key,
    )

    response = (
        _table(service_client, "commission_rates")
        .update({"rate_bps": body.rate_bps})
        .eq("category_key", category_key)
        .execute()
    )
    after_row = _single_row(
        response.data,
        entity="commission_rate",
        key=category_key,
    )

    _audit_mutation(
        recorder,
        action="config.commission.update",
        entity_type="commission_rate",
        entity_id=category_key,
        before=before_row,
        after=after_row,
    )
    return CommissionRateOut.model_validate(after_row)


# ---------------------------------------------------------------------------
# Delivery zones
# ---------------------------------------------------------------------------
@config_router.get("/delivery-zones", response_model=list[DeliveryZoneOut])
async def list_delivery_zones(
    service_client: Annotated[Any, Depends(get_supabase_client)],
) -> list[DeliveryZoneOut]:
    response = _table(service_client, "delivery_zones").select("*").order("zone_key").execute()
    rows = response.data if isinstance(response.data, list) else []
    return [DeliveryZoneOut.model_validate(row) for row in rows]


@config_router.patch("/delivery-zones/{zone_key}", response_model=DeliveryZoneOut)
async def update_delivery_zone(
    zone_key: str,
    body: DeliveryZoneUpdate,
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    service_client: Annotated[Any, Depends(get_supabase_client)],
) -> DeliveryZoneOut:
    if body.fee_ngwee is not None:
        validate_zone_fee_ngwee(body.fee_ngwee)

    before_row = _single_row(
        _table(service_client, "delivery_zones")
        .select("*")
        .eq("zone_key", zone_key)
        .execute()
        .data,
        entity="delivery_zone",
        key=zone_key,
    )

    patch: dict[str, Any] = {}
    if body.label is not None:
        patch["label"] = body.label
    if body.fee_ngwee is not None:
        patch["fee_ngwee"] = body.fee_ngwee
    if body.active is not None:
        patch["active"] = body.active

    if not patch:
        raise AppError(
            code="validation_error",
            message="No fields to update",
            http_status=400,
        )

    response = (
        _table(service_client, "delivery_zones")
        .update(patch)
        .eq("zone_key", zone_key)
        .execute()
    )
    after_row = _single_row(response.data, entity="delivery_zone", key=zone_key)

    _audit_mutation(
        recorder,
        action="config.delivery_zone.update",
        entity_type="delivery_zone",
        entity_id=zone_key,
        before=before_row,
        after=after_row,
    )
    return DeliveryZoneOut.model_validate(after_row)


# ---------------------------------------------------------------------------
# Platform config
# ---------------------------------------------------------------------------
@config_router.get("/platform", response_model=list[PlatformConfigOut])
async def list_platform_config(
    service_client: Annotated[Any, Depends(get_supabase_client)],
) -> list[PlatformConfigOut]:
    response = (
        _table(service_client, "platform_config")
        .select("key,value,description")
        .in_("key", list(EDITABLE_PLATFORM_KEYS))
        .order("key")
        .execute()
    )
    rows = response.data if isinstance(response.data, list) else []
    result: list[PlatformConfigOut] = []
    for row in rows:
        result.append(
            PlatformConfigOut(
                key=str(row["key"]),
                value=_extract_json_int(row["value"]),
                description=row.get("description"),
            )
        )
    return result


@config_router.patch("/platform/{key}", response_model=PlatformConfigOut)
async def update_platform_config(
    key: str,
    body: PlatformConfigUpdate,
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    service_client: Annotated[Any, Depends(get_supabase_client)],
) -> PlatformConfigOut:
    if key not in EDITABLE_PLATFORM_KEYS:
        raise AppError(
            code="validation_error",
            message="platform config key is not editable",
            http_status=400,
            details={"key": key},
        )

    validate_platform_value(key, body.value)

    before_row = _single_row(
        _table(service_client, "platform_config").select("*").eq("key", key).execute().data,
        entity="platform_config",
        key=key,
    )
    before_value = _extract_json_int(before_row["value"])

    response = (
        _table(service_client, "platform_config")
        .update({"value": body.value})
        .eq("key", key)
        .execute()
    )
    after_row = _single_row(response.data, entity="platform_config", key=key)

    _audit_mutation(
        recorder,
        action="config.platform.update",
        entity_type="platform_config",
        entity_id=key,
        before={"key": key, "value": before_value},
        after={"key": key, "value": body.value},
    )
    return PlatformConfigOut(
        key=key,
        value=body.value,
        description=after_row.get("description"),
    )


# ---------------------------------------------------------------------------
# Feature flags
# ---------------------------------------------------------------------------
@config_router.get("/flags", response_model=list[FeatureFlagOut])
async def list_feature_flags(
    service_client: Annotated[Any, Depends(get_supabase_client)],
) -> list[FeatureFlagOut]:
    response = _table(service_client, "feature_flags").select("*").order("flag").execute()
    rows = response.data if isinstance(response.data, list) else []
    return [FeatureFlagOut.model_validate(row) for row in rows]


@config_router.patch("/flags/{flag}", response_model=FeatureFlagOut)
async def update_feature_flag(
    flag: str,
    body: FeatureFlagUpdate,
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    service_client: Annotated[Any, Depends(get_supabase_client)],
) -> FeatureFlagOut:
    before_row = _single_row(
        _table(service_client, "feature_flags").select("*").eq("flag", flag).execute().data,
        entity="feature_flag",
        key=flag,
    )

    response = (
        _table(service_client, "feature_flags")
        .update({"enabled": body.enabled})
        .eq("flag", flag)
        .execute()
    )
    after_row = _single_row(response.data, entity="feature_flag", key=flag)

    _audit_mutation(
        recorder,
        action="config.feature_flag.update",
        entity_type="feature_flag",
        entity_id=flag,
        before=before_row,
        after=after_row,
    )
    return FeatureFlagOut.model_validate(after_row)


# ---------------------------------------------------------------------------
# Category tree
# ---------------------------------------------------------------------------
def _load_categories(service_client: Any) -> list[dict[str, Any]]:
    response = (
        _table(service_client, "categories")
        .select(
            "id,parent_id,name,slug,path,commission_key,prohibited,position"
        )
        .order("position")
        .execute()
    )
    return response.data if isinstance(response.data, list) else []


def _children_of(categories: list[dict[str, Any]], parent_id: str) -> list[dict[str, Any]]:
    return [row for row in categories if str(row.get("parent_id")) == parent_id]


def _compute_path(
    categories_by_id: dict[str, dict[str, Any]],
    *,
    parent_id: str | None,
    slug: str,
) -> str:
    if parent_id is None:
        return slug
    parent = categories_by_id.get(parent_id)
    if parent is None:
        return slug
    return f"{parent['path']}/{slug}"


def _descendant_ids(categories: list[dict[str, Any]], root_id: str) -> list[str]:
    result: list[str] = []
    queue = [root_id]
    while queue:
        current = queue.pop(0)
        for child in categories:
            if str(child.get("parent_id")) == current:
                child_id = str(child["id"])
                result.append(child_id)
                queue.append(child_id)
    return result


@config_router.get("/categories", response_model=list[CategoryOut])
async def list_categories(
    service_client: Annotated[Any, Depends(get_supabase_client)],
) -> list[CategoryOut]:
    rows = _load_categories(service_client)
    return [CategoryOut.model_validate(row) for row in rows]


def _apply_category_parent_change(
    service_client: Any,
    *,
    category_id: str,
    new_parent_id: str | None,
    move_children: bool,
    categories: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    categories_by_id = {str(row["id"]): row for row in categories}
    target = categories_by_id.get(category_id)
    if target is None:
        raise AppError(
            code="not_found",
            message="category not found",
            http_status=404,
            details={"id": category_id},
        )

    children = _children_of(categories, category_id)
    parent_changing = (
        new_parent_id != str(target["parent_id"])
        if target.get("parent_id")
        else new_parent_id is not None
    )

    if parent_changing and children and not move_children:
        raise AppError(
            code="orphan_children",
            message="Category has children; set move_children=true to move subtree",
            http_status=409,
            details={
                "id": category_id,
                "child_ids": [str(child["id"]) for child in children],
            },
        )

    if new_parent_id == category_id:
        raise AppError(
            code="validation_error",
            message="Category cannot be its own parent",
            http_status=422,
            details={"parent_id": new_parent_id},
        )

    if new_parent_id is not None and new_parent_id not in categories_by_id:
        raise AppError(
            code="not_found",
            message="parent category not found",
            http_status=404,
            details={"parent_id": new_parent_id},
        )

    if new_parent_id is not None:
        descendants = set(_descendant_ids(categories, category_id))
        if new_parent_id in descendants:
            raise AppError(
                code="validation_error",
                message="Cannot move category under its own descendant",
                http_status=422,
                details={"parent_id": new_parent_id},
            )

    updated_rows: list[dict[str, Any]] = []
    slug = str(target["slug"])

    if parent_changing:
        target["parent_id"] = new_parent_id
        target["path"] = _compute_path(
            categories_by_id,
            parent_id=new_parent_id,
            slug=slug,
        )
        _table(service_client, "categories").update(
            {"parent_id": new_parent_id, "path": target["path"]}
        ).eq("id", category_id).execute()
        updated_rows.append(dict(target))

        if move_children and children:
            refreshed_by_id = {**categories_by_id, category_id: target}
            for child in children:
                child_id = str(child["id"])
                child_slug = str(child["slug"])
                child_path = _compute_path(
                    refreshed_by_id,
                    parent_id=category_id,
                    slug=child_slug,
                )
                child["path"] = child_path
                refreshed_by_id[child_id] = child
                _table(service_client, "categories").update({"path": child_path}).eq(
                    "id", child_id
                ).execute()
                updated_rows.append(dict(child))
                for grandchild_id in _descendant_ids(categories, child_id):
                    grandchild = refreshed_by_id[grandchild_id]
                    grand_path = _compute_path(
                        refreshed_by_id,
                        parent_id=str(grandchild.get("parent_id")),
                        slug=str(grandchild["slug"]),
                    )
                    grandchild["path"] = grand_path
                    refreshed_by_id[grandchild_id] = grandchild
                    _table(service_client, "categories").update({"path": grand_path}).eq(
                        "id", grandchild_id
                    ).execute()
                    updated_rows.append(dict(grandchild))

    return target, updated_rows


@config_router.patch("/categories/{category_id}", response_model=CategoryOut)
async def update_category(
    category_id: UUID,
    body: CategoryUpdate,
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    service_client: Annotated[Any, Depends(get_supabase_client)],
) -> CategoryOut:
    category_id_str = str(category_id)
    categories = _load_categories(service_client)
    before_row = _single_row(
        [row for row in categories if str(row["id"]) == category_id_str],
        entity="category",
        key=category_id_str,
    )

    patch: dict[str, Any] = {}
    if body.prohibited is not None:
        patch["prohibited"] = body.prohibited
    if body.position is not None:
        patch["position"] = body.position

    parent_provided = "parent_id" in body.model_fields_set
    if parent_provided:
        new_parent_id = str(body.parent_id) if body.parent_id is not None else None
        _apply_category_parent_change(
            service_client,
            category_id=category_id_str,
            new_parent_id=new_parent_id,
            move_children=body.move_children,
            categories=categories,
        )

    if patch:
        _table(service_client, "categories").update(patch).eq("id", category_id_str).execute()

    after_row = _single_row(
        _table(service_client, "categories")
        .select("id,parent_id,name,slug,path,commission_key,prohibited,position")
        .eq("id", category_id_str)
        .execute()
        .data,
        entity="category",
        key=category_id_str,
    )

    _audit_mutation(
        recorder,
        action="config.category.update",
        entity_type="category",
        entity_id=category_id_str,
        before=before_row,
        after=after_row,
    )
    return CategoryOut.model_validate(after_row)


@config_router.post("/categories/reorder", response_model=list[CategoryOut])
async def reorder_categories(
    body: CategoryReorderRequest,
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    service_client: Annotated[Any, Depends(get_supabase_client)],
) -> list[CategoryOut]:
    categories = _load_categories(service_client)
    before_snapshot = [dict(row) for row in categories]
    updated: list[CategoryOut] = []

    for move in body.moves:
        category_id_str = str(move.id)
        new_parent_id = str(move.parent_id) if move.parent_id is not None else None
        categories = _load_categories(service_client)
        _apply_category_parent_change(
            service_client,
            category_id=category_id_str,
            new_parent_id=new_parent_id,
            move_children=move.move_children,
            categories=categories,
        )
        _table(service_client, "categories").update({"position": move.position}).eq(
            "id", category_id_str
        ).execute()
        row = _single_row(
            _table(service_client, "categories")
            .select("id,parent_id,name,slug,path,commission_key,prohibited,position")
            .eq("id", category_id_str)
            .execute()
            .data,
            entity="category",
            key=category_id_str,
        )
        updated.append(CategoryOut.model_validate(row))

    after_snapshot = _load_categories(service_client)
    _audit_mutation(
        recorder,
        action="config.category.reorder",
        entity_type="category_tree",
        entity_id="reorder",
        before={"categories": before_snapshot},
        after={"categories": after_snapshot},
    )
    return updated


# ---------------------------------------------------------------------------
# FX rates, category product policy, Class-D release checklist
# ---------------------------------------------------------------------------

ALLOWED_PRODUCT_CLASSES = frozenset({"A", "B", "C", "D", "E"})


class FxRateOut(BaseModel):
    id: str
    rate_zmw_per_usd_micros: int
    vendor_margin_bps: int
    source: str
    source_reference: str | None = None
    effective_at: datetime
    expires_at: datetime
    stale: bool


class FxRatesResponse(BaseModel):
    current: FxRateOut | None = None
    history: list[FxRateOut] = Field(default_factory=list)


class PublishFxRateRequest(BaseModel):
    rate_zmw_per_usd_micros: int = Field(gt=0)
    vendor_margin_bps: int = Field(default=0, ge=0, le=5000)
    source: str = Field(min_length=1, max_length=160)
    source_reference: str | None = Field(default=None, max_length=240)
    effective_at: datetime
    expires_at: datetime


class CategoryPolicyOut(BaseModel):
    category_id: str
    category_name: str
    path: str
    phase: int
    enabled: bool
    allowed_product_classes: list[str]
    minimum_kyc_tier: int | None = None
    required_licence_types: list[str] = Field(default_factory=list)
    evidence_requirements: dict[str, Any] = Field(default_factory=dict)
    high_risk: bool = False


class CategoryPolicyPatch(BaseModel):
    phase: int | None = Field(default=None, ge=1, le=3)
    enabled: bool | None = None
    allowed_product_classes: list[Literal["A", "B", "C", "D", "E"]] | None = None
    minimum_kyc_tier: int | None = Field(default=None, ge=1, le=3)
    required_licence_types: list[str] | None = None
    evidence_requirements: dict[str, Any] | None = None
    high_risk: bool | None = None


class ClassDReadinessResponse(BaseModel):
    customer_release: bool
    operations_approved: bool
    escrow_hours: int
    shopper_visible: bool


def _fx_out(snapshot: Any) -> FxRateOut:
    return FxRateOut(
        id=snapshot.rate_id,
        rate_zmw_per_usd_micros=snapshot.rate_zmw_per_usd_micros,
        vendor_margin_bps=snapshot.vendor_margin_bps,
        source=snapshot.source,
        source_reference=snapshot.source_reference,
        effective_at=snapshot.effective_at,
        expires_at=snapshot.expires_at,
        stale=snapshot.stale,
    )


def _policy_classes(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return ["A", "B"]
    classes = [str(item).strip().upper() for item in raw if str(item).strip()]
    return [item for item in classes if item in ALLOWED_PRODUCT_CLASSES] or ["A", "B"]


@config_router.get("/fx-rates", response_model=FxRatesResponse)
async def list_fx_rates(
    service_client: Annotated[Any, Depends(get_supabase_client)],
) -> FxRatesResponse:
    from app.services.fx.rates import list_usd_zmw_rates, load_current_usd_zmw_rate

    current = load_current_usd_zmw_rate(service_client.client)
    history = list_usd_zmw_rates(service_client.client)
    return FxRatesResponse(
        current=_fx_out(current) if current is not None else None,
        history=[_fx_out(item) for item in history],
    )


@config_router.post("/fx-rates", response_model=FxRateOut)
async def publish_fx_rate(
    body: PublishFxRateRequest,
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[Any, Depends(get_supabase_client)],
) -> FxRateOut:
    from app.services.fx.rates import load_current_usd_zmw_rate, publish_usd_zmw_rate

    before = load_current_usd_zmw_rate(service_client.client)
    published = publish_usd_zmw_rate(
        service_client.client,
        rate_zmw_per_usd_micros=body.rate_zmw_per_usd_micros,
        vendor_margin_bps=body.vendor_margin_bps,
        source=body.source,
        source_reference=body.source_reference,
        effective_at=body.effective_at,
        expires_at=body.expires_at,
        created_by=current_user.id,
    )
    _audit_mutation(
        recorder,
        action="config.fx_rate.publish",
        entity_type="fx_rate",
        entity_id=published.rate_id,
        before=_fx_out(before).model_dump(mode="json") if before is not None else None,
        after=_fx_out(published).model_dump(mode="json"),
    )
    return _fx_out(published)


@config_router.get("/category-policies", response_model=list[CategoryPolicyOut])
async def list_category_policies(
    service_client: Annotated[Any, Depends(get_supabase_client)],
) -> list[CategoryPolicyOut]:
    categories = _load_categories(service_client)
    response = (
        _table(service_client, "category_product_policies")
        .select(
            "category_id, phase, enabled, allowed_product_classes, minimum_kyc_tier, "
            "required_licence_types, evidence_requirements, high_risk"
        )
        .execute()
    )
    rows = response.data if isinstance(response.data, list) else []
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("category_id"), str):
            by_id[str(row["category_id"])] = row

    out: list[CategoryPolicyOut] = []
    for category in categories:
        category_id = str(category["id"])
        policy = by_id.get(category_id, {})
        out.append(
            CategoryPolicyOut(
                category_id=category_id,
                category_name=str(category.get("name") or ""),
                path=str(category.get("path") or ""),
                phase=int(policy.get("phase") or 1),
                enabled=bool(policy["enabled"]) if "enabled" in policy else True,
                allowed_product_classes=_policy_classes(policy.get("allowed_product_classes")),
                minimum_kyc_tier=(
                    int(policy["minimum_kyc_tier"])
                    if isinstance(policy.get("minimum_kyc_tier"), int)
                    else None
                ),
                required_licence_types=(
                    [str(item) for item in policy["required_licence_types"]]
                    if isinstance(policy.get("required_licence_types"), list)
                    else []
                ),
                evidence_requirements=(
                    policy["evidence_requirements"]
                    if isinstance(policy.get("evidence_requirements"), dict)
                    else {}
                ),
                high_risk=bool(policy.get("high_risk")),
            )
        )
    return out


@config_router.patch(
    "/category-policies/{category_id}",
    response_model=CategoryPolicyOut,
)
async def patch_category_policy(
    category_id: UUID,
    body: CategoryPolicyPatch,
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    service_client: Annotated[Any, Depends(get_supabase_client)],
) -> CategoryPolicyOut:
    category_id_str = str(category_id)
    category = _single_row(
        _table(service_client, "categories")
        .select("id,name,path")
        .eq("id", category_id_str)
        .execute()
        .data,
        entity="category",
        key=category_id_str,
    )
    existing_response = (
        _table(service_client, "category_product_policies")
        .select(
            "category_id, phase, enabled, allowed_product_classes, minimum_kyc_tier, "
            "required_licence_types, evidence_requirements, high_risk"
        )
        .eq("category_id", category_id_str)
        .execute()
    )
    existing_rows = existing_response.data if isinstance(existing_response.data, list) else []
    existing = existing_rows[0] if existing_rows and isinstance(existing_rows[0], dict) else None
    patch: dict[str, Any] = {}
    if body.phase is not None:
        patch["phase"] = body.phase
    if body.enabled is not None:
        patch["enabled"] = body.enabled
    if body.allowed_product_classes is not None:
        patch["allowed_product_classes"] = list(body.allowed_product_classes)
    if body.minimum_kyc_tier is not None:
        patch["minimum_kyc_tier"] = body.minimum_kyc_tier
    if body.required_licence_types is not None:
        patch["required_licence_types"] = body.required_licence_types
    if body.evidence_requirements is not None:
        patch["evidence_requirements"] = body.evidence_requirements
    if body.high_risk is not None:
        patch["high_risk"] = body.high_risk
    if not patch:
        raise AppError(
            code="validation_error",
            message="No fields to update",
            http_status=400,
        )

    if existing is None:
        payload = {
            "category_id": category_id_str,
            "phase": patch.get("phase", 1),
            "enabled": patch.get("enabled", False),
            "allowed_product_classes": patch.get("allowed_product_classes", ["A", "B"]),
            "minimum_kyc_tier": patch.get("minimum_kyc_tier"),
            "required_licence_types": patch.get("required_licence_types", []),
            "evidence_requirements": patch.get("evidence_requirements", {}),
            "high_risk": patch.get("high_risk", False),
        }
        _table(service_client, "category_product_policies").insert(payload).execute()
        after = payload
    else:
        _table(service_client, "category_product_policies").update(patch).eq(
            "category_id", category_id_str
        ).execute()
        after = {**existing, **patch}

    _audit_mutation(
        recorder,
        action="config.category_policy.update",
        entity_type="category_product_policy",
        entity_id=category_id_str,
        before=existing,
        after=after,
    )
    return CategoryPolicyOut(
        category_id=category_id_str,
        category_name=str(category.get("name") or ""),
        path=str(category.get("path") or ""),
        phase=int(after.get("phase") or 1),
        enabled=bool(after.get("enabled")),
        allowed_product_classes=_policy_classes(after.get("allowed_product_classes")),
        minimum_kyc_tier=(
            int(after["minimum_kyc_tier"])
            if isinstance(after.get("minimum_kyc_tier"), int)
            else None
        ),
        required_licence_types=(
            [str(item) for item in after["required_licence_types"]]
            if isinstance(after.get("required_licence_types"), list)
            else []
        ),
        evidence_requirements=(
            after["evidence_requirements"]
            if isinstance(after.get("evidence_requirements"), dict)
            else {}
        ),
        high_risk=bool(after.get("high_risk")),
    )


@config_router.get("/class-d-readiness", response_model=ClassDReadinessResponse)
async def get_class_d_readiness(
    service_client: Annotated[Any, Depends(get_supabase_client)],
) -> ClassDReadinessResponse:
    flags = (
        _table(service_client, "feature_flags")
        .select("flag, enabled")
        .in_(
            "flag",
            [
                "product_class_d_customer_release",
                "product_class_d_operations_approved",
            ],
        )
        .execute()
    )
    enabled = {
        str(row.get("flag"))
        for row in (flags.data if isinstance(flags.data, list) else [])
        if isinstance(row, dict) and row.get("enabled") is True
    }
    config = (
        _table(service_client, "platform_config")
        .select("key, value")
        .eq("key", "product_class_d_escrow_hours")
        .execute()
    )
    escrow_hours = 72
    config_rows = config.data if isinstance(config.data, list) else []
    if config_rows and isinstance(config_rows[0], dict):
        raw = config_rows[0].get("value")
        if isinstance(raw, int):
            escrow_hours = raw
        elif isinstance(raw, str) and raw.isdigit():
            escrow_hours = int(raw)
    customer_release = "product_class_d_customer_release" in enabled
    operations_approved = "product_class_d_operations_approved" in enabled
    return ClassDReadinessResponse(
        customer_release=customer_release,
        operations_approved=operations_approved,
        escrow_hours=escrow_hours,
        shopper_visible=customer_release and operations_approved,
    )


# Mount on admin_base so authz + audit route class apply automatically.
admin_router.include_router(config_router)
