from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.errors import AppError
from app.routers.admin_base import router as admin_router
from app.supabase_client import SupabaseServiceClient, get_supabase_service_client
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


def _table(client: SupabaseServiceClient, name: str) -> Any:
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
    service_client: Annotated[SupabaseServiceClient, Depends(get_supabase_service_client)],
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
    service_client: Annotated[SupabaseServiceClient, Depends(get_supabase_service_client)],
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
    service_client: Annotated[SupabaseServiceClient, Depends(get_supabase_service_client)],
) -> list[DeliveryZoneOut]:
    response = _table(service_client, "delivery_zones").select("*").order("zone_key").execute()
    rows = response.data if isinstance(response.data, list) else []
    return [DeliveryZoneOut.model_validate(row) for row in rows]


@config_router.patch("/delivery-zones/{zone_key}", response_model=DeliveryZoneOut)
async def update_delivery_zone(
    zone_key: str,
    body: DeliveryZoneUpdate,
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    service_client: Annotated[SupabaseServiceClient, Depends(get_supabase_service_client)],
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
    service_client: Annotated[SupabaseServiceClient, Depends(get_supabase_service_client)],
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
    service_client: Annotated[SupabaseServiceClient, Depends(get_supabase_service_client)],
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
    service_client: Annotated[SupabaseServiceClient, Depends(get_supabase_service_client)],
) -> list[FeatureFlagOut]:
    response = _table(service_client, "feature_flags").select("*").order("flag").execute()
    rows = response.data if isinstance(response.data, list) else []
    return [FeatureFlagOut.model_validate(row) for row in rows]


@config_router.patch("/flags/{flag}", response_model=FeatureFlagOut)
async def update_feature_flag(
    flag: str,
    body: FeatureFlagUpdate,
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    service_client: Annotated[SupabaseServiceClient, Depends(get_supabase_service_client)],
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
def _load_categories(service_client: SupabaseServiceClient) -> list[dict[str, Any]]:
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
    service_client: Annotated[SupabaseServiceClient, Depends(get_supabase_service_client)],
) -> list[CategoryOut]:
    rows = _load_categories(service_client)
    return [CategoryOut.model_validate(row) for row in rows]


def _apply_category_parent_change(
    service_client: SupabaseServiceClient,
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
    service_client: Annotated[SupabaseServiceClient, Depends(get_supabase_service_client)],
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
    service_client: Annotated[SupabaseServiceClient, Depends(get_supabase_service_client)],
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


# Mount on admin_base so authz + audit route class apply automatically.
admin_router.include_router(config_router)
