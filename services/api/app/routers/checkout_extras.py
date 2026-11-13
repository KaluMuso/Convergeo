"""Checkout extras — coupon code and "send as a gift" (flags ``coupons`` / ``gift_orders``).

Both steps only RECORD the buyer's choice on the pending checkout session. The
money decision is re-made at order creation from authoritative cart lines, and
the coupon use is reserved there under the coupon row lock (no overuse under
concurrency). Applying a code here never consumes a use.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from app.core.auth import CurrentUser, get_current_user
from app.core.ratelimit import bump_rate_counter, get_client_ip, raise_rate_limited
from app.core.supabase import get_user_client
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.checkout import (
    ServiceRoleClient,
    _build_line_views,
    _ensure_session_active,
    _fetch_active_cart_by_user,
    _fetch_cart_items,
    _int_or_zero,
    _normalize_phone,
)
from app.services.cart.store import fetch_listings_for_items
from app.services.coupons.rules import MIN_PAYABLE_NGWEE, CouponError, quote_coupon
from app.services.coupons.store import (
    COUPONS_FLAG,
    GIFT_ORDERS_FLAG,
    build_discount_lines,
    coupon_app_error,
    load_coupon_by_code,
    normalize_code,
    precheck_limits,
    require_flag,
)
from app.settings import Settings, get_settings
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix="/checkout", tags=["checkout"])

#: Code guessing guard: per user and per IP, short window.
COUPON_ATTEMPT_LIMIT = 10
COUPON_ATTEMPT_WINDOW = timedelta(minutes=10)
GIFT_WRITE_LIMIT = 20
GIFT_WRITE_WINDOW = timedelta(minutes=10)
_ZM_PHONE_RE = re.compile(r"^\+260[0-9]{9}$")
_LINK_RE = re.compile(r"(https?://|www\.|\.com\b|\.zm\b)", re.IGNORECASE)


class CouponApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    session_id: str = Field(min_length=36, max_length=36)
    code: str = Field(min_length=3, max_length=40)


class CouponVendorShare(BaseModel):
    vendor_id: str
    discount_ngwee: int


class CheckoutTotalsResponse(BaseModel):
    session_id: str
    subtotal_ngwee: int
    delivery_fee_ngwee: int
    discount_ngwee: int
    total_ngwee: int
    coupon_code: str | None = None
    #: "platform" coupons are paid for by Vergeo5; "vendor" coupons by the shop.
    coupon_funder: str | None = None
    vendor_discounts: list[CouponVendorShare] = Field(default_factory=list)


class GiftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    session_id: str = Field(min_length=36, max_length=36)
    recipient_name: str = Field(min_length=1, max_length=80)
    recipient_phone: str = Field(min_length=9, max_length=20)
    message: str | None = Field(default=None, max_length=200)
    #: The buyer confirms the recipient agreed to share their phone (and
    #: address, for delivery) with Vergeo5 for this gift only (DPA).
    recipient_agreed: bool


class GiftResponse(BaseModel):
    session_id: str
    is_gift: bool
    recipient_name: str | None = None
    recipient_phone_masked: str | None = None
    message: str | None = None


def _rate_limit(scope: str, key: str, *, limit: int, window: timedelta, message_key: str) -> None:
    allowed, retry_after = bump_rate_counter(scope=scope, key=key, window=window, limit=limit)
    if not allowed:
        raise_rate_limited(retry_after=retry_after, message_key=message_key)


def _cart_discount_lines(
    service: ServiceRoleClient, current_user: CurrentUser, settings: Settings, *, categories: bool
) -> list[Any]:
    user_client = get_user_client(current_user.token, settings)
    cart = _fetch_active_cart_by_user(user_client, current_user.id)
    if cart is None:
        raise AppError(code="checkout.cart_empty", message="Your cart is empty", http_status=400)
    items = _fetch_cart_items(user_client, str(cart["id"]))
    views = _build_line_views(items, fetch_listings_for_items(items))
    return build_discount_lines(
        service,
        ((view.listing_id, view.vendor_id, view.line_total_ngwee) for view in views),
        needs_categories=categories,
    )


def _totals(group: dict[str, Any], *, session_id: str) -> CheckoutTotalsResponse:
    return CheckoutTotalsResponse(
        session_id=session_id,
        subtotal_ngwee=_int_or_zero(group.get("subtotal_ngwee")),
        delivery_fee_ngwee=_int_or_zero(group.get("delivery_fee_ngwee")),
        discount_ngwee=_int_or_zero(group.get("discount_ngwee")),
        total_ngwee=_int_or_zero(group.get("total_ngwee")),
        coupon_code=group.get("coupon_code") if group.get("discount_ngwee") else None,
    )


def _require_pending(group: dict[str, Any], session_id: str) -> None:
    if str(group.get("status") or "") != "pending":
        raise AppError(
            code="orders.session_already_completed",
            message="Checkout session already completed",
            http_status=409,
            details={"session_id": session_id},
        )


@router.post("/steps/coupon", response_model=CheckoutTotalsResponse)
async def apply_coupon(
    body: CouponApplyRequest,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> CheckoutTotalsResponse:
    require_flag(service, COUPONS_FLAG)
    _rate_limit(
        "coupon_attempt_user",
        current_user.id,
        limit=COUPON_ATTEMPT_LIMIT,
        window=COUPON_ATTEMPT_WINDOW,
        message_key="checkout.coupon.errors.tooManyAttempts",
    )
    _rate_limit(
        "coupon_attempt_ip",
        get_client_ip(request),
        limit=COUPON_ATTEMPT_LIMIT * 3,
        window=COUPON_ATTEMPT_WINDOW,
        message_key="checkout.coupon.errors.tooManyAttempts",
    )
    group, _ = _ensure_session_active(service, body.session_id, current_user.id)
    _require_pending(group, body.session_id)

    subtotal = _int_or_zero(group.get("subtotal_ngwee"))
    delivery = _int_or_zero(group.get("delivery_fee_ngwee"))
    try:
        rule = load_coupon_by_code(service, normalize_code(body.code))
        lines = _cart_discount_lines(
            service, current_user, settings, categories=rule.scope == "category"
        )
        quote = quote_coupon(
            rule,
            lines,
            now=datetime.now(UTC),
            user_id=current_user.id,
            max_discount_ngwee=subtotal + delivery - MIN_PAYABLE_NGWEE,
        )
        precheck_limits(service, rule, user_id=current_user.id)
    except CouponError as exc:
        raise coupon_app_error(exc) from exc

    total = subtotal + delivery - quote.discount_ngwee
    service.client.table("checkout_groups").update(
        {
            "coupon_id": quote.coupon_id,
            "coupon_code": quote.code,
            "discount_ngwee": quote.discount_ngwee,
            "total_ngwee": total,
        }
    ).eq("id", body.session_id).eq("status", "pending").execute()

    return CheckoutTotalsResponse(
        session_id=body.session_id,
        subtotal_ngwee=subtotal,
        delivery_fee_ngwee=delivery,
        discount_ngwee=quote.discount_ngwee,
        total_ngwee=total,
        coupon_code=quote.code,
        coupon_funder=quote.funder,
        vendor_discounts=[
            CouponVendorShare(vendor_id=vendor_id, discount_ngwee=amount)
            for vendor_id, amount in sorted(quote.vendor_discounts.items())
        ],
    )


@router.delete("/steps/coupon", response_model=CheckoutTotalsResponse)
async def remove_coupon(
    session_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> CheckoutTotalsResponse:
    group, _ = _ensure_session_active(service, session_id, current_user.id)
    _require_pending(group, session_id)
    subtotal = _int_or_zero(group.get("subtotal_ngwee"))
    delivery = _int_or_zero(group.get("delivery_fee_ngwee"))
    cleared = {
        **group,
        "coupon_id": None,
        "coupon_code": None,
        "discount_ngwee": 0,
        "total_ngwee": subtotal + delivery,
    }
    service.client.table("checkout_groups").update(
        {
            "coupon_id": None,
            "coupon_code": None,
            "discount_ngwee": 0,
            "total_ngwee": subtotal + delivery,
        }
    ).eq("id", session_id).eq("status", "pending").execute()
    return _totals(cleared, session_id=session_id)


def mask_phone(phone: str | None) -> str | None:
    if not phone or len(phone) < 7:
        return None
    return f"{phone[:4]}••••{phone[-3:]}"


def _validated_gift(body: GiftRequest) -> tuple[str, str, str | None]:
    if not body.recipient_agreed:
        raise AppError(
            code="gift.consent_required",
            message="Confirm the recipient agreed to share their details",
            http_status=422,
            details={"field": "recipient_agreed", "message_key": "checkout.gift.errors.consent"},
        )
    name = " ".join(body.recipient_name.split())
    digits = re.sub(r"\D", "", body.recipient_phone)
    if len(digits) == 10 and digits.startswith("0"):
        digits = digits[1:]  # local 09x / 07x format
    phone = _normalize_phone(digits if len(digits) == 9 else body.recipient_phone)
    if not name:
        raise AppError(
            code="gift.name_required",
            message="Enter the recipient's name",
            http_status=422,
            details={"field": "recipient_name", "message_key": "checkout.gift.errors.name"},
        )
    if not _ZM_PHONE_RE.match(phone):
        raise AppError(
            code="gift.phone_invalid",
            message="Enter a valid Zambian mobile number",
            http_status=422,
            details={"field": "recipient_phone", "message_key": "checkout.gift.errors.phone"},
        )
    message = " ".join((body.message or "").split()) or None
    if message is not None and _LINK_RE.search(message):
        # A gift note is a personal message, not a channel for links/spam.
        raise AppError(
            code="gift.message_invalid",
            message="Gift messages cannot contain links",
            http_status=422,
            details={"field": "message", "message_key": "checkout.gift.errors.message"},
        )
    return name, phone, message


@router.put("/steps/gift", response_model=GiftResponse)
async def set_gift(
    body: GiftRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> GiftResponse:
    require_flag(service, GIFT_ORDERS_FLAG)
    _rate_limit(
        "gift_write",
        current_user.id,
        limit=GIFT_WRITE_LIMIT,
        window=GIFT_WRITE_WINDOW,
        message_key="checkout.gift.errors.tooMany",
    )
    group, _ = _ensure_session_active(service, body.session_id, current_user.id)
    _require_pending(group, body.session_id)
    name, phone, message = _validated_gift(body)
    service.client.table("gift_details").upsert(
        {
            "checkout_group_id": body.session_id,
            "buyer_id": current_user.id,
            "recipient_name": name,
            "recipient_phone": phone,
            "message": message,
            "buyer_attested_at": datetime.now(UTC).isoformat(),
        },
        on_conflict="checkout_group_id",
    ).execute()
    return GiftResponse(
        session_id=body.session_id,
        is_gift=True,
        recipient_name=name,
        recipient_phone_masked=mask_phone(phone),
        message=message,
    )


@router.delete("/steps/gift", response_model=GiftResponse)
async def remove_gift(
    session_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> GiftResponse:
    group, _ = _ensure_session_active(service, session_id, current_user.id)
    _require_pending(group, session_id)
    service.client.table("gift_details").delete().eq("checkout_group_id", session_id).eq(
        "buyer_id", current_user.id
    ).execute()
    return GiftResponse(session_id=session_id, is_gift=False)
