"""Admin: platform-funded coupons (flag ``coupons``). Admin / superadmin only."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.services.coupons.manage import (
    CouponCreateRequest,
    CouponListResponse,
    CouponOut,
    CouponStatusRequest,
    build_coupon_row,
    insert_coupon,
    list_coupons,
    set_coupon_status,
)
from app.services.coupons.rules import LUSAKA
from app.services.coupons.store import COUPONS_FLAG, ServiceRoleClient, require_flag
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/admin/coupons", tags=["admin-coupons"])


@router.get("", response_model=CouponListResponse)
def admin_list_coupons(
    _user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> CouponListResponse:
    return list_coupons(service, vendor_id=None)


@router.post("", response_model=CouponOut, status_code=201)
def admin_create_coupon(
    body: CouponCreateRequest,
    user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> CouponOut:
    require_flag(service, COUPONS_FLAG)
    row = build_coupon_row(
        body,
        funder="platform",
        vendor_id=None,
        actor_id=user.id,
        today=datetime.now(LUSAKA).date(),
    )
    return insert_coupon(service, row, actor_id=user.id)


@router.patch("/{coupon_id}", response_model=CouponOut)
def admin_set_coupon_status(
    coupon_id: str,
    body: CouponStatusRequest,
    user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> CouponOut:
    return set_coupon_status(
        service, coupon_id=coupon_id, status=body.status, actor_id=user.id, vendor_id=None
    )
