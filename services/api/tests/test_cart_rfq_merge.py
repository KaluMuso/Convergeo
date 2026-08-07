"""BATCH 1D — RFQ cart merge continuity tests."""

from __future__ import annotations

from typing import Any

import pytest
from app.services.cart.merge import merge_cart_items

LISTING_RETAIL = "10101010-1010-1010-1010-101010101010"
LISTING_WHOLESALE = "20202020-2020-2020-2020-202020202020"
CUSTOMER_A = "11111111-1111-1111-1111-111111111111"
CUSTOMER_B = "22222222-2222-2222-2222-222222222222"
RFQ_THREAD = "33333333-3333-3333-3333-333333333333"
RFQ_THREAD_B = "44444444-4444-4444-4444-444444444444"
VENDOR_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _retail_listing(price_ngwee: int = 150_000) -> dict[str, Any]:
    return {
        "id": LISTING_RETAIL,
        "vendor_id": VENDOR_A,
        "price_ngwee": price_ngwee,
        "wholesale": False,
        "moq": 1,
        "price_tiers": None,
        "status": "active",
        "title_override": "Retail item",
    }


def _accepted_thread(
    *,
    thread_id: str = RFQ_THREAD,
    customer_id: str = CUSTOMER_A,
    listing_id: str = LISTING_RETAIL,
    quote_price_ngwee: int = 125_000,
    status: str = "accepted",
) -> dict[str, Any]:
    return {
        "id": thread_id,
        "customer_id": customer_id,
        "listing_id": listing_id,
        "status": status,
        "quote_price_ngwee": quote_price_ngwee,
        "quote_valid_until": "2099-01-01T00:00:00+00:00",
    }


def _rfq_line(
    *,
    price: int = 125_000,
    qty: int = 2,
    thread_id: str = RFQ_THREAD,
) -> dict[str, Any]:
    return {
        "listing_id": LISTING_RETAIL,
        "qty": qty,
        "unit_price_ngwee": price,
        "wholesale": False,
        "rfq_thread_id": thread_id,
    }


def _ordinary_line(qty: int = 1, price: int = 150_000) -> dict[str, Any]:
    return {
        "listing_id": LISTING_RETAIL,
        "qty": qty,
        "unit_price_ngwee": price,
        "wholesale": False,
    }


class TestRfqCartMerge:
    def test_rfq_line_survives_login_merge_at_quoted_price(self) -> None:
        merged, conflicts = merge_cart_items(
            user_items=[_rfq_line(price=125_000, qty=2)],
            guest_items=[],
            listings_by_id={LISTING_RETAIL: _retail_listing()},
            customer_id=CUSTOMER_A,
            rfq_threads_by_id={RFQ_THREAD: _accepted_thread()},
        )
        assert conflicts == []
        assert len(merged) == 1
        assert merged[0].unit_price_ngwee == 125_000
        assert merged[0].rfq_thread_id == RFQ_THREAD
        assert merged[0].qty == 2

    def test_merge_never_reprices_rfq_to_listing_price(self) -> None:
        merged, conflicts = merge_cart_items(
            user_items=[_rfq_line(price=125_000)],
            guest_items=[],
            listings_by_id={LISTING_RETAIL: _retail_listing(price_ngwee=200_000)},
            customer_id=CUSTOMER_A,
            rfq_threads_by_id={RFQ_THREAD: _accepted_thread()},
        )
        assert conflicts == []
        assert merged[0].unit_price_ngwee == 125_000

    def test_forged_rfq_id_rejected(self) -> None:
        merged, conflicts = merge_cart_items(
            user_items=[_rfq_line()],
            guest_items=[],
            listings_by_id={LISTING_RETAIL: _retail_listing()},
            customer_id=CUSTOMER_A,
            rfq_threads_by_id={},
        )
        assert merged == []
        assert conflicts[0].code == "rfq.not_found"

    def test_cross_user_rfq_rejected(self) -> None:
        merged, conflicts = merge_cart_items(
            user_items=[_rfq_line()],
            guest_items=[],
            listings_by_id={LISTING_RETAIL: _retail_listing()},
            customer_id=CUSTOMER_B,
            rfq_threads_by_id={RFQ_THREAD: _accepted_thread()},
        )
        assert merged == []
        assert conflicts[0].code == "rfq.not_found"

    def test_rejected_rfq_does_not_survive(self) -> None:
        merged, conflicts = merge_cart_items(
            user_items=[_rfq_line()],
            guest_items=[],
            listings_by_id={LISTING_RETAIL: _retail_listing()},
            customer_id=CUSTOMER_A,
            rfq_threads_by_id={RFQ_THREAD: _accepted_thread(status="rejected")},
        )
        assert merged == []
        assert conflicts[0].code == "rfq.not_accepted"

    def test_listing_mismatch_rejected(self) -> None:
        merged, conflicts = merge_cart_items(
            user_items=[_rfq_line()],
            guest_items=[],
            listings_by_id={LISTING_RETAIL: _retail_listing()},
            customer_id=CUSTOMER_A,
            rfq_threads_by_id={
                RFQ_THREAD: _accepted_thread(listing_id=LISTING_WHOLESALE),
            },
        )
        assert merged == []
        assert conflicts[0].code == "rfq.listing_mismatch"

    def test_ordinary_cart_merge_unchanged(self) -> None:
        merged, conflicts = merge_cart_items(
            user_items=[_ordinary_line(qty=1, price=150_000)],
            guest_items=[_ordinary_line(qty=2, price=140_000)],
            listings_by_id={LISTING_RETAIL: _retail_listing()},
        )
        assert conflicts == []
        assert len(merged) == 1
        assert merged[0].qty == 3
        assert merged[0].unit_price_ngwee == 150_000
        assert merged[0].rfq_thread_id is None

    def test_user_ordinary_guest_rfq_valid_rfq_wins(self) -> None:
        merged, conflicts = merge_cart_items(
            user_items=[_ordinary_line(qty=3)],
            guest_items=[_rfq_line(qty=1, price=125_000)],
            listings_by_id={LISTING_RETAIL: _retail_listing()},
            customer_id=CUSTOMER_A,
            rfq_threads_by_id={RFQ_THREAD: _accepted_thread()},
        )
        assert len(merged) == 1
        assert merged[0].unit_price_ngwee == 125_000
        assert merged[0].qty == 1
        assert merged[0].rfq_thread_id == RFQ_THREAD
        assert any(c.code == "cart.rfq_merge_conflict" for c in conflicts)

    def test_user_rfq_guest_ordinary_valid_rfq_wins(self) -> None:
        merged, conflicts = merge_cart_items(
            user_items=[_rfq_line(qty=2, price=125_000)],
            guest_items=[_ordinary_line(qty=4)],
            listings_by_id={LISTING_RETAIL: _retail_listing()},
            customer_id=CUSTOMER_A,
            rfq_threads_by_id={RFQ_THREAD: _accepted_thread()},
        )
        assert len(merged) == 1
        assert merged[0].unit_price_ngwee == 125_000
        assert merged[0].qty == 2
        assert any(c.code == "cart.rfq_merge_conflict" for c in conflicts)

    def test_same_thread_rfq_lines_sum_qty(self) -> None:
        merged, conflicts = merge_cart_items(
            user_items=[_rfq_line(qty=1, price=125_000)],
            guest_items=[_rfq_line(qty=3, price=125_000)],
            listings_by_id={LISTING_RETAIL: _retail_listing()},
            customer_id=CUSTOMER_A,
            rfq_threads_by_id={RFQ_THREAD: _accepted_thread()},
        )
        assert conflicts == []
        assert merged[0].qty == 4
        assert merged[0].unit_price_ngwee == 125_000

    def test_different_rfq_threads_same_listing_conflict(self) -> None:
        merged, conflicts = merge_cart_items(
            user_items=[_rfq_line(thread_id=RFQ_THREAD, price=125_000)],
            guest_items=[_rfq_line(thread_id=RFQ_THREAD_B, price=130_000)],
            listings_by_id={LISTING_RETAIL: _retail_listing()},
            customer_id=CUSTOMER_A,
            rfq_threads_by_id={
                RFQ_THREAD: _accepted_thread(thread_id=RFQ_THREAD, quote_price_ngwee=125_000),
                RFQ_THREAD_B: _accepted_thread(
                    thread_id=RFQ_THREAD_B,
                    quote_price_ngwee=130_000,
                ),
            },
        )
        assert merged == []
        assert any(c.code == "cart.rfq_merge_conflict" for c in conflicts)

    def test_forged_stored_price_rejected(self) -> None:
        merged, conflicts = merge_cart_items(
            user_items=[_rfq_line(price=99_000)],
            guest_items=[],
            listings_by_id={LISTING_RETAIL: _retail_listing()},
            customer_id=CUSTOMER_A,
            rfq_threads_by_id={RFQ_THREAD: _accepted_thread()},
        )
        assert merged == []
        assert conflicts[0].code == "cart.price_changed"
