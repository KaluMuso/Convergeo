"""Recommendations, listing sorts, retention endpoints (authz failure paths), deals,
Q&A and the internal alerts tick."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.main import create_app
from app.routers.catalog import CatalogCandidate, _sort_candidates, best_score
from app.routers.events_public import EventBrowseItem, EventOrganiserResponse, sort_events
from app.routers.internal_retention import TickResult, run_listing_alerts, run_saved_search_alerts
from app.routers.services_listings import ProviderSummary, ServiceBrowseItem, sort_services
from app.services.discovery.recommendations import (
    recommend_events,
    recommend_for_product,
    recommend_services,
)
from fastapi.testclient import TestClient
from tests.test_home_feed import FakeClient

CUSTOMER_ID = "00000000-0000-0000-0000-0000000c0001"
ADMIN_ID = "00000000-0000-0000-0000-0000000a0001"
LISTING_ID = "22222222-2222-4222-8222-222222222222"
NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


def cand(
    listing_id: str,
    *,
    vendor: str,
    slug: str | None,
    path: str,
    price: int,
    rating: float = 0.0,
    reviews: int = 0,
    in_stock: bool = True,
    product_class: str = "A",
    moq: int = 1,
    preferred: bool = False,
    kyc: int | None = None,
    created_at: str = "2026-11-01T00:00:00+00:00",
) -> CatalogCandidate:
    return CatalogCandidate.model_validate(
        {
            "search_doc": {
                "entity_id": listing_id,
                "title": listing_id,
                "category_path": path,
                "price_min_ngwee": price,
                "boost_signals": {},
            },
            "listing": {
                "id": listing_id,
                "vendor_id": vendor,
                "product_id": f"p-{slug}" if slug else None,
                "condition": "new",
                "product_class": product_class,
                "stock_mode": "always_available",
                "moq": moq,
                "created_at": created_at,
            },
            "vendor": {
                "display_name": vendor,
                "slug": vendor,
                "preferred_badge": preferred,
                "kyc_tier": kyc,
            },
            "product": {"slug": slug} if slug else None,
            "image_public_id": None,
            "landmark": None,
            "rating": rating,
            "review_count": reviews,
            "in_stock": in_stock,
        }
    )


POOL = [
    cand("own", vendor="va", slug="phone-x", path="electronics/mobile-phones", price=200_000),
    cand("va-case", vendor="va", slug="case", path="electronics/phone-accessories", price=5_000),
    cand(
        "va-oos",
        vendor="va",
        slug="cable",
        path="electronics/phone-accessories",
        price=2_000,
        in_stock=False,
    ),
    cand(
        "vb-phone",
        vendor="vb",
        slug="phone-y",
        path="electronics/mobile-phones",
        price=210_000,
        rating=4.8,
        reviews=40,
    ),
    cand(
        "vc-phone",
        vendor="vc",
        slug="phone-z",
        path="electronics/mobile-phones",
        price=900_000,
        rating=4.8,
        reviews=40,
    ),
    cand(
        "vd-classb",
        vendor="vd",
        slug="phone-b",
        path="electronics/mobile-phones",
        price=200_000,
        product_class="B",
    ),
    cand("ve-laptop", vendor="ve", slug="laptop", path="electronics/laptops", price=300_000),
]


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------


def test_more_from_store_excludes_current_and_ranks_in_stock_first() -> None:
    items = recommend_for_product(FakeClient(), "phone-x", scope="store", limit=8, candidates=POOL)
    assert items is not None
    assert [item.id for item in items] == ["va-case", "va-oos"]


def test_similar_in_category_other_vendors_same_class_price_proximity() -> None:
    items = recommend_for_product(
        FakeClient(), "phone-x", scope="category", limit=8, candidates=POOL
    )
    assert items is not None
    ids = [item.id for item in items]
    assert "vd-classb" not in ids and "va-case" not in ids and "own" not in ids
    assert ids.index("vb-phone") < ids.index("vc-phone")  # closer price wins at equal rating
    assert "ve-laptop" in ids  # parent-category fallback fills the rail


def test_unknown_product_returns_none() -> None:
    assert (
        recommend_for_product(FakeClient(), "nope", scope="store", limit=4, candidates=POOL) is None
    )


def _service(
    sid: str, provider: str, category: str, price: int | None, preferred: bool = False
) -> ServiceBrowseItem:
    return ServiceBrowseItem(
        id=sid,
        slug=sid,
        title=sid,
        category=category,  # type: ignore[arg-type]
        from_price_ngwee=price,
        provider=ProviderSummary(
            id=provider, slug=provider, display_name=provider, preferred_badge=preferred
        ),
    )


def test_service_recommendations_and_sort() -> None:
    from app.routers.services_listings import SERVICE_VERTICALS

    vertical = sorted(SERVICE_VERTICALS)[0]
    other = sorted(SERVICE_VERTICALS)[1]
    items = [
        _service("s1", "p1", vertical, 10_000),
        _service("s2", "p1", other, 5_000),
        _service("s3", "p2", vertical, 11_000, preferred=True),
        _service("s4", "p3", vertical, None),
    ]
    assert [s.id for s in recommend_services(items, "s1", scope="provider", limit=5) or []] == [
        "s2"
    ]
    similar = recommend_services(items, "s1", scope="category", limit=5) or []
    assert similar[0].id == "s3"
    assert recommend_services(items, "missing", scope="provider", limit=5) is None
    assert [s.id for s in sort_services(items, "price_asc")] == ["s2", "s1", "s3", "s4"]
    assert sort_services(items, "verified")[0].id == "s3"


def _event(slug: str, organiser: str, category: str, days: int, **extra: Any) -> EventBrowseItem:
    return EventBrowseItem(
        id=slug,
        slug=slug,
        title=slug,
        category=category,
        next_starts_at=NOW + timedelta(days=days),
        organiser=EventOrganiserResponse(id=organiser, slug=organiser, display_name=organiser),
        **extra,
    )


def test_event_recommendations_and_sort() -> None:
    events = [
        _event("e1", "o1", "music", 1),
        _event("e2", "o1", "sports", 3),
        _event("e3", "o2", "music", 5, spots_sold=90, min_price_ngwee=5_000),
        _event("e4", "o3", "music", 2, is_sold_out=True),
        _event("e5", "o4", "music", 4, is_free=True),
    ]
    assert [e.slug for e in recommend_events(events, "e1", scope="organiser", limit=4) or []] == [
        "e2"
    ]
    assert [e.slug for e in recommend_events(events, "e1", scope="category", limit=4) or []] == [
        "e5",
        "e3",
    ]
    assert sort_events(events, "price_asc")[0].slug == "e5"
    assert sort_events(events, "popular")[0].slug == "e3"


# ---------------------------------------------------------------------------
# Catalogue sorts
# ---------------------------------------------------------------------------


def test_catalog_sorts_verified_bundle_best_price_asc() -> None:
    pool = [
        cand("a", vendor="x", slug="a", path="p", price=300, rating=5.0, reviews=1),
        cand("b", vendor="y", slug="b", path="p", price=100, preferred=True, kyc=2),
        cand("c", vendor="z", slug="c", path="p", price=200, moq=6, rating=4.6, reviews=50),
    ]
    sort = _sort_candidates
    assert [r.listing.id for r in sort(pool, sort="price_asc", lat=None, lng=None)] == [
        "b",
        "c",
        "a",
    ]
    assert sort(pool, sort="verified", lat=None, lng=None)[0].listing.id == "b"
    assert sort(pool, sort="bundle", lat=None, lng=None)[0].listing.id == "c"
    # Damped rating: 50 reviews at 4.6 beats a single 5-star review.
    assert sort(pool, sort="best", lat=None, lng=None)[0].listing.id == "c"
    assert best_score(pool[2])[0] > best_score(pool[0])[0]


# ---------------------------------------------------------------------------
# HTTP: authz + validation
# ---------------------------------------------------------------------------


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeClient:
    client = FakeClient()
    wrapper = MagicMock()
    wrapper.client = client
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: wrapper)
    monkeypatch.setattr("app.core.admin_audit.get_supabase_service_client", lambda: wrapper)
    monkeypatch.setattr("app.core.auth.get_supabase_service_client", lambda: wrapper)
    monkeypatch.setattr("app.routers.retention.build_catalog_candidates", lambda _c: POOL)
    return client


@pytest.fixture
def http(fake: FakeClient) -> Generator[TestClient, None, None]:
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        yield client


def _login(monkeypatch: pytest.MonkeyPatch, user_id: str, roles: frozenset[str]) -> dict[str, str]:
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": user_id, "exp": 9_999_999_999},
    )
    monkeypatch.setattr("app.core.auth._load_user_roles", lambda _uid, _svc: roles)
    return {"Authorization": "Bearer token"}


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/me/saved-searches"),
        ("POST", "/me/saved-searches"),
        ("DELETE", f"/me/saved-searches/{LISTING_ID}"),
        ("GET", "/me/listing-alerts"),
        ("POST", "/me/listing-alerts"),
        ("GET", "/me/follows/feed"),
        ("POST", "/products/phone-x/questions"),
        ("POST", f"/questions/{LISTING_ID}/answers"),
        ("POST", f"/qa/questions/{LISTING_ID}/flag"),
    ],
)
def test_retention_routes_require_auth(http: TestClient, method: str, path: str) -> None:
    assert http.request(method, path, json={}).status_code == 401


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/admin/flash-deals"),
        ("POST", "/admin/flash-deals"),
        ("POST", f"/admin/qa/questions/{LISTING_ID}/moderate"),
    ],
)
def test_admin_retention_routes_deny_customer(
    http: TestClient, monkeypatch: pytest.MonkeyPatch, method: str, path: str
) -> None:
    assert http.request(method, path, json={}).status_code == 401
    headers = _login(monkeypatch, CUSTOMER_ID, frozenset({"customer"}))
    assert http.request(method, path, json={}, headers=headers).status_code == 403


def test_internal_tick_requires_token(http: TestClient) -> None:
    assert http.post("/internal/retention/alerts-tick").status_code == 401
    assert (
        http.post(
            "/internal/retention/alerts-tick", headers={"X-Internal-Token": "wrong"}
        ).status_code
        == 401
    )


def test_saved_search_crud_scoped_to_owner(
    http: TestClient, fake: FakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _login(monkeypatch, CUSTOMER_ID, frozenset({"customer"}))
    bad = http.post("/me/saved-searches", headers=headers, json={"filters": {"max_price": 10.5}})
    assert bad.status_code == 422
    unknown = http.post("/me/saved-searches", headers=headers, json={"filters": {"evil": "x"}})
    assert unknown.status_code == 422
    empty = http.post("/me/saved-searches", headers=headers, json={})
    assert empty.status_code == 422
    created = http.post(
        "/me/saved-searches",
        headers=headers,
        json={"query": "solar", "filters": {"max_price": 100000}, "alert_frequency": "weekly"},
    )
    assert created.status_code == 201, created.text
    sid = created.json()["id"]
    fake.table("saved_searches").rows.append(
        {
            "id": "33333333-3333-4333-8333-333333333333",
            "user_id": "someone-else",
            "query": "x",
            "filters": {},
            "alert_enabled": True,
            "alert_frequency": "daily",
        }
    )
    listed = http.get("/me/saved-searches", headers=headers).json()
    assert [row["id"] for row in listed] == [sid]
    other = http.patch(
        "/me/saved-searches/33333333-3333-4333-8333-333333333333",
        headers=headers,
        json={"alert_enabled": False},
    )
    assert other.status_code == 404


def test_listing_alert_validation(
    http: TestClient, fake: FakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _login(monkeypatch, CUSTOMER_ID, frozenset({"customer"}))
    missing = http.post(
        "/me/listing-alerts", headers=headers, json={"listing_id": LISTING_ID, "kind": "price_drop"}
    )
    assert missing.status_code == 404
    fake.table("vendor_listings").rows.append(
        {"id": LISTING_ID, "price_ngwee": 50_000, "status": "active"}
    )
    too_high = http.post(
        "/me/listing-alerts",
        headers=headers,
        json={"listing_id": LISTING_ID, "kind": "price_drop", "target_price_ngwee": 60_000},
    )
    assert too_high.status_code == 422
    ok = http.post(
        "/me/listing-alerts",
        headers=headers,
        json={"listing_id": LISTING_ID, "kind": "price_drop", "target_price_ngwee": 40_000},
    )
    assert ok.status_code == 201 and ok.json()["baseline_price_ngwee"] == 50_000
    again = http.post(
        "/me/listing-alerts", headers=headers, json={"listing_id": LISTING_ID, "kind": "price_drop"}
    )
    assert again.status_code == 201
    assert len(fake.table("listing_alert_subscriptions").rows) == 1  # upsert, not duplicate


def test_deals_only_show_when_live_price_honours_deal(http: TestClient, fake: FakeClient) -> None:
    window = {
        "starts_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        "ends_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "enabled": True,
        "position": 0,
    }
    fake.table("flash_deals").rows.extend(
        [
            {
                "id": "d1",
                "listing_id": "va-case",
                "deal_price_ngwee": 5_000,
                "reference_price_ngwee": 8_000,
                **window,
            },
            {
                "id": "d2",
                "listing_id": "vb-phone",
                "deal_price_ngwee": 150_000,
                "reference_price_ngwee": 250_000,
                **window,
            },  # live price 210k > deal → hidden
            {
                "id": "d3",
                "listing_id": "va-oos",
                "deal_price_ngwee": 2_000,
                "reference_price_ngwee": 3_000,
                **window,
            },  # out of stock → hidden
        ]
    )
    body = http.get("/deals").json()
    assert [item["deal_id"] for item in body["items"]] == ["d1"]
    assert body["items"][0]["discount_percent"] == 37


def test_admin_flash_deal_create_validates_discount(
    http: TestClient, fake: FakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _login(monkeypatch, ADMIN_ID, frozenset({"admin"}))
    fake.table("vendor_listings").rows.append(
        {"id": LISTING_ID, "price_ngwee": 50_000, "compare_at_ngwee": 70_000, "status": "active"}
    )
    base = {
        "listing_id": LISTING_ID,
        "starts_at": NOW.isoformat(),
        "ends_at": (NOW + timedelta(days=1)).isoformat(),
    }
    not_discount = http.post(
        "/admin/flash-deals", headers=headers, json={**base, "deal_price_ngwee": 80_000}
    )
    assert not_discount.status_code == 422
    bad_window = http.post(
        "/admin/flash-deals",
        headers=headers,
        json={**base, "deal_price_ngwee": 40_000, "ends_at": NOW.isoformat()},
    )
    assert bad_window.status_code == 422
    created = http.post(
        "/admin/flash-deals", headers=headers, json={**base, "deal_price_ngwee": 45_000}
    )
    assert created.status_code == 201, created.text
    assert created.json()["reference_price_ngwee"] == 70_000
    assert "deals.flash.create" in [row["action"] for row in fake.table("audit_log").rows]


def test_qa_flow_vendor_answer_and_auto_hide(
    http: TestClient, fake: FakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake.table("products").rows.append({"id": "prod-1", "slug": "phone-x", "status": "active"})
    headers = _login(monkeypatch, CUSTOMER_ID, frozenset({"customer"}))
    short = http.post("/products/phone-x/questions", headers=headers, json={"body": "hi"})
    assert short.status_code == 422
    asked = http.post(
        "/products/phone-x/questions", headers=headers, json={"body": "Does it support dual SIM?"}
    )
    assert asked.status_code == 201, asked.text
    qid = asked.json()["id"]
    fake.table("product_questions").rows[0]["status"] = "published"

    vendor_user = "00000000-0000-0000-0000-0000000e0001"
    fake.table("vendors").rows.append(
        {"id": "vendor-1", "owner_user_id": vendor_user, "status": "active", "display_name": "Shop"}
    )
    fake.table("vendor_listings").rows.append(
        {"id": "l1", "vendor_id": "vendor-1", "product_id": "prod-1", "status": "active"}
    )
    vendor_headers = _login(monkeypatch, vendor_user, frozenset({"vendor"}))
    answered = http.post(
        f"/questions/{qid}/answers", headers=vendor_headers, json={"body": "Yes, dual SIM."}
    )
    assert answered.status_code == 201, answered.text
    assert answered.json()["author_role"] == "vendor"
    fake.table("product_answers").rows[0]["status"] = "published"

    public = http.get("/products/phone-x/questions").json()
    assert public[0]["answers"][0]["vendor_name"] == "Shop"

    for _ in range(3):
        assert http.post(f"/qa/questions/{qid}/flag", headers=headers).status_code == 204
    assert fake.table("product_questions").rows[0]["status"] == "hidden"
    assert http.get("/products/phone-x/questions").json() == []


# ---------------------------------------------------------------------------
# Internal alerts tick
# ---------------------------------------------------------------------------


def test_tick_enqueues_price_drop_and_back_in_stock_once() -> None:
    client = FakeClient()
    client.table("vendor_listings").rows.extend(
        [
            {
                "id": "l-drop",
                "price_ngwee": 40_000,
                "status": "active",
                "stock_mode": "always_available",
            },
            {
                "id": "l-stock",
                "price_ngwee": 10_000,
                "status": "active",
                "stock_mode": "tracked",
                "stock_qty": 3,
            },
            {
                "id": "l-same",
                "price_ngwee": 50_000,
                "status": "active",
                "stock_mode": "always_available",
            },
        ]
    )
    client.table("listing_alert_subscriptions").rows.extend(
        [
            {
                "id": "s1",
                "user_id": "u1",
                "listing_id": "l-drop",
                "kind": "price_drop",
                "baseline_price_ngwee": 50_000,
                "target_price_ngwee": None,
                "active": True,
            },
            {
                "id": "s2",
                "user_id": "u1",
                "listing_id": "l-stock",
                "kind": "back_in_stock",
                "baseline_price_ngwee": 10_000,
                "active": True,
            },
            {
                "id": "s3",
                "user_id": "u2",
                "listing_id": "l-same",
                "kind": "price_drop",
                "baseline_price_ngwee": 50_000,
                "active": True,
            },
        ]
    )
    result = TickResult()
    run_listing_alerts(client, now=NOW, result=result)
    assert result.price_drop_enqueued == 1 and result.back_in_stock_enqueued == 1
    outbox = client.table("notification_outbox").rows
    assert {row["template"] for row in outbox} == {"price_drop_alert", "back_in_stock_alert"}
    assert all(row["payload"]["recipient_id"] == "u1" for row in outbox)
    subs = {row["id"]: row for row in client.table("listing_alert_subscriptions").rows}
    assert subs["s1"]["baseline_price_ngwee"] == 40_000
    assert subs["s2"]["active"] is False
    # A second tick with no further change enqueues nothing new.
    second = TickResult()
    run_listing_alerts(client, now=NOW, result=second)
    assert second.price_drop_enqueued == 0 and second.back_in_stock_enqueued == 0


def test_tick_saved_search_respects_frequency() -> None:
    client = FakeClient()
    client.table("search_documents").rows.append(
        {
            "entity_id": "x",
            "entity_kind": "listing",
            "is_public": True,
            "title": "Solar panel",
            "category_path": "electronics/solar-power",
            "price_min_ngwee": 90_000,
            "updated_at": (NOW - timedelta(hours=2)).isoformat(),
        }
    )
    client.table("saved_searches").rows.extend(
        [
            {
                "id": "due",
                "user_id": "u1",
                "query": "solar",
                "filters": {"max_price": 100_000},
                "alert_enabled": True,
                "alert_frequency": "daily",
                "last_alerted_at": (NOW - timedelta(days=2)).isoformat(),
            },
            {
                "id": "recent",
                "user_id": "u2",
                "query": "solar",
                "filters": {},
                "alert_enabled": True,
                "alert_frequency": "weekly",
                "last_alerted_at": (NOW - timedelta(days=1)).isoformat(),
            },
        ]
    )
    result = TickResult()
    run_saved_search_alerts(client, now=NOW, result=result)
    assert result.saved_search_enqueued == 1
    assert client.table("notification_outbox").rows[0]["payload"]["saved_search_id"] == "due"
