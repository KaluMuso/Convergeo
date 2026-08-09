"""Regression: staging-synthetic inventory excluded from public consumer discovery."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from app.services.discovery import trending as trending_mod
from app.services.discovery.trending import fetch_trending_listings
from app.services.listings.demo import (
    fetch_demo_listing_ids,
    is_demo_public_id,
    is_non_genuine_public_id,
    is_staging_synthetic_public_id,
)


@pytest.mark.parametrize(
    ("public_id", "expected"),
    [
        ("staging-synthetic/stg-rv-20260719/product-a/hero", True),
        ("vergeo5/staging-synthetic/stg-rv-20260719/product-a/hero", True),
        ("demo/products/itel-a70", True),
        ("vergeo5/catalog/real-phone", False),
        ("listings/vendor-a/photo-1", False),
        (None, False),
        ("", False),
    ],
)
def test_is_non_genuine_public_id(public_id: str | None, expected: bool) -> None:
    assert is_non_genuine_public_id(public_id) is expected


def test_is_staging_synthetic_public_id_does_not_match_real_inventory() -> None:
    assert is_staging_synthetic_public_id("vergeo5/catalog/real-phone") is False
    assert is_staging_synthetic_public_id("demo/products/phone") is False


def test_legacy_demo_public_id_still_excluded() -> None:
    assert is_demo_public_id("demo/products/itel-a70") is True
    assert is_non_genuine_public_id("demo/products/itel-a70") is True


def test_fetch_demo_listing_ids_excludes_synthetic_media() -> None:
    real_id = "11111111-1111-1111-1111-111111111111"
    synthetic_id = "22222222-2222-2222-2222-222222222222"
    demo_id = "33333333-3333-3333-3333-333333333333"

    class _Resp:
        def __init__(self, data: list[dict[str, str]]) -> None:
            self.data = data

    class _Query:
        def __init__(self, data: list[dict[str, str]]) -> None:
            self._data = data

        def select(self, *_a: object, **_k: object) -> _Query:
            return self

        def in_(self, *_a: object, **_k: object) -> _Query:
            return self

        def execute(self) -> _Resp:
            return _Resp(self._data)

    client = MagicMock()
    client.table.return_value = _Query(
        [
            {
                "listing_id": real_id,
                "cloudinary_public_id": "vergeo5/catalog/real-phone",
            },
            {
                "listing_id": synthetic_id,
                "cloudinary_public_id": "staging-synthetic/stg-rv-20260719/product-a/hero",
            },
            {
                "listing_id": demo_id,
                "cloudinary_public_id": "demo/products/legacy",
            },
        ]
    )

    excluded = fetch_demo_listing_ids(client, [real_id, synthetic_id, demo_id])
    assert excluded == {synthetic_id, demo_id}


def test_synthetic_listing_with_high_views_does_not_trend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Synthetic inventory must not trend even when analytics exceed the view floor."""
    real_listing = "11111111-1111-1111-1111-111111111111"
    synthetic_listing = "22222222-2222-2222-2222-222222222222"
    result = MagicMock()
    result.ok = True
    result.rows = [
        f"{real_listing}|Real Phone|real-phone|Tech Shop|15000|vergeo5/catalog/real|42.0",
        f"{synthetic_listing}|Synthetic Gadget|synthetic-gadget|Synth Co|9900|staging-synthetic/stg-rv-20260719/product-a/hero|99.0",
    ]
    monkeypatch.setattr(trending_mod, "run_sql_script", lambda _sql: result)
    monkeypatch.setattr(
        trending_mod,
        "fetch_demo_listing_ids",
        lambda _c, ids: fetch_demo_listing_ids(_make_listing_images_client(), ids),
    )

    items = fetch_trending_listings(_make_listing_images_client(), limit=8)
    assert len(items) == 1
    assert items[0].listing_id == real_listing


def _make_listing_images_client() -> MagicMock:
    real_listing = "11111111-1111-1111-1111-111111111111"
    synthetic_listing = "22222222-2222-2222-2222-222222222222"

    class _Resp:
        def __init__(self, data: list[dict[str, str]]) -> None:
            self.data = data

    class _Query:
        def __init__(self) -> None:
            self._ids: list[str] = []

        def select(self, *_a: object, **_k: object) -> _Query:
            return self

        def in_(self, _col: str, ids: list[str]) -> _Query:
            self._ids = ids
            return self

        def execute(self) -> _Resp:
            rows = []
            for listing_id in self._ids:
                if listing_id == synthetic_listing:
                    rows.append(
                        {
                            "listing_id": listing_id,
                            "cloudinary_public_id": "staging-synthetic/stg-rv-20260719/product-a/hero",
                        }
                    )
                elif listing_id == real_listing:
                    rows.append(
                        {
                            "listing_id": listing_id,
                            "cloudinary_public_id": "vergeo5/catalog/real-phone",
                        }
                    )
            return _Resp(rows)

    client = MagicMock()
    client.table.return_value = _Query()
    return client
