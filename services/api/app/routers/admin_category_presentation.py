"""Admin editing of category icons, banners and banner copy.

Mounted on the shared ``/admin`` router (``require_admin_scope`` + audited route
class), under ``/config`` like the rest of the category tree. These routes are
not mapped to an ``rbac_*`` permission, so only the unrestricted ``admin`` and
``superadmin`` roles reach them (same as ``PATCH /admin/config/categories``).

Images are uploaded straight from the browser to Cloudinary with a signature
from ``POST /admin/config/category-media/sign``. The signature pins the upload
to the ``categories/icons`` or ``categories/banners`` folder, so an admin does
not need a vendor profile (the vendor ``/media/sign`` route requires one).
"""

from __future__ import annotations

import time
from typing import Annotated, Any, Literal
from uuid import UUID

from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.errors import AppError
from app.media.cloudinary_signing import DEFAULT_ALLOWED_FORMATS, build_signed_params
from app.routers.admin_base import router as admin_router
from app.services.categories.presentation import (
    PRESENTATION_COLUMNS,
    TABLE,
    CategoryPresentationOut,
    CategoryPresentationUpsert,
    invalidate_public_presentations_cache,
    load_presentations,
    row_to_presentation,
)
from app.settings import Settings, get_settings
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

presentation_router = APIRouter(prefix="/config", tags=["admin-config"])

#: Icons are small; banners are wide hero images. Both are downscaled in the
#: browser before upload, so these are ceilings, not targets.
MAX_ICON_BYTES = 2_097_152
MAX_BANNER_BYTES = 5_242_880
MEDIA_FOLDERS: dict[str, str] = {"icon": "categories/icons", "banner": "categories/banners"}
MEDIA_MAX_BYTES: dict[str, int] = {"icon": MAX_ICON_BYTES, "banner": MAX_BANNER_BYTES}


class CategoryMediaSignRequest(BaseModel):
    model_config = {"extra": "forbid"}

    kind: Literal["icon", "banner"]
    file_size_bytes: int | None = Field(default=None, ge=1)


class CategoryMediaSignResponse(BaseModel):
    cloud_name: str
    api_key: str
    timestamp: int
    signature: str
    folder: str
    allowed_formats: str
    max_file_size: int


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    return [dict(row) for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def _load_category(service_client: Any, category_id: str) -> dict[str, Any]:
    rows = _rows(
        service_client.client.table("categories")
        .select("id, slug")
        .eq("id", category_id)
        .limit(1)
        .execute()
    )
    if not rows:
        raise AppError(
            code="not_found",
            message="category not found",
            http_status=404,
            details={"id": category_id},
        )
    return rows[0]


def _load_presentation_row(service_client: Any, category_id: str) -> dict[str, Any] | None:
    rows = _rows(
        service_client.client.table(TABLE)
        .select(PRESENTATION_COLUMNS)
        .eq("category_id", category_id)
        .limit(1)
        .execute()
    )
    return rows[0] if rows else None


def _audit_view(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row.get(key) for key in row if key != "updated_at"}


@presentation_router.get("/categories/presentations", response_model=list[CategoryPresentationOut])
async def list_category_presentations(
    service_client: Annotated[Any, Depends(get_supabase_client)],
) -> list[CategoryPresentationOut]:
    """Every saved presentation, including prohibited categories (admin view)."""
    return load_presentations(service_client.client, public_only=False)


@presentation_router.put(
    "/categories/{category_id}/presentation", response_model=CategoryPresentationOut
)
async def upsert_category_presentation(
    category_id: UUID,
    body: CategoryPresentationUpsert,
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[Any, Depends(get_supabase_client)],
) -> CategoryPresentationOut:
    category_id_str = str(category_id)
    category = _load_category(service_client, category_id_str)
    if body.is_empty():
        raise AppError(
            code="validation_error",
            message="Set an icon, a banner or banner text, or delete the presentation",
            http_status=422,
        )
    before = _load_presentation_row(service_client, category_id_str)
    payload = {
        "category_id": category_id_str,
        "icon_public_id": body.icon_public_id,
        "banner_public_id": body.banner_public_id,
        "banner_title_i18n": body.banner_title_i18n,
        "banner_description_i18n": body.banner_description_i18n,
        "updated_by": current_user.id,
    }
    rows = _rows(
        service_client.client.table(TABLE).upsert(payload, on_conflict="category_id").execute()
    )
    after = rows[0] if rows else _load_presentation_row(service_client, category_id_str)
    if after is None:
        raise AppError(
            code="internal_error",
            message="category presentation write returned no row",
            http_status=500,
        )
    invalidate_public_presentations_cache()
    recorder.record(
        action="config.category_presentation.upsert",
        entity_type="category_presentation",
        entity_id=category_id_str,
        before=_audit_view(before),
        after=_audit_view(after),
    )
    return row_to_presentation(after, str(category["slug"]))


@presentation_router.delete("/categories/{category_id}/presentation", status_code=204)
async def delete_category_presentation(
    category_id: UUID,
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    service_client: Annotated[Any, Depends(get_supabase_client)],
) -> None:
    category_id_str = str(category_id)
    _load_category(service_client, category_id_str)
    before = _load_presentation_row(service_client, category_id_str)
    if before is None:
        raise AppError(
            code="not_found",
            message="category presentation not found",
            http_status=404,
            details={"id": category_id_str},
        )
    service_client.client.table(TABLE).delete().eq("category_id", category_id_str).execute()
    invalidate_public_presentations_cache()
    recorder.record(
        action="config.category_presentation.delete",
        entity_type="category_presentation",
        entity_id=category_id_str,
        before=_audit_view(before),
        after=None,
    )


@presentation_router.post("/category-media/sign", response_model=CategoryMediaSignResponse)
async def sign_category_media_upload(
    body: CategoryMediaSignRequest,
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CategoryMediaSignResponse:
    max_bytes = MEDIA_MAX_BYTES[body.kind]
    if body.file_size_bytes is not None and body.file_size_bytes > max_bytes:
        raise AppError(
            code="file_too_large",
            message="Requested file exceeds the maximum allowed upload size",
            http_status=400,
            details={"file_size_bytes": body.file_size_bytes, "max_bytes": max_bytes},
        )
    try:
        cloud_name = settings.cloudinary_cloud_name
        api_key = settings.cloudinary_api_key
        api_secret = settings.cloudinary_api_secret
    except ValueError as exc:
        raise AppError(
            code="configuration_error",
            message="Cloudinary is not configured",
            http_status=503,
        ) from exc

    folder = MEDIA_FOLDERS[body.kind]
    signed = build_signed_params(
        folder=folder,
        public_id=None,
        timestamp=int(time.time()),
        api_secret=api_secret,
        allowed_formats=DEFAULT_ALLOWED_FORMATS,
        max_bytes=max_bytes,
    )
    recorder.record(
        action="config.category_media.sign",
        entity_type="category_media",
        entity_id=body.kind,
        before=None,
        after={"folder": folder, "max_file_size": max_bytes},
    )
    return CategoryMediaSignResponse(
        cloud_name=cloud_name,
        api_key=api_key,
        timestamp=int(signed["timestamp"]),
        signature=str(signed["signature"]),
        folder=str(signed["folder"]),
        allowed_formats=str(signed["allowed_formats"]),
        max_file_size=int(signed["max_file_size"]),
    )


admin_router.include_router(presentation_router)
