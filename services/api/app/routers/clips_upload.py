"""M17-P02 — vendor clip upload: draft creation + signed direct upload.

The API **never proxies video bytes**. It creates a `draft` row, screens the
caption, and hands back signed parameters so the vendor's browser uploads
straight to Cloudinary. That is what keeps an 80 MB upload off the OCI
always-free box entirely.

Order matters here, and it is the opposite of the obvious one: the **caption is
screened before an upload slot is issued**. Screening after upload would mean
paying to store and transcode content we were always going to reject, and would
leave prohibited bytes sitting in the account in the meantime.

This pebble has no path to `published` (D-V8). The furthest a clip can travel
from here is `screening`.
"""

from __future__ import annotations

import time
from typing import Annotated, Any, Final, Protocol

from app.deps import get_supabase_client
from app.errors import AppError
from app.media.authz import VendorScope, require_vendor_scope
from app.media.cloudinary_signing import (
    MAX_CLIP_BYTES,
    MAX_CLIP_DURATION_S,
    build_signed_clip_params,
)
from app.schemas.base import StrictModel
from app.services.clips import screen, state_machine
from app.settings import Settings, get_settings
from fastapi import APIRouter, Depends
from pydantic import Field

router = APIRouter(prefix="/clips", tags=["clips"])

CLIPS_TABLE: Final = "video_clips"
CATEGORIES_TABLE: Final = "categories"


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class ClipCreateRequest(StrictModel):
    caption: str | None = Field(default=None, max_length=screen.MAX_CAPTION_LEN)
    category_id: str | None = None
    public_id: str | None = None
    file_size_bytes: int | None = Field(default=None, ge=1)
    duration_s: int | None = Field(default=None, ge=1)


class ClipCreateResponse(StrictModel):
    clip_id: str
    status: str
    cloud_name: str
    api_key: str
    timestamp: int
    signature: str
    folder: str
    allowed_formats: str
    max_file_size: int
    eager: str
    eager_async: str
    duration: int
    public_id: str | None = None
    notification_url: str | None = None
    eager_notification_url: str | None = None


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _category_name(service_client: ServiceRoleClient, category_id: str | None) -> str | None:
    """Resolve the category so the D8 category fence has something to match."""
    if not category_id:
        return None
    rows = _rows(
        service_client.client.table(CATEGORIES_TABLE)
        .select("id, name, prohibited")
        .eq("id", category_id)
        .maybe_single()
        .execute()
    )
    if not rows:
        raise AppError(
            code="not_found",
            message="Category not found",
            http_status=404,
            details={"category_id": category_id},
        )
    if bool(rows[0].get("prohibited")):
        raise AppError(
            code="prohibited_clip",
            message="Clips are not permitted in this category",
            http_status=422,
            details={"reason": "category"},
        )
    return str(rows[0].get("name") or "")


@router.post("", response_model=ClipCreateResponse)
async def create_clip(
    body: ClipCreateRequest,
    scope: Annotated[VendorScope, Depends(require_vendor_scope)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ClipCreateResponse:
    """Create a draft clip and return signed upload parameters.

    ``require_vendor_scope`` is the D-V7 gate: only a KYC-verified vendor with an
    owned vendor row reaches this, and the folder it signs into is derived from
    that row rather than from anything the caller sent.
    """
    # D-V3, checked before anything is created or signed.
    if body.file_size_bytes is not None and body.file_size_bytes > MAX_CLIP_BYTES:
        raise AppError(
            code="file_too_large",
            message="Clip exceeds the maximum upload size",
            http_status=400,
            details={"max_bytes": MAX_CLIP_BYTES, "file_size_bytes": body.file_size_bytes},
        )
    if body.duration_s is not None and body.duration_s > MAX_CLIP_DURATION_S:
        raise AppError(
            code="clip_too_long",
            message="Clip exceeds the maximum duration",
            http_status=400,
            details={"max_duration_s": MAX_CLIP_DURATION_S, "duration_s": body.duration_s},
        )

    category_name = _category_name(service_client, body.category_id)

    # Screen FIRST. A prohibited caption never receives an upload slot, so we
    # never pay to store or transcode something we would reject anyway.
    verdict = screen.screen_text(body.caption, category_name)
    if not verdict.allowed:
        raise AppError(
            code="prohibited_clip",
            message="Clip caption or category is not permitted",
            http_status=422,
            details={"reason": verdict.reason, "matched": verdict.matched},
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

    created = _rows(
        service_client.client.table(CLIPS_TABLE)
        .insert(
            {
                "vendor_id": scope.vendor_id,
                "status": state_machine.DRAFT,
                "caption": body.caption,
                "category_id": body.category_id,
                "duration_s": body.duration_s,
            }
        )
        .execute()
    )
    if not created:
        raise AppError(
            code="internal_error",
            message="Failed to create clip draft",
            http_status=500,
        )
    clip_id = str(created[0]["id"])

    signed = build_signed_clip_params(
        folder=f"clips/{scope.vendor_id}",
        # The clip id is the public id: it is server-generated, so a caller
        # cannot steer the upload at another vendor's object.
        public_id=clip_id,
        timestamp=int(time.time()),
        api_secret=api_secret,
        notification_url=settings.cloudinary_notification_url or None,
    )

    # The draft is now waiting for bytes; the callback moves it onward.
    moved = state_machine.start_screening(service_client, clip_id=clip_id)

    return ClipCreateResponse(
        clip_id=clip_id,
        status=str(moved.get("status", state_machine.SCREENING)),
        cloud_name=cloud_name,
        api_key=api_key,
        timestamp=int(signed["timestamp"]),
        signature=str(signed["signature"]),
        folder=str(signed["folder"]),
        allowed_formats=str(signed["allowed_formats"]),
        max_file_size=int(signed["max_file_size"]),
        eager=str(signed["eager"]),
        eager_async=str(signed["eager_async"]),
        duration=int(signed["duration"]),
        public_id=str(signed["public_id"]) if signed.get("public_id") else None,
        notification_url=(
            str(signed["notification_url"]) if signed.get("notification_url") else None
        ),
        eager_notification_url=(
            str(signed["eager_notification_url"])
            if signed.get("eager_notification_url")
            else None
        ),
    )
