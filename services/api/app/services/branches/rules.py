"""Multi-branch rules shared by the vendor and admin routers.

The database (migration 20261115100000) is the authority for every limit:
shop allowance, unregistered single shop, sibling distance, payout ownership,
branch state machine. This module mirrors the arithmetic for friendly previews
(quotes, distance hints) and maps database refusals to stable API errors with
i18n message keys.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from typing import Any, Final

from app.errors import AppError
from app.services.vendor_plans.resolver import flag_enabled

logger = logging.getLogger(__name__)

MULTI_BRANCH_FLAG: Final = "multi_branch"
DEFAULT_MIN_SIBLING_DISTANCE_M: Final = 50
MIN_SIBLING_DISTANCE_BOUNDS: Final = (10, 5000)
EARTH_RADIUS_M: Final = 6_371_008.8
REGISTERED_TYPES: Final = frozenset({"company", "business_name"})
EVIDENCE_BUCKET: Final = "kyc-docs"  # private bucket; same RLS default-deny as KYC docs.

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def multi_branch_enabled(client: Any) -> bool:
    return flag_enabled(client, MULTI_BRANCH_FLAG)


def normalize_zm_msisdn(raw: str | None) -> str | None:
    """Same rule as SQL ``normalize_zm_msisdn``: 0977… / 977… / +260977… -> 260977…"""
    if raw is None:
        return None
    digits = "".join(char for char in raw if char.isdigit())
    if not digits:
        return None
    if len(digits) == 10 and digits.startswith("0"):
        digits = "260" + digits[1:]
    elif len(digits) == 9:
        digits = "260" + digits
    return digits


def is_zm_mobile(value: str | None) -> bool:
    return value is not None and re.fullmatch(r"260[79][5-7]\d{7}", value) is not None


def geo_distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Haversine, identical to SQL ``geo_distance_m``."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlng / 2) ** 2
    return EARTH_RADIUS_M * 2 * math.asin(math.sqrt(min(1.0, a)))


def slugify_branch(name: str) -> str:
    slug = _SLUG_STRIP.sub("-", name.lower()).strip("-")[:70].strip("-")
    return slug if len(slug) >= 2 else f"shop-{slug or 'branch'}"


@dataclass(frozen=True, slots=True)
class ShopAllowance:
    """How many shops a business may run and what the next one costs (ngwee)."""

    registered: bool
    plan_key: str | None
    included_shops: int | None
    extra_shop_price_ngwee: int | None
    used: int
    limit: int | None
    can_add: bool
    next_billing_role: str | None  # "included" | "addon" | None (cannot add)
    next_price_ngwee: int | None
    blocked_reason: str | None  # "unregistered" | "plan" | None


def shop_allowance(
    *, pacra_number: str | None, plan: dict[str, Any] | None, used: int
) -> ShopAllowance:
    """Python mirror of SQL ``business_shop_limit`` + ``create_vendor_branch`` pricing."""
    registered = bool(pacra_number)
    included = _int_or_none(plan.get("included_shops")) if plan else 1
    extra = _int_or_none(plan.get("extra_shop_price_ngwee")) if plan else None
    plan_key = str(plan["key"]) if plan and plan.get("key") else None
    if plan is not None and "included_shops" in plan and plan.get("included_shops") is None:
        included = None
    if not registered:
        limit: int | None = 1
    elif plan is None:
        limit = 1
    elif extra is not None or included is None:
        limit = None
    else:
        limit = included
    can_add = limit is None or used < limit
    role: str | None = None
    price: int | None = None
    if can_add:
        if included is None or used < included:
            role, price = "included", 0
        else:
            role, price = "addon", extra
    reason = None
    if not can_add:
        reason = "unregistered" if not registered else "plan"
    return ShopAllowance(
        registered=registered,
        plan_key=plan_key,
        included_shops=included,
        extra_shop_price_ngwee=extra,
        used=used,
        limit=limit,
        can_add=can_add,
        next_billing_role=role,
        next_price_ngwee=price,
        blocked_reason=reason,
    )


def _int_or_none(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def min_sibling_distance_m(client: Any) -> int:
    try:
        rows = (
            client.table("platform_config")
            .select("value")
            .eq("key", "branch_min_sibling_distance_m")
            .execute()
            .data
        )
    except Exception:
        logger.warning("branch distance config read failed; using default")
        return DEFAULT_MIN_SIBLING_DISTANCE_M
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        value = _int_or_none(rows[0].get("value"))
        if value is not None:
            return value
    return DEFAULT_MIN_SIBLING_DISTANCE_M


# ---------------------------------------------------------------------------
# Database refusal -> API error
# ---------------------------------------------------------------------------
_DB_ERRORS: Final[dict[str, tuple[int, str, str]]] = {
    "multi_branch_disabled": (404, "feature_disabled", "vendor.branches.errors.disabled"),
    "business_not_found": (404, "not_found", "vendor.branches.errors.businessNotFound"),
    "business_suspended": (409, "conflict", "vendor.branches.errors.businessSuspended"),
    "branch_owner_kyc_required": (409, "conflict", "vendor.branches.errors.ownerKycRequired"),
    "branch_location_required": (
        422,
        "validation_error",
        "vendor.branches.errors.locationRequired",
    ),
    "branch_slug_invalid": (422, "validation_error", "vendor.branches.errors.slugInvalid"),
    "branch_limit_unregistered": (409, "conflict", "vendor.branches.errors.unregisteredLimit"),
    "branch_limit_plan": (409, "conflict", "vendor.branches.errors.planLimit"),
    "branch_too_close_to_sibling": (422, "validation_error", "vendor.branches.errors.tooClose"),
    "payout_msisdn_other_owner": (409, "conflict", "vendor.branches.errors.payoutTaken"),
    "branch_evidence_required": (409, "conflict", "vendor.branches.errors.evidenceRequired"),
    "branch_invalid_transition": (409, "conflict", "vendor.branches.errors.invalidTransition"),
    "branch_note_required": (422, "validation_error", "admin.branches.errors.noteRequired"),
    "branch_open_flags": (409, "conflict", "admin.branches.errors.openFlags"),
    "branch_primary_not_reviewable": (409, "conflict", "admin.branches.errors.primary"),
    "branch_not_found": (404, "not_found", "vendor.branches.errors.branchNotFound"),
    "staff_seat_limit": (409, "conflict", "vendor.branches.errors.staffSeatLimit"),
    "vendor_businesses_pacra_number_key": (409, "conflict", "vendor.branches.errors.pacraTaken"),
    "vendor_business_staff_msisdn_key": (409, "conflict", "vendor.branches.errors.staffDuplicate"),
}


def map_db_error(exc: Exception) -> AppError | None:
    """Translate a known database refusal into an AppError; ``None`` if unknown."""
    text = str(getattr(exc, "message", None) or exc)
    details_raw = str(getattr(exc, "details", None) or "")
    for token, (status, code, key) in _DB_ERRORS.items():
        if token in text or token in details_raw:
            details: dict[str, Any] = {"message_key": key, "reason": token}
            if token == "branch_too_close_to_sibling" and details_raw:
                details["detail"] = details_raw
            return AppError(code=code, message=token, http_status=status, details=details)
    return None


def raise_mapped(exc: Exception) -> None:
    mapped = map_db_error(exc)
    if mapped is not None:
        raise mapped from exc
    raise exc
