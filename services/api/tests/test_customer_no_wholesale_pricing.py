"""Wholesale and tier prices exist only in the vendor app (founder decision).

Money path: whatever a buyer's business status, customer carts and checkout are
priced at retail; wholesale listings are rejected, never discounted.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from app.errors import AppError
from app.routers import cart as cart_router
from app.routers.checkout import _rederive_line_prices
from app.services.cart.merge import merge_cart_items
from app.services.cart.totals import select_unit_price_ngwee

LISTING = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
VENDOR = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
CUSTOMER = "11111111-1111-1111-1111-111111111111"


def _wholesale_listing() -> dict[str, Any]:
    return {
        "id": LISTING,
        "vendor_id": VENDOR,
        "price_ngwee": 50_000,
        "wholesale": True,
        "moq": 10,
        "price_tiers": [{"min_qty": 50, "price_ngwee": 40_000}],
        "status": "active",
    }


def test_cart_never_treats_a_verified_business_as_eligible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _no_db() -> Any:
        raise AssertionError("business status must not be consulted for customer pricing")

    monkeypatch.setattr(cart_router, "service_db_client", _no_db)
    assert cart_router._business_eligible_for_user(CUSTOMER) is False
    assert cart_router._business_eligible_for_user(None) is False


def test_checkout_blocks_wholesale_line_for_a_business_buyer_instead_of_discounting() -> None:
    service = MagicMock()
    stored = {
        "id": "item-1",
        "listing_id": LISTING,
        "qty": 60,
        "unit_price_ngwee": 40_000,
        "wholesale": True,
    }
    with pytest.raises(AppError) as excinfo:
        # The checkout/orders entry points always pass business_eligible=False.
        _rederive_line_prices(
            [stored],
            {LISTING: _wholesale_listing()},
            business_eligible=cart_router._business_eligible_for_user(CUSTOMER),
            service=service,
            customer_id=CUSTOMER,
        )
    assert excinfo.value.http_status == 409
    assert excinfo.value.details["conflicts"][0]["code"] == "cart.listing_unavailable"
    service.client.table.assert_not_called()


def test_tier_price_only_applies_to_wholesale_lines_never_retail() -> None:
    tiers = [{"min_qty": 5, "price_ngwee": 1}]
    assert (
        select_unit_price_ngwee(base_price_ngwee=50_000, wholesale=False, qty=99, price_tiers=tiers)
        == 50_000
    )


def test_merge_never_prices_wholesale_listing_for_a_customer_cart() -> None:
    _, conflicts = merge_cart_items(
        user_items=[],
        guest_items=[
            {"id": "g1", "listing_id": LISTING, "qty": 60, "unit_price_ngwee": 40_000}
        ],
        listings_by_id={LISTING: _wholesale_listing()},
        business_eligible=cart_router._business_eligible_for_user(CUSTOMER),
        customer_id=CUSTOMER,
    )
    assert [c.code for c in conflicts] == ["cart.listing_unavailable"]
