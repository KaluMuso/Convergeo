from __future__ import annotations

import pytest

from app.services.listings.pricing import (
    normalized_price_per_base_unit_microngwee,
    resolve_option_price_ngwee,
    usd_microdollars_to_zmw_ngwee,
)


def test_normalized_measured_price_is_integer_exact() -> None:
    # K37.50 per 0.5 m -> K75.00 per metre, in micro-ngwee.
    assert normalized_price_per_base_unit_microngwee(
        price_per_step_ngwee=3_750,
        unit_step_milli=500,
        base_units_per_sale_unit_milli=1_000,
    ) == 7_500_000_000


def test_deterministic_class_e_options_produce_final_price() -> None:
    resolved = resolve_option_price_ngwee(
        base_price_ngwee=100_000,
        option_deltas_ngwee=[(12_500, True), (5_000, True)],
    )
    assert resolved.price_ngwee == 117_500
    assert not resolved.requires_rfq


def test_non_deterministic_class_e_option_requires_rfq() -> None:
    resolved = resolve_option_price_ngwee(
        base_price_ngwee=100_000,
        option_deltas_ngwee=[(0, False)],
    )
    assert resolved.price_ngwee is None
    assert resolved.requires_rfq


def test_fx_conversion_is_integer_and_snapshottable() -> None:
    # $10 at K25/USD plus a 5% margin = K262.50.
    assert usd_microdollars_to_zmw_ngwee(
        usd_microdollars=10_000_000,
        rate_zmw_per_usd_micros=25_000_000,
        vendor_margin_bps=500,
    ) == 26_250


@pytest.mark.parametrize("amount,rate,margin", [(0, 1, 0), (1, 0, 0), (1, 1, 5001)])
def test_fx_rejects_invalid_integer_inputs(amount: int, rate: int, margin: int) -> None:
    with pytest.raises(ValueError):
        usd_microdollars_to_zmw_ngwee(
            usd_microdollars=amount,
            rate_zmw_per_usd_micros=rate,
            vendor_margin_bps=margin,
        )
