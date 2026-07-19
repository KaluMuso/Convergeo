from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any, cast

from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.errors import AppError
from app.services.kyc.badge import payout_velocity_window_start
from app.services.kyc.eligibility import cap_tier_for_quotas, resolve_vendor_eligibility
from app.services.kyc.state_machine import ServiceRoleClient
from fastapi import Depends

ServiceClient = Any

LISTING_COUNT_STATUSES = frozenset({"draft", "active", "paused"})
ORDER_COUNT_STATUSES = frozenset(
    {
        "placed",
        "confirmed",
        "processing",
        "ready",
        "shipped",
        "delivered",
        "completed",
    }
)

_CONFIG_CACHE_TTL_SECONDS = 60.0
_quota_cache: dict[int, tuple[float, VendorQuota]] = {}
_cod_cap_cache: tuple[float, int] | None = None
_cache_lock = threading.Lock()


@dataclass(frozen=True, slots=True)
class VendorQuota:
    tier: int
    max_listings: int
    first_orders_cap_ngwee: int | None
    first_orders_count: int | None
    payout_velocity: dict[str, Any]


@dataclass(frozen=True, slots=True)
class VendorCapLimits:
    vendor_id: str
    kyc_tier: int
    quota: VendorQuota
    cod_cap_ngwee: int
    listing_count: int
    order_count: int


@dataclass(slots=True)
class OrderCapChecker:
    limits: VendorCapLimits

    def ensure_can_accept(self, order_total_ngwee: int) -> None:
        enforce_first_order_cap(self.limits, order_total_ngwee)


@dataclass(slots=True)
class PayoutVelocityChecker:
    limits: VendorCapLimits
    service_client: ServiceRoleClient

    def ensure_can_payout(self, amount_ngwee: int) -> None:
        enforce_payout_velocity(self.limits, amount_ngwee, self.service_client)


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [cast(dict[str, Any], row) for row in data if isinstance(row, dict)]
    return []


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return cast(dict[str, Any], data)
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            return cast(dict[str, Any], first)
    return None


def _parse_int(value: Any, default: int | None = None) -> int | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _parse_config_int(client: ServiceClient, key: str, default: int) -> int:
    global _cod_cap_cache
    now = datetime.now(UTC).timestamp()
    if key == "cod_cap_ngwee":
        with _cache_lock:
            if _cod_cap_cache is not None and _cod_cap_cache[0] > now:
                return _cod_cap_cache[1]

    response = (
        client.table("platform_config").select("value").eq("key", key).maybe_single().execute()
    )
    row = _single_row(response)
    # `_parse_int` already substitutes `default` for a missing/invalid value, so a
    # returned 0 is an intentional config (e.g. cod_cap_ngwee = 0 disables COD).
    # A trailing `or default` here would silently re-enable it — do not add one.
    parsed = _parse_int(row.get("value") if row else None, default)
    if parsed is None:
        parsed = default

    if key == "cod_cap_ngwee":
        with _cache_lock:
            _cod_cap_cache = (now + _CONFIG_CACHE_TTL_SECONDS, parsed)
    return parsed


def load_vendor_quota(service_client: ServiceRoleClient, tier: int) -> VendorQuota:
    now = datetime.now(UTC).timestamp()
    with _cache_lock:
        cached = _quota_cache.get(tier)
        if cached is not None and cached[0] > now:
            return cached[1]

    response = (
        service_client.client.table("vendor_quotas")
        .select("tier, max_listings, first_orders_cap_ngwee, first_orders_count, payout_velocity")
        .eq("tier", tier)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(
            code="configuration_error",
            message=f"Vendor quota missing for tier {tier}",
            http_status=500,
        )

    payout_velocity = row.get("payout_velocity")
    velocity = cast(dict[str, Any], payout_velocity) if isinstance(payout_velocity, dict) else {}
    quota = VendorQuota(
        tier=int(row["tier"]),
        max_listings=int(row["max_listings"]),
        first_orders_cap_ngwee=_parse_int(row.get("first_orders_cap_ngwee")),
        first_orders_count=_parse_int(row.get("first_orders_count")),
        payout_velocity=velocity,
    )
    with _cache_lock:
        _quota_cache[tier] = (now + _CONFIG_CACHE_TTL_SECONDS, quota)
    return quota


def clear_vendor_cap_cache() -> None:
    global _cod_cap_cache
    with _cache_lock:
        _quota_cache.clear()
        _cod_cap_cache = None


def _count_vendor_listings(service_client: ServiceRoleClient, vendor_id: str) -> int:
    client: ServiceClient = service_client.client
    response = (
        client.table("vendor_listings")
        .select("id", count="exact")
        .eq("vendor_id", vendor_id)
        .in_("status", list(LISTING_COUNT_STATUSES))
        .execute()
    )
    count = getattr(response, "count", None)
    if isinstance(count, int):
        return count
    return len(_rows(response))


def _count_vendor_orders(service_client: ServiceRoleClient, vendor_id: str) -> int:
    client: ServiceClient = service_client.client
    response = (
        client.table("orders")
        .select("id", count="exact")
        .eq("vendor_id", vendor_id)
        .in_("status", list(ORDER_COUNT_STATUSES))
        .execute()
    )
    count = getattr(response, "count", None)
    if isinstance(count, int):
        return count
    return len(_rows(response))


def _load_vendor_for_owner(
    service_client: ServiceRoleClient,
    owner_user_id: str,
) -> dict[str, Any]:
    response = (
        service_client.client.table("vendors")
        .select("id, owner_user_id, status, kyc_tier")
        .eq("owner_user_id", owner_user_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(
            code="forbidden",
            message="Authenticated user does not own a vendor profile",
            http_status=403,
            details={"message_key": "vendor.errors.not_found"},
        )
    return row


def load_vendor_cap_limits_by_id(
    service_client: ServiceRoleClient,
    vendor_id: str,
    *,
    vendor_row: dict[str, Any] | None = None,
) -> VendorCapLimits:
    """Load full vendor KYC quota limits (listings, first-order, COD, order_count).

    Used at order creation (customer path) and vendor-owned dependency paths.
    Tier is auditable-approval derived — orphaned ``vendors.kyc_tier`` stays T1.
    """
    row = vendor_row
    if row is None:
        response = (
            service_client.client.table("vendors")
            .select("id, owner_user_id, status, kyc_tier")
            .eq("id", vendor_id)
            .maybe_single()
            .execute()
        )
        row = _single_row(response)
    if row is None:
        raise AppError(
            code="vendor_not_found",
            message=f"Vendor {vendor_id} not found",
            http_status=404,
        )
    eligibility = resolve_vendor_eligibility(
        service_client,
        vendor_id,
        vendor_row=row,
    )
    # Orphaned bare kyc_tier must not unlock T2/T3 quota lifts (MR-D02).
    tier = cap_tier_for_quotas(eligibility)
    quota = load_vendor_quota(service_client, tier)
    cod_cap = _parse_config_int(service_client.client, "cod_cap_ngwee", 50_000)
    listing_count = _count_vendor_listings(service_client, vendor_id)
    order_count = _count_vendor_orders(service_client, vendor_id)
    return VendorCapLimits(
        vendor_id=vendor_id,
        kyc_tier=tier,
        quota=quota,
        cod_cap_ngwee=cod_cap,
        listing_count=listing_count,
        order_count=order_count,
    )


def enforce_first_order_caps_for_vendors(
    service_client: ServiceRoleClient,
    vendor_totals_ngwee: dict[str, int],
) -> None:
    """D9 T1: first N orders each ≤ cap — enforced per vendor for all payment methods."""
    for vendor_id, order_total_ngwee in vendor_totals_ngwee.items():
        limits = load_vendor_cap_limits_by_id(service_client, vendor_id)
        OrderCapChecker(limits=limits).ensure_can_accept(order_total_ngwee)


async def get_vendor_cap_limits(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> VendorCapLimits:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    return load_vendor_cap_limits_by_id(
        service_client,
        str(vendor["id"]),
        vendor_row=vendor,
    )


def _raise_cap_error(
    *,
    code: str,
    message_key: str,
    details: dict[str, Any] | None = None,
) -> None:
    payload = {"message_key": message_key}
    if details:
        payload.update(details)
    raise AppError(
        code=code,
        message="Vendor cap enforcement blocked this action",
        http_status=403,
        details=payload,
    )


def enforce_listing_cap(limits: VendorCapLimits) -> None:
    if limits.listing_count >= limits.quota.max_listings:
        _raise_cap_error(
            code="listing_cap_exceeded",
            message_key="vendor.caps.listing_limit",
            details={
                "max_listings": limits.quota.max_listings,
                "current_listings": limits.listing_count,
                "kyc_tier": limits.kyc_tier,
            },
        )


def enforce_first_order_cap(limits: VendorCapLimits, order_total_ngwee: int) -> None:
    first_orders_count = limits.quota.first_orders_count
    first_orders_cap = limits.quota.first_orders_cap_ngwee
    if first_orders_count is None or first_orders_cap is None:
        return

    if limits.order_count >= first_orders_count:
        return

    cap_ngwee = min(first_orders_cap, limits.cod_cap_ngwee)
    if order_total_ngwee > cap_ngwee:
        _raise_cap_error(
            code="first_order_cap_exceeded",
            message_key="vendor.caps.first_order_amount",
            details={
                "cap_ngwee": cap_ngwee,
                "order_total_ngwee": order_total_ngwee,
                "orders_so_far": limits.order_count,
                "first_orders_count": first_orders_count,
                "kyc_tier": limits.kyc_tier,
            },
        )


def enforce_payout_velocity(
    limits: VendorCapLimits,
    amount_ngwee: int,
    service_client: ServiceRoleClient,
) -> None:
    velocity = limits.quota.payout_velocity
    max_payouts = _parse_int(velocity.get("max_payouts_per_day"))
    max_amount = _parse_int(velocity.get("max_amount_ngwee_per_day"))
    if max_payouts is None and max_amount is None:
        return

    since = payout_velocity_window_start()
    client: ServiceClient = service_client.client
    response = (
        client.table("payouts")
        .select("amount_ngwee", count="exact")
        .eq("vendor_id", limits.vendor_id)
        .gte("created_at", since)
        .in_("status", ["pending", "processing", "paid"])
        .execute()
    )
    payouts = _rows(response)
    payout_count = getattr(response, "count", None)
    if not isinstance(payout_count, int):
        payout_count = len(payouts)

    amount_total = sum(int(row.get("amount_ngwee", 0)) for row in payouts)

    if max_payouts is not None and payout_count >= max_payouts:
        _raise_cap_error(
            code="payout_velocity_exceeded",
            message_key="vendor.caps.payout_velocity",
            details={
                "max_payouts_per_day": max_payouts,
                "payouts_today": payout_count,
            },
        )

    if max_amount is not None and amount_total + amount_ngwee > max_amount:
        _raise_cap_error(
            code="payout_velocity_exceeded",
            message_key="vendor.caps.payout_velocity",
            details={
                "max_amount_ngwee_per_day": max_amount,
                "amount_requested_ngwee": amount_ngwee,
                "amount_used_ngwee": amount_total,
            },
        )


async def require_listing_cap(
    limits: Annotated[VendorCapLimits, Depends(get_vendor_cap_limits)],
) -> VendorCapLimits:
    enforce_listing_cap(limits)
    return limits


async def get_order_cap_checker(
    limits: Annotated[VendorCapLimits, Depends(get_vendor_cap_limits)],
) -> OrderCapChecker:
    return OrderCapChecker(limits=limits)


async def get_payout_velocity_checker(
    limits: Annotated[VendorCapLimits, Depends(get_vendor_cap_limits)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> PayoutVelocityChecker:
    return PayoutVelocityChecker(limits=limits, service_client=service_client)
