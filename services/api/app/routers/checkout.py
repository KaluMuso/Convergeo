from __future__ import annotations

import logging
import math
import re
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
from app.services.cart.grouping import (
    CartLineView,
    group_by_vendor,
    line_variant_id,
    line_variant_options,
)
from app.services.cart.merge import validate_item_qty_for_listing
from app.services.cart.read_path import listing_cart_access_conflict, variant_stock_conflict
from app.services.cart.store import fetch_listings_for_items
from app.services.cart.totals import cart_subtotal_ngwee, line_total_ngwee
from app.services.coupons.rules import MIN_PAYABLE_NGWEE
from app.services.listings.class_rules import listing_lead_time_days
from app.services.payments.state import expire_checkout_group_if_unpaid
from app.services.rfq.listing_cart_authority import (
    fetch_rfq_threads_for_items,
    is_rfq_pinned_line,
    validate_rfq_pinned_line_authority,
)
from app.services.stock.claim import (
    claim_reservation,
    get_reservation_ttl_minutes,
    run_sql_script,
    sql_uuid,
)
from app.services.stock.release import release_reservation
from app.settings import Settings, get_settings
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from supabase import Client

router = APIRouter(prefix="/checkout", tags=["checkout"])
logger = logging.getLogger(__name__)

LUSAKA_CENTER_LAT = -15.4167
LUSAKA_CENTER_LNG = 28.2833
ZONE_BANDS_KM: tuple[tuple[str, float], ...] = (
    ("lusaka_a", 5.0),
    ("lusaka_b", 12.0),
    ("lusaka_c", 25.0),
)
DEFAULT_FREE_DELIVERY_THRESHOLD_NGEWEE = 20_000
# Towns a typed landmark can name that are definitely not Lusaka delivery
# (beyond the 25 km Band C ring): provincial and district towns of Zambia.
# Near-Lusaka places stay with the landmark bands instead: Chongwe, Chilanga
# and "Kafue Road" are Band C keywords below. Kafue *town* (~45 km) and
# Chisamba (~50 km) are outside. Matched whole-word; a town name used as a
# Lusaka street or landmark ("Kabwe Roundabout", "Mumbwa Road") is not a town.
# fmt: off
OTHER_TOWN_TOKENS: tuple[str, ...] = (
    # Copperbelt
    "ndola", "kitwe", "chingola", "mufulira", "luanshya", "chililabombwe",
    "kalulushi", "masaiti", "mpongwe", "lufwanyama",
    # Central (outside the Lusaka ring)
    "kabwe", "kapiri mposhi", "kapiri", "mkushi", "serenje", "mumbwa",
    "chibombo", "chisamba", "itezhi tezhi", "itezhi-tezhi",
    # Southern
    "livingstone", "choma", "mazabuka", "monze", "kalomo", "namwala",
    "siavonga", "sinazongwe", "gwembe", "kazungula", "chirundu",
    # Lusaka Province towns outside the ring
    "kafue", "luangwa", "rufunsa",
    # Eastern
    "chipata", "petauke", "katete", "lundazi", "chadiza", "nyimba", "sinda",
    # Northern / Muchinga
    "kasama", "mbala", "mpulungu", "mporokoso", "luwingu", "mpika", "chinsali",
    "nakonde", "isoka",
    # Luapula
    "mansa", "samfya", "kawambwa", "nchelenge", "mwense",
    # North-Western
    "solwezi", "mwinilunga", "kasempa", "kabompo", "zambezi", "chavuma",
    # Western
    "mongu", "senanga", "sesheke", "kaoma", "kalabo", "lukulu", "shangombo",
)
# Words after a town name that make it a Lusaka street / landmark, not a town.
_LUSAKA_STREET_SUFFIXES: tuple[str, ...] = (
    "road", "rd", "roundabout", "round about", "r/a", "rdbt", "rbt", "street", "st",
    "avenue", "ave", "drive", "close", "compound", "cmpd", "overspill", "turn off",
    "turnoff", "turn-off",
)
# fmt: on
# platform_config key naming the delivery zone for a typed Lusaka landmark the
# keyword matcher cannot place. Unset (the default) keeps the strict behaviour.
FALLBACK_DELIVERY_ZONE_KEY = "delivery_fallback_zone"


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Client: ...


class VariantOptionOut(BaseModel):
    group: str
    value: str


class CartLineOut(BaseModel):
    id: str
    listing_id: str
    vendor_id: str
    qty: int
    unit_price_ngwee: int
    line_total_ngwee: int
    title_override: str | None = None
    product_class: str = "A"
    condition: str = "new"
    sale_unit: str = "each"
    unit_step_milli: int = 1000
    min_steps: int = 1
    fulfilment_mode: str = "stocked"
    lead_time_days: int | None = None
    vendor_capacity_per_week: int | None = None
    defect_notes: str | None = None
    listing_variant_id: str | None = None
    variant_options: list[VariantOptionOut] = Field(default_factory=list)


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


def _other_town_pattern() -> re.Pattern[str]:
    ordered = sorted(OTHER_TOWN_TOKENS, key=lambda word: (-len(word), word))
    alternation = "|".join(
        r"[\s-]+".join(re.escape(part) for part in re.split(r"[\s-]+", word)) for word in ordered
    )
    suffixes = "|".join(
        r"[\s-]+".join(re.escape(part) for part in re.split(r"[\s-]+", word))
        for word in sorted(_LUSAKA_STREET_SUFFIXES, key=lambda word: (-len(word), word))
    )
    # "Kafue-Road" / "Kabwe R/A" / "Chipata Overspill" are Lusaka places too.
    return re.compile(
        rf"(?<![a-z0-9])(?:{alternation})(?![a-z0-9])(?![\s-]+(?:{suffixes})(?![a-z0-9]))"
    )


_OTHER_TOWN_PATTERN = _other_town_pattern()


def landmark_names_other_town(landmark: str | None) -> bool:
    """True when a typed landmark names a town outside Lusaka delivery.

    Whole-word, so "Kafue Road" (Lusaka, Band C) and "Kabwe Roundabout" are not
    towns, while "Kafue town" or "Plot 4, Kabwe" are.
    """
    text = " ".join((landmark or "").lower().replace("\u2019", "").replace("'", "").split())
    return bool(_OTHER_TOWN_PATTERN.search(text))


def _keyword_pattern(keywords: tuple[str, ...]) -> re.Pattern[str]:
    ordered = sorted(keywords, key=lambda word: (-len(word), word))
    alternation = "|".join(
        r"\s+".join(re.escape(part) for part in word.split()) for word in ordered
    )
    return re.compile(rf"(?<![a-z0-9])(?:{alternation})(?![a-z0-9])")


# Explicit band words a customer or operator types. Checked first, in this order.
_EXPLICIT_BAND_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("lusaka_a", ("band a", "central", "cbd")),
    ("lusaka_b", ("band b", "mid-ring")),
    ("lusaka_c", ("band c", "outer")),
)
# Area names by band (docs/ops/lusaka-delivery-reference-prices.md section 4/5).
# Bare "garden" and "levy" are left out on purpose: they false-match inside other names.
_AREA_KEYWORDS: dict[str, tuple[str, ...]] = {
    "lusaka_a": (
        "kabulonga",
        "woodlands",
        "east park",
        "cairo road",
        "longacres",
        "rhodes park",
        "northmead",
        "fairview",
        "kabwata",
        "olympia",
        "roma",
        "kalingalinga",
        "emmasdale",
        "manda hill",
        "arcades",
        "levy junction",
        "levy mall",
        "thorn park",
        "thornpark",
        "uth",
        "unza",
    ),
    "lusaka_b": (
        "chilenje",
        "makeni",
        "matero",
        "mtendere",
        "ibex hill",
        "chelston",
        "chelstone",
        "chainda",
        "libala",
        "kamwala",
        "kalundu",
        "lilayi",
        "chawama",
        "ngombe",
        "john laing",
        "chaisa",
        "bauleni",
        "kabanana",
    ),
    "lusaka_c": (
        "chalala",
        "chilanga",
        "airport",
        "kkia",
        "chongwe",
        "kafue road",
        "kanyama",
        "leopards hill",
        "foxdale",
    ),
}
_EXPLICIT_BAND_PATTERNS = tuple(
    (zone, _keyword_pattern(words)) for zone, words in _EXPLICIT_BAND_KEYWORDS
)
# One pattern over every area name so the longest phrase wins wherever it appears.
_AREA_ZONE_BY_KEYWORD = {word: zone for zone, words in _AREA_KEYWORDS.items() for word in words}
_AREA_PATTERN = _keyword_pattern(tuple(_AREA_ZONE_BY_KEYWORD))


def _normalise_landmark(landmark: str) -> str:
    lowered = landmark.lower().replace("\u2019", "").replace("'", "")
    return " ".join(lowered.split())


def _match_landmark_zone(landmark: str) -> str | None:
    """Zone for a typed landmark with no GPS; whole-word, longest area phrase first."""
    text = _normalise_landmark(landmark)
    for zone_key, pattern in _EXPLICIT_BAND_PATTERNS:
        if pattern.search(text):
            return zone_key
    found = [re.sub(r"\s+", " ", m.group(0)) for m in _AREA_PATTERN.finditer(text)]
    if found:
        return _AREA_ZONE_BY_KEYWORD[max(found, key=len)]
    return None


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
        if landmark_names_other_town(landmark):
            return None
        zone = _match_landmark_zone(landmark)
        if zone is not None:
            return zone

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
        .select(
            "id, cart_id, listing_id, qty, unit_price_ngwee, wholesale, "
            "pickup_location_id, rfq_thread_id, listing_variant_id"
        )
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


def _load_fallback_delivery_zone(
    service: ServiceRoleClient, zones: dict[str, dict[str, Any]]
) -> str | None:
    """Operator-chosen zone for a Lusaka landmark the matcher cannot place.

    The fulfilment form collects a free-text landmark and no GPS, and the matcher
    only knows a handful of area names, so most real Lusaka addresses used to be
    refused as "outside Lusaka". Which band (and so which fee) such an address
    gets is a pricing choice, so it is read from ``platform_config`` and only
    honoured when it names an active zone; unset keeps the refusal.
    """
    response = (
        service.client.table("platform_config")
        .select("value")
        .eq("key", FALLBACK_DELIVERY_ZONE_KEY)
        .maybe_single()
        .execute()
    )
    data = _extract_data(response)
    if not isinstance(data, dict):
        return None
    raw = data.get("value")
    if isinstance(raw, str) and raw.strip() in zones:
        return raw.strip()
    return None


def resolve_address_zone(
    service: ServiceRoleClient,
    zones: dict[str, dict[str, Any]],
    *,
    lat: float | None,
    lng: float | None,
    landmark: str | None,
) -> str | None:
    """Delivery zone for an address, with the operator fallback for bare landmarks.

    The fulfilment step and ``POST /orders`` both price delivery through this one
    rule, so the zone an order is created with is the zone the buyer was quoted.
    """
    zone = resolve_delivery_zone(lat=lat, lng=lng, landmark=landmark)
    if zone is None and lat is None and lng is None and not landmark_names_other_town(landmark):
        zone = _load_fallback_delivery_zone(service, zones)
        if zone is not None:
            # Ops review these daily to grow the area keywords / town list.
            # Landmark is truncated: it is address text (Zambia DPA minimisation).
            logger.warning(
                "checkout.delivery_fallback_zone_used",
                extra={
                    "event": "delivery_fallback_zone_used",
                    "fallback_zone": zone,
                    "landmark_excerpt": _normalise_landmark(landmark or "")[:60],
                },
            )
    return zone


def load_zone_fees(zones: dict[str, dict[str, Any]]) -> dict[str, int]:
    return {
        key: int(zone.get("fee_ngwee", 0))
        for key, zone in zones.items()
        if isinstance(zone.get("fee_ngwee"), int)
    }


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
    customer_id: str,
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

    RFQ-pinned lines (accepted listing quotes) use the authoritative thread
    quote instead of ordinary listing tier pricing.

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
    rfq_threads = fetch_rfq_threads_for_items(service.client, items)

    for item in items:
        listing_id = str(item["listing_id"])
        listing = listings_by_id.get(listing_id)

        if is_rfq_pinned_line(item):
            if listing is None:
                conflicts.append({"listing_id": listing_id, "code": "cart.listing_unavailable"})
                continue
            if listing.get("status") != "active":
                conflicts.append({"listing_id": listing_id, "code": "cart.listing_unavailable"})
                continue

            thread_id = str(item["rfq_thread_id"]).strip()
            stored_price = int(item["unit_price_ngwee"])
            _, conflict_code, conflict_details = validate_rfq_pinned_line_authority(
                rfq_thread_id=thread_id,
                customer_id=customer_id,
                listing_id=listing_id,
                stored_unit_price_ngwee=stored_price,
                thread=rfq_threads.get(thread_id),
            )
            if conflict_code is not None:
                conflict: dict[str, Any] = {"listing_id": listing_id, "code": conflict_code}
                if conflict_code == "cart.price_changed":
                    conflict.update(conflict_details)
                conflicts.append(conflict)
                continue
            continue

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
        variant_conflict = variant_stock_conflict(listing_id, listing, int(item["qty"]))
        if variant_conflict is not None:
            conflicts.append(variant_conflict)
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
                product_class=str(listing.get("product_class") or "A"),
                condition=str(listing.get("condition") or "new"),
                sale_unit=str(listing.get("sale_unit") or "each"),
                unit_step_milli=int(listing.get("unit_step_milli") or 1000),
                min_steps=int(listing.get("min_steps") or 1),
                fulfilment_mode=str(listing.get("fulfilment_mode") or "stocked"),
                lead_time_days=listing_lead_time_days(listing),
                vendor_capacity_per_week=(
                    int(listing["vendor_capacity_per_week"])
                    if listing.get("vendor_capacity_per_week") is not None
                    else None
                ),
                defect_notes=(
                    str(listing["defect_notes"]) if listing.get("defect_notes") else None
                ),
                listing_variant_id=line_variant_id(item),
                variant_options=line_variant_options(listing),
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


def _release_session_holds(session_id: str) -> int:
    """Put every stock hold of ``session_id`` back on the shelf right away."""
    group_sql = sql_uuid(session_id, "session_id")
    held = run_sql_script(
        f"SELECT listing_id::text FROM public.stock_reservations "
        f"WHERE checkout_group_id = {group_sql};"
    )
    if not held.ok:
        raise RuntimeError(f"load session holds failed: {held.error}")
    released = 0
    for listing_id in sorted({row for row in held.rows if row}):
        if release_reservation(listing_id=listing_id, checkout_group_id=session_id).released:
            released += 1
    return released


def _supersede_own_pending_sessions(customer_id: str) -> int:
    """Abandon the caller's earlier, never-ordered checkouts and free their stock.

    Every visit to /checkout opens a new session, and each session takes its own
    hold. Without this, a refresh or a trip back to the cart left the buyer
    competing with their own previous hold for up to the reservation TTL: the
    last unit of a listing showed as out of stock in the cart of the very person
    trying to buy it. Only sessions that still hold stock and never produced an
    order or a payment are touched; the status flip waits on the same row lock
    order creation takes, so a session that is completing concurrently wins.
    """
    customer_sql = sql_uuid(customer_id, "customer_id")
    superseded = run_sql_script(
        f"""
BEGIN;
WITH superseded AS (
  UPDATE public.checkout_groups cg
  SET status = 'abandoned'
  WHERE cg.customer_id = {customer_sql}
    AND cg.status = 'pending'
    AND EXISTS (
      SELECT 1 FROM public.stock_reservations sr WHERE sr.checkout_group_id = cg.id
    )
    AND NOT EXISTS (SELECT 1 FROM public.orders o WHERE o.checkout_group_id = cg.id)
    AND NOT EXISTS (SELECT 1 FROM public.payments p WHERE p.checkout_group_id = cg.id)
  RETURNING cg.id
)
SELECT id::text FROM superseded;
COMMIT;
"""
    )
    if not superseded.ok:
        raise RuntimeError(f"supersede pending checkouts failed: {superseded.error}")
    released = 0
    for session_id in sorted({row for row in superseded.rows if row}):
        released += _release_session_holds(session_id)
    return released


def _ensure_session_active(
    service: ServiceRoleClient, session_id: str, customer_id: str
) -> tuple[dict[str, Any], datetime]:
    group = _fetch_checkout_group(service, session_id, customer_id)
    status = str(group.get("status") or "")
    if status == "completed":
        # The order is placed and its holds were consumed, so the reservation
        # clock no longer applies. Expiring here would turn a retried POST /orders
        # (lost response on a slow link) into "reservation expired" for an order
        # that exists; the idempotent replay downstream owns this case.
        return group, datetime.now(UTC)
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
        expire_checkout_group_if_unpaid(
            service.client, checkout_group_id=session_id, terminal_status="expired"
        )
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


def _int_or_zero(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


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
        items,
        listings,
        business_eligible=access.eligible,
        service=service,
        customer_id=current_user.id,
    )

    line_views = _build_line_views(items, listings)
    vendor_groups = group_by_vendor(
        line_views,
        free_delivery_threshold_ngwee=_load_free_delivery_threshold(service),
    )
    subtotal = cart_subtotal_ngwee([(line.qty, line.unit_price_ngwee) for line in line_views])

    try:
        _supersede_own_pending_sessions(current_user.id)
    except Exception:
        # Best effort: the sweeper still reclaims these holds at TTL.
        logger.warning("checkout.supersede_pending_failed", exc_info=True)

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
            expire_checkout_group_if_unpaid(
                service.client, checkout_group_id=session_id, terminal_status="abandoned"
            )
            try:
                # Lines claimed before the one that failed must not stay held.
                _release_session_holds(session_id)
            except Exception:
                logger.warning("checkout.release_partial_holds_failed", exc_info=True)
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
                        product_class=item.product_class,
                        condition=item.condition,
                        sale_unit=item.sale_unit,
                        unit_step_milli=item.unit_step_milli,
                        min_steps=item.min_steps,
                        fulfilment_mode=item.fulfilment_mode,
                        lead_time_days=item.lead_time_days,
                        vendor_capacity_per_week=item.vendor_capacity_per_week,
                        defect_notes=item.defect_notes,
                        listing_variant_id=item.listing_variant_id,
                        variant_options=[
                            VariantOptionOut(group=group_name, value=value)
                            for group_name, value in item.variant_options
                        ],
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
    active_group, _ = _ensure_session_active(service, body.session_id, current_user.id)
    if str(active_group.get("status") or "") == "completed":
        # Totals of an ordered session are what the buyer agreed to pay.
        raise AppError(
            code="orders.session_already_completed",
            message="Checkout session already completed",
            http_status=409,
            details={"session_id": body.session_id},
        )

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
    zone_fees = load_zone_fees(zones)

    resolved_zone: str | None = None
    pickup_only = False
    if delivery_requested and body.address is not None:
        resolved_zone = resolve_address_zone(
            service,
            zones,
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

    # A coupon applied earlier stays applied; it never discounts the delivery
    # fee and never takes the payable amount below MIN_PAYABLE_NGWEE.
    discount = _int_or_zero(active_group.get("discount_ngwee"))
    discount = min(discount, max(0, subtotal + total_delivery_fee - MIN_PAYABLE_NGWEE))
    total = subtotal + total_delivery_fee - discount
    service.client.table("checkout_groups").update(
        {
            "subtotal_ngwee": subtotal,
            "delivery_fee_ngwee": total_delivery_fee,
            "discount_ngwee": discount,
            "total_ngwee": total,
            # POST /orders re-prices from these server-recorded choices; the
            # groups a client sends there are only checked against them.
            "fulfilment_choices": [
                {
                    "vendor_id": result.vendor_id,
                    "fulfilment": result.fulfilment,
                    "delivery_zone": result.delivery_zone,
                }
                for result in results
            ],
        }
    ).eq("id", body.session_id).eq("status", "pending").execute()

    return FulfilmentStepResponse(
        session_id=body.session_id,
        groups=results,
        subtotal_ngwee=subtotal,
        delivery_fee_ngwee=total_delivery_fee,
        total_ngwee=total,
        resolved_zone_key=resolved_zone,
        pickup_only=pickup_only,
    )
