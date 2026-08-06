"""RFQ threads API — listing/service quote pipeline."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.main import create_app
from fastapi.testclient import TestClient

CUSTOMER_A = "11111111-1111-1111-1111-111111111111"
VENDOR_OWNER = "33333333-3333-3333-3333-333333333333"
VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
LISTING_ID = "10101010-1010-1010-1010-101010101010"
SERVICE_ID = "20202020-2020-2020-2020-202020202020"
THREAD_ID = "30303030-3030-3030-3030-303030303030"


@pytest.fixture(autouse=True)
def _allow_rate_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.routers.rfq.bump_rate_counter",
        lambda **kwargs: (True, 0),
    )
    monkeypatch.setattr(
        "app.routers.rfq.enqueue_outbox_row",
        lambda *args, **kwargs: None,
    )


class FakeQuery:
    def __init__(self, parent: "FakeTable") -> None:
        self._parent = parent
        self._eq: list[tuple[str, Any]] = []
        self._neq: list[tuple[str, Any]] = []
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._range: tuple[int, int] | None = None
        self._maybe_single = False
        self._op: str | None = None
        self._payload: dict[str, Any] | None = None

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._eq.append((column, value))
        return self

    def neq(self, column: str, value: Any) -> FakeQuery:
        self._neq.append((column, value))
        return self

    def order(self, column: str, *, desc: bool = False) -> FakeQuery:
        self._order = (column, desc)
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
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self._op = "update"
        self._payload = payload
        return self

    def _match(self, row: dict[str, Any]) -> bool:
        for column, value in self._eq:
            if row.get(column) != value:
                return False
        for column, value in self._neq:
            if row.get(column) == value:
                return False
        return True

    def execute(self) -> MagicMock:
        if self._op == "insert":
            assert isinstance(self._payload, dict)
            row = dict(self._payload)
            self._parent.rows.append(row)
            return MagicMock(data=[row])

        matched = [row for row in self._parent.rows if self._match(row)]
        if self._op == "update":
            assert isinstance(self._payload, dict)
            for row in matched:
                row.update(self._payload)
            return MagicMock(data=[dict(row) for row in matched])

        rows = matched
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: str(row.get(column) or ""), reverse=desc)
        if self._range is not None:
            start, end = self._range
            rows = rows[start : end + 1]
        elif self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=list(rows))


class FakeTable:
    def __init__(self, name: str) -> None:
        self.name = name
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self).select(columns, count=count)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).insert(payload)

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).update(payload)


class FakeClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "vendor_listings": FakeTable("vendor_listings"),
            "services": FakeTable("services"),
            "vendors": FakeTable("vendors"),
            "rfq_threads": FakeTable("rfq_threads"),
            "rfq_messages": FakeTable("rfq_messages"),
        }

    def table(self, name: str) -> FakeTable:
        return self.tables[name]


@pytest.fixture
def fake_client() -> FakeClient:
    client = FakeClient()
    client.tables["vendors"].rows.append(
        {"id": VENDOR_ID, "owner_user_id": VENDOR_OWNER},
    )
    client.tables["vendor_listings"].rows.append(
        {
            "id": LISTING_ID,
            "vendor_id": VENDOR_ID,
            "status": "active",
            "wholesale": False,
            "product_class": "E",
        },
    )
    client.tables["services"].rows.append(
        {
            "id": SERVICE_ID,
            "vendor_id": VENDOR_ID,
            "status": "active",
            "from_price_ngwee": None,
        },
    )
    return client


@pytest.fixture
def customer_app(fake_client: FakeClient) -> TestClient:
    app = create_app()

    async def _customer() -> CurrentUser:
        return CurrentUser(id=CUSTOMER_A, roles=frozenset({"customer"}), token="cust-token")

    class _Svc:
        @property
        def client(self) -> FakeClient:
            return fake_client

    app.dependency_overrides[get_current_user] = _customer
    app.dependency_overrides[get_supabase_client] = lambda: _Svc()
    return TestClient(app)


@pytest.fixture
def vendor_app(fake_client: FakeClient) -> TestClient:
    app = create_app()

    async def _vendor() -> CurrentUser:
        return CurrentUser(id=VENDOR_OWNER, roles=frozenset({"vendor"}), token="vendor-token")

    class _Svc:
        @property
        def client(self) -> FakeClient:
            return fake_client

    app.dependency_overrides[get_current_user] = _vendor
    app.dependency_overrides[get_supabase_client] = lambda: _Svc()
    return TestClient(app)


def test_create_listing_rfq(customer_app: TestClient) -> None:
    response = customer_app.post(
        "/rfq",
        json={"listing_id": LISTING_ID, "requested_details": "Custom cake, 50 servings"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["thread"]["status"] == "pending"
    assert payload["thread"]["listing_id"] == LISTING_ID
    assert payload["reused_existing_thread"] is False


def test_create_service_rfq(customer_app: TestClient) -> None:
    response = customer_app.post(
        "/rfq",
        json={"service_id": SERVICE_ID, "requested_details": "Logo design for bakery"},
    )
    assert response.status_code == 200
    assert response.json()["thread"]["service_id"] == SERVICE_ID


def test_vendor_issues_quote(vendor_app: TestClient, customer_app: TestClient) -> None:
    created = customer_app.post(
        "/rfq",
        json={"listing_id": LISTING_ID, "requested_details": "Branded uniforms x20"},
    )
    thread_id = created.json()["thread"]["id"]

    quoted = vendor_app.post(
        f"/rfq/{thread_id}/quote",
        json={"price_ngwee": 250_000, "validity_days": 7, "message": "Includes delivery"},
    )
    assert quoted.status_code == 200
    body = quoted.json()
    assert body["status"] == "quoted"
    assert body["quote_price_ngwee"] == 250_000


def test_reject_rfq(vendor_app: TestClient, customer_app: TestClient) -> None:
    created = customer_app.post(
        "/rfq",
        json={"listing_id": LISTING_ID, "requested_details": "Too vague"},
    )
    thread_id = created.json()["thread"]["id"]
    rejected = vendor_app.post(f"/rfq/{thread_id}/reject")
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
