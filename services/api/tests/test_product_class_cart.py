from __future__ import annotations

from typing import Any

import pytest
from app.errors import AppError
from app.services.cart.merge import validate_item_qty_for_listing
from app.services.listings.class_rules import validate_listing_purchasable_for_cart

LISTING_D_USED = {
    "id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
    "vendor_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    "product_class": "D",
    "condition": "used",
    "price_ngwee": 5_000,
    "wholesale": False,
    "moq": 1,
    "price_tiers": None,
    "status": "active",
    "stock_mode": "tracked",
    "stock_qty": 1,
}

LISTING_E_MTO = {
    "id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
    "vendor_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    "product_class": "E",
    "condition": "new",
    "fulfilment_mode": "made_to_order",
    "lead_time_days": 10,
    "vendor_capacity_per_week": 3,
    "price_ngwee": 80_000,
    "wholesale": False,
    "moq": 1,
    "price_tiers": None,
    "status": "active",
    "stock_mode": "tracked",
    "stock_qty": 0,
}


class TestClassDCartGuard:
    def test_fails_without_evidence_images(self) -> None:
        with pytest.raises(AppError) as exc_info:
            validate_listing_purchasable_for_cart(
                listing=LISTING_D_USED,
                qty=1,
                evidence_image_count=0,
            )
        assert exc_info.value.code == "cart.class_d_missing_evidence"

    def test_fails_when_condition_is_new(self) -> None:
        listing: dict[str, Any] = {**LISTING_D_USED, "condition": "new"}
        with pytest.raises(AppError) as exc_info:
            validate_listing_purchasable_for_cart(
                listing=listing,
                qty=1,
                evidence_image_count=2,
            )
        assert exc_info.value.code == "cart.class_d_invalid_condition"

    def test_passes_with_evidence(self) -> None:
        validate_listing_purchasable_for_cart(
            listing=LISTING_D_USED,
            qty=1,
            evidence_image_count=1,
        )


class TestClassECartGuard:
    def test_bypasses_zero_stock_qty(self) -> None:
        validate_listing_purchasable_for_cart(
            listing=LISTING_E_MTO,
            qty=2,
            evidence_image_count=1,
            weekly_committed_qty=0,
        )
        unit_price, wholesale = validate_item_qty_for_listing(
            listing=LISTING_E_MTO,
            qty=2,
            business_eligible=False,
        )
        assert unit_price == 80_000
        assert wholesale is False

    def test_enforces_weekly_capacity(self) -> None:
        with pytest.raises(AppError) as exc_info:
            validate_listing_purchasable_for_cart(
                listing=LISTING_E_MTO,
                qty=2,
                evidence_image_count=1,
                weekly_committed_qty=2,
            )
        assert exc_info.value.code == "cart.class_e_capacity_exceeded"
        assert exc_info.value.details["remaining"] == 1

    def test_requires_lead_time_days(self) -> None:
        listing: dict[str, Any] = {**LISTING_E_MTO, "lead_time_days": None}
        with pytest.raises(AppError) as exc_info:
            validate_listing_purchasable_for_cart(
                listing=listing,
                qty=1,
                evidence_image_count=0,
            )
        assert exc_info.value.code == "cart.class_e_missing_lead_time"
