from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import patch

import pytest
from app.main import create_app
from app.routers import directory as directory_module
from fastapi import FastAPI
from fastapi.testclient import TestClient

ACTIVE_VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
PENDING_VENDOR_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
SUSPENDED_VENDOR_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
LISTING_A = "11111111-1111-1111-1111-111111111111"
LISTING_B = "22222222-2222-2222-2222-222222222222"
PRODUCT_A = "p00000001-0000-4000-8000-000000000001"
PRODUCT_B = "p00000002-0000-4000-8000-000000000002"
CATEGORY_ELECTRONICS = "d00000001-0000-4000-8000-000000000001"
CATEGORY_FASHION = "d00000002-0000-4000-8000-000000000002"

LUSAKA_CBD = (-15.4167, 28.2833)
KABULONGA = (-15.3875, 28.3228)


def _vendor_row(
    *,
    vendor_id: str = ACTIVE_VENDOR_ID,
    slug: str = "tech-hub-lusaka",
    display_name: str = "Tech Hub Lusaka",
    status: str = "active",
    preferred_badge: bool = True,
    kyc_tier: int | None = 2,
    description: str = "Electronics and phones in Lusaka.",
    landmark: str = "East Park Mall, Lusaka",
    lat: float = LUSAKA_CBD[0],
    lng: float = LUSAKA_CBD[1],
) -> dict[str, Any]:
    return {
        "id": vendor_id,
        "slug": slug,
        "display_name": display_name,
        "description": description,
        "logo_url": "https://example.com/logo.png",
        "status": status,
        "kyc_tier": kyc_tier,
        "preferred_badge": preferred_badge,
        "created_at": "2025-01-01T00:00:00Z",
        "vendor_locations": [
            {
                "landmark": landmark,
                "lat": lat,
                "lng": lng,
                "hours": {"mon": "09:00-17:00", "sat": "09:00-13:00"},
            }
        ],
    }


def _product_row(
    *,
    product_id: str,
    slug: str,
    name: str,
    category_id: str,
    path: str,
) -> dict[str, Any]:
    return {
        "id": product_id,
        "slug": slug,
        "name": name,
        "status": "active",
        "category_id": category_id,
        "categories": {"path": path},
    }


def _listing_row(
    *,
    listing_id: str,
    vendor_id: str,
    product: dict[str, Any],
    price_ngwee: int = 450_000,
) -> dict[str, Any]:
    return {
        "id": listing_id,
        "vendor_id": vendor_id,
        "title_override": None,
        "price_ngwee": price_ngwee,
        "condition": "new",
        "stock_mode": "tracked",
        "stock_qty": 5,
        "status": "active",
        "products": product,
    }


class FakeResponse:
    def __init__(self, data: Any) -> None:
        self.data = data


class FakeQuery:
    def __init__(self, store: FakeSupabaseStore, table: str) -> None:
        self.store = store
        self.table = table
        self._filters: list[tuple[str, str, Any]] = []
        self._order: tuple[str, bool] | None = None
        self._maybe_single = False
        self._limit: int | None = None

    def select(self, columns: str, count: str | None = None) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._filters.append(("in", column, values))
        return self

    def limit(self, count: int) -> FakeQuery:
        self._limit = count
        return self

    def order(self, column: str, desc: bool = False) -> FakeQuery:
        self._order = (column, desc)
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def execute(self) -> FakeResponse:
        rows = self.store.query(self.table, self._filters)
        if self._order:
            column, desc = self._order

            def sort_key(row: dict[str, Any]) -> str | int | float:
                value = row.get(column)
                if isinstance(value, (str, int, float)):
                    return value
                return ""

            rows = sorted(rows, key=sort_key, reverse=desc)
        if self._maybe_single:
            return FakeResponse(rows[0] if rows else None)
        if self._limit is not None:
            rows = rows[: self._limit]
        return FakeResponse(rows)


class FakeSupabaseStore:
    def __init__(self) -> None:
        self.vendors: list[dict[str, Any]] = []
        self.vendor_listings: list[dict[str, Any]] = []
        self.listing_images: list[dict[str, Any]] = []
        self.order_item_products: list[dict[str, Any]] = []
        self.reviews: list[dict[str, Any]] = []

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self, name)

    def query(self, table: str, filters: list[tuple[str, str, Any]]) -> list[dict[str, Any]]:
        rows = getattr(self, table, []).copy()
        for op, column, value in filters:
            if op == "eq":
                rows = [row for row in rows if self._match_eq(row, column, value)]
            elif op == "in":
                rows = [row for row in rows if row.get(column) in value]
        return rows

    @staticmethod
    def _match_eq(row: dict[str, Any], column: str, value: Any) -> bool:
        if "->>" in column:
            base, _, key = column.partition("->>")
            container = row.get(base)
            return bool(isinstance(container, dict) and container.get(key) == value)
        return bool(row.get(column) == value)


@pytest.fixture
def store() -> FakeSupabaseStore:
    return FakeSupabaseStore()


@pytest.fixture
def client(store: FakeSupabaseStore) -> Generator[TestClient, None, None]:
    app: FastAPI = create_app()

    class FakeServiceClient:
        def __init__(self) -> None:
            self.client = store

    with patch("app.deps.get_supabase_service_client", return_value=FakeServiceClient()):
        with TestClient(app, raise_server_exceptions=False) as test_client:
            yield test_client


def seed_active_vendor(store: FakeSupabaseStore) -> None:
    store.vendors = [_vendor_row()]
    store.vendor_listings = [
        _listing_row(
            listing_id=LISTING_A,
            vendor_id=ACTIVE_VENDOR_ID,
            product=_product_row(
                product_id=PRODUCT_A,
                slug="itel-a70",
                name="Itel A70 Smartphone",
                category_id=CATEGORY_ELECTRONICS,
                path="electronics/phones",
            ),
        )
    ]
    store.listing_images = [
        {
            "listing_id": LISTING_A,
            "cloudinary_public_id": "listings/phone-cover",
            "position": 1,
        }
    ]


class TestDirectoryVisibility:
    def test_active_vendor_listed(self, client: TestClient, store: FakeSupabaseStore) -> None:
        seed_active_vendor(store)

        response = client.get("/directory")
        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        assert payload["items"][0]["slug"] == "tech-hub-lusaka"

    def test_pending_vendor_excluded_from_index(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        store.vendors = [
            _vendor_row(status="active"),
            _vendor_row(
                vendor_id=PENDING_VENDOR_ID,
                slug="pending-shop",
                display_name="Pending Shop",
                status="pending_kyc",
                preferred_badge=False,
                kyc_tier=1,
            ),
        ]

        response = client.get("/directory")
        assert response.status_code == 200
        slugs = [item["slug"] for item in response.json()["items"]]
        assert slugs == ["tech-hub-lusaka"]

    def test_suspended_vendor_profile_returns_404(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        store.vendors = [
            _vendor_row(
                vendor_id=SUSPENDED_VENDOR_ID,
                slug="suspended-shop",
                display_name="Suspended Shop",
                status="suspended",
            )
        ]

        response = client.get("/directory/suspended-shop")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "vendor.not_found"

    def test_pending_vendor_profile_returns_404(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        store.vendors = [
            _vendor_row(
                vendor_id=PENDING_VENDOR_ID,
                slug="pending-shop",
                display_name="Pending Shop",
                status="pending_kyc",
            )
        ]

        response = client.get("/directory/pending-shop")
        assert response.status_code == 404

    def test_old_slug_301_redirects_to_current_slug(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        # M12-P09 records the old slug in caps_snapshot.previous_slug when a vendor
        # changes its slug once; the old link must 301 to the current slug, not 404.
        vendor = _vendor_row(slug="new-shop-name")
        vendor["caps_snapshot"] = {"slug_locked": True, "previous_slug": "old-shop-name"}
        store.vendors = [vendor]

        response = client.get("/directory/old-shop-name", follow_redirects=False)
        assert response.status_code == 301
        assert response.headers["location"] == "/directory/new-shop-name"

    def test_unknown_slug_still_404s(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        store.vendors = [_vendor_row(slug="real-shop")]
        response = client.get("/directory/does-not-exist", follow_redirects=False)
        assert response.status_code == 404


class TestDirectoryFilters:
    def test_category_and_badge_filters_compose(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        store.vendors = [
            _vendor_row(),
            _vendor_row(
                vendor_id=PENDING_VENDOR_ID,
                slug="fashion-boutique",
                display_name="Fashion Boutique",
                preferred_badge=False,
                kyc_tier=1,
                description="Chitenge and dresses",
                landmark="Kabwata Cultural Village",
                lat=KABULONGA[0],
                lng=KABULONGA[1],
            ),
        ]
        store.vendor_listings = [
            _listing_row(
                listing_id=LISTING_A,
                vendor_id=ACTIVE_VENDOR_ID,
                product=_product_row(
                    product_id=PRODUCT_A,
                    slug="itel-a70",
                    name="Itel A70 Smartphone",
                    category_id=CATEGORY_ELECTRONICS,
                    path="electronics/phones",
                ),
            ),
            _listing_row(
                listing_id=LISTING_B,
                vendor_id=PENDING_VENDOR_ID,
                product=_product_row(
                    product_id=PRODUCT_B,
                    slug="chitenge-print",
                    name="Chitenge Print",
                    category_id=CATEGORY_FASHION,
                    path="fashion-beauty/chitenge-fabric",
                ),
            ),
        ]

        response = client.get("/directory?category=electronics&badges=preferred")
        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        assert payload["items"][0]["slug"] == "tech-hub-lusaka"

    def test_location_filter_matches_landmark(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        seed_active_vendor(store)
        store.vendors.append(
            _vendor_row(
                vendor_id=PENDING_VENDOR_ID,
                slug="fashion-boutique",
                display_name="Fashion Boutique",
                landmark="Kabwata Cultural Village",
                lat=KABULONGA[0],
                lng=KABULONGA[1],
            )
        )

        response = client.get("/directory?location=East%20Park")
        assert response.status_code == 200
        assert response.json()["total"] == 1
        assert response.json()["items"][0]["slug"] == "tech-hub-lusaka"

    def test_query_filter_matches_display_name(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        seed_active_vendor(store)

        response = client.get("/directory?q=tech%20hub")
        assert response.status_code == 200
        assert response.json()["total"] == 1


class TestDirectoryEmptyState:
    def test_empty_directory_when_no_active_vendors(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        store.vendors = [
            _vendor_row(status="pending_kyc"),
            _vendor_row(vendor_id=SUSPENDED_VENDOR_ID, slug="gone", status="suspended"),
        ]

        response = client.get("/directory")
        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 0
        assert payload["items"] == []
        assert payload["facets"]["categories"] == []


class TestVendorProfile:
    def test_profile_includes_listings_hours_and_reviews(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        seed_active_vendor(store)
        store.order_item_products = [
            {"order_item_id": "oip-1", "listing_id": LISTING_A},
        ]
        store.reviews = [
            {"order_item_id": "oip-1", "rating": 5, "status": "published"},
        ]

        response = client.get("/directory/tech-hub-lusaka")
        assert response.status_code == 200
        payload = response.json()
        assert payload["vendor"]["display_name"] == "Tech Hub Lusaka"
        assert payload["vendor"]["location"]["landmark"] == "East Park Mall, Lusaka"
        assert payload["vendor"]["location"]["hours"]["mon"] == "09:00-17:00"
        assert len(payload["listings"]) == 1
        assert payload["listings"][0]["product_slug"] == "itel-a70"
        assert payload["reviews_summary"]["rating_count"] == 1
        assert payload["reviews_summary"]["rating_avg"] == 5.0


class TestDirectoryHelpers:
    def test_matches_category_prefix(self) -> None:
        assert directory_module._matches_category({"electronics/phones"}, "electronics")
        assert not directory_module._matches_category({"fashion-beauty"}, "electronics")

    def test_parse_badges_deduplicates(self) -> None:
        assert directory_module._parse_badges("preferred,verified,preferred") == [
            "preferred",
            "verified",
        ]

    def test_sanitize_query_strips_wildcards(self) -> None:
        assert directory_module._sanitize_query("%hack_") == "hack"
