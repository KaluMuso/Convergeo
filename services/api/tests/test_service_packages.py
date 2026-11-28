"""Service packages — vendor CRUD, public detail, RFQ prefill, admin oversight.

Design: docs/plan/service-packages.md. The claims defended here:

* money is an integer number of ngwee end to end (floats, strings and bools refused);
* only the owning vendor can create/update/archive, and a non-owner sees a 404;
* status moves only through the guarded transition, which writes an audit row;
* the public detail shows active packages only, in the vendor's order;
* a service holds an open list of at most 10 active packages (`package_limit_reached`);
* rows from the old fixed-tier era (tier label, no sort_order) still read and sort;
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

    def delete(self) -> FakeQuery:
        self._op = "delete"
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
                row.setdefault("id", str(uuid.uuid4()))
            table.rows.append(row)
            return MagicMock(data=[dict(row)])
        matched = [r for r in table.rows if self._match(r)]
        if self._op == "delete":
            table.rows[:] = [r for r in table.rows if not self._match(r)]
            return MagicMock(data=[dict(r) for r in matched])
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

    def delete(self) -> FakeQuery:
        return FakeQuery(self).delete()


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


def _put(client: TestClient, _label: str, service_id: str = SERVICE_ID, **over: Any) -> Any:
    """Create one package (the label only documents the intent at the call site)."""
    return client.post(f"/vendor/services/{service_id}/packages", json=_pkg(**over))


def _update(client: TestClient, package_id: str, service_id: str = SERVICE_ID, **over: Any) -> Any:
    return client.put(f"/vendor/services/{service_id}/packages/{package_id}", json=_pkg(**over))


def _archive(client: TestClient, package_id: str, service_id: str = SERVICE_ID) -> Any:
    return client.post(f"/vendor/services/{service_id}/packages/{package_id}/archive")


def _ids(client: TestClient, service_id: str = SERVICE_ID) -> list[str]:
    items = client.get(f"/vendor/services/{service_id}/packages").json()["items"]
    return [item["id"] for item in items]


# --- Vendor CRUD + validation ------------------------------------------------
def test_vendor_creates_and_lists_packages_in_the_order_added(vendor: TestClient) -> None:
    first = _put(vendor, "a", name="Full brand", price_ngwee=None)
    assert first.status_code == 200, first.text
    created = _put(vendor, "b")
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["tier"] is None and body["status"] == "active" and body["sort_order"] == 1
    assert body["price_ngwee"] == 75_000 and isinstance(body["price_ngwee"], int)

    listed = vendor.get(f"/vendor/services/{SERVICE_ID}/packages").json()
    assert [p["name"] for p in listed["items"]] == ["Full brand", "Starter logo"]
    assert listed["max_packages"] == 10
    assert listed["items"][0]["price_ngwee"] is None  # request-a-quote package


def test_packages_are_not_limited_to_three_and_names_may_repeat(
    vendor: TestClient, db: FakeClient
) -> None:
    for index in range(6):
        assert _put(vendor, "x", name=f"Option {index}").status_code == 200
    assert _put(vendor, "x", name="Option 0").status_code == 200  # same name is fine
    assert len(db.rows("service_packages")) == 7


def test_the_eleventh_active_package_is_refused_with_a_stable_code(
    vendor: TestClient, db: FakeClient
) -> None:
    for index in range(10):
        assert _put(vendor, "x", name=f"Option {index}").status_code == 200
    over = _put(vendor, "x", name="One too many")
    assert over.status_code == 409
    error = over.json()["error"]
    assert error["code"] == "package_limit_reached"
    assert error["details"]["max"] == 10
    assert error["details"]["message_key"] == "services.vendor.packages.errors.limitReached"
    assert len(db.rows("service_packages")) == 10


def test_the_cap_is_per_service_and_archived_packages_do_not_count(
    vendor: TestClient, db: FakeClient
) -> None:
    for index in range(10):
        _put(vendor, "x", name=f"Option {index}")
    assert _put(vendor, "x", service_id=PRICED_SERVICE).status_code == 200  # other service
    first_id = _ids(vendor)[0]
    assert _archive(vendor, first_id).status_code == 200
    assert _put(vendor, "x", name="Replacement").status_code == 200  # slot freed
    # ...and bringing the archived one back now would be the 11th.
    revive = _update(vendor, first_id, name="Back again")
    assert revive.status_code == 409 and revive.json()["error"]["code"] == "package_limit_reached"
    assert next(r for r in db.rows("service_packages") if r["id"] == first_id)["status"] == (
        "archived"
    )


def test_updating_a_package_changes_it_in_place(vendor: TestClient, db: FakeClient) -> None:
    for name in ("One", "Two", "Three"):
        _put(vendor, "x", name=name)
    target = _ids(vendor)[1]
    assert _update(vendor, target, name="Two plus", price_ngwee=120_000).status_code == 200
    rows = db.rows("service_packages")
    assert len(rows) == 3
    assert next(r for r in rows if r["id"] == target)["price_ngwee"] == 120_000
    assert next(r for r in rows if r["id"] == target)["name"] == "Two plus"


def test_updating_a_missing_or_malformed_package_is_404(vendor: TestClient) -> None:
    assert _update(vendor, str(uuid.uuid4())).status_code == 404
    assert _update(vendor, "not-a-uuid").status_code == 404


def test_reordering_sets_the_order_the_customer_sees(
    vendor: TestClient, customer: TestClient
) -> None:
    for name in ("One", "Two", "Three"):
        _put(vendor, "x", name=name)
    one, two, three = _ids(vendor)
    response = vendor.post(
        f"/vendor/services/{SERVICE_ID}/packages/reorder", json={"ids": [three, one, two]}
    )
    assert response.status_code == 200, response.text
    assert [p["name"] for p in response.json()["items"]] == ["Three", "One", "Two"]
    public = customer.get(f"/services/{SERVICE_ID}").json()["packages"]
    assert [p["name"] for p in public] == ["Three", "One", "Two"]


@pytest.mark.parametrize("case", ["missing", "extra", "duplicate", "empty"])
def test_a_bad_reorder_is_refused_and_changes_nothing(
    vendor: TestClient, db: FakeClient, case: str
) -> None:
    for name in ("One", "Two"):
        _put(vendor, "x", name=name)
    one, two = _ids(vendor)
    ids = {
        "missing": [one],
        "extra": [one, two, str(uuid.uuid4())],
        "duplicate": [one, one],
        "empty": [],
    }[case]
    response = vendor.post(f"/vendor/services/{SERVICE_ID}/packages/reorder", json={"ids": ids})
    assert response.status_code in (409, 422), response.text
    assert _ids(vendor) == [one, two]


def test_deleting_a_package_removes_it_and_writes_an_audit_row(
    vendor: TestClient, db: FakeClient
) -> None:
    _put(vendor, "x", name="Keep")
    _put(vendor, "x", name="Drop")
    keep, drop = _ids(vendor)
    response = vendor.delete(f"/vendor/services/{SERVICE_ID}/packages/{drop}")
    assert response.status_code == 204
    assert _ids(vendor) == [keep]
    audit = [r for r in db.rows("audit_log") if r["action"] == "service_package.deleted"]
    assert len(audit) == 1 and audit[0]["entity_id"] == drop and audit[0]["actor"] == VENDOR_OWNER
    assert vendor.delete(f"/vendor/services/{SERVICE_ID}/packages/{drop}").status_code == 404


def test_a_package_from_the_old_tier_era_still_works_end_to_end(
    vendor: TestClient, customer: TestClient, db: FakeClient
) -> None:
    """Pre-migration rows: tier label set, backfilled sort_order 0/1/2, vendor-chosen name."""
    legacy = [
        ("premium", 2, "Full brand", None),
        ("basic", 0, "Starter logo", 75_000),
        ("standard", 1, "Logo + card", 150_000),
    ]
    ids: dict[str, str] = {}
    for tier, order, name, price in legacy:
        row = {
            "id": str(uuid.uuid4()),
            "service_id": SERVICE_ID,
            "vendor_id": VENDOR_ID,
            "tier": tier,
            "sort_order": order,
            "name": name,
            "description": None,
            "price_ngwee": price,
            "delivery_days": 3,
            "revisions": None,
            "includes": [],
            "status": "active",
        }
        db.rows("service_packages").append(row)
        ids[tier] = str(row["id"])

    listed = vendor.get(f"/vendor/services/{SERVICE_ID}/packages").json()["items"]
    assert [p["tier"] for p in listed] == ["basic", "standard", "premium"]
    public = customer.get(f"/services/{SERVICE_ID}").json()["packages"]
    assert [p["name"] for p in public] == ["Starter logo", "Logo + card", "Full brand"]

    # The vendor can edit a legacy row (its tier label is preserved) and append a new one.
    assert (
        _update(vendor, ids["standard"], name="Logo + card", price_ngwee=160_000).status_code == 200
    )
    assert next(r for r in db.rows("service_packages") if r["id"] == ids["standard"])["tier"] == (
        "standard"
    )
    assert _put(vendor, "x", name="Brand audit").json()["sort_order"] == 3

    # A legacy package still carries its price into an RFQ snapshot.
    response = customer.post(
        "/rfq",
        json={"service_id": SERVICE_ID, "package_id": ids["basic"], "requested_details": "hi"},
    )
    assert response.status_code == 200, response.text
    snap = response.json()["thread"]["package_snapshot"]
    assert snap["tier"] == "basic" and snap["price_ngwee"] == 75_000


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


def test_a_tier_field_is_not_accepted_from_clients(vendor: TestClient, db: FakeClient) -> None:
    assert _put(vendor, "basic", tier="basic").status_code == 422
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
    assert (
        other.post(
            f"/vendor/services/{SERVICE_ID}/packages/reorder", json={"ids": [str(uuid.uuid4())]}
        ).status_code
        == 404
    )
    assert db.rows("service_packages") == []


def test_a_malformed_service_id_is_404(vendor: TestClient) -> None:
    assert _put(vendor, "basic", service_id="not-a-uuid").status_code == 404


def test_a_customer_cannot_manage_packages(customer: TestClient) -> None:
    assert _put(customer, "basic").status_code == 403


def test_a_vendor_cannot_touch_another_vendors_package(
    vendor: TestClient, db: FakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = _app(db, OTHER_OWNER, "vendor", monkeypatch)
    theirs = _put(other, "x", service_id=OTHER_SERVICE).json()["id"]
    # Own service id + their package id: not found (the package is scoped to the service).
    assert _update(vendor, theirs).status_code == 404
    assert vendor.delete(f"/vendor/services/{SERVICE_ID}/packages/{theirs}").status_code == 404
    assert _archive(vendor, theirs).status_code == 404
    # Their service id: not found (ownership).
    assert _update(vendor, theirs, service_id=OTHER_SERVICE).status_code == 404
    assert len(db.rows("service_packages")) == 1


# --- Guarded transitions -----------------------------------------------------
def test_archive_is_guarded_audited_and_idempotent(vendor: TestClient, db: FakeClient) -> None:
    pid = _put(vendor, "basic").json()["id"]
    first = _archive(vendor, pid)
    second = _archive(vendor, pid)
    assert first.status_code == 200 and first.json()["status"] == "archived"
    assert second.status_code == 200
    audit = [r for r in db.rows("audit_log") if r["action"] == "service_package.transition"]
    assert len(audit) == 1
    assert audit[0]["before"] == {"status": "active"}
    assert audit[0]["after"]["status"] == "archived"
    assert audit[0]["actor"] == VENDOR_OWNER


def test_saving_an_archived_package_reactivates_it_through_the_guard(
    vendor: TestClient, db: FakeClient
) -> None:
    pid = _put(vendor, "basic").json()["id"]
    _archive(vendor, pid)
    revived = _update(vendor, pid, name="Starter logo v2")
    assert revived.json()["status"] == "active"
    actions = [r["after"]["status"] for r in db.rows("audit_log")]
    assert actions == ["archived", "active"]


def test_archiving_a_missing_package_is_404(vendor: TestClient) -> None:
    assert _archive(vendor, str(uuid.uuid4())).status_code == 404


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
    assert "sort_by_tier" not in source


# --- Public detail -----------------------------------------------------------
def test_public_detail_lists_active_packages_only(vendor: TestClient, customer: TestClient) -> None:
    _put(vendor, "premium", name="Full brand", price_ngwee=None)
    _put(vendor, "basic")
    hidden = _put(vendor, "standard", name="Logo + card").json()["id"]
    _archive(vendor, hidden)

    detail = customer.get(f"/services/{SERVICE_ID}")
    assert detail.status_code == 200, detail.text
    packages = detail.json()["packages"]
    assert [p["name"] for p in packages] == ["Full brand", "Starter logo"]
    assert "status" not in packages[0]  # public shape carries no lifecycle state
    assert packages[1]["price_ngwee"] == 75_000


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
    assert snap["tier"] is None and snap["name"] == "Logo + card"
    assert snap["price_ngwee"] == 150_000
    assert isinstance(snap["price_ngwee"], int)
    assert snap["delivery_days"] == 3 and snap["includes"] == ["1 concept", "PNG + PDF files"]

    # The vendor later changes the price; the thread keeps what the customer saw.
    _update(vendor, pkg["id"], name="Logo + card", price_ngwee=999_000)
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
        _archive(vendor, pkg["id"])
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
    assert [p["name"] for p in mine["packages"]] == ["Full brand", "Starter logo"]
    assert mine["packages"][1]["price_ngwee"] == 75_000
    other = next(item for item in items if item["id"] == OTHER_SERVICE)
    assert other["packages"] == []


def test_package_write_routes_have_rate_limit_policies() -> None:
    from app.core import ratelimit_policies as rp

    for route in (
        "POST /vendor/services/{service_id}/packages",
        "PUT /vendor/services/{service_id}/packages/{package_id}",
        "DELETE /vendor/services/{service_id}/packages/{package_id}",
        "POST /vendor/services/{service_id}/packages/reorder",
        "POST /vendor/services/{service_id}/packages/{package_id}/archive",
    ):
        assert route in rp.POLICIES, route


# --- Migration pins -----------------------------------------------------------
def test_the_migration_is_additive_with_rls_and_no_client_writes() -> None:
    sql = (REPO_ROOT / "supabase/migrations/20261124090100_service_packages.sql").read_text()
    lowered = sql.lower()
    assert "force row level security" in lowered
    assert "unique (service_id, tier)" in lowered
    assert "price_ngwee bigint" in lowered
    assert "grant select on table public.service_packages to anon, authenticated;" in lowered
    for verb in ("insert", "update", "delete"):
        assert f"grant {verb}" not in lowered.replace("service_role", "")
    assert "drop table public.services" not in lowered
    assert "down (reversible)" in lowered


def test_the_open_list_migration_is_additive_reversible_and_capped() -> None:
    sql = (
        REPO_ROOT / "supabase/migrations/20261127120000_service_packages_open_list.sql"
    ).read_text()
    lowered = sql.lower()
    assert "drop constraint if exists service_packages_one_per_tier" in lowered
    assert "alter column tier drop not null" in lowered
    assert "add column if not exists sort_order integer not null default 0" in lowered
    assert "when 'basic' then 0" in lowered  # existing rows keep their tier order
    assert "if active_count >= 10" in lowered  # database-level cap mirrors the API
    assert "down (reversible" in lowered
    assert "drop table" not in lowered.split("down (reversible")[0]
    assert "drop column" not in lowered.split("down (reversible")[0]
    assert "grant insert" not in lowered and "grant update" not in lowered
