from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import patch

import pytest
from app.main import create_app
from app.routers import products as products_router
from fastapi import FastAPI
from fastapi.testclient import TestClient

PRODUCT_ID = "p00000133-0000-4000-8000-000000000001"
MERGED_PRODUCT_ID = "p00009999-0000-4000-8000-000000000099"
CANONICAL_PRODUCT_ID = "p00000134-0000-4000-8000-000000000001"
VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
LISTING_IN_STOCK = "11111111-1111-1111-1111-111111111111"
LISTING_OUT_OF_STOCK = "22222222-2222-2222-2222-222222222222"
LISTING_QUICK = "33333333-3333-3333-3333-333333333333"


def _product_row(
    *,
    slug: str = "itel-a70",
    status: str = "active",
    merged_into_id: str | None = None,
    spec: dict[str, Any] | None = None,
    description: str | None = None,
    product_id: str = PRODUCT_ID,
) -> dict[str, Any]:
    return {
        "id": product_id,
        "name": "Itel A70 Smartphone",
        "slug": slug,
        "brand": "Itel",
        "description": description,
        "spec": spec if spec is not None else {"storage_gb": "128", "ram_gb": "4"},
        "category_id": "d00000027-0000-4000-8000-000000000001",
        "status": status,
        "merged_into_id": merged_into_id,
    }


def _vendor_row(*, preferred_badge: bool = True) -> dict[str, Any]:
    return {
        "id": VENDOR_ID,
        "slug": "tech-hub-lusaka",
        "display_name": "Tech Hub Lusaka",
        "preferred_badge": preferred_badge,
        "status": "active",
        "vendor_locations": [
            {
                "landmark": "East Park Mall",
                "lat": -15.4167,
                "lng": 28.2833,
            }
        ],
    }


def _listing_row(
    *,
    listing_id: str,
    price_ngwee: int = 450_000,
    stock_mode: str = "tracked",
    stock_qty: int | None = 12,
    title_override: str | None = None,
    product_id: str | None = PRODUCT_ID,
) -> dict[str, Any]:
    return {
        "id": listing_id,
        "title_override": title_override,
        "price_ngwee": price_ngwee,
        "condition": "new",
        "stock_mode": stock_mode,
        "stock_qty": stock_qty,
        "moq": 1,
        "wholesale": False,
        "status": "active",
        "product_id": product_id,
        "vendors": _vendor_row(),
    }


class FakeResponse:
    def __init__(self, data: Any) -> None:
        self.data = data


class FakeQuery:
    def __init__(self, store: FakeSupabaseStore, table: str) -> None:
        self.store = store
        self.table = table
        self._filters: list[tuple[str, str, Any]] = []
        self._select = "*"
        self._order: tuple[str, bool] | None = None
        self._maybe_single = False

    def select(self, columns: str, count: str | None = None) -> FakeQuery:
        self._select = columns
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._filters.append(("in", column, values))
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
        return FakeResponse(rows)


class FakeSupabaseStore:
    def __init__(self) -> None:
        self.products: list[dict[str, Any]] = []
        self.vendor_listings: list[dict[str, Any]] = []
        self.listing_images: list[dict[str, Any]] = []
        self.order_item_products: list[dict[str, Any]] = []
        self.reviews: list[dict[str, Any]] = []

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self, name)

    def query(self, table: str, filters: list[tuple[str, str, Any]]) -> list[dict[str, Any]]:
        rows = getattr(self, table.replace("-", "_"), []).copy()
        for op, column, value in filters:
            if op == "eq":
                rows = [row for row in rows if self._match_eq(row, column, value)]
            elif op == "in":
                rows = [row for row in rows if row.get(column) in value]
        return rows

    @staticmethod
    def _match_eq(row: dict[str, Any], column: str, value: Any) -> bool:
        if "." in column:
            return True
        if column == "vendors.status":
            vendor = row.get("vendors")
            return isinstance(vendor, dict) and vendor.get("status") == value
        row_value = row.get(column)
        return bool(row_value == value)


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


class TestProductDetailStates:
    def test_in_stock_listing(self, client: TestClient, store: FakeSupabaseStore) -> None:
        store.products = [_product_row()]
        store.vendor_listings = [_listing_row(listing_id=LISTING_IN_STOCK, stock_qty=8)]
        store.listing_images = [
            {
                "listing_id": LISTING_IN_STOCK,
                "cloudinary_public_id": "listings/phone-cover",
                "position": 1,
            }
        ]

        response = client.get("/products/itel-a70")
        assert response.status_code == 200
        payload = response.json()
        assert payload["slug"] == "itel-a70"
        assert payload["listing_count"] == 1
        assert payload["listings"][0]["in_stock"] is True
        assert payload["listings"][0]["stock_qty"] == 8
        assert payload["images"][0]["public_id"] == "listings/phone-cover"
        # No canonical description set → field is null, not the empty string.
        assert payload["description"] is None

    def test_description_is_returned(self, client: TestClient, store: FakeSupabaseStore) -> None:
        store.products = [
            _product_row(description="  A durable smartphone built for Zambia.  ")
        ]
        store.vendor_listings = [_listing_row(listing_id=LISTING_IN_STOCK)]

        response = client.get("/products/itel-a70")
        assert response.status_code == 200
        # Trimmed, non-empty description flows to the PDP Overview tab.
        assert response.json()["description"] == "A durable smartphone built for Zambia."

    def test_blank_description_normalized_to_null(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        store.products = [_product_row(description="   ")]
        store.vendor_listings = [_listing_row(listing_id=LISTING_IN_STOCK)]

        response = client.get("/products/itel-a70")
        assert response.status_code == 200
        assert response.json()["description"] is None

    def test_out_of_stock_listing(self, client: TestClient, store: FakeSupabaseStore) -> None:
        store.products = [_product_row()]
        store.vendor_listings = [
            _listing_row(listing_id=LISTING_OUT_OF_STOCK, stock_mode="tracked", stock_qty=0)
        ]

        response = client.get("/products/itel-a70")
        assert response.status_code == 200
        listing = response.json()["listings"][0]
        assert listing["in_stock"] is False
        assert listing["stock_qty"] == 0

    def test_no_reviews_vendor_rating(self, client: TestClient, store: FakeSupabaseStore) -> None:
        store.products = [_product_row()]
        store.vendor_listings = [_listing_row(listing_id=LISTING_IN_STOCK)]

        response = client.get("/products/itel-a70")
        assert response.status_code == 200
        vendor = response.json()["listings"][0]["vendor"]
        assert vendor["rating_avg"] is None
        assert vendor["rating_count"] == 0

    def test_quick_list_without_canonical_spec(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        store.products = [_product_row(spec={})]
        store.vendor_listings = [
            _listing_row(
                listing_id=LISTING_QUICK,
                title_override="Fresh Tomatoes per kg",
                stock_mode="always_available",
                stock_qty=None,
            )
        ]

        response = client.get("/products/itel-a70")
        assert response.status_code == 200
        payload = response.json()
        assert payload["spec"] == {}
        listing = payload["listings"][0]
        assert listing["title"] == "Fresh Tomatoes per kg"
        assert listing["in_stock"] is True
        assert listing["stock_mode"] == "always_available"


class TestProductErrors:
    def test_unknown_slug_returns_404(self, client: TestClient) -> None:
        response = client.get("/products/does-not-exist")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "product.not_found"

    def test_merged_product_redirects_301(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        store.products = [
            _product_row(
                slug="old-itel-a70",
                status="merged",
                merged_into_id=CANONICAL_PRODUCT_ID,
                product_id=MERGED_PRODUCT_ID,
            ),
            _product_row(slug="tecno-spark-20", product_id=CANONICAL_PRODUCT_ID),
        ]

        response = client.get("/products/old-itel-a70", follow_redirects=False)
        assert response.status_code == 301
        assert response.headers["location"] == "/products/tecno-spark-20"


class TestProductHelpers:
    def test_is_in_stock_matrix(self) -> None:
        assert products_router._is_in_stock("always_available", None) is True
        assert products_router._is_in_stock("tracked", 3) is True
        assert products_router._is_in_stock("tracked", 0) is False

    def test_collect_images_caps_at_eight(self) -> None:
        listing_id = LISTING_IN_STOCK
        listing_rows = [_listing_row(listing_id=listing_id)]
        images_by_listing = {
            listing_id: [
                {
                    "cloudinary_public_id": f"img-{index}",
                    "position": index,
                }
                for index in range(1, 10)
            ]
        }
        images = products_router._collect_images(
            listing_rows,
            images_by_listing,
            primary_listing_id=listing_id,
        )
        assert len(images) == 8
        assert images[0].public_id == "img-1"
