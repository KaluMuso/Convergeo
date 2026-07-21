"""VC-P06 / FD-04 / G11 — public discovery excludes demo Cloudinary inventory."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import pytest
from app.errors import AppError
from app.routers.catalog import PlpFilterState, list_catalog
from app.routers.comparison import build_comparison
from app.routers.directory import VendorProfileResponse, get_vendor_profile, list_directory_vendors
from app.routers.products import ProductDetailResponse, build_product_detail, build_related_products
from app.routers.services_listings import build_browse_response, get_service_detail
from app.services.ask.filters import AskFilters
from app.services.ask.retrieve import top_k
from app.services.listings.demo import (
    drop_demo_listing_hits,
    fetch_demo_listing_ids,
    has_demo_media,
    is_demo_public_id,
)
from app.services.search import SearchHit, run_search, run_suggest
from fastapi.responses import RedirectResponse

REAL_LISTING_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1"
DEMO_LISTING_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb1"
REAL_PRODUCT_ID = "cccccccc-cccc-cccc-cccc-ccccccccccc1"
DEMO_PRODUCT_ID = "dddddddd-dddd-dddd-dddd-ddddddddddd1"
REAL_VENDOR_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeee1"
DEMO_VENDOR_ID = "ffffffff-ffff-ffff-ffff-fffffffffff1"
MIXED_VENDOR_ID = "12345678-1234-1234-1234-1234567890ab"
MIXED_REAL_LISTING = "11111111-1111-1111-1111-111111111111"
MIXED_DEMO_LISTING = "22222222-2222-2222-2222-222222222222"
REAL_SERVICE_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaa11"
DEMO_SERVICE_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbb11"
REAL_EVENT_ID = "cccccccc-cccc-cccc-cccc-cccccccccc11"
DEMO_EVENT_ID = "dddddddd-dddd-dddd-dddd-dddddddddd11"


@pytest.mark.parametrize(
    ("public_id", "expected"),
    [
        ("demo/products/itel-a70", True),
        ("demo/categories/phones", True),
        ("vergeo5/demo/products/itel-a70", True),
        ("/demo/categories/phones", True),
        ("demo", True),
        ("vergeo5/catalog/phone-a", False),
        ("listings/vendor-a/photo-1", False),
        ("demodex/hero", False),
        (None, False),
        ("", False),
    ],
)
def test_is_demo_public_id_matches_client_rule(
    public_id: str | None, expected: bool
) -> None:
    assert is_demo_public_id(public_id) is expected


class _Resp:
    def __init__(self, data: Any) -> None:
        self.data = data


class _Query:
    def __init__(self, store: _Store, table: str) -> None:
        self._store = store
        self._table = table
        self._filters: list[tuple[str, str, Any]] = []
        self._maybe_single = False
        self._orders: list[tuple[str, bool]] = []

    def select(self, *_a: Any, **_k: Any) -> _Query:
        return self

    def eq(self, column: str, value: Any) -> _Query:
        self._filters.append(("eq", column, value))
        return self

    def like(self, column: str, value: str) -> _Query:
        self._filters.append(("like", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> _Query:
        self._filters.append(("in", column, values))
        return self

    def order(self, column: str = "", desc: bool = False, **_k: Any) -> _Query:
        self._orders.append((column, desc))
        return self

    def maybe_single(self) -> _Query:
        self._maybe_single = True
        return self

    def execute(self) -> _Resp:
        rows = list(getattr(self._store, self._table, []))
        for op, column, value in self._filters:
            if op == "eq":
                if column == "vendors.status":
                    rows = [
                        row
                        for row in rows
                        if isinstance(row.get("vendors"), dict)
                        and row["vendors"].get("status") == value
                    ]
                else:
                    rows = [row for row in rows if row.get(column) == value]
            elif op == "like":
                prefix = str(value).replace(r"\%", "%").rstrip("%")
                rows = [
                    row
                    for row in rows
                    if isinstance(row.get(column), str)
                    and str(row[column]).startswith(prefix)
                ]
            elif op == "in":
                allowed = set(value)
                rows = [row for row in rows if row.get(column) in allowed]
        for column, desc in self._orders:
            rows = sorted(
                rows,
                key=lambda row: (row.get(column), row.get("id", "")),
                reverse=desc,
            )
        if self._maybe_single:
            return _Resp(rows[0] if rows else None)
        return _Resp(rows)


class _Store:
    def __init__(self) -> None:
        self.listing_images: list[dict[str, Any]] = []
        self.vendor_listings: list[dict[str, Any]] = []
        self.products: list[dict[str, Any]] = []
        self.vendors: list[dict[str, Any]] = []
        self.search_documents: list[dict[str, Any]] = []
        self.vendor_locations: list[dict[str, Any]] = []
        self.order_item_products: list[dict[str, Any]] = []
        self.reviews: list[dict[str, Any]] = []
        self.services: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self.orders: list[dict[str, Any]] = []
        self.kyc_records: list[dict[str, Any]] = []
        self.product_relations: list[dict[str, Any]] = []
        self._rpc_hits: list[dict[str, Any]] = []

    def table(self, name: str) -> _Query:
        return _Query(self, name)

    def rpc(self, name: str, params: dict[str, Any]) -> Any:
        class _Rpc:
            def __init__(self, hits: list[dict[str, Any]]) -> None:
                self._hits = hits

            def execute(self) -> _Resp:
                if name == "expand_search_terms":
                    return _Resp([str(params.get("p_query", ""))])
                if name == "search_rrf":
                    return _Resp(self._hits)
                return _Resp([])

        return _Rpc(self._rpc_hits)


def _seed_catalog_mix(store: _Store) -> None:
    store.vendors = [
        {
            "id": REAL_VENDOR_ID,
            "slug": "real-shop",
            "display_name": "Real Shop",
            "status": "active",
            "preferred_badge": False,
            "kyc_tier": 1,
            "description": None,
            "logo_url": None,
            "cover_url": None,
            "whatsapp_msisdn": None,
            "created_at": "2026-01-01T00:00:00Z",
            "vendor_locations": [
                {"landmark": "Cairo Road", "lat": -15.4, "lng": 28.3, "hours": None}
            ],
        },
        {
            "id": DEMO_VENDOR_ID,
            "slug": "demo-shop",
            "display_name": "Demo Shop",
            "status": "active",
            "preferred_badge": False,
            "kyc_tier": 1,
            "description": None,
            "logo_url": None,
            "cover_url": None,
            "whatsapp_msisdn": None,
            "created_at": "2026-01-01T00:00:00Z",
            "vendor_locations": [
                {"landmark": "Manda Hill", "lat": -15.4, "lng": 28.3, "hours": None}
            ],
        },
        {
            "id": MIXED_VENDOR_ID,
            "slug": "mixed-shop",
            "display_name": "Mixed Shop",
            "status": "active",
            "preferred_badge": True,
            "kyc_tier": 2,
            "description": "Has real + demo",
            "logo_url": None,
            "cover_url": None,
            "whatsapp_msisdn": None,
            "created_at": "2026-01-01T00:00:00Z",
            "vendor_locations": [
                {"landmark": "East Park", "lat": -15.4, "lng": 28.3, "hours": None}
            ],
        },
    ]
    store.products = [
        {
            "id": REAL_PRODUCT_ID,
            "slug": "real-phone",
            "name": "Real Phone",
            "status": "active",
            "brand": "Itel",
            "description": None,
            "spec": {},
            "category_id": "cat-electronics",
            "merged_into_id": None,
        },
        {
            "id": DEMO_PRODUCT_ID,
            "slug": "demo-phone",
            "name": "Demo Phone",
            "status": "active",
            "brand": "Demo",
            "description": None,
            "spec": {},
            "category_id": "cat-electronics",
            "merged_into_id": None,
        },
    ]
    store.vendor_listings = [
        {
            "id": REAL_LISTING_ID,
            "vendor_id": REAL_VENDOR_ID,
            "product_id": REAL_PRODUCT_ID,
            "title_override": None,
            "price_ngwee": 450_000,
            "condition": "new",
            "stock_mode": "tracked",
            "stock_qty": 3,
            "moq": 1,
            "wholesale": False,
            "status": "active",
            "created_at": "2026-01-02T00:00:00Z",
            "vendors": {
                "id": REAL_VENDOR_ID,
                "slug": "real-shop",
                "display_name": "Real Shop",
                "preferred_badge": False,
                "status": "active",
                "vendor_locations": [
                    {"landmark": "Cairo Road", "lat": -15.4, "lng": 28.3}
                ],
            },
            "products": {
                "name": "Real Phone",
                "slug": "real-phone",
                "status": "active",
                "category_id": "cat-electronics",
                "categories": {"path": "electronics/phones"},
            },
        },
        {
            "id": DEMO_LISTING_ID,
            "vendor_id": DEMO_VENDOR_ID,
            "product_id": DEMO_PRODUCT_ID,
            "title_override": None,
            "price_ngwee": 199_000,
            "condition": "new",
            "stock_mode": "tracked",
            "stock_qty": 10,
            "moq": 1,
            "wholesale": False,
            "status": "active",
            "created_at": "2026-01-01T00:00:00Z",
            "vendors": {
                "id": DEMO_VENDOR_ID,
                "slug": "demo-shop",
                "display_name": "Demo Shop",
                "preferred_badge": False,
                "status": "active",
                "vendor_locations": [
                    {"landmark": "Manda Hill", "lat": -15.4, "lng": 28.3}
                ],
            },
            "products": {
                "name": "Demo Phone",
                "slug": "demo-phone",
                "status": "active",
                "category_id": "cat-electronics",
                "categories": {"path": "electronics/phones"},
            },
        },
        {
            "id": MIXED_REAL_LISTING,
            "vendor_id": MIXED_VENDOR_ID,
            "product_id": REAL_PRODUCT_ID,
            "title_override": None,
            "price_ngwee": 460_000,
            "condition": "new",
            "stock_mode": "tracked",
            "stock_qty": 2,
            "moq": 1,
            "wholesale": False,
            "status": "active",
            "created_at": "2026-01-03T00:00:00Z",
            "vendors": {
                "id": MIXED_VENDOR_ID,
                "slug": "mixed-shop",
                "display_name": "Mixed Shop",
                "preferred_badge": True,
                "status": "active",
                "vendor_locations": [
                    {"landmark": "East Park", "lat": -15.4, "lng": 28.3}
                ],
            },
            "products": {
                "name": "Real Phone",
                "slug": "real-phone",
                "status": "active",
                "category_id": "cat-electronics",
                "categories": {"path": "electronics/phones"},
            },
        },
        {
            "id": MIXED_DEMO_LISTING,
            "vendor_id": MIXED_VENDOR_ID,
            "product_id": REAL_PRODUCT_ID,
            "title_override": "Sample SKU",
            "price_ngwee": 100_000,
            "condition": "new",
            "stock_mode": "tracked",
            "stock_qty": 99,
            "moq": 1,
            "wholesale": False,
            "status": "active",
            "created_at": "2026-01-03T00:00:00Z",
            "vendors": {
                "id": MIXED_VENDOR_ID,
                "slug": "mixed-shop",
                "display_name": "Mixed Shop",
                "preferred_badge": True,
                "status": "active",
                "vendor_locations": [
                    {"landmark": "East Park", "lat": -15.4, "lng": 28.3}
                ],
            },
            "products": {
                "name": "Real Phone",
                "slug": "real-phone",
                "status": "active",
                "category_id": "cat-electronics",
                "categories": {"path": "electronics/phones"},
            },
        },
    ]
    store.listing_images = [
        {
            "listing_id": REAL_LISTING_ID,
            "cloudinary_public_id": "listings/real-phone",
            "position": 1,
        },
        {
            "listing_id": DEMO_LISTING_ID,
            "cloudinary_public_id": "demo/products/demo-phone",
            "position": 1,
        },
        {
            "listing_id": MIXED_REAL_LISTING,
            "cloudinary_public_id": "listings/mixed-real",
            "position": 1,
        },
        {
            "listing_id": MIXED_DEMO_LISTING,
            "cloudinary_public_id": "demo/products/mixed-demo",
            "position": 1,
        },
    ]
    store.search_documents = [
        {
            "entity_id": REAL_LISTING_ID,
            "title": "Real Phone",
            "category_path": "electronics/phones",
            "price_min_ngwee": 450_000,
            "lat": -15.4,
            "lng": 28.3,
            "boost_signals": {"verified": True, "in_stock": True},
            "updated_at": "2026-01-02T00:00:00Z",
            "entity_kind": "listing",
            "is_public": True,
        },
        {
            "entity_id": DEMO_LISTING_ID,
            "title": "Demo Phone",
            "category_path": "electronics/phones",
            "price_min_ngwee": 199_000,
            "lat": -15.4,
            "lng": 28.3,
            "boost_signals": {"verified": False, "in_stock": True},
            "updated_at": "2026-01-01T00:00:00Z",
            "entity_kind": "listing",
            "is_public": True,
        },
        {
            "entity_id": MIXED_REAL_LISTING,
            "title": "Real Phone (Mixed Shop)",
            "category_path": "electronics/phones",
            "price_min_ngwee": 460_000,
            "lat": -15.4,
            "lng": 28.3,
            "boost_signals": {"verified": True, "in_stock": True},
            "updated_at": "2026-01-03T00:00:00Z",
            "entity_kind": "listing",
            "is_public": True,
        },
        {
            "entity_id": MIXED_DEMO_LISTING,
            "title": "Sample SKU",
            "category_path": "electronics/phones",
            "price_min_ngwee": 100_000,
            "lat": -15.4,
            "lng": 28.3,
            "boost_signals": {"verified": False, "in_stock": True},
            "updated_at": "2026-01-03T00:00:00Z",
            "entity_kind": "listing",
            "is_public": True,
        },
    ]
    store.vendor_locations = [
        {
            "vendor_id": REAL_VENDOR_ID,
            "landmark": "Cairo Road",
            "created_at": "2026-01-01T00:00:00Z",
        },
        {
            "vendor_id": DEMO_VENDOR_ID,
            "landmark": "Manda Hill",
            "created_at": "2026-01-01T00:00:00Z",
        },
        {
            "vendor_id": MIXED_VENDOR_ID,
            "landmark": "East Park",
            "created_at": "2026-01-01T00:00:00Z",
        },
    ]


def test_fetch_demo_listing_ids_batch() -> None:
    store = _Store()
    _seed_catalog_mix(store)
    demo_ids = fetch_demo_listing_ids(
        store, [REAL_LISTING_ID, DEMO_LISTING_ID, MIXED_DEMO_LISTING]
    )
    assert demo_ids == {DEMO_LISTING_ID, MIXED_DEMO_LISTING}


def test_catalog_excludes_demo_keeps_real_and_consistent_total() -> None:
    store = _Store()
    _seed_catalog_mix(store)
    response = list_catalog(store, PlpFilterState(category_path="electronics"))
    ids = {item.id for item in response.items}
    assert DEMO_LISTING_ID not in ids
    assert MIXED_DEMO_LISTING not in ids
    assert REAL_LISTING_ID in ids
    assert MIXED_REAL_LISTING in ids
    assert response.total == len(response.items) == 2
    # Facets must match the filtered set (no demo leakage into counts).
    in_stock = next(b for b in response.facets.availability if b.value == "in_stock")
    assert in_stock.count == 2


def test_catalog_empty_public_results_are_honest_empty() -> None:
    store = _Store()
    store.search_documents = [
        {
            "entity_id": DEMO_LISTING_ID,
            "title": "Demo Only",
            "category_path": "electronics/phones",
            "price_min_ngwee": 1000,
            "lat": None,
            "lng": None,
            "boost_signals": {},
            "updated_at": "2026-01-01T00:00:00Z",
            "entity_kind": "listing",
            "is_public": True,
        }
    ]
    store.vendor_listings = [
        {
            "id": DEMO_LISTING_ID,
            "vendor_id": DEMO_VENDOR_ID,
            "product_id": DEMO_PRODUCT_ID,
            "condition": "new",
            "stock_mode": "tracked",
            "stock_qty": 1,
            "created_at": "2026-01-01T00:00:00Z",
            "status": "active",
            "wholesale": False,
        }
    ]
    store.vendors = [
        {
            "id": DEMO_VENDOR_ID,
            "slug": "demo-shop",
            "display_name": "Demo Shop",
            "status": "active",
        }
    ]
    store.products = [
        {
            "id": DEMO_PRODUCT_ID,
            "slug": "demo-phone",
            "name": "Demo Phone",
            "status": "active",
        }
    ]
    store.listing_images = [
        {
            "listing_id": DEMO_LISTING_ID,
            "cloudinary_public_id": "demo/only",
            "position": 1,
        }
    ]
    response = list_catalog(store, PlpFilterState(category_path="electronics"))
    assert response.total == 0
    assert response.items == []
    assert response.next_cursor is None


def _hit(
    *,
    entity_id: str,
    title: str,
    entity_kind: str = "listing",
    score: float = 1.0,
) -> dict[str, Any]:
    return {
        "id": str(UUID(int=abs(hash(entity_id)) % (2**128 - 1))),
        "entity_kind": entity_kind,
        "entity_id": entity_id,
        "title": title,
        "body": None,
        "category_path": "electronics/phones",
        "price_min_ngwee": 1000,
        "price_max_ngwee": 1000,
        "lat": None,
        "lng": None,
        "locale_terms": None,
        "boost_signals": {},
        "rrf_score": score,
    }


async def _no_embedding(_query: str) -> list[float] | None:
    return None


def test_search_and_suggest_exclude_demo_listing_hits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _Store()
    _seed_catalog_mix(store)
    store._rpc_hits = [
        _hit(entity_id=REAL_LISTING_ID, title="Real Phone", score=1.2),
        _hit(entity_id=DEMO_LISTING_ID, title="Demo Phone", score=1.1),
        _hit(
            entity_id=DEMO_PRODUCT_ID,
            title="Demo Phone Product",
            entity_kind="product",
            score=1.0,
        ),
        _hit(
            entity_id=REAL_PRODUCT_ID,
            title="Real Phone Product",
            entity_kind="product",
            score=0.9,
        ),
        _hit(
            entity_id=DEMO_VENDOR_ID,
            title="Demo Shop",
            entity_kind="vendor",
            score=0.8,
        ),
        _hit(
            entity_id=REAL_VENDOR_ID,
            title="Real Shop",
            entity_kind="vendor",
            score=0.7,
        ),
    ]
    monkeypatch.setattr("app.services.search.fetch_query_embedding", _no_embedding)

    result = asyncio.run(run_search(store, query="phone", include_wholesale=True))
    ids = {hit.entity_id for hit in result.results}
    assert REAL_LISTING_ID in ids
    assert REAL_PRODUCT_ID in ids
    assert REAL_VENDOR_ID in ids
    assert DEMO_LISTING_ID not in ids
    assert DEMO_PRODUCT_ID not in ids
    assert DEMO_VENDOR_ID not in ids
    assert result.total == 3

    suggestions = run_suggest(store, query="phone", include_wholesale=True).suggestions
    titles = {item.title for item in suggestions}
    assert "Demo Phone" not in titles
    assert "Demo Phone Product" not in titles
    assert "Demo Shop" not in titles
    assert "Real Phone" in titles


def test_search_pagination_total_excludes_demo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _Store()
    _seed_catalog_mix(store)
    store._rpc_hits = [
        _hit(entity_id=REAL_LISTING_ID, title="Real Phone", score=1.2),
        _hit(entity_id=DEMO_LISTING_ID, title="Demo Phone", score=1.1),
        _hit(entity_id=MIXED_REAL_LISTING, title="Mixed Real", score=1.0),
        _hit(entity_id=MIXED_DEMO_LISTING, title="Mixed Demo", score=0.9),
    ]
    monkeypatch.setattr("app.services.search.fetch_query_embedding", _no_embedding)
    page1 = asyncio.run(
        run_search(store, query="phone", page=1, page_size=1, include_wholesale=True)
    )
    assert page1.total == 2
    assert len(page1.results) == 1
    assert page1.results[0].entity_id == REAL_LISTING_ID
    page2 = asyncio.run(
        run_search(store, query="phone", page=2, page_size=1, include_wholesale=True)
    )
    assert page2.total == 2
    assert page2.results[0].entity_id == MIXED_REAL_LISTING


def test_ask_retrieve_excludes_demo(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _Store()
    _seed_catalog_mix(store)
    store._rpc_hits = [
        _hit(entity_id=REAL_LISTING_ID, title="Real Phone"),
        _hit(entity_id=DEMO_LISTING_ID, title="Demo Phone"),
    ]
    monkeypatch.setattr(
        "app.services.ask.retrieve.fetch_query_embedding", _no_embedding
    )
    docs = asyncio.run(
        top_k(store, query="phone", filters=AskFilters(), limit=8)
    )
    ids = {doc.entity_id for doc in docs}
    assert REAL_LISTING_ID in ids
    assert DEMO_LISTING_ID not in ids


def test_product_detail_hides_demo_listings_keeps_real() -> None:
    store = _Store()
    _seed_catalog_mix(store)
    detail = build_product_detail(store, "real-phone")
    assert isinstance(detail, ProductDetailResponse)
    assert detail.listing_count == 2  # real shop + mixed real; demo listing dropped
    ids = {listing.id for listing in detail.listings}
    assert REAL_LISTING_ID in ids
    assert MIXED_REAL_LISTING in ids
    assert MIXED_DEMO_LISTING not in ids


def test_product_detail_demo_only_is_hidden() -> None:
    store = _Store()
    _seed_catalog_mix(store)
    with pytest.raises(AppError) as exc:
        build_product_detail(store, "demo-phone")
    assert exc.value.http_status == 404
    assert exc.value.code == "product.not_found"


def test_comparison_excludes_demo_and_hides_demo_only() -> None:
    store = _Store()
    _seed_catalog_mix(store)
    comparison = build_comparison(store, "real-phone")
    ids = {item.id for item in comparison.listings}
    assert REAL_LISTING_ID in ids
    assert MIXED_REAL_LISTING in ids
    assert MIXED_DEMO_LISTING not in ids

    with pytest.raises(AppError) as exc:
        build_comparison(store, "demo-phone")
    assert exc.value.http_status == 404
    assert exc.value.code == "product.not_found"


def test_directory_excludes_demo_vendor_keeps_real_and_mixed() -> None:
    store = _Store()
    _seed_catalog_mix(store)
    listing = list_directory_vendors(store)
    slugs = {item.slug for item in listing.items}
    assert "demo-shop" not in slugs
    assert "real-shop" in slugs
    assert "mixed-shop" in slugs
    assert listing.total == 2

    mixed = get_vendor_profile(store, "mixed-shop")
    assert isinstance(mixed, VendorProfileResponse)
    assert not isinstance(mixed, RedirectResponse)
    listing_ids = {item.id for item in mixed.listings}
    assert MIXED_REAL_LISTING in listing_ids
    assert MIXED_DEMO_LISTING not in listing_ids

    with pytest.raises(AppError) as exc:
        get_vendor_profile(store, "demo-shop")
    assert exc.value.http_status == 404
    assert exc.value.code == "vendor.not_found"


def test_related_products_skip_demo_only_siblings() -> None:
    store = _Store()
    _seed_catalog_mix(store)
    # Point a second product in the same category that is demo-only.
    related = build_related_products(store, "real-phone")
    slugs = {item.slug for item in related.items}
    assert "demo-phone" not in slugs


def test_drop_demo_listing_hits_no_secondary_leak() -> None:
    store = _Store()
    _seed_catalog_mix(store)
    hits = [
        SearchHit(
            id="1",
            entity_kind="listing",
            entity_id=DEMO_LISTING_ID,
            title="Demo",
            rrf_score=1.0,
        ),
        SearchHit(
            id="2",
            entity_kind="listing",
            entity_id=REAL_LISTING_ID,
            title="Real",
            rrf_score=0.9,
        ),
    ]
    kept = drop_demo_listing_hits(store, hits)
    assert [hit.entity_id for hit in kept] == [REAL_LISTING_ID]


def test_vendor_manage_images_still_accept_demo_public_ids() -> None:
    """Vendor-owned attach path must not reject demo/ IDs (owner retains access)."""
    # The manage router does not call fetch_demo_listing_ids — assert helper
    # still classifies the marker so owners can label seed media while public
    # discovery excludes it.
    assert is_demo_public_id("demo/products/seed-sku") is True


def test_has_demo_media_matches_portfolio_arrays() -> None:
    assert has_demo_media(["demo/services/plumbing"]) is True
    assert has_demo_media(["vergeo5/catalog/hero"]) is False
    assert has_demo_media([]) is False


def _seed_service_event_mix(store: _Store) -> None:
    store.services = [
        {
            "id": REAL_SERVICE_ID,
            "vendor_id": REAL_VENDOR_ID,
            "category": "cleaning",
            "title": "Office Cleaning",
            "description": "Weekly office cleaning in Lusaka",
            "service_area": "Lusaka",
            "from_price_ngwee": 25000,
            "portfolio_images": ["vergeo5/services/cleaning"],
            "status": "active",
            "vendors": {
                "id": REAL_VENDOR_ID,
                "slug": "real-shop",
                "display_name": "Real Shop",
                "preferred_badge": False,
                "status": "active",
            },
        },
        {
            "id": DEMO_SERVICE_ID,
            "vendor_id": REAL_VENDOR_ID,
            "category": "tech-services",
            "title": "Laptop & Phone Repair (demo)",
            "description": "Demo repair service",
            "service_area": "Lusaka",
            "from_price_ngwee": 15000,
            "portfolio_images": ["demo/services/tech-services"],
            "status": "active",
            "vendors": {
                "id": REAL_VENDOR_ID,
                "slug": "real-shop",
                "display_name": "Real Shop",
                "preferred_badge": True,
                "status": "active",
            },
        },
    ]
    store.events = [
        {
            "id": REAL_EVENT_ID,
            "images": ["vergeo5/events/live-music"],
        },
        {
            "id": DEMO_EVENT_ID,
            "images": ["demo/events/zed-summer-festival"],
        },
    ]


def test_search_and_suggest_exclude_demo_service_and_event_hits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _Store()
    _seed_service_event_mix(store)
    store._rpc_hits = [
        _hit(entity_id=REAL_SERVICE_ID, title="Office Cleaning", entity_kind="service", score=1.2),
        _hit(
            entity_id=DEMO_SERVICE_ID,
            title="Laptop & Phone Repair (demo)",
            entity_kind="service",
            score=1.1,
        ),
        _hit(entity_id=REAL_EVENT_ID, title="Live Music Night", entity_kind="event", score=1.0),
        _hit(
            entity_id=DEMO_EVENT_ID,
            title="Zed Summer Festival",
            entity_kind="event",
            score=0.9,
        ),
    ]
    monkeypatch.setattr("app.services.search.fetch_query_embedding", _no_embedding)

    result = asyncio.run(run_search(store, query="laptop", include_wholesale=True))
    ids = {(hit.entity_kind, hit.entity_id) for hit in result.results}
    assert ("service", REAL_SERVICE_ID) in ids
    assert ("service", DEMO_SERVICE_ID) not in ids
    assert ("event", REAL_EVENT_ID) in ids
    assert ("event", DEMO_EVENT_ID) not in ids
    assert result.total == 2

    suggestions = run_suggest(store, query="laptop", include_wholesale=True).suggestions
    titles = {item.title for item in suggestions}
    assert "Laptop & Phone Repair (demo)" not in titles
    assert "Office Cleaning" in titles


def test_ask_retrieve_excludes_demo_service_and_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _Store()
    _seed_service_event_mix(store)
    store._rpc_hits = [
        _hit(entity_id=REAL_SERVICE_ID, title="Office Cleaning", entity_kind="service"),
        _hit(
            entity_id=DEMO_SERVICE_ID,
            title="Laptop & Phone Repair (demo)",
            entity_kind="service",
        ),
        _hit(entity_id=REAL_EVENT_ID, title="Live Music Night", entity_kind="event"),
        _hit(entity_id=DEMO_EVENT_ID, title="Zed Summer Festival", entity_kind="event"),
    ]
    monkeypatch.setattr(
        "app.services.ask.retrieve.fetch_query_embedding", _no_embedding
    )
    docs = asyncio.run(top_k(store, query="repair", filters=AskFilters(), limit=8))
    keys = {(doc.entity_kind, doc.entity_id) for doc in docs}
    assert ("service", REAL_SERVICE_ID) in keys
    assert ("service", DEMO_SERVICE_ID) not in keys
    assert ("event", REAL_EVENT_ID) in keys
    assert ("event", DEMO_EVENT_ID) not in keys


def test_services_browse_and_detail_exclude_demo_inventory() -> None:
    store = _Store()
    _seed_service_event_mix(store)

    browse = build_browse_response(store)
    service_ids = {item.id for item in browse.items}
    assert REAL_SERVICE_ID in service_ids
    assert DEMO_SERVICE_ID not in service_ids
    assert browse.total == 1

    real = get_service_detail(REAL_SERVICE_ID, type("C", (), {"client": store})())
    assert real.id == REAL_SERVICE_ID

    with pytest.raises(AppError) as exc:
        get_service_detail(DEMO_SERVICE_ID, type("C", (), {"client": store})())
    assert exc.value.http_status == 404
