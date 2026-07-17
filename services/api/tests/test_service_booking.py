"""Direct service booking — validation, idempotent replay, and spine hand-off."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.main import create_app
from app.services.rfq.engagement import AcceptResult
from fastapi import FastAPI
from fastapi.testclient import TestClient

CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
VENDOR_OWNER_ID = "22222222-2222-2222-2222-222222222222"
VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SERVICE_ID = "b0000000-0000-4000-8000-000000000001"
IDEM = "idem-key-12345678"


def _accept_result(*, replayed: bool = False) -> AcceptResult:
    return AcceptResult(
        job_id="job-1",
        quote_id="quote-1",
        checkout_group_id="cg-1",
        order_id="ord-1",
        vendor_id=VENDOR_ID,
        deposit_order_item_id="oi-1",
        total_job_ngwee=100_000,
        deposit_ngwee=50_000,
        balance_ngwee=50_000,
        commission_ngwee=12_000,
        commission_rate_bps=1200,
        replayed=replayed,
    )


class FakeQuery:
    def __init__(self, parent: FakeTable) -> None:
        self._parent = parent
        self._filters: list[tuple[str, Any]] = []
        self._maybe_single = False

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append((column, value))
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def execute(self) -> MagicMock:
        rows = [
            row
            for row in self._parent.rows
            if all(row.get(col) == val for col, val in self._filters)
        ]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=list(rows))


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self).select(columns, count=count)


class FakeClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {}

    def table(self, name: str) -> FakeTable:
        if name not in self.tables:
            self.tables[name] = FakeTable()
        return self.tables[name]


class _Wrapper:
    def __init__(self, client: FakeClient) -> None:
        self.client = client


@pytest.fixture
def fake() -> FakeClient:
    client = FakeClient()
    client.table("services").rows.append(
        {
            "id": SERVICE_ID,
            "vendor_id": VENDOR_ID,
            "category": "cleaning",
            "title": "Deep Clean",
            "status": "active",
            "bookable": True,
            "booking_price_ngwee": 100_000,
        }
    )
    client.table("vendors").rows.append(
        {"id": VENDOR_ID, "owner_user_id": VENDOR_OWNER_ID}
    )
    return client


@pytest.fixture(autouse=True)
def _allow_rate_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.routers.service_booking.bump_rate_counter",
        lambda **kwargs: (True, 0),
    )


def _make_client(*, user_id: str, fake: FakeClient) -> TestClient:
    app: FastAPI = create_app()

    async def override_current_user() -> CurrentUser:
        return CurrentUser(id=user_id, roles=frozenset({"customer"}), token="test-token")

    def override_service_client() -> _Wrapper:
        return _Wrapper(fake)

    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_supabase_client] = override_service_client
    return TestClient(app, raise_server_exceptions=False)


def _mock_spine(
    monkeypatch: pytest.MonkeyPatch,
    *,
    existing: AcceptResult | None,
    accept: AcceptResult | None,
) -> MagicMock:
    monkeypatch.setattr(
        "app.services.rfq.booking._load_existing_accept", lambda quote_id: existing
    )
    monkeypatch.setattr(
        "app.services.rfq.booking.run_sql_script",
        lambda script: MagicMock(ok=True, error=None, rows=[]),
    )
    accept_mock = MagicMock(return_value=accept)
    monkeypatch.setattr("app.services.rfq.booking.accept_quote", accept_mock)
    return accept_mock


def test_book_success_reuses_spine(fake: FakeClient, monkeypatch: pytest.MonkeyPatch) -> None:
    accept_mock = _mock_spine(monkeypatch, existing=None, accept=_accept_result())
    client = _make_client(user_id=CUSTOMER_ID, fake=fake)

    response = client.post(f"/services/{SERVICE_ID}/book", json={"idempotency_key": IDEM})
    assert response.status_code == 200
    body = response.json()
    assert body["deposit_ngwee"] == 50_000
    assert body["total_job_ngwee"] == 100_000
    assert body["replayed"] is False
    accept_mock.assert_called_once()


def test_book_replay_is_idempotent(fake: FakeClient, monkeypatch: pytest.MonkeyPatch) -> None:
    accept_mock = _mock_spine(
        monkeypatch, existing=_accept_result(replayed=True), accept=None
    )
    client = _make_client(user_id=CUSTOMER_ID, fake=fake)

    response = client.post(f"/services/{SERVICE_ID}/book", json={"idempotency_key": IDEM})
    assert response.status_code == 200
    assert response.json()["replayed"] is True
    # A prior booking short-circuits — the spine is never re-invoked.
    accept_mock.assert_not_called()


def test_book_service_not_found(fake: FakeClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_spine(monkeypatch, existing=None, accept=_accept_result())
    client = _make_client(user_id=CUSTOMER_ID, fake=fake)
    response = client.post(
        "/services/c0000000-0000-4000-8000-000000000009/book",
        json={"idempotency_key": IDEM},
    )
    assert response.status_code == 404


def test_book_not_active(fake: FakeClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake.table("services").rows[0]["status"] = "paused"
    _mock_spine(monkeypatch, existing=None, accept=_accept_result())
    client = _make_client(user_id=CUSTOMER_ID, fake=fake)
    response = client.post(f"/services/{SERVICE_ID}/book", json={"idempotency_key": IDEM})
    assert response.status_code == 409


def test_book_not_bookable(fake: FakeClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake.table("services").rows[0]["bookable"] = False
    _mock_spine(monkeypatch, existing=None, accept=_accept_result())
    client = _make_client(user_id=CUSTOMER_ID, fake=fake)
    response = client.post(f"/services/{SERVICE_ID}/book", json={"idempotency_key": IDEM})
    assert response.status_code == 409


def test_book_own_service_rejected(fake: FakeClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_spine(monkeypatch, existing=None, accept=_accept_result())
    # The customer IS the provider's owner.
    client = _make_client(user_id=VENDOR_OWNER_ID, fake=fake)
    response = client.post(f"/services/{SERVICE_ID}/book", json={"idempotency_key": IDEM})
    assert response.status_code == 422


def test_book_requires_idempotency_key(fake: FakeClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_spine(monkeypatch, existing=None, accept=_accept_result())
    client = _make_client(user_id=CUSTOMER_ID, fake=fake)
    response = client.post(f"/services/{SERVICE_ID}/book", json={})
    assert response.status_code == 422  # missing required idempotency_key
