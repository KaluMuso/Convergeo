"""Pure coupon money rules: rounding, caps, exact splits, scopes, refund shares, ledger legs."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import pytest
from app.services.coupons.rules import (
    CouponError,
    CouponRule,
    DiscountLine,
    allocate_proportionally,
    quote_coupon,
    refund_discount_share_ngwee,
    scale_snapshot_for_vendor_discount,
)
from app.services.ledger.templates import (
    clawback,
    coupon_funding,
    refund_lane1,
    refund_lane2,
    refund_reversal,
)

NOW = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)
USER = "11111111-1111-1111-1111-111111111111"
VENDOR_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VENDOR_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def _rule(**overrides: object) -> CouponRule:
    base: dict[str, object] = {
        "id": "c-1",
        "code": "SAVE10",
        "kind": "percent",
        "percent_bps": 1_000,
        "funder": "platform",
        "scope": "all",
        "starts_at": NOW - timedelta(days=1),
    }
    base.update(overrides)
    return CouponRule(**base)  # type: ignore[arg-type]


LINES = [
    DiscountLine("l-a1", VENDOR_A, 12_345, frozenset({"cat-phones", "cat-electronics"})),
    DiscountLine("l-a2", VENDOR_A, 999),
    DiscountLine("l-b1", VENDOR_B, 7_001, frozenset({"cat-fashion"})),
]


def test_percent_discount_rounds_down_and_splits_exactly() -> None:
    quote = quote_coupon(_rule(), LINES, now=NOW, user_id=USER)
    assert quote.discount_ngwee == (12_345 + 999 + 7_001) * 1_000 // 10_000  # 2034
    assert sum(quote.line_discounts.values()) == quote.discount_ngwee
    assert sum(quote.vendor_discounts.values()) == quote.discount_ngwee
    totals = {line.listing_id: line.line_total_ngwee for line in LINES}
    assert all(0 < share <= totals[key] for key, share in quote.line_discounts.items())


def test_max_discount_cap_and_payable_floor() -> None:
    assert (
        quote_coupon(_rule(max_discount_ngwee=500), LINES, now=NOW, user_id=USER).discount_ngwee
        == 500
    )
    capped = quote_coupon(
        _rule(kind="fixed", percent_bps=None, amount_ngwee=50_000),
        LINES,
        now=NOW,
        user_id=USER,
        max_discount_ngwee=1_234,
    )
    assert capped.discount_ngwee == 1_234


def test_fixed_discount_never_exceeds_eligible_items() -> None:
    quote = quote_coupon(
        _rule(
            kind="fixed",
            percent_bps=None,
            amount_ngwee=10_000_000,
            scope="listing",
            scope_listing_id="l-a2",
        ),
        LINES,
        now=NOW,
        user_id=USER,
    )
    assert quote.discount_ngwee == 999
    assert dict(quote.line_discounts) == {"l-a2": 999}


def test_vendor_funded_coupon_only_touches_that_vendors_items() -> None:
    quote = quote_coupon(
        _rule(funder="vendor", vendor_id=VENDOR_B, scope="vendor", scope_vendor_id=VENDOR_B),
        LINES,
        now=NOW,
        user_id=USER,
    )
    assert set(quote.vendor_discounts) == {VENDOR_B}
    # Even a mis-scoped vendor coupon (scope=all) cannot discount another shop.
    other = quote_coupon(
        _rule(funder="vendor", vendor_id=VENDOR_B, scope="all"), LINES, now=NOW, user_id=USER
    )
    assert set(other.line_discounts) == {"l-b1"}


def test_category_scope_matches_ancestors() -> None:
    quote = quote_coupon(
        _rule(scope="category", scope_category_id="cat-electronics"), LINES, now=NOW, user_id=USER
    )
    assert set(quote.line_discounts) == {"l-a1"}


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"status": "paused"}, "coupon.inactive"),
        ({"starts_at": NOW + timedelta(hours=1)}, "coupon.not_started"),
        ({"ends_at": NOW}, "coupon.expired"),
        ({"personal_user_id": "someone-else"}, "coupon.not_found"),
        ({"min_spend_ngwee": 1_000_000}, "coupon.min_spend"),
        ({"scope": "listing", "scope_listing_id": "missing"}, "coupon.not_applicable"),
    ],
)
def test_rejections(overrides: dict[str, object], code: str) -> None:
    with pytest.raises(CouponError) as exc:
        quote_coupon(_rule(**overrides), LINES, now=NOW, user_id=USER)
    assert exc.value.code == code


def test_validity_window_ends_exclusive() -> None:
    rule = _rule(ends_at=NOW + timedelta(seconds=1))
    assert quote_coupon(rule, LINES, now=NOW, user_id=USER).discount_ngwee > 0


def test_allocation_property_exact_and_bounded() -> None:
    rng = random.Random(0xC0)
    for _ in range(500):
        weights = {f"k{i}": rng.randint(1, 50_000) for i in range(rng.randint(1, 6))}
        total = rng.randint(1, sum(weights.values()))
        shares = allocate_proportionally(total, weights)
        assert sum(shares.values()) == total
        assert all(0 <= shares[key] <= weights[key] for key in weights)


def test_partial_refund_shares_sum_to_the_order_discount() -> None:
    discount, items = 2_001, 30_000
    returned = 0
    for slice_ngwee in (10_000, 7_000):
        share = refund_discount_share_ngwee(
            order_discount_ngwee=discount,
            order_items_ngwee=items,
            refunded_items_ngwee=slice_ngwee,
            already_returned_ngwee=returned,
        )
        assert share == discount * slice_ngwee // items
        returned += share
    # Final full-order refund hands back whatever is still outstanding.
    returned += refund_discount_share_ngwee(
        order_discount_ngwee=discount,
        order_items_ngwee=items,
        refunded_items_ngwee=items,
        already_returned_ngwee=returned,
    )
    assert returned == discount


def test_refund_share_without_discount_is_zero() -> None:
    assert (
        refund_discount_share_ngwee(
            order_discount_ngwee=0,
            order_items_ngwee=10_000,
            refunded_items_ngwee=10_000,
            already_returned_ngwee=0,
        )
        == 0
    )


def test_vendor_snapshot_charges_commission_on_discounted_price() -> None:
    snapshot = {
        "lines": [
            {"listing_id": "l-b1", "rate_bps": 1_000, "line_total_ngwee": 7_001},
            {"listing_id": "l-b2", "rate_bps": 1_000, "line_total_ngwee": 3_000},
        ]
    }
    scaled = scale_snapshot_for_vendor_discount(snapshot, {"l-b1": 1_001})
    lines = scaled["lines"]
    assert isinstance(lines, list)
    assert lines[0]["line_total_ngwee"] == 6_000
    assert lines[0]["coupon_discount_ngwee"] == 1_001
    assert lines[1]["line_total_ngwee"] == 3_000


# --- ledger legs --------------------------------------------------------------


def _by_kind(legs: tuple[object, ...]) -> dict[str, int]:
    out: dict[str, int] = {}
    for leg in legs:
        kind = leg.account.kind  # type: ignore[attr-defined]
        out[kind] = out.get(kind, 0) + leg.amount_ngwee  # type: ignore[attr-defined]
    return out


def test_coupon_funding_legs() -> None:
    assert _by_kind(coupon_funding(discount_ngwee=2_000).legs) == {
        "marketing_expense": 2_000,
        "escrow": -2_000,
    }


def test_refund_lane1_returns_platform_share_to_marketing() -> None:
    legs = refund_lane1(refund_ngwee=21_000, promo_return_ngwee=2_000).legs
    assert _by_kind(legs) == {
        "escrow": 23_000,
        "platform_cash": -21_000,
        "marketing_expense": -2_000,
    }
    # Payout failure reverses every leg, coupon share included.
    reversed_legs = refund_reversal(original_legs=legs).legs
    assert _by_kind(reversed_legs) == {
        "escrow": -23_000,
        "platform_cash": 21_000,
        "marketing_expense": 2_000,
    }


def test_refund_lane1_without_coupon_is_unchanged() -> None:
    assert len(refund_lane1(refund_ngwee=5_000).legs) == 2


def test_refund_lane2_with_promo_balances() -> None:
    legs = refund_lane2(
        escrow_release_ngwee=10_000,
        refund_to_customer_ngwee=8_000,
        vendor_retained_ngwee=1_000,
        restocking_fee_ngwee=1_000,
        vendor_id=VENDOR_A,
        promo_return_ngwee=500,
    ).legs
    kinds = _by_kind(legs)
    assert kinds["escrow"] == 10_500 and kinds["marketing_expense"] == -500
    assert sum(kinds.values()) == 0


def test_post_release_clawback_takes_full_price_from_vendor() -> None:
    legs = clawback(clawback_ngwee=18_000, vendor_id=VENDOR_A, promo_return_ngwee=2_000).legs
    kinds = _by_kind(legs)
    assert kinds == {
        "vendor_payable": 20_000,
        "platform_cash": -18_000,
        "marketing_expense": -2_000,
    }
