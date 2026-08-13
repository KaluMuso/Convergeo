from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from app.errors import AppError
from app.main import create_app
from app.services.cart.grouping import FREE_DELIVERY_THRESHOLD_NGEWEE, CartLineView, group_by_vendor
from app.services.cart.merge import merge_cart_items, validate_item_qty_for_listing
from app.services.cart.read_path import prepare_cart_items_for_read
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

    def test_validate_item_qty_enforces_minimum_sale_steps(self) -> None:
        listing = {
            **_retail_listing(),
            "sale_unit": "metre",
            "unit_step_milli": 500,
            "min_steps": 3,
        }
        with pytest.raises(AppError) as exc_info:
            validate_item_qty_for_listing(
                listing=listing,
                qty=2,
                business_eligible=False,
            )
        assert exc_info.value.code == "cart.min_steps_violation"
        assert exc_info.value.details["min_steps"] == 3

    def test_validate_item_qty_allows_minimum_sale_steps(self) -> None:
        listing = {
            **_retail_listing(),
            "sale_unit": "metre",
            "unit_step_milli": 500,
            "min_steps": 3,
        }
        unit_price, wholesale = validate_item_qty_for_listing(
            listing=listing,
            qty=3,
            business_eligible=False,
        )
        assert unit_price == 10_000
        assert wholesale is False


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
    listing alone — a consumer never gets B2B pricing (strategy alignment fix).

    NOTE (D36, 2026-08-02): the retail fallback these tests exercise is now
    **defence in depth, not a live path**. `fetch_listing` refuses a wholesale-only
    listing to a non-eligible caller before pricing is ever reached, so a consumer
    request can no longer arrive here. The fallback is kept deliberately — it is the
    right failure mode if a gate is ever missed — and these tests keep it honest.
    `TestWholesaleOnlyIsOmittedFromTheCart` asserts the gate that now sits in front.
    """

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

    def test_merge_consumer_drops_the_line_instead_of_repricing_it(self) -> None:
        """CHANGED BY D36 (2026-08-02). This test previously asserted the opposite:
        that a non-business merge re-derived the wholesale line down to retail and
        raised no conflict.

        That was the pricing-rule reading of the wholesale flag. D36 makes it an
        access rule — a wholesale-only listing is omitted from consumer surfaces
        entirely — so the line is dropped with a conflict rather than converted
        into a consumer-priced sale of wholesale stock at no MOQ.
        """
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
        assert merged == [], "a wholesale-only line survived a consumer merge"
        assert len(conflicts) == 1
        assert conflicts[0].code == "cart.listing_unavailable"

    def test_merge_conflict_does_not_reveal_that_the_listing_is_wholesale(self) -> None:
        """The conflict must be byte-identical to the one for an id that does not
        exist. A distinct `cart.wholesale_forbidden` would tell the client exactly
        what it was denied, which is the disclosure D36 exists to prevent."""
        wholesale_line = {
            "listing_id": LISTING_WHOLESALE,
            "qty": 3,
            "unit_price_ngwee": 45_000,
            "wholesale": True,
        }
        _, wholesale_conflicts = merge_cart_items(
            user_items=[],
            guest_items=[wholesale_line],
            listings_by_id={LISTING_WHOLESALE: _wholesale_listing()},
            business_eligible=False,
        )
        # Same id, but the listing is simply absent from the lookup.
        _, absent_conflicts = merge_cart_items(
            user_items=[],
            guest_items=[wholesale_line],
            listings_by_id={},
            business_eligible=False,
        )
        assert wholesale_conflicts[0].code == absent_conflicts[0].code
        assert wholesale_conflicts[0].message_key == absent_conflicts[0].message_key
        assert wholesale_conflicts[0].details == absent_conflicts[0].details

    def test_verified_business_still_merges_the_wholesale_line(self) -> None:
        """The omission is scoped to non-eligible callers — D36 must not break B2B."""
        merged, conflicts = merge_cart_items(
            user_items=[],
            guest_items=[
                {
                    "listing_id": LISTING_WHOLESALE,
                    "qty": 60,
                    "unit_price_ngwee": 40_000,
                    "wholesale": True,
                }
            ],
            listings_by_id={LISTING_WHOLESALE: _wholesale_listing()},
            business_eligible=True,
        )
        assert conflicts == []
        assert len(merged) == 1
        assert merged[0].wholesale is True
        assert merged[0].unit_price_ngwee == 40_000


class TestSuspendedBusinessLosesWholesalePricing:
    """R02-P06: suspension must take effect on a cart that was priced while the
    buyer was still verified.

    This is the money-shaped failure path. The line was legitimately stored at a
    tier price; the buyer is then suspended. Because eligibility is re-resolved
    per request and the flag is re-derived from listing AND eligibility — never
    read back off the stored line — the cart must fall to retail on the very
    next touch. Nothing had asserted it: `suspended` appeared nowhere in the
    cart or access tests.
    """

    def test_stale_wholesale_line_is_dropped_when_suspended(self) -> None:
        """CHANGED BY D36 (2026-08-02). Previously asserted the line re-priced to
        retail (50_000). Under D36 the suspended buyer loses *access*, not just the
        discount, so the line is dropped with a conflict.

        The property that actually mattered is unchanged and still asserted: the
        stored line is never trusted. A suspended buyer must not keep the 40_000
        tier price they were legitimately given while verified.
        """
        stored_line = {
            "listing_id": LISTING_WHOLESALE,
            "qty": 60,
            "unit_price_ngwee": 40_000,
            "wholesale": True,
        }

        merged, conflicts = merge_cart_items(
            user_items=[stored_line],
            guest_items=[],
            listings_by_id={LISTING_WHOLESALE: _wholesale_listing()},
            business_eligible=False,  # suspension resolved for this request
        )

        assert merged == [], "a suspended buyer kept a wholesale line"
        assert [c.code for c in conflicts] == ["cart.listing_unavailable"]

    def test_suspended_buyer_is_not_blocked_by_the_wholesale_moq(self) -> None:
        """Losing eligibility must not strand the buyer: MOQ is a B2B rule, so
        it stops applying at the same moment tier pricing does. A suspended
        buyer holding 3 units must be able to check out at retail, not be told
        their cart violates a minimum they can no longer benefit from."""
        unit_price, wholesale = validate_item_qty_for_listing(
            listing=_wholesale_listing(), qty=3, business_eligible=False
        )
        assert wholesale is False
        assert unit_price == 50_000

    def test_price_is_integer_ngwee_on_the_downgrade_path(self) -> None:
        unit_price, _ = validate_item_qty_for_listing(
            listing=_wholesale_listing(), qty=60, business_eligible=False
        )
        assert isinstance(unit_price, int)


class TestWholesaleOnlyIsOmittedFromTheCart:
    """R02-P05b / B2B audit G8 — the live defect this class closes.

    Before this, `fetch_listing` filtered on `status == 'active'` and nothing else.
    A consumer who obtained a wholesale-only listing id could `POST /cart/items`
    with qty=1 and have it accepted at the base retail price with no MOQ: the
    listing that was supposed to be invisible became an order, and wholesale stock
    was sold at consumer prices.
    """

    @staticmethod
    def _store_returning(row: dict[str, Any] | None) -> Any:
        """Fake the service-role client chain `fetch_listing` walks."""

        class FakeQuery:
            def select(self, *_a: Any, **_k: Any) -> FakeQuery:
                return self

            def eq(self, *_a: Any, **_k: Any) -> FakeQuery:
                return self

            def limit(self, *_a: Any, **_k: Any) -> FakeQuery:
                return self

            def execute(self) -> MagicMock:
                return MagicMock(data=[row] if row is not None else [])

        service = MagicMock()
        service.client.table.return_value = FakeQuery()
        return service

    def _fetch(
        self,
        monkeypatch: pytest.MonkeyPatch,
        row: dict[str, Any] | None,
        *,
        business_eligible: bool,
    ) -> dict[str, Any]:
        from app.services.cart import store

        monkeypatch.setattr(store, "get_service_client", lambda: self._store_returning(row))
        return store.fetch_listing(LISTING_WHOLESALE, business_eligible=business_eligible)

    def test_consumer_cannot_fetch_a_wholesale_only_listing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        with pytest.raises(AppError) as excinfo:
            self._fetch(monkeypatch, _wholesale_listing(), business_eligible=False)
        assert excinfo.value.http_status == 404

    def test_404_is_indistinguishable_from_a_listing_that_never_existed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The whole point of D36's 404-over-403 choice.

        A 403 would confirm the id names a real listing, letting anyone who can
        enumerate ids map the B2B catalogue — its size, its vendors, and by
        inference its pricing — without ever qualifying as a buyer. Asserting
        merely "not 200" would pass a 403 and miss exactly that.
        """
        with pytest.raises(AppError) as wholesale:
            self._fetch(monkeypatch, _wholesale_listing(), business_eligible=False)
        with pytest.raises(AppError) as absent:
            self._fetch(monkeypatch, None, business_eligible=False)

        assert wholesale.value.code == absent.value.code
        assert wholesale.value.http_status == absent.value.http_status
        assert wholesale.value.message == absent.value.message
        assert wholesale.value.details == absent.value.details

    def test_an_inactive_wholesale_listing_is_also_indistinguishable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The wholesale check runs before the status check on purpose. If it ran
        after, an inactive wholesale listing would answer `cart.listing_inactive`
        while an inactive retail one answered the same — but a *draft* wholesale
        listing would still be distinguishable from an absent id, reopening the
        oracle through a side door."""
        draft = {**_wholesale_listing(), "status": "draft"}
        with pytest.raises(AppError) as excinfo:
            self._fetch(monkeypatch, draft, business_eligible=False)
        assert excinfo.value.code == "cart.listing_not_found"
        assert excinfo.value.http_status == 404

    def test_verified_business_fetches_it_normally(self, monkeypatch: pytest.MonkeyPatch) -> None:
        listing = self._fetch(monkeypatch, _wholesale_listing(), business_eligible=True)
        assert listing["id"] == LISTING_WHOLESALE
        assert listing["wholesale"] is True

    def test_retail_listing_is_unaffected_for_a_consumer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services.cart import store

        monkeypatch.setattr(
            store, "get_service_client", lambda: self._store_returning(_retail_listing())
        )
        listing = store.fetch_listing(LISTING_RETAIL, business_eligible=False)
        assert listing["id"] == LISTING_RETAIL

    def test_eligibility_defaults_to_the_safe_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A caller that forgets the keyword must get the stricter behaviour. The
        leakier default would fail open, and silently."""
        from app.services.cart import store

        monkeypatch.setattr(
            store, "get_service_client", lambda: self._store_returning(_wholesale_listing())
        )
        with pytest.raises(AppError) as excinfo:
            store.fetch_listing(LISTING_WHOLESALE)
        assert excinfo.value.http_status == 404


class TestCartReadPathWholesaleVisibility:
    """BATCH 1B — GET /cart must re-derive wholesale access (CAN-CAT-003).

    Closes the gap where a retail line that later became wholesale-only still
    appeared in cart responses with stale tier pricing until checkout blocked it.
    """

    @staticmethod
    def _stored_line(
        *,
        listing_id: str = LISTING_WHOLESALE,
        qty: int = 60,
        price: int = 40_000,
        wholesale: bool = True,
        rfq_thread_id: str | None = None,
    ) -> dict[str, Any]:
        line: dict[str, Any] = {
            "id": "line-1",
            "listing_id": listing_id,
            "qty": qty,
            "unit_price_ngwee": price,
            "wholesale": wholesale,
        }
        if rfq_thread_id is not None:
            line["rfq_thread_id"] = rfq_thread_id
        return line

    def test_retail_user_stale_wholesale_line_is_omitted_with_generic_conflict(self) -> None:
        """Listing transitioned retail → wholesale after cart insert."""
        prepared = prepare_cart_items_for_read(
            [self._stored_line()],
            {LISTING_WHOLESALE: _wholesale_listing()},
            business_eligible=False,
        )
        assert prepared.items == []
        assert len(prepared.conflicts) == 1
        assert prepared.conflicts[0].code == "cart.listing_unavailable"

    def test_wholesale_conflict_is_indistinguishable_from_absent_listing(self) -> None:
        line = self._stored_line()
        wholesale_prep = prepare_cart_items_for_read(
            [line],
            {LISTING_WHOLESALE: _wholesale_listing()},
            business_eligible=False,
        )
        absent_prep = prepare_cart_items_for_read([line], {}, business_eligible=False)
        assert wholesale_prep.conflicts[0].code == absent_prep.conflicts[0].code
        assert wholesale_prep.conflicts[0].message_key == absent_prep.conflicts[0].message_key
        assert wholesale_prep.conflicts[0].details == absent_prep.conflicts[0].details

    def test_verified_business_still_sees_wholesale_line_with_derived_tier(self) -> None:
        prepared = prepare_cart_items_for_read(
            [self._stored_line()],
            {LISTING_WHOLESALE: _wholesale_listing()},
            business_eligible=True,
        )
        assert len(prepared.items) == 1
        assert prepared.conflicts == []
        assert prepared.items[0]["unit_price_ngwee"] == 40_000
        assert prepared.items[0]["wholesale"] is True

    def test_guest_cannot_see_wholesale_only_line(self) -> None:
        prepared = prepare_cart_items_for_read(
            [self._stored_line()],
            {LISTING_WHOLESALE: _wholesale_listing()},
            business_eligible=False,
        )
        assert prepared.items == []

    def test_retail_cart_line_unaffected_when_listing_stays_retail(self) -> None:
        retail_line = {
            "id": "line-retail",
            "listing_id": LISTING_RETAIL,
            "qty": 2,
            "unit_price_ngwee": 10_000,
            "wholesale": False,
        }
        prepared = prepare_cart_items_for_read(
            [retail_line],
            {LISTING_RETAIL: _retail_listing()},
            business_eligible=False,
        )
        assert len(prepared.items) == 1
        assert prepared.items[0]["unit_price_ngwee"] == 10_000
        assert prepared.conflicts == []

    def test_stale_tier_price_is_rederived_on_read_for_eligible_buyer(self) -> None:
        """Stored 50-unit tier price with qty 20 must present the 10-unit tier."""
        prepared = prepare_cart_items_for_read(
            [self._stored_line(qty=20, price=40_000)],
            {LISTING_WHOLESALE: _wholesale_listing()},
            business_eligible=True,
        )
        assert len(prepared.items) == 1
        assert prepared.items[0]["unit_price_ngwee"] == 45_000
        assert prepared.items[0]["wholesale"] is True

    def test_rfq_pinned_line_keeps_quote_price_and_survives_wholesale_transition(self) -> None:
        rfq_line = self._stored_line(
            qty=5,
            price=33_000,
            wholesale=False,
            rfq_thread_id="rfq-thread-1",
        )
        prepared = prepare_cart_items_for_read(
            [rfq_line],
            {LISTING_WHOLESALE: _wholesale_listing()},
            business_eligible=False,
        )
        assert prepared.conflicts == []
        assert len(prepared.items) == 1
        assert prepared.items[0]["unit_price_ngwee"] == 33_000
        assert prepared.items[0]["wholesale"] is False

    def test_response_does_not_expose_wholesale_title_for_blocked_line(self) -> None:
        """Blocked lines never reach _build_cart_response item list."""
        from app.routers.cart import _cart_response

        cart = _cart_response(
            cart_id="cart-1",
            items=[self._stored_line()],
            listings_by_id={LISTING_WHOLESALE: _wholesale_listing()},
            business_eligible=False,
        )
        assert cart.items == []
        assert cart.subtotal_ngwee == 0
        assert cart.conflicts[0].code == "cart.listing_unavailable"


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

    def test_cart_response_includes_sale_increment_metadata(self) -> None:
        from app.routers.cart import _build_cart_response

        listing = {
            **_retail_listing(),
            "product_class": "C",
            "condition": "used",
            "sale_unit": "kg",
            "unit_step_milli": 250,
            "min_steps": 4,
            "fulfilment_mode": "stocked",
            "defect_notes": "Surface marks visible on the package",
        }
        response = _build_cart_response(
            cart_id="cart-1",
            items=[
                {
                    "id": "line-1",
                    "listing_id": LISTING_RETAIL,
                    "qty": 4,
                    "unit_price_ngwee": 10_000,
                    "wholesale": False,
                }
            ],
            listings_by_id={LISTING_RETAIL: listing},
        )

        line = response.items[0]
        assert line.product_class == "C"
        assert line.condition == "used"
        assert line.sale_unit == "kg"
        assert line.unit_step_milli == 250
        assert line.min_steps == 4
        assert line.defect_notes == "Surface marks visible on the package"


class TestCartAuthz:
    def test_user_a_cannot_read_user_b_cart_via_service_filter(
        self,
        monkeypatch: pytest.MonkeyPatch,
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
                    return MagicMock(data=[{"id": "cart-a", "user_id": USER_A, "status": "active"}])
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
