"""W8 vendor offers API — authz, validation, abuse caps, rate limit, flag gate."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from app.deps import get_supabase_client
from app.main import create_app
from fastapi.testclient import TestClient

USER_A = "11111111-1111-4111-8111-111111111111"
USER_B = "22222222-2222-4222-8222-222222222222"
VENDOR_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
VENDOR_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
LA1 = "a1000000-0000-4000-8000-000000000001"
LA2 = "a2000000-0000-4000-8000-000000000002"
LA3 = "a3000000-0000-4000-8000-000000000003"
LB1 = "b1000000-0000-4000-8000-000000000001"
SERVICE_A = "5a000000-0000-4000-8000-000000000001"


class FakeQuery:
    def __init__(self, table: FakeTable) -> None:
        self.table = table
        self.filters: list[tuple[str, str, Any]] = []
        self.op = "select"
        self.payload: Any = None
        self.single = False
        self.order_by: tuple[str, bool] | None = None

    def select(self, *_a: Any, **_k: Any) -> FakeQuery:
        return self

    def eq(self, col: str, val: Any) -> FakeQuery:
        self.filters.append(("eq", col, val))
        return self

    def neq(self, col: str, val: Any) -> FakeQuery:
        self.filters.append(("neq", col, val))
        return self

    def in_(self, col: str, vals: list[Any]) -> FakeQuery:
        self.filters.append(("in", col, list(vals)))
        return self

    def lte(self, *_a: Any) -> FakeQuery:
        return self

    def order(self, col: str, *, desc: bool = False) -> FakeQuery:
        self.order_by = (col, desc)
        return self

    def maybe_single(self) -> FakeQuery:
        self.single = True
        return self

    def insert(self, payload: Any) -> FakeQuery:
        self.op, self.payload = "insert", payload
        return self

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self.op, self.payload = "update", payload
        return self

    def delete(self) -> FakeQuery:
        self.op = "delete"
        return self

    def _match(self, row: dict[str, Any]) -> bool:
        for op, col, val in self.filters:
            if op == "eq" and row.get(col) != val:
                return False
            if op == "neq" and row.get(col) == val:
                return False
            if op == "in" and row.get(col) not in val:
                return False
        return True

    def execute(self) -> MagicMock:
        rows = self.table.rows
        if self.op == "insert":
            payloads = self.payload if isinstance(self.payload, list) else [self.payload]
            out = []
            for p in payloads:
                row = {"id": str(uuid4()), "gift_stock_reserved": 0, **p}
                rows.append(row)
                out.append(row)
            return MagicMock(data=out)
        matched = [r for r in rows if self._match(r)]
        if self.op == "update":
            for r in matched:
                r.update(self.payload)
            return MagicMock(data=matched)
        if self.op == "delete":
            self.table.rows = [r for r in rows if not self._match(r)]
            return MagicMock(data=matched)
        if self.order_by:
            col, desc = self.order_by
            matched = sorted(matched, key=lambda r: str(r.get(col) or ""), reverse=desc)
        if self.single:
            return MagicMock(data=matched[0] if matched else None)
        return MagicMock(data=matched)


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(FakeQuery(self), name)


class FakeClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {}

    def table(self, name: str) -> FakeTable:
        return self.tables.setdefault(name, FakeTable())


@pytest.fixture
def fake() -> FakeClient:
    client = FakeClient()
    client.table("feature_flags").rows.append({"flag": "bundles", "enabled": True})
    client.table("platform_config").rows.append({"key": "bundles_max_discount_pct", "value": 80})
    client.table("vendors").rows.extend(
        [
            {
                "id": VENDOR_A,
                "owner_user_id": USER_A,
                "status": "active",
                "display_name": "Shop A",
            },
            {
                "id": VENDOR_B,
                "owner_user_id": USER_B,
                "status": "active",
                "display_name": "Shop B",
            },
        ]
    )
    client.table("vendor_listings").rows.extend(
        [
            {
                "id": LA1,
                "vendor_id": VENDOR_A,
                "price_ngwee": 10_000,
                "status": "active",
                "title_override": "Kit",
            },
            {
                "id": LA2,
                "vendor_id": VENDOR_A,
                "price_ngwee": 2_000,
                "status": "active",
                "title_override": "Brush",
            },
            {
                "id": LA3,
                "vendor_id": VENDOR_A,
                "price_ngwee": 1_000,
                "status": "removed",
                "title_override": "Old",
            },
            {
                "id": LB1,
                "vendor_id": VENDOR_B,
                "price_ngwee": 5_000,
                "status": "active",
                "title_override": "Theirs",
            },
        ]
    )
    client.table("services").rows.append(
        {
            "id": SERVICE_A,
            "vendor_id": VENDOR_A,
            "title": "Facial",
            "status": "active",
            "from_price_ngwee": 15_000,
        }
    )
    return client


@pytest.fixture
def rate_calls() -> list[str]:
    return []


@pytest.fixture
def api(
    monkeypatch: pytest.MonkeyPatch, fake: FakeClient, rate_calls: list[str]
) -> Generator[TestClient, None, None]:
    def verify(token: str, settings: Any) -> dict[str, Any]:
        return {"sub": USER_A if token == "a" else USER_B, "exp": 9_999_999_999}

    monkeypatch.setattr("app.core.auth.verify_supabase_jwt", verify)
    monkeypatch.setattr(
        "app.core.auth._load_user_roles", lambda uid, service_client: frozenset({"vendor"})
    )

    def bump(**kwargs: Any) -> tuple[bool, int]:
        rate_calls.append(kwargs["scope"])
        return (len(rate_calls) <= 100, 30)

    monkeypatch.setattr("app.routers.vendor_offers.bump_rate_counter", bump)
    wrapper = MagicMock()
    wrapper.client = fake
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: wrapper)
    monkeypatch.setattr("app.supabase_client.get_supabase_service_client", lambda: wrapper)
    monkeypatch.setattr("app.core.admin_audit.get_supabase_service_client", lambda: wrapper)
    app = create_app()
    app.dependency_overrides[get_supabase_client] = lambda: wrapper
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


def H(who: str = "a") -> dict[str, str]:
    return {"Authorization": f"Bearer {who}"}


def bundle_body(**over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "offer_type": "bundle",
        "title": "Kit + brush",
        "status": "active",
        "bundle_pricing": "addon_percent_off",
        "addon_percent_off": 75,
        "items": [
            {"role": "anchor", "item_kind": "product", "ref_id": LA1},
            {"role": "addon", "item_kind": "product", "ref_id": LA2},
        ],
    }
    body.update(over)
    return body


def test_create_list_and_preview(api: TestClient, rate_calls: list[str]) -> None:
    res = api.post("/vendor/offers", json=bundle_body(), headers=H())
    assert res.status_code == 201, res.text
    offer = res.json()
    assert offer["vendor_id"] == VENDOR_A
    assert [i["ref_id"] for i in offer["items"]] == [LA1, LA2]
    assert "vendor_offers_write" in rate_calls
    listed = api.get("/vendor/offers", headers=H()).json()
    assert [o["id"] for o in listed["items"]] == [offer["id"]]
    assert listed["max_discount_pct"] == 80
    preview = api.post("/vendor/offers/preview", json=bundle_body(), headers=H()).json()
    assert preview["applies"] is True
    assert preview["list_total_ngwee"] == 12_000
    assert preview["savings_ngwee"] == 1_500
    assert preview["pay_ngwee"] == 10_500


def test_vendor_b_cannot_read_edit_or_archive_vendor_a_offer(api: TestClient) -> None:
    offer_id = api.post("/vendor/offers", json=bundle_body(), headers=H()).json()["id"]
    assert api.get(f"/vendor/offers/{offer_id}", headers=H("b")).status_code == 404
    patched = api.patch(
        f"/vendor/offers/{offer_id}", json=bundle_body(title="mine"), headers=H("b")
    )
    assert patched.status_code == 404
    assert api.delete(f"/vendor/offers/{offer_id}", headers=H("b")).status_code == 404
    assert api.get(f"/vendor/offers/{offer_id}", headers=H()).json()["title"] == "Kit + brush"
    assert api.get("/vendor/offers", headers=H("b")).json()["items"] == []


def test_foreign_item_is_forbidden(api: TestClient) -> None:
    body = bundle_body(
        items=[
            {"role": "anchor", "item_kind": "product", "ref_id": LA1},
            {"role": "addon", "item_kind": "product", "ref_id": LB1},
        ]
    )
    res = api.post("/vendor/offers", json=body, headers=H())
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "offers.item_forbidden"


def test_removed_listing_is_refused(api: TestClient) -> None:
    body = bundle_body(
        items=[
            {"role": "anchor", "item_kind": "product", "ref_id": LA1},
            {"role": "addon", "item_kind": "product", "ref_id": LA3},
        ]
    )
    res = api.post("/vendor/offers", json=body, headers=H())
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "offers.item_unavailable"


def test_discount_over_admin_cap_is_refused(api: TestClient) -> None:
    res = api.post("/vendor/offers", json=bundle_body(addon_percent_off=90), headers=H())
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "offers.discount_too_large"


def test_fixed_price_must_save(api: TestClient) -> None:
    body = bundle_body(
        bundle_pricing="fixed_price", addon_percent_off=None, bundle_price_ngwee=12_000
    )
    res = api.post("/vendor/offers", json=body, headers=H())
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "offers.no_saving"


@pytest.mark.parametrize(
    "body",
    [
        bundle_body(addon_percent_off=None),  # missing pricing field
        bundle_body(bundle_price_ngwee=1.5),  # float money
        bundle_body(bundle_price_ngwee="100"),  # string money
        bundle_body(buy_n=3),  # field of another type
        {
            "offer_type": "bxgy",
            "title": "x",
            "buy_qty": 2,
            "get_qty": 1,
            "items": [{"role": "trigger", "item_kind": "product", "ref_id": LA1}],
        },  # no reward
        {
            "offer_type": "buy_n_pay_m",
            "title": "x",
            "buy_n": 2,
            "pay_m": 2,
            "items": [{"role": "eligible", "item_kind": "product", "ref_id": LA1}],
        },
        bundle_body(items=[{"role": "anchor", "item_kind": "product", "ref_id": "nope"}]),
        bundle_body(per_customer_limit=0),  # limit below 1
        bundle_body(per_customer_limit=1001),  # above the DB check
        bundle_body(per_customer_limit="2"),  # string, strict model
    ],
)
def test_invalid_shapes_are_422(api: TestClient, body: dict[str, Any]) -> None:
    assert api.post("/vendor/offers", json=body, headers=H()).status_code == 422


def test_per_customer_limit_round_trips_and_can_be_cleared(api: TestClient) -> None:
    created = api.post("/vendor/offers", json=bundle_body(per_customer_limit=2), headers=H())
    assert created.status_code == 201, created.text
    offer = created.json()
    assert offer["per_customer_limit"] == 2
    cleared = api.patch(
        f"/vendor/offers/{offer['id']}", json=bundle_body(per_customer_limit=None), headers=H()
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["per_customer_limit"] is None


def test_service_trigger_gift_offer_is_allowed_but_not_cart_applicable(api: TestClient) -> None:
    body = {
        "offer_type": "free_gift",
        "title": "Facial + free lotion",
        "gift_stock_total": 10,
        "items": [
            {"role": "trigger", "item_kind": "service", "ref_id": SERVICE_A},
            {"role": "reward", "item_kind": "product", "ref_id": LA2},
        ],
    }
    res = api.post("/vendor/offers", json=body, headers=H())
    assert res.status_code == 201, res.text
    assert res.json()["cart_applicable"] is False


def test_gift_stock_cannot_drop_below_reserved(api: TestClient, fake: FakeClient) -> None:
    body = {
        "offer_type": "free_gift",
        "title": "Free brush",
        "gift_stock_total": 10,
        "items": [
            {"role": "trigger", "item_kind": "product", "ref_id": LA1},
            {"role": "reward", "item_kind": "product", "ref_id": LA2},
        ],
    }
    offer_id = api.post("/vendor/offers", json=body, headers=H()).json()["id"]
    next(r for r in fake.table("offers").rows if r["id"] == offer_id)["gift_stock_reserved"] = 4
    res = api.patch(f"/vendor/offers/{offer_id}", json={**body, "gift_stock_total": 3}, headers=H())
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "offers.gift_stock_below_reserved"


def test_type_is_immutable(api: TestClient) -> None:
    offer_id = api.post("/vendor/offers", json=bundle_body(), headers=H()).json()["id"]
    body = {
        "offer_type": "buy_n_pay_m",
        "title": "x",
        "buy_n": 3,
        "pay_m": 2,
        "items": [{"role": "eligible", "item_kind": "product", "ref_id": LA1}],
    }
    res = api.patch(f"/vendor/offers/{offer_id}", json=body, headers=H())
    assert res.status_code == 422


def test_rate_limited(api: TestClient, rate_calls: list[str]) -> None:
    rate_calls.extend(["x"] * 100)
    res = api.post("/vendor/offers", json=bundle_body(), headers=H())
    assert res.status_code == 429


def test_flag_off_hides_vendor_offers(api: TestClient, fake: FakeClient) -> None:
    fake.table("feature_flags").rows[0]["enabled"] = False
    assert api.get("/vendor/offers", headers=H()).status_code == 404
    assert api.post("/vendor/offers", json=bundle_body(), headers=H()).status_code == 404


def test_archive_soft_deletes(api: TestClient) -> None:
    offer_id = api.post("/vendor/offers", json=bundle_body(), headers=H()).json()["id"]
    assert api.delete(f"/vendor/offers/{offer_id}", headers=H()).json()["status"] == "archived"
    assert api.get("/vendor/offers", headers=H()).json()["items"] == []


def test_public_badges_and_pdp_bundle(api: TestClient, fake: FakeClient) -> None:
    offer_id = api.post(
        "/vendor/offers",
        json=bundle_body(starts_at="2026-01-01T00:00:00+00:00"),
        headers=H(),
    ).json()["id"]
    badges = api.get(f"/offers/badges?listing_ids={LA1},{LA2},{LB1}").json()["badges"]
    assert set(badges) == {LA1, LA2}
    assert badges[LA1]["offer_type"] == "bundle"
    assert badges[LA1]["addon_percent_off"] == 75
    pdp = api.get(f"/offers/listing/{LA1}").json()["offers"]
    assert [o["id"] for o in pdp] == [offer_id]
    assert pdp[0]["list_total_ngwee"] == 12_000
    assert pdp[0]["pay_ngwee"] == 10_500
    fake.table("feature_flags").rows[0]["enabled"] = False
    assert api.get(f"/offers/badges?listing_ids={LA1}").json()["badges"] == {}
    assert api.get(f"/offers/listing/{LA1}").json()["offers"] == []


def test_public_hides_gift_offer_when_pool_is_empty(api: TestClient, fake: FakeClient) -> None:
    body = {
        "offer_type": "free_gift",
        "title": "Free brush",
        "status": "active",
        "starts_at": "2026-01-01T00:00:00+00:00",
        "gift_stock_total": 2,
        "items": [
            {"role": "trigger", "item_kind": "product", "ref_id": LA1},
            {"role": "reward", "item_kind": "product", "ref_id": LA2},
        ],
    }
    offer_id = api.post("/vendor/offers", json=body, headers=H()).json()["id"]
    assert LA1 in api.get(f"/offers/badges?listing_ids={LA1}").json()["badges"]
    next(r for r in fake.table("offers").rows if r["id"] == offer_id)["gift_stock_reserved"] = 2
    assert api.get(f"/offers/badges?listing_ids={LA1}").json()["badges"] == {}


def test_admin_pause_overrides_vendor(
    api: TestClient, fake: FakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    offer_id = api.post(
        "/vendor/offers", json=bundle_body(starts_at="2026-01-01T00:00:00+00:00"), headers=H()
    ).json()["id"]
    # Vendor role cannot reach the admin route.
    assert api.post(f"/admin/offers/{offer_id}/pause", json={}, headers=H()).status_code == 403
    monkeypatch.setattr(
        "app.core.auth._load_user_roles", lambda uid, service_client: frozenset({"admin"})
    )
    res = api.post(f"/admin/offers/{offer_id}/pause", json={"note": "abuse"}, headers=H("b"))
    assert res.status_code == 200, res.text
    assert res.json()["paused_by_admin"] is True
    assert res.json()["live"] is False
    audit = [r for r in fake.table("audit_log").rows if r.get("action") == "offer.admin_pause"]
    assert len(audit) == 1
    assert api.get(f"/offers/badges?listing_ids={LA1}").json()["badges"] == {}


def _as_roles(monkeypatch: pytest.MonkeyPatch, *roles: str) -> None:
    monkeypatch.setattr(
        "app.core.auth._load_user_roles", lambda uid, service_client: frozenset(roles)
    )


def test_admin_offer_list_filters_and_vendor_names(
    api: TestClient, fake: FakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    live = api.post("/vendor/offers", json=bundle_body(title="Live kit"), headers=H()).json()
    draft = api.post(
        "/vendor/offers", json=bundle_body(title="Draft kit", status="draft"), headers=H()
    ).json()
    theirs = api.post(
        "/vendor/offers",
        json={
            "offer_type": "buy_n_pay_m",
            "title": "3 for 2",
            "status": "active",
            "buy_n": 3,
            "pay_m": 2,
            "items": [{"role": "eligible", "item_kind": "product", "ref_id": LB1}],
        },
        headers=H("b"),
    ).json()
    # A vendor cannot list across vendors through the admin route.
    assert api.get("/admin/offers", headers=H()).status_code == 403
    _as_roles(monkeypatch, "admin")
    every = api.get("/admin/offers", headers=H()).json()
    assert {o["id"] for o in every["items"]} == {live["id"], draft["id"], theirs["id"]}
    assert every["truncated"] is False
    by_id = {o["id"]: o for o in every["items"]}
    assert by_id[theirs["id"]]["vendor_name"] == "Shop B"
    assert by_id[live["id"]]["vendor_name"] == "Shop A"

    def ids(query: str) -> set[str]:
        res = api.get(f"/admin/offers?{query}", headers=H())
        assert res.status_code == 200, res.text
        return {o["id"] for o in res.json()["items"]}

    assert ids("status=draft") == {draft["id"]}
    assert ids("offer_type=buy_n_pay_m") == {theirs["id"]}
    assert ids(f"vendor_id={VENDOR_B}") == {theirs["id"]}
    assert ids("q=KIT") == {live["id"], draft["id"]}
    assert ids("state=live") == {live["id"], theirs["id"]}
    api.post(f"/admin/offers/{theirs['id']}/pause", json={"note": "abuse"}, headers=H())
    assert ids("state=admin_paused") == {theirs["id"]}
    assert ids("state=live") == {live["id"]}
    # Unknown filter values are validation errors, not silent "all".
    assert api.get("/admin/offers?status=bogus", headers=H()).status_code == 422
    assert api.get("/admin/offers?state=bogus", headers=H()).status_code == 422


def test_admin_unpause_is_audited_and_restores_live(
    api: TestClient, fake: FakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    offer_id = api.post(
        "/vendor/offers", json=bundle_body(starts_at="2026-01-01T00:00:00+00:00"), headers=H()
    ).json()["id"]
    _as_roles(monkeypatch, "admin")
    paused = api.post(f"/admin/offers/{offer_id}/pause", json={"note": "check"}, headers=H())
    assert paused.json()["admin_note"] == "check"
    res = api.post(f"/admin/offers/{offer_id}/unpause", json={}, headers=H())
    assert res.status_code == 200, res.text
    assert res.json()["paused_by_admin"] is False
    assert res.json()["live"] is True
    actions = [
        r.get("action")
        for r in fake.table("audit_log").rows
        if r.get("entity_id") == offer_id and str(r.get("action")).startswith("offer.admin")
    ]
    assert actions == ["offer.admin_pause", "offer.admin_unpause"]
    unpause = next(
        r for r in fake.table("audit_log").rows if r.get("action") == "offer.admin_unpause"
    )
    assert unpause["before"]["paused_by_admin"] is True
    assert unpause["after"]["paused_by_admin"] is False


def test_admin_offer_routes_follow_the_permission_map(
    api: TestClient, fake: FakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    offer_id = api.post("/vendor/offers", json=bundle_body(), headers=H()).json()["id"]
    fake.table("admin_roles").rows.extend(
        [
            {"key": "rbac_ads", "permissions": ["ads.manage"]},
            {"key": "rbac_finance", "permissions": ["finance.read"]},
        ]
    )
    wrapper = MagicMock()
    wrapper.client = fake
    monkeypatch.setattr("app.core.auth.get_supabase_service_client", lambda: wrapper)
    # A custom role without ads.manage is refused on every admin offers route.
    _as_roles(monkeypatch, "rbac_finance")
    assert api.get("/admin/offers", headers=H()).status_code == 403
    assert api.post(f"/admin/offers/{offer_id}/pause", json={}, headers=H()).status_code == 403
    assert api.post(f"/admin/offers/{offer_id}/unpause", json={}, headers=H()).status_code == 403
    # Customers and moderators (no ads.manage) are refused too.
    for roles in (("customer",), ("moderator",)):
        _as_roles(monkeypatch, *roles)
        assert api.get("/admin/offers", headers=H()).status_code == 403
    # A custom role granted ads.manage may list and pause.
    _as_roles(monkeypatch, "rbac_ads")
    assert api.get("/admin/offers", headers=H()).status_code == 200
    res = api.post(f"/admin/offers/{offer_id}/pause", json={}, headers=H())
    assert res.status_code == 200, res.text
    assert not [
        r for r in fake.table("audit_log").rows if r.get("action") == "offer.admin_unpause"
    ]
    assert api.post(
        "/admin/offers/not-a-uuid/pause", json={}, headers=H()
    ).status_code == 404
