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
from app.services.vendor_plans.billing import annual_price_ngwee, in_trial
from app.services.vendor_plans.resolver import (
    HARD_MAX_IMAGES_PER_LISTING,
    PlanFeatures,
    list_plans,
    vendor_plans_enabled,
)
from app.services.vendor_plans.trial import load_annual_discount_pct, load_vendor_trial_end
from fastapi import APIRouter, Depends
from pydantic import BaseModel

router = APIRouter(prefix="/vendor/plan", tags=["vendor-plan"])

# vendor_quotas seeds T2/T3 at 9,999 listings, i.e. "caps lifted" (0008_config).
KYC_CAPS_LIFTED_AT = 9999


class PlanSummary(BaseModel):
    key: str
    name: str
    price_ngwee: int
    #: 12 x monthly less the annual prepay discount, integer ngwee rounded down.
    annual_price_ngwee: int = 0
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
    #: Plan picker: every active plan with its monthly and annual price.
    plans: list[PlanSummary] = []
    annual_discount_pct: int = 0
    trial_ends_at: str | None = None
    in_trial: bool = False


def plan_summary(plan: PlanFeatures, discount_pct: int = 0) -> PlanSummary:
    return PlanSummary(
        key=plan.key,
        name=plan.name,
        price_ngwee=plan.price_ngwee,
        annual_price_ngwee=annual_price_ngwee(plan.price_ngwee, discount_pct),
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
        # The free trial applies to every seller, plans flag or not.
        owner_vendor = _load_vendor_for_owner(service_client, current_user.id)
        off_trial_end = load_vendor_trial_end(client, str(owner_vendor["id"]))
        return VendorPlanStatus(
            enabled=False,
            trial_ends_at=off_trial_end.isoformat() if off_trial_end is not None else None,
            in_trial=in_trial(off_trial_end),
        )

    vendor = _load_vendor_for_owner(service_client, current_user.id)
    vendor_id = str(vendor["id"])
    limits = load_vendor_cap_limits_by_id(service_client, vendor_id, vendor_row=vendor)
    effective = limits.plan
    discount = load_annual_discount_pct(client)
    trial_end = load_vendor_trial_end(client, vendor_id)

    # Two caps: the plan limits ACTIVE (published) listings; the KYC trust cap
    # limits all listings including drafts. Show whichever binds first.
    limited_by: Literal["plan", "kyc", "none"]
    plan_cap = limits.plan_max_active
    kyc_cap = limits.kyc_max_listings
    if plan_cap is not None and (kyc_cap is None or plan_cap < kyc_cap):
        limited_by = "plan"
        effective_cap: int | None = plan_cap
        count = limits.active_listing_count
    elif (kyc_cap or 0) >= KYC_CAPS_LIFTED_AT:
        # vendor_quotas T2/T3 (9,999) mean "caps lifted": shown as unlimited.
        limited_by = "none"
        effective_cap = None
        count = limits.listing_count
    else:
        limited_by = "kyc"
        effective_cap = kyc_cap
        count = limits.listing_count

    active_plans = list_plans(client, active_only=True)
    upgrade_options: list[PlanSummary] = []
    if effective is not None and limited_by == "plan":
        upgrade_options = [
            plan_summary(candidate, discount)
            for candidate in active_plans
            if candidate.key != effective.plan.key and _lifts_cap(candidate, effective.max_listings)
        ]

    return VendorPlanStatus(
        enabled=True,
        plan=plan_summary(effective.plan, discount) if effective is not None else None,
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
        plans=[plan_summary(candidate, discount) for candidate in active_plans],
        annual_discount_pct=discount,
        trial_ends_at=trial_end.isoformat() if trial_end is not None else None,
        in_trial=in_trial(trial_end),
    )
