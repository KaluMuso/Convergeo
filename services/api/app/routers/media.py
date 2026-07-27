from __future__ import annotations

import re
import time
from typing import Annotated, Literal

from app.errors import AppError
from app.media.authz import VendorScope, require_vendor_scope
from app.media.cloudinary_signing import (
    DEFAULT_ALLOWED_FORMATS,
    MAX_CLIP_BYTES,
    build_signed_clip_params,
    build_signed_params,
)
from app.settings import Settings, get_settings
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

router = APIRouter(prefix="/media", tags=["media"])

MAX_LISTING_IMAGE_BYTES = 10_485_760
# M17-P02: "clip" is a DISTINCT kind with its own preset, cap, formats and
# folder. The image ceiling above is untouched — a video preset must never
# reach the listing path, and keeping the kinds separate is what guarantees it.
SUPPORTED_RESOURCE_KINDS = frozenset({"listing", "clip"})
PUBLIC_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


class SignUploadRequest(BaseModel):
    resource_kind: Literal["listing", "clip"]
    public_id: str | None = None
    file_size_bytes: int | None = Field(default=None, ge=1)
    folder: str | None = None


class SignUploadResponse(BaseModel):
    cloud_name: str
    api_key: str
    timestamp: int
    signature: str
    folder: str
    allowed_formats: str
    max_file_size: int
    # Returned only when a public_id was requested (and therefore signed). Kept in
    # sync with the signed params so a client that requests a public_id can also SEND
    # it — a signed-but-unreturned param would reproduce the #416 "Invalid Signature".
    public_id: str | None = None
    # M17-P02 clip preset. These are SIGNED, so they must also be returned: the
    # client has to send back every parameter that went into the signature or
    # Cloudinary rejects the upload with #416. This is the same trap the
    # public_id note above records, and adding eager/notification params is
    # exactly where it would reappear.
    eager: str | None = None
    eager_async: str | None = None
    eager_notification_url: str | None = None
    notification_url: str | None = None
    duration: int | None = None


def _sanitize_public_id(public_id: str | None) -> str | None:
    if public_id is None:
        return None

    trimmed = public_id.strip()
    if not trimmed:
        raise AppError(
            code="validation_error",
            message="public_id must not be empty",
            http_status=400,
        )

    if "/" in trimmed or "\\" in trimmed or ".." in trimmed:
        raise AppError(
            code="validation_error",
            message="public_id must not contain path segments",
            http_status=400,
            details={"public_id": public_id},
        )

    if not PUBLIC_ID_PATTERN.fullmatch(trimmed):
        raise AppError(
            code="validation_error",
            message="public_id contains invalid characters",
            http_status=400,
            details={"public_id": public_id},
        )

    return trimmed


def _resolve_folder(scope: VendorScope, resource_kind: str) -> str:
    if resource_kind == "listing":
        return f"listings/{scope.vendor_id}"
    if resource_kind == "clip":
        # Vendor-scoped folder, same shape as listings: a vendor can only ever be
        # signed into their own prefix.
        return f"clips/{scope.vendor_id}"
    raise AppError(
        code="unsupported_resource_kind",
        message="Unsupported resource kind",
        http_status=400,
        details={"resource_kind": resource_kind},
    )


def _validate_request(
    request: SignUploadRequest,
    scope: VendorScope,
) -> tuple[str, str | None, int]:
    if request.resource_kind not in SUPPORTED_RESOURCE_KINDS:
        raise AppError(
            code="unsupported_resource_kind",
            message="Unsupported resource kind",
            http_status=400,
            details={"resource_kind": request.resource_kind},
        )

    max_bytes = MAX_CLIP_BYTES if request.resource_kind == "clip" else MAX_LISTING_IMAGE_BYTES

    if request.file_size_bytes is not None and request.file_size_bytes > max_bytes:
        raise AppError(
            code="file_too_large",
            message="Requested file exceeds the maximum allowed upload size",
            http_status=400,
            details={
                "file_size_bytes": request.file_size_bytes,
                "max_bytes": max_bytes,
            },
        )

    folder = _resolve_folder(scope, request.resource_kind)
    public_id = _sanitize_public_id(request.public_id)
    return folder, public_id, max_bytes


@router.post("/sign", response_model=SignUploadResponse)
async def sign_upload(
    body: SignUploadRequest,
    scope: Annotated[VendorScope, Depends(require_vendor_scope)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SignUploadResponse:
    folder, public_id, max_bytes = _validate_request(body, scope)
    timestamp = int(time.time())

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

    if body.resource_kind == "clip":
        signed = build_signed_clip_params(
            folder=folder,
            public_id=public_id,
            timestamp=timestamp,
            api_secret=api_secret,
        )
    else:
        signed = build_signed_params(
            folder=folder,
            public_id=public_id,
            timestamp=timestamp,
            api_secret=api_secret,
            allowed_formats=DEFAULT_ALLOWED_FORMATS,
            max_bytes=max_bytes,
        )

    return SignUploadResponse(
        cloud_name=cloud_name,
        api_key=api_key,
        timestamp=int(signed["timestamp"]),
        signature=str(signed["signature"]),
        folder=str(signed["folder"]),
        allowed_formats=str(signed["allowed_formats"]),
        max_file_size=int(signed["max_file_size"]),
        public_id=str(signed["public_id"]) if signed.get("public_id") else None,
        eager=str(signed["eager"]) if signed.get("eager") else None,
        eager_async=str(signed["eager_async"]) if signed.get("eager_async") else None,
        eager_notification_url=(
            str(signed["eager_notification_url"])
            if signed.get("eager_notification_url")
            else None
        ),
        notification_url=(
            str(signed["notification_url"]) if signed.get("notification_url") else None
        ),
        duration=int(signed["duration"]) if signed.get("duration") else None,
    )
