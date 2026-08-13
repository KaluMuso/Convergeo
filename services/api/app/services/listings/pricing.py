"""Integer-only product pricing and FX snapshot helpers.

The API stores ZMW money in integer ngwee and quantities in integer milli-units.
This module is intentionally free of floats and Decimal so the same result is
obtained in the vendor preview, cart validation, and checkout snapshot path.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence
from typing import Literal


PricingMode = Literal["fixed", "measured", "bundle", "tiered", "range", "from", "quote_only"]


@dataclass(frozen=True, slots=True)
class PriceResolution:
    price_ngwee: int | None
    requires_rfq: bool


def normalized_price_per_base_unit_microngwee(
    *,
    price_per_step_ngwee: int,
    unit_step_milli: int,
    base_units_per_sale_unit_milli: int,
) -> int:
    """Return exact micro-ngwee per base unit without lossy decimal rounding."""
    if price_per_step_ngwee <= 0 or unit_step_milli <= 0 or base_units_per_sale_unit_milli <= 0:
        raise ValueError("price and unit normalizers must be positive integers")
    # Both unit inputs are milli-scaled.  Convert their product back to whole
    # base units while retaining micro-ngwee precision for the comparison value.
    numerator = price_per_step_ngwee * 1_000_000_000_000
    denominator = unit_step_milli * base_units_per_sale_unit_milli
    # Stored precision is micro-ngwee, so rounding half up remains deterministic
    # and never invokes a floating-point representation.
    return (numerator + denominator // 2) // denominator


def resolve_option_price_ngwee(
    *,
    base_price_ngwee: int,
    option_deltas_ngwee: Sequence[tuple[int, bool]],
) -> PriceResolution:
    """Resolve a Class-E configuration or require an accepted RFQ.

    A non-deterministic option deliberately has no estimated checkout price:
    it must become an accepted-RFQ line instead of allowing a stale quote to be
    charged after payment.
    """
    if base_price_ngwee <= 0:
        raise ValueError("base_price_ngwee must be positive")
    if any(not deterministic for _delta, deterministic in option_deltas_ngwee):
        return PriceResolution(price_ngwee=None, requires_rfq=True)
    total = base_price_ngwee + sum(delta for delta, _deterministic in option_deltas_ngwee)
    if total <= 0:
        raise ValueError("configured price must be positive")
    return PriceResolution(price_ngwee=total, requires_rfq=False)


def usd_microdollars_to_zmw_ngwee(
    *,
    usd_microdollars: int,
    rate_zmw_per_usd_micros: int,
    vendor_margin_bps: int,
) -> int:
    """Convert USD micro-dollars to ZMW ngwee, rounded half-up in integers."""
    if usd_microdollars <= 0 or rate_zmw_per_usd_micros <= 0:
        raise ValueError("USD amount and FX rate must be positive")
    if not 0 <= vendor_margin_bps <= 5_000:
        raise ValueError("vendor_margin_bps must be between 0 and 5000")
    numerator = usd_microdollars * rate_zmw_per_usd_micros * 100 * (10_000 + vendor_margin_bps)
    denominator = 1_000_000 * 1_000_000 * 10_000
    return (numerator + denominator // 2) // denominator
