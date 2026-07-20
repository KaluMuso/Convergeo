"""Demo-catalogue exclusion from public surfaces (VC-P06 / FD-04 / G11).

Demo-seeded listings (``vendor_listings.demo``) stay browsable during the
invite-only beta; once ``feature_flags.public_launch`` flips ON they must
vanish from public search, suggest, and the catalogue PLP. Flag flip — not a
deploy — is what retires the demo catalogue.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from app.services.flags import is_public_launch
from app.services.search import SearchHit, drop_demo_listing_hits

DEMO_LISTING_ID = UUID("00000000-0000-4000-8000-00000000d301")
REAL_LISTING_ID = UUID("00000000-0000-4000-8000-00000000d302")


class _Response:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class _TableQuery:
    """Minimal PostgREST-ish stub covering feature_flags + vendor_listings."""

    def __init__(self, table: str, rows: list[dict[str, Any]]) -> None:
        self._table = table
        self._rows = rows
        self._ids: set[str] | None = None
        self._eq: dict[str, Any] = {}

    def select(self, *_a: Any, **_k: Any) -> _TableQuery:
        return self

    def in_(self, _column: str, values: list[str]) -> _TableQuery:
        self._ids = {str(value) for value in values}
        return self

    def eq(self, column: str, value: Any) -> _TableQuery:
        self._eq[column] = value
        return self

    def limit(self, _n: int) -> _TableQuery:
        return self

    def execute(self) -> _Response:
        rows = self._rows
        if self._ids is not None:
            rows = [row for row in rows if str(row.get("id")) in self._ids]
        for column, value in self._eq.items():
            rows = [row for row in rows if row.get(column) == value]
        return _Response([dict(row) for row in rows])


class _FakeClient:
    def __init__(self, *, public_launch: bool, listings: list[dict[str, Any]]) -> None:
        self._flags = [{"flag": "public_launch", "enabled": public_launch}]
        self._listings = listings

    def table(self, name: str) -> _TableQuery:
        if name == "feature_flags":
            return _TableQuery(name, self._flags)
        if name == "vendor_listings":
            return _TableQuery(name, self._listings)
        return _TableQuery(name, [])


class _BrokenClient:
    def table(self, _name: str) -> Any:
        raise RuntimeError("db unavailable")


def _client(*, public_launch: bool) -> _FakeClient:
    return _FakeClient(
        public_launch=public_launch,
        listings=[
            {"id": str(DEMO_LISTING_ID), "demo": True},
            {"id": str(REAL_LISTING_ID), "demo": False},
        ],
    )


def _hit(entity_id: UUID, *, kind: str = "listing") -> SearchHit:
    return SearchHit(
        id=str(entity_id),
        entity_kind=kind,
        entity_id=str(entity_id),
        title="Listing",
        rrf_score=1.0,
    )


class TestIsPublicLaunch:
    def test_on_flag_returns_true(self) -> None:
        assert is_public_launch(_client(public_launch=True)) is True

    def test_off_flag_returns_false(self) -> None:
        assert is_public_launch(_client(public_launch=False)) is False

    def test_missing_flag_row_defaults_false(self) -> None:
        client = _FakeClient(public_launch=True, listings=[])
        client._flags = []
        assert is_public_launch(client) is False

    def test_read_error_fails_safe_to_false(self) -> None:
        assert is_public_launch(_BrokenClient()) is False


class TestDropDemoListingHits:
    def test_drops_only_demo_listing_hits(self) -> None:
        hits = [_hit(DEMO_LISTING_ID), _hit(REAL_LISTING_ID)]
        kept = drop_demo_listing_hits(_client(public_launch=True), hits)
        assert [h.entity_id for h in kept] == [str(REAL_LISTING_ID)]

    def test_non_listing_hits_untouched(self) -> None:
        hits = [_hit(DEMO_LISTING_ID, kind="product")]
        kept = drop_demo_listing_hits(_client(public_launch=True), hits)
        assert len(kept) == 1

    def test_no_listing_hits_short_circuits(self) -> None:
        assert drop_demo_listing_hits(_BrokenClient(), []) == []


class TestCatalogDemoExclusion:
    @staticmethod
    def _candidate(listing_id: UUID, *, demo: bool) -> Any:
        from app.routers.catalog import _CatalogCandidate, _ListingRow, _SearchDocRow

        return _CatalogCandidate(
            search_doc=_SearchDocRow(
                entity_id=str(listing_id),
                title="Listing",
                category_path="electronics",
                price_min_ngwee=10_000,
            ),
            listing=_ListingRow(
                id=str(listing_id),
                vendor_id="00000000-0000-4000-8000-00000000aaaa",
                condition="new",
                stock_mode="finite",
                stock_qty=3,
                demo=demo,
            ),
            vendor={"id": "00000000-0000-4000-8000-00000000aaaa", "display_name": "V", "slug": "v"},
            product=None,
            image_public_id=None,
            landmark=None,
            rating=0.0,
            review_count=0,
            in_stock=True,
        )

    @pytest.mark.parametrize(
        ("exclude_demo", "expected_ids"),
        [
            (True, [str(REAL_LISTING_ID)]),
            (False, [str(DEMO_LISTING_ID), str(REAL_LISTING_ID)]),
        ],
    )
    def test_list_catalog_honours_exclude_demo(
        self,
        monkeypatch: pytest.MonkeyPatch,
        exclude_demo: bool,
        expected_ids: list[str],
    ) -> None:
        import app.routers.catalog as catalog

        candidates = [
            self._candidate(DEMO_LISTING_ID, demo=True),
            self._candidate(REAL_LISTING_ID, demo=False),
        ]
        monkeypatch.setattr(catalog, "_build_candidates", lambda _c, _p: candidates)

        filters = catalog.PlpFilterState()
        response = catalog.list_catalog(object(), filters, exclude_demo=exclude_demo)
        assert [item.id for item in response.items] == expected_ids
