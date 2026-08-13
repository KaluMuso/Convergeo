from __future__ import annotations

from typing import Any

import pytest
from app.errors import AppError
from app.services.cart.merge import validate_item_qty_for_listing
from app.services.listings.class_rules import (
    count_weekly_committed_qty,
    validate_listing_purchasable_for_cart,
)

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


def test_legacy_non_class_e_made_to_order_does_not_require_capacity() -> None:
    listing: dict[str, Any] = {
        **LISTING_E_MTO,
        "product_class": "A",
        "vendor_capacity_per_week": None,
    }

    validate_listing_purchasable_for_cart(
        listing=listing,
        qty=2,
        evidence_image_count=0,
    )


class _CommittedQtyQuery:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.selected = ""
        self.filters: list[tuple[str, str, Any]] = []

    def select(self, columns: str) -> _CommittedQtyQuery:
        self.selected = columns
        return self

    def eq(self, column: str, value: Any) -> _CommittedQtyQuery:
        self.filters.append(("eq", column, value))
        return self

    def gte(self, column: str, value: Any) -> _CommittedQtyQuery:
        self.filters.append(("gte", column, value))
        return self

    def execute(self) -> Any:
        return type("Response", (), {"data": self.rows})()


def test_weekly_capacity_reads_listing_link_table_and_excludes_cancelled() -> None:
    rows = [
        {"order_items": {"qty": 2, "orders": {"status": "paid"}}},
        {"order_items": [{"qty": 1, "orders": {"status": "delivered"}}]},
        {"order_items": {"qty": 8, "orders": {"status": "cancelled"}}},
        {"order_items": {"qty": 5, "orders": {"status": "refunded"}}},
    ]
    query = _CommittedQtyQuery(rows)

    class Client:
        def table(self, name: str) -> _CommittedQtyQuery:
            assert name == "order_item_products"
            return query

    total = count_weekly_committed_qty(Client(), LISTING_E_MTO["id"])

    assert total == 3
    assert query.selected == "order_items!inner(qty, orders!inner(status, created_at))"
    assert ("eq", "listing_id", LISTING_E_MTO["id"]) in query.filters
    assert any(
        operation == "gte" and column == "order_items.orders.created_at"
        for operation, column, _value in query.filters
    )
