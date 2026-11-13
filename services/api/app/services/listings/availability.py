"""Shared public availability rules for vendor listings."""

from __future__ import annotations


def minimum_purchase_qty(*, min_steps: int = 1, moq: int = 1) -> int:
    """Return the smallest cart quantity that can satisfy every listing floor."""
    return max(1, min_steps, moq)


def is_listing_available(
    stock_mode: str,
    stock_qty: int | None,
    *,
    min_steps: int = 1,
    moq: int = 1,
    product_class: str = "A",
    fulfilment_mode: str = "stocked",
    vendor_capacity_per_week: int | None = None,
) -> bool:
    """Whether at least one valid minimum purchase can currently be offered.

    Browse endpoints do not reserve stock or made-to-order capacity. Checkout
    still performs the authoritative branch-stock and current-week capacity
    checks; this helper prevents a listing from being advertised as available
    when even its configured gross quantity cannot satisfy its own minimum.
    """
    minimum_qty = minimum_purchase_qty(min_steps=min_steps, moq=moq)
    if product_class == "E":
        return (
            isinstance(vendor_capacity_per_week, int)
            and vendor_capacity_per_week >= minimum_qty
        )
    # Migration 0085 predates product classes and allowed made-to-order offers
    # with lead time but no weekly capacity. Preserve those legacy listings;
    # the stricter capacity contract belongs to explicit Class E offers.
    if fulfilment_mode == "made_to_order":
        return True
    if stock_mode == "always_available":
        return True
    if stock_mode == "tracked":
        return isinstance(stock_qty, int) and stock_qty >= minimum_qty
    return False
