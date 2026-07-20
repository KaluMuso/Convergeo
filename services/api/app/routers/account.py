from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from app.core.auth import CurrentUser, get_current_user
from app.core.supabase import get_user_client
from app.errors import AppError
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from supabase import Client

router = APIRouter(prefix="/account", tags=["account"])

SUPPORTED_LOCALES = frozenset({"en", "bem", "nya", "fr"})


class ProfileResponse(BaseModel):
    id: str
    phone: str | None = None
    display_name: str | None = None
    locale: str


class ProfilePatchRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    locale: str | None = None


class AddressResponse(BaseModel):
    id: str
    label: str | None = None
    landmark: str
    lat: float | None = None
    lng: float | None = None
    phone: str | None = None


class AddressCreateRequest(BaseModel):
    label: str | None = Field(default=None, max_length=80)
    landmark: str = Field(min_length=1, max_length=500)
    lat: float | None = None
    lng: float | None = None
    phone: str | None = Field(default=None, max_length=20)


class AddressPatchRequest(BaseModel):
    label: str | None = Field(default=None, max_length=80)
    landmark: str | None = Field(default=None, min_length=1, max_length=500)
    lat: float | None = None
    lng: float | None = None
    phone: str | None = Field(default=None, max_length=20)


class NotificationPrefs(BaseModel):
    whatsapp: bool = True
    sms: bool = True
    email: bool = True


class PreferencesResponse(BaseModel):
    notif_prefs: NotificationPrefs


class PreferencesPatchRequest(BaseModel):
    whatsapp: bool | None = None
    sms: bool | None = None
    email: bool | None = None


def _user_client(current_user: CurrentUser) -> Client:
    return get_user_client(current_user.token)


def _parse_profile_row(row: dict[str, Any]) -> ProfileResponse:
    return ProfileResponse(
        id=str(row["id"]),
        phone=row.get("phone"),
        display_name=row.get("display_name"),
        locale=str(row.get("locale") or "en"),
    )


def _parse_address_row(row: dict[str, Any]) -> AddressResponse:
    return AddressResponse(
        id=str(row["id"]),
        label=row.get("label"),
        landmark=str(row["landmark"]),
        lat=row.get("lat"),
        lng=row.get("lng"),
        phone=row.get("phone"),
    )


def _normalize_notif_prefs(raw: Any) -> NotificationPrefs:
    if not isinstance(raw, dict):
        return NotificationPrefs()

    return NotificationPrefs(
        whatsapp=bool(raw.get("whatsapp", True)),
        sms=bool(raw.get("sms", True)),
        email=bool(raw.get("email", True)),
    )


def _validate_locale(locale: str | None) -> str:
    if locale is None:
        raise AppError(
            code="validation_error",
            message="locale is required",
            http_status=422,
        )
    normalized = locale.strip().lower()
    if normalized not in SUPPORTED_LOCALES:
        raise AppError(
            code="validation_error",
            message="Unsupported locale",
            http_status=422,
            details={"locale": locale, "supported": sorted(SUPPORTED_LOCALES)},
        )
    return normalized


def _ensure_address_owner(row: dict[str, Any] | None, user_id: str) -> dict[str, Any]:
    if not row:
        raise AppError(
            code="not_found",
            message="Address not found",
            http_status=404,
        )
    if str(row.get("user_id")) != user_id:
        raise AppError(
            code="forbidden",
            message="You cannot access this address",
            http_status=403,
        )
    return row


def _extract_data(response: object | None) -> Any:
    if response is None:
        return None
    return getattr(response, "data", None)


def _fetch_profile(client: Client, user_id: str) -> ProfileResponse:
    response = client.table("profiles").select("*").eq("id", user_id).maybe_single().execute()
    row = _extract_data(response)
    if not isinstance(row, dict):
        raise AppError(
            code="not_found",
            message="Profile not found",
            http_status=404,
        )
    return _parse_profile_row(row)


@router.get("/profile", response_model=ProfileResponse)
async def get_profile(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ProfileResponse:
    client = _user_client(current_user)
    return _fetch_profile(client, current_user.id)


@router.patch("/profile", response_model=ProfileResponse)
async def patch_profile(
    body: ProfilePatchRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ProfileResponse:
    if body.display_name is None and body.locale is None:
        raise AppError(
            code="validation_error",
            message="At least one field must be provided",
            http_status=422,
        )

    updates: dict[str, Any] = {}
    if body.display_name is not None:
        updates["display_name"] = body.display_name.strip() or None
    if body.locale is not None:
        updates["locale"] = _validate_locale(body.locale)

    client = _user_client(current_user)
    response = client.table("profiles").update(updates).eq("id", current_user.id).execute()
    rows = _extract_data(response)
    if not isinstance(rows, list) or not rows:
        return _fetch_profile(client, current_user.id)

    row = rows[0]
    if not isinstance(row, dict):
        return _fetch_profile(client, current_user.id)
    return _parse_profile_row(row)


@router.get("/addresses", response_model=list[AddressResponse])
async def list_addresses(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[AddressResponse]:
    client = _user_client(current_user)
    response = (
        client.table("addresses")
        .select("id,label,landmark,lat,lng,phone")
        .eq("user_id", current_user.id)
        .order("created_at")
        .execute()
    )
    rows = _extract_data(response)
    if not isinstance(rows, list):
        return []
    return [_parse_address_row(row) for row in rows if isinstance(row, dict)]


@router.post("/addresses", response_model=AddressResponse, status_code=201)
async def create_address(
    body: AddressCreateRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> AddressResponse:
    payload = {
        "user_id": current_user.id,
        "label": body.label.strip() if body.label else None,
        "landmark": body.landmark.strip(),
        "lat": body.lat,
        "lng": body.lng,
        "phone": body.phone.strip() if body.phone else None,
    }
    client = _user_client(current_user)
    response = client.table("addresses").insert(payload).execute()
    rows = _extract_data(response)
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        raise AppError(
            code="internal_error",
            message="Failed to create address",
            http_status=500,
        )
    return _parse_address_row(rows[0])


@router.get("/addresses/{address_id}", response_model=AddressResponse)
async def get_address(
    address_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> AddressResponse:
    client = _user_client(current_user)
    response = (
        client.table("addresses")
        .select("id,user_id,label,landmark,lat,lng,phone")
        .eq("id", address_id)
        .maybe_single()
        .execute()
    )
    row = _extract_data(response)
    if not isinstance(row, dict):
        raise AppError(
            code="not_found",
            message="Address not found",
            http_status=404,
        )
    _ensure_address_owner(row, current_user.id)
    return _parse_address_row(row)


@router.patch("/addresses/{address_id}", response_model=AddressResponse)
async def patch_address(
    address_id: str,
    body: AddressPatchRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> AddressResponse:
    if (
        body.label is None
        and body.landmark is None
        and body.lat is None
        and body.lng is None
        and body.phone is None
    ):
        raise AppError(
            code="validation_error",
            message="At least one field must be provided",
            http_status=422,
        )

    client = _user_client(current_user)
    existing_response = (
        client.table("addresses")
        .select("id,user_id,label,landmark,lat,lng,phone")
        .eq("id", address_id)
        .maybe_single()
        .execute()
    )
    existing = _extract_data(existing_response)
    if not isinstance(existing, dict):
        raise AppError(
            code="not_found",
            message="Address not found",
            http_status=404,
        )
    _ensure_address_owner(existing, current_user.id)

    updates: dict[str, Any] = {}
    if body.label is not None:
        updates["label"] = body.label.strip() or None
    if body.landmark is not None:
        updates["landmark"] = body.landmark.strip()
    if body.lat is not None:
        updates["lat"] = body.lat
    if body.lng is not None:
        updates["lng"] = body.lng
    if body.phone is not None:
        updates["phone"] = body.phone.strip() or None

    response = client.table("addresses").update(updates).eq("id", address_id).execute()
    rows = _extract_data(response)
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return _parse_address_row(rows[0])
    return _parse_address_row({**existing, **updates})


@router.delete("/addresses/{address_id}", status_code=204)
async def delete_address(
    address_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> None:
    client = _user_client(current_user)
    existing_response = (
        client.table("addresses")
        .select("id,user_id")
        .eq("id", address_id)
        .maybe_single()
        .execute()
    )
    existing = _extract_data(existing_response)
    if not isinstance(existing, dict):
        raise AppError(
            code="not_found",
            message="Address not found",
            http_status=404,
        )
    _ensure_address_owner(existing, current_user.id)
    client.table("addresses").delete().eq("id", address_id).execute()


@router.get("/preferences", response_model=PreferencesResponse)
async def get_preferences(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> PreferencesResponse:
    client = _user_client(current_user)
    response = (
        client.table("profiles")
        .select("notif_prefs")
        .eq("id", current_user.id)
        .maybe_single()
        .execute()
    )
    row = _extract_data(response)
    if not isinstance(row, dict):
        raise AppError(
            code="not_found",
            message="Profile not found",
            http_status=404,
        )
    return PreferencesResponse(notif_prefs=_normalize_notif_prefs(row.get("notif_prefs")))


@router.patch("/preferences", response_model=PreferencesResponse)
async def patch_preferences(
    body: PreferencesPatchRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> PreferencesResponse:
    if body.whatsapp is None and body.sms is None and body.email is None:
        raise AppError(
            code="validation_error",
            message="At least one preference must be provided",
            http_status=422,
        )

    client = _user_client(current_user)
    existing_response = (
        client.table("profiles")
        .select("notif_prefs")
        .eq("id", current_user.id)
        .maybe_single()
        .execute()
    )
    row = _extract_data(existing_response)
    if not isinstance(row, dict):
        raise AppError(
            code="not_found",
            message="Profile not found",
            http_status=404,
        )

    merged = _normalize_notif_prefs(row.get("notif_prefs")).model_dump()
    if body.whatsapp is not None:
        merged["whatsapp"] = body.whatsapp
    if body.sms is not None:
        merged["sms"] = body.sms
    if body.email is not None:
        merged["email"] = body.email

    response = (
        client.table("profiles")
        .update({"notif_prefs": merged})
        .eq("id", current_user.id)
        .execute()
    )
    rows = _extract_data(response)
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return PreferencesResponse(
            notif_prefs=_normalize_notif_prefs(rows[0].get("notif_prefs")),
        )
    return PreferencesResponse(notif_prefs=NotificationPrefs(**merged))


RECENTLY_VIEWED_MAX = 20


class WishlistItemOut(BaseModel):
    product_id: str
    slug: str
    name: str
    created_at: str


class WishlistResponse(BaseModel):
    items: list[WishlistItemOut]


class WishlistPutRequest(BaseModel):
    product_ids: list[str] = Field(default_factory=list, max_length=200)


class RecentlyViewedItemOut(BaseModel):
    product_id: str
    slug: str
    name: str
    viewed_at: str


class RecentlyViewedResponse(BaseModel):
    items: list[RecentlyViewedItemOut]


class RecentlyViewedPostRequest(BaseModel):
    product_id: str = Field(min_length=1)


@router.get("/wishlist", response_model=WishlistResponse)
async def get_wishlist(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> WishlistResponse:
    client = _user_client(current_user)
    response = (
        client.table("user_wishlist")
        .select("product_id, created_at, products(id, slug, name)")
        .eq("user_id", current_user.id)
        .order("created_at", desc=True)
        .execute()
    )
    rows = _extract_data(response)
    items: list[WishlistItemOut] = []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            product = row.get("products")
            if not isinstance(product, dict):
                continue
            items.append(
                WishlistItemOut(
                    product_id=str(product.get("id") or row.get("product_id")),
                    slug=str(product.get("slug") or ""),
                    name=str(product.get("name") or ""),
                    created_at=str(row.get("created_at") or ""),
                )
            )
    return WishlistResponse(items=items)


@router.put("/wishlist", response_model=WishlistResponse)
async def put_wishlist(
    body: WishlistPutRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> WishlistResponse:
    """Replace wishlist with the provided product id set (deduped, order preserved)."""
    client = _user_client(current_user)
    seen: set[str] = set()
    product_ids: list[str] = []
    for raw in body.product_ids:
        pid = raw.strip()
        if not pid or pid in seen:
            continue
        seen.add(pid)
        product_ids.append(pid)

    client.table("user_wishlist").delete().eq("user_id", current_user.id).execute()
    if product_ids:
        client.table("user_wishlist").insert(
            [{"user_id": current_user.id, "product_id": pid} for pid in product_ids]
        ).execute()
    return await get_wishlist(current_user)


@router.get("/recently-viewed", response_model=RecentlyViewedResponse)
async def get_recently_viewed(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> RecentlyViewedResponse:
    client = _user_client(current_user)
    response = (
        client.table("user_recently_viewed")
        .select("product_id, viewed_at, products(id, slug, name)")
        .eq("user_id", current_user.id)
        .order("viewed_at", desc=True)
        .limit(RECENTLY_VIEWED_MAX)
        .execute()
    )
    rows = _extract_data(response)
    items: list[RecentlyViewedItemOut] = []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            product = row.get("products")
            if not isinstance(product, dict):
                continue
            items.append(
                RecentlyViewedItemOut(
                    product_id=str(product.get("id") or row.get("product_id")),
                    slug=str(product.get("slug") or ""),
                    name=str(product.get("name") or ""),
                    viewed_at=str(row.get("viewed_at") or ""),
                )
            )
    return RecentlyViewedResponse(items=items)


@router.post("/recently-viewed", response_model=RecentlyViewedResponse)
async def post_recently_viewed(
    body: RecentlyViewedPostRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> RecentlyViewedResponse:
    client = _user_client(current_user)
    product_id = body.product_id.strip()
    client.table("user_recently_viewed").upsert(
        {
            "user_id": current_user.id,
            "product_id": product_id,
            "viewed_at": datetime.now(UTC).isoformat(),
        },
        on_conflict="user_id,product_id",
    ).execute()

    # Cap to RECENTLY_VIEWED_MAX by deleting oldest beyond the window.
    listed = (
        client.table("user_recently_viewed")
        .select("product_id, viewed_at")
        .eq("user_id", current_user.id)
        .order("viewed_at", desc=True)
        .execute()
    )
    rows = _extract_data(listed)
    if isinstance(rows, list) and len(rows) > RECENTLY_VIEWED_MAX:
        drop_ids = [
            str(row["product_id"])
            for row in rows[RECENTLY_VIEWED_MAX:]
            if isinstance(row, dict) and row.get("product_id")
        ]
        if drop_ids:
            client.table("user_recently_viewed").delete().eq(
                "user_id", current_user.id
            ).in_("product_id", drop_ids).execute()

    return await get_recently_viewed(current_user)
