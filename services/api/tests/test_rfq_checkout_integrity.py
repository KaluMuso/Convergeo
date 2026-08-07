"""BATCH 1C — RFQ accepted-quote checkout integrity tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from app.errors import AppError
from app.routers.checkout import _rederive_line_prices
from app.services.cart.read_path import prepare_cart_items_for_read
from app.services.rfq.listing_cart_authority import (
    validate_rfq_pinned_line_authority,
)

LISTING = "20202020-2020-2020-2020-202020202020"
LISTING_RETAIL = "10101010-1010-1010-1010-101010101010"
CUSTOMER_A = "11111111-1111-1111-1111-111111111111"
CUSTOMER_B = "22222222-2222-2222-2222-222222222222"
RFQ_THREAD = "33333333-3333-3333-3333-333333333333"
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


def _wholesale_listing() -> dict[str, Any]:
    return {
        "id": LISTING,
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


def _accepted_thread(
    *,
    customer_id: str = CUSTOMER_A,
    listing_id: str = LISTING_RETAIL,
    quote_price_ngwee: int = 125_000,
    status: str = "accepted",
) -> dict[str, Any]:
    return {
        "id": RFQ_THREAD,
        "customer_id": customer_id,
        "listing_id": listing_id,
        "status": status,
        "quote_price_ngwee": quote_price_ngwee,
        "quote_valid_until": "2099-01-01T00:00:00+00:00",
    }


def _rfq_line(
    *,
    price: int = 125_000,
    listing_id: str = LISTING_RETAIL,
    qty: int = 1,
) -> dict[str, Any]:
    return {
        "id": "line-1",
        "listing_id": listing_id,
        "qty": qty,
        "unit_price_ngwee": price,
        "wholesale": False,
        "rfq_thread_id": RFQ_THREAD,
    }


def _service_with_rfq_threads(threads: list[dict[str, Any]]) -> MagicMock:
    service = MagicMock()
    cart_update = service.client.table.return_value.update.return_value
    cart_update.eq.return_value.execute.return_value = MagicMock(data=[])

    rfq_table = MagicMock()
    rfq_table.select.return_value.in_.return_value.execute.return_value = MagicMock(
        data=threads
    )

    def table_router(name: str) -> MagicMock:
        if name == "rfq_threads":
            return rfq_table
        return MagicMock()

    service.client.table.side_effect = table_router
    return service


class TestRfqPinnedAuthority:
    def test_valid_accepted_quote_authorizes(self) -> None:
        authority, code, _ = validate_rfq_pinned_line_authority(
            rfq_thread_id=RFQ_THREAD,
            customer_id=CUSTOMER_A,
            listing_id=LISTING_RETAIL,
            stored_unit_price_ngwee=125_000,
            thread=_accepted_thread(),
        )
        assert code is None
        assert authority is not None
        assert authority.quote_price_ngwee == 125_000

    def test_wrong_customer_rejected(self) -> None:
        _, code, _ = validate_rfq_pinned_line_authority(
            rfq_thread_id=RFQ_THREAD,
            customer_id=CUSTOMER_B,
            listing_id=LISTING_RETAIL,
            stored_unit_price_ngwee=125_000,
            thread=_accepted_thread(),
        )
        assert code == "rfq.not_found"

    def test_listing_mismatch_rejected(self) -> None:
        _, code, _ = validate_rfq_pinned_line_authority(
            rfq_thread_id=RFQ_THREAD,
            customer_id=CUSTOMER_A,
            listing_id=LISTING,
            stored_unit_price_ngwee=125_000,
            thread=_accepted_thread(),
        )
        assert code == "rfq.listing_mismatch"

    def test_rejected_status_blocked(self) -> None:
        _, code, _ = validate_rfq_pinned_line_authority(
            rfq_thread_id=RFQ_THREAD,
            customer_id=CUSTOMER_A,
            listing_id=LISTING_RETAIL,
            stored_unit_price_ngwee=125_000,
            thread=_accepted_thread(status="rejected"),
        )
        assert code == "rfq.not_accepted"

    def test_forged_stored_price_rejected(self) -> None:
        _, code, details = validate_rfq_pinned_line_authority(
            rfq_thread_id=RFQ_THREAD,
            customer_id=CUSTOMER_A,
            listing_id=LISTING_RETAIL,
            stored_unit_price_ngwee=99_000,
            thread=_accepted_thread(),
        )
        assert code == "cart.price_changed"
        assert details["current_unit_price_ngwee"] == 125_000


class TestCheckoutRfqPinnedLines:
    def test_accepted_rfq_quote_passes_when_listing_price_differs(self) -> None:
        """Listing K1500, accepted RFQ K1250 → checkout K1250."""
        service = _service_with_rfq_threads([_accepted_thread(quote_price_ngwee=125_000)])
        items = [_rfq_line(price=125_000)]
        result = _rederive_line_prices(
            items,
            {LISTING_RETAIL: _retail_listing(price_ngwee=150_000)},
            business_eligible=False,
            service=service,
            customer_id=CUSTOMER_A,
        )
        assert result == items
        assert result[0]["unit_price_ngwee"] == 125_000

    def test_listing_price_change_after_accept_does_not_block_rfq_line(self) -> None:
        service = _service_with_rfq_threads([_accepted_thread(quote_price_ngwee=125_000)])
        items = [_rfq_line(price=125_000)]
        result = _rederive_line_prices(
            items,
            {LISTING_RETAIL: _retail_listing(price_ngwee=200_000)},
            business_eligible=False,
            service=service,
            customer_id=CUSTOMER_A,
        )
        assert result[0]["unit_price_ngwee"] == 125_000

    def test_other_customer_rfq_blocked(self) -> None:
        service = _service_with_rfq_threads([_accepted_thread()])
        with pytest.raises(AppError) as excinfo:
            _rederive_line_prices(
                [_rfq_line()],
                {LISTING_RETAIL: _retail_listing()},
                business_eligible=False,
                service=service,
                customer_id=CUSTOMER_B,
            )
        assert excinfo.value.code == "checkout.cart_changed"
        assert excinfo.value.details["conflicts"][0]["code"] == "rfq.not_found"

    def test_listing_mismatch_blocked(self) -> None:
        service = _service_with_rfq_threads([_accepted_thread()])
        with pytest.raises(AppError) as excinfo:
            _rederive_line_prices(
                [_rfq_line(listing_id=LISTING)],
                {LISTING: _wholesale_listing()},
                business_eligible=False,
                service=service,
                customer_id=CUSTOMER_A,
            )
        assert excinfo.value.details["conflicts"][0]["code"] == "rfq.listing_mismatch"

    def test_rejected_rfq_blocked(self) -> None:
        service = _service_with_rfq_threads([_accepted_thread(status="rejected")])
        with pytest.raises(AppError) as excinfo:
            _rederive_line_prices(
                [_rfq_line()],
                {LISTING_RETAIL: _retail_listing()},
                business_eligible=False,
                service=service,
                customer_id=CUSTOMER_A,
            )
        assert excinfo.value.details["conflicts"][0]["code"] == "rfq.not_accepted"

    def test_inactive_listing_blocked(self) -> None:
        inactive = _retail_listing()
        inactive["status"] = "inactive"
        service = _service_with_rfq_threads([_accepted_thread()])
        with pytest.raises(AppError) as excinfo:
            _rederive_line_prices(
                [_rfq_line()],
                {LISTING_RETAIL: inactive},
                business_eligible=False,
                service=service,
                customer_id=CUSTOMER_A,
            )
        assert excinfo.value.details["conflicts"][0]["code"] == "cart.listing_unavailable"

    def test_missing_listing_blocked(self) -> None:
        service = _service_with_rfq_threads([_accepted_thread()])
        with pytest.raises(AppError) as excinfo:
            _rederive_line_prices(
                [_rfq_line()],
                {},
                business_eligible=False,
                service=service,
                customer_id=CUSTOMER_A,
            )
        assert excinfo.value.details["conflicts"][0]["code"] == "cart.listing_unavailable"

    def test_normal_retail_line_still_rederives(self) -> None:
        service = _service_with_rfq_threads([])
        line = {
            "id": "line-retail",
            "listing_id": LISTING_RETAIL,
            "qty": 2,
            "unit_price_ngwee": 10_000,
            "wholesale": False,
        }
        with pytest.raises(AppError) as excinfo:
            _rederive_line_prices(
                [line],
                {LISTING_RETAIL: _retail_listing(price_ngwee=150_000)},
                business_eligible=False,
                service=service,
                customer_id=CUSTOMER_A,
            )
        assert excinfo.value.details["conflicts"][0]["code"] == "cart.price_changed"

    def test_wholesale_line_still_rederives_tier(self) -> None:
        service = _service_with_rfq_threads([])
        line = {
            "id": "line-wholesale",
            "listing_id": LISTING,
            "qty": 60,
            "unit_price_ngwee": 40_000,
            "wholesale": True,
        }
        result = _rederive_line_prices(
            [line],
            {LISTING: _wholesale_listing()},
            business_eligible=True,
            service=service,
            customer_id=CUSTOMER_A,
        )
        assert result[0]["unit_price_ngwee"] == 40_000

    def test_rfq_pinned_wholesale_listing_survives_consumer_eligibility(self) -> None:
        """Accepted RFQ bypasses D36 wholesale omission at checkout."""
        service = _service_with_rfq_threads(
            [_accepted_thread(listing_id=LISTING, quote_price_ngwee=33_000)]
        )
        items = [
            {
                "id": "line-rfq-wholesale",
                "listing_id": LISTING,
                "qty": 5,
                "unit_price_ngwee": 33_000,
                "wholesale": False,
                "rfq_thread_id": RFQ_THREAD,
            }
        ]
        result = _rederive_line_prices(
            items,
            {LISTING: _wholesale_listing()},
            business_eligible=False,
            service=service,
            customer_id=CUSTOMER_A,
        )
        assert result[0]["unit_price_ngwee"] == 33_000


class TestCartReadRfqValidation:
    def test_inactive_listing_on_rfq_line_conflicts(self) -> None:
        inactive = _retail_listing()
        inactive["status"] = "inactive"
        prepared = prepare_cart_items_for_read(
            [_rfq_line()],
            {LISTING_RETAIL: inactive},
            business_eligible=False,
            customer_id=CUSTOMER_A,
            rfq_threads_by_id={RFQ_THREAD: _accepted_thread()},
        )
        assert prepared.items == []
        assert prepared.conflicts[0].code == "cart.listing_inactive"

    def test_rejected_rfq_thread_conflicts_on_read(self) -> None:
        prepared = prepare_cart_items_for_read(
            [_rfq_line()],
            {LISTING_RETAIL: _retail_listing()},
            business_eligible=False,
            customer_id=CUSTOMER_A,
            rfq_threads_by_id={RFQ_THREAD: _accepted_thread(status="rejected")},
        )
        assert prepared.items == []
        assert prepared.conflicts[0].code == "rfq.not_accepted"

    def test_wholesale_listing_still_hidden_without_rfq_pin(self) -> None:
        """CAN-CAT-003 regression: non-RFQ wholesale lines stay omitted."""
        line = {
            "id": "line-1",
            "listing_id": LISTING,
            "qty": 60,
            "unit_price_ngwee": 40_000,
            "wholesale": True,
        }
        prepared = prepare_cart_items_for_read(
            [line],
            {LISTING: _wholesale_listing()},
            business_eligible=False,
            customer_id=CUSTOMER_A,
            rfq_threads_by_id={},
        )
        assert prepared.items == []
        assert prepared.conflicts[0].code == "cart.listing_unavailable"
