from __future__ import annotations

from collections import defaultdict
from typing import Annotated, Literal, Protocol

from app.core.auth import CurrentUser, get_current_user
from app.core.supabase import get_user_client
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.checkout import _ensure_session_active, _extract_data
from app.routers.checkout_payment import _load_cod_cap_ngwee, _validate_payment_method
from app.services.cart.totals import line_total_ngwee
from app.services.kyc.caps import enforce_first_order_caps_for_vendors
from app.services.orders.create import (
    CartLineInput,
    CreateOrdersResult,
    VendorFulfilmentInput,
    create_orders_atomic,
)
from app.services.orders.events import emit_order_placed_funnel
from app.settings import Settings, get_settings
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from supabase import Client

router = APIRouter(prefix="/orders", tags=["orders"])


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Client: ...


class VendorGroupRequest(BaseModel):
    vendor_id: str
    fulfilment: Literal["delivery", "pickup"]
    delivery_zone: str | None = None
    delivery_fee_ngwee: int = Field(ge=0)
    subtotal_ngwee: int = Field(ge=0)


class CreateOrderRequest(BaseModel):
    session_id: str
    idempotency_key: str = Field(min_length=1, max_length=200)
    method: Literal["momo", "card", "cod"]
    rail: str | None = None
    payer_number: str | None = Field(default=None, max_length=20)
    address_id: str | None = None
    groups: list[VendorGroupRequest] = Field(min_length=1)


class CreatedOrderItemOut(BaseModel):
    order_item_id: str
    listing_id: str
    qty: int
    unit_price_ngwee: int
    line_total_ngwee: int


class CreatedOrderOut(BaseModel):
    order_id: str
    vendor_id: str
    fulfilment: Literal["delivery", "pickup"]
    delivery_zone: str | None = None
    delivery_fee_ngwee: int
    subtotal_ngwee: int
    cod: bool
    commission_snapshot: dict[str, object]
    items: list[CreatedOrderItemOut]


class CreateOrderResponse(BaseModel):
    checkout_group_id: str
    idempotency_key: str
    status: str
    subtotal_ngwee: int
    delivery_fee_ngwee: int
    total_ngwee: int
    replayed: bool
    orders: list[CreatedOrderOut]


def _fetch_active_cart_by_user(client: Client, user_id: str) -> dict[str, object]:
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
    raise AppError(
        code="checkout.cart_empty",
        message="Your cart is empty",
        http_status=400,
        details={"redirect_to": "cart"},
    )


def _fetch_cart_items(client: Client, cart_id: str) -> list[dict[str, object]]:
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


def _to_response(result: CreateOrdersResult) -> CreateOrderResponse:
    return CreateOrderResponse(
        checkout_group_id=result.checkout_group_id,
        idempotency_key=result.idempotency_key,
        status=result.status,
        subtotal_ngwee=result.subtotal_ngwee,
        delivery_fee_ngwee=result.delivery_fee_ngwee,
        total_ngwee=result.total_ngwee,
        replayed=result.replayed,
        orders=[
            CreatedOrderOut(
                order_id=order.order_id,
                vendor_id=order.vendor_id,
                fulfilment=order.fulfilment,
                delivery_zone=order.delivery_zone,
                delivery_fee_ngwee=order.delivery_fee_ngwee,
                subtotal_ngwee=order.subtotal_ngwee,
                cod=order.cod,
                commission_snapshot=order.commission_snapshot,
                items=[
                    CreatedOrderItemOut(
                        order_item_id=item.order_item_id,
                        listing_id=item.listing_id,
                        qty=item.qty,
                        unit_price_ngwee=item.unit_price_ngwee,
                        line_total_ngwee=item.line_total_ngwee,
                    )
                    for item in order.items
                ],
            )
            for order in result.orders
        ],
    )


@router.post("", response_model=CreateOrderResponse)
async def create_orders(
    body: CreateOrderRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> CreateOrderResponse:
    _ensure_session_active(service, body.session_id, current_user.id)

    group_response = (
        service.client.table("checkout_groups")
        .select("subtotal_ngwee, delivery_fee_ngwee, total_ngwee")
        .eq("id", body.session_id)
        .eq("customer_id", current_user.id)
        .maybe_single()
        .execute()
    )
    group = _extract_data(group_response)
    if not isinstance(group, dict):
        raise AppError(
            code="checkout.session_not_found",
            message="Checkout session not found",
            http_status=404,
            details={"session_id": body.session_id},
        )

    total = int(group.get("total_ngwee", 0))

    cod_cap = _load_cod_cap_ngwee(service)
    _validate_payment_method(
        method=body.method,
        rail=body.rail,
        payer_number=body.payer_number,
        total_ngwee=total,
        cod_cap_ngwee=cod_cap,
    )

    if any(group_req.fulfilment == "delivery" for group_req in body.groups) and not body.address_id:
        raise AppError(
            code="checkout.address_required",
            message="Delivery address is required when any group uses delivery",
            http_status=422,
        )

    user_client = get_user_client(current_user.token, settings)
    cart = _fetch_active_cart_by_user(user_client, current_user.id)
    cart_id = str(cart["id"])
    items = _fetch_cart_items(user_client, cart_id)
    if not items:
        raise AppError(
            code="checkout.cart_empty",
            message="Your cart is empty",
            http_status=400,
        )

    listing_ids = sorted({str(item["listing_id"]) for item in items})
    listings_response = (
        service.client.table("vendor_listings")
        .select("id, vendor_id, title_override")
        .in_("id", listing_ids)
        .execute()
    )
    listing_rows = listings_response.data if isinstance(listings_response.data, list) else []
    listings_by_id = {
        str(row["id"]): row for row in listing_rows if isinstance(row, dict) and row.get("id")
    }

    cart_lines: list[CartLineInput] = []
    for item in items:
        listing_id = str(item["listing_id"])
        listing = listings_by_id.get(listing_id, {})
        title = listing.get("title_override")
        qty_raw = item.get("qty", 0)
        price_raw = item.get("unit_price_ngwee", 0)
        if not isinstance(qty_raw, int) or not isinstance(price_raw, int):
            raise AppError(
                code="orders.invalid_cart_line",
                message="Cart line has invalid quantity or price",
                http_status=409,
            )
        cart_lines.append(
            CartLineInput(
                cart_item_id=str(item["id"]),
                listing_id=listing_id,
                vendor_id=str(listing.get("vendor_id", "")),
                qty=qty_raw,
                unit_price_ngwee=price_raw,
                title_snapshot=title if isinstance(title, str) else None,
            )
        )

    vendor_groups = [
        VendorFulfilmentInput(
            vendor_id=group_req.vendor_id,
            fulfilment=group_req.fulfilment,
            delivery_zone=group_req.delivery_zone,
            delivery_fee_ngwee=group_req.delivery_fee_ngwee,
            subtotal_ngwee=group_req.subtotal_ngwee,
        )
        for group_req in body.groups
    ]

    # D9 T1 first-order ≤K500: server-side, every payment method (not just COD).
    # Totals from cart lines (authoritative) + per-vendor delivery fee.
    per_vendor_subtotal: dict[str, int] = defaultdict(int)
    for line in cart_lines:
        per_vendor_subtotal[line.vendor_id] += line_total_ngwee(
            line.qty, line.unit_price_ngwee
        )
    delivery_by_vendor = {group.vendor_id: group.delivery_fee_ngwee for group in vendor_groups}
    vendor_order_totals = {
        vendor_id: subtotal + delivery_by_vendor.get(vendor_id, 0)
        for vendor_id, subtotal in per_vendor_subtotal.items()
    }
    enforce_first_order_caps_for_vendors(service, vendor_order_totals)

    result = create_orders_atomic(
        client=service.client,
        customer_id=current_user.id,
        session_id=body.session_id,
        idempotency_key=body.idempotency_key,
        payment_method=body.method,
        cart_lines=cart_lines,
        vendor_groups=vendor_groups,
        address_id=body.address_id,
    )

    # Fire-and-forget funnel event (order_placed); server operational, consent-independent.
    # Idempotent per (checkout_group_id, stage); marks the session as converted.
    emit_order_placed_funnel(
        checkout_group_id=body.session_id,
        customer_id=current_user.id,
        snapshot={"order_count": len(result.orders), "total_ngwee": total},
    )

    return _to_response(result)
