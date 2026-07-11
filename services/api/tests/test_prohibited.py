"""Prohibited-category + keyword screen tests (M15-P08).

Pure-unit / isolation-clean: no network, no DB, no TestClient. Exercises the
central screen directly, the CSV/JSON import per-row rejection via a tiny fake
Supabase client, and asserts every create/edit/import path invokes the guard.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest
from app.routers import (
    listing_import,
    services_listings,
    vendor_listings,
    vendor_listings_manage,
)
from app.services.kyc.caps import VendorCapLimits, VendorQuota
from app.services.listings import csv_import
from app.services.listings.csv_import import import_listing_rows
from app.services.moderation.prohibited import (
    PROHIBITED_CATEGORIES,
    PROHIBITED_KEYWORDS,
    screen_listing,
)

VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


# --------------------------------------------------------------------------- #
# Category block
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("category", sorted(PROHIBITED_CATEGORIES))
def test_every_prohibited_category_is_blocked(category: str) -> None:
    result = screen_listing(title="A perfectly normal item", category=category)
    assert result.allowed is False
    assert result.reason == "category"
    assert result.matched == category


@pytest.mark.parametrize(
    "raw_category",
    ["Used Phones", "used_phones", "  ALCOHOL  ", "Live-Animals", "Salaula"],
)
def test_category_block_is_case_space_and_separator_insensitive(raw_category: str) -> None:
    result = screen_listing(title="Nice item", category=raw_category)
    assert result.allowed is False
    assert result.reason == "category"


def test_benign_category_is_allowed() -> None:
    assert screen_listing(title="Fresh tomatoes", category="groceries").allowed is True
    assert screen_listing(title="Haircut at home", category="beauty").allowed is True


# --------------------------------------------------------------------------- #
# Keyword block (incl. case / diacritic / plural variants)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("keyword", sorted(PROHIBITED_KEYWORDS))
def test_every_seed_keyword_is_blocked(keyword: str) -> None:
    result = screen_listing(title=f"Selling {keyword} today", description=None)
    assert result.allowed is False
    assert result.reason == "keyword"
    # Overlapping phrases (e.g. "aggregate" ⊂ "heavy aggregate") may match the
    # shorter token first; either way a real prohibited keyword is reported.
    assert result.matched in PROHIBITED_KEYWORDS


@pytest.mark.parametrize(
    ("text", "expected_match"),
    [
        ("Cold ALCOHOL crate", "alcohol"),  # uppercase
        ("Cheap álcohol here", "alcohol"),  # diacritic
        ("Quality Salaula bales", "salaula"),  # capitalised
        ("Used  phones for resale", "used phone"),  # extra whitespace + plural
        ("Bag of CEMENT", "cement"),  # uppercase
        ("Assorted live animals", "live animal"),  # plural on last word
        ("prescription   drugs cheap", "prescription drug"),  # multi-word + plural
    ],
)
def test_keyword_variants_are_blocked(text: str, expected_match: str) -> None:
    result = screen_listing(title=text)
    assert result.allowed is False
    assert result.reason == "keyword"
    assert result.matched == expected_match


def test_keyword_screen_reads_description_too() -> None:
    result = screen_listing(title="Great deal", description="comes with free beer")
    assert result.allowed is False
    assert result.matched == "beer"


# --------------------------------------------------------------------------- #
# No false positives on innocent substrings (word-boundary anchored)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "benign",
    [
        "Placement services for graduates",  # contains "cement"
        "Aggregated analytics dashboard",  # contains "aggregate"
        "Winery tour experience",  # contains "wine"
        "Fresh farm tomatoes per kg",  # unrelated
        "Reusable shopping bags",  # contains "used" but not "used phone"
        "Beetroot and beans bundle",  # near "beer" but not a match
    ],
)
def test_benign_listings_pass(benign: str) -> None:
    result = screen_listing(title=benign, description=benign)
    assert result.allowed is True
    assert result.reason is None
    assert result.matched is None


def test_word_boundary_blocks_standalone_but_not_substring() -> None:
    assert screen_listing(title="aggregate stone").allowed is False
    assert screen_listing(title="aggregated report").allowed is True


# --------------------------------------------------------------------------- #
# CSV / JSON import: reject offending row, keep clean rows
# --------------------------------------------------------------------------- #
class _FakeResult:
    def __init__(self, data: Any) -> None:
        self.data = data


class _FakeQuery:
    def __init__(self, table: _FakeTable) -> None:
        self._table = table
        self._op: str | None = None
        self._payload: dict[str, Any] | None = None

    def select(self, *_args: Any, **_kwargs: Any) -> _FakeQuery:
        return self

    def eq(self, *_args: Any, **_kwargs: Any) -> _FakeQuery:
        return self

    def insert(self, payload: dict[str, Any]) -> _FakeQuery:
        self._op = "insert"
        self._payload = payload
        return self

    def execute(self) -> _FakeResult:
        if self._op == "insert":
            assert self._payload is not None
            row = dict(self._payload)
            row["id"] = f"listing-{len(self._table.rows):04d}"
            self._table.rows.append(row)
            return _FakeResult(row)
        return _FakeResult(list(self._table.rows))


class _FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, *args: Any, **kwargs: Any) -> _FakeQuery:
        return _FakeQuery(self).select(*args, **kwargs)

    def insert(self, payload: dict[str, Any]) -> _FakeQuery:
        return _FakeQuery(self).insert(payload)


class _FakeClient:
    def __init__(self) -> None:
        self.tables = {"vendor_listings": _FakeTable()}

    def table(self, name: str) -> _FakeTable:
        return self.tables[name]


def _limits() -> VendorCapLimits:
    return VendorCapLimits(
        vendor_id=VENDOR_ID,
        kyc_tier=2,
        quota=VendorQuota(
            tier=2,
            max_listings=100,
            first_orders_cap_ngwee=None,
            first_orders_count=None,
            payout_velocity={},
        ),
        cod_cap_ngwee=50_000,
        listing_count=0,
        order_count=0,
    )


def _row(sku: str, title: str) -> dict[str, str]:
    return {
        "sku": sku,
        "title": title,
        "price_ngwee": "2500",
        "stock_mode": "tracked",
        "stock_qty": "5",
        "condition": "new",
    }


def test_import_rejects_prohibited_row_and_keeps_clean_rows() -> None:
    rows = [
        _row("OK-1", "Fresh tomatoes per kg"),
        _row("BAD-1", "Crate of cold beer"),
        _row("OK-2", "White rice 10kg bag"),
    ]
    summary = import_listing_rows(
        _FakeClient(), vendor_id=VENDOR_ID, limits=_limits(), rows=rows
    )

    assert summary.accepted == 2
    assert summary.rejected == 1

    by_row = {result.row: result for result in summary.rows}
    assert by_row[1].ok is True
    assert by_row[3].ok is True
    assert by_row[2].ok is False
    assert any("prohibited" in err for err in by_row[2].errors)
    assert "beer" in by_row[2].errors[0]


def test_import_accepts_all_clean_rows() -> None:
    rows = [_row("OK-1", "Fresh tomatoes"), _row("OK-2", "Bananas bunch")]
    summary = import_listing_rows(
        _FakeClient(), vendor_id=VENDOR_ID, limits=_limits(), rows=rows
    )
    assert summary.accepted == 2
    assert summary.rejected == 0


# --------------------------------------------------------------------------- #
# Guard is invoked on every create / edit / import path
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "module",
    [
        vendor_listings,
        vendor_listings_manage,
        services_listings,
        listing_import,
        csv_import,
    ],
)
def test_screen_listing_invoked_on_every_path(module: Any) -> None:
    source = inspect.getsource(module)
    assert "from app.services.moderation.prohibited import screen_listing" in source
    assert "screen_listing(" in source
