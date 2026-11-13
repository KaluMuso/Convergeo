"""Coupon persistence helpers — flag gates, lookups, SQL error mapping."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from datetime import datetime
from typing import Any, Final, Protocol

from app.errors import AppError
from app.services.coupons.rules import CouponError, CouponRule, DiscountLine

logger = logging.getLogger(__name__)

COUPONS_FLAG: Final = "coupons"
GIFT_ORDERS_FLAG: Final = "gift_orders"
BIRTHDAY_FLAG: Final = "birthday_greetings"

COUPON_COLUMNS = (
    "id, code, title, kind, percent_bps, amount_ngwee, max_discount_ngwee, funder, vendor_id, "
    "scope, scope_vendor_id, scope_category_id, scope_listing_id, min_spend_ngwee, starts_at, "
    "ends_at, total_limit, per_user_limit, uses_count, personal_user_id, source, status, "
    "created_at"
)

_CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9-]{2,31}$")
_SQL_MARKER_RE = re.compile(r"COUPON_(INVALID|LIMIT|BUDGET):([a-z_]+)")

#: Customer-facing 409 codes for the SQL reservation markers.
_MARKER_CODES: Final = {
    ("LIMIT", "total"): "coupon.limit_reached",
    ("LIMIT", "user"): "coupon.already_used",
    ("BUDGET", "exhausted"): "coupon.budget_exhausted",
}


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


def flag_enabled(service_client: ServiceRoleClient, flag: str) -> bool:
    """Fail closed: a missing row or read error means OFF."""
    try:
        response = (
            service_client.client.table("feature_flags")
            .select("enabled")
            .eq("flag", flag)
            .maybe_single()
            .execute()
        )
    except Exception:
        logger.warning("feature flag read failed; treating as disabled")
        return False
    data = getattr(response, "data", None)
    if isinstance(data, list):
        data = data[0] if data else None
    return isinstance(data, dict) and bool(data.get("enabled", False))


def require_flag(service_client: ServiceRoleClient, flag: str) -> None:
    if not flag_enabled(service_client, flag):
        raise AppError(
            code="feature_disabled",
            message="This feature is not available yet",
            http_status=404,
            details={"flag": flag, "message_key": "common.featureUnavailable"},
        )


def normalize_code(raw: str) -> str:
    code = re.sub(r"\s+", "", raw or "").upper()
    if not _CODE_RE.match(code):
        raise CouponError("coupon.not_found")
    return code


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _opt_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _opt_str(value: Any) -> str | None:
    return str(value) if isinstance(value, str) and value else None


def rule_from_row(row: dict[str, Any]) -> CouponRule:
    starts = _parse_ts(row.get("starts_at"))
    if starts is None:
        raise CouponError("coupon.inactive")
    return CouponRule(
        id=str(row["id"]),
        code=str(row["code"]),
        kind="percent" if row.get("kind") == "percent" else "fixed",
        funder="vendor" if row.get("funder") == "vendor" else "platform",
        scope=row.get("scope") or "all",
        starts_at=starts,
        status=str(row.get("status") or "paused"),
        percent_bps=_opt_int(row.get("percent_bps")),
        amount_ngwee=_opt_int(row.get("amount_ngwee")),
        max_discount_ngwee=_opt_int(row.get("max_discount_ngwee")),
        vendor_id=_opt_str(row.get("vendor_id")),
        scope_vendor_id=_opt_str(row.get("scope_vendor_id")),
        scope_category_id=_opt_str(row.get("scope_category_id")),
        scope_listing_id=_opt_str(row.get("scope_listing_id")),
        min_spend_ngwee=_opt_int(row.get("min_spend_ngwee")) or 0,
        ends_at=_parse_ts(row.get("ends_at")),
        personal_user_id=_opt_str(row.get("personal_user_id")),
        total_limit=_opt_int(row.get("total_limit")),
        per_user_limit=_opt_int(row.get("per_user_limit")) or 1,
        uses_count=_opt_int(row.get("uses_count")) or 0,
    )


def _single(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        data = data[0] if data else None
    return data if isinstance(data, dict) else None


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def load_coupon_by_code(service_client: ServiceRoleClient, code: str) -> CouponRule:
    response = (
        service_client.client.table("coupons")
        .select(COUPON_COLUMNS)
        .eq("code", code)
        .maybe_single()
        .execute()
    )
    row = _single(response)
    if row is None:
        raise CouponError("coupon.not_found")
    return rule_from_row(row)


def load_coupon_by_id(service_client: ServiceRoleClient, coupon_id: str) -> CouponRule:
    response = (
        service_client.client.table("coupons")
        .select(COUPON_COLUMNS)
        .eq("id", coupon_id)
        .maybe_single()
        .execute()
    )
    row = _single(response)
    if row is None:
        raise CouponError("coupon.not_found")
    return rule_from_row(row)


def count_active_uses(
    service_client: ServiceRoleClient, *, coupon_id: str, user_id: str
) -> tuple[int, int]:
    """(total, by this user) reserved+applied uses — advisory pre-check only.

    The authoritative check runs under the coupon row lock at order creation.
    """
    response = (
        service_client.client.table("coupon_redemptions")
        .select("user_id")
        .eq("coupon_id", coupon_id)
        .in_("status", ["reserved", "applied"])
        .execute()
    )
    rows = _rows(response)
    return len(rows), sum(1 for row in rows if str(row.get("user_id")) == user_id)


def precheck_limits(service_client: ServiceRoleClient, rule: CouponRule, *, user_id: str) -> None:
    total, mine = count_active_uses(service_client, coupon_id=rule.id, user_id=user_id)
    if mine >= rule.per_user_limit:
        raise CouponError("coupon.already_used")
    if rule.total_limit is not None and total >= rule.total_limit:
        raise CouponError("coupon.limit_reached")


def load_category_ancestry(
    service_client: ServiceRoleClient, listing_ids: Iterable[str]
) -> dict[str, frozenset[str]]:
    """listing_id → {product category, its parent, grandparent} (best effort)."""
    ids = sorted(set(listing_ids))
    if not ids:
        return {}
    listings = _rows(
        service_client.client.table("vendor_listings")
        .select("id, product_id")
        .in_("id", ids)
        .execute()
    )
    product_by_listing = {
        str(row["id"]): str(row["product_id"]) for row in listings if row.get("product_id")
    }
    products = (
        _rows(
            service_client.client.table("products")
            .select("id, category_id")
            .in_("id", sorted(set(product_by_listing.values())))
            .execute()
        )
        if product_by_listing
        else []
    )
    category_by_product = {
        str(row["id"]): str(row["category_id"]) for row in products if row.get("category_id")
    }
    categories = _rows(service_client.client.table("categories").select("id, parent_id").execute())
    parent = {
        str(row["id"]): (str(row["parent_id"]) if row.get("parent_id") else None)
        for row in categories
    }
    result: dict[str, frozenset[str]] = {}
    for listing_id in ids:
        chain: list[str] = []
        current = category_by_product.get(product_by_listing.get(listing_id, ""))
        while current and current not in chain and len(chain) < 6:
            chain.append(current)
            current = parent.get(current)
        result[listing_id] = frozenset(chain)
    return result


def build_discount_lines(
    service_client: ServiceRoleClient,
    lines: Iterable[tuple[str, str, int]],
    *,
    needs_categories: bool,
) -> list[DiscountLine]:
    """(listing_id, vendor_id, line_total_ngwee) → DiscountLine (categories on demand)."""
    materialized = list(lines)
    ancestry = (
        load_category_ancestry(service_client, (line[0] for line in materialized))
        if needs_categories
        else {}
    )
    return [
        DiscountLine(
            listing_id=listing_id,
            vendor_id=vendor_id,
            line_total_ngwee=line_total,
            category_ids=ancestry.get(listing_id, frozenset()),
        )
        for listing_id, vendor_id, line_total in materialized
    ]


def coupon_app_error(exc: CouponError) -> AppError:
    status = 404 if exc.code == "coupon.not_found" else 409
    return AppError(
        code=exc.code,
        message="This coupon cannot be used",
        http_status=status,
        details={
            "message_key": f"checkout.coupon.errors.{exc.code.split('.', 1)[1]}",
            **exc.details,
        },
    )


def map_reservation_error(error: str) -> AppError | None:
    """Translate a ``reserve_coupon_redemption`` marker into a customer 409."""
    match = _SQL_MARKER_RE.search(error or "")
    if match is None:
        return None
    family, reason = match.group(1), match.group(2)
    code = _MARKER_CODES.get((family, reason))
    if code is None:
        code = {
            "inactive": "coupon.inactive",
            "expired": "coupon.expired",
            "not_started": "coupon.not_started",
        }.get(reason, "coupon.changed")
    return coupon_app_error(CouponError(code))
