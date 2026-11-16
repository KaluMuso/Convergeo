"""Coupon rules — pure, integer-ngwee discount math (no I/O).

* A coupon discounts ITEMS only; the delivery fee is never reduced.
* Percent discounts round DOWN to a whole ngwee, then cap at ``max_discount_ngwee``.
* Fixed discounts never exceed the eligible subtotal.
* The discount is spread across eligible lines with the largest-remainder
  method, so the per-line (and therefore per-shop) parts sum exactly to the
  total and no line is ever discounted below zero.
* Refund shares are proportional to the refunded item value and capped by what
  is still outstanding, so a fully returned order hands back the exact discount.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

LUSAKA = ZoneInfo("Africa/Lusaka")
#: The amount a checkout must still cost after a coupon (Lenco rejects K0 charges).
MIN_PAYABLE_NGWEE = 100

Funder = Literal["platform", "vendor"]
Scope = Literal["all", "vendor", "category", "listing"]
CouponKind = Literal["percent", "fixed"]


class CouponError(Exception):
    """A coupon cannot be used; ``code`` is a stable ``coupon.*`` error code."""

    def __init__(self, code: str, **details: int | str) -> None:
        super().__init__(code)
        self.code = code
        self.details = details


@dataclass(frozen=True, slots=True)
class CouponRule:
    id: str
    code: str
    kind: CouponKind
    funder: Funder
    scope: Scope
    starts_at: datetime
    status: str = "active"
    percent_bps: int | None = None
    amount_ngwee: int | None = None
    max_discount_ngwee: int | None = None
    vendor_id: str | None = None
    scope_vendor_id: str | None = None
    scope_category_id: str | None = None
    scope_listing_id: str | None = None
    min_spend_ngwee: int = 0
    ends_at: datetime | None = None
    personal_user_id: str | None = None
    total_limit: int | None = None
    per_user_limit: int = 1
    uses_count: int = 0


@dataclass(frozen=True, slots=True)
class DiscountLine:
    listing_id: str
    vendor_id: str
    line_total_ngwee: int
    #: The product's category and its ancestors (nearest first).
    category_ids: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class CouponQuote:
    coupon_id: str
    code: str
    funder: Funder
    discount_ngwee: int
    eligible_subtotal_ngwee: int
    line_discounts: Mapping[str, int]
    vendor_discounts: Mapping[str, int]


def line_is_eligible(rule: CouponRule, line: DiscountLine) -> bool:
    # A vendor-funded coupon only ever touches that vendor's own items.
    if rule.funder == "vendor" and line.vendor_id != rule.vendor_id:
        return False
    if rule.scope == "all":
        return True
    if rule.scope == "vendor":
        return line.vendor_id == rule.scope_vendor_id
    if rule.scope == "listing":
        return line.listing_id == rule.scope_listing_id
    return rule.scope_category_id is not None and rule.scope_category_id in line.category_ids


def check_window(rule: CouponRule, *, now: datetime, user_id: str) -> None:
    if rule.personal_user_id is not None and rule.personal_user_id != user_id:
        # Never reveal that someone else's personal code exists.
        raise CouponError("coupon.not_found")
    if rule.status != "active":
        raise CouponError("coupon.inactive")
    if now < rule.starts_at:
        raise CouponError("coupon.not_started")
    if rule.ends_at is not None and now >= rule.ends_at:
        raise CouponError("coupon.expired")


def raw_discount_ngwee(rule: CouponRule, eligible_subtotal_ngwee: int) -> int:
    if eligible_subtotal_ngwee <= 0:
        return 0
    if rule.kind == "percent":
        bps = rule.percent_bps or 0
        discount = (eligible_subtotal_ngwee * bps) // 10_000
    else:
        discount = rule.amount_ngwee or 0
    if rule.max_discount_ngwee is not None:
        discount = min(discount, rule.max_discount_ngwee)
    return max(0, min(discount, eligible_subtotal_ngwee))


def allocate_proportionally(total_ngwee: int, weights: Mapping[str, int]) -> dict[str, int]:
    """Split ``total`` over ``weights`` (largest remainder; exact; never > weight)."""
    keys = sorted(key for key, weight in weights.items() if weight > 0)
    weight_sum = sum(weights[key] for key in keys)
    if total_ngwee <= 0 or weight_sum <= 0:
        return {key: 0 for key in weights}
    if total_ngwee > weight_sum:
        msg = "cannot allocate more than the weights allow"
        raise ValueError(msg)
    shares: dict[str, int] = {}
    remainders: list[tuple[int, str]] = []
    for key in keys:
        numerator = total_ngwee * weights[key]
        shares[key] = numerator // weight_sum
        remainders.append((numerator % weight_sum, key))
    leftover = total_ngwee - sum(shares.values())
    # Largest fractional part first; ties broken by key for determinism.
    for _, key in sorted(remainders, key=lambda item: (-item[0], item[1]))[:leftover]:
        shares[key] += 1
    for key in weights:
        shares.setdefault(key, 0)
    return shares


def quote_coupon(
    rule: CouponRule,
    lines: Iterable[DiscountLine],
    *,
    now: datetime,
    user_id: str,
    max_discount_ngwee: int | None = None,
) -> CouponQuote:
    """Validate ``rule`` against the cart and compute the exact discount split.

    ``max_discount_ngwee`` caps the result so a checkout never costs less than
    ``MIN_PAYABLE_NGWEE`` (callers pass items + delivery − MIN_PAYABLE_NGWEE).
    """
    check_window(rule, now=now, user_id=user_id)
    all_lines = list(lines)
    eligible = [line for line in all_lines if line_is_eligible(rule, line)]
    if not eligible:
        raise CouponError("coupon.not_applicable")
    eligible_subtotal = sum(line.line_total_ngwee for line in eligible)
    if eligible_subtotal < rule.min_spend_ngwee:
        raise CouponError("coupon.min_spend", min_spend_ngwee=rule.min_spend_ngwee)
    discount = raw_discount_ngwee(rule, eligible_subtotal)
    if max_discount_ngwee is not None:
        discount = min(discount, max(0, max_discount_ngwee))
    if discount <= 0:
        raise CouponError("coupon.not_applicable")
    per_line = allocate_proportionally(
        discount, {line.listing_id: line.line_total_ngwee for line in eligible}
    )
    vendor_discounts: dict[str, int] = {}
    for line in eligible:
        share = per_line.get(line.listing_id, 0)
        if share:
            vendor_discounts[line.vendor_id] = vendor_discounts.get(line.vendor_id, 0) + share
    return CouponQuote(
        coupon_id=rule.id,
        code=rule.code,
        funder=rule.funder,
        discount_ngwee=discount,
        eligible_subtotal_ngwee=eligible_subtotal,
        line_discounts={key: value for key, value in per_line.items() if value},
        vendor_discounts=vendor_discounts,
    )


def refund_discount_share_ngwee(
    *,
    order_discount_ngwee: int,
    order_items_ngwee: int,
    refunded_items_ngwee: int,
    already_returned_ngwee: int,
) -> int:
    """Coupon discount attached to a refunded slice of an order (integer, capped).

    Full refunds (``refunded_items_ngwee >= order_items_ngwee``) return whatever
    is still outstanding, so a series of partial returns always sums exactly to
    the order discount.
    """
    outstanding = max(0, order_discount_ngwee - max(0, already_returned_ngwee))
    if outstanding == 0 or refunded_items_ngwee <= 0 or order_items_ngwee <= 0:
        return 0
    if refunded_items_ngwee >= order_items_ngwee:
        return outstanding
    share = (order_discount_ngwee * refunded_items_ngwee) // order_items_ngwee
    return min(share, outstanding)


def scale_snapshot_for_vendor_discount(
    snapshot: Mapping[str, object], line_discounts: Mapping[str, int]
) -> dict[str, object]:
    """Vendor-funded coupon: commission is charged on the discounted line totals."""
    raw_lines = snapshot.get("lines")
    if not isinstance(raw_lines, list):
        return dict(snapshot)
    scaled: list[object] = []
    for raw in raw_lines:
        if not isinstance(raw, dict):
            scaled.append(raw)
            continue
        share = line_discounts.get(str(raw.get("listing_id")), 0)
        if share <= 0:
            scaled.append(dict(raw))
            continue
        total = int(raw.get("line_total_ngwee", 0))
        scaled.append(
            {**raw, "line_total_ngwee": max(0, total - share), "coupon_discount_ngwee": share}
        )
    return {**snapshot, "lines": scaled}


def lusaka_day_start(day: str) -> datetime:
    """``YYYY-MM-DD`` → 00:00 Africa/Lusaka (coupon windows are local dates)."""
    parsed = datetime.strptime(day, "%Y-%m-%d")
    return parsed.replace(tzinfo=LUSAKA)
