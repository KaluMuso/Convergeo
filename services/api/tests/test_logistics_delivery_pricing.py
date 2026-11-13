"""Who pays for delivery (logistics phase 1): customer, vendor free delivery, automatic."""

from __future__ import annotations

import pytest
from app.services.logistics.delivery_pricing import (
    AutoFreeDeliveryPolicy,
    PricingLine,
    VendorDeliveryTerms,
    basket_auto_free_eligible,
    price_delivery_groups,
)

FEES = {"lusaka_a": 3_000, "lusaka_b": 4_500, "lusaka_c": 6_500}
POLICY = AutoFreeDeliveryPolicy()  # K15,000 · 500 kg · 50% of commission


def _line(
    vendor: str,
    total: int,
    *,
    bps: int = 1_000,
    weight: int | None = 1_000,
    qty: int = 1,
    free: bool = False,
    wholesale: bool = False,
) -> PricingLine:
    return PricingLine(
        vendor_id=vendor,
        listing_id=f"l-{vendor}-{total}",
        qty=qty,
        line_total_ngwee=total,
        commission_bps=bps,
        wholesale=wholesale,
        free_delivery=free,
        weight_grams=weight,
    )


def test_customer_pays_zone_fee_by_default_and_k200_rule_is_gone() -> None:
    prices = price_delivery_groups(
        lines=[_line("v1", 50_000)],  # K500: used to be free under the K200 rule
        delivery_zones={"v1": "lusaka_b"},
        zone_fees=FEES,
        vendor_terms={},
        policy=POLICY,
    )
    assert prices["v1"].customer_fee_ngwee == 4_500
    assert prices["v1"].funding == "customer"
    assert prices["v1"].funded_ngwee == 0


def test_pickup_group_costs_nothing() -> None:
    prices = price_delivery_groups(
        lines=[_line("v1", 5_000)],
        delivery_zones={"v1": None},
        zone_fees=FEES,
        vendor_terms={},
        policy=POLICY,
    )
    assert prices["v1"].customer_fee_ngwee == 0
    assert prices["v1"].funding == "customer"


def test_vendor_free_delivery_charges_vendor_not_customer() -> None:
    prices = price_delivery_groups(
        lines=[_line("v1", 5_000, free=True), _line("v2", 7_000)],
        delivery_zones={"v1": "lusaka_c", "v2": "lusaka_c"},
        zone_fees=FEES,
        vendor_terms={},
        policy=POLICY,
    )
    assert (prices["v1"].customer_fee_ngwee, prices["v1"].funding) == (0, "vendor")
    assert prices["v1"].funded_ngwee == 6_500
    assert (prices["v2"].customer_fee_ngwee, prices["v2"].funding) == (6_500, "customer")


def test_listing_free_delivery_needs_every_line_of_the_group() -> None:
    prices = price_delivery_groups(
        lines=[_line("v1", 5_000, free=True), _line("v1", 6_000, free=False)],
        delivery_zones={"v1": "lusaka_a"},
        zone_fees=FEES,
        vendor_terms={},
        policy=POLICY,
    )
    assert prices["v1"].funding == "customer"
    assert prices["v1"].customer_fee_ngwee == 3_000


def test_vendor_wide_free_delivery_and_self_delivery() -> None:
    prices = price_delivery_groups(
        lines=[_line("v1", 5_000), _line("v2", 5_000)],
        delivery_zones={"v1": "lusaka_a", "v2": "lusaka_a"},
        zone_fees=FEES,
        vendor_terms={
            "v1": VendorDeliveryTerms(free_delivery_all=True),
            "v2": VendorDeliveryTerms(free_delivery_all=True, free_delivery_method="self_delivery"),
        },
        policy=POLICY,
    )
    assert (prices["v1"].funding, prices["v1"].funded_ngwee) == ("vendor", 3_000)
    # Restaurant / own courier / Yango: vendor delivers, nothing is booked.
    assert (prices["v2"].funding, prices["v2"].funded_ngwee) == ("vendor_self", 0)
    assert prices["v2"].customer_fee_ngwee == 0


def test_automatic_free_delivery_for_large_retail_basket() -> None:
    lines = [_line("v1", 1_000_000), _line("v2", 600_000)]  # K16,000 at 10%
    prices = price_delivery_groups(
        lines=lines,
        delivery_zones={"v1": "lusaka_c", "v2": "lusaka_b"},
        zone_fees=FEES,
        vendor_terms={},
        policy=POLICY,
    )
    assert {v: (p.customer_fee_ngwee, p.funding, p.funded_ngwee) for v, p in prices.items()} == {
        "v1": (0, "platform", 6_500),
        "v2": (0, "platform", 4_500),
    }


@pytest.mark.parametrize(
    ("lines", "reason"),
    [
        ([_line("v1", 1_499_999)], "below threshold"),
        ([_line("v1", 1_600_000, wholesale=True)], "wholesale basket"),
        ([_line("v1", 1_600_000, weight=None)], "unknown weight"),
        ([_line("v1", 1_600_000, weight=250_000, qty=2)], "exactly 500 kg"),
        # 0.5% commission on K16,000 = K80; half of it (K40) cannot fund K65.
        ([_line("v1", 1_600_000, bps=50)], "commission cannot fund it"),
    ],
)
def test_automatic_free_delivery_refusals_leave_customer_paying(
    lines: list[PricingLine], reason: str
) -> None:
    prices = price_delivery_groups(
        lines=lines,
        delivery_zones={"v1": "lusaka_c"},
        zone_fees=FEES,
        vendor_terms={},
        policy=POLICY,
    )
    assert prices["v1"].funding == "customer", reason
    assert prices["v1"].customer_fee_ngwee == 6_500, reason
    assert prices["v1"].funded_ngwee == 0, reason


def test_vendor_free_group_is_not_double_funded_by_automatic_rule() -> None:
    lines = [_line("v1", 1_000_000, free=True), _line("v2", 600_000)]
    prices = price_delivery_groups(
        lines=lines,
        delivery_zones={"v1": "lusaka_a", "v2": "lusaka_a"},
        zone_fees=FEES,
        vendor_terms={},
        policy=POLICY,
    )
    assert (prices["v1"].funding, prices["v1"].funded_ngwee) == ("vendor", 3_000)
    assert (prices["v2"].funding, prices["v2"].funded_ngwee) == ("platform", 3_000)
    # Never both: one leg per group, so delivery_revenue is booked exactly once.
    assert sum(p.funded_ngwee for p in prices.values()) == 6_000


def test_threshold_zero_disables_the_automatic_rule() -> None:
    policy = AutoFreeDeliveryPolicy(threshold_ngwee=0)
    assert not basket_auto_free_eligible([_line("v1", 10_000_000)], policy)


def test_money_inputs_must_be_integer_ngwee() -> None:
    with pytest.raises(TypeError):
        price_delivery_groups(
            lines=[_line("v1", 1_600_000)],
            delivery_zones={"v1": "lusaka_a"},
            zone_fees={"lusaka_a": 30.5},  # type: ignore[dict-item]
            vendor_terms={},
            policy=POLICY,
        )
    with pytest.raises(ValueError):
        AutoFreeDeliveryPolicy(commission_share_bps=10_001)


def test_order_insert_refuses_inconsistent_funding() -> None:
    from app.services.orders.create import VendorFulfilmentInput, _delivery_funding_for

    def group(**kw: object) -> VendorFulfilmentInput:
        base: dict[str, object] = {
            "vendor_id": "v1",
            "fulfilment": "delivery",
            "delivery_zone": "lusaka_a",
            "delivery_fee_ngwee": 0,
            "subtotal_ngwee": 10_000,
        }
        base.update(kw)
        return VendorFulfilmentInput(**base)  # type: ignore[arg-type]

    assert _delivery_funding_for(group(delivery_funding="vendor", delivery_funded_ngwee=3_000)) == (
        "vendor",
        3_000,
    )
    # Customer pays AND vendor is charged: double-charging is refused.
    with pytest.raises(ValueError):
        _delivery_funding_for(
            group(delivery_fee_ngwee=3_000, delivery_funding="vendor", delivery_funded_ngwee=3_000)
        )
    with pytest.raises(ValueError):
        _delivery_funding_for(group(delivery_funding="vendor_self", delivery_funded_ngwee=3_000))
    with pytest.raises(ValueError):
        _delivery_funding_for(group(delivery_funding="nobody"))
    with pytest.raises(TypeError):
        _delivery_funding_for(group(delivery_funding="vendor", delivery_funded_ngwee=30.0))
    # Pickup never carries funding, whatever the caller says.
    assert _delivery_funding_for(
        group(fulfilment="pickup", delivery_funding="vendor", delivery_funded_ngwee=3_000)
    ) == ("customer", 0)
