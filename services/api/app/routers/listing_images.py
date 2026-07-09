from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.errors import AppError
from app.services.kyc.state_machine import ServiceRoleClient
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

router = APIRouter(prefix="/vendor/listings", tags=["listing-images"])

MAX_IMAGES_PER_LISTING = 8
EDITABLE_LISTING_STATUSES = frozenset({"draft", "active", "paused"})


class ListingImageResponse(BaseModel):
    id: str
    listing_id: str
    cloudinary_public_id: str
    position: int


class AttachImageRequest(BaseModel):
    cloudinary_public_id: str = Field(min_length=1, max_length=500)
    position: int | None = Field(default=None, ge=1, le=MAX_IMAGES_PER_LISTING)

    @field_validator("cloudinary_public_id")
    @classmethod
    def validate_public_id(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("cloudinary_public_id must not be empty")
        if ".." in trimmed or trimmed.startswith("/"):
            raise ValueError("cloudinary_public_id is invalid")
        return trimmed


class ReorderImagesRequest(BaseModel):
    image_ids: list[str] = Field(min_length=1, max_length=MAX_IMAGES_PER_LISTING)

    @field_validator("image_ids")
    @classmethod
    def validate_unique_ids(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("image_ids must be unique")
        return value


def _parse_uuid(value: str, *, field_name: str) -> str:
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise AppError(
            code="validation_error",
            message=f"Invalid {field_name}",
            http_status=400,
            details={field_name: value},
        ) from exc


def _load_vendor_for_owner(
    service_client: ServiceRoleClient,
    owner_user_id: str,
) -> dict[str, Any]:
    response = (
        service_client.client.table("vendors")
        .select("id, owner_user_id, status")
        .eq("owner_user_id", owner_user_id)
        .maybe_single()
        .execute()
    )
    if response is None:
        raise AppError(
            code="internal_error",
            message="Vendor lookup failed",
            http_status=500,
        )

    data = response.data
    row: dict[str, Any] | None
    if isinstance(data, dict):
        row = data
    elif isinstance(data, list) and data and isinstance(data[0], dict):
        row = data[0]
    else:
        row = None

    if row is None:
        raise AppError(
            code="forbidden",
            message="Authenticated user does not own a vendor profile",
            http_status=403,
            details={"message_key": "vendor.errors.not_found"},
        )
    return row


def _load_listing(
    service_client: ServiceRoleClient,
    listing_id: str,
) -> dict[str, Any]:
    response = (
        service_client.client.table("vendor_listings")
        .select("id, vendor_id, status")
        .eq("id", listing_id)
        .maybe_single()
        .execute()
    )
    if response is None:
        raise AppError(
            code="internal_error",
            message="Listing lookup failed",
            http_status=500,
        )

    data = response.data
    row: dict[str, Any] | None
    if isinstance(data, dict):
        row = data
    elif isinstance(data, list) and data and isinstance(data[0], dict):
        row = data[0]
    else:
        row = None

    if row is None:
        raise AppError(
            code="not_found",
            message="Listing not found",
            http_status=404,
            details={"listing_id": listing_id},
        )
    return row


def _assert_listing_owned_by_vendor(
    listing: dict[str, Any],
    vendor_id: str,
    *,
    listing_id: str,
) -> None:
    if str(listing.get("vendor_id")) != vendor_id:
        raise AppError(
            code="forbidden",
            message="Listing does not belong to the authenticated vendor",
            http_status=403,
            details={"listing_id": listing_id, "vendor_id": vendor_id},
        )


def _assert_listing_editable(listing: dict[str, Any], *, listing_id: str) -> None:
    status = str(listing.get("status", ""))
    if status not in EDITABLE_LISTING_STATUSES:
        raise AppError(
            code="listing_not_editable",
            message="Listing status does not allow image changes",
            http_status=409,
            details={"listing_id": listing_id, "status": status},
        )


def _list_images(
    service_client: ServiceRoleClient,
    listing_id: str,
) -> list[dict[str, Any]]:
    response = (
        service_client.client.table("listing_images")
        .select("id, listing_id, cloudinary_public_id, position")
        .eq("listing_id", listing_id)
        .order("position")
        .execute()
    )
    data = response.data if response is not None else []
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def _next_position(images: list[dict[str, Any]]) -> int:
    if not images:
        return 1
    return max(int(row.get("position", 0)) for row in images) + 1


def _enforce_image_cap(images: list[dict[str, Any]], *, listing_id: str) -> None:
    if len(images) >= MAX_IMAGES_PER_LISTING:
        raise AppError(
            code="image_limit_reached",
            message="A listing cannot have more than 8 images",
            http_status=400,
            details={
                "listing_id": listing_id,
                "max_images": MAX_IMAGES_PER_LISTING,
                "message_key": "vendor.listings.images.limit_reached",
            },
        )


def _serialize_image(row: dict[str, Any]) -> ListingImageResponse:
    return ListingImageResponse(
        id=str(row["id"]),
        listing_id=str(row["listing_id"]),
        cloudinary_public_id=str(row["cloudinary_public_id"]),
        position=int(row["position"]),
    )


async def _require_owned_listing(
    listing_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> tuple[dict[str, Any], dict[str, Any]]:
    parsed_listing_id = _parse_uuid(listing_id, field_name="listing_id")
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    listing = _load_listing(service_client, parsed_listing_id)
    _assert_listing_owned_by_vendor(
        listing,
        str(vendor["id"]),
        listing_id=parsed_listing_id,
    )
    _assert_listing_editable(listing, listing_id=parsed_listing_id)
    return vendor, listing


@router.post("/{listing_id}/images", response_model=ListingImageResponse)
async def attach_listing_image(
    listing_id: str,
    body: AttachImageRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ListingImageResponse:
    parsed_listing_id = _parse_uuid(listing_id, field_name="listing_id")
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    listing = _load_listing(service_client, parsed_listing_id)
    _assert_listing_owned_by_vendor(
        listing,
        str(vendor["id"]),
        listing_id=parsed_listing_id,
    )
    _assert_listing_editable(listing, listing_id=parsed_listing_id)

    existing = _list_images(service_client, parsed_listing_id)
    _enforce_image_cap(existing, listing_id=parsed_listing_id)

    position = body.position if body.position is not None else _next_position(existing)
    if position < 1 or position > MAX_IMAGES_PER_LISTING:
        raise AppError(
            code="validation_error",
            message="position must be between 1 and 8",
            http_status=400,
            details={"position": position},
        )
    if any(int(row.get("position", 0)) == position for row in existing):
        raise AppError(
            code="validation_error",
            message="position is already taken",
            http_status=400,
            details={"position": position},
        )

    response = (
        service_client.client.table("listing_images")
        .insert(
            {
                "listing_id": parsed_listing_id,
                "cloudinary_public_id": body.cloudinary_public_id,
                "position": position,
            }
        )
        .execute()
    )
    data = response.data if response is not None else None
    row: dict[str, Any] | None = None
    if isinstance(data, list) and data and isinstance(data[0], dict):
        row = data[0]
    elif isinstance(data, dict):
        row = data

    if row is None:
        raise AppError(
            code="internal_error",
            message="Failed to attach listing image",
            http_status=500,
        )

    return _serialize_image(row)


@router.delete("/{listing_id}/images/{image_id}", status_code=204)
async def detach_listing_image(
    listing_id: str,
    image_id: str,
    _context: Annotated[tuple[dict[str, Any], dict[str, Any]], Depends(_require_owned_listing)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> None:
    parsed_listing_id = _parse_uuid(listing_id, field_name="listing_id")
    parsed_image_id = _parse_uuid(image_id, field_name="image_id")

    images = _list_images(service_client, parsed_listing_id)
    target = next((row for row in images if str(row.get("id")) == parsed_image_id), None)
    if target is None:
        raise AppError(
            code="not_found",
            message="Listing image not found",
            http_status=404,
            details={"image_id": parsed_image_id},
        )

    (
        service_client.client.table("listing_images")
        .delete()
        .eq("id", parsed_image_id)
        .eq("listing_id", parsed_listing_id)
        .execute()
    )

    remaining = [row for row in images if str(row.get("id")) != parsed_image_id]
    remaining.sort(key=lambda row: int(row.get("position", 0)))
    temp_offset = 100
    for index, row in enumerate(remaining):
        (
            service_client.client.table("listing_images")
            .update({"position": temp_offset + index})
            .eq("id", str(row["id"]))
            .execute()
        )
    for index, row in enumerate(remaining):
        (
            service_client.client.table("listing_images")
            .update({"position": index + 1})
            .eq("id", str(row["id"]))
            .execute()
        )


@router.patch("/{listing_id}/images/reorder", response_model=list[ListingImageResponse])
async def reorder_listing_images(
    listing_id: str,
    body: ReorderImagesRequest,
    _context: Annotated[tuple[dict[str, Any], dict[str, Any]], Depends(_require_owned_listing)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> list[ListingImageResponse]:
    parsed_listing_id = _parse_uuid(listing_id, field_name="listing_id")
    images = _list_images(service_client, parsed_listing_id)
    existing_ids = {str(row["id"]) for row in images}
    requested_ids = [_parse_uuid(image_id, field_name="image_id") for image_id in body.image_ids]

    if set(requested_ids) != existing_ids:
        raise AppError(
            code="validation_error",
            message="image_ids must match the listing's current images",
            http_status=400,
            details={"image_ids": body.image_ids},
        )

    temp_offset = 100
    for index, image_id in enumerate(requested_ids):
        (
            service_client.client.table("listing_images")
            .update({"position": temp_offset + index})
            .eq("id", image_id)
            .eq("listing_id", parsed_listing_id)
            .execute()
        )
    for index, image_id in enumerate(requested_ids):
        (
            service_client.client.table("listing_images")
            .update({"position": index + 1})
            .eq("id", image_id)
            .eq("listing_id", parsed_listing_id)
            .execute()
        )

    refreshed = _list_images(service_client, parsed_listing_id)
    return [_serialize_image(row) for row in refreshed]
