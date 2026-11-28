"""Non-blocking listing price review flags (category floors from packages/config)."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.catalog.listing_price_review import (
    REVIEW_FLAG_PRICE_BELOW_CATEGORY_FLOOR,
    category_floor_ngwee,
    listing_price_review_flags,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SHARED_FLOORS_JSON = _REPO_ROOT / "packages/config/src/listing-category-price-floors.json"
_API_FLOORS_JSON = (
    Path(__file__).resolve().parents[1]
    / "app/services/catalog/listing-category-price-floors.json"
)


def test_api_floor_json_matches_typescript_source() -> None:
    shared = json.loads(_SHARED_FLOORS_JSON.read_text(encoding="utf-8"))
    bundled = json.loads(_API_FLOORS_JSON.read_text(encoding="utf-8"))
    assert bundled == shared


def test_phones_floor_is_k300_ngwee() -> None:
    floor = category_floor_ngwee(
        category_path="electronics/mobile-phones",
        title=None,
    )
    assert floor == (30_000, "electronics/mobile-phones")


def test_laptop_title_fallback_when_category_missing() -> None:
    floor = category_floor_ngwee(category_path=None, title="Lenovo ThinkPad T14")
    assert floor == (100_000, "title:laptop")


def test_review_flag_when_below_floor_never_empty_when_above() -> None:
    assert listing_price_review_flags(
        price_ngwee=5_000,
        category_path="electronics/mobile-phones",
        title="Budget phone",
    ) == [REVIEW_FLAG_PRICE_BELOW_CATEGORY_FLOOR]
    assert (
        listing_price_review_flags(
            price_ngwee=30_000,
            category_path="electronics/mobile-phones",
            title="Budget phone",
        )
        == []
    )


def test_unknown_category_has_no_review_flags() -> None:
    assert (
        listing_price_review_flags(
            price_ngwee=100,
            category_path="home/kitchen",
            title="Spatula",
        )
        == []
    )