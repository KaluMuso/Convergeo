"""Vendor sourcing hub + import requests — API layer (no Postgres).

Row-level isolation of the new tables is in tests/rls/test_matrix.py; this module
covers authz (vendor-only, own-only, admin-all), validation, rate limits, audit,
the state machine and that nothing here can move money.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.main import create_app
from app.routers import admin_import_requests, admin_made_in_zambia, vendor_sourcing
from fastapi.testclient import TestClient

ADMIN_ID = "00000000-0000-0000-0000-0000000a0001"
USER_A = "11111111-1111-1111-1111-111111111111"
USER_B = "22222222-2222-2222-2222-222222222222"
CUSTOMER = "33333333-3333-3333-3333-333333333333"
VENDOR_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VENDOR_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
VENDOR_C = "cccccccc-cccc-cccc-cccc-cccccccccccc"
CATEGORY = "d0000000-0000-0000-0000-000000000001"


class FakeQuery:
    def __init__(self, db: FakeDb, table: str) -> None:
        self.db, self.table = db, table
        self.filters: list[tuple[str, str, Any]] = []
        self.op = "select"
        self.payload: Any = None
        self.limit_n: int | None = None

    def select(self, *_a: Any, **_k: Any) -> FakeQuery:
        return self

    def eq(self, c: str, v: Any) -> FakeQuery:
        self.filters.append(("eq", c, v))
        return self

    def neq(self, c: str, v: Any) -> FakeQuery:
        self.filters.append(("neq", c, v))
        return self

    def in_(self, c: str, v: Any) -> FakeQuery:
        self.filters.append(("in", c, list(v)))
        return self

    def contains(self, c: str, v: Any) -> FakeQuery:
        self.filters.append(("contains", c, list(v)))
        return self

    def order(self, *_a: Any, **_k: Any) -> FakeQuery:
        return self

    def limit(self, n: int) -> FakeQuery:
        self.limit_n = n
        return self

    def insert(self, payload: Any) -> FakeQuery:
        self.op, self.payload = "insert", payload
        return self

    def update(self, payload: Any) -> FakeQuery:
        self.op, self.payload = "update", payload
        return self

    def maybe_single(self) -> FakeQuery:
        return self

    @staticmethod
    def _get(row: dict[str, Any], col: str) -> Any:
        if "." in col:
            outer, inner = col.split(".", 1)
            embed = row.get(outer)
            return embed.get(inner) if isinstance(embed, dict) else None
        return row.get(col)

    def _match(self, row: dict[str, Any]) -> bool:
        for op, col, val in self.filters:
            cur = self._get(row, col)
            if op == "eq" and cur != val:
                return False
            if op == "neq" and cur == val:
                return False
            if op == "in" and cur not in val:
                return False
            if op == "contains" and not set(val) <= set(cur or []):
                return False
        return True

    def execute(self) -> MagicMock:
        rows = self.db.rows(self.table)
        self.db.calls.append((self.table, self.op))
        if self.op == "insert":
            new = {
                "id": str(uuid4()),
                "created_at": "2026-11-27T00:00:00+00:00",
                "updated_at": "2026-11-27T00:00:00+00:00",
                **self.payload,
            }
            if self.table == "import_request_quotes":
                new["total_ngwee"] = sum(
                    new[k]
                    for k in (
                        "product_ngwee",
                        "freight_ngwee",
                        "duty_ngwee",
                        "clearing_ngwee",
                        "other_ngwee",
                    )
                )
            rows.append(new)
            return MagicMock(data=[dict(new)])
        matched = [r for r in rows if self._match(r)]
        if self.op == "update":
            for r in matched:
                r.update(self.payload)
            return MagicMock(data=[dict(r) for r in matched])
        if self.limit_n is not None:
            matched = matched[: self.limit_n]
        return MagicMock(data=[dict(r) for r in matched])


class FakeDb:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {}
        self.calls: list[tuple[str, str]] = []

    def rows(self, table: str) -> list[dict[str, Any]]:
        return self.tables.setdefault(table, [])

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self, name)


class FakeService:
    def __init__(self, db: FakeDb) -> None:
        self.client = db


def _vendor(
    vid: str, name: str, *, tier: int = 2, types: list[str] | None = None
) -> dict[str, Any]:
    return {
        "id": vid, "slug": name.lower(), "display_name": name, "status": "active",
        "kyc_tier": tier, "whatsapp_msisdn": "260977000000", "supplier_types": types or [],
        "vendor_locations": [{"landmark": "Cairo Road"}],
        "owner_user_id": {VENDOR_A: USER_A, VENDOR_B: USER_B}.get(vid, "x"),
    }  # fmt: skip


def _listing(lid: str, vendor: dict[str, Any], **kw: Any) -> dict[str, Any]:
    return {
        "id": lid, "vendor_id": vendor["id"], "status": "active", "vendors": vendor,
        "title_override": kw.pop("title", "Bulk sugar"), "price_ngwee": 5000,
        "wholesale": False, "price_tiers": None, "moq": 1, "made_in_zambia_status": None,
        "products": {"name": "Sugar", "category_id": CATEGORY}, "listing_images": [],
        **kw,
    }  # fmt: skip


def make_db() -> FakeDb:
    db = FakeDb()
    a, b, c = (
        _vendor(VENDOR_A, "Alpha"),
        _vendor(VENDOR_B, "Bravo", tier=1),
        _vendor(VENDOR_C, "Charlie", types=["wholesaler", "manufacturer"]),
    )
    db.tables["vendors"] = [a, b, c]
    tiers = [{"min_qty": 10, "price_ngwee": 4000}]
    db.tables["vendor_listings"] = [
        _listing("l-own", a, wholesale=True, price_tiers=tiers, title="Own wholesale"),
        _listing("l-b", b, wholesale=True, price_tiers=tiers, moq=10, title="Bravo flour"),
        _listing("l-c-retail", c, title="Charlie retail"),
        _listing("l-c-mz", c, made_in_zambia_status="approved", wholesale=True,
                 price_tiers=tiers, title="Zambian honey"),
        _listing("l-c-claimed", c, made_in_zambia_status="claimed", title="Claimed jam"),
        _listing("l-c-rejected", c, made_in_zambia_status="rejected", title="Rejected tea"),
        _listing("l-demo", c, wholesale=True, price_tiers=tiers, title="Demo item",
                 listing_images=[{"cloudinary_public_id": "demo/x", "position": 0}]),
    ]  # fmt: skip
    db.tables["listing_images"] = [{"listing_id": "l-demo", "cloudinary_public_id": "demo/x"}]
    db.tables["services"] = [
        {"id": "s-print", "vendor_id": VENDOR_B, "category": "printing-creative",
         "status": "active",
         "title": "Flyer printing", "description": None, "service_area": "Lusaka",
         "from_price_ngwee": 20000, "portfolio_images": [], "vendors": b},
        {"id": "s-beauty", "vendor_id": VENDOR_B, "category": "beauty", "status": "active",
         "title": "Salon", "description": None, "service_area": "Lusaka",
         "from_price_ngwee": None, "portfolio_images": [], "vendors": b},
    ]  # fmt: skip
    return db


class Harness:
    def __init__(self, db: FakeDb, client: TestClient) -> None:
        self.db, self.client = db, client
        self.user = CurrentUser(id=USER_A, roles=frozenset({"vendor"}), token="t")
        self.rate_allowed = True
        self.rate_scopes: list[str] = []

    def as_role(self, user_id: str, *roles: str) -> Harness:
        self.user = CurrentUser(id=user_id, roles=frozenset(roles), token="t")
        return self


@pytest.fixture
def h(monkeypatch: pytest.MonkeyPatch) -> Generator[Harness, None, None]:
    app = create_app()
    holder: dict[str, Harness] = {}

    async def current_user() -> CurrentUser:
        return holder["h"].user

    def service_dep() -> Generator[FakeService, None, None]:
        yield FakeService(holder["h"].db)

    def fake_bump(**kwargs: Any) -> tuple[bool, int]:
        holder["h"].rate_scopes.append(kwargs["scope"])
        return (holder["h"].rate_allowed, 0 if holder["h"].rate_allowed else 30)

    monkeypatch.setattr(vendor_sourcing, "bump_rate_counter", fake_bump)
    monkeypatch.setattr(admin_import_requests, "bump_rate_counter", fake_bump)
    monkeypatch.setattr(admin_made_in_zambia, "bump_rate_counter", fake_bump)
    monkeypatch.setattr(
        "app.core.admin_audit.get_supabase_service_client", lambda: FakeService(holder["h"].db)
    )
    monkeypatch.setattr(
        "app.core.auth.get_supabase_service_client", lambda: FakeService(holder["h"].db)
    )
    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_supabase_client] = service_dep
    with TestClient(app, raise_server_exceptions=False) as client:
        holder["h"] = Harness(make_db(), client)
        yield holder["h"]
    app.dependency_overrides.clear()


AUTH = {"Authorization": "Bearer t"}
BODY: dict[str, Any] = {
    "title": "LED strip lights",
    "description": "5m RGB",
    "reference_url": "https://example.com/item/1",
    "image_urls": ["https://example.com/a.jpg"],
    "quantity": 200,
    "unit": "pcs",
    "target_unit_price_ngwee": 3500,
    "destination_city": "Lusaka",
}
QUOTE: dict[str, Any] = {
    "partner_label": "Partner X",
    "product_ngwee": 700000,
    "freight_ngwee": 150000,
    "duty_ngwee": 120000,
    "clearing_ngwee": 30000,
    "lead_time_days": 35,
    "notes": "Estimate only",
}


def search(h: Harness, **params: Any) -> dict[str, Any]:
    r = h.client.get("/vendor/sourcing/search", params=params, headers=AUTH)
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


# --- authz -------------------------------------------------------------------
@pytest.mark.parametrize("role", ["customer", "admin"])
def test_search_is_vendor_only(h: Harness, role: str) -> None:
    h.as_role(CUSTOMER, role)
    assert h.client.get("/vendor/sourcing/search", headers=AUTH).status_code == 403


def test_wholesale_never_leaks_to_non_vendor_routes(h: Harness) -> None:
    h.as_role(CUSTOMER, "customer")
    for method, path in (
        ("get", "/vendor/sourcing/import-requests"),
        ("get", "/vendor/sourcing/profile"),
        ("get", "/vendor/sourcing/listings"),
    ):
        assert getattr(h.client, method)(path, headers=AUTH).status_code == 403


# --- search ------------------------------------------------------------------
def test_suppliers_tab_lists_other_vendors_wholesale_with_tiers_and_hides_own_and_demo(
    h: Harness,
) -> None:
    data = search(h, tab="suppliers")
    ids = {i["id"] for i in data["items"]}
    assert "l-b" in ids and "l-c-mz" in ids
    assert "l-own" not in ids  # never your own listing
    assert "l-demo" not in ids  # demo media excluded
    assert "l-c-retail" not in ids  # retail listings are not supplies
    bravo = next(i for i in data["items"] if i["id"] == "l-b")
    assert bravo["price_tiers"] == [{"min_qty": 10, "price_ngwee": 4000}]
    assert bravo["moq"] == 10 and bravo["verified"] is False
    assert bravo["prices_locked"] is False and data["viewer_verified"] is True
    shop = next(i for i in data["items"] if i["kind"] == "shop")
    assert shop["id"] == VENDOR_C and shop["verified"] is True


def test_made_in_zambia_tab_shows_approved_only_and_no_shops(h: Harness) -> None:
    data = search(h, tab="made_in_zambia")
    ids = {i["id"] for i in data["items"]}
    assert ids == {"l-c-mz"}  # claimed / rejected / unclaimed and manufacturer shops hidden
    assert data["items"][0]["made_in_zambia"] is True
    # the badge is approved-only on the suppliers tab too
    sup = {i["id"]: i for i in search(h, tab="suppliers")["items"]}
    assert sup["l-c-mz"]["made_in_zambia"] is True and sup["l-b"]["made_in_zambia"] is False


def test_unverified_viewer_gets_locked_prices_server_side(h: Harness) -> None:
    h.as_role(USER_B, "vendor")  # Bravo is kyc_tier 1
    data = search(h, tab="suppliers")
    assert data["viewer_verified"] is False
    listings = [i for i in data["items"] if i["kind"] == "listing"]
    assert listings
    for item in listings:
        assert item["prices_locked"] is True
        assert item["price_ngwee"] is None and item["price_tiers"] is None  # not just hidden in UI
        assert item["title"]  # the card itself is still visible
    assert (
        "4000"
        not in h.client.get(
            "/vendor/sourcing/search", params={"tab": "made_in_zambia"}, headers=AUTH
        ).text
    )


def test_search_text_and_category_filters(h: Harness) -> None:
    assert [i["id"] for i in search(h, tab="suppliers", q="flour")["items"]] == ["l-b"]
    other = "d0000000-0000-0000-0000-0000000000ff"
    assert search(h, tab="suppliers", category=other)["items"] == []
    assert search(h, tab="suppliers", category="not-a-uuid")["items"]  # ignored, not an error


def test_services_tab_includes_logistics_and_packaging(h: Harness) -> None:
    b = h.db.tables["vendors"][1]
    for sid, cat in (("s-log", "logistics"), ("s-pack", "packaging")):
        h.db.tables["services"].append(
            {"id": sid, "vendor_id": VENDOR_B, "category": cat, "status": "active", "title": cat,
             "description": None, "service_area": "Lusaka", "from_price_ngwee": None,
             "portfolio_images": [], "vendors": b}
        )  # fmt: skip
    ids = {i["id"] for i in search(h, tab="services")["items"]}
    assert {"s-log", "s-pack", "s-print"} <= ids and "s-beauty" not in ids
    assert [i["id"] for i in search(h, tab="services", category="logistics")["items"]] == ["s-log"]


def test_services_tab_only_business_verticals(h: Harness) -> None:
    items = search(h, tab="services")["items"]
    assert [i["id"] for i in items] == ["s-print"]
    assert items[0]["kind"] == "service" and items[0]["price_ngwee"] == 20000


def test_pagination(h: Harness) -> None:
    data = search(h, tab="suppliers", limit=1)
    assert len(data["items"]) == 1 and data["next_offset"] == 1
    assert (
        h.client.get("/vendor/sourcing/search", params={"limit": 99}, headers=AUTH).status_code
        == 422
    )


# --- supplier profile + made in zambia ----------------------------------------------
def test_profile_roundtrip_and_validation(h: Harness) -> None:
    r = h.client.put(
        "/vendor/sourcing/profile",
        json={"supplier_types": ["wholesaler", "wholesaler", "importer"]},
        headers=AUTH,
    )
    assert r.status_code == 200 and r.json()["supplier_types"] == ["wholesaler", "importer"]
    assert h.db.tables["vendors"][0]["supplier_types"] == ["wholesaler", "importer"]
    assert (
        h.client.put(
            "/vendor/sourcing/profile", json={"supplier_types": ["pirate"]}, headers=AUTH
        ).status_code
        == 422
    )
    assert (
        h.client.put(
            "/vendor/sourcing/profile", json={"supplier_types": [], "extra": 1}, headers=AUTH
        ).status_code
        == 422
    )


def _miz(h: Harness, lid: str, body: dict[str, Any]) -> Any:
    return h.client.put(f"/vendor/sourcing/listings/{lid}/made-in-zambia", json=body, headers=AUTH)


def test_made_in_zambia_claim_only_on_own_listing(h: Harness) -> None:
    assert _miz(h, "00000000-0000-0000-0000-000000000000", {"claim": True}).status_code == 404
    own = "e0000000-0000-0000-0000-000000000001"
    h.db.tables["vendor_listings"][0]["id"] = own
    r = _miz(h, own, {"claim": True, "reference": " ZABS-2026-114 "})
    assert r.status_code == 200
    assert r.json()["made_in_zambia_status"] == "claimed"  # a claim, never an approval
    assert r.json()["made_in_zambia_reference"] == "ZABS-2026-114"
    stored = h.db.tables["vendor_listings"][0]
    assert stored["made_in_zambia_status"] == "claimed" and stored["made_in_zambia_claimed_at"]
    assert "made_in_zambia_reviewed_by" not in stored  # reviewer fields are admin-only
    rival = "e0000000-0000-0000-0000-000000000002"
    h.db.tables["vendor_listings"][1]["id"] = rival
    assert _miz(h, rival, {"claim": True}).status_code == 404  # a rival's listing looks absent
    assert h.db.tables["vendor_listings"][1]["made_in_zambia_status"] is None
    withdrawn = _miz(h, own, {"claim": False})
    assert withdrawn.json()["made_in_zambia_status"] is None


def test_vendor_cannot_overwrite_an_approved_claim(h: Harness) -> None:
    own = "e0000000-0000-0000-0000-000000000001"
    row = h.db.tables["vendor_listings"][0]
    row.update(id=own, made_in_zambia_status="approved", made_in_zambia_reference="PACRA-1")
    r = _miz(h, own, {"claim": True, "reference": "PACRA-2"})
    assert r.status_code == 200 and r.json()["made_in_zambia_status"] == "approved"
    assert row["made_in_zambia_reference"] == "PACRA-1"


@pytest.mark.parametrize(
    "body",
    [
        {"made_in_zambia": True},
        {"claim": True, "status": "approved"},
        {"claim": True, "reference": "ab"},
        {"claim": "yes"},
    ],
)
def test_made_in_zambia_claim_validation(h: Harness, body: dict[str, Any]) -> None:
    own = "e0000000-0000-0000-0000-000000000001"
    h.db.tables["vendor_listings"][0]["id"] = own
    assert _miz(h, own, body).status_code == 422
    assert h.db.tables["vendor_listings"][0]["made_in_zambia_status"] is None


def test_writes_are_rate_limited(h: Harness) -> None:
    h.rate_allowed = False
    r = h.client.put("/vendor/sourcing/profile", json={"supplier_types": []}, headers=AUTH)
    assert r.status_code == 429
    r = h.client.post("/vendor/sourcing/import-requests", json=BODY, headers=AUTH)
    assert r.status_code == 429
    assert h.db.rows("import_requests") == []


# --- import requests -------------------------------------------------------------------
def test_create_and_list_own_import_requests_only(h: Harness) -> None:
    r = h.client.post("/vendor/sourcing/import-requests", json=BODY, headers=AUTH)
    assert r.status_code == 201
    assert r.json()["status"] == "submitted" and r.json()["target_unit_price_ngwee"] == 3500
    assert "write_standard" in h.rate_scopes  # registered scope, 1-day window
    h.as_role(USER_B, "vendor")
    assert h.client.get("/vendor/sourcing/import-requests", headers=AUTH).json() == []
    h.as_role(USER_A, "vendor")
    assert len(h.client.get("/vendor/sourcing/import-requests", headers=AUTH).json()) == 1
    stored = h.db.rows("import_requests")[0]
    assert stored["vendor_id"] == VENDOR_A and stored["requested_by"] == USER_A


@pytest.mark.parametrize(
    "patch",
    [
        {"reference_url": "http://insecure.example.com"},
        {"image_urls": ["javascript:alert(1)"]},
        {"image_urls": [f"https://e.com/{i}" for i in range(6)]},
        {"quantity": 0},
        {"quantity": 1.5},
        {"target_unit_price_ngwee": 10.5},
        {"target_unit_price_ngwee": -1},
        {"title": "ab"},
        {"unknown": 1},
    ],
)
def test_import_request_validation(h: Harness, patch: dict[str, Any]) -> None:
    r = h.client.post("/vendor/sourcing/import-requests", json={**BODY, **patch}, headers=AUTH)
    assert r.status_code == 422
    assert h.db.rows("import_requests") == []


def test_prohibited_item_is_refused(h: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    class Blocked:
        allowed = False

    monkeypatch.setattr(vendor_sourcing, "screen_listing", lambda **_k: Blocked())
    r = h.client.post("/vendor/sourcing/import-requests", json=BODY, headers=AUTH)
    assert r.status_code == 422 and h.db.rows("import_requests") == []


def test_cancel_only_own_request(h: Harness) -> None:
    rid = h.client.post("/vendor/sourcing/import-requests", json=BODY, headers=AUTH).json()["id"]
    h.as_role(USER_B, "vendor")
    assert (
        h.client.post(f"/vendor/sourcing/import-requests/{rid}/cancel", headers=AUTH).status_code
        == 404
    )
    h.as_role(USER_A, "vendor")
    r = h.client.post(f"/vendor/sourcing/import-requests/{rid}/cancel", headers=AUTH)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"


# --- admin queue ---------------------------------------------------------------------------
def _submit(h: Harness) -> str:
    return str(
        h.client.post("/vendor/sourcing/import-requests", json=BODY, headers=AUTH).json()["id"]
    )


@pytest.mark.parametrize("role", ["vendor", "customer"])
def test_admin_queue_is_admin_only(h: Harness, role: str) -> None:
    rid = _submit(h)
    h.as_role(USER_A, role)
    assert h.client.get("/admin/import-requests", headers=AUTH).status_code == 403
    assert (
        h.client.post(f"/admin/import-requests/{rid}/quotes", json=QUOTE, headers=AUTH).status_code
        == 403
    )
    assert h.db.rows("import_request_quotes") == []


def test_admin_sees_all_and_quotes_with_separate_ngwee_lines_and_audit(h: Harness) -> None:
    rid = _submit(h)
    h.as_role(USER_B, "vendor")
    _submit(h)
    h.as_role(ADMIN_ID, "admin")
    queue = h.client.get("/admin/import-requests", headers=AUTH).json()
    assert len(queue) == 2 and {q["vendor_id"] for q in queue} == {VENDOR_A, VENDOR_B}
    r = h.client.post(f"/admin/import-requests/{rid}/quotes", json=QUOTE, headers=AUTH)
    assert r.status_code == 201, r.text
    quote = r.json()["quote"]
    assert quote["total_ngwee"] == 1_000_000 and quote["is_estimate"] is True
    assert (quote["product_ngwee"], quote["freight_ngwee"], quote["duty_ngwee"],
            quote["clearing_ngwee"]) == (700000, 150000, 120000, 30000)  # fmt: skip
    assert r.json()["request"]["status"] == "quoted"
    audit = h.db.rows("audit_log")
    assert audit and audit[-1]["action"] == "import_request.quote"
    # the owning vendor sees the quote; the other vendor never does
    h.as_role(USER_A, "vendor")
    mine = h.client.get("/vendor/sourcing/import-requests", headers=AUTH).json()
    assert mine[0]["latest_quote"]["total_ngwee"] == 1_000_000
    h.as_role(USER_B, "vendor")
    theirs = h.client.get("/vendor/sourcing/import-requests", headers=AUTH).json()
    assert all(t["latest_quote"] is None for t in theirs)


@pytest.mark.parametrize(
    "patch",
    [{"freight_ngwee": -1}, {"duty_ngwee": 1.5}, {"product_ngwee": "100"}, {"lead_time_days": 0},
     {"is_estimate": False}, {"total_ngwee": 5}],
)  # fmt: skip
def test_quote_validation(h: Harness, patch: dict[str, Any]) -> None:
    rid = _submit(h)
    h.as_role(ADMIN_ID, "admin")
    r = h.client.post(f"/admin/import-requests/{rid}/quotes", json={**QUOTE, **patch}, headers=AUTH)
    assert r.status_code == 422 and h.db.rows("import_request_quotes") == []


def test_status_machine_and_terminal_states(h: Harness) -> None:
    rid = _submit(h)
    h.as_role(ADMIN_ID, "admin")
    ok = h.client.post(
        f"/admin/import-requests/{rid}/status", json={"to": "in_review"}, headers=AUTH
    )
    assert ok.status_code == 200 and ok.json()["status"] == "in_review"
    assert (
        h.client.post(
            f"/admin/import-requests/{rid}/status", json={"to": "in_review"}, headers=AUTH
        ).status_code
        == 409
    )
    closed = h.client.post(
        f"/admin/import-requests/{rid}/status", json={"to": "closed"}, headers=AUTH
    )
    assert closed.status_code == 200
    assert (
        h.client.post(f"/admin/import-requests/{rid}/quotes", json=QUOTE, headers=AUTH).status_code
        == 409
    )  # cannot quote a closed request
    assert (
        h.client.post(
            f"/admin/import-requests/{rid}/status", json={"to": "cancelled"}, headers=AUTH
        ).status_code
        == 422
    )
    assert (
        h.client.post(
            f"/admin/import-requests/{uuid4()}/status", json={"to": "closed"}, headers=AUTH
        ).status_code
        == 404
    )


def test_admin_writes_are_rate_limited(h: Harness) -> None:
    rid = _submit(h)
    h.as_role(ADMIN_ID, "admin")
    h.rate_allowed = False
    r = h.client.post(f"/admin/import-requests/{rid}/quotes", json=QUOTE, headers=AUTH)
    assert r.status_code == 429 and h.db.rows("import_request_quotes") == []


def test_no_money_tables_are_ever_touched(h: Harness) -> None:
    rid = _submit(h)
    h.as_role(ADMIN_ID, "admin")
    h.client.post(f"/admin/import-requests/{rid}/quotes", json=QUOTE, headers=AUTH)
    touched = {t for t, _ in h.db.calls}
    forbidden = {"orders", "payments", "ledger_transactions", "payouts", "refunds", "order_items"}
    assert not touched & forbidden


# --- import quote notifications ----------------------------------------------------------
def test_quote_notifies_vendor_in_app_and_email_only(h: Harness) -> None:
    rid = _submit(h)
    h.as_role(ADMIN_ID, "admin")
    r = h.client.post(f"/admin/import-requests/{rid}/quotes", json=QUOTE, headers=AUTH)
    assert r.status_code == 201
    qid = r.json()["quote"]["id"]
    (note,) = h.db.rows("in_app_notifications")
    assert note["recipient_user_id"] == USER_A and note["audience"] == "vendor"
    assert note["i18n_key"] == "notifications.inApp.vendor.import_quote_ready"
    assert note["dedupe_key"] == f"import_quote_ready:{qid}" and note["link_path"] == "/source"
    (mail,) = h.db.rows("notification_outbox")
    assert mail["channel"] == "email" and mail["template"] == "import_quote_ready"
    assert mail["payload"]["recipient_id"] == USER_A and mail["payload"]["total_ngwee"] == 1_000_000
    assert mail["status"] == "pending"
    # no WhatsApp / SMS rows are ever queued for this event
    assert {row["channel"] for row in h.db.rows("notification_outbox")} == {"email"}


def test_quote_succeeds_even_if_notification_fails(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("outbox down")

    monkeypatch.setattr(admin_import_requests, "enqueue_outbox_row", boom)
    rid = _submit(h)
    h.as_role(ADMIN_ID, "admin")
    assert (
        h.client.post(f"/admin/import-requests/{rid}/quotes", json=QUOTE, headers=AUTH).status_code
        == 201
    )


def test_import_quote_email_template_renders() -> None:
    from app.services.notifications.adapters.email import render_email_html
    from app.services.notifications.dispatcher import TEMPLATE_CLASSIFICATION, TemplateClass

    subject, html_body, subject_key, _ = render_email_html(
        "import_quote_ready",
        payload={"title": "LED <b>strips</b>", "total_ngwee": 1_000_000},
    )
    assert subject_key == "notifications.email.import_quote_ready.subject"
    assert "K10000.00" in html_body or "K10,000.00" in html_body
    assert "<b>strips" not in html_body  # html-escaped
    assert TEMPLATE_CLASSIFICATION["import_quote_ready"] is TemplateClass.TRANSACTIONAL


# --- admin Made in Zambia claim queue -------------------------------------------------------
def _claimed(h: Harness) -> str:
    lid = "e0000000-0000-0000-0000-0000000000c1"
    h.db.tables["vendor_listings"][0].update(
        id=lid, made_in_zambia_status="claimed", made_in_zambia_reference="ZABS-9",
        made_in_zambia_claimed_at="2026-11-26T08:00:00+00:00",
    )  # fmt: skip
    return lid


@pytest.mark.parametrize("role", ["vendor", "customer"])
def test_claims_queue_is_admin_only(h: Harness, role: str) -> None:
    lid = _claimed(h)
    h.as_role(USER_A, role)
    assert h.client.get("/admin/made-in-zambia-claims", headers=AUTH).status_code == 403
    r = h.client.post(
        f"/admin/made-in-zambia-claims/{lid}/decision", json={"decision": "approve"}, headers=AUTH
    )
    assert r.status_code == 403
    assert h.db.tables["vendor_listings"][0]["made_in_zambia_status"] == "claimed"


def test_admin_approves_claim_with_reviewer_timestamp_and_audit(h: Harness) -> None:
    lid = _claimed(h)
    h.as_role(ADMIN_ID, "admin")
    queue = h.client.get("/admin/made-in-zambia-claims", headers=AUTH).json()
    mine = [c for c in queue if c["listing_id"] == lid]
    assert [(c["reference"], c["vendor_name"]) for c in mine] == [("ZABS-9", "Alpha")]
    assert {c["status"] for c in queue} == {"claimed"}
    r = h.client.post(
        f"/admin/made-in-zambia-claims/{lid}/decision",
        json={"decision": "approve", "note": "Checked certificate"},
        headers=AUTH,
    )
    assert r.status_code == 200 and r.json()["status"] == "approved"
    row = h.db.tables["vendor_listings"][0]
    assert row["made_in_zambia_reviewed_by"] == ADMIN_ID and row["made_in_zambia_reviewed_at"]
    assert h.db.rows("audit_log")[-1]["action"] == "made_in_zambia.approved"
    left = h.client.get("/admin/made-in-zambia-claims", headers=AUTH).json()
    assert lid not in {c["listing_id"] for c in left}
    # an approved claim can be revoked, but not approved twice
    again = h.client.post(
        f"/admin/made-in-zambia-claims/{lid}/decision", json={"decision": "approve"}, headers=AUTH
    )
    assert again.status_code == 409
    revoked = h.client.post(
        f"/admin/made-in-zambia-claims/{lid}/decision", json={"decision": "reject"}, headers=AUTH
    )
    assert revoked.status_code == 200 and revoked.json()["status"] == "rejected"


def test_claim_decision_validation_and_missing(h: Harness) -> None:
    lid = _claimed(h)
    h.as_role(ADMIN_ID, "admin")
    path = f"/admin/made-in-zambia-claims/{lid}/decision"
    assert h.client.post(path, json={"decision": "maybe"}, headers=AUTH).status_code == 422
    assert (
        h.client.post(path, json={"decision": "approve", "x": 1}, headers=AUTH).status_code == 422
    )
    missing = f"/admin/made-in-zambia-claims/{uuid4()}/decision"
    assert h.client.post(missing, json={"decision": "approve"}, headers=AUTH).status_code == 404
    h.rate_allowed = False
    assert h.client.post(path, json={"decision": "reject"}, headers=AUTH).status_code == 429
    assert h.db.tables["vendor_listings"][0]["made_in_zambia_status"] == "claimed"


def test_migration_guards_self_approval_and_is_reversible() -> None:
    from pathlib import Path

    sql = next(
        p for p in Path(__file__).parents[3].glob("supabase/migrations/*_vendor_sourcing_hub.sql")
    ).read_text()
    assert "vendor_listings_made_in_zambia_guard" in sql
    assert "made_in_zambia approval is admin-only" in sql  # owners hold an UPDATE policy
    assert "made_in_zambia_status in ('claimed', 'approved', 'rejected')" in sql
    assert "drop column made_in_zambia_status" in sql  # documented reversal
    assert "logistics" not in sql  # service categories are free text: no DB seed needed
