from __future__ import annotations

import re
from typing import Annotated, Any, Protocol

from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from fastapi import APIRouter, Depends
from pydantic import Field, field_validator

router = APIRouter(prefix="/vendor/profile", tags=["vendor-profile"])

SLUG_PATTERN = re.compile(r"^[a-z0-9-]+$")
TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
DAY_KEYS = frozenset({"mon", "tue", "wed", "thu", "fri", "sat", "sun"})

COMPLETENESS_FIELDS = (
    "logo",
    "description",
    "hours",
    "location",
    "badge",
)


class _ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class VendorHoursDay(StrictModel):
    open: str
    close: str
    closed: bool = False


class VendorLocationInput(StrictModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    landmark: str = Field(min_length=1, max_length=500)


class ProfilePatchRequest(StrictModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    logo_url: str | None = Field(default=None, max_length=2000)
    cover_url: str | None = Field(default=None, max_length=2000)
    slug: str | None = Field(default=None, min_length=2, max_length=80)
    whatsapp_msisdn: str | None = Field(default=None, max_length=32)
    hours: dict[str, Any] | None = None
    location: VendorLocationInput | None = None

    @field_validator("slug")
    @classmethod
    def normalize_slug(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("slug must not be empty")
        return normalized


class CompletenessBreakdown(StrictModel):
    logo: bool
    description: bool
    hours: bool
    location: bool
    badge: bool


class VendorProfileResponse(StrictModel):
    vendor_id: str
    slug: str
    display_name: str
    description: str | None
    logo_url: str | None
    cover_url: str | None
    whatsapp_msisdn: str | None
    preferred_badge: bool
    kyc_tier: int | None
    status: str
    hours: dict[str, Any]
    lat: float | None
    lng: float | None
    landmark: str | None
    slug_locked: bool
    previous_slug: str | None
    completeness_score: int
    completeness: CompletenessBreakdown


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def _parse_caps_snapshot(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    return {}


def normalize_whatsapp_msisdn(value: str) -> str | None:
    """Normalise a Zambian mobile number to E.164 digits (``260`` + 9), or None if invalid.

    Accepts local (``0977123456``), national (``977123456``), and international
    (``+260 977 123 456`` / ``260977123456``) inputs. Zambian mobile subscriber
    numbers start with 7 or 9 (07x / 09x); anything else is rejected so the wa.me
    deep link the storefront builds is always dialable.
    """
    digits = "".join(ch for ch in value if ch.isdigit())
    if digits.startswith("260"):
        national = digits[3:]
    elif digits.startswith("0"):
        national = digits[1:]
    else:
        national = digits
    if len(national) != 9 or national[0] not in {"7", "9"}:
        return None
    return f"260{national}"


def _is_description_complete(description: str | None) -> bool:
    return bool(description and len(description.strip()) >= 50)


def _is_logo_complete(logo_url: str | None) -> bool:
    return bool(logo_url and logo_url.strip())


def _parse_time_minutes(value: str) -> int | None:
    if not TIME_PATTERN.fullmatch(value):
        return None
    hours, minutes = value.split(":", 1)
    return int(hours) * 60 + int(minutes)


def _is_valid_hours_day(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("closed") is True:
        return True
    open_time = payload.get("open")
    close_time = payload.get("close")
    if not isinstance(open_time, str) or not isinstance(close_time, str):
        return False
    open_minutes = _parse_time_minutes(open_time)
    close_minutes = _parse_time_minutes(close_time)
    if open_minutes is None or close_minutes is None:
        return False
    if open_minutes == close_minutes:
        return False
    return True


def validate_vendor_hours(hours: dict[str, Any]) -> dict[str, Any]:
    if not hours:
        raise AppError(
            code="validation_error",
            message="hours must include at least one day",
            http_status=400,
            details={"message_key": "vendor.profile.errors.hours_empty"},
        )

    cleaned: dict[str, Any] = {}
    for day, payload in hours.items():
        day_key = day.strip().lower()
        if day_key not in DAY_KEYS:
            raise AppError(
                code="validation_error",
                message="hours contains an invalid day key",
                http_status=400,
                details={"day": day, "message_key": "vendor.profile.errors.hours_invalid_day"},
            )
        if not _is_valid_hours_day(payload):
            raise AppError(
                code="validation_error",
                message="hours day entry is invalid",
                http_status=400,
                details={"day": day_key, "message_key": "vendor.profile.errors.hours_invalid"},
            )
        cleaned[day_key] = payload

    if not any(
        isinstance(day_payload, dict) and day_payload.get("closed") is not True
        for day_payload in cleaned.values()
    ):
        raise AppError(
            code="validation_error",
            message="hours must include at least one open day",
            http_status=400,
            details={"message_key": "vendor.profile.errors.hours_all_closed"},
        )

    return cleaned


def _has_complete_hours(hours: dict[str, Any]) -> bool:
    if not hours:
        return False
    try:
        validate_vendor_hours(hours)
    except AppError:
        return False
    return any(
        isinstance(day_payload, dict) and day_payload.get("closed") is not True
        for day_payload in hours.values()
    )


def _is_location_complete(
    *,
    lat: float | None,
    lng: float | None,
    landmark: str | None,
) -> bool:
    return lat is not None and lng is not None and bool(landmark and landmark.strip())


def compute_profile_completeness(
    *,
    logo_url: str | None,
    description: str | None,
    hours: dict[str, Any],
    lat: float | None,
    lng: float | None,
    landmark: str | None,
    preferred_badge: bool,
) -> tuple[int, CompletenessBreakdown]:
    breakdown = CompletenessBreakdown(
        logo=_is_logo_complete(logo_url),
        description=_is_description_complete(description),
        hours=_has_complete_hours(hours),
        location=_is_location_complete(lat=lat, lng=lng, landmark=landmark),
        badge=preferred_badge,
    )
    filled = sum(
        (
            breakdown.logo,
            breakdown.description,
            breakdown.hours,
            breakdown.location,
            breakdown.badge,
        )
    )
    score = round((filled / len(COMPLETENESS_FIELDS)) * 100)
    return score, breakdown


def _load_vendor_for_owner(
    service_client: _ServiceRoleClient,
    owner_user_id: str,
) -> dict[str, Any]:
    response = (
        service_client.client.table("vendors")
        .select(
            "id, owner_user_id, slug, display_name, description, logo_url, cover_url, "
            "whatsapp_msisdn, status, kyc_tier, preferred_badge, caps_snapshot"
        )
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


def _load_primary_location(
    service_client: _ServiceRoleClient,
    vendor_id: str,
) -> dict[str, Any] | None:
    response = (
        service_client.client.table("vendor_locations")
        .select("id, lat, lng, landmark, hours")
        .eq("vendor_id", vendor_id)
        .order("created_at", desc=False)
        .limit(1)
        .execute()
    )
    data = getattr(response, "data", None)
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def _serialize_profile(
    vendor: dict[str, Any],
    location: dict[str, Any] | None,
) -> VendorProfileResponse:
    caps = _parse_caps_snapshot(vendor.get("caps_snapshot"))
    hours_raw = location.get("hours") if location else {}
    hours = hours_raw if isinstance(hours_raw, dict) else {}
    lat = location.get("lat") if location else None
    lng = location.get("lng") if location else None
    landmark = location.get("landmark") if location else None
    lat_value = float(lat) if isinstance(lat, (int, float)) else None
    lng_value = float(lng) if isinstance(lng, (int, float)) else None
    landmark_value = str(landmark) if isinstance(landmark, str) else None

    score, breakdown = compute_profile_completeness(
        logo_url=vendor.get("logo_url") if isinstance(vendor.get("logo_url"), str) else None,
        description=(
            str(vendor["description"])
            if isinstance(vendor.get("description"), str)
            else None
        ),
        hours=hours,
        lat=lat_value,
        lng=lng_value,
        landmark=landmark_value,
        preferred_badge=bool(vendor.get("preferred_badge")),
    )

    previous_slug = caps.get("previous_slug")
    return VendorProfileResponse(
        vendor_id=str(vendor["id"]),
        slug=str(vendor["slug"]),
        display_name=str(vendor["display_name"]),
        description=(
            str(vendor["description"])
            if isinstance(vendor.get("description"), str)
            else None
        ),
        logo_url=str(vendor["logo_url"]) if isinstance(vendor.get("logo_url"), str) else None,
        cover_url=str(vendor["cover_url"]) if isinstance(vendor.get("cover_url"), str) else None,
        whatsapp_msisdn=(
            str(vendor["whatsapp_msisdn"])
            if isinstance(vendor.get("whatsapp_msisdn"), str)
            else None
        ),
        preferred_badge=bool(vendor.get("preferred_badge")),
        kyc_tier=vendor.get("kyc_tier") if isinstance(vendor.get("kyc_tier"), int) else None,
        status=str(vendor.get("status", "draft")),
        hours=hours,
        lat=lat_value,
        lng=lng_value,
        landmark=landmark_value,
        slug_locked=bool(caps.get("slug_locked")),
        previous_slug=str(previous_slug) if isinstance(previous_slug, str) else None,
        completeness_score=score,
        completeness=breakdown,
    )


def _validate_slug_charset(slug: str) -> None:
    if not SLUG_PATTERN.fullmatch(slug):
        raise AppError(
            code="validation_error",
            message="slug must contain only lowercase letters, numbers, and hyphens",
            http_status=400,
            details={"message_key": "vendor.profile.errors.slug_charset"},
        )


def _assert_slug_available(
    service_client: _ServiceRoleClient,
    *,
    slug: str,
    vendor_id: str,
) -> None:
    response = (
        service_client.client.table("vendors")
        .select("id, slug")
        .eq("slug", slug)
        .maybe_single()
        .execute()
    )
    existing = _single_row(response)
    if existing is not None and str(existing.get("id")) != vendor_id:
        raise AppError(
            code="conflict",
            message="slug is already taken",
            http_status=409,
            details={"message_key": "vendor.profile.errors.slug_taken"},
        )


def _apply_slug_change(
    service_client: _ServiceRoleClient,
    vendor: dict[str, Any],
    new_slug: str,
) -> dict[str, Any]:
    current_slug = str(vendor["slug"])
    if new_slug == current_slug:
        return vendor

    caps = _parse_caps_snapshot(vendor.get("caps_snapshot"))
    if caps.get("slug_locked"):
        raise AppError(
            code="conflict",
            message="slug can only be changed once",
            http_status=409,
            details={"message_key": "vendor.profile.errors.slug_locked"},
        )

    _validate_slug_charset(new_slug)
    _assert_slug_available(service_client, slug=new_slug, vendor_id=str(vendor["id"]))

    caps["slug_locked"] = True
    caps["previous_slug"] = current_slug

    response = (
        service_client.client.table("vendors")
        .update({"slug": new_slug, "caps_snapshot": caps})
        .eq("id", vendor["id"])
        .execute()
    )
    updated = _single_row(response)
    if updated is None:
        raise AppError(
            code="internal_error",
            message="Failed to update vendor slug",
            http_status=500,
        )
    return updated


def _upsert_location(
    service_client: _ServiceRoleClient,
    *,
    vendor_id: str,
    location: VendorLocationInput,
    hours: dict[str, Any] | None,
) -> None:
    existing = _load_primary_location(service_client, vendor_id)
    payload: dict[str, Any] = {
        "lat": location.lat,
        "lng": location.lng,
        "landmark": location.landmark.strip(),
    }
    if hours is not None:
        payload["hours"] = hours
    elif existing and isinstance(existing.get("hours"), dict):
        payload["hours"] = existing["hours"]
    else:
        payload["hours"] = {}

    if existing is None:
        payload["vendor_id"] = vendor_id
        service_client.client.table("vendor_locations").insert(payload).execute()
        return

    service_client.client.table("vendor_locations").update(payload).eq(
        "id", existing["id"]
    ).execute()


async def require_vendor_owner(
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> dict[str, Any]:
    return _load_vendor_for_owner(service_client, current_user.id)


@router.get("", response_model=VendorProfileResponse)
async def get_vendor_profile(
    vendor: Annotated[dict[str, Any], Depends(require_vendor_owner)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> VendorProfileResponse:
    location = _load_primary_location(service_client, str(vendor["id"]))
    return _serialize_profile(vendor, location)


@router.patch("", response_model=VendorProfileResponse)
async def patch_vendor_profile(
    body: ProfilePatchRequest,
    vendor: Annotated[dict[str, Any], Depends(require_vendor_owner)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> VendorProfileResponse:
    vendor_row = dict(vendor)
    vendor_id = str(vendor_row["id"])

    if body.slug is not None:
        vendor_row = _apply_slug_change(service_client, vendor_row, body.slug)

    vendor_updates: dict[str, Any] = {}
    if body.display_name is not None:
        vendor_updates["display_name"] = body.display_name.strip()
    if body.description is not None:
        vendor_updates["description"] = body.description.strip() or None
    if body.logo_url is not None:
        vendor_updates["logo_url"] = body.logo_url.strip() or None
    if body.cover_url is not None:
        vendor_updates["cover_url"] = body.cover_url.strip() or None
    if body.whatsapp_msisdn is not None:
        stripped = body.whatsapp_msisdn.strip()
        if not stripped:
            vendor_updates["whatsapp_msisdn"] = None
        else:
            normalized = normalize_whatsapp_msisdn(stripped)
            if normalized is None:
                raise AppError(
                    code="validation_error",
                    message="whatsapp_msisdn is not a valid Zambian mobile number",
                    http_status=400,
                    details={"message_key": "vendor.profile.errors.whatsapp_invalid"},
                )
            vendor_updates["whatsapp_msisdn"] = normalized

    if vendor_updates:
        response = (
            service_client.client.table("vendors")
            .update(vendor_updates)
            .eq("id", vendor_id)
            .execute()
        )
        updated = _single_row(response)
        if updated is not None:
            vendor_row.update(updated)

    cleaned_hours: dict[str, Any] | None = None
    if body.hours is not None:
        cleaned_hours = validate_vendor_hours(body.hours)

    location = _load_primary_location(service_client, vendor_id)

    if body.location is not None:
        hours_payload = cleaned_hours
        if hours_payload is None:
            if location is not None and isinstance(location.get("hours"), dict):
                hours_payload = location["hours"]
            else:
                hours_payload = {}
        _upsert_location(
            service_client,
            vendor_id=vendor_id,
            location=body.location,
            hours=hours_payload,
        )
    elif cleaned_hours is not None:
        if location is None:
            raise AppError(
                code="validation_error",
                message="location is required when setting hours without an existing location",
                http_status=400,
                details={"message_key": "vendor.profile.errors.location_required"},
            )
        service_client.client.table("vendor_locations").update({"hours": cleaned_hours}).eq(
            "id", location["id"]
        ).execute()

    refreshed_vendor = _load_vendor_for_owner(service_client, str(vendor_row["owner_user_id"]))
    refreshed_location = _load_primary_location(service_client, vendor_id)
    return _serialize_profile(refreshed_vendor, refreshed_location)


def resolve_slug_redirect(
    service_client: _ServiceRoleClient,
    slug: str,
) -> str | None:
    """Return the current slug when ``slug`` is a stored previous slug (301 target)."""
    response = (
        service_client.client.table("vendors")
        .select("slug, caps_snapshot")
        .execute()
    )
    data = getattr(response, "data", None)
    if not isinstance(data, list):
        return None
    for row in data:
        if not isinstance(row, dict):
            continue
        caps = _parse_caps_snapshot(row.get("caps_snapshot"))
        if caps.get("previous_slug") == slug:
            return str(row["slug"])
    return None
