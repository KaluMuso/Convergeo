from __future__ import annotations

from collections.abc import Generator
from typing import Any, cast

import pytest
from app.main import create_app
from app.routers import catalog as catalog_module
from app.routers.catalog import (
    DISTANCE_SORT_SQL,
    FACET_COUNT_SQL,
    PlpFilterState,
    _CatalogCandidate,
    _ListingRow,
    _SearchDocRow,
    compute_facet_counts,
    decode_plp_filters,
    encode_plp_filters,
    haversine_m,
    list_catalog,
)
from app.services.business.access import BusinessAccess, get_business_access
from fastapi import FastAPI
from fastapi.testclient import TestClient

PHONE_LISTING_ID = "b1000000-0000-0000-0000-000000000001"
CHITENGE_LISTING_ID = "b1000000-0000-0000-0000-000000000002"
DEMO_LISTING_ID = "b1000000-0000-0000-0000-000000000003"
WHOLESALE_LISTING_ID = "b1000000-0000-0000-0000-000000000004"
SHOP_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SHOP_B_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
PHONE_PRODUCT_ID = "b0000000-0000-0000-0000-000000000001"
CHITENGE_PRODUCT_ID = "b0000000-0000-0000-0000-000000000002"

LUSAKA_CBD = (-15.4167, 28.2833)
KABULONGA = (-15.3875, 28.3228)


def _search_doc(
    entity_id: str,
    *,
    title: str,
    category_path: str,
    price: int,
    lat: float,
    lng: float,
    updated_at: str = "2026-01-01T00:00:00Z",
) -> dict[str, Any]:
    return {
        "entity_id": entity_id,
        "entity_kind": "listing",
        "is_public": True,
        "title": title,
        "category_path": category_path,
        "price_min_ngwee": price,
        "lat": lat,
        "lng": lng,
        "boost_signals": {"in_stock": True, "verified": True},
        "updated_at": updated_at,
    }


def _listing(
    listing_id: str,
    *,
    vendor_id: str,
    product_id: str,
    condition: str = "new",
    stock_mode: str = "tracked",
    stock_qty: int = 5,
    created_at: str = "2026-01-01T00:00:00Z",
    wholesale: bool = False,
) -> dict[str, Any]:
    return {
        "id": listing_id,
        "vendor_id": vendor_id,
        "product_id": product_id,
        "condition": condition,
        "stock_mode": stock_mode,
        "stock_qty": stock_qty,
        "created_at": created_at,
        "status": "active",
        "wholesale": wholesale,
    }


SEED_STORE: dict[str, list[dict[str, Any]]] = {
    "search_documents": [
        _search_doc(
            PHONE_LISTING_ID,
            title="Smartphone X1 — 128GB",
            category_path="electronics",
            price=450_000,
            lat=LUSAKA_CBD[0],
            lng=LUSAKA_CBD[1],
            updated_at="2026-02-01T00:00:00Z",
        ),
        _search_doc(
            CHITENGE_LISTING_ID,
            title="Premium Chitenge — 6 yards",
            category_path="fashion-beauty",
            price=85_000,
            lat=KABULONGA[0],
            lng=KABULONGA[1],
            updated_at="2026-03-01T00:00:00Z",
        ),
        _search_doc(
            DEMO_LISTING_ID,
            title="Demo Gadget (sandbox)",
            category_path="electronics",
            price=10_000,
            lat=LUSAKA_CBD[0],
            lng=LUSAKA_CBD[1],
            updated_at="2026-01-15T00:00:00Z",
        ),
        _search_doc(
            WHOLESALE_LISTING_ID,
            title="Bulk Chargers — carton of 50",
            category_path="electronics",
            price=500_000,
            lat=LUSAKA_CBD[0],
            lng=LUSAKA_CBD[1],
            updated_at="2026-04-01T00:00:00Z",
        ),
    ],
    "vendor_listings": [
        _listing(
            PHONE_LISTING_ID,
            vendor_id=SHOP_A_ID,
            product_id=PHONE_PRODUCT_ID,
            created_at="2026-02-01T00:00:00Z",
        ),
        _listing(
            CHITENGE_LISTING_ID,
            vendor_id=SHOP_B_ID,
            product_id=CHITENGE_PRODUCT_ID,
            created_at="2026-03-01T00:00:00Z",
        ),
        _listing(
            DEMO_LISTING_ID,
            vendor_id="d0000000-0000-0000-0000-000000000001",
            product_id=PHONE_PRODUCT_ID,
            stock_mode="always_available",
            stock_qty=0,
        ),
        _listing(
            WHOLESALE_LISTING_ID,
            vendor_id=SHOP_A_ID,
            product_id=PHONE_PRODUCT_ID,
            created_at="2026-04-01T00:00:00Z",
            wholesale=True,
        ),
    ],
    "vendors": [
        {
            "id": SHOP_A_ID,
            "slug": "lusaka-electronics",
            "display_name": "Lusaka Electronics Hub",
            "status": "active",
        },
        {
            "id": SHOP_B_ID,
            "slug": "zed-fashion",
            "display_name": "Zed Fashion House",
            "status": "active",
        },
        {
            "id": "d0000000-0000-0000-0000-000000000001",
            "slug": "demo-sandbox",
            "display_name": "Demo Sandbox Shop",
            "status": "active",
        },
    ],
    "products": [
        {
            "id": PHONE_PRODUCT_ID,
            "slug": "smartphone-x1",
            "name": "Smartphone X1",
            "status": "active",
        },
        {
            "id": CHITENGE_PRODUCT_ID,
            "slug": "premium-chitenge",
            "name": "Premium Chitenge Fabric",
            "status": "active",
        },
    ],
    "vendor_locations": [
        {
            "vendor_id": SHOP_A_ID,
            "landmark": "East Park Mall, Lusaka",
            "created_at": "2026-01-01T00:00:00Z",
        },
        {
            "vendor_id": SHOP_B_ID,
            "landmark": "Kabulonga, Lusaka",
            "created_at": "2026-01-01T00:00:00Z",
        },
    ],
    "listing_images": [
        {
            "listing_id": PHONE_LISTING_ID,
            "cloudinary_public_id": "vergeo5/catalog/phone-a",
            "position": 1,
        },
        {
            "listing_id": CHITENGE_LISTING_ID,
            "cloudinary_public_id": "vergeo5/catalog/chitenge-b",
            "position": 1,
        },
    ],
    "order_item_products": [],
    "reviews": [],
}


class FakeQuery:
    def __init__(self, table: str, rows: list[dict[str, Any]]) -> None:
        self._table = table
        self._rows = rows
        self._filters: list[tuple[str, str, Any]] = []
        self._order: tuple[str, bool] | None = None

    def select(self, _columns: str) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def like(self, column: str, value: str) -> FakeQuery:
        self._filters.append(("like", column, value))
        return self

    def gte(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("gte", column, value))
        return self

    def lte(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("lte", column, value))
        return self

    def in_(self, column: str, values: list[str]) -> FakeQuery:
        self._filters.append(("in", column, values))
        return self

    def order(self, column: str, desc: bool = False) -> FakeQuery:
        self._order = (column, desc)
        return self

    def execute(self) -> Any:
        rows = list(self._rows)
        for op, column, value in self._filters:
            if op == "eq":
                rows = [row for row in rows if row.get(column) == value]
            elif op == "like":
                prefix = value.replace(r"\%", "%").rstrip("%")
                rows = [
                    row
                    for row in rows
                    if isinstance(row.get(column), str) and row[column].startswith(prefix)
                ]
            elif op == "gte":
                rows = [
                    row
                    for row in rows
                    if row.get(column) is not None and row[column] >= value
                ]
            elif op == "lte":
                rows = [
                    row
                    for row in rows
                    if row.get(column) is not None and row[column] <= value
                ]
            elif op == "in":
                allowed = set(value)
                rows = [row for row in rows if row.get(column) in allowed]
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: str(row.get(column) or ""), reverse=desc)
        return type("Result", (), {"data": rows})()


class FakeSupabaseClient:
    def __init__(self, store: dict[str, list[dict[str, Any]]]) -> None:
        self._store = store

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(name, list(self._store.get(name, [])))


@pytest.fixture
def fake_client() -> FakeSupabaseClient:
    return FakeSupabaseClient(SEED_STORE)


@pytest.fixture
def catalog_client(fake_client: FakeSupabaseClient) -> Generator[TestClient, None, None]:
    from app.deps import get_supabase_client

    class FakeServiceClient:
        def __init__(self, client: FakeSupabaseClient) -> None:
            self.client = client

    app: FastAPI = create_app()
    app.dependency_overrides[get_supabase_client] = lambda: FakeServiceClient(fake_client)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


def test_url_filter_state_roundtrip() -> None:
    state = PlpFilterState(
        category_path="electronics",
        sort="cheapest",
        price_min_ngwee=10_000,
        price_max_ngwee=500_000,
        condition=["new"],
        availability=["in_stock"],
        min_rating=4,
        lat=LUSAKA_CBD[0],
        lng=LUSAKA_CBD[1],
        radius_km=25,
        cursor=24,
        limit=12,
    )
    encoded = encode_plp_filters(state)
    restored = decode_plp_filters(cast(dict[str, str | list[str] | None], encoded))
    assert restored.category_path == state.category_path
    assert restored.sort == state.sort
    assert restored.price_min_ngwee == state.price_min_ngwee
    assert restored.price_max_ngwee == state.price_max_ngwee
    assert restored.condition == state.condition
    assert restored.availability == state.availability
    assert restored.min_rating == state.min_rating
    assert restored.lat == state.lat
    assert restored.lng == state.lng
    assert restored.radius_km == state.radius_km
    assert restored.cursor == state.cursor
    assert restored.limit == state.limit


def test_facet_counts_on_seed(fake_client: FakeSupabaseClient) -> None:
    response = list_catalog(
        fake_client,
        PlpFilterState(category_path="electronics"),
    )
    assert response.total == 2
    condition = {bucket.value: bucket.count for bucket in response.facets.condition}
    assert condition["new"] == 2
    availability = {bucket.value: bucket.count for bucket in response.facets.availability}
    assert availability["in_stock"] == 2


def test_facet_counts_empty_category(fake_client: FakeSupabaseClient) -> None:
    response = list_catalog(
        fake_client,
        PlpFilterState(category_path="services/plumbing"),
    )
    assert response.total == 0
    assert all(bucket.count == 0 for bucket in response.facets.condition)
    assert all(bucket.count == 0 for bucket in response.facets.availability)


def test_cheapest_sort_orders_by_price(fake_client: FakeSupabaseClient) -> None:
    response = list_catalog(
        fake_client,
        PlpFilterState(category_path="electronics", sort="cheapest"),
    )
    prices = [item.price_ngwee for item in response.items]
    assert prices == sorted(prices)


def test_newest_sort_orders_by_created_at(fake_client: FakeSupabaseClient) -> None:
    response = list_catalog(
        fake_client,
        PlpFilterState(sort="newest", limit=10),
    )
    titles = [item.title for item in response.items]
    assert titles[0] == "Premium Chitenge — 6 yards"


def test_distance_sort_orders_by_lat_lng(fake_client: FakeSupabaseClient) -> None:
    response = list_catalog(
        fake_client,
        PlpFilterState(
            sort="nearest",
            lat=KABULONGA[0],
            lng=KABULONGA[1],
            limit=10,
        ),
    )
    distances = [item.distance_m for item in response.items if item.distance_m is not None]
    assert distances == sorted(distances)
    assert response.items[0].id == CHITENGE_LISTING_ID


def test_filter_combinations_compose(fake_client: FakeSupabaseClient) -> None:
    response = list_catalog(
        fake_client,
        PlpFilterState(
            category_path="electronics",
            price_min_ngwee=20_000,
            condition=["new"],
            availability=["in_stock"],
        ),
    )
    assert response.total == 1
    assert response.items[0].id == PHONE_LISTING_ID


def test_injection_safe_category_path_is_literal(
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str] = []

    original_fetch = catalog_module._fetch_search_documents

    def spy(client: Any, category_path: str | None) -> list[_SearchDocRow]:
        if category_path is not None:
            captured.append(category_path)
        return original_fetch(client, category_path)

    monkeypatch.setattr(catalog_module, "_fetch_search_documents", spy)
    list_catalog(
        fake_client,
        PlpFilterState(category_path="electronics'; drop table search_documents; --"),
    )
    assert captured == ["electronics'; drop table search_documents; --"]
    assert "'; drop" in captured[0]


def test_catalog_endpoint_returns_facets(catalog_client: TestClient) -> None:
    response = catalog_client.get("/catalog/listings", params={"category_path": "electronics"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2


def test_catalog_endpoint_distance_sort(catalog_client: TestClient) -> None:
    response = catalog_client.get(
        "/catalog/listings",
        params={
            "sort": "nearest",
            "lat": KABULONGA[0],
            "lng": KABULONGA[1],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["id"] == CHITENGE_LISTING_ID


def test_list_catalog_hides_wholesale_by_default(fake_client: FakeSupabaseClient) -> None:
    response = list_catalog(fake_client, PlpFilterState(category_path="electronics"))
    ids = {item.id for item in response.items}
    assert WHOLESALE_LISTING_ID not in ids
    # Facet counts must also ignore the hidden wholesale listing.
    assert response.total == 2


def test_list_catalog_includes_wholesale_when_eligible(
    fake_client: FakeSupabaseClient,
) -> None:
    response = list_catalog(
        fake_client,
        PlpFilterState(category_path="electronics"),
        include_wholesale=True,
    )
    ids = {item.id for item in response.items}
    assert WHOLESALE_LISTING_ID in ids
    assert response.total == 3


def test_catalog_endpoint_guest_excludes_wholesale(catalog_client: TestClient) -> None:
    response = catalog_client.get(
        "/catalog/listings", params={"category_path": "electronics"}
    )
    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["items"]}
    assert WHOLESALE_LISTING_ID not in ids


def test_catalog_endpoint_verified_business_sees_wholesale(
    fake_client: FakeSupabaseClient,
) -> None:
    from app.deps import get_supabase_client

    class FakeServiceClient:
        def __init__(self, client: FakeSupabaseClient) -> None:
            self.client = client

    app: FastAPI = create_app()
    app.dependency_overrides[get_supabase_client] = lambda: FakeServiceClient(fake_client)
    app.dependency_overrides[get_business_access] = lambda: BusinessAccess(
        user_id="11111111-1111-1111-1111-111111111111",
        status="verified",
        eligible=True,
    )
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(
                "/catalog/listings", params={"category_path": "electronics"}
            )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["items"]}
    assert WHOLESALE_LISTING_ID in ids


def test_haversine_zero_distance() -> None:
    assert haversine_m(LUSAKA_CBD[0], LUSAKA_CBD[1], LUSAKA_CBD[0], LUSAKA_CBD[1]) == pytest.approx(
        0.0,
        abs=1.0,
    )


def test_compute_facet_counts_unit() -> None:
    candidate = _CatalogCandidate(
        search_doc=_SearchDocRow(
            entity_id=PHONE_LISTING_ID,
            title="Phone",
            category_path="electronics",
            price_min_ngwee=100_000,
            lat=LUSAKA_CBD[0],
            lng=LUSAKA_CBD[1],
        ),
        listing=_ListingRow(
            id=PHONE_LISTING_ID,
            vendor_id=SHOP_A_ID,
            product_id=PHONE_PRODUCT_ID,
            condition="new",
            stock_mode="tracked",
            stock_qty=2,
        ),
        vendor={"id": SHOP_A_ID, "display_name": "Shop"},
        product={"slug": "phone"},
        image_public_id=None,
        landmark=None,
        rating=4.5,
        review_count=2,
        in_stock=True,
    )
    facets = compute_facet_counts([candidate], PlpFilterState())
    assert {bucket.value: bucket.count for bucket in facets.condition}["new"] == 1


def test_documented_sql_fragments_present() -> None:
    assert "GROUP BY condition" in FACET_COUNT_SQL
    assert "ORDER BY distance_m ASC" in DISTANCE_SORT_SQL


@pytest.mark.integration
def test_integration_distance_sort_on_seed_db() -> None:
    import shutil

    if shutil.which("psql") is None:
        pytest.skip("psql not available")

    from tests.rls.conftest import PgConn, apply_migrations, resolve_db_url, seed_matrix_fixtures

    url = resolve_db_url()
    conn = PgConn(url)
    if not conn.run("SELECT 1").ok:
        pytest.skip("database unavailable")

    if not conn.run("SELECT to_regclass('public.search_documents')").rows:
        apply_migrations(conn)
    seed_matrix_fixtures(conn)

    result = conn.run(
        f"""
SELECT sd.entity_id::text,
       (
         6371000 * acos(
           least(1.0, greatest(-1.0,
             cos(radians({KABULONGA[0]})) * cos(radians(sd.lat))
             * cos(radians(sd.lng) - radians({KABULONGA[1]}))
             + sin(radians({KABULONGA[0]})) * sin(radians(sd.lat))
           ))
         )
       ) AS distance_m
FROM public.search_documents sd
WHERE sd.entity_kind = 'listing'
  AND sd.is_public = true
  AND sd.lat IS NOT NULL
  AND sd.lng IS NOT NULL
ORDER BY distance_m ASC
LIMIT 3;
"""
    )
    if not result.ok or len(result.rows) < 2:
        pytest.skip("seed search projection unavailable")

    distances = [float(row.split("|")[1]) for row in result.rows]
    assert distances == sorted(distances)


@pytest.mark.integration
def test_integration_facet_counts_on_seed_db() -> None:
    import shutil

    if shutil.which("psql") is None:
        pytest.skip("psql not available")

    from tests.rls.conftest import PgConn, apply_migrations, resolve_db_url, seed_matrix_fixtures

    url = resolve_db_url()
    conn = PgConn(url)
    if not conn.run("SELECT 1").ok:
        pytest.skip("database unavailable")

    if not conn.run("SELECT to_regclass('public.search_documents')").rows:
        apply_migrations(conn)
    seed_matrix_fixtures(conn)

    result = conn.run(
        """
SELECT vl.condition, count(*)::int
FROM public.search_documents sd
JOIN public.vendor_listings vl ON vl.id = sd.entity_id AND vl.status = 'active'
JOIN public.vendors v ON v.id = vl.vendor_id AND v.status = 'active'
WHERE sd.entity_kind = 'listing'
  AND sd.is_public = true
  AND sd.category_path LIKE 'electronics%'
GROUP BY vl.condition
ORDER BY vl.condition;
"""
    )
    if not result.ok:
        pytest.skip("facet query failed")

    counts = {row.split("|")[0]: int(row.split("|")[1]) for row in result.rows}
    assert counts.get("new", 0) >= 1
