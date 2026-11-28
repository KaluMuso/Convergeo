"""Vendor bulk price preview rules."""

from __future__ import annotations

from app.services.listings.bulk_price import (
    SKIP_TIER_PRICING,
    build_bulk_price_rows,
    compute_new_price_ngwee,
)


def test_compute_percent_adjustment_in_ngwee() -> None:
    assert compute_new_price_ngwee(
        old_price_ngwee=10_000,
        adjustment_kind="percent_bps",
        adjustment_value=1_000,
    ) == 11_000


def test_preview_skips_tier_pricing_listings() -> None:
    listing_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    vendor_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    rows = build_bulk_price_rows(
        listing_ids=[listing_id],
        listings_by_id={
            listing_id: {
                "id": listing_id,
                "vendor_id": vendor_id,
                "status": "active",
                "price_ngwee": 25_000,
                "price_tiers": [{"min_qty": 10, "price_ngwee": 20_000}],
                "title_override": "Wholesale widget",
            }
        },
        vendor_id=vendor_id,
        adjustment_kind="delta_ngwee",
        adjustment_value=1_000,
    )
    assert rows[0].skip_reason == SKIP_TIER_PRICING
    assert rows[0].new_price_ngwee is None


def test_preview_adds_floor_warning_without_blocking() -> None:
    listing_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
    vendor_id = "dddddddd-dddd-dddd-dddd-dddddddddddd"
    rows = build_bulk_price_rows(
        listing_ids=[listing_id],
        listings_by_id={
            listing_id: {
                "id": listing_id,
                "vendor_id": vendor_id,
                "status": "active",
                "price_ngwee": 25_000,
                "price_tiers": [],
                "title_override": "Budget phone",
                "products": {"name": "Phone", "category_path": "electronics/mobile-phones"},
            }
        },
        vendor_id=vendor_id,
        adjustment_kind="delta_ngwee",
        adjustment_value=-24_000,
    )
    assert rows[0].applied is True
    assert rows[0].new_price_ngwee == 1_000
    assert "price_below_category_floor" in rows[0].warnings