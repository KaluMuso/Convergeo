"""Service packages — vendor CRUD, public detail, RFQ prefill, admin oversight.

Design: docs/plan/service-packages.md. The claims defended here:

* money is an integer number of ngwee end to end (floats, strings and bools refused);
* only the owning vendor can create/update/archive, and a non-owner sees a 404;
* status moves only through the guarded transition, which writes an audit row;
* the public detail shows active packages only, tier-ordered;
* a package-carrying RFQ stores an immutable snapshot, and refuses a foreign,
  archived, or service-less package;
* nothing here touches orders, payments or the booking spine (SP-1).
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.main import create_app
from app.services.service_packages import state
from fastapi.testclient import TestClient

CUSTOMER = "11111111-1111-4111-8111-111111111111"
VENDOR_OWNER = "33333333-3333-4333-8333-333333333333"
OTHER_OWNER = "44444444-4444-4444-8444-444444444444"
VENDOR_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OTHER_VENDOR = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
SERVICE_ID = "20202020-2020-4020-8020-202020202020"
PRICED_SERVICE = "21212121-2121-4121-8121-212121212121"
OTHER_SERVICE = "22222222-2222-4222-8222-222222222222"
ADMIN = "aaaa0000-0000-4000-8000-00000000000a"

REPO_ROOT = Path(__file__).resolve().parents[3]


# --- Fake Supabase ----------------------------------------------------------
class FakeQuery:
    def __init__(self, parent: FakeTable) -> None:
        self._parent = parent
        self._eq: list[tuple[str, Any]] = []
        self._neq: list[tuple[str, Any]] = []
        self._in: list[tuple[str, set[str]]] = []
        self._maybe_single = False
        self._limit: int | None = None
        self._range: tuple[int, int] | None = None
        self._op: str | None = None
        self._payload: dict[str, Any] | None = None

    def select(self, *_a: Any, **_k: Any) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        # PostgREST embed filters ("vendors.status") are modelled by the seed.
        if "." not in column:
            self._eq.append((column, value))
        return self

    def neq(self, column: str, value: Any) -> FakeQuery:
        self._neq.append((column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._in.append((column, {str(v) for v in values}))
        return self

    def order(self, *_a: Any, **_k: Any) -> FakeQuery:
        return self

    def limit(self, count: int) -> FakeQuery:
        self._limit = count
        return self

    def range(self, start: int, end: int) -> FakeQuery:
        self._range = (start, end)
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        self._op, self._payload = "insert", payload
        return self

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self._op, self._payload = "update", payload
        return self

    def _match(self, row: dict[str, Any]) -> bool:
        if not all(row.get(c) == v for c, v in self._eq):
            return False
        if any(row.get(c) == v for c, v in self._neq):
            return False
        return all(str(row.get(c)) in vs for c, vs in self._in)

    def execute(self) -> MagicMock:
        table = self._parent
        if self._op == "insert":
            assert self._payload is not None
            row = dict(self._payload)
            if table.name == "service_packages":
                # Mirror the UNIQUE (service_id, tier) constraint.
                for existing in table.rows:
                    if (existing["service_id"], existing["tier"]) == (
                        row["service_id"],
                        row["tier"],
                    ):
                        raise RuntimeError("duplicate key value violates unique constraint")
                row.setdefault("id", str(uuid.uuid4()))
            table.rows.append(row)
            return MagicMock(data=[dict(row)])
        matched = [r for r in table.rows if self._match(r)]
        if self._op == "update":
            assert self._payload is not None
            for row in matched:
                row.update(self._payload)
            return MagicMock(data=[dict(r) for r in matched])
        rows = [dict(r) for r in matched]
        if self._range is not None:
            rows = rows[self._range[0] : self._range[1] + 1]
        elif self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=rows)


class FakeTable:
    def __init__(self, name: str) -> None:
        self.name = name
        self.rows: list[dict[str, Any]] = []

    def select(self, *a: Any, **k: Any) -> FakeQuery:
        return FakeQuery(self).select(*a, **k)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).insert(payload)

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).update(payload)


class FakeClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {}

    def table(self, name: str) -> FakeTable:
        return self.tables.setdefault(name, FakeTable(name))

    def rows(self, name: str) -> list[dict[str, Any]]:
        return self.table(name).rows

    def rpc(self, name: str, params: dict[str, Any]) -> MagicMock:
        if name == "bump_rate_counter":
            return MagicMock(
                execute=lambda: MagicMock(data=[{"allowed": True, "retry_after_seconds": 0}])
            )
        return MagicMock(execute=lambda: MagicMock(data=[]))


def _service(service_id: str, vendor_id: str, *, from_price: int | None = None) -> dict[str, Any]:
    vendor_row = {
        "id": vendor_id,
        "slug": "shop",
        "display_name": "Shop",
        "preferred_badge": False,
        "status": "active",
    }
    return {
        "id": service_id,
        "vendor_id": vendor_id,
        "category": "printing-creative",
        "title": "Logo design",
        "description": "Brand marks for small shops",
        "service_area": "Lusaka",
        "from_price_ngwee": from_price,
        "bookable": False,
        "booking_price_ngwee": None,
        "portfolio_images": [],
        "includes": [],
        "status": "active",
        "vendors": vendor_row,
    }


@pytest.fixture
def db() -> FakeClient:
    client = FakeClient()
    client.rows("vendors").extend(
        [
            {"id": VENDOR_ID, "owner_user_id": VENDOR_OWNER, "status": "active"},
            {"id": OTHER_VENDOR, "owner_user_id": OTHER_OWNER, "status": "active"},
        ]
    )
    client.rows("services").extend(
        [
            _service(SERVICE_ID, VENDOR_ID),
            _service(PRICED_SERVICE, VENDOR_ID, from_price=50_000),
            _service(OTHER_SERVICE, OTHER_VENDOR),
        ]
    )
    for name in ("service_packages", "rfq_threads", "rfq_messages", "audit_log", "job_quotes"):
        client.table(name)
    return client


def _app(db: FakeClient, user_id: str, role: str, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr("app.routers.rfq.bump_rate_counter", lambda **kwargs: (True, 0))
    monkeypatch.setattr("app.routers.rfq.enqueue_outbox_row", lambda *a, **k: None)
    monkeypatch.setattr(
        "app.routers.service_packages.bump_rate_counter", lambda **kwargs: (True, 0)
    )
    app = create_app()

    async def _user() -> CurrentUser:
        return CurrentUser(id=user_id, roles=frozenset({role}), token="t")

    class _Svc:
        @property
        def client(self) -> FakeClient:
            return db

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_supabase_client] = lambda: _Svc()
    return TestClient(app)


@pytest.fixture
def vendor(db: FakeClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    return _app(db, VENDOR_OWNER, "vendor", monkeypatch)


@pytest.fixture
def customer(db: FakeClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    return _app(db, CUSTOMER, "customer", monkeypatch)


def _pkg(**over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": "Starter logo",
        "description": "One concept, PNG + PDF",
        "price_ngwee": 75_000,
        "delivery_days": 3,
        "revisions": 1,
        "includes": ["1 concept", "PNG + PDF files"],
    }
    body.update(over)
    return body


def _put(client: TestClient, tier: str, service_id: str = SERVICE_ID, **over: Any) -> Any:
    return client.put(f"/vendor/services/{service_id}/packages/{tier}", json=_pkg(**over))


# --- Vendor CRUD + validation ------------------------------------------------
def test_vendor_creates_and_lists_packages_in_tier_order(vendor: TestClient) -> None:
    assert _put(vendor, "premium", name="Full brand", price_ngwee=None).status_code == 200
    created = _put(vendor, "basic")
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["tier"] == "basic" and body["status"] == "active"
    assert body["price_ngwee"] == 75_000 and isinstance(body["price_ngwee"], int)

    listed = vendor.get(f"/vendor/services/{SERVICE_ID}/packages").json()
    assert [p["tier"] for p in listed["items"]] == ["basic", "premium"]
    assert listed["items"][1]["price_ngwee"] is None  # request-a-quote package


def test_saving_a_tier_twice_updates_it_and_never_creates_a_fourth(
    vendor: TestClient, db: FakeClient
) -> None:
    for tier in ("basic", "standard", "premium"):
        assert _put(vendor, tier).status_code == 200
    assert _put(vendor, "standard", name="Standard logo", price_ngwee=120_000).status_code == 200
    rows = db.rows("service_packages")
    assert len(rows) == 3
    assert next(r for r in rows if r["tier"] == "standard")["price_ngwee"] == 120_000


def test_an_unknown_tier_is_refused(vendor: TestClient) -> None:
    assert _put(vendor, "deluxe").status_code == 422


@pytest.mark.parametrize(
    "override",
    [
        {"price_ngwee": 750.5},
        {"price_ngwee": "75000"},
        {"price_ngwee": True},
        {"price_ngwee": 0},
        {"price_ngwee": -100},
        {"delivery_days": 0},
        {"delivery_days": 91},
        {"delivery_days": "3"},
        {"revisions": 11},
        {"name": "x"},
        {"name": "n" * 41},
        {"description": "d" * 301},
        {"includes": ["ok"] * 9},
        {"includes": ["   "]},
        {"includes": ["i" * 121]},
        {"unexpected": "field"},
    ],
)
def test_invalid_packages_are_refused(vendor: TestClient, db: FakeClient, override: Any) -> None:
    response = _put(vendor, "basic", **override)
    assert response.status_code == 422, override
    assert db.rows("service_packages") == []


def test_a_prohibited_package_is_refused(
    vendor: TestClient, db: FakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services.moderation import prohibited

    verdict = prohibited.screen_listing(title="x", description="x", category="x")
    blocked = type(verdict)(allowed=False, reason="keyword", matched="blocked")
    monkeypatch.setattr("app.routers.service_packages.screen_listing", lambda **kwargs: blocked)
    response = _put(vendor, "basic")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "prohibited_listing"
    assert db.rows("service_packages") == []


def test_a_non_owner_gets_404_and_writes_nothing(
    db: FakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = _app(db, OTHER_OWNER, "vendor", monkeypatch)
    assert _put(other, "basic").status_code == 404
    assert other.get(f"/vendor/services/{SERVICE_ID}/packages").status_code == 404
    assert other.post(f"/vendor/services/{SERVICE_ID}/packages/basic/archive").status_code == 404
    assert db.rows("service_packages") == []


def test_a_malformed_service_id_is_404(vendor: TestClient) -> None:
    assert _put(vendor, "basic", service_id="not-a-uuid").status_code == 404


def test_a_customer_cannot_manage_packages(customer: TestClient) -> None:
    assert _put(customer, "basic").status_code == 403


# --- Guarded transitions -----------------------------------------------------
def test_archive_is_guarded_audited_and_idempotent(vendor: TestClient, db: FakeClient) -> None:
    _put(vendor, "basic")
    first = vendor.post(f"/vendor/services/{SERVICE_ID}/packages/basic/archive")
    second = vendor.post(f"/vendor/services/{SERVICE_ID}/packages/basic/archive")
    assert first.status_code == 200 and first.json()["status"] == "archived"
    assert second.status_code == 200
    audit = [r for r in db.rows("audit_log") if r["action"] == "service_package.transition"]
    assert len(audit) == 1
    assert audit[0]["before"] == {"status": "active"}
    assert audit[0]["after"]["status"] == "archived"
    assert audit[0]["actor"] == VENDOR_OWNER


def test_saving_an_archived_tier_reactivates_it_through_the_guard(
    vendor: TestClient, db: FakeClient
) -> None:
    _put(vendor, "basic")
    vendor.post(f"/vendor/services/{SERVICE_ID}/packages/basic/archive")
    revived = _put(vendor, "basic", name="Starter logo v2")
    assert revived.json()["status"] == "active"
    actions = [r["after"]["status"] for r in db.rows("audit_log")]
    assert actions == ["archived", "active"]


def test_archiving_a_missing_tier_is_404(vendor: TestClient) -> None:
    assert vendor.post(f"/vendor/services/{SERVICE_ID}/packages/premium/archive").status_code == 404


def test_the_transition_table_is_closed() -> None:
    assert state.ALLOWED_TRANSITIONS == {("active", "archived"), ("archived", "active")}
    with pytest.raises(Exception) as excinfo:
        state.transition_status(
            MagicMock(),
            package={"id": "p", "status": "deleted"},
            to_status="active",
            actor_id=VENDOR_OWNER,
            reason="test",
        )
    assert getattr(excinfo.value, "code", None) == "invalid_transition"


def test_the_router_never_writes_status_directly() -> None:
    source = (REPO_ROOT / "services/api/app/routers/service_packages.py").read_text()
    assert '"status": state.ARCHIVED' not in source
    assert '.update({"status"' not in source


# --- Public detail -----------------------------------------------------------
def test_public_detail_lists_active_packages_only(vendor: TestClient, customer: TestClient) -> None:
    _put(vendor, "premium", name="Full brand", price_ngwee=None)
    _put(vendor, "basic")
    _put(vendor, "standard", name="Logo + card")
    vendor.post(f"/vendor/services/{SERVICE_ID}/packages/standard/archive")

    detail = customer.get(f"/services/{SERVICE_ID}")
    assert detail.status_code == 200, detail.text
    packages = detail.json()["packages"]
    assert [p["tier"] for p in packages] == ["basic", "premium"]
    assert "status" not in packages[0]  # public shape carries no lifecycle state
    assert packages[0]["price_ngwee"] == 75_000


def test_a_service_without_packages_is_unchanged(customer: TestClient) -> None:
    assert customer.get(f"/services/{SERVICE_ID}").json()["packages"] == []


# --- RFQ prefill ------------------------------------------------------------
def test_requesting_a_package_stores_an_immutable_snapshot(
    vendor: TestClient, customer: TestClient, db: FakeClient
) -> None:
    pkg = _put(vendor, "standard", name="Logo + card", price_ngwee=150_000).json()
    response = customer.post(
        "/rfq",
        json={
            "service_id": SERVICE_ID,
            "package_id": pkg["id"],
            "requested_details": "Package: Logo + card. For my bakery in Kabulonga.",
        },
    )
    assert response.status_code == 200, response.text
    thread = response.json()["thread"]
    assert thread["package_id"] == pkg["id"]
    snap = thread["package_snapshot"]
    assert snap["tier"] == "standard" and snap["price_ngwee"] == 150_000
    assert isinstance(snap["price_ngwee"], int)
    assert snap["delivery_days"] == 3 and snap["includes"] == ["1 concept", "PNG + PDF files"]

    # The vendor later changes the price; the thread keeps what the customer saw.
    _put(vendor, "standard", name="Logo + card", price_ngwee=999_000)
    stored = db.rows("rfq_threads")[0]["package_snapshot"]
    assert stored["price_ngwee"] == 150_000
    # No order, payment or job was created (SP-1).
    assert "orders" not in db.tables and "payments" not in db.tables
    assert db.rows("job_quotes") == []


def test_a_package_on_a_fixed_price_service_can_still_be_quoted(
    vendor: TestClient, customer: TestClient
) -> None:
    pkg = _put(vendor, "basic", service_id=PRICED_SERVICE).json()
    plain = customer.post("/rfq", json={"service_id": PRICED_SERVICE, "requested_details": "hi"})
    with_pkg = customer.post(
        "/rfq",
        json={"service_id": PRICED_SERVICE, "package_id": pkg["id"], "requested_details": "hi"},
    )
    assert plain.status_code == 404  # unchanged behaviour without a package
    assert with_pkg.status_code == 200, with_pkg.text


def test_reusing_a_thread_moves_it_to_the_latest_package(
    vendor: TestClient, customer: TestClient, db: FakeClient
) -> None:
    basic = _put(vendor, "basic").json()
    premium = _put(vendor, "premium", name="Full brand", price_ngwee=None).json()
    customer.post(
        "/rfq",
        json={"service_id": SERVICE_ID, "package_id": basic["id"], "requested_details": "a"},
    )
    second = customer.post(
        "/rfq",
        json={"service_id": SERVICE_ID, "package_id": premium["id"], "requested_details": "b"},
    )
    assert second.json()["reused_existing_thread"] is True
    assert len(db.rows("rfq_threads")) == 1
    assert db.rows("rfq_threads")[0]["package_id"] == premium["id"]
    assert db.rows("rfq_threads")[0]["package_snapshot"]["price_ngwee"] is None


@pytest.mark.parametrize("case", ["archived", "foreign", "garbage", "no_service"])
def test_an_unavailable_package_is_refused(
    vendor: TestClient,
    customer: TestClient,
    db: FakeClient,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    pkg = _put(vendor, "basic").json()
    payload: dict[str, Any] = {"service_id": SERVICE_ID, "requested_details": "hi"}
    if case == "archived":
        vendor.post(f"/vendor/services/{SERVICE_ID}/packages/basic/archive")
        payload["package_id"] = pkg["id"]
    elif case == "foreign":
        other = _app(db, OTHER_OWNER, "vendor", monkeypatch)
        foreign = _put(other, "basic", service_id=OTHER_SERVICE).json()
        payload["package_id"] = foreign["id"]
    elif case == "garbage":
        payload["package_id"] = "not-a-uuid"
    else:
        payload = {
            "listing_id": "10101010-1010-4010-8010-101010101010",
            "package_id": pkg["id"],
            "requested_details": "hi",
        }
        db.rows("vendor_listings").append(
            {
                "id": payload["listing_id"],
                "vendor_id": VENDOR_ID,
                "status": "active",
                "wholesale": False,
                "product_class": "E",
            }
        )
    response = customer.post("/rfq", json=payload)
    assert response.status_code in (409, 422), (case, response.text)
    assert db.rows("rfq_threads") == []


# --- Admin --------------------------------------------------------------------
def test_admin_services_list_shows_packages(
    vendor: TestClient, db: FakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _put(vendor, "premium", name="Full brand", price_ngwee=None)
    _put(vendor, "basic")
    admin = _app(db, ADMIN, "admin", monkeypatch)
    items = admin.get("/admin/services").json()["items"]
    mine = next(item for item in items if item["id"] == SERVICE_ID)
    assert [p["tier"] for p in mine["packages"]] == ["basic", "premium"]
    assert mine["packages"][0]["price_ngwee"] == 75_000
    other = next(item for item in items if item["id"] == OTHER_SERVICE)
    assert other["packages"] == []


def test_package_write_routes_have_rate_limit_policies() -> None:
    from app.core import ratelimit_policies as rp

    assert "PUT /vendor/services/{service_id}/packages/{tier}" in rp.POLICIES
    assert "POST /vendor/services/{service_id}/packages/{tier}/archive" in rp.POLICIES


# --- Migration pins -----------------------------------------------------------
def test_the_migration_is_additive_with_rls_and_no_client_writes() -> None:
    sql = (REPO_ROOT / "supabase/migrations/20261113045000_service_packages.sql").read_text()
    lowered = sql.lower()
    assert "force row level security" in lowered
    assert "unique (service_id, tier)" in lowered
    assert "price_ngwee bigint" in lowered
    assert "grant select on table public.service_packages to anon, authenticated;" in lowered
    for verb in ("insert", "update", "delete"):
        assert f"grant {verb}" not in lowered.replace("service_role", "")
    assert "drop table public.services" not in lowered
    assert "down (reversible)" in lowered
