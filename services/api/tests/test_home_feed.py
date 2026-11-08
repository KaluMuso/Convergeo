"""Home feed resolver, ads interleave, admin CRUD/authz and state-machine paths."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.main import create_app
from app.routers.catalog import CatalogCandidate
from app.services.home_feed import resolver
from app.services.home_feed.models import (
    PlacementCreate,
    SectionConfig,
    SectionCreate,
    SectionRule,
    validate_cta_href,
)
from app.services.home_feed.personalization import (
    CategoryAffinityRecommender,
    UserSignals,
)
from fastapi.testclient import TestClient
from pydantic import ValidationError

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
ADMIN_ID = "00000000-0000-0000-0000-0000000a0001"
CUSTOMER_ID = "00000000-0000-0000-0000-0000000c0001"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeQuery:
    def __init__(self, table: FakeTable) -> None:
        self.table = table
        self.filters: list[tuple[str, str, Any]] = []
        self.op: str | None = None
        self.payload: Any = None
        self.order_by: tuple[str, bool] | None = None

    def select(self, *_args: Any, **_kwargs: Any) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self.filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self.filters.append(("in", column, list(values)))
        return self

    def gte(self, column: str, value: Any) -> FakeQuery:
        self.filters.append(("gte", column, value))
        return self

    def order(self, column: str, *, desc: bool = False) -> FakeQuery:
        self.order_by = (column, desc)
        return self

    def limit(self, _count: int) -> FakeQuery:
        return self

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        self.op, self.payload = "insert", payload
        return self

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self.op, self.payload = "update", payload
        return self

    def delete(self) -> FakeQuery:
        self.op = "delete"
        return self

    def _match(self, row: dict[str, Any]) -> bool:
        for kind, column, value in self.filters:
            if kind == "eq" and row.get(column) != value:
                return False
            if kind == "in" and row.get(column) not in value:
                return False
            if kind == "gte" and str(row.get(column, "")) < str(value):
                return False
        return True

    def execute(self) -> MagicMock:
        rows = self.table.rows
        if self.op == "insert":
            row = {"id": f"00000000-0000-4000-8000-{len(rows) + 1:012d}", **self.payload}
            row.setdefault("updated_at", NOW.isoformat())
            rows.append(row)
            return MagicMock(data=[dict(row)])
        if self.op == "update":
            out = []
            for row in rows:
                if self._match(row):
                    row.update(self.payload)
                    out.append(dict(row))
            return MagicMock(data=out)
        if self.op == "delete":
            self.table.rows = [row for row in rows if not self._match(row)]
            return MagicMock(data=[])
        result = [dict(row) for row in rows if self._match(row)]
        if self.order_by:
            column, desc = self.order_by
            result.sort(key=lambda row: str(row.get(column) or "").zfill(12), reverse=desc)
        return MagicMock(data=result)


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(FakeQuery(self), name)


class FakeRpc:
    def __init__(self, client: FakeClient, name: str, params: dict[str, Any]) -> None:
        self.client, self.name, self.params = client, name, params

    def execute(self) -> MagicMock:
        self.client.rpc_calls.append((self.name, self.params))
        if self.name == "bump_rate_counter":
            return MagicMock(data=[{"allowed": True, "retry_after": 0}])
        if self.name == "transition_ad_placement":
            row = next(
                r
                for r in self.client.tables["ad_placements"].rows
                if r["id"] == self.params["p_placement_id"]
            )
            allowed = {
                "draft": {"scheduled"},
                "scheduled": {"active", "paused", "draft", "ended"},
                "active": {"paused", "ended"},
                "paused": {"active", "scheduled", "ended"},
            }.get(row["status"], set())
            if self.params["p_to_status"] not in allowed:
                raise RuntimeError("Invalid ad placement transition")
            row["status"] = self.params["p_to_status"]
            return MagicMock(data=dict(row))
        if self.name == "record_ad_placement_events":
            return MagicMock(data=1)
        return MagicMock(data=None)


class FakeClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {}
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []

    def table(self, name: str) -> FakeTable:
        return self.tables.setdefault(name, FakeTable())

    def rpc(self, name: str, params: dict[str, Any]) -> FakeRpc:
        return FakeRpc(self, name, params)


def _candidate(
    listing_id: str,
    *,
    path: str,
    price: int,
    title: str = "Item",
    rating: float = 0.0,
    in_stock: bool = True,
    created_at: str = "2026-11-01T00:00:00+00:00",
    product_id: str | None = None,
) -> CatalogCandidate:
    return CatalogCandidate.model_validate(
        {
            "search_doc": {
                "entity_id": listing_id,
                "title": title,
                "category_path": path,
                "price_min_ngwee": price,
                "boost_signals": {},
            },
            "listing": {
                "id": listing_id,
                "vendor_id": "v1",
                "product_id": product_id,
                "condition": "new",
                "stock_mode": "always_available",
                "created_at": created_at,
            },
            "vendor": {"display_name": "Shop", "slug": "shop"},
            "product": None,
            "image_public_id": None,
            "landmark": None,
            "rating": rating,
            "review_count": int(rating),
            "in_stock": in_stock,
        }
    )


CANDIDATES = [
    _candidate(
        "l-phone", path="electronics/mobile-phones", price=250_000, rating=4.5, product_id="p-phone"
    ),
    _candidate("l-case", path="electronics/phone-accessories", price=8_000, title="Summer case"),
    _candidate("l-dress", path="fashion/womens-clothing", price=30_000, rating=5.0),
    _candidate("l-oos", path="fashion/mens-clothing", price=5_000, in_stock=False),
]


def _section(key: str, section_type: str, position: int, **extra: Any) -> dict[str, Any]:
    return {
        "id": f"sec-{key}",
        "key": key,
        "section_type": section_type,
        "layout": "ad" if section_type == "ad_slot" else "rail",
        "title_key": None if section_type == "ad_slot" else f"home.feed.sections.{key}",
        "title_i18n": {},
        "config": {},
        "position": position,
        "enabled": True,
        "starts_at": None,
        "ends_at": None,
        "audience": "all",
        **extra,
    }


def _placement(pid: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": pid,
        "advertiser_kind": "external",
        "advertiser_vendor_id": None,
        "advertiser_name": "Acme",
        "placement_type": "feed_slot",
        "image_public_id": "ads/acme",
        "headline": "Acme sale",
        "body": None,
        "cta_label": "Shop",
        "cta_href": "/en/search",
        "starts_at": (NOW - timedelta(days=1)).isoformat(),
        "ends_at": (NOW + timedelta(days=1)).isoformat(),
        "priority": 0,
        "paid_amount_ngwee": 150_000,
        "payment_reference": "inv-1",
        "status": "active",
        "enabled": True,
        **extra,
    }


def _feed_client(sections: list[dict[str, Any]], placements: list[dict[str, Any]]) -> FakeClient:
    client = FakeClient()
    client.table("home_feed_sections").rows = sections
    client.table("ad_placements").rows = placements
    return client


def _page(client: FakeClient, **kwargs: Any) -> Any:
    kwargs.setdefault("cursor", None)
    kwargs.setdefault("now", NOW)
    return resolver.build_feed_page(client, candidate_loader=lambda _c: CANDIDATES, **kwargs)


@pytest.fixture(autouse=True)
def _no_trending(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.discovery.trending.fetch_trending_listings",
        lambda _client, limit=24: [MagicMock(listing_id="l-case")],
    )


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


def test_rule_sections_filter_and_skip_empty() -> None:
    sections = [
        _section(
            "under_k100",
            "rule",
            10,
            config={"rule": {"price_max_ngwee": 10_000, "sort": "cheapest"}},
        ),
        _section("empty", "rule", 20, config={"rule": {"category_paths": ["groceries"]}}),
        _section("fashion", "category", 30, config={"category_path": "fashion"}),
    ]
    page = _page(_feed_client(sections, []), page_size=8)
    keys = [section.key for section in page.sections]
    assert keys == ["under_k100", "fashion"]
    # Out-of-stock listing never appears even though it is under K100.
    assert [item.id for item in page.sections[0].listings] == ["l-case"]
    assert page.next_cursor is None


def test_cursor_pagination_is_stable_and_continues() -> None:
    sections = [
        _section(f"s{i}", "category", i, config={"category_path": "electronics"})
        for i in range(1, 6)
    ]
    client = _feed_client(sections, [])
    first = _page(client, page_size=2)
    assert [s.key for s in first.sections] == ["s1", "s2"]
    assert first.next_cursor == "v1.2"
    second = _page(client, cursor=first.next_cursor, page_size=2)
    assert [s.key for s in second.sections] == ["s3", "s4"]
    with pytest.raises(ValueError):
        _page(client, cursor="garbage")


def test_disabled_and_out_of_window_sections_hidden() -> None:
    sections = [
        _section("off", "category", 1, enabled=False, config={"category_path": "fashion"}),
        _section(
            "future",
            "category",
            2,
            config={"category_path": "fashion"},
            starts_at=(NOW + timedelta(days=1)).isoformat(),
        ),
        _section(
            "past",
            "category",
            3,
            config={"category_path": "fashion"},
            ends_at=(NOW - timedelta(hours=1)).isoformat(),
        ),
        _section(
            "members", "category", 4, config={"category_path": "fashion"}, audience="signed_in"
        ),
        _section("live", "category", 5, config={"category_path": "fashion"}),
    ]
    page = _page(_feed_client(sections, []), page_size=8)
    assert [s.key for s in page.sections] == ["live"]


def test_ads_interleave_and_hidden_when_disabled_or_out_of_window() -> None:
    sections = [
        _section("a", "category", 1, config={"category_path": "fashion"}),
        _section("ad1", "ad_slot", 2),
        _section("ad2", "ad_slot", 3),
    ]
    placements = [
        _placement("ad-low", priority=1),
        _placement("ad-high", priority=9),
        _placement("ad-off", priority=99, enabled=False),
        _placement("ad-expired", priority=99, ends_at=(NOW - timedelta(minutes=1)).isoformat()),
        _placement("ad-draft", priority=99, status="draft"),
        _placement("ad-paused", priority=99, status="paused"),
        _placement("slide", placement_type="carousel_slide"),
    ]
    page = _page(_feed_client(sections, placements), page_size=8)
    ads = [s.ad.placement_id for s in page.sections if s.ad]
    assert ads == ["ad-high", "ad-low"]
    assert [slide.placement_id for slide in page.carousel] == ["slide"]
    assert page.carousel[0].sponsored is True
    dumped = page.model_dump()
    assert "paid_amount_ngwee" not in str(dumped)


def test_ad_slot_without_placement_renders_nothing() -> None:
    sections = [_section("ad1", "ad_slot", 1)]
    page = _page(_feed_client(sections, []), page_size=4)
    assert page.sections == []


def test_for_you_guest_falls_back_to_trending() -> None:
    sections = [_section("for_you", "for_you", 1)]
    page = _page(_feed_client(sections, []), page_size=4)
    assert page.sections[0].explanation is not None
    assert page.sections[0].explanation.basis == "trending"
    assert [item.id for item in page.sections[0].listings] == ["l-case"]


def test_for_you_personal_ranks_by_category_affinity() -> None:
    signals = UserSignals(
        viewed_product_ids={"p-phone"}, cart_listing_ids=set(), purchased_listing_ids=set()
    )
    ranked = CategoryAffinityRecommender().rank(CANDIDATES, signals)
    assert ranked.personal is True
    assert ranked.top_categories == ["electronics"]
    assert [row.listing.id for row in ranked.candidates] == ["l-phone", "l-case"]

    purchased = UserSignals(set(), set(), {"l-phone"})
    ranked = CategoryAffinityRecommender().rank(CANDIDATES, purchased)
    assert "l-phone" not in [row.listing.id for row in ranked.candidates]


def test_rule_keyword_and_new_within_days() -> None:
    rule = SectionRule(keywords=["summer"], new_within_days=30)
    assert [r.listing.id for r in resolver.apply_rule(CANDIDATES, rule, now=NOW)] == ["l-case"]
    old = SectionRule(new_within_days=1)
    assert resolver.apply_rule(CANDIDATES, old, now=NOW) == []


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_section_create_validation_failures() -> None:
    with pytest.raises(ValidationError):
        SectionCreate(key="x", section_type="rule", title_key="a.b")  # key too short
    with pytest.raises(ValidationError):
        SectionCreate(key="rule_one", section_type="rule", title_key="a.b")  # rule missing
    with pytest.raises(ValidationError):
        SectionCreate(key="ad_one", section_type="ad_slot", layout="rail")
    with pytest.raises(ValidationError):
        SectionConfig(view_all_href="https://evil.example")
    with pytest.raises(ValidationError):
        SectionRule(price_min_ngwee=500, price_max_ngwee=100)
    ok = SectionCreate(key="ad_one", section_type="ad_slot", layout="ad")
    assert ok.layout == "ad"


def test_cta_href_allow_list() -> None:
    hosts = frozenset({"acme.co.zm"})
    assert validate_cta_href("/en/c/fashion", hosts) == "/en/c/fashion"
    assert validate_cta_href("https://shop.acme.co.zm/x", hosts)
    for bad in (
        "//evil.com",
        "http://acme.co.zm",
        "https://evil.com",
        "javascript:alert(1)",
        "https://acme.co.zm.evil.com/",
        "https://u:p@acme.co.zm/",
    ):
        with pytest.raises(ValueError):
            validate_cta_href(bad, hosts)


def test_placement_create_validation() -> None:
    base = {
        "advertiser_kind": "external",
        "advertiser_name": "Acme",
        "placement_type": "feed_slot",
        "image_public_id": "ads/acme",
        "headline": "Sale",
        "cta_href": "/en",
        "starts_at": NOW.isoformat(),
        "ends_at": (NOW + timedelta(days=1)).isoformat(),
    }
    PlacementCreate.model_validate(base)
    for patch in (
        {"ends_at": NOW.isoformat()},
        {"advertiser_kind": "vendor"},
        {"paid_amount_ngwee": -1},
        {"paid_amount_ngwee": 10.5},
        {"payment_reference": "bad ref!"},
        {"image_public_id": "../../x?y"},
    ):
        with pytest.raises(ValidationError):
            PlacementCreate.model_validate({**base, **patch})


# ---------------------------------------------------------------------------
# HTTP: public + admin
# ---------------------------------------------------------------------------


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeClient:
    client = FakeClient()
    wrapper = MagicMock()
    wrapper.client = client
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: wrapper)
    monkeypatch.setattr("app.core.admin_audit.get_supabase_service_client", lambda: wrapper)
    monkeypatch.setattr("app.core.auth.get_supabase_service_client", lambda: wrapper)
    monkeypatch.setattr(
        "app.services.home_feed.resolver.build_catalog_candidates", lambda _c: CANDIDATES
    )
    monkeypatch.setattr("app.routers.home_feed.get_cached_json", lambda _key: None)
    monkeypatch.setattr("app.routers.home_feed.set_cached_json", lambda *_a, **_k: None)
    return client


@pytest.fixture
def http(fake: FakeClient) -> Generator[TestClient, None, None]:
    with TestClient(create_app(), raise_server_exceptions=False) as test_client:
        yield test_client


def _login(monkeypatch: pytest.MonkeyPatch, user_id: str, roles: frozenset[str]) -> dict[str, str]:
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": user_id, "exp": 9_999_999_999},
    )
    monkeypatch.setattr("app.core.auth._load_user_roles", lambda _uid, _svc: roles)
    return {"Authorization": "Bearer token"}


def test_public_feed_endpoint_is_cacheable(http: TestClient, fake: FakeClient) -> None:
    fake.table("home_feed_sections").rows = [
        _section("fashion", "category", 1, config={"category_path": "fashion"})
    ]
    response = http.get("/home/feed?page_size=2")
    assert response.status_code == 200
    assert response.json()["sections"][0]["key"] == "fashion"
    assert response.headers["cache-control"].startswith("public")
    assert http.get("/home/feed?cursor=bad").status_code == 422


def test_ad_events_counts_are_bounded(http: TestClient, fake: FakeClient) -> None:
    pid = "11111111-1111-4111-8111-111111111111"
    events = [{"placement_id": pid, "kind": "impression"}] * 20
    response = http.post("/home/ads/events", json={"events": events})
    assert response.status_code == 200
    call = [c for c in fake.rpc_calls if c[0] == "record_ad_placement_events"][0]
    assert call[1]["p_impressions"] == 20
    too_many = http.post("/home/ads/events", json={"events": events * 2})
    assert too_many.status_code == 422


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/admin/home-feed/sections"),
        ("POST", "/admin/home-feed/sections"),
        ("POST", "/admin/home-feed/sections/reorder"),
        ("GET", "/admin/ads/placements"),
        ("POST", "/admin/ads/placements"),
        ("POST", "/admin/ads/placements/11111111-1111-4111-8111-111111111111/transition"),
    ],
)
def test_admin_routes_deny_anon_and_customer(
    http: TestClient, monkeypatch: pytest.MonkeyPatch, method: str, path: str
) -> None:
    assert http.request(method, path, json={}).status_code == 401
    headers = _login(monkeypatch, CUSTOMER_ID, frozenset({"customer"}))
    assert http.request(method, path, json={}, headers=headers).status_code == 403


def test_admin_section_crud_reorder_and_audit(
    http: TestClient, fake: FakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _login(monkeypatch, ADMIN_ID, frozenset({"admin"}))
    created = http.post(
        "/admin/home-feed/sections",
        headers=headers,
        json={
            "key": "cheap_finds",
            "section_type": "rule",
            "title_i18n": {"en": "Cheap finds"},
            "config": {"rule": {"price_max_ngwee": 10000}},
            "position": 5,
        },
    )
    assert created.status_code == 201, created.text
    section_id = created.json()["id"]
    dup = http.post(
        "/admin/home-feed/sections",
        headers=headers,
        json={"key": "cheap_finds", "section_type": "ad_slot", "layout": "ad"},
    )
    assert dup.status_code == 409

    second = http.post(
        "/admin/home-feed/sections",
        headers=headers,
        json={"key": "ad_one", "section_type": "ad_slot", "layout": "ad", "position": 1},
    )
    patched = http.patch(
        f"/admin/home-feed/sections/{section_id}", headers=headers, json={"enabled": False}
    )
    assert patched.status_code == 200 and patched.json()["enabled"] is False
    bad = http.patch(
        f"/admin/home-feed/sections/{section_id}", headers=headers, json={"layout": "ad"}
    )
    assert bad.status_code == 422

    order = [section_id, second.json()["id"]]
    reordered = http.post(
        "/admin/home-feed/sections/reorder", headers=headers, json={"ordered_ids": order}
    )
    assert reordered.status_code == 200
    assert [row["id"] for row in reordered.json()] == order
    partial = http.post(
        "/admin/home-feed/sections/reorder", headers=headers, json={"ordered_ids": order[:1]}
    )
    assert partial.status_code == 422
    actions = [row["action"] for row in fake.table("audit_log").rows]
    assert actions.count("home_feed.section.create") == 2
    assert "home_feed.section.reorder" in actions


def test_admin_placement_lifecycle_uses_guarded_transition(
    http: TestClient, fake: FakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _login(monkeypatch, ADMIN_ID, frozenset({"admin"}))
    body = {
        "advertiser_kind": "external",
        "advertiser_name": "Acme Ltd",
        "placement_type": "carousel_slide",
        "image_public_id": "ads/acme",
        "headline": "Acme sale",
        "cta_href": "https://acme.co.zm/sale",
        "starts_at": (NOW - timedelta(days=1)).isoformat(),
        "ends_at": (NOW + timedelta(days=400)).isoformat(),
        "paid_amount_ngwee": 250000,
        "payment_reference": "acme-001",
    }
    rejected = http.post("/admin/ads/placements", headers=headers, json=body)
    assert rejected.status_code == 422  # external host not allow-listed
    monkeypatch.setenv("AD_EXTERNAL_HOST_ALLOWLIST", "acme.co.zm")
    created = http.post("/admin/ads/placements", headers=headers, json=body)
    assert created.status_code == 201, created.text
    placement = created.json()
    assert placement["status"] == "draft" and placement["effective_state"] == "draft"
    pid = placement["id"]

    invalid = http.post(
        f"/admin/ads/placements/{pid}/transition", headers=headers, json={"to_status": "active"}
    )
    assert invalid.status_code == 409
    for status in ("scheduled", "active"):
        moved = http.post(
            f"/admin/ads/placements/{pid}/transition",
            headers=headers,
            json={"to_status": status, "reason": "go"},
        )
        assert moved.status_code == 200, moved.text
    assert moved.json()["effective_state"] == "live"
    # Status cannot be smuggled through PATCH.
    smuggle = http.patch(f"/admin/ads/placements/{pid}", headers=headers, json={"status": "ended"})
    assert smuggle.status_code == 422
    listed = http.get("/admin/ads/placements", headers=headers)
    assert listed.json()[0]["paid_amount_ngwee"] == 250000
    assert "ads.placement.transition" in [row["action"] for row in fake.table("audit_log").rows]
