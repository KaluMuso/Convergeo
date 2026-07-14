from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from app.errors import AppError
from app.main import create_app
from app.services.cart.grouping import FREE_DELIVERY_THRESHOLD_NGEWEE, CartLineView, group_by_vendor
from app.services.cart.merge import merge_cart_items, validate_item_qty_for_listing
from app.services.cart.totals import (
    cart_subtotal_ngwee,
    select_unit_price_ngwee,
    validate_moq,
)
from fastapi.testclient import TestClient

USER_A = "11111111-1111-1111-1111-111111111111"
USER_B = "22222222-2222-2222-2222-222222222222"
LISTING_RETAIL = "10101010-1010-1010-1010-101010101010"
LISTING_WHOLESALE = "20202020-2020-2020-2020-202020202020"
VENDOR_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _retail_listing() -> dict[str, Any]:
    return {
        "id": LISTING_RETAIL,
        "vendor_id": VENDOR_A,
        "price_ngwee": 10_000,
        "wholesale": False,
        "moq": 1,
        "price_tiers": None,
        "status": "active",
        "title_override": "Retail item",
    }


def _wholesale_listing() -> dict[str, Any]:
    return {
        "id": LISTING_WHOLESALE,
        "vendor_id": VENDOR_A,
        "price_ngwee": 50_000,
        "wholesale": True,
        "moq": 10,
        "price_tiers": [
            {"min_qty": 10, "price_ngwee": 45_000},
            {"min_qty": 50, "price_ngwee": 40_000},
        ],
        "status": "active",
        "title_override": "Wholesale item",
    }


class TestTierPricing:
    def test_retail_uses_base_price(self) -> None:
        price = select_unit_price_ngwee(
            base_price_ngwee=10_000,
            wholesale=False,
            qty=5,
            price_tiers=[{"min_qty": 10, "price_ngwee": 8_000}],
        )
        assert price == 10_000

    def test_wholesale_picks_highest_applicable_tier(self) -> None:
        tiers = [
            {"min_qty": 10, "price_ngwee": 45_000},
            {"min_qty": 50, "price_ngwee": 40_000},
        ]
        assert (
            select_unit_price_ngwee(
                base_price_ngwee=50_000,
                wholesale=True,
                qty=10,
                price_tiers=tiers,
            )
            == 45_000
        )
        assert (
            select_unit_price_ngwee(
                base_price_ngwee=50_000,
                wholesale=True,
                qty=55,
                price_tiers=tiers,
            )
            == 40_000
        )


class TestMoq:
    def test_moq_boundary_allows_at_moq(self) -> None:
        validate_moq(wholesale=True, moq=10, qty=10)

    def test_moq_boundary_rejects_below_moq(self) -> None:
        with pytest.raises(AppError) as exc_info:
            validate_moq(wholesale=True, moq=10, qty=9)
        err = exc_info.value
        assert err.code == "cart.moq_violation"
        assert err.details["retry"] is True
        assert err.details["moq"] == 10

    def test_validate_item_qty_for_listing_raises_on_moq(self) -> None:
        with pytest.raises(AppError) as exc_info:
            validate_item_qty_for_listing(
                listing=_wholesale_listing(), qty=5, business_eligible=True
            )
        assert exc_info.value.code == "cart.moq_violation"


class TestMergeMatrix:
    def test_guest_only_items_preserved(self) -> None:
        listing = _retail_listing()
        merged, conflicts = merge_cart_items(
            user_items=[],
            guest_items=[
                {
                    "listing_id": LISTING_RETAIL,
                    "qty": 2,
                    "unit_price_ngwee": 9_000,
                    "wholesale": False,
                }
            ],
            listings_by_id={LISTING_RETAIL: listing},
        )
        assert len(conflicts) == 0
        assert len(merged) == 1
        assert merged[0].qty == 2
        assert merged[0].unit_price_ngwee == 10_000

    def test_both_carts_merge_with_qty_sum(self) -> None:
        listing = _retail_listing()
        merged, conflicts = merge_cart_items(
            user_items=[
                {
                    "listing_id": LISTING_RETAIL,
                    "qty": 1,
                    "unit_price_ngwee": 10_000,
                    "wholesale": False,
                }
            ],
            guest_items=[
                {
                    "listing_id": LISTING_RETAIL,
                    "qty": 3,
                    "unit_price_ngwee": 9_500,
                    "wholesale": False,
                }
            ],
            listings_by_id={LISTING_RETAIL: listing},
        )
        assert len(conflicts) == 0
        assert len(merged) == 1
        assert merged[0].qty == 4
        assert merged[0].unit_price_ngwee == 10_000

    def test_duplicate_listings_qty_sum_and_price_refresh(self) -> None:
        listing = _wholesale_listing()
        merged, conflicts = merge_cart_items(
            user_items=[
                {
                    "listing_id": LISTING_WHOLESALE,
                    "qty": 10,
                    "unit_price_ngwee": 45_000,
                    "wholesale": True,
                }
            ],
            guest_items=[
                {
                    "listing_id": LISTING_WHOLESALE,
                    "qty": 40,
                    "unit_price_ngwee": 45_000,
                    "wholesale": True,
                }
            ],
            listings_by_id={LISTING_WHOLESALE: listing},
            business_eligible=True,
        )
        assert len(merged) == 1
        assert merged[0].qty == 50
        assert merged[0].unit_price_ngwee == 40_000

    def test_moq_violation_after_merge_surfaces_conflict(self) -> None:
        listing = _wholesale_listing()
        merged, conflicts = merge_cart_items(
            user_items=[
                {
                    "listing_id": LISTING_WHOLESALE,
                    "qty": 4,
                    "unit_price_ngwee": 50_000,
                    "wholesale": True,
                }
            ],
            guest_items=[
                {
                    "listing_id": LISTING_WHOLESALE,
                    "qty": 3,
                    "unit_price_ngwee": 50_000,
                    "wholesale": True,
                }
            ],
            listings_by_id={LISTING_WHOLESALE: listing},
            business_eligible=True,
        )
        assert merged == []
        assert len(conflicts) == 1
        assert conflicts[0].code == "cart.moq_violation"
        assert conflicts[0].details["retry"] is True

    def test_price_change_conflict_surfaced(self) -> None:
        listing = _retail_listing()
        listing_changed = {**listing, "price_ngwee": 12_000}
        merged, conflicts = merge_cart_items(
            user_items=[
                {
                    "listing_id": LISTING_RETAIL,
                    "qty": 1,
                    "unit_price_ngwee": 10_000,
                    "wholesale": False,
                }
            ],
            guest_items=[],
            listings_by_id={LISTING_RETAIL: listing_changed},
        )
        assert len(merged) == 1
        assert merged[0].unit_price_ngwee == 12_000
        assert any(c.code == "cart.price_changed" for c in conflicts)


class TestWholesaleBusinessGating:
    """Wholesale pricing/MOQ must be gated on verified-business eligibility, not the
    listing alone — a consumer never gets B2B pricing (strategy alignment fix)."""

    def test_consumer_forced_to_retail_no_moq(self) -> None:
        # qty below the listing MOQ (10) must NOT raise for a non-business buyer,
        # and the price must be the retail base price (not a wholesale tier).
        unit_price, wholesale = validate_item_qty_for_listing(
            listing=_wholesale_listing(), qty=5, business_eligible=False
        )
        assert wholesale is False
        assert unit_price == 50_000

    def test_consumer_bulk_qty_still_retail(self) -> None:
        # Even at a qty that would unlock a wholesale tier, a consumer pays base.
        unit_price, wholesale = validate_item_qty_for_listing(
            listing=_wholesale_listing(), qty=60, business_eligible=False
        )
        assert wholesale is False
        assert unit_price == 50_000

    def test_business_buyer_gets_wholesale_tier(self) -> None:
        unit_price, wholesale = validate_item_qty_for_listing(
            listing=_wholesale_listing(), qty=60, business_eligible=True
        )
        assert wholesale is True
        assert unit_price == 40_000

    def test_merge_consumer_forces_retail_ignoring_stored_flag(self) -> None:
        # A guest line claims wholesale=True + a wholesale price, but a non-business
        # merge must re-derive to retail (no MOQ conflict, base price).
        merged, conflicts = merge_cart_items(
            user_items=[],
            guest_items=[
                {
                    "listing_id": LISTING_WHOLESALE,
                    "qty": 3,
                    "unit_price_ngwee": 45_000,
                    "wholesale": True,
                }
            ],
            listings_by_id={LISTING_WHOLESALE: _wholesale_listing()},
            business_eligible=False,
        )
        assert conflicts == []
        assert len(merged) == 1
        assert merged[0].wholesale is False
        assert merged[0].unit_price_ngwee == 50_000


class TestGroupingAndTotals:
    def test_group_delivery_eligible_at_threshold(self) -> None:
        line = CartLineView(
            id="line-1",
            listing_id=LISTING_RETAIL,
            vendor_id=VENDOR_A,
            qty=2,
            unit_price_ngwee=FREE_DELIVERY_THRESHOLD_NGEWEE // 2,
            wholesale=False,
            line_total_ngwee=FREE_DELIVERY_THRESHOLD_NGEWEE,
            title_override=None,
        )
        groups = group_by_vendor([line])
        assert len(groups) == 1
        assert groups[0].delivery_eligible is True
        assert groups[0].subtotal_ngwee == FREE_DELIVERY_THRESHOLD_NGEWEE

    def test_cart_subtotal_integer_ngwee(self) -> None:
        assert cart_subtotal_ngwee([(2, 10_000), (3, 5_000)]) == 35_000


class TestCartAuthz:
    def test_user_a_cannot_read_user_b_cart_via_service_filter(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Authz: cart fetch scoped to owner user_id — stranger gets empty result."""

        class FakeQuery:
            def __init__(self, owner_id: str) -> None:
                self._owner_id = owner_id

            def select(self, *_args: Any, **_kwargs: Any) -> FakeQuery:
                return self

            def eq(self, field: str, value: Any) -> FakeQuery:
                if field == "user_id":
                    self._owner_id = str(value)
                return self

            def limit(self, *_args: Any, **_kwargs: Any) -> FakeQuery:
                return self

            def execute(self) -> MagicMock:
                if self._owner_id == USER_A:
                    return MagicMock(
                        data=[{"id": "cart-a", "user_id": USER_A, "status": "active"}]
                    )
                return MagicMock(data=[])

        fake_client = MagicMock()
        fake_client.table.return_value = FakeQuery("")

        from app.routers.cart import _fetch_active_cart_by_user

        cart_a = _fetch_active_cart_by_user(fake_client, USER_A)
        cart_b = _fetch_active_cart_by_user(fake_client, USER_B)
        assert cart_a is not None
        assert cart_b is None

    def test_merge_endpoint_requires_auth(self) -> None:
        with TestClient(create_app(), raise_server_exceptions=False) as client:
            response = client.post("/cart/merge")
        assert response.status_code == 401
        body = response.json()
        assert body["error"]["code"] == "unauthorized"
