from __future__ import annotations

import math
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal, Protocol

from app.core.auth import CurrentUser, get_current_user
from app.core.supabase import get_user_client
from app.deps import get_supabase_client
from app.errors import AppError
from app.services.business.access import resolve_business_eligibility
from app.services.cart.events import emit_checkout_start
from app.services.cart.grouping import CartLineView, group_by_vendor
from app.services.cart.merge import validate_item_qty_for_listing
from app.services.cart.read_path import listing_cart_access_conflict
from app.services.cart.store import fetch_listings_for_items
from app.services.cart.totals import cart_subtotal_ngwee, line_total_ngwee
from app.services.listings.class_rules import listing_lead_time_days
from app.services.stock.claim import claim_reservation, get_reservation_ttl_minutes
from app.settings import Settings, get_settings
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from supabase import Client

router = APIRouter(prefix="/checkout", tags=["checkout"])

LUSAKA_CENTER_LAT = -15.4167
LUSAKA_CENTER_LNG = 28.2833
ZONE_BANDS_KM: tuple[tuple[str, float], ...] = (
    ("lusaka_a", 5.0),
    ("lusaka_b", 12.0),
    ("lusaka_c", 25.0),
)
DEFAULT_FREE_DELIVERY_THRESHOLD_NGEWEE = 20_000


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Client: ...


class CartLineOut(BaseModel):
    id: str
    listing_id: str
    vendor_id: str
    qty: int
    unit_price_ngwee: int
    line_total_ngwee: int
    title_override: str | None = None
    lead_time_days: int | None = None


class PickupLocationOut(BaseModel):
    landmark: str
    lat: float
    lng: float
    hours: dict[str, Any] = Field(default_factory=dict)


class VendorGroupOut(BaseModel):
    vendor_id: str
    vendor_name: str
    items: list[CartLineOut]
    subtotal_ngwee: int
    delivery_eligible: bool
    pickup_location: PickupLocationOut | None = None


class ReservationClaimOut(BaseModel):
    listing_id: str
    qty: int
    claimed: bool
    skipped: bool = False


class CheckoutSessionResponse(BaseModel):
    session_id: str
    expires_at: datetime
    reservation_ttl_min: int
    vendor_groups: list[VendorGroupOut]
    subtotal_ngwee: int
    reservations: list[ReservationClaimOut]
    contact_skipped: bool = False


class SessionStatusResponse(BaseModel):
    session_id: str
    status: str
    expires_at: datetime
    expired: bool
    redirect_notice_key: str | None = None


class ContactStepRequest(BaseModel):
    phone: str | None = Field(default=None, max_length=20)


class ContactStepResponse(BaseModel):
    verified: bool
    phone: str | None = None
    skipped: bool = False


class GroupFulfilmentChoice(BaseModel):
    vendor_id: str
    fulfilment: Literal["delivery", "pickup"]


class FulfilmentAddress(BaseModel):
    landmark: str = Field(min_length=1, max_length=500)
    lat: float | None = None
    lng: float | None = None


class FulfilmentStepRequest(BaseModel):
    session_id: str
    address: FulfilmentAddress | None = None
    groups: list[GroupFulfilmentChoice] = Field(min_length=1)


class GroupFulfilmentResult(BaseModel):
    vendor_id: str
    fulfilment: Literal["delivery", "pickup"]
    delivery_zone: str | None = None
    delivery_zone_label: str | None = None
    delivery_fee_ngwee: int
    subtotal_ngwee: int
    pickup_location: PickupLocationOut | None = None


class FulfilmentStepResponse(BaseModel):
    session_id: str
    groups: list[GroupFulfilmentResult]
    subtotal_ngwee: int
    delivery_fee_ngwee: int
    total_ngwee: int
    resolved_zone_key: str | None = None
    pickup_only: bool = False


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius_km * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def resolve_delivery_zone(
    *,
    lat: float | None,
    lng: float | None,
    landmark: str | None = None,
) -> str | None:
    """Resolve a Lusaka delivery zone from GPS or landmark; None means pickup-only."""
    if lat is not None and lng is not None:
        distance_km = haversine_km(lat, lng, LUSAKA_CENTER_LAT, LUSAKA_CENTER_LNG)
        for zone_key, max_km in ZONE_BANDS_KM:
            if distance_km <= max_km:
                return zone_key
        return None

    if landmark:
        lower = landmark.lower()
        if any(token in lower for token in ("ndola", "kitwe", "livingstone", "chipata")):
            return None
        if "band a" in lower or "central" in lower or "cbd" in lower:
            return "lusaka_a"
        if "band b" in lower or "mid-ring" in lower or "kabulonga" in lower:
            return "lusaka_b"
        if "band c" in lower or "outer" in lower:
            return "lusaka_c"
        if "lusaka" in lower or "woodlands" in lower or "east park" in lower:
            return "lusaka_a"

    return None


def compute_group_delivery_fee_ngwee(
    *,
    subtotal_ngwee: int,
    zone_key: str | None,
    zone_fees: dict[str, int],
    free_delivery_threshold_ngwee: int,
) -> int:
    if zone_key is None:
        return 0
    if subtotal_ngwee >= free_delivery_threshold_ngwee:
        return 0
    return zone_fees.get(zone_key, 0)


def _fetch_active_cart_by_user(client: Client, user_id: str) -> dict[str, Any] | None:
    response = (
        client.table("carts")
        .select("id, user_id, status")
        .eq("user_id", user_id)
        .eq("status", "active")
        .limit(1)
        .execute()
    )
    rows = response.data
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return rows[0]
    return None


def _fetch_cart_items(client: Client, cart_id: str) -> list[dict[str, Any]]:
    response = (
        client.table("cart_items")
        .select("id, cart_id, listing_id, qty, unit_price_ngwee, wholesale, pickup_location_id")
        .eq("cart_id", cart_id)
        .execute()
    )
    rows = response.data
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _load_delivery_zones(service: ServiceRoleClient) -> dict[str, dict[str, Any]]:
    response = service.client.table("delivery_zones").select("*").eq("active", True).execute()
    rows = response.data if isinstance(response.data, list) else []
    zones: dict[str, dict[str, Any]] = {}
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("zone_key"), str):
            zones[row["zone_key"]] = row
    return zones


def _extract_data(response: object | None) -> Any:
    if response is None:
        return None
    return getattr(response, "data", None)


def _load_free_delivery_threshold(service: ServiceRoleClient) -> int:
    response = (
        service.client.table("platform_config")
        .select("value")
        .eq("key", "free_delivery_threshold_ngwee")
        .maybe_single()
        .execute()
    )
    data = _extract_data(response)
    if isinstance(data, dict) and data.get("value") is not None:
        raw = data["value"]
        if isinstance(raw, int):
            return raw
        if isinstance(raw, str) and raw.isdigit():
            return int(raw)
    return DEFAULT_FREE_DELIVERY_THRESHOLD_NGEWEE


def _fetch_vendor_names(service: ServiceRoleClient, vendor_ids: list[str]) -> dict[str, str]:
    if not vendor_ids:
        return {}
    response = (
        service.client.table("vendors").select("id, display_name").in_("id", vendor_ids).execute()
    )
    rows = response.data if isinstance(response.data, list) else []
    return {
        str(row["id"]): str(row.get("display_name") or "")
        for row in rows
        if isinstance(row, dict) and row.get("id")
    }


def _fetch_vendor_locations(
    service: ServiceRoleClient, vendor_ids: list[str]
) -> dict[str, PickupLocationOut]:
    if not vendor_ids:
        return {}
    response = (
        service.client.table("vendor_locations")
        .select("vendor_id, lat, lng, landmark, hours")
        .in_("vendor_id", vendor_ids)
        .execute()
    )
    rows = response.data if isinstance(response.data, list) else []
    locations: dict[str, PickupLocationOut] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        vendor_id = row.get("vendor_id")
        if not isinstance(vendor_id, str):
            continue
        lat = row.get("lat")
        lng = row.get("lng")
        landmark = row.get("landmark")
        if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
            continue
        if not isinstance(landmark, str):
            continue
        hours = row.get("hours")
        locations[vendor_id] = PickupLocationOut(
            landmark=landmark,
            lat=float(lat),
            lng=float(lng),
            hours=hours if isinstance(hours, dict) else {},
        )
    return locations


def _rederive_line_prices(
    items: list[dict[str, Any]],
    listings_by_id: dict[str, dict[str, Any]],
    *,
    business_eligible: bool,
    service: ServiceRoleClient,
) -> list[dict[str, Any]]:
    """B0-P02a defence-in-depth: a checkout session is never opened on stored prices.

    Migration 0086 makes cart price columns writable only by the service role,
    so stored lines are normally trustworthy — but the contract is derivation,
    not trust. Each line's price and wholesale flag are re-derived here from
    the LISTING and the caller's CURRENT eligibility. Divergence means the
    world changed since the line was written (tier crossed, listing re-priced,
    eligibility revoked, or a write path was missed), and the customer must
    see the real number before money is reserved — never be charged an amount
    they were not shown.

    Conflicts collected, then one 409 `checkout.cart_changed`:
      * wholesale-only listing, caller no longer eligible → the line reports
        `cart.listing_unavailable` — the same non-disclosing code an absent
        listing gets (D36; G8.1 §3: block, never re-price);
      * qty below MOQ for an eligible buyer → `cart.moq_violation`;
      * derived price != stored → `cart.price_changed`, and the stored line is
        corrected via the service client so the cart the customer returns to
        shows the true price.
    """
    conflicts: list[dict[str, Any]] = []
    for item in items:
        listing_id = str(item["listing_id"])
        listing = listings_by_id.get(listing_id)
        access_conflict = listing_cart_access_conflict(
            listing_id,
            listing,
            business_eligible=business_eligible,
        )
        if access_conflict is not None:
            # Checkout sessions surface inactive lines as unavailable (same as absent).
            code = access_conflict.code
            if code == "cart.listing_inactive":
                code = "cart.listing_unavailable"
            conflicts.append({"listing_id": listing_id, "code": code})
            continue
        if listing is None:
            conflicts.append({"listing_id": listing_id, "code": "cart.listing_unavailable"})
            continue
        try:
            fresh_price, fresh_wholesale = validate_item_qty_for_listing(
                listing=listing,
                qty=int(item["qty"]),
                business_eligible=business_eligible,
            )
        except AppError as exc:
            conflicts.append({"listing_id": listing_id, "code": exc.code})
            continue
        stored_price = int(item["unit_price_ngwee"])
        if fresh_price != stored_price or bool(item.get("wholesale", False)) != fresh_wholesale:
            service.client.table("cart_items").update(
                {"unit_price_ngwee": fresh_price, "wholesale": fresh_wholesale}
            ).eq("id", str(item["id"])).execute()
            conflicts.append(
                {
                    "listing_id": listing_id,
                    "code": "cart.price_changed",
                    "previous_unit_price_ngwee": stored_price,
                    "current_unit_price_ngwee": fresh_price,
                }
            )
            continue
        # Line verified: totals below may safely use the stored value, because
        # it just proved equal to the derived one.
    if conflicts:
        raise AppError(
            code="checkout.cart_changed",
            message="Your cart has changed and needs review before checkout",
            http_status=409,
            details={"redirect_to": "cart", "conflicts": conflicts},
        )
    return items


def _build_line_views(
    items: list[dict[str, Any]], listings_by_id: dict[str, dict[str, Any]]
) -> list[CartLineView]:
    line_views: list[CartLineView] = []
    for item in items:
        listing_id = str(item["listing_id"])
        listing = listings_by_id.get(listing_id, {})
        qty = int(item["qty"])
        unit_price = int(item["unit_price_ngwee"])
        line_views.append(
            CartLineView(
                id=str(item["id"]),
                listing_id=listing_id,
                vendor_id=str(listing.get("vendor_id", "")),
                qty=qty,
                unit_price_ngwee=unit_price,
                wholesale=bool(item.get("wholesale", False)),
                line_total_ngwee=line_total_ngwee(qty, unit_price),
                title_override=listing.get("title_override")
                if isinstance(listing.get("title_override"), str)
                else None,
                lead_time_days=listing_lead_time_days(listing),
            )
        )
    return line_views


def _fetch_checkout_group(
    service: ServiceRoleClient, session_id: str, customer_id: str
) -> dict[str, Any]:
    response = (
        service.client.table("checkout_groups")
        .select("*")
        .eq("id", session_id)
        .eq("customer_id", customer_id)
        .maybe_single()
        .execute()
    )
    row = _extract_data(response)
    if not isinstance(row, dict):
        raise AppError(
            code="checkout.session_not_found",
            message="Checkout session not found",
            http_status=404,
            details={"session_id": session_id},
        )
    return row


def _session_expires_at(service: ServiceRoleClient, session_id: str) -> datetime | None:
    response = (
        service.client.table("stock_reservations")
        .select("expires_at")
        .eq("checkout_group_id", session_id)
        .order("expires_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = response.data if isinstance(response.data, list) else []
    if not rows or not isinstance(rows[0], dict):
        return None
    raw = rows[0].get("expires_at")
    if not isinstance(raw, str):
        return None
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _ensure_session_active(
    service: ServiceRoleClient, session_id: str, customer_id: str
) -> tuple[dict[str, Any], datetime]:
    group = _fetch_checkout_group(service, session_id, customer_id)
    status = str(group.get("status") or "")
    if status in {"expired", "abandoned"}:
        raise AppError(
            code="checkout.reservation_expired",
            message="Your reservation has expired",
            http_status=410,
            details={
                "redirect_to": "cart",
                "notice_key": "checkout.checkout.reservationExpired",
                "session_id": session_id,
            },
        )

    expires_at = _session_expires_at(service, session_id)
    if expires_at is None:
        ttl_min = get_reservation_ttl_minutes()
        created_raw = group.get("created_at")
        if isinstance(created_raw, str):
            created_at = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
            expires_at = created_at + timedelta(minutes=ttl_min)
        else:
            expires_at = datetime.now(UTC) + timedelta(minutes=ttl_min)

    if expires_at <= datetime.now(UTC):
        service.client.table("checkout_groups").update({"status": "expired"}).eq(
            "id", session_id
        ).execute()
        raise AppError(
            code="checkout.reservation_expired",
            message="Your reservation has expired",
            http_status=410,
            details={
                "redirect_to": "cart",
                "notice_key": "checkout.checkout.reservationExpired",
                "session_id": session_id,
            },
        )

    return group, expires_at


def _normalize_phone(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    if value.strip().startswith("+"):
        return f"+{digits}"
    if digits.startswith("260"):
        return f"+{digits}"
    if len(digits) == 9:
        return f"+260{digits}"
    return value.strip()


@router.post("/session", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> CheckoutSessionResponse:
    user_client = get_user_client(current_user.token, settings)
    cart = _fetch_active_cart_by_user(user_client, current_user.id)
    if cart is None:
        raise AppError(
            code="checkout.cart_empty",
            message="Your cart is empty",
            http_status=400,
            details={"redirect_to": "cart"},
        )

    cart_id = str(cart["id"])
    items = _fetch_cart_items(user_client, cart_id)
    if not items:
        raise AppError(
            code="checkout.cart_empty",
            message="Your cart is empty",
            http_status=400,
            details={"redirect_to": "cart"},
        )

    listings = fetch_listings_for_items(items)

    # B0-P02a: prices re-derived before any money number is computed. Raises
    # 409 checkout.cart_changed on divergence; see _rederive_line_prices.
    access = resolve_business_eligibility(current_user.id, service)
    items = _rederive_line_prices(
        items, listings, business_eligible=access.eligible, service=service
    )

    line_views = _build_line_views(items, listings)
    vendor_groups = group_by_vendor(
        line_views,
        free_delivery_threshold_ngwee=_load_free_delivery_threshold(service),
    )
    subtotal = cart_subtotal_ngwee([(line.qty, line.unit_price_ngwee) for line in line_views])

    session_id = str(uuid.uuid4())
    idempotency_key = f"chk-{secrets.token_urlsafe(16)}"
    service.client.table("checkout_groups").insert(
        {
            "id": session_id,
            "customer_id": current_user.id,
            "idempotency_key": idempotency_key,
            "subtotal_ngwee": subtotal,
            "delivery_fee_ngwee": 0,
            "total_ngwee": subtotal,
            "status": "pending",
        }
    ).execute()

    ttl_min = get_reservation_ttl_minutes()
    reservations: list[ReservationClaimOut] = []
    items_by_listing = {str(item["listing_id"]): item for item in items}
    for line in line_views:
        cart_item = items_by_listing.get(line.listing_id, {})
        raw_location = cart_item.get("pickup_location_id")
        location_id = str(raw_location) if isinstance(raw_location, str) else None
        result = claim_reservation(
            listing_id=line.listing_id,
            checkout_group_id=session_id,
            qty=line.qty,
            ttl_minutes=ttl_min,
            location_id=location_id,
        )
        reservations.append(
            ReservationClaimOut(
                listing_id=line.listing_id,
                qty=line.qty,
                claimed=result.claimed,
                skipped=result.skipped,
            )
        )
        if not result.claimed and not result.skipped:
            service.client.table("checkout_groups").update({"status": "abandoned"}).eq(
                "id", session_id
            ).execute()
            raise AppError(
                code="checkout.stock_unavailable",
                message="An item in your cart is no longer available",
                http_status=409,
                details={
                    "listing_id": line.listing_id,
                    "redirect_to": "cart",
                    "notice_key": "checkout.checkout.stockUnavailable",
                },
            )

    expires_at = datetime.now(UTC) + timedelta(minutes=ttl_min)
    vendor_ids = [group.vendor_id for group in vendor_groups]
    vendor_names = _fetch_vendor_names(service, vendor_ids)
    pickup_locations = _fetch_vendor_locations(service, vendor_ids)

    profile_response = (
        service.client.table("profiles")
        .select("phone")
        .eq("id", current_user.id)
        .maybe_single()
        .execute()
    )
    profile = _extract_data(profile_response)
    profile_dict = profile if isinstance(profile, dict) else {}
    contact_skipped = bool(profile_dict.get("phone"))

    # Fire-and-forget funnel event (checkout_start); server operational, consent-independent.
    # Idempotent per (checkout_group_id, stage); snapshot.lines feeds vendor view attribution.
    emit_checkout_start(
        checkout_group_id=session_id,
        customer_id=current_user.id,
        snapshot={
            "lines": [{"listing_id": line.listing_id, "qty": line.qty} for line in line_views],
            "total_ngwee": subtotal,
        },
    )

    return CheckoutSessionResponse(
        session_id=session_id,
        expires_at=expires_at,
        reservation_ttl_min=ttl_min,
        vendor_groups=[
            VendorGroupOut(
                vendor_id=group.vendor_id,
                vendor_name=vendor_names.get(group.vendor_id, group.vendor_id),
                items=[
                    CartLineOut(
                        id=item.id,
                        listing_id=item.listing_id,
                        vendor_id=item.vendor_id,
                        qty=item.qty,
                        unit_price_ngwee=item.unit_price_ngwee,
                        line_total_ngwee=item.line_total_ngwee,
                        title_override=item.title_override,
                        lead_time_days=item.lead_time_days,
                    )
                    for item in group.items
                ],
                subtotal_ngwee=group.subtotal_ngwee,
                delivery_eligible=group.delivery_eligible,
                pickup_location=pickup_locations.get(group.vendor_id),
            )
            for group in vendor_groups
        ],
        subtotal_ngwee=subtotal,
        reservations=reservations,
        contact_skipped=contact_skipped,
    )


@router.get("/session/{session_id}", response_model=SessionStatusResponse)
async def get_checkout_session_status(
    session_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> SessionStatusResponse:
    group = _fetch_checkout_group(service, session_id, current_user.id)
    expires_at = _session_expires_at(service, session_id)
    status = str(group.get("status") or "pending")
    now = datetime.now(UTC)

    if expires_at is None:
        ttl_min = get_reservation_ttl_minutes()
        created_raw = group.get("created_at")
        if isinstance(created_raw, str):
            created_at = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
            expires_at = created_at + timedelta(minutes=ttl_min)
        else:
            expires_at = now + timedelta(minutes=ttl_min)

    expired = status in {"expired", "abandoned"} or expires_at <= now
    return SessionStatusResponse(
        session_id=session_id,
        status="expired" if expired else status,
        expires_at=expires_at,
        expired=expired,
        redirect_notice_key="checkout.checkout.reservationExpired" if expired else None,
    )


@router.post("/steps/contact", response_model=ContactStepResponse)
async def validate_contact_step(
    body: ContactStepRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ContactStepResponse:
    profile_response = (
        service.client.table("profiles")
        .select("phone")
        .eq("id", current_user.id)
        .maybe_single()
        .execute()
    )
    profile = _extract_data(profile_response)
    profile_dict = profile if isinstance(profile, dict) else {}
    phone_value = profile_dict.get("phone")
    existing_phone = phone_value if isinstance(phone_value, str) else None

    if existing_phone:
        return ContactStepResponse(verified=True, phone=existing_phone, skipped=True)

    if not body.phone:
        raise AppError(
            code="checkout.phone_required",
            message="Phone number is required for checkout",
            http_status=422,
            details={"field": "phone"},
        )

    normalized = _normalize_phone(body.phone)
    service.client.table("profiles").update({"phone": normalized}).eq(
        "id", current_user.id
    ).execute()

    return ContactStepResponse(verified=True, phone=normalized, skipped=False)


@router.post("/steps/fulfilment", response_model=FulfilmentStepResponse)
async def validate_fulfilment_step(
    body: FulfilmentStepRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> FulfilmentStepResponse:
    _ensure_session_active(service, body.session_id, current_user.id)

    user_client = get_user_client(current_user.token, settings)
    cart = _fetch_active_cart_by_user(user_client, current_user.id)
    if cart is None:
        raise AppError(
            code="checkout.cart_empty",
            message="Your cart is empty",
            http_status=400,
        )

    items = _fetch_cart_items(user_client, str(cart["id"]))
    listings = fetch_listings_for_items(items)
    line_views = _build_line_views(items, listings)
    free_threshold = _load_free_delivery_threshold(service)
    vendor_groups = group_by_vendor(line_views, free_delivery_threshold_ngwee=free_threshold)
    groups_by_vendor = {group.vendor_id: group for group in vendor_groups}
    choices_by_vendor = {choice.vendor_id: choice for choice in body.groups}

    if set(choices_by_vendor) != set(groups_by_vendor):
        raise AppError(
            code="checkout.invalid_groups",
            message="Fulfilment choices must cover every vendor group exactly once",
            http_status=422,
        )

    delivery_requested = any(choice.fulfilment == "delivery" for choice in body.groups)
    if delivery_requested and body.address is None:
        raise AppError(
            code="checkout.address_required",
            message="Delivery address is required when any group uses delivery",
            http_status=422,
        )

    zones = _load_delivery_zones(service)
    zone_fees = {
        key: int(zone.get("fee_ngwee", 0))
        for key, zone in zones.items()
        if isinstance(zone.get("fee_ngwee"), int)
    }

    resolved_zone: str | None = None
    pickup_only = False
    if delivery_requested and body.address is not None:
        resolved_zone = resolve_delivery_zone(
            lat=body.address.lat,
            lng=body.address.lng,
            landmark=body.address.landmark,
        )
        if resolved_zone is None:
            pickup_only = True
            for choice in body.groups:
                if choice.fulfilment == "delivery":
                    raise AppError(
                        code="checkout.outside_delivery_zone",
                        message="Address is outside Lusaka delivery zones — pickup only",
                        http_status=422,
                        details={
                            "notice_key": "checkout.checkout.outsideZone",
                            "pickup_only": True,
                        },
                    )

    pickup_locations = _fetch_vendor_locations(service, list(groups_by_vendor))
    results: list[GroupFulfilmentResult] = []
    total_delivery_fee = 0
    subtotal = 0

    for vendor_id, group in groups_by_vendor.items():
        choice = choices_by_vendor[vendor_id]
        group_subtotal = group.subtotal_ngwee
        subtotal += group_subtotal

        if choice.fulfilment == "pickup":
            fee = 0
            zone_key = None
            zone_label = None
        else:
            zone_key = resolved_zone
            zone_label = (
                str(zones[zone_key].get("label")) if zone_key and zone_key in zones else None
            )
            fee = compute_group_delivery_fee_ngwee(
                subtotal_ngwee=group_subtotal,
                zone_key=zone_key,
                zone_fees=zone_fees,
                free_delivery_threshold_ngwee=free_threshold,
            )

        total_delivery_fee += fee
        results.append(
            GroupFulfilmentResult(
                vendor_id=vendor_id,
                fulfilment=choice.fulfilment,
                delivery_zone=zone_key,
                delivery_zone_label=zone_label,
                delivery_fee_ngwee=fee,
                subtotal_ngwee=group_subtotal,
                pickup_location=pickup_locations.get(vendor_id),
            )
        )

    total = subtotal + total_delivery_fee
    service.client.table("checkout_groups").update(
        {
            "subtotal_ngwee": subtotal,
            "delivery_fee_ngwee": total_delivery_fee,
            "total_ngwee": total,
        }
    ).eq("id", body.session_id).execute()

    return FulfilmentStepResponse(
        session_id=body.session_id,
        groups=results,
        subtotal_ngwee=subtotal,
        delivery_fee_ngwee=total_delivery_fee,
        total_ngwee=total,
        resolved_zone_key=resolved_zone,
        pickup_only=pickup_only,
    )
