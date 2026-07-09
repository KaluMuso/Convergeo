from __future__ import annotations

import math
from collections.abc import Generator
from typing import Any
from unittest.mock import patch

import pytest
from app.main import create_app
from app.routers.comparison import (
    COMPARISON_LISTINGS_SQL,
    LUSAKA_DELIVERY_RADIUS_M,
    ComparisonListingItem,
    ComparisonVendorResponse,
    build_comparison,
    haversine_m,
    is_lusaka_delivery_available,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient

PRODUCT_ID = "p00000133-0000-4000-8000-000000000001"
VENDOR_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VENDOR_B_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
VENDOR_SUSPENDED_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
LISTING_CHEAP = "11111111-1111-1111-1111-111111111111"
LISTING_MID = "22222222-2222-2222-2222-222222222222"
LISTING_FAR = "33333333-3333-3333-3333-333333333333"
LISTING_SUSPENDED = "44444444-4444-4444-4444-444444444444"

LUSAKA_CBD = (-15.4167, 28.2833)
KABULONGA = (-15.3875, 28.3228)
NDOLA = (-12.9683, 28.6336)


def should_show_comparison(listing_count: int) -> bool:
    return listing_count > 1


def resolve_user_coords_py(
    geo: dict[str, float] | None,
    *,
    permission_denied: bool,
) -> dict[str, float]:
    if geo is not None and not permission_denied:
        return geo
    return {"lat": LUSAKA_CBD[0], "lng": LUSAKA_CBD[1]}


def sort_comparison_listings(
    listings: list[ComparisonListingItem],
    *,
    sort: str,
    user_coords: dict[str, float],
) -> list[ComparisonListingItem]:
    indexed = list(enumerate(listings))

    def distance_for(item: ComparisonListingItem) -> float:
        lat = item.vendor.lat
        lng = item.vendor.lng
        if lat is None or lng is None:
            return math.inf
        return haversine_m(user_coords["lat"], user_coords["lng"], lat, lng)

    if sort == "price":
        indexed.sort(key=lambda pair: (pair[1].price_ngwee, pair[0]))
    else:
        indexed.sort(
            key=lambda pair: (distance_for(pair[1]), pair[1].price_ngwee, pair[0]),
        )

    return [item for _, item in indexed]


def _product_row(*, slug: str = "itel-a70") -> dict[str, Any]:
    return {
        "id": PRODUCT_ID,
        "slug": slug,
        "status": "active",
        "merged_into_id": None,
    }


def _vendor_row(
    *,
    vendor_id: str,
    display_name: str,
    status: str = "active",
    lat: float = LUSAKA_CBD[0],
    lng: float = LUSAKA_CBD[1],
    preferred_badge: bool = False,
) -> dict[str, Any]:
    return {
        "id": vendor_id,
        "slug": display_name.lower().replace(" ", "-"),
        "display_name": display_name,
        "preferred_badge": preferred_badge,
        "status": status,
        "vendor_locations": [
            {
                "landmark": "East Park Mall",
                "lat": lat,
                "lng": lng,
            }
        ],
    }


def _listing_row(
    *,
    listing_id: str,
    vendor: dict[str, Any],
    price_ngwee: int,
    condition: str = "new",
) -> dict[str, Any]:
    return {
        "id": listing_id,
        "price_ngwee": price_ngwee,
        "condition": condition,
        "status": "active",
        "product_id": PRODUCT_ID,
        "vendors": vendor,
    }


def _comparison_item(
    *,
    listing_id: str,
    price_ngwee: int,
    lat: float | None,
    lng: float | None,
) -> ComparisonListingItem:
    return ComparisonListingItem(
        id=listing_id,
        price_ngwee=price_ngwee,
        condition="new",
        vendor=ComparisonVendorResponse(
            id=VENDOR_A_ID,
            slug="vendor-a",
            display_name="Vendor A",
            preferred_badge=False,
            rating_avg=None,
            rating_count=0,
            lat=lat,
            lng=lng,
            landmark="East Park Mall",
        ),
        delivery_available=is_lusaka_delivery_available(lat, lng),
        pickup_available=lat is not None and lng is not None,
    )


class FakeResponse:
    def __init__(self, data: Any) -> None:
        self.data = data


class FakeQuery:
    def __init__(self, store: FakeSupabaseStore, table: str) -> None:
        self.store = store
        self.table = table
        self._filters: list[tuple[str, str, Any]] = []
        self._orders: list[tuple[str, bool]] = []
        self._maybe_single = False

    def select(self, columns: str, count: str | None = None) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._filters.append(("in", column, values))
        return self

    def order(self, column: str, desc: bool = False) -> FakeQuery:
        self._orders.append((column, desc))
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def execute(self) -> FakeResponse:
        rows = self.store.query(self.table, self._filters)
        for column, desc in self._orders:
            rows = sorted(
                rows,
                key=lambda row: (row.get(column), row.get("id", "")),
                reverse=desc,
            )
        if self._maybe_single:
            return FakeResponse(rows[0] if rows else None)
        return FakeResponse(rows)


class FakeSupabaseStore:
    def __init__(self) -> None:
        self.products: list[dict[str, Any]] = []
        self.vendor_listings: list[dict[str, Any]] = []
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
        if column == "vendors.status":
            vendor = row.get("vendors")
            return isinstance(vendor, dict) and vendor.get("status") == value
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


class TestComparisonHelpers:
    def test_should_hide_comparison_single_listing(self) -> None:
        assert should_show_comparison(1) is False
        assert should_show_comparison(2) is True

    def test_distance_fallback_uses_lusaka_cbd(self) -> None:
        coords = resolve_user_coords_py(None, permission_denied=True)
        assert coords == {"lat": LUSAKA_CBD[0], "lng": LUSAKA_CBD[1]}

    def test_distance_sort_orders_nearest_first(self) -> None:
        listings = [
            _comparison_item(
                listing_id=LISTING_FAR,
                price_ngwee=300_000,
                lat=NDOLA[0],
                lng=NDOLA[1],
            ),
            _comparison_item(
                listing_id=LISTING_CHEAP,
                price_ngwee=500_000,
                lat=KABULONGA[0],
                lng=KABULONGA[1],
            ),
            _comparison_item(
                listing_id=LISTING_MID,
                price_ngwee=400_000,
                lat=LUSAKA_CBD[0],
                lng=LUSAKA_CBD[1],
            ),
        ]

        sorted_listings = sort_comparison_listings(
            listings,
            sort="distance",
            user_coords={"lat": LUSAKA_CBD[0], "lng": LUSAKA_CBD[1]},
        )

        assert [item.id for item in sorted_listings] == [
            LISTING_MID,
            LISTING_CHEAP,
            LISTING_FAR,
        ]

    def test_price_sort_is_stable_on_ties(self) -> None:
        listings = [
            _comparison_item(
                listing_id=LISTING_MID,
                price_ngwee=400_000,
                lat=LUSAKA_CBD[0],
                lng=LUSAKA_CBD[1],
            ),
            _comparison_item(
                listing_id=LISTING_CHEAP,
                price_ngwee=400_000,
                lat=KABULONGA[0],
                lng=KABULONGA[1],
            ),
        ]

        sorted_listings = sort_comparison_listings(
            listings,
            sort="price",
            user_coords={"lat": LUSAKA_CBD[0], "lng": LUSAKA_CBD[1]},
        )

        assert [item.id for item in sorted_listings] == [LISTING_MID, LISTING_CHEAP]

    def test_haversine_zero_distance(self) -> None:
        distance = haversine_m(
            LUSAKA_CBD[0],
            LUSAKA_CBD[1],
            LUSAKA_CBD[0],
            LUSAKA_CBD[1],
        )
        assert distance == pytest.approx(0.0)


class TestComparisonEndpoint:
    def test_returns_active_listings_sorted_by_price(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        store.products = [_product_row()]
        store.vendor_listings = [
            _listing_row(
                listing_id=LISTING_MID,
                vendor=_vendor_row(vendor_id=VENDOR_B_ID, display_name="Vendor B"),
                price_ngwee=460_000,
            ),
            _listing_row(
                listing_id=LISTING_CHEAP,
                vendor=_vendor_row(vendor_id=VENDOR_A_ID, display_name="Vendor A"),
                price_ngwee=420_000,
            ),
        ]

        response = client.get("/products/itel-a70/comparison")
        assert response.status_code == 200
        payload = response.json()
        assert payload["listing_count"] == 2
        assert [item["id"] for item in payload["listings"]] == [LISTING_CHEAP, LISTING_MID]
        assert payload["listings"][0]["pickup_available"] is True
        assert payload["listings"][0]["delivery_available"] is True

    def test_excludes_suspended_vendor_listings(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        store.products = [_product_row()]
        store.vendor_listings = [
            _listing_row(
                listing_id=LISTING_CHEAP,
                vendor=_vendor_row(vendor_id=VENDOR_A_ID, display_name="Vendor A"),
                price_ngwee=420_000,
            ),
            _listing_row(
                listing_id=LISTING_SUSPENDED,
                vendor=_vendor_row(
                    vendor_id=VENDOR_SUSPENDED_ID,
                    display_name="Suspended Vendor",
                    status="suspended",
                ),
                price_ngwee=390_000,
            ),
        ]

        response = client.get("/products/itel-a70/comparison")
        assert response.status_code == 200
        payload = response.json()
        assert payload["listing_count"] == 1
        assert payload["listings"][0]["id"] == LISTING_CHEAP

    def test_product_not_found(self, client: TestClient) -> None:
        response = client.get("/products/missing-product/comparison")
        assert response.status_code == 404

    def test_build_comparison_direct(self, store: FakeSupabaseStore) -> None:
        store.products = [_product_row()]
        store.vendor_listings = [
            _listing_row(
                listing_id=LISTING_CHEAP,
                vendor=_vendor_row(vendor_id=VENDOR_A_ID, display_name="Vendor A"),
                price_ngwee=420_000,
            ),
        ]

        response = build_comparison(store, "itel-a70")
        assert response.listing_count == 1
        assert response.listings[0].delivery_available is True
        assert is_lusaka_delivery_available(NDOLA[0], NDOLA[1]) is False
        ndola_distance = haversine_m(
            NDOLA[0],
            NDOLA[1],
            LUSAKA_CBD[0],
            LUSAKA_CBD[1],
        )
        assert ndola_distance > LUSAKA_DELIVERY_RADIUS_M


class TestComparisonSqlPlan:
    def test_documented_sql_uses_product_id_index(self) -> None:
        assert "vendor_listings_product_id_active_idx" in COMPARISON_LISTINGS_SQL
        assert "vl.product_id = $1::uuid" in COMPARISON_LISTINGS_SQL
        assert "vl.status = 'active'" in COMPARISON_LISTINGS_SQL
        assert "v.status = 'active'" in COMPARISON_LISTINGS_SQL

    @pytest.mark.integration
    def test_integration_explain_uses_product_id_index(self) -> None:
        import shutil

        if shutil.which("psql") is None:
            pytest.skip("psql not available")

        from tests.rls.conftest import PgConn, apply_migrations, resolve_db_url

        url = resolve_db_url()
        conn = PgConn(url)
        if not conn.run("SELECT 1").ok:
            pytest.skip("database unavailable")

        if not conn.run("SELECT to_regclass('public.vendor_listings')").rows:
            apply_migrations(conn)

        result = conn.run(
            """
EXPLAIN (COSTS OFF)
SELECT id
FROM public.vendor_listings
WHERE product_id = 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'
  AND status = 'active';
"""
        )
        if not result.ok:
            pytest.skip("EXPLAIN unavailable")

        plan = "\n".join(result.rows)
        assert (
            "vendor_listings_product_id_active_idx" in plan
            or (
                "Index Scan" in plan
                and "vendor_listings" in plan
                and "product_id" in plan
            )
        )
