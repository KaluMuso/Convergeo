"""Integrity tests for deterministic trending discovery."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from app.services.discovery import trending as trending_mod
from app.services.discovery.trending import (
    MIN_UNIQUE_VIEWS,
    WINDOW_DAYS,
    fetch_trending_listings,
)


def test_trending_sql_requires_raised_unique_view_floor() -> None:
    sql = trending_mod._trending_sql(
        min_unique_views=MIN_UNIQUE_VIEWS,
        window_days=WINDOW_DAYS,
        decay=0.85,
    )
    assert f"HAVING sum(la.pdp_views) >= {MIN_UNIQUE_VIEWS}" in sql
    # Reject the weak #601 floor.
    assert "HAVING sum(la.pdp_views) >= 2" not in sql
    assert "vl.status = 'active'" in sql
    assert "v.status = 'active'" in sql
    assert "coalesce(vl.wholesale, false) = false" in sql
    assert "vl.stock_mode = 'always_available'" in sql
    assert "coalesce(vl.stock_qty, 0) > 0" in sql


def test_fetch_trending_returns_empty_on_query_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = MagicMock()
    result.ok = False
    result.error = "boom"
    result.rows = []
    monkeypatch.setattr(trending_mod, "run_sql_script", lambda _sql: result)
    assert fetch_trending_listings(MagicMock(), limit=8) == []


def test_fetch_trending_returns_empty_when_confidence_insufficient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Honest empty rail — never invent trending from thin signal."""
    result = MagicMock()
    result.ok = True
    result.rows = []  # HAVING floor filtered everything server-side
    monkeypatch.setattr(trending_mod, "run_sql_script", lambda _sql: result)
    monkeypatch.setattr(trending_mod, "fetch_demo_listing_ids", lambda _c, _ids: set())
    assert fetch_trending_listings(MagicMock(), limit=8) == []


def test_fetch_trending_excludes_demo_and_parses_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listing_a = "11111111-1111-1111-1111-111111111111"
    listing_b = "22222222-2222-2222-2222-222222222222"
    result = MagicMock()
    result.ok = True
    result.rows = [
        f"{listing_a}|Phone Case|phone-case|Tech Shop|15000|img/a|12.5",
        f"{listing_b}|Demo Gadget|demo-gadget|Demo Co|9900|img/b|11.0",
    ]
    monkeypatch.setattr(trending_mod, "run_sql_script", lambda _sql: result)
    monkeypatch.setattr(
        trending_mod,
        "fetch_demo_listing_ids",
        lambda _c, ids: {listing_b} & set(ids),
    )

    items = fetch_trending_listings(MagicMock(), limit=8)
    assert len(items) == 1
    assert items[0].listing_id == listing_a
    assert items[0].price_ngwee == 15000
    assert items[0].score == 12.5


def test_min_unique_views_constant_is_substantial() -> None:
    assert MIN_UNIQUE_VIEWS >= 10


def test_trending_sql_joins_search_documents_on_uuid_not_text() -> None:
    """search_documents.entity_id is uuid; comparing it to vl.id::text raised
    'operator does not exist: uuid = text' in production and emptied the rail."""
    from app.services.discovery.trending import _trending_sql

    sql = _trending_sql(min_unique_views=10, window_days=7, decay=0.85)
    assert "sd.entity_id = vl.id\n" in sql
    assert "sd.entity_id = vl.id::text" not in sql


def test_trending_sql_uses_existing_listing_columns() -> None:
    """vendor_listings has title_override (no title); listing_images has
    cloudinary_public_id (no public_id). Production raised 'column vl.title
    does not exist' after the uuid join was fixed."""
    from app.services.discovery.trending import _trending_sql

    sql = _trending_sql(min_unique_views=10, window_days=7, decay=0.85)
    assert "vl.title," not in sql
    assert "vl.title_override" in sql
    assert "li.cloudinary_public_id" in sql
    assert "li.public_id" not in sql
