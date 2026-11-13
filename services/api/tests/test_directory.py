from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
from typing import Any
from unittest.mock import patch

import pytest
from app.main import create_app
from app.routers import directory as directory_module
from app.services.business.access import BusinessAccess, get_business_access
from app.services.vendors.hours import LUSAKA_TZ
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient

ACTIVE_VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
OTHER_VENDOR_UUID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
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
    commercial_tier: str | None = None,
    description: str = "Electronics and phones in Lusaka.",
    landmark: str = "East Park Mall, Lusaka",
    lat: float = LUSAKA_CBD[0],
    lng: float = LUSAKA_CBD[1],
    whatsapp_msisdn: str | None = None,
) -> dict[str, Any]:
    return {
        "id": vendor_id,
        "slug": slug,
        "display_name": display_name,
        "description": description,
        "logo_url": "https://example.com/logo.png",
        "whatsapp_msisdn": whatsapp_msisdn,
        "status": status,
        "kyc_tier": kyc_tier,
        "commercial_tier": commercial_tier,
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
    wholesale: bool = False,
) -> dict[str, Any]:
    return {
        "id": listing_id,
        "vendor_id": vendor_id,
        "product_id": product["id"],
        "title_override": None,
        "price_ngwee": price_ngwee,
        "condition": "new",
        "stock_mode": "tracked",
        "stock_qty": 5,
        "status": "active",
        "wholesale": wholesale,
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
        self.services: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self.orders: list[dict[str, Any]] = []
        self.kyc_records: list[dict[str, Any]] = []

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

    def test_unknown_slug_still_404s(self, client: TestClient, store: FakeSupabaseStore) -> None:
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
        # No contact number set on this vendor → field is null.
        assert payload["vendor"]["whatsapp_msisdn"] is None
        # No orders seeded → count is zero (not an error).
        assert payload["vendor"]["order_count"] == 0
        assert len(payload["listings"]) == 1
        assert payload["listings"][0]["product_slug"] == "itel-a70"
        assert payload["reviews_summary"]["rating_count"] == 1
        assert payload["reviews_summary"]["rating_avg"] == 5.0
        # Single-branch vendor: the locations array mirrors the singular location.
        assert [loc["landmark"] for loc in payload["vendor"]["locations"]] == [
            "East Park Mall, Lusaka"
        ]

    def test_profile_listing_exposes_category_for_storefront_chips(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        seed_active_vendor(store)
        store.vendor_listings[0]["products"] = {
            **store.vendor_listings[0]["products"],
            "categories": {"slug": "phones", "name": "Phones"},
        }
        payload = client.get("/directory/tech-hub-lusaka").json()
        assert payload["listings"][0]["category_slug"] == "phones"
        assert payload["listings"][0]["category_name"] == "Phones"

    def test_profile_includes_standalone_made_to_order_listing(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        seed_active_vendor(store)
        standalone_id = "33333333-3333-3333-3333-333333333333"
        store.vendor_listings.append(
            {
                "id": standalone_id,
                "vendor_id": ACTIVE_VENDOR_ID,
                "title_override": "Custom chitenge curtains",
                "price_ngwee": 320_000,
                "condition": "new",
                "product_class": "E",
                "sale_unit": "metre",
                "unit_step_milli": 500,
                "min_steps": 4,
                "fulfilment_mode": "made_to_order",
                "lead_time_days": 7,
                "vendor_capacity_per_week": 8,
                "stock_mode": "tracked",
                "stock_qty": 0,
                "moq": 1,
                "status": "active",
                "wholesale": False,
                "products": None,
            }
        )
        store.listing_images.append(
            {
                "listing_id": standalone_id,
                "cloudinary_public_id": "vergeo5/listings/custom-curtains",
                "position": 1,
            }
        )

        response = client.get("/directory/tech-hub-lusaka")

        assert response.status_code == 200
        listing = next(item for item in response.json()["listings"] if item["id"] == standalone_id)
        assert listing["title"] == "Custom chitenge curtains"
        assert listing["product_slug"] is None
        assert listing["product_class"] == "E"
        assert listing["sale_unit"] == "metre"
        assert listing["unit_step_milli"] == 500
        assert listing["min_steps"] == 4
        assert listing["lead_time_days"] == 7
        assert listing["in_stock"] is True

    def test_profile_marks_stock_below_minimum_purchase_out_of_stock(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        seed_active_vendor(store)
        store.vendor_listings[0].update(
            {
                "min_steps": 6,
                "moq": 1,
                "stock_qty": 5,
            }
        )

        response = client.get("/directory/tech-hub-lusaka")

        assert response.status_code == 200
        assert response.json()["listings"][0]["in_stock"] is False

    def test_profile_omits_canonical_listing_with_missing_product_relation(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        seed_active_vendor(store)
        store.vendor_listings[0]["products"] = None

        response = client.get("/directory/tech-hub-lusaka")

        assert response.status_code == 200
        assert response.json()["listings"] == []

    def test_profile_exposes_commercial_tier(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        seed_active_vendor(store)
        store.vendors[0]["commercial_tier"] = "gold"

        response = client.get("/directory/tech-hub-lusaka")
        assert response.status_code == 200
        assert response.json()["vendor"]["commercial_tier"] == "gold"

    def test_directory_list_includes_commercial_tier(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        seed_active_vendor(store)
        store.vendors[0]["commercial_tier"] = "silver"

        response = client.get("/directory")
        assert response.status_code == 200
        assert response.json()["items"][0]["commercial_tier"] == "silver"

    def test_profile_exposes_whatsapp_contact(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        seed_active_vendor(store)
        store.vendors[0]["whatsapp_msisdn"] = "260977123456"

        response = client.get("/directory/tech-hub-lusaka")
        assert response.status_code == 200
        # Returned as E.164 digits so the storefront can build wa.me/<msisdn>.
        assert response.json()["vendor"]["whatsapp_msisdn"] == "260977123456"

    def test_profile_counts_completed_orders(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        seed_active_vendor(store)
        # Only delivered/completed orders for THIS vendor count.
        store.orders = [
            {"id": "o1", "vendor_id": ACTIVE_VENDOR_ID, "status": "delivered"},
            {"id": "o2", "vendor_id": ACTIVE_VENDOR_ID, "status": "completed"},
            {"id": "o3", "vendor_id": ACTIVE_VENDOR_ID, "status": "placed"},
            {"id": "o4", "vendor_id": ACTIVE_VENDOR_ID, "status": "cancelled"},
            {"id": "o5", "vendor_id": OTHER_VENDOR_UUID, "status": "completed"},
        ]

        response = client.get("/directory/tech-hub-lusaka")
        assert response.status_code == 200
        assert response.json()["vendor"]["order_count"] == 2

    def test_profile_exposes_cover_image(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        seed_active_vendor(store)
        assert store.vendors[0].get("cover_url") is None
        # Default: no cover set → null (storefront falls back to the gradient).
        default = client.get("/directory/tech-hub-lusaka")
        assert default.json()["vendor"]["cover_url"] is None

        store.vendors[0]["cover_url"] = "https://res.cloudinary.com/demo/cover.png"
        response = client.get("/directory/tech-hub-lusaka")
        assert response.status_code == 200
        assert response.json()["vendor"]["cover_url"] == "https://res.cloudinary.com/demo/cover.png"

    def test_profile_returns_all_branch_locations(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        seed_active_vendor(store)
        store.vendors[0]["vendor_locations"].append(
            {
                "landmark": "Manda Hill, Lusaka",
                "lat": LUSAKA_CBD[0],
                "lng": LUSAKA_CBD[1],
                "hours": {"mon": "10:00-18:00"},
            }
        )

        response = client.get("/directory/tech-hub-lusaka")
        assert response.status_code == 200
        payload = response.json()
        assert [loc["landmark"] for loc in payload["vendor"]["locations"]] == [
            "East Park Mall, Lusaka",
            "Manda Hill, Lusaka",
        ]
        # `location` (singular) still returns the first branch for backward compat.
        assert payload["vendor"]["location"]["landmark"] == "East Park Mall, Lusaka"

    def test_profile_returns_vendor_services_and_events(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        seed_active_vendor(store)
        store.services = [
            {
                "id": "svc-1",
                "vendor_id": ACTIVE_VENDOR_ID,
                "title": "Deep clean",
                "category": "cleaning",
                "from_price_ngwee": 50000,
                "portfolio_images": ["services/clean-1"],
                "status": "active",
            },
            {
                "id": "svc-2",
                "vendor_id": ACTIVE_VENDOR_ID,
                "title": "Draft service (excluded)",
                "status": "draft",
            },
        ]
        store.events = [
            {
                "id": "evt-1",
                "organiser_vendor_id": ACTIVE_VENDOR_ID,
                "slug": "summer-fest",
                "title": "Summer Fest",
                "images": ["events/fest-1"],
                "status": "published",
            },
            {
                "id": "evt-past",
                "organiser_vendor_id": ACTIVE_VENDOR_ID,
                "slug": "last-year",
                "title": "Last year's fair",
                "images": [],
                "status": "published",
            },
        ]
        store.event_instances = [  # type: ignore[attr-defined]
            {"event_id": "evt-1", "starts_at": "2099-01-10T16:00:00+00:00"},
            {"event_id": "evt-past", "starts_at": "2020-01-10T16:00:00+00:00"},
        ]

        response = client.get("/directory/tech-hub-lusaka")
        assert response.status_code == 200
        payload = response.json()
        # Only the active service is returned; the draft is excluded.
        assert [s["title"] for s in payload["services"]] == ["Deep clean"]
        assert payload["services"][0]["from_price_ngwee"] == 50000
        assert payload["services"][0]["image_public_id"] == "services/clean-1"
        # Only events with an upcoming date are live; past-only events are hidden.
        assert [e["slug"] for e in payload["events"]] == ["summer-fest"]
        assert payload["events"][0]["image_public_id"] == "events/fest-1"
        assert payload["events"][0]["next_starts_at"].startswith("2099-01-10")


class TestVendorProfileWholesaleGating:
    """Wholesale-only listings are hidden from a vendor's public storefront profile
    unless the caller is a verified business buyer (audit gating fix)."""

    def _seed(self, store: FakeSupabaseStore) -> None:
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
            ),
            _listing_row(
                listing_id=LISTING_B,
                vendor_id=ACTIVE_VENDOR_ID,
                product=_product_row(
                    product_id=PRODUCT_B,
                    slug="bulk-chargers",
                    name="Bulk Chargers Carton",
                    category_id=CATEGORY_ELECTRONICS,
                    path="electronics/accessories",
                ),
                price_ngwee=1_200_000,
                wholesale=True,
            ),
        ]

    def test_build_hides_wholesale_by_default(self, store: FakeSupabaseStore) -> None:
        self._seed(store)
        result = directory_module.get_vendor_profile(store, "tech-hub-lusaka")
        assert not isinstance(result, RedirectResponse)
        assert {listing.product_slug for listing in result.listings} == {"itel-a70"}

    def test_build_includes_wholesale_when_eligible(self, store: FakeSupabaseStore) -> None:
        self._seed(store)
        result = directory_module.get_vendor_profile(
            store, "tech-hub-lusaka", include_wholesale=True
        )
        assert not isinstance(result, RedirectResponse)
        assert {listing.product_slug for listing in result.listings} == {
            "itel-a70",
            "bulk-chargers",
        }

    def test_endpoint_guest_hides_wholesale(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        self._seed(store)
        response = client.get("/directory/tech-hub-lusaka")
        assert response.status_code == 200
        slugs = {listing["product_slug"] for listing in response.json()["listings"]}
        assert slugs == {"itel-a70"}

    def test_endpoint_verified_business_sees_wholesale(self, store: FakeSupabaseStore) -> None:
        self._seed(store)
        app: FastAPI = create_app()
        app.dependency_overrides[get_business_access] = lambda: BusinessAccess(
            user_id="11111111-1111-1111-1111-111111111111",
            status="verified",
            eligible=True,
        )

        class FakeServiceClient:
            def __init__(self) -> None:
                self.client = store

        with patch("app.deps.get_supabase_service_client", return_value=FakeServiceClient()):
            with TestClient(app, raise_server_exceptions=False) as test_client:
                response = test_client.get("/directory/tech-hub-lusaka")
        app.dependency_overrides.clear()
        assert response.status_code == 200
        slugs = {listing["product_slug"] for listing in response.json()["listings"]}
        assert slugs == {"itel-a70", "bulk-chargers"}


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


class TestOpenNowFilter:
    """R02-P10 wiring. The filter is opt-in and must not disturb the default."""

    # Monday noon Lusaka — stable reference clock for time-dependent assertions.
    _FIXED_NOW = datetime(2026, 8, 3, 12, 0, tzinfo=LUSAKA_TZ)

    @pytest.fixture(autouse=True)
    def _freeze_open_now_clock(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Directory open_now uses server clock; freeze it so CI never hits the
        23:59 close boundary of the all-day test hours."""
        fixed_now = self._FIXED_NOW

        class _FixedDatetime(datetime):
            @classmethod
            def now(cls, tz: Any = None) -> datetime:  # type: ignore[override]
                if tz is not None:
                    return fixed_now.astimezone(tz)
                return fixed_now.replace(tzinfo=None)

        monkeypatch.setattr(directory_module, "datetime", _FixedDatetime)

    def _seed_two_vendors(self, store: FakeSupabaseStore) -> None:
        always = _vendor_row(
            vendor_id="11111111-1111-1111-1111-111111111111",
            slug="always-open",
            display_name="Always Open",
        )
        # 24:00 closes at end-of-day per hours parser (23:59:59).
        always["vendor_locations"][0]["hours"] = {
            day: "00:00-24:00" for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
        }
        no_hours = _vendor_row(
            vendor_id="22222222-2222-2222-2222-222222222222",
            slug="hours-unknown",
            display_name="Hours Unknown",
        )
        no_hours["vendor_locations"][0]["hours"] = {}
        store.vendors = [always, no_hours]

    def test_default_response_includes_both_vendors(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        """Without the flag, nothing changes — the filter cannot silently
        shrink an existing result set."""
        self._seed_two_vendors(store)
        response = client.get("/directory")
        assert response.status_code == 200
        slugs = {item["slug"] for item in response.json()["items"]}
        assert slugs == {"always-open", "hours-unknown"}

    def test_open_now_excludes_a_vendor_with_no_published_hours(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        """An unknown is not a yes: `open_now=true` answers 'shops I can walk
        into now', so a vendor whose hours nobody published is excluded rather
        than assumed open."""
        self._seed_two_vendors(store)
        response = client.get("/directory?open_now=true")
        assert response.status_code == 200
        slugs = {item["slug"] for item in response.json()["items"]}
        assert slugs == {"always-open"}

    def test_profile_reports_open_now_and_distinguishes_unknown_from_shut(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        self._seed_two_vendors(store)

        open_profile = client.get("/directory/always-open")
        assert open_profile.status_code == 200
        assert open_profile.json()["vendor"]["location"]["open_now"] is True

        unknown_profile = client.get("/directory/hours-unknown")
        assert unknown_profile.status_code == 200
        # None, not False — we do not know it is shut, and claiming so would
        # assert something the data cannot support.
        assert unknown_profile.json()["vendor"]["location"]["open_now"] is None

    def test_any_open_branch_counts(self) -> None:
        """A vendor with a shut office and an open stall is, to a customer
        looking for somewhere to buy, open."""
        all_week = {day: "00:00-24:00" for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}
        row = {"vendor_locations": [{"hours": {}}, {"hours": all_week}]}
        assert directory_module._any_branch_open_now(row, now=self._FIXED_NOW) is True

    def test_no_branches_is_not_open(self) -> None:
        assert directory_module._any_branch_open_now({"vendor_locations": []}) is False
        assert directory_module._any_branch_open_now({}) is False


class TestBusinessHome:
    """Business Home (/v/[slug]): customer-first fields on the vendor profile."""

    def _other_shop_listing(
        self,
        *,
        listing_id: str,
        vendor_id: str = OTHER_VENDOR_UUID,
        price_ngwee: int,
        vendor_status: str = "active",
        wholesale: bool = False,
    ) -> dict[str, Any]:
        return {
            "id": listing_id,
            "vendor_id": vendor_id,
            "product_id": PRODUCT_A,
            "price_ngwee": price_ngwee,
            "status": "active",
            "wholesale": wholesale,
            "vendors": {"status": vendor_status},
        }

    def test_listing_reports_other_shops_and_lowest_price(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        seed_active_vendor(store)
        store.vendor_listings[0]["vendors"] = {"status": "active"}
        store.vendor_listings += [
            self._other_shop_listing(listing_id="o-1", price_ngwee=430_000),
            self._other_shop_listing(listing_id="o-2", price_ngwee=470_000),
            # Suspended shop and wholesale-only offers never count for a guest.
            self._other_shop_listing(
                listing_id="o-3",
                vendor_id=SUSPENDED_VENDOR_ID,
                price_ngwee=100_000,
                vendor_status="suspended",
            ),
            self._other_shop_listing(
                listing_id="o-4",
                vendor_id="dddddddd-dddd-dddd-dddd-dddddddddddd",
                price_ngwee=90_000,
                wholesale=True,
            ),
        ]

        payload = client.get("/directory/tech-hub-lusaka").json()
        listing = next(item for item in payload["listings"] if item["id"] == LISTING_A)
        assert listing["other_offers_count"] == 1
        assert listing["other_min_price_ngwee"] == 430_000

    def test_own_listing_alone_has_no_compare_offers(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        seed_active_vendor(store)
        payload = client.get("/directory/tech-hub-lusaka").json()
        assert payload["listings"][0]["other_offers_count"] == 0
        assert payload["listings"][0]["other_min_price_ngwee"] is None

    def test_lusaka_branch_offers_delivery_and_pickup(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        seed_active_vendor(store)
        listing = client.get("/directory/tech-hub-lusaka").json()["listings"][0]
        assert listing["delivery_available"] is True
        assert listing["pickup_available"] is True

    def test_out_of_metro_branch_is_pickup_only(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        seed_active_vendor(store)
        store.vendors = [_vendor_row(landmark="Kitwe Market", lat=-12.8, lng=28.2)]
        listing = client.get("/directory/tech-hub-lusaka").json()["listings"][0]
        assert listing["delivery_available"] is False
        assert listing["pickup_available"] is True

    def test_branch_schedule_is_normalised_for_display(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        seed_active_vendor(store)
        store.vendors[0]["vendor_locations"][0]["hours"] = {
            "tue": {"open": "08:00", "close": "17:00", "closed": False},
            "sun": {"open": "08:00", "close": "17:00", "closed": True},
            "mon": "09:00-17:00",
        }
        location = client.get("/directory/tech-hub-lusaka").json()["vendor"]["location"]
        assert location["schedule"] == [
            {"day": "mon", "opens": "09:00", "closes": "17:00"},
            {"day": "tue", "opens": "08:00", "closes": "17:00"},
        ]

    def test_clips_and_offers_hidden_while_flags_off(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        seed_active_vendor(store)
        store.video_clips = [  # type: ignore[attr-defined]
            {
                "id": "clip-1",
                "vendor_id": ACTIVE_VENDOR_ID,
                "status": "published",
                "poster_url": "https://res.cloudinary.com/x/poster.jpg",
                "caption": "New stock",
                "duration_s": 20,
                "published_at": "2026-11-01T00:00:00Z",
            }
        ]
        payload = client.get("/directory/tech-hub-lusaka").json()
        assert payload["clips"] == []
        assert payload["offers_enabled"] is False

    def test_clips_row_shows_only_published_clips_when_flag_on(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        seed_active_vendor(store)
        store.feature_flags = [  # type: ignore[attr-defined]
            {"flag": "clips", "enabled": True},
            {"flag": "business_offers", "enabled": True},
        ]
        store.video_clips = [  # type: ignore[attr-defined]
            {
                "id": "clip-1",
                "vendor_id": ACTIVE_VENDOR_ID,
                "status": "published",
                "poster_url": "https://res.cloudinary.com/x/poster.jpg",
                "caption": "New stock",
                "duration_s": 20,
                "published_at": "2026-11-01T00:00:00Z",
            },
            {
                "id": "clip-draft",
                "vendor_id": ACTIVE_VENDOR_ID,
                "status": "pending_review",
                "published_at": None,
            },
            {
                "id": "clip-other",
                "vendor_id": OTHER_VENDOR_UUID,
                "status": "published",
                "published_at": "2026-11-02T00:00:00Z",
            },
        ]
        payload = client.get("/directory/tech-hub-lusaka").json()
        assert [clip["id"] for clip in payload["clips"]] == ["clip-1"]
        # Creator-clip seam: each clip names its author kind and profile slug.
        assert payload["clips"][0]["author"] == {
            "kind": "business",
            "slug": "tech-hub-lusaka",
            "display_name": "Tech Hub Lusaka",
        }
        assert payload["offers_enabled"] is True

    def test_services_carry_fixed_booking_price_only_when_bookable(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        seed_active_vendor(store)
        store.services = [
            {
                "id": "svc-1",
                "vendor_id": ACTIVE_VENDOR_ID,
                "title": "Phone screen repair",
                "category": "repairs",
                "from_price_ngwee": 25_000,
                "portfolio_images": [],
                "status": "active",
                "service_area": "Lusaka",
                "bookable": True,
                "booking_price_ngwee": 30_000,
            },
            {
                "id": "svc-2",
                "vendor_id": ACTIVE_VENDOR_ID,
                "title": "Data recovery",
                "category": "repairs",
                "from_price_ngwee": None,
                "portfolio_images": [],
                "status": "active",
                "bookable": False,
                "booking_price_ngwee": 99_000,
            },
        ]
        services = {s["id"]: s for s in client.get("/directory/tech-hub-lusaka").json()["services"]}
        assert services["svc-1"]["bookable"] is True
        assert services["svc-1"]["booking_price_ngwee"] == 30_000
        assert services["svc-1"]["service_area"] == "Lusaka"
        assert services["svc-2"]["bookable"] is False
        assert services["svc-2"]["booking_price_ngwee"] is None


class TestBusinessHomeElsewhere:
    """GET /directory/{slug}/elsewhere — related items from OTHER shops only."""

    def _seed(self, store: FakeSupabaseStore) -> None:
        seed_active_vendor(store)
        store.vendor_listings[0]["products"]["category_id"] = CATEGORY_ELECTRONICS
        other = {"slug": "phone-planet", "display_name": "Phone Planet", "status": "active"}
        store.products = [  # type: ignore[attr-defined]
            {
                "id": PRODUCT_A,
                "slug": "itel-a70",
                "name": "Itel A70",
                "status": "active",
                "category_id": CATEGORY_ELECTRONICS,
            },
            {
                "id": PRODUCT_B,
                "slug": "tecno-spark",
                "name": "Tecno Spark",
                "status": "active",
                "category_id": CATEGORY_ELECTRONICS,
            },
        ]
        base = {
            "status": "active",
            "stock_mode": "tracked",
            "stock_qty": 3,
            "min_steps": 1,
            "moq": 1,
            "product_class": "A",
            "fulfilment_mode": "stocked",
        }
        store.vendor_listings += [
            # Same product as the shop's own listing: covered by compare, not here.
            {
                **base,
                "id": "x-1",
                "product_id": PRODUCT_A,
                "vendor_id": OTHER_VENDOR_UUID,
                "price_ngwee": 400_000,
                "wholesale": False,
                "vendors": other,
            },
            {
                **base,
                "id": "x-2",
                "product_id": PRODUCT_B,
                "vendor_id": OTHER_VENDOR_UUID,
                "price_ngwee": 300_000,
                "wholesale": False,
                "vendors": other,
            },
            {
                **base,
                "id": "x-3",
                "product_id": PRODUCT_B,
                "vendor_id": OTHER_VENDOR_UUID,
                "price_ngwee": 100_000,
                "wholesale": True,
                "vendors": other,
            },
            {
                **base,
                "id": "x-4",
                "product_id": PRODUCT_B,
                "vendor_id": SUSPENDED_VENDOR_ID,
                "price_ngwee": 50_000,
                "wholesale": False,
                "vendors": {"slug": "gone", "display_name": "Gone", "status": "suspended"},
            },
        ]
        store.services = [
            {
                "id": "own-s",
                "vendor_id": ACTIVE_VENDOR_ID,
                "title": "Screen repair",
                "category": "repairs",
                "status": "active",
            },
            {
                "id": "other-s",
                "vendor_id": OTHER_VENDOR_UUID,
                "title": "Battery swap",
                "category": "repairs",
                "status": "active",
                "from_price_ngwee": 15_000,
                "bookable": False,
                "portfolio_images": [],
                "vendors": other,
            },
            {
                "id": "other-cat",
                "vendor_id": OTHER_VENDOR_UUID,
                "title": "Plumbing",
                "category": "plumbing",
                "status": "active",
                "vendors": other,
            },
        ]
        store.events = [
            {
                "id": "own-e",
                "organiser_vendor_id": ACTIVE_VENDOR_ID,
                "slug": "own",
                "title": "Own launch",
                "status": "published",
                "images": [],
                "vendors": {"slug": "tech-hub-lusaka", "display_name": "Tech", "status": "active"},
            },
            {
                "id": "other-e",
                "organiser_vendor_id": OTHER_VENDOR_UUID,
                "slug": "expo",
                "title": "Phone Expo",
                "status": "published",
                "images": [],
                "vendors": other,
            },
        ]
        store.event_instances = [  # type: ignore[attr-defined]
            {"event_id": "own-e", "starts_at": "2099-02-01T10:00:00+00:00"},
            {"event_id": "other-e", "starts_at": "2099-03-01T10:00:00+00:00"},
        ]

    def test_returns_only_other_active_shops_retail_items(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        self._seed(store)
        response = client.get("/directory/tech-hub-lusaka/elsewhere")
        assert response.status_code == 200
        payload = response.json()
        assert [(p["listing_id"], p["price_ngwee"]) for p in payload["products"]] == [
            ("x-2", 300_000)
        ]
        assert payload["products"][0]["vendor_slug"] == "phone-planet"
        assert [s["id"] for s in payload["services"]] == ["other-s"]
        assert [e["slug"] for e in payload["events"]] == ["expo"]

    def test_unknown_or_inactive_shop_is_404(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        self._seed(store)
        store.vendors[0]["status"] = "suspended"
        assert client.get("/directory/tech-hub-lusaka/elsewhere").status_code == 404
        assert client.get("/directory/nobody/elsewhere").status_code == 404

    def test_mutations_are_not_allowed(self, client: TestClient, store: FakeSupabaseStore) -> None:
        self._seed(store)
        assert client.post("/directory/tech-hub-lusaka/elsewhere").status_code == 405

    def test_product_focus_narrows_to_that_category_and_skips_that_product(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        self._seed(store)
        on_itel = client.get("/directory/tech-hub-lusaka/elsewhere?product=itel-a70").json()
        assert [p["listing_id"] for p in on_itel["products"]] == ["x-2"]
        on_tecno = client.get("/directory/tech-hub-lusaka/elsewhere?product=tecno-spark").json()
        # The product being viewed never appears in its own "other shops" rail.
        assert on_tecno["products"] == []

    def test_service_focus_uses_that_service_category_and_ignores_bad_ids(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        self._seed(store)
        unknown = "dddddddd-dddd-dddd-dddd-dddddddddddd"
        focused = client.get(f"/directory/tech-hub-lusaka/elsewhere?service={unknown}")
        assert focused.status_code == 200
        assert focused.json()["services"] == []
        malformed = client.get("/directory/tech-hub-lusaka/elsewhere?service=not-a-uuid")
        assert malformed.status_code == 200
        assert [s["id"] for s in malformed.json()["services"]] == ["other-s"]


class TestBusinessHomeSections:
    """Founder rule: a section shows only when its flag is ON and it has items."""

    def test_defaults_show_only_sections_with_live_items(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        seed_active_vendor(store)
        sections = client.get("/directory/tech-hub-lusaka").json()["sections"]
        assert sections == {
            "products": True,
            "services": False,
            "events": False,
            "offers": False,
            "clips": False,
        }

    def test_switched_off_section_sends_no_items(
        self, client: TestClient, store: FakeSupabaseStore
    ) -> None:
        seed_active_vendor(store)
        store.feature_flags = [  # type: ignore[attr-defined]
            {"flag": "business_home_products", "enabled": False},
            {"flag": "business_offers", "enabled": True},
        ]
        payload = client.get("/directory/tech-hub-lusaka").json()
        assert payload["listings"] == []
        assert payload["sections"]["products"] is False
        # Offers flag ON but no offers yet: still hidden, never an empty block.
        assert payload["offers_enabled"] is True
        assert payload["offers"] == []
        assert payload["sections"]["offers"] is False
