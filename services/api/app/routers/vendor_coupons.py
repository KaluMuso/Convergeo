"""Vendor: the shop's own (vendor-funded) coupons (flag ``coupons``).

A vendor coupon can only discount that vendor's items (DB check + rules), is
capped at ``vendor_coupon_max_percent_bps`` and reduces the vendor's revenue:
commission is charged on the discounted price.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.errors import AppError
from app.services.coupons.manage import (
    CouponCreateRequest,
    CouponListResponse,
    CouponOut,
    CouponStatusRequest,
    assert_vendor_owns_listing,
    build_coupon_row,
    insert_coupon,
    list_coupons,
    set_coupon_status,
    vendor_max_percent_bps,
)
from app.services.coupons.rules import LUSAKA
from app.services.coupons.store import COUPONS_FLAG, ServiceRoleClient, require_flag
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/vendor/coupons", tags=["vendor-coupons"])


def _vendor_id(service: ServiceRoleClient, user: CurrentUser) -> str:
    response = (
        service.client.table("vendors")
        .select("id, status")
        .eq("owner_user_id", user.id)
        .maybe_single()
        .execute()
    )
    data: Any = getattr(response, "data", None)
    if isinstance(data, list):
        data = data[0] if data else None
    if not isinstance(data, dict):
        raise AppError(
            code="forbidden",
            message="Authenticated user does not own a vendor profile",
            http_status=403,
            details={"message_key": "vendor.errors.not_found"},
        )
    return str(data["id"])


@router.get("", response_model=CouponListResponse)
def vendor_list_coupons(
    user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> CouponListResponse:
    require_flag(service, COUPONS_FLAG)
    return list_coupons(service, vendor_id=_vendor_id(service, user))


@router.post("", response_model=CouponOut, status_code=201)
def vendor_create_coupon(
    body: CouponCreateRequest,
    user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> CouponOut:
    require_flag(service, COUPONS_FLAG)
    vendor_id = _vendor_id(service, user)
    if body.scope == "listing" and body.scope_id:
        assert_vendor_owns_listing(service, vendor_id=vendor_id, listing_id=body.scope_id)
    row = build_coupon_row(
        body,
        funder="vendor",
        vendor_id=vendor_id,
        actor_id=user.id,
        max_percent_bps=vendor_max_percent_bps(service),
        today=datetime.now(LUSAKA).date(),
    )
    return insert_coupon(service, row, actor_id=user.id)


@router.patch("/{coupon_id}", response_model=CouponOut)
def vendor_set_coupon_status(
    coupon_id: str,
    body: CouponStatusRequest,
    user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> CouponOut:
    require_flag(service, COUPONS_FLAG)
    return set_coupon_status(
        service,
        coupon_id=coupon_id,
        status=body.status,
        actor_id=user.id,
        vendor_id=_vendor_id(service, user),
    )
