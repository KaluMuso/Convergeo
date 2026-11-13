"""Vendor-facing plan status (flag ``vendor_plans``).

Read-only. Powers the vendor app's plan card and the friendly upgrade prompt:
usage against the effective cap (min of KYC cap and plan cap), what binds, and
which plans would lift it. No billing — upgrading is a request to the team
until a Lenco subscription charge exists (see services/vendor_plans/billing.py).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.services.kyc.caps import _load_vendor_for_owner, load_vendor_cap_limits_by_id
from app.services.kyc.state_machine import ServiceRoleClient
from app.services.vendor_plans.resolver import (
    HARD_MAX_IMAGES_PER_LISTING,
    PlanFeatures,
    list_plans,
    vendor_plans_enabled,
)
from fastapi import APIRouter, Depends
from pydantic import BaseModel

router = APIRouter(prefix="/vendor/plan", tags=["vendor-plan"])

# vendor_quotas seeds T2/T3 at 9,999 listings, i.e. "caps lifted" (0008_config).
KYC_CAPS_LIFTED_AT = 9999


class PlanSummary(BaseModel):
    key: str
    name: str
    price_ngwee: int
    max_listings: int | None
    max_images_per_listing: int
    featured_slots: int
    analytics_depth: str
    wholesale_tools: bool


class VendorPlanStatus(BaseModel):
    enabled: bool
    plan: PlanSummary | None = None
    effective_max_listings: int | None = None
    max_images_per_listing: int = HARD_MAX_IMAGES_PER_LISTING
    listing_count: int = 0
    remaining_listings: int | None = None
    at_limit: bool = False
    over_limit: bool = False
    limited_by: Literal["plan", "kyc", "none"] = "none"
    override_expires_at: str | None = None
    upgrade_options: list[PlanSummary] = []


def plan_summary(plan: PlanFeatures) -> PlanSummary:
    return PlanSummary(
        key=plan.key,
        name=plan.name,
        price_ngwee=plan.price_ngwee,
        max_listings=plan.max_listings,
        max_images_per_listing=plan.max_images_per_listing,
        featured_slots=plan.featured_slots,
        analytics_depth=plan.analytics_depth,
        wholesale_tools=plan.wholesale_tools,
    )


def _lifts_cap(candidate: PlanFeatures, current_cap: int | None) -> bool:
    if current_cap is None:
        return False
    return candidate.max_listings is None or candidate.max_listings > current_cap


@router.get("", response_model=VendorPlanStatus)
async def get_vendor_plan(
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> VendorPlanStatus:
    client: Any = service_client.client
    if not vendor_plans_enabled(client):
        return VendorPlanStatus(enabled=False)

    vendor = _load_vendor_for_owner(service_client, current_user.id)
    limits = load_vendor_cap_limits_by_id(service_client, str(vendor["id"]), vendor_row=vendor)
    effective = limits.plan
    cap = limits.quota.max_listings
    count = limits.listing_count
    # KYC T2/T3 caps (9,999 in vendor_quotas) mean "caps lifted": when the KYC
    # cap binds at that level the vendor sees "unlimited", not a magic number.
    effective_cap: int | None = cap
    limited_by: Literal["plan", "kyc", "none"] = "kyc"
    if limits.limited_by_plan:
        limited_by = "plan"
    elif (limits.kyc_max_listings or 0) >= KYC_CAPS_LIFTED_AT:
        effective_cap = None
        limited_by = "none"

    upgrade_options: list[PlanSummary] = []
    if effective is not None and limited_by == "plan":
        upgrade_options = [
            plan_summary(candidate)
            for candidate in list_plans(client, active_only=True)
            if candidate.key != effective.plan.key and _lifts_cap(candidate, effective.max_listings)
        ]

    return VendorPlanStatus(
        enabled=True,
        plan=plan_summary(effective.plan) if effective is not None else None,
        effective_max_listings=effective_cap,
        max_images_per_listing=(
            effective.max_images_per_listing
            if effective is not None
            else HARD_MAX_IMAGES_PER_LISTING
        ),
        listing_count=count,
        remaining_listings=max(effective_cap - count, 0) if effective_cap is not None else None,
        at_limit=effective_cap is not None and count >= effective_cap,
        over_limit=effective_cap is not None and count > effective_cap,
        limited_by=limited_by,
        override_expires_at=effective.override_expires_at if effective is not None else None,
        upgrade_options=upgrade_options,
    )
