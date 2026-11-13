"""Admin advance-debt endpoints: admin-only, strict validation, audited repayments.

Service functions are stubbed here (the ledger / debt / sweep behaviour is covered
against Postgres in test_event_advance_policy.py::TestRepaymentBeforeDue).
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.core.auth import CurrentUser, get_current_user
from app.main import create_app
from app.routers import admin_event_advance_debts as route
from app.services.events.advance_policy import AdvanceDebtRow
from fastapi.testclient import TestClient

ADMIN_ID = "11111111-1111-1111-1111-111111111111"
VENDOR_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
DEBT_ROW = AdvanceDebtRow(
    id="d0000000-0000-4000-8000-000000000001",
    vendor_id=VENDOR_ID,
    vendor_name="Shop B",
    event_id="e0000000-0000-4000-8000-000000000001",
    event_title="Festival",
    order_id="0a000000-0000-4000-8000-000000000001",
    amount_ngwee=45_000,
    recovered_ngwee=0,
    status="open",
    due_at="2026-12-01T00:00:00+00:00",
    suspended_at=None,
    blacklisted_at=None,
    legal_followup_at=None,
    created_at="2026-11-13T00:00:00+00:00",
)


class Harness:
    def __init__(self) -> None:
        self.audit_rows: list[dict[str, Any]] = []
        self.list_calls: list[dict[str, Any]] = []
        self.repayments: list[dict[str, Any]] = []
        self.receivable = 45_000


def _service_client(harness: Harness) -> MagicMock:
    class FakeAuditQuery:
        def __init__(self, row: dict[str, Any]) -> None:
            self._row = row

        def execute(self) -> MagicMock:
            harness.audit_rows.append(self._row)
            return MagicMock(data=[{**self._row, "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}])

    class FakeAuditTable:
        def insert(self, row: dict[str, Any]) -> FakeAuditQuery:
            return FakeAuditQuery(row)

    client = MagicMock()
    client.client.table.side_effect = lambda name: (
        FakeAuditTable() if name == "audit_log" else MagicMock()
    )
    return client


def _client(
    monkeypatch: pytest.MonkeyPatch, roles: frozenset[str]
) -> Generator[tuple[TestClient, Harness], None, None]:
    harness = Harness()
    service = _service_client(harness)
    monkeypatch.setattr("app.core.admin_audit.get_supabase_service_client", lambda: service)
    monkeypatch.setattr("app.core.auth.get_supabase_service_client", lambda: service)
    monkeypatch.setattr("app.core.auth.load_admin_permissions", lambda *_a: frozenset())

    def fake_list(**kwargs: Any) -> list[AdvanceDebtRow]:
        harness.list_calls.append(kwargs)
        return [DEBT_ROW]

    def fake_repay(**kwargs: Any) -> str:
        harness.repayments.append(kwargs)
        harness.receivable -= int(kwargs["amount_ngwee"])
        return "txn-1"

    monkeypatch.setattr(route, "list_advance_debts", fake_list)
    monkeypatch.setattr(route, "record_organiser_repayment", fake_repay)
    monkeypatch.setattr(route, "organiser_receivable_balance_ngwee", lambda _v: harness.receivable)
    app = create_app()
    user = CurrentUser(id=ADMIN_ID, roles=roles, token="test")
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, harness


@pytest.fixture
def admin(monkeypatch: pytest.MonkeyPatch) -> Generator[tuple[TestClient, Harness], None, None]:
    yield from _client(monkeypatch, frozenset({"admin"}))


@pytest.mark.parametrize("roles", [frozenset({"vendor"}), frozenset({"rbac_finance"})])
def test_non_admins_are_denied(monkeypatch: pytest.MonkeyPatch, roles: frozenset[str]) -> None:
    for client, harness in _client(monkeypatch, roles):
        assert client.get("/admin/event-advance-debts").status_code == 403
        response = client.post(
            "/admin/event-advance-debts/repayments",
            json={"vendor_id": VENDOR_ID, "amount_ngwee": 100, "reference": "bank-1"},
        )
        assert response.status_code == 403
        assert harness.repayments == [] and harness.audit_rows == []


def test_list_passes_filters(admin: tuple[TestClient, Harness]) -> None:
    client, harness = admin
    response = client.get(
        "/admin/event-advance-debts", params={"status": "open", "vendor_id": VENDOR_ID}
    )
    assert response.status_code == 200, response.text
    item = response.json()["items"][0]
    assert item["outstanding_ngwee"] == 45_000
    assert item["vendor_name"] == "Shop B"
    assert harness.list_calls[0] == {"status": "open", "vendor_id": VENDOR_ID, "limit": 100}


@pytest.mark.parametrize(
    "params", [{"status": "paid"}, {"vendor_id": "not-a-uuid"}, {"limit": "0"}]
)
def test_list_rejects_bad_filters(
    admin: tuple[TestClient, Harness], params: dict[str, str]
) -> None:
    client, harness = admin
    assert client.get("/admin/event-advance-debts", params=params).status_code == 422
    assert harness.list_calls == []


def test_repayment_is_recorded_and_audited(admin: tuple[TestClient, Harness]) -> None:
    client, harness = admin
    response = client.post(
        "/admin/event-advance-debts/repayments",
        json={"vendor_id": VENDOR_ID, "amount_ngwee": 45_000, "reference": "MTN.Momo-0091"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["transaction_id"] == "txn-1"
    assert body["receivable_ngwee"] == 0
    assert harness.repayments == [
        {
            "vendor_id": VENDOR_ID,
            "amount_ngwee": 45_000,
            "actor_user_id": ADMIN_ID,
            "reference": "MTN.Momo-0091",
        }
    ]
    assert len(harness.audit_rows) == 1
    audit = harness.audit_rows[0]
    assert audit["action"] == "admin.event_advance.repayment_recorded"
    assert audit["entity_id"] == VENDOR_ID
    assert audit["before"] == {"receivable_ngwee": 45_000}
    assert audit["after"]["amount_ngwee"] == 45_000


@pytest.mark.parametrize(
    "payload",
    [
        {"vendor_id": VENDOR_ID, "amount_ngwee": 0, "reference": "bank-1"},
        {"vendor_id": VENDOR_ID, "amount_ngwee": -5, "reference": "bank-1"},
        {"vendor_id": VENDOR_ID, "amount_ngwee": 100.5, "reference": "bank-1"},
        {"vendor_id": VENDOR_ID, "amount_ngwee": "100", "reference": "bank-1"},
        {"vendor_id": VENDOR_ID, "amount_ngwee": 1_000_000_001, "reference": "bank-1"},
        {"vendor_id": VENDOR_ID, "amount_ngwee": 100, "reference": "x"},
        {"vendor_id": VENDOR_ID, "amount_ngwee": 100, "reference": "bank 1; drop"},
        {"vendor_id": "nope", "amount_ngwee": 100, "reference": "bank-1"},
        {"vendor_id": VENDOR_ID, "amount_ngwee": 100, "reference": "bank-1", "extra": 1},
        {"vendor_id": VENDOR_ID, "reference": "bank-1"},
    ],
)
def test_repayment_validation(admin: tuple[TestClient, Harness], payload: dict[str, Any]) -> None:
    client, harness = admin
    response = client.post("/admin/event-advance-debts/repayments", json=payload)
    assert response.status_code == 422, response.text
    assert harness.repayments == [] and harness.audit_rows == []


def test_repayment_route_has_payment_rate_limit() -> None:
    from app.core.ratelimit_policies import PAYMENT_WRITE, POLICIES

    assert POLICIES["POST /admin/event-advance-debts/repayments"] is PAYMENT_WRITE


def test_routes_are_not_delegated_to_admin_permission_roles() -> None:
    from app.core.auth import admin_permission_for_request

    assert admin_permission_for_request("/admin/event-advance-debts", "GET") is None
    assert admin_permission_for_request("/admin/event-advance-debts/repayments", "POST") is None
