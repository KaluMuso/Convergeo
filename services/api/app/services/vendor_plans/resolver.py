"""Effective vendor plan resolution (flag ``vendor_plans``, default off).

One rule, mirrored by the SQL function ``public.vendor_plan_listing_cap``
(migration 20261114030000) which the listing admission trigger uses:

1. Flag off (or unreadable) -> no plan applies; behaviour is exactly pre-plans.
2. A non-expired override wins for the fields it sets (``unlimited_listings``,
   ``max_listings``, ``max_images_per_listing``).
3. Otherwise the vendor's assigned plan; otherwise the default plan.

The plan cap never replaces the KYC trust cap — callers take
``min(kyc_cap, plan cap)``. ``max_listings is None`` means unlimited.
Stock quantity is never an input: limits count distinct listings only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

logger = logging.getLogger(__name__)

VENDOR_PLANS_FLAG: Final = "vendor_plans"
SHARED_CANONICAL_PHOTOS_FLAG: Final = "shared_canonical_photos"
HARD_MAX_IMAGES_PER_LISTING: Final = 8

PLAN_COLUMNS: Final = (
    "key, name, price_ngwee, max_listings, max_images_per_listing, featured_slots, "
    "analytics_depth, wholesale_tools, is_default, active, position"
)
OVERRIDE_COLUMNS: Final = (
    "id, vendor_id, max_listings, unlimited_listings, max_images_per_listing, "
    "expires_at, reason, created_by, created_at, updated_at"
)
ASSIGNMENT_COLUMNS: Final = (
    "id, vendor_id, plan_key, source, billing_status, paid_through, billing_reference, "
    "note, assigned_by, assigned_at"
)


@dataclass(frozen=True, slots=True)
class PlanFeatures:
    key: str
    name: str
    price_ngwee: int
    max_listings: int | None
    max_images_per_listing: int
    featured_slots: int
    analytics_depth: str
    wholesale_tools: bool
    is_default: bool
    active: bool
    position: int


@dataclass(frozen=True, slots=True)
class EffectivePlan:
    plan: PlanFeatures
    max_listings: int | None
    max_images_per_listing: int
    override_active: bool
    override_expires_at: str | None


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def flag_enabled(client: Any, flag: str) -> bool:
    """Fail closed: a missing row or any read error means disabled."""
    try:
        response = client.table("feature_flags").select("enabled").eq("flag", flag).execute()
    except Exception:
        logger.warning("feature flag read failed; treating as disabled", extra={"flag": flag})
        return False
    rows = _rows(response)
    return bool(rows) and rows[0].get("enabled") is True


def vendor_plans_enabled(client: Any) -> bool:
    return flag_enabled(client, VENDOR_PLANS_FLAG)


def shared_photos_enabled(client: Any) -> bool:
    return flag_enabled(client, SHARED_CANONICAL_PHOTOS_FLAG)


def _int_or_none(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def plan_from_row(row: dict[str, Any]) -> PlanFeatures:
    images = _int_or_none(row.get("max_images_per_listing")) or HARD_MAX_IMAGES_PER_LISTING
    return PlanFeatures(
        key=str(row["key"]),
        name=str(row.get("name") or row["key"]),
        price_ngwee=_int_or_none(row.get("price_ngwee")) or 0,
        max_listings=_int_or_none(row.get("max_listings")),
        max_images_per_listing=max(1, min(images, HARD_MAX_IMAGES_PER_LISTING)),
        featured_slots=_int_or_none(row.get("featured_slots")) or 0,
        analytics_depth=str(row.get("analytics_depth") or "basic"),
        wholesale_tools=row.get("wholesale_tools") is True,
        is_default=row.get("is_default") is True,
        active=row.get("active") is not False,
        position=_int_or_none(row.get("position")) or 0,
    )


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def override_is_live(row: dict[str, Any] | None, *, now: datetime | None = None) -> bool:
    if row is None:
        return False
    expires = _parse_ts(row.get("expires_at"))
    return expires is not None and expires > (now or datetime.now(UTC))


def list_plans(client: Any, *, active_only: bool = False) -> list[PlanFeatures]:
    query = client.table("vendor_plans").select(PLAN_COLUMNS)
    if active_only:
        query = query.eq("active", True)
    rows = _rows(query.order("position").execute())
    return [plan_from_row(row) for row in rows if row.get("key")]


def load_assignment(client: Any, vendor_id: str) -> dict[str, Any] | None:
    rows = _rows(
        client.table("vendor_plan_assignments")
        .select(ASSIGNMENT_COLUMNS)
        .eq("vendor_id", vendor_id)
        .execute()
    )
    return rows[0] if rows else None


def load_override(client: Any, vendor_id: str) -> dict[str, Any] | None:
    rows = _rows(
        client.table("vendor_plan_overrides")
        .select(OVERRIDE_COLUMNS)
        .eq("vendor_id", vendor_id)
        .execute()
    )
    return rows[0] if rows else None


def compose_effective_plan(
    plan: PlanFeatures,
    override: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> EffectivePlan:
    """Pure: apply a (possibly expired) override on top of a plan."""
    max_listings = plan.max_listings
    max_images = plan.max_images_per_listing
    live = override_is_live(override, now=now)
    if live and override is not None:
        if override.get("unlimited_listings") is True:
            max_listings = None
        else:
            override_listings = _int_or_none(override.get("max_listings"))
            if override_listings is not None:
                max_listings = override_listings
        override_images = _int_or_none(override.get("max_images_per_listing"))
        if override_images is not None:
            max_images = max(1, min(override_images, HARD_MAX_IMAGES_PER_LISTING))
    return EffectivePlan(
        plan=plan,
        max_listings=max_listings,
        max_images_per_listing=max_images,
        override_active=live,
        override_expires_at=str(override["expires_at"]) if live and override else None,
    )


def resolve_plan_for_vendor(client: Any, vendor_id: str) -> EffectivePlan | None:
    """Resolve ignoring the flag (admin views). ``None`` if no plan can be found."""
    plans = {plan.key: plan for plan in list_plans(client)}
    assignment = load_assignment(client, vendor_id)
    plan: PlanFeatures | None = None
    if assignment is not None:
        plan = plans.get(str(assignment.get("plan_key")))
    if plan is None:
        plan = next((candidate for candidate in plans.values() if candidate.is_default), None)
    if plan is None:
        return None
    return compose_effective_plan(plan, load_override(client, vendor_id))


def resolve_effective_plan(client: Any, vendor_id: str) -> EffectivePlan | None:
    """Plan that applies right now, or ``None`` when ``vendor_plans`` is off.

    Never raises: a plan read failure must not block listing writes that the
    KYC cap (and the DB trigger, which re-checks atomically) still governs.
    """
    if not vendor_plans_enabled(client):
        return None
    try:
        return resolve_plan_for_vendor(client, vendor_id)
    except Exception:
        logger.warning("vendor plan resolution failed; KYC cap only", exc_info=True)
        return None
