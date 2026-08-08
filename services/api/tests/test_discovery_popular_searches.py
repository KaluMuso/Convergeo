"""Privacy regression tests for public popular-search discovery."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from app.services.discovery import popular_searches as popular_mod
from app.services.discovery.popular_searches import (
    MIN_AGGREGATION_COUNT,
    MIN_WINDOW_DAYS,
    fetch_popular_searches,
    is_publishable_popular_term,
    looks_like_pii,
)


def test_looks_like_pii_email() -> None:
    assert looks_like_pii("alice@example.com")
    assert looks_like_pii("contact alice@mail.zm for phones")


def test_looks_like_pii_zambian_phone() -> None:
    assert looks_like_pii("0977123456")
    assert looks_like_pii("+260977123456")
    assert looks_like_pii("call 0977 123 456 now")


def test_benign_terms_are_not_pii() -> None:
    assert not looks_like_pii("iphone 15")
    assert not looks_like_pii("chitenge lusaka")
    # Price-shaped numbers must not trip phone detection.
    assert not looks_like_pii("K970 blender")


def test_prohibited_terms_blocked() -> None:
    assert not is_publishable_popular_term("salaula", count=100)
    assert not is_publishable_popular_term("used phone cheap", count=100)
    assert not is_publishable_popular_term("alcohol delivery", count=100)


def test_rare_terms_blocked_by_threshold() -> None:
    assert not is_publishable_popular_term("iphone 15", count=MIN_AGGREGATION_COUNT - 1)
    assert is_publishable_popular_term("iphone 15", count=MIN_AGGREGATION_COUNT)


def test_fetch_popular_searches_filters_pii_and_rare(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        popular_mod._RawTermCount("iphone 15", "iPhone 15", 12),
        popular_mod._RawTermCount("0977123456", "0977123456", 20),
        popular_mod._RawTermCount("alice@example.com", "alice@example.com", 15),
        popular_mod._RawTermCount("salaula", "salaula", 30),
        popular_mod._RawTermCount("rare niche", "rare niche", 2),
        popular_mod._RawTermCount("chitenge", "Chitenge", 8),
    ]
    monkeypatch.setattr(popular_mod, "_fetch_aggregated_terms", lambda **_kw: rows)

    items = fetch_popular_searches(limit=10, days=30)
    terms = [item.term.lower() for item in items]
    assert "iphone 15" in terms
    assert "chitenge" in terms
    assert "0977123456" not in terms
    assert "alice@example.com" not in terms
    assert "salaula" not in terms
    assert "rare niche" not in terms


def test_fetch_clamps_window_to_privacy_minimum(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, int] = {}

    def _spy(*, days: int, limit: int) -> list[popular_mod._RawTermCount]:
        seen["days"] = days
        seen["limit"] = limit
        return []

    monkeypatch.setattr(popular_mod, "_fetch_aggregated_terms", _spy)
    fetch_popular_searches(limit=6, days=1)
    assert seen["days"] == MIN_WINDOW_DAYS


def test_fetch_bounds_result_count(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        popular_mod._RawTermCount(f"term {i}", f"Term {i}", 10 + i) for i in range(40)
    ]
    monkeypatch.setattr(popular_mod, "_fetch_aggregated_terms", lambda **_kw: rows)
    items = fetch_popular_searches(limit=8, days=30)
    assert len(items) == 8


def test_sql_includes_having_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def _fake_sql(script: str) -> MagicMock:
        captured["script"] = script
        result = MagicMock()
        result.ok = True
        result.rows = []
        return result

    monkeypatch.setattr(popular_mod, "run_sql_script", _fake_sql)
    popular_mod._fetch_aggregated_terms(days=30, limit=8)
    assert f"HAVING count(*) >= {MIN_AGGREGATION_COUNT}" in captured["script"]
    assert "kind = 'search'" in captured["script"]
