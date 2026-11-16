"""W8 offers — allocation math, pricing engine, order-line expansion (pure units)."""

from __future__ import annotations

import itertools
import random
from datetime import UTC, datetime, timedelta

import pytest
from app.errors import AppError
from app.services.offers.allocation import allocate_pro_rata, percent_of, split_line_units
from app.services.offers.apply import expand_priced_lines
from app.services.offers.engine import (
    OfferDef,
    OfferItemDef,
    PricingLine,
    price_cart,
)
from app.services.offers.store import build_offer_def, offer_is_live
from app.services.orders.create import CartLineInput, VendorFulfilmentInput, _validate_vendor_groups

VENDOR_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
VENDOR_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
L1 = "11111111-1111-4111-8111-111111111111"
L2 = "22222222-2222-4222-8222-222222222222"
L3 = "33333333-3333-4333-8333-333333333333"
L4 = "44444444-4444-4444-8444-444444444444"
GIFT = "99999999-9999-4999-8999-999999999999"
C1 = "c1111111-1111-4111-8111-111111111111"
C2 = "c2222222-2222-4222-8222-222222222222"
C3 = "c3333333-3333-4333-8333-333333333333"
OFFER = "0ffe0000-0000-4000-8000-000000000001"


def line(key: str, listing: str, qty: int, unit: int, vendor: str = VENDOR_A) -> PricingLine:
    return PricingLine(
        key=key, listing_id=listing, vendor_id=vendor, qty=qty, unit_price_ngwee=unit
    )


def bundle_percent(pct: int, *, vendor: str = VENDOR_A, max_apps: int = 1) -> OfferDef:
    return OfferDef(
        id=OFFER,
        vendor_id=vendor,
        offer_type="bundle",
        title="Starter kit",
        items=(
            OfferItemDef("anchor", "product", L1),
            OfferItemDef("addon", "product", L2),
            OfferItemDef("addon", "product", L3),
            OfferItemDef("addon", "product", L4),
        ),
        bundle_pricing="addon_percent_off",
        addon_percent_off=pct,
        max_applications_per_order=max_apps,
    )


# ---------------------------------------------------------------------------
# allocation
# ---------------------------------------------------------------------------


def test_allocation_sums_exactly_and_is_deterministic() -> None:
    shares = allocate_pro_rata(100, [1, 1, 1])
    assert shares == [34, 33, 33]
    assert sum(shares) == 100
    assert allocate_pro_rata(100, [1, 1, 1]) == shares


def test_allocation_largest_remainder_then_position() -> None:
    # 10 * [3, 3, 4] / 10 = [3, 3, 4] exactly; 11 -> remainders [3, 3, 4]/10 -> idx 2 first.
    assert allocate_pro_rata(11, [3, 3, 4]) == [3, 3, 5]
    assert allocate_pro_rata(1, [5, 5]) == [1, 0]


def test_allocation_one_ngwee_edges() -> None:
    assert allocate_pro_rata(1, [1]) == [1]
    assert allocate_pro_rata(1, [1, 1, 1]) == [1, 0, 0]
    assert allocate_pro_rata(0, [7, 9]) == [0, 0]
    assert allocate_pro_rata(2, [1, 1]) == [1, 1]
    assert allocate_pro_rata(1, [0, 1]) == [0, 1]


def test_allocation_property_random() -> None:
    rng = random.Random(8)
    for _ in range(2000):
        weights = [rng.randint(0, 50_000) for _ in range(rng.randint(1, 6))]
        total = sum(weights)
        if total == 0:
            continue
        amount = rng.randint(0, total)
        shares = allocate_pro_rata(amount, weights)
        assert sum(shares) == amount
        assert all(0 <= s <= w for s, w in zip(shares, weights, strict=True))


def test_allocation_rejects_float_and_negative() -> None:
    with pytest.raises(TypeError):
        allocate_pro_rata(1.5, [1])  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        allocate_pro_rata(1, [1.0])  # type: ignore[list-item]
    with pytest.raises(ValueError):
        allocate_pro_rata(-1, [1])
    with pytest.raises(ValueError):
        allocate_pro_rata(1, [0, 0])
    with pytest.raises(ValueError):
        allocate_pro_rata(1, [])


@pytest.mark.parametrize(("total", "qty"), [(1000, 3), (7, 7), (8, 7), (999, 1), (1, 1), (10, 4)])
def test_split_line_units_sums_and_is_integral(total: int, qty: int) -> None:
    parts = split_line_units(total, qty)
    assert sum(q for q, _ in parts) == qty
    assert sum(q * u for q, u in parts) == total
    assert len(parts) <= 2
    assert all(isinstance(u, int) for _, u in parts)


def test_split_line_units_one_ngwee_below_qty_gives_zero_part() -> None:
    assert split_line_units(1, 3) == [(2, 0), (1, 1)]


def test_percent_of_floors_in_vendors_favour() -> None:
    assert percent_of(999, 75) == 749
    assert percent_of(1, 75) == 0


# ---------------------------------------------------------------------------
# engine
# ---------------------------------------------------------------------------


def test_bundle_percent_addons_only_and_sums_to_bundle_total() -> None:
    lines = [
        line(C1, L1, 1, 50_000),
        line(C2, L2, 1, 1_001),
        line(C3, L3, 1, 2_002),
        line("c4", L4, 1, 3_003),
    ]
    priced = price_cart(lines, [bundle_percent(75)])
    addon_total = 1_001 + 2_002 + 3_003
    discount = addon_total * 75 // 100
    assert priced.lines[C1].final_total_ngwee == 50_000  # anchor untouched
    assert priced.savings_ngwee == discount
    assert priced.subtotal_ngwee == 50_000 + addon_total - discount
    assert sum(o.final_total_ngwee for o in priced.lines.values()) == priced.subtotal_ngwee
    assert all(o.offer_id == OFFER for o in priced.lines.values())


def test_bundle_fixed_price_allocates_across_every_line() -> None:
    offer = OfferDef(
        id=OFFER,
        vendor_id=VENDOR_A,
        offer_type="bundle",
        title="Trio",
        items=(
            OfferItemDef("anchor", "product", L1),
            OfferItemDef("addon", "product", L2),
            OfferItemDef("addon", "product", L3),
        ),
        bundle_pricing="fixed_price",
        bundle_price_ngwee=10_000,
    )
    lines = [line(C1, L1, 1, 6_667), line(C2, L2, 1, 3_333), line(C3, L3, 1, 3_333)]
    priced = price_cart(lines, [offer])
    assert priced.subtotal_ngwee == 10_000
    assert sum(o.final_total_ngwee for o in priced.lines.values()) == 10_000


def test_bundle_partial_quantity_only_discounts_complete_sets() -> None:
    lines = [
        line(C1, L1, 3, 1_000),
        line(C2, L2, 1, 1_000),
        line(C3, L3, 1, 1_000),
        line("c4", L4, 1, 1_000),
    ]
    priced = price_cart(lines, [bundle_percent(50)])
    # one set: addons 3 * 1000 at 50% -> 1500 off; anchor keeps 3 * 1000.
    assert priced.savings_ngwee == 1_500
    assert priced.lines[C1].final_total_ngwee == 3_000


def test_bundle_missing_member_does_not_apply() -> None:
    lines = [line(C1, L1, 1, 1_000), line(C2, L2, 1, 1_000)]
    priced = price_cart(lines, [bundle_percent(50)])
    assert priced.applications == ()
    assert priced.savings_ngwee == 0


def test_buy_n_pay_m_three_for_two_cheapest_free() -> None:
    offer = OfferDef(
        id=OFFER,
        vendor_id=VENDOR_A,
        offer_type="buy_n_pay_m",
        title="3 for 2",
        items=(OfferItemDef("eligible", "product", L1), OfferItemDef("eligible", "product", L2)),
        buy_n=3,
        pay_m=2,
    )
    lines = [line(C1, L1, 2, 5_000), line(C2, L2, 2, 1_000)]
    priced = price_cart(lines, [offer])
    # units desc: 5000, 5000, 1000 | 1000 -> one chunk, 1000 free.
    assert priced.savings_ngwee == 1_000
    assert priced.subtotal_ngwee == 12_000 - 1_000
    assert priced.lines[C1].discount_ngwee + priced.lines[C2].discount_ngwee == 1_000


def test_bxgy_gift_line_limited_by_pool_and_applications() -> None:
    offer = OfferDef(
        id=OFFER,
        vendor_id=VENDOR_A,
        offer_type="bxgy",
        title="Buy 2 get 1",
        items=(OfferItemDef("trigger", "product", L1), OfferItemDef("reward", "product", GIFT)),
        buy_qty=2,
        get_qty=1,
        gift_available=1,
        max_applications_per_order=5,
        reward_unit_price_ngwee=2_500,
        reward_title="Lotion",
    )
    priced = price_cart([line(C1, L1, 6, 1_000)], [offer])
    assert len(priced.gifts) == 1
    gift = priced.gifts[0]
    assert (gift.qty, gift.listing_id, gift.parent_key) == (1, GIFT, C1)
    assert priced.subtotal_ngwee == 6_000  # trigger keeps its price; gift is free
    assert priced.gift_value_ngwee == 2_500


def test_gift_out_of_stock_skips_offer() -> None:
    offer = OfferDef(
        id=OFFER,
        vendor_id=VENDOR_A,
        offer_type="free_gift",
        title="Free gift",
        items=(OfferItemDef("trigger", "product", L1), OfferItemDef("reward", "product", GIFT)),
        gift_available=0,
        reward_unit_price_ngwee=2_500,
    )
    priced = price_cart([line(C1, L1, 1, 1_000)], [offer])
    assert priced.gifts == ()
    assert priced.applications == ()


def test_offer_from_another_vendor_never_applies() -> None:
    lines = [
        line(C1, L1, 1, 1_000),
        line(C2, L2, 1, 1_000),
        line(C3, L3, 1, 1_000),
        line("c4", L4, 1, 1_000),
    ]
    priced = price_cart(lines, [bundle_percent(50, vendor=VENDOR_B)])
    assert priced.applications == ()
    # Same listing ids but the line belongs to vendor A: B's offer cannot touch it.
    assert all(o.offer_id is None for o in priced.lines.values())


def test_service_or_event_offer_is_not_cart_applicable() -> None:
    offer = OfferDef(
        id=OFFER,
        vendor_id=VENDOR_A,
        offer_type="free_gift",
        title="Book a facial",
        items=(OfferItemDef("trigger", "service", L1), OfferItemDef("reward", "product", GIFT)),
        gift_available=5,
        reward_unit_price_ngwee=2_500,
    )
    assert not offer.cart_applicable
    assert price_cart([line(C1, L1, 1, 1_000)], [offer]).applications == ()


def test_discount_over_admin_cap_is_skipped() -> None:
    lines = [
        line(C1, L1, 1, 1_000),
        line(C2, L2, 1, 1_000),
        line(C3, L3, 1, 1_000),
        line("c4", L4, 1, 1_000),
    ]
    assert price_cart(lines, [bundle_percent(95)], max_discount_pct=50).applications == ()


def test_allocation_that_would_zero_a_paid_unit_is_skipped() -> None:
    offer = OfferDef(
        id=OFFER,
        vendor_id=VENDOR_A,
        offer_type="bundle",
        title="Tiny",
        items=(OfferItemDef("anchor", "product", L1), OfferItemDef("addon", "product", L2)),
        bundle_pricing="fixed_price",
        bundle_price_ngwee=1,
    )
    priced = price_cart([line(C1, L1, 1, 2), line(C2, L2, 1, 2)], [offer], max_discount_pct=95)
    assert priced.applications == ()


def test_one_offer_per_line_no_stacking() -> None:
    other = OfferDef(
        id="0ffe0000-0000-4000-8000-000000000002",
        vendor_id=VENDOR_A,
        offer_type="buy_n_pay_m",
        title="2 for 1",
        items=(OfferItemDef("eligible", "product", L2),),
        buy_n=2,
        pay_m=1,
    )
    lines = [
        line(C1, L1, 1, 1_000),
        line(C2, L2, 2, 1_000),
        line(C3, L3, 1, 1_000),
        line("c4", L4, 1, 1_000),
    ]
    priced = price_cart(lines, [other, bundle_percent(10)])
    # bundle evaluates first and claims L2's line; buy_n_pay_m finds nothing left.
    assert [a.offer_type for a in priced.applications] == ["bundle"]


def test_engine_is_order_independent_and_idempotent() -> None:
    lines = [
        line(C1, L1, 1, 1_000),
        line(C2, L2, 1, 333),
        line(C3, L3, 1, 777),
        line("c4", L4, 1, 101),
    ]
    first = price_cart(lines, [bundle_percent(75)])
    for perm in itertools.permutations(lines):
        again = price_cart(list(perm), [bundle_percent(75)])
        assert again.lines == first.lines


def test_engine_rejects_nonpositive_lines() -> None:
    with pytest.raises(ValueError):
        price_cart([line(C1, L1, 1, 0)], [])


# ---------------------------------------------------------------------------
# liveness (expired offers)
# ---------------------------------------------------------------------------


def test_offer_is_live_window_and_pause() -> None:
    now = datetime(2026, 11, 15, 12, tzinfo=UTC)
    row = {
        "status": "active",
        "paused_by_admin": False,
        "starts_at": (now - timedelta(days=1)).isoformat(),
        "ends_at": (now + timedelta(days=1)).isoformat(),
    }
    assert offer_is_live(row, now)
    assert not offer_is_live({**row, "ends_at": (now - timedelta(seconds=1)).isoformat()}, now)
    assert not offer_is_live({**row, "starts_at": (now + timedelta(hours=1)).isoformat()}, now)
    assert not offer_is_live({**row, "paused_by_admin": True}, now)
    assert not offer_is_live({**row, "status": "paused"}, now)


def test_build_offer_def_gift_available_from_pool() -> None:
    offer = build_offer_def(
        {
            "id": OFFER,
            "vendor_id": VENDOR_A,
            "offer_type": "free_gift",
            "title": "G",
            "gift_stock_total": 5,
            "gift_stock_reserved": 5,
            "max_applications_per_order": 1,
        },
        [
            {"role": "trigger", "item_kind": "product", "listing_id": L1, "qty": 1},
            {"role": "reward", "item_kind": "product", "listing_id": GIFT, "qty": 1},
        ],
        reward_listing={"price_ngwee": 900, "title_override": "Shirt"},
    )
    assert offer.gift_available == 0
    assert offer.reward_title == "Shirt"


# ---------------------------------------------------------------------------
# expansion into order lines + checkout tamper guard
# ---------------------------------------------------------------------------


def _cart_line(cid: str, listing: str, qty: int, unit: int) -> CartLineInput:
    return CartLineInput(
        cart_item_id=cid,
        listing_id=listing,
        vendor_id=VENDOR_A,
        qty=qty,
        unit_price_ngwee=unit,
        title_snapshot=None,
    )


def test_expansion_splits_with_integral_units_and_one_hold_consumer() -> None:
    cart = [
        _cart_line(C1, L1, 1, 10_000),
        _cart_line(C2, L2, 3, 1_000),
        _cart_line(C3, L3, 1, 1_000),
        _cart_line("c4", L4, 1, 1_000),
    ]
    priced = price_cart(
        [
            PricingLine(c.cart_item_id, c.listing_id, c.vendor_id, c.qty, c.unit_price_ngwee)
            for c in cart
        ],
        [bundle_percent(33)],
    )
    expanded = expand_priced_lines(cart, priced)
    assert sum(e.qty * e.unit_price_ngwee for e in expanded) == priced.subtotal_ngwee
    by_cart: dict[str, list[CartLineInput]] = {}
    for e in expanded:
        by_cart.setdefault(e.cart_item_id, []).append(e)
    for cid, parts in by_cart.items():
        consumers = [p for p in parts if p.consumes_reservation]
        assert len(consumers) == 1
        original = next(c for c in cart if c.cart_item_id == cid)
        assert consumers[0].hold_qty == original.qty
        assert sum(p.qty for p in parts) == original.qty
        assert sum(p.offer_discount_ngwee for p in parts) == priced.lines[cid].discount_ngwee
        assert all(p.list_unit_price_ngwee == original.unit_price_ngwee for p in parts)
        assert all(p.offer_snapshot and p.offer_snapshot["offer_id"] == OFFER for p in parts)


def test_expansion_appends_gift_after_parent_at_zero() -> None:
    offer = OfferDef(
        id=OFFER,
        vendor_id=VENDOR_A,
        offer_type="free_gift",
        title="Free shirt",
        items=(OfferItemDef("trigger", "product", L1), OfferItemDef("reward", "product", GIFT)),
        gift_available=3,
        reward_unit_price_ngwee=4_000,
        reward_title="Shirt",
    )
    cart = [_cart_line(C1, L1, 1, 20_000)]
    priced = price_cart([PricingLine(C1, L1, VENDOR_A, 1, 20_000)], [offer])
    expanded = expand_priced_lines(cart, priced)
    assert [e.is_offer_gift for e in expanded] == [False, True]
    gift = expanded[1]
    assert gift.unit_price_ngwee == 0
    assert gift.consumes_reservation is False
    assert gift.offer_parent_cart_item_id == C1
    assert gift.list_unit_price_ngwee == 4_000
    # Commission is charged on what is paid: the gift contributes 0 to the subtotal.
    assert sum(e.qty * e.unit_price_ngwee for e in expanded) == 20_000


def test_expansion_refuses_zero_priced_paid_unit() -> None:
    cart = [_cart_line(C1, L1, 3, 1)]
    from app.services.offers.engine import LineOutcome, PricedCart

    tampered = PricedCart(
        lines={C1: LineOutcome(key=C1, list_total_ngwee=3, final_total_ngwee=1, offer_id=OFFER)},
        gifts=(),
        applications=(),
    )
    with pytest.raises(AppError) as exc:
        expand_priced_lines(cart, tampered)
    assert exc.value.code == "offers.invalid_allocation"


def test_tampered_client_subtotal_is_rejected_against_offer_pricing() -> None:
    cart = [
        _cart_line(C1, L1, 1, 10_000),
        _cart_line(C2, L2, 1, 1_000),
        _cart_line(C3, L3, 1, 1_000),
        _cart_line("c4", L4, 1, 1_000),
    ]
    priced = price_cart(
        [
            PricingLine(c.cart_item_id, c.listing_id, c.vendor_id, c.qty, c.unit_price_ngwee)
            for c in cart
        ],
        [bundle_percent(50)],
    )
    expanded = expand_priced_lines(cart, priced)
    honest = priced.subtotal_ngwee
    # Client claims a bigger discount than the offer gives -> 409.
    with pytest.raises(AppError) as exc:
        _validate_vendor_groups(
            vendor_groups=[VendorFulfilmentInput(VENDOR_A, "pickup", None, 0, honest - 100)],
            cart_lines=expanded,
            session_subtotal=honest - 100,
            session_delivery_fee=0,
            session_total=honest - 100,
        )
    assert exc.value.code == "orders.totals_mismatch"
    # The honest numbers pass.
    _validate_vendor_groups(
        vendor_groups=[VendorFulfilmentInput(VENDOR_A, "pickup", None, 0, honest)],
        cart_lines=expanded,
        session_subtotal=honest,
        session_delivery_fee=0,
        session_total=honest,
    )


def test_refund_of_one_bundle_line_is_its_pro_rata_share() -> None:
    from app.services.refunds.math import compute_lane1_refund

    cart = [
        _cart_line(C1, L1, 1, 10_000),
        _cart_line(C2, L2, 1, 1_001),
        _cart_line(C3, L3, 1, 1_001),
        _cart_line("c4", L4, 1, 1_001),
    ]
    priced = price_cart(
        [
            PricingLine(c.cart_item_id, c.listing_id, c.vendor_id, c.qty, c.unit_price_ngwee)
            for c in cart
        ],
        [bundle_percent(75)],
    )
    expanded = expand_priced_lines(cart, priced)
    addon = next(e for e in expanded if e.cart_item_id == C2)
    refund = compute_lane1_refund(
        item_ngwee=addon.qty * addon.unit_price_ngwee, delivery_fee_ngwee=0
    )
    assert refund.refund_ngwee == priced.lines[C2].final_total_ngwee
    assert refund.refund_ngwee < 1_001
