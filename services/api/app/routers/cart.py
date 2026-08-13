from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from typing import Annotated, Any, Literal

import jwt
from app.core.auth import CurrentUser, get_current_user
from app.core.supabase import get_user_client
from app.deps import get_supabase_client
from app.errors import AppError
from app.services.business.access import fetch_business_buyer
from app.services.cart.events import emit_cart_add
from app.services.cart.grouping import CartLineView, group_by_vendor
from app.services.cart.merge import MergeConflict, merge_cart_items, validate_item_qty_for_listing
from app.services.cart.read_path import prepare_cart_items_for_read
from app.services.cart.store import (
    create_guest_cart,
    fetch_active_cart_by_guest,
    fetch_listing,
    fetch_listings_for_items,
    mark_guest_cart_converted,
    service_db_client,
)
from app.services.cart.totals import cart_subtotal_ngwee, line_total_ngwee
from app.services.clips.attribution import validate_clip_attribution
from app.services.inventory.location_stock import resolve_stock_location_id
from app.services.listings.class_rules import (
    count_listing_images,
    count_weekly_committed_qty,
    listing_lead_time_days,
    validate_listing_purchasable_for_cart,
)
from app.services.stock.revalidate import CartLineSnapshot, revalidate_lines
from app.settings import Settings, get_settings
from fastapi import APIRouter, Depends, Request, Response
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel, Field
from supabase import Client

router = APIRouter(prefix="/cart", tags=["cart"])

GUEST_CART_COOKIE = "vergeo_guest_cart"
GUEST_CART_MAX_AGE_SECONDS = 60 * 60 * 24 * 30


@dataclass(frozen=True, slots=True)
class CartOwner:
    cart_id: str | None
    user_id: str | None
    guest_token: str | None
    is_guest: bool


class CartItemInput(BaseModel):
    listing_id: str
    qty: int = Field(ge=1)
    pickup_location_id: str | None = None
    fulfilment: Literal["pickup", "delivery"] | None = None
    delivery_lat: float | None = None
    delivery_lng: float | None = None
    #: M17-P05 attribution. A CLAIM, not a credit: validated server-side against
    #: a published clip that actually links this listing, and silently dropped
    #: otherwise. Refusing the cart action on a bad clip id would let a forged
    #: value DENY someone their add-to-cart, which is the worse bug.
    clip_id: str | None = None


class CartItemUpdate(BaseModel):
    qty: int = Field(ge=1)
    pickup_location_id: str | None = None
    fulfilment: Literal["pickup", "delivery"] | None = None
    delivery_lat: float | None = None
    delivery_lng: float | None = None


class AcceptRfqCartRequest(BaseModel):
    qty: int = Field(default=1, ge=1)
    pickup_location_id: str | None = None
    fulfilment: Literal["pickup", "delivery"] | None = None
    delivery_lat: float | None = None
    delivery_lng: float | None = None


class CartLineResponse(BaseModel):
    id: str
    listing_id: str
    vendor_id: str
    qty: int
    unit_price_ngwee: int
    wholesale: bool
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
    is_rfq_quote: bool = False


class VendorGroupResponse(BaseModel):
    vendor_id: str
    items: list[CartLineResponse]
    subtotal_ngwee: int
    delivery_eligible: bool


class MergeConflictResponse(BaseModel):
    listing_id: str
    code: str
    message_key: str
    details: dict[str, Any]


class ChangeNoticeResponse(BaseModel):
    listing_id: str
    kind: str
    requested_qty: int
    available_qty: int | None = None
    snapshot_price_ngwee: int
    current_price_ngwee: int | None = None


class CartResponse(BaseModel):
    cart_id: str
    items: list[CartLineResponse]
    vendor_groups: list[VendorGroupResponse]
    subtotal_ngwee: int
    conflicts: list[MergeConflictResponse] = Field(default_factory=list)
    notices: list[ChangeNoticeResponse] = Field(default_factory=list)


class RevalidateResponse(BaseModel):
    notices: list[ChangeNoticeResponse]
    has_changes: bool


class SaveForLaterResponse(BaseModel):
    listing_id: str
    product_id: str | None = None
    product_slug: str | None = None
    removed: bool
    cart: CartResponse


def _sign_guest_cart_cookie(guest_token: str, settings: Settings) -> str:
    return jwt.encode(
        {"gt": guest_token, "typ": "cart_guest"},
        settings.supabase_service_role_key,
        algorithm="HS256",
    )


def _verify_guest_cart_cookie(cookie_value: str, settings: Settings) -> str:
    try:
        payload = jwt.decode(
            cookie_value,
            settings.supabase_service_role_key,
            algorithms=["HS256"],
        )
    except InvalidTokenError as exc:
        raise AppError(
            code="cart.invalid_guest_token",
            message="Guest cart token is invalid or expired",
            http_status=401,
            details={"retry": False},
        ) from exc

    guest_token = payload.get("gt")
    if not isinstance(guest_token, str) or not guest_token.strip():
        raise AppError(
            code="cart.invalid_guest_token",
            message="Guest cart token is invalid or expired",
            http_status=401,
            details={"retry": False},
        )
    return guest_token.strip()


def _new_guest_token() -> str:
    return secrets.token_urlsafe(32)


def _set_guest_cookie(response: Response, guest_token: str, settings: Settings) -> None:
    response.set_cookie(
        key=GUEST_CART_COOKIE,
        value=_sign_guest_cart_cookie(guest_token, settings),
        httponly=True,
        secure=settings.env != "development",
        samesite="lax",
        max_age=GUEST_CART_MAX_AGE_SECONDS,
        path="/",
    )


def _clear_guest_cookie(response: Response) -> None:
    response.delete_cookie(key=GUEST_CART_COOKIE, path="/")


async def _optional_current_user(request: Request) -> CurrentUser | None:
    authorization = request.headers.get("Authorization")
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return await get_current_user(request, get_settings())


def _business_eligible_for_user(user_id: str | None) -> bool:
    """Verified-business gate for wholesale pricing. Guests are never eligible."""
    if not user_id:
        return False
    row = fetch_business_buyer(service_db_client(), user_id)
    return bool(row and row.get("status") == "verified")


def _resolve_guest_token(request: Request, settings: Settings) -> str | None:
    cookie = request.cookies.get(GUEST_CART_COOKIE)
    if not cookie:
        return None
    return _verify_guest_cart_cookie(cookie, settings)


def _extract_bearer_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth.removeprefix("Bearer ").strip()
        return token or None
    return None


def _fetch_active_cart_by_user(client: Client, user_id: str) -> dict[str, Any] | None:
    response = (
        client.table("carts")
        .select("id, user_id, guest_token, status")
        .eq("user_id", user_id)
        .eq("status", "active")
        .limit(1)
        .execute()
    )
    rows = response.data
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return rows[0]
    return None


def _create_user_cart(client: Client, user_id: str) -> dict[str, Any]:
    cart_id = str(uuid.uuid4())
    response = (
        client.table("carts")
        .insert({"id": cart_id, "user_id": user_id, "status": "active"})
        .execute()
    )
    rows = response.data
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return rows[0]
    return {"id": cart_id, "user_id": user_id, "guest_token": None, "status": "active"}


async def _resolve_cart_owner(
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
) -> CartOwner:
    current_user = await _optional_current_user(request)
    if current_user is not None:
        client = get_user_client(current_user.token, settings)
        cart = _fetch_active_cart_by_user(client, current_user.id)
        if cart is None:
            cart = _create_user_cart(client, current_user.id)
        return CartOwner(
            cart_id=str(cart["id"]),
            user_id=current_user.id,
            guest_token=None,
            is_guest=False,
        )

    guest_token = _resolve_guest_token(request, settings)
    if guest_token is None:
        guest_token = _new_guest_token()
        _set_guest_cookie(response, guest_token, settings)
        cart = create_guest_cart(guest_token)
        return CartOwner(
            cart_id=str(cart["id"]),
            user_id=None,
            guest_token=guest_token,
            is_guest=True,
        )

    cart = fetch_active_cart_by_guest(guest_token)
    if cart is None:
        cart = create_guest_cart(guest_token)
    return CartOwner(
        cart_id=str(cart["id"]),
        user_id=None,
        guest_token=guest_token,
        is_guest=True,
    )


def _db_client_for_owner(
    owner: CartOwner,
    *,
    settings: Settings,
    user_token: str | None,
) -> Client:
    if owner.is_guest:
        return service_db_client()
    if user_token is None:
        raise AppError(code="unauthorized", message="Authentication required", http_status=401)
    return get_user_client(user_token, settings)


def _fetch_cart_items(client: Client, cart_id: str) -> list[dict[str, Any]]:
    response = (
        client.table("cart_items")
        .select(
            "id, cart_id, listing_id, qty, unit_price_ngwee, wholesale, "
            "pickup_location_id, rfq_thread_id"
        )
        .eq("cart_id", cart_id)
        .execute()
    )
    rows = response.data
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _cart_response(
    *,
    cart_id: str,
    items: list[dict[str, Any]],
    listings_by_id: dict[str, dict[str, Any]],
    business_eligible: bool,
    conflicts: list[MergeConflict] | None = None,
    customer_id: str | None = None,
) -> CartResponse:
    """Build a cart response after read-path access filtering and price derivation."""
    rfq_threads_by_id: dict[str, dict[str, Any]] | None = None
    if customer_id is not None:
        from app.services.rfq.listing_cart_authority import fetch_rfq_threads_for_items

        rfq_threads_by_id = fetch_rfq_threads_for_items(service_db_client(), items)
    prepared = prepare_cart_items_for_read(
        items,
        listings_by_id,
        business_eligible=business_eligible,
        customer_id=customer_id,
        rfq_threads_by_id=rfq_threads_by_id,
    )
    merged_conflicts = list(conflicts or []) + prepared.conflicts
    return _build_cart_response(
        cart_id=cart_id,
        items=prepared.items,
        listings_by_id=listings_by_id,
        conflicts=merged_conflicts or None,
    )


def _build_cart_response(
    *,
    cart_id: str,
    items: list[dict[str, Any]],
    listings_by_id: dict[str, dict[str, Any]],
    conflicts: list[MergeConflict] | None = None,
) -> CartResponse:
    line_views: list[CartLineView] = []
    for item in items:
        listing_id = str(item["listing_id"])
        listing = listings_by_id.get(listing_id, {})
        qty = int(item["qty"])
        unit_price = int(item["unit_price_ngwee"])
        from app.services.rfq.listing_cart_authority import is_rfq_pinned_line

        is_rfq_quote = is_rfq_pinned_line(item)
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
                    str(listing["defect_notes"])
                    if listing.get("defect_notes")
                    else None
                ),
                is_rfq_quote=is_rfq_quote,
            )
        )

    vendor_groups = group_by_vendor(line_views)
    subtotal = cart_subtotal_ngwee(
        [(line.qty, line.unit_price_ngwee) for line in line_views],
    )

    return CartResponse(
        cart_id=cart_id,
        items=[
            CartLineResponse(
                id=line.id,
                listing_id=line.listing_id,
                vendor_id=line.vendor_id,
                qty=line.qty,
                unit_price_ngwee=line.unit_price_ngwee,
                wholesale=line.wholesale,
                line_total_ngwee=line.line_total_ngwee,
                title_override=line.title_override,
                product_class=line.product_class,
                condition=line.condition,
                sale_unit=line.sale_unit,
                unit_step_milli=line.unit_step_milli,
                min_steps=line.min_steps,
                fulfilment_mode=line.fulfilment_mode,
                lead_time_days=line.lead_time_days,
                vendor_capacity_per_week=line.vendor_capacity_per_week,
                defect_notes=line.defect_notes,
                is_rfq_quote=line.is_rfq_quote,
            )
            for line in line_views
        ],
        vendor_groups=[
            VendorGroupResponse(
                vendor_id=group.vendor_id,
                items=[
                    CartLineResponse(
                        id=item.id,
                        listing_id=item.listing_id,
                        vendor_id=item.vendor_id,
                        qty=item.qty,
                        unit_price_ngwee=item.unit_price_ngwee,
                        wholesale=item.wholesale,
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
                        is_rfq_quote=item.is_rfq_quote,
                    )
                    for item in group.items
                ],
                subtotal_ngwee=group.subtotal_ngwee,
                delivery_eligible=group.delivery_eligible,
            )
            for group in vendor_groups
        ],
        subtotal_ngwee=subtotal,
        conflicts=[
            MergeConflictResponse(
                listing_id=conflict.listing_id,
                code=conflict.code,
                message_key=conflict.message_key,
                details=conflict.details,
            )
            for conflict in (conflicts or [])
        ],
    )


def _resolve_line_location_id(
    listing_id: str,
    *,
    pickup_location_id: str | None,
    fulfilment: Literal["pickup", "delivery"] | None,
    delivery_lat: float | None,
    delivery_lng: float | None,
    existing_location_id: str | None = None,
) -> str | None:
    if pickup_location_id is not None:
        return resolve_stock_location_id(
            listing_id,
            pickup_location_id=pickup_location_id,
        )
    if fulfilment == "delivery" and delivery_lat is not None and delivery_lng is not None:
        return resolve_stock_location_id(
            listing_id,
            fulfilment="delivery",
            delivery_lat=delivery_lat,
            delivery_lng=delivery_lng,
        )
    if existing_location_id is not None:
        return resolve_stock_location_id(
            listing_id,
            pickup_location_id=existing_location_id,
        )
    return resolve_stock_location_id(listing_id)


def _enforce_listing_cart_rules(
    listing: dict[str, Any],
    qty: int,
    *,
    location_id: str | None = None,
) -> None:
    service = service_db_client()
    listing_id = str(listing["id"])
    product_class = str(listing.get("product_class") or "A")
    release_flags = {
        "C": ("product_class_c_customer_release",),
        "D": (
            "product_class_d_customer_release",
            "product_class_d_operations_approved",
        ),
        "E": ("product_class_e_customer_release",),
    }
    customer_released = True
    for flag in release_flags.get(product_class, ()):
        response = (
            service.table("feature_flags")
            .select("enabled")
            .eq("flag", flag)
            .maybe_single()
            .execute()
        )
        row = response.data if isinstance(response.data, dict) else None
        # A missing flag must not make a pre-release product class purchasable.
        if row is None or row.get("enabled") is not True:
            customer_released = False
            break
    evidence_count = count_listing_images(service, listing_id)
    weekly_committed = count_weekly_committed_qty(service, listing_id)
    validate_listing_purchasable_for_cart(
        listing=listing,
        qty=qty,
        evidence_image_count=evidence_count,
        weekly_committed_qty=weekly_committed,
        location_id=location_id,
        customer_released=customer_released,
    )


@router.get("", response_model=CartResponse)
async def get_cart(
    owner: Annotated[CartOwner, Depends(_resolve_cart_owner)],
    settings: Annotated[Settings, Depends(get_settings)],
    request: Request,
) -> CartResponse:
    client = _db_client_for_owner(
        owner,
        settings=settings,
        user_token=_extract_bearer_token(request),
    )
    cart_id = owner.cart_id or ""
    items = _fetch_cart_items(client, cart_id)
    listings = fetch_listings_for_items(items)
    return _cart_response(
        cart_id=cart_id,
        items=items,
        listings_by_id=listings,
        business_eligible=_business_eligible_for_user(owner.user_id),
        customer_id=owner.user_id,
    )


@router.post("/items", response_model=CartResponse)
async def add_cart_item(
    body: CartItemInput,
    owner: Annotated[CartOwner, Depends(_resolve_cart_owner)],
    settings: Annotated[Settings, Depends(get_settings)],
    # Attribution validation only (M17-P05). Provided by the dependency rather
    # than imported, so the service-role client stays greppable to the allowlist
    # in tests/test_service_role_import_guard.py.
    service_client: Annotated[Any, Depends(get_supabase_client)],
    request: Request,
) -> CartResponse:
    # Eligibility is resolved BEFORE the fetch: under D36 it decides whether the
    # listing is visible at all, not merely how it is priced.
    business_eligible = _business_eligible_for_user(owner.user_id)
    listing = fetch_listing(body.listing_id, business_eligible=business_eligible)
    unit_price, wholesale = validate_item_qty_for_listing(
        listing=listing, qty=body.qty, business_eligible=business_eligible
    )
    location_id = _resolve_line_location_id(
        body.listing_id,
        pickup_location_id=body.pickup_location_id,
        fulfilment=body.fulfilment,
        delivery_lat=body.delivery_lat,
        delivery_lng=body.delivery_lng,
    )
    _enforce_listing_cart_rules(listing, body.qty, location_id=location_id)

    client = _db_client_for_owner(
        owner,
        settings=settings,
        user_token=_extract_bearer_token(request),
    )
    cart_id = owner.cart_id or ""

    existing = (
        client.table("cart_items")
        .select("id, qty, pickup_location_id")
        .eq("cart_id", cart_id)
        .eq("listing_id", body.listing_id)
        .limit(1)
        .execute()
    )
    rows = existing.data if isinstance(existing.data, list) else []
    # Line WRITES go through the service client: migration 0086 revoked client
    # INSERT/UPDATE on cart_items so unit_price_ngwee/wholesale cannot be set
    # from outside this API (B0-P02a). Ownership is already established —
    # cart_id comes from _resolve_cart_owner (auth token or verified guest
    # cookie), never from request input — and every write below scopes on it.
    line_writer = service_db_client()
    if rows and isinstance(rows[0], dict):
        existing_location = rows[0].get("pickup_location_id")
        existing_location_id = (
            str(existing_location) if isinstance(existing_location, str) else None
        )
        new_qty = int(rows[0]["qty"]) + body.qty
        location_id = _resolve_line_location_id(
            body.listing_id,
            pickup_location_id=body.pickup_location_id,
            fulfilment=body.fulfilment,
            delivery_lat=body.delivery_lat,
            delivery_lng=body.delivery_lng,
            existing_location_id=existing_location_id,
        )
        unit_price, wholesale = validate_item_qty_for_listing(
            listing=listing, qty=new_qty, business_eligible=business_eligible
        )
        _enforce_listing_cart_rules(listing, new_qty, location_id=location_id)
        line_writer.table("cart_items").update(
            {
                "qty": new_qty,
                "unit_price_ngwee": unit_price,
                "wholesale": wholesale,
                "pickup_location_id": location_id,
            }
        ).eq("id", str(rows[0]["id"])).eq("cart_id", cart_id).execute()
    else:
        line_writer.table("cart_items").insert(
            {
                "cart_id": cart_id,
                "listing_id": body.listing_id,
                "qty": body.qty,
                "unit_price_ngwee": unit_price,
                "wholesale": wholesale,
                "pickup_location_id": location_id,
            }
        ).execute()

    # Fire-and-forget funnel event (cart_add); server operational, consent-independent.
    # snapshot.lines carries the listing so vendor analytics can attribute the view.
    line: dict[str, Any] = {"listing_id": body.listing_id, "qty": body.qty}
    attributed_clip = validate_clip_attribution(
        service_client,
        clip_id=body.clip_id,
        listing_id=body.listing_id,
    )
    if attributed_clip:
        line["clip_id"] = attributed_clip
    emit_cart_add(
        checkout_group_id=None,
        customer_id=owner.user_id,
        snapshot={"lines": [line]},
    )

    items = _fetch_cart_items(client, cart_id)
    listings = fetch_listings_for_items(items)
    return _cart_response(
        cart_id=cart_id,
        items=items,
        listings_by_id=listings,
        business_eligible=business_eligible,
        customer_id=owner.user_id,
    )


@router.patch("/items/{listing_id}", response_model=CartResponse)
async def update_cart_item(
    listing_id: str,
    body: CartItemUpdate,
    owner: Annotated[CartOwner, Depends(_resolve_cart_owner)],
    settings: Annotated[Settings, Depends(get_settings)],
    request: Request,
) -> CartResponse:
    business_eligible = _business_eligible_for_user(owner.user_id)
    listing = fetch_listing(listing_id, business_eligible=business_eligible)

    client = _db_client_for_owner(
        owner,
        settings=settings,
        user_token=_extract_bearer_token(request),
    )
    cart_id = owner.cart_id or ""

    existing = (
        client.table("cart_items")
        .select("pickup_location_id, rfq_thread_id, unit_price_ngwee, wholesale")
        .eq("cart_id", cart_id)
        .eq("listing_id", listing_id)
        .limit(1)
        .execute()
    )
    existing_rows = existing.data if isinstance(existing.data, list) else []
    existing_location_id: str | None = None
    rfq_thread_id: str | None = None
    rfq_unit_price: int | None = None
    rfq_wholesale = False
    if existing_rows and isinstance(existing_rows[0], dict):
        raw_location = existing_rows[0].get("pickup_location_id")
        if isinstance(raw_location, str):
            existing_location_id = raw_location
        raw_rfq = existing_rows[0].get("rfq_thread_id")
        if isinstance(raw_rfq, str):
            rfq_thread_id = raw_rfq
            raw_price = existing_rows[0].get("unit_price_ngwee")
            if raw_price is not None:
                rfq_unit_price = int(raw_price)
            rfq_wholesale = bool(existing_rows[0].get("wholesale"))

    location_id = _resolve_line_location_id(
        listing_id,
        pickup_location_id=body.pickup_location_id,
        fulfilment=body.fulfilment,
        delivery_lat=body.delivery_lat,
        delivery_lng=body.delivery_lng,
        existing_location_id=existing_location_id,
    )
    if rfq_thread_id is not None and rfq_unit_price is not None:
        unit_price = rfq_unit_price
        wholesale = rfq_wholesale
    else:
        unit_price, wholesale = validate_item_qty_for_listing(
            listing=listing, qty=body.qty, business_eligible=business_eligible
        )
    _enforce_listing_cart_rules(listing, body.qty, location_id=location_id)

    # Service client for the same reason as add_cart_item: 0086 revoked client
    # writes on cart_items, and the price columns must come from this API's
    # re-derivation only. cart_id is from the resolved owner, so the .eq scope
    # is the authz.
    updated = (
        service_db_client()
        .table("cart_items")
        .update(
            {
                "qty": body.qty,
                "unit_price_ngwee": unit_price,
                "wholesale": wholesale,
                "pickup_location_id": location_id,
            }
        )
        .eq("cart_id", cart_id)
        .eq("listing_id", listing_id)
        .execute()
    )
    rows = updated.data if isinstance(updated.data, list) else []
    if not rows:
        raise AppError(
            code="cart.item_not_found",
            message="Cart item not found",
            http_status=404,
            details={"listing_id": listing_id},
        )

    items = _fetch_cart_items(client, cart_id)
    listings = fetch_listings_for_items(items)
    return _cart_response(
        cart_id=cart_id,
        items=items,
        listings_by_id=listings,
        business_eligible=business_eligible,
        customer_id=owner.user_id,
    )


@router.delete("/items/{listing_id}", response_model=CartResponse)
async def remove_cart_item(
    listing_id: str,
    owner: Annotated[CartOwner, Depends(_resolve_cart_owner)],
    settings: Annotated[Settings, Depends(get_settings)],
    request: Request,
) -> CartResponse:
    client = _db_client_for_owner(
        owner,
        settings=settings,
        user_token=_extract_bearer_token(request),
    )
    cart_id = owner.cart_id or ""

    deleted = (
        client.table("cart_items")
        .delete()
        .eq("cart_id", cart_id)
        .eq("listing_id", listing_id)
        .execute()
    )
    rows = deleted.data if isinstance(deleted.data, list) else []
    if not rows:
        raise AppError(
            code="cart.item_not_found",
            message="Cart item not found",
            http_status=404,
            details={"listing_id": listing_id},
        )

    items = _fetch_cart_items(client, cart_id)
    listings = fetch_listings_for_items(items)
    return _cart_response(
        cart_id=cart_id,
        items=items,
        listings_by_id=listings,
        business_eligible=_business_eligible_for_user(owner.user_id),
        customer_id=owner.user_id,
    )


def _notice_responses_for_items(items: list[dict[str, Any]]) -> list[ChangeNoticeResponse]:
    from app.services.rfq.listing_cart_authority import is_rfq_pinned_line

    snapshots = [
        CartLineSnapshot(
            listing_id=str(item["listing_id"]),
            qty=int(item["qty"]),
            unit_price_ngwee=int(item["unit_price_ngwee"]),
            pickup_location_id=(
                str(item["pickup_location_id"])
                if isinstance(item.get("pickup_location_id"), str)
                else None
            ),
        )
        for item in items
        if not is_rfq_pinned_line(item)
    ]
    result = revalidate_lines(snapshots)
    return [
        ChangeNoticeResponse(
            listing_id=notice.listing_id,
            kind=notice.kind,
            requested_qty=notice.requested_qty,
            available_qty=notice.available_qty,
            snapshot_price_ngwee=notice.snapshot_price_ngwee,
            current_price_ngwee=notice.current_price_ngwee,
        )
        for notice in result.notices
    ]


@router.post("/revalidate", response_model=RevalidateResponse)
async def revalidate_cart(
    owner: Annotated[CartOwner, Depends(_resolve_cart_owner)],
    settings: Annotated[Settings, Depends(get_settings)],
    request: Request,
) -> RevalidateResponse:
    """Compare cart line snapshots to live listing price/stock (honest change notices)."""
    client = _db_client_for_owner(
        owner,
        settings=settings,
        user_token=_extract_bearer_token(request),
    )
    cart_id = owner.cart_id or ""
    items = _fetch_cart_items(client, cart_id)
    notices = _notice_responses_for_items(items)
    return RevalidateResponse(notices=notices, has_changes=len(notices) > 0)


@router.post("/items/{listing_id}/save-for-later", response_model=SaveForLaterResponse)
async def save_cart_item_for_later(
    listing_id: str,
    owner: Annotated[CartOwner, Depends(_resolve_cart_owner)],
    settings: Annotated[Settings, Depends(get_settings)],
    request: Request,
) -> SaveForLaterResponse:
    """Remove a cart line and return product identity so the client can persist wishlist."""
    client = _db_client_for_owner(
        owner,
        settings=settings,
        user_token=_extract_bearer_token(request),
    )
    cart_id = owner.cart_id or ""
    existing = (
        client.table("cart_items")
        .select("id")
        .eq("cart_id", cart_id)
        .eq("listing_id", listing_id)
        .limit(1)
        .execute()
    )
    rows = existing.data if isinstance(existing.data, list) else []
    if not rows:
        raise AppError(
            code="cart.item_not_found",
            message="Cart item not found",
            http_status=404,
            details={"listing_id": listing_id},
        )

    client.table("cart_items").delete().eq("cart_id", cart_id).eq(
        "listing_id", listing_id
    ).execute()

    product_id: str | None = None
    product_slug: str | None = None
    service = service_db_client()
    listing_response = (
        service.table("vendor_listings")
        .select("product_id, products(id, slug)")
        .eq("id", listing_id)
        .limit(1)
        .execute()
    )
    listing_rows = listing_response.data if isinstance(listing_response.data, list) else []
    if listing_rows and isinstance(listing_rows[0], dict):
        row = listing_rows[0]
        raw_product = row.get("products")
        if isinstance(raw_product, dict):
            product_id = str(raw_product.get("id") or "") or None
            product_slug = str(raw_product.get("slug")).strip() if raw_product.get("slug") else None
        elif row.get("product_id"):
            product_id = str(row["product_id"])

    if owner.user_id and product_id:
        service.table("user_wishlist").upsert(
            {
                "user_id": owner.user_id,
                "product_id": product_id,
            },
            on_conflict="user_id,product_id",
        ).execute()

    items = _fetch_cart_items(client, cart_id)
    listings = fetch_listings_for_items(items)
    cart = _cart_response(
        cart_id=cart_id,
        items=items,
        listings_by_id=listings,
        business_eligible=_business_eligible_for_user(owner.user_id),
        customer_id=owner.user_id,
    )
    return SaveForLaterResponse(
        listing_id=listing_id,
        product_id=product_id,
        product_slug=product_slug,
        removed=True,
        cart=cart,
    )


@router.post("/merge", response_model=CartResponse)
async def merge_cart_on_login(
    response: Response,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    request: Request,
) -> CartResponse:
    guest_token = _resolve_guest_token(request, settings)
    user_client = get_user_client(current_user.token, settings)

    user_cart = _fetch_active_cart_by_user(user_client, current_user.id)
    if user_cart is None:
        user_cart = _create_user_cart(user_client, current_user.id)
    user_cart_id = str(user_cart["id"])

    user_items = _fetch_cart_items(user_client, user_cart_id)
    guest_items: list[dict[str, Any]] = []
    guest_cart_id: str | None = None

    if guest_token is not None:
        guest_cart = fetch_active_cart_by_guest(guest_token)
        if guest_cart is not None:
            guest_cart_id = str(guest_cart["id"])
            guest_items = _fetch_cart_items(service_db_client(), guest_cart_id)

    all_items = user_items + guest_items
    listings = fetch_listings_for_items(all_items)
    from app.services.rfq.listing_cart_authority import fetch_rfq_threads_for_items

    rfq_threads_by_id = fetch_rfq_threads_for_items(service_db_client(), all_items)
    merged_items, conflicts = merge_cart_items(
        user_items=user_items,
        guest_items=guest_items,
        listings_by_id=listings,
        business_eligible=_business_eligible_for_user(current_user.id),
        customer_id=current_user.id,
        rfq_threads_by_id=rfq_threads_by_id,
    )

    # DELETE stays on the user client — 0086 left client DELETE granted, and
    # exercising it here keeps the RLS delete path honest. The INSERT of the
    # re-derived lines must be the service client (0086, B0-P02a).
    user_client.table("cart_items").delete().eq("cart_id", user_cart_id).execute()
    if merged_items:
        service_db_client().table("cart_items").insert(
            [
                {
                    "cart_id": user_cart_id,
                    "listing_id": item.listing_id,
                    "qty": item.qty,
                    "unit_price_ngwee": item.unit_price_ngwee,
                    "wholesale": item.wholesale,
                    **(
                        {"rfq_thread_id": item.rfq_thread_id}
                        if item.rfq_thread_id is not None
                        else {}
                    ),
                }
                for item in merged_items
            ]
        ).execute()

    if guest_cart_id is not None:
        mark_guest_cart_converted(guest_cart_id)

    _clear_guest_cookie(response)

    final_items = _fetch_cart_items(user_client, user_cart_id)
    return _cart_response(
        cart_id=user_cart_id,
        items=final_items,
        listings_by_id=listings,
        business_eligible=_business_eligible_for_user(current_user.id),
        conflicts=conflicts,
        customer_id=current_user.id,
    )


@router.post("/rfq/{rfq_id}/accept", response_model=CartResponse)
async def accept_rfq_into_cart(
    rfq_id: str,
    body: AcceptRfqCartRequest,
    owner: Annotated[CartOwner, Depends(_resolve_cart_owner)],
    settings: Annotated[Settings, Depends(get_settings)],
    request: Request,
) -> CartResponse:
    """Convert an accepted vendor quote into a cart line at the quoted ngwee price."""
    if owner.is_guest or owner.user_id is None:
        raise AppError(
            code="cart.auth_required",
            message="Sign in to accept a quote into your cart",
            http_status=401,
            details={},
        )

    from app.routers.rfq import load_rfq_for_cart_accept

    service = service_db_client()
    rfq_row = load_rfq_for_cart_accept(
        service,
        rfq_id=rfq_id,
        customer_id=owner.user_id,
    )
    listing_id = str(rfq_row["listing_id"])
    quote_price = int(rfq_row["quote_price_ngwee"])

    business_eligible = _business_eligible_for_user(owner.user_id)
    listing = fetch_listing(listing_id, business_eligible=business_eligible)
    location_id = _resolve_line_location_id(
        listing_id,
        pickup_location_id=body.pickup_location_id,
        fulfilment=body.fulfilment,
        delivery_lat=body.delivery_lat,
        delivery_lng=body.delivery_lng,
    )
    _enforce_listing_cart_rules(listing, body.qty, location_id=location_id)

    client = _db_client_for_owner(
        owner,
        settings=settings,
        user_token=_extract_bearer_token(request),
    )
    cart_id = owner.cart_id or ""
    line_writer = service_db_client()

    existing = (
        client.table("cart_items")
        .select("id, qty, pickup_location_id")
        .eq("cart_id", cart_id)
        .eq("listing_id", listing_id)
        .limit(1)
        .execute()
    )
    rows = existing.data if isinstance(existing.data, list) else []

    line_payload = {
        "qty": body.qty,
        "unit_price_ngwee": quote_price,
        "wholesale": False,
        "pickup_location_id": location_id,
        "rfq_thread_id": rfq_id,
    }

    if rows and isinstance(rows[0], dict):
        line_writer.table("cart_items").update(line_payload).eq(
            "id", str(rows[0]["id"])
        ).eq("cart_id", cart_id).execute()
    else:
        line_writer.table("cart_items").insert(
            {
                "cart_id": cart_id,
                "listing_id": listing_id,
                **line_payload,
            }
        ).execute()

    service.table("rfq_threads").update({"status": "accepted"}).eq("id", rfq_id).execute()

    items = _fetch_cart_items(client, cart_id)
    listings = fetch_listings_for_items(items)
    return _cart_response(
        cart_id=cart_id,
        items=items,
        listings_by_id=listings,
        business_eligible=business_eligible,
        customer_id=owner.user_id,
    )
