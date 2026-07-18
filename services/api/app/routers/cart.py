from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from typing import Annotated, Any

import jwt
from app.core.auth import CurrentUser, get_current_user
from app.core.supabase import get_user_client
from app.errors import AppError
from app.services.business.access import fetch_business_buyer
from app.services.cart.events import emit_cart_add
from app.services.cart.grouping import CartLineView, group_by_vendor
from app.services.cart.merge import MergeConflict, merge_cart_items, validate_item_qty_for_listing
from app.services.cart.store import (
    create_guest_cart,
    fetch_active_cart_by_guest,
    fetch_listing,
    fetch_listings_for_items,
    mark_guest_cart_converted,
    service_db_client,
)
from app.services.cart.totals import cart_subtotal_ngwee, line_total_ngwee
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


class CartItemUpdate(BaseModel):
    qty: int = Field(ge=1)


class CartLineResponse(BaseModel):
    id: str
    listing_id: str
    vendor_id: str
    qty: int
    unit_price_ngwee: int
    wholesale: bool
    line_total_ngwee: int
    title_override: str | None = None


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


class CartResponse(BaseModel):
    cart_id: str
    items: list[CartLineResponse]
    vendor_groups: list[VendorGroupResponse]
    subtotal_ngwee: int
    conflicts: list[MergeConflictResponse] = Field(default_factory=list)


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
        .select("id, cart_id, listing_id, qty, unit_price_ngwee, wholesale")
        .eq("cart_id", cart_id)
        .execute()
    )
    rows = response.data
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


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
    return _build_cart_response(cart_id=cart_id, items=items, listings_by_id=listings)


@router.post("/items", response_model=CartResponse)
async def add_cart_item(
    body: CartItemInput,
    owner: Annotated[CartOwner, Depends(_resolve_cart_owner)],
    settings: Annotated[Settings, Depends(get_settings)],
    request: Request,
) -> CartResponse:
    listing = fetch_listing(body.listing_id)
    business_eligible = _business_eligible_for_user(owner.user_id)
    unit_price, wholesale = validate_item_qty_for_listing(
        listing=listing, qty=body.qty, business_eligible=business_eligible
    )

    client = _db_client_for_owner(
        owner,
        settings=settings,
        user_token=_extract_bearer_token(request),
    )
    cart_id = owner.cart_id or ""

    existing = (
        client.table("cart_items")
        .select("id, qty")
        .eq("cart_id", cart_id)
        .eq("listing_id", body.listing_id)
        .limit(1)
        .execute()
    )
    rows = existing.data if isinstance(existing.data, list) else []
    if rows and isinstance(rows[0], dict):
        new_qty = int(rows[0]["qty"]) + body.qty
        unit_price, wholesale = validate_item_qty_for_listing(
            listing=listing, qty=new_qty, business_eligible=business_eligible
        )
        client.table("cart_items").update(
            {
                "qty": new_qty,
                "unit_price_ngwee": unit_price,
                "wholesale": wholesale,
            }
        ).eq("id", str(rows[0]["id"])).execute()
    else:
        client.table("cart_items").insert(
            {
                "cart_id": cart_id,
                "listing_id": body.listing_id,
                "qty": body.qty,
                "unit_price_ngwee": unit_price,
                "wholesale": wholesale,
            }
        ).execute()

    # Fire-and-forget funnel event (cart_add); server operational, consent-independent.
    # snapshot.lines carries the listing so vendor analytics can attribute the view.
    emit_cart_add(
        checkout_group_id=None,
        customer_id=owner.user_id,
        snapshot={"lines": [{"listing_id": body.listing_id, "qty": body.qty}]},
    )

    items = _fetch_cart_items(client, cart_id)
    listings = fetch_listings_for_items(items)
    return _build_cart_response(cart_id=cart_id, items=items, listings_by_id=listings)


@router.patch("/items/{listing_id}", response_model=CartResponse)
async def update_cart_item(
    listing_id: str,
    body: CartItemUpdate,
    owner: Annotated[CartOwner, Depends(_resolve_cart_owner)],
    settings: Annotated[Settings, Depends(get_settings)],
    request: Request,
) -> CartResponse:
    listing = fetch_listing(listing_id)
    business_eligible = _business_eligible_for_user(owner.user_id)
    unit_price, wholesale = validate_item_qty_for_listing(
        listing=listing, qty=body.qty, business_eligible=business_eligible
    )

    client = _db_client_for_owner(
        owner,
        settings=settings,
        user_token=_extract_bearer_token(request),
    )
    cart_id = owner.cart_id or ""

    updated = (
        client.table("cart_items")
        .update(
            {
                "qty": body.qty,
                "unit_price_ngwee": unit_price,
                "wholesale": wholesale,
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
    return _build_cart_response(cart_id=cart_id, items=items, listings_by_id=listings)


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
    return _build_cart_response(cart_id=cart_id, items=items, listings_by_id=listings)


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
    merged_items, conflicts = merge_cart_items(
        user_items=user_items,
        guest_items=guest_items,
        listings_by_id=listings,
        business_eligible=_business_eligible_for_user(current_user.id),
    )

    user_client.table("cart_items").delete().eq("cart_id", user_cart_id).execute()
    if merged_items:
        user_client.table("cart_items").insert(
            [
                {
                    "cart_id": user_cart_id,
                    "listing_id": item.listing_id,
                    "qty": item.qty,
                    "unit_price_ngwee": item.unit_price_ngwee,
                    "wholesale": item.wholesale,
                }
                for item in merged_items
            ]
        ).execute()

    if guest_cart_id is not None:
        mark_guest_cart_converted(guest_cart_id)

    _clear_guest_cookie(response)

    final_items = _fetch_cart_items(user_client, user_cart_id)
    return _build_cart_response(
        cart_id=user_cart_id,
        items=final_items,
        listings_by_id=listings,
        conflicts=conflicts,
    )
