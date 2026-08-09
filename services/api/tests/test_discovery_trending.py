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
