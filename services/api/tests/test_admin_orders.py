from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.errors import AppError
from app.main import create_app
from app.routers.admin_orders import (
    MANUAL_ESCROW_CONFIRMATION_PHRASE,
    enforce_dual_note,
    post_manual_escrow_transaction,
)
from app.services.orders.state import OrderEvent
from fastapi.testclient import TestClient

USER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_USER_ID = "22222222-2222-2222-2222-222222222222"
ADMIN_ID = "66666666-6666-6666-6666-666666666666"
VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
CUSTOMER_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
ORDER_ID = "30303030-3030-3030-3030-303030303030"
ORDER_B_ID = "31313131-3131-3131-3131-313131313131"
CHECKOUT_GROUP_ID = "40404040-4040-4040-4040-404040404040"
ESCROW_ACCOUNT_ID = "50505050-5050-5050-5050-505050505050"
CASH_ACCOUNT_ID = "60606060-6060-6060-6060-606060606060"
VALID_TOKEN = "valid.jwt.token"


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | list[dict[str, Any]] | None = None
        self._selected_columns = "*"
        self._or_filter: str | None = None

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        self._selected_columns = columns
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._filters.append(("in", column, values))
        return self

    def ilike(self, column: str, pattern: str) -> FakeQuery:
        self._filters.append(("ilike", column, pattern))
        return self

    def is_(self, column: str, value: str) -> FakeQuery:
        self._filters.append(("is", column, value))
        return self

    def or_(self, expression: str) -> FakeQuery:
        self._or_filter = expression
        return self

    def order(self, column: str, *, desc: bool = False) -> FakeQuery:
        self._order = (column, desc)
        return self

    def limit(self, count: int) -> FakeQuery:
        self._limit = count
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        self._pending_op = "insert"
        self._payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self._pending_op = "update"
        self._payload = payload
        return self

    def execute(self) -> MagicMock:
        if self._pending_op == "insert":
            assert isinstance(self._payload, dict)
            row = dict(self._payload)
            if "id" not in row:
                row["id"] = f"{len(self._parent.rows):08x}-fake-fake-fake-fakefakefake"
            if "created_at" not in row:
                row["created_at"] = datetime.now(UTC).isoformat()
            self._parent.rows.append(row)
            return MagicMock(data=[row])

        if self._pending_op == "update":
            assert isinstance(self._payload, dict)
            updated: list[dict[str, Any]] = []
            for row in self._parent.rows:
                if all(
                    row.get(column) == value
                    for op, column, value in self._filters
                    if op == "eq"
                ):
                    row.update(self._payload)
                    updated.append(dict(row))
            return MagicMock(data=updated)

        rows = self._apply_filters(self._parent.rows)
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: row.get(column, ""), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=rows)

    def _apply_filters(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        filtered = rows
        if self._or_filter:
            filtered = [row for row in filtered if self._matches_or(row, self._or_filter)]
        for op, column, value in self._filters:
            if op == "eq":
                filtered = [row for row in filtered if row.get(column) == value]
            elif op == "in":
                allowed = set(value)
                filtered = [row for row in filtered if row.get(column) in allowed]
            elif op == "ilike":
                needle = value.strip("%").lower()
                filtered = [
                    row
                    for row in filtered
                    if needle in str(row.get(column, "")).lower()
                ]
            elif op == "is" and value == "null":
                filtered = [row for row in filtered if row.get(column) is None]
        return filtered

    def _matches_or(self, row: dict[str, Any], expression: str) -> bool:
        clauses = expression.split(",")
        for clause in clauses:
            if ".ilike." not in clause:
                continue
            column, pattern = clause.split(".ilike.", 1)
            needle = pattern.strip("%").lower()
            if needle in str(row.get(column, "")).lower():
                return True
        return False


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self, []).select(columns, count=count)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).insert(payload)

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).update(payload)


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "orders": FakeTable(),
            "profiles": FakeTable(),
            "vendors": FakeTable(),
            "order_items": FakeTable(),
            "payments": FakeTable(),
            "ledger_transactions": FakeTable(),
            "ledger_postings": FakeTable(),
            "ledger_accounts": FakeTable(),
            "order_events": FakeTable(),
            "audit_log": FakeTable(),
        }

    def table(self, name: str) -> FakeTable:
        return self.tables[name]


@pytest.fixture
def admin_orders_app() -> Any:
    return create_app()


@pytest.fixture
def admin_orders_client(admin_orders_app: Any) -> Generator[TestClient, None, None]:
    with TestClient(admin_orders_app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> FakeSupabaseClient:
    client = FakeSupabaseClient()
    service_wrapper = MagicMock()
    service_wrapper.client = client
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: service_wrapper)
    monkeypatch.setattr("app.routers.admin_orders.get_supabase_client", lambda: service_wrapper)
    monkeypatch.setattr(
        "app.core.admin_audit.get_supabase_service_client",
        lambda: service_wrapper,
    )
    return client


def _mock_verify(monkeypatch: pytest.MonkeyPatch, user_id: str = ADMIN_ID) -> None:
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": user_id, "exp": 9_999_999_999},
    )


def _mock_roles(monkeypatch: pytest.MonkeyPatch, roles_by_user: dict[str, frozenset[str]]) -> None:
    def fake_load(user_id: str, service_client: Any) -> frozenset[str]:
        _ = service_client
        return roles_by_user.get(user_id, frozenset())

    monkeypatch.setattr("app.core.auth._load_user_roles", fake_load)


def _mock_audit_insert(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    inserted: list[dict[str, Any]] = []

    class AuditQuery:
        def __init__(self, row: dict[str, Any]) -> None:
            self._row = row

        def execute(self) -> MagicMock:
            inserted.append(self._row)
            return MagicMock(data=[{**self._row, "id": "audit-0001"}])

    class AuditTable:
        def insert(self, row: dict[str, Any]) -> AuditQuery:
            return AuditQuery(row)

    audit_client = MagicMock()
    audit_client.client.table.side_effect = (
        lambda name: AuditTable() if name == "audit_log" else MagicMock()
    )
    monkeypatch.setattr(
        "app.core.admin_audit.get_supabase_service_client",
        lambda: audit_client,
    )
    return inserted


def _seed_search_fixtures(fake: FakeSupabaseClient) -> None:
    fake.tables["vendors"].rows.append(
        {
            "id": VENDOR_ID,
            "display_name": "Lusaka Electronics",
            "slug": "lusaka-electronics",
        }
    )
    fake.tables["profiles"].rows.append(
        {
            "id": CUSTOMER_ID,
            "phone": "+260971234567",
            "display_name": "Jane Customer",
        }
    )
    fake.tables["orders"].rows.extend(
        [
            {
                "id": ORDER_ID,
                "status": "processing",
                "fulfilment": "delivery",
                "vendor_id": VENDOR_ID,
                "customer_id": CUSTOMER_ID,
                "checkout_group_id": CHECKOUT_GROUP_ID,
                "cod": False,
                "delivery_fee_ngwee": 0,
                "created_at": "2026-01-01T10:00:00+00:00",
            },
            {
                "id": ORDER_B_ID,
                "status": "placed",
                "fulfilment": "pickup",
                "vendor_id": VENDOR_ID,
                "customer_id": CUSTOMER_ID,
                "checkout_group_id": CHECKOUT_GROUP_ID,
                "cod": True,
                "delivery_fee_ngwee": 0,
                "created_at": "2026-01-02T10:00:00+00:00",
            },
        ]
    )
    fake.tables["ledger_accounts"].rows.extend(
        [
            {"id": ESCROW_ACCOUNT_ID, "kind": "escrow", "vendor_id": None},
            {"id": CASH_ACCOUNT_ID, "kind": "platform_cash", "vendor_id": None},
        ]
    )


def test_search_by_order_id(
    admin_orders_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {ADMIN_ID: frozenset({"admin"})})
    _seed_search_fixtures(fake_client)

    response = admin_orders_client.get(
        f"/admin/orders/search?order_id={ORDER_ID}",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == ORDER_ID


def test_search_by_phone(
    admin_orders_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {ADMIN_ID: frozenset({"admin"})})
    _seed_search_fixtures(fake_client)

    response = admin_orders_client.get(
        "/admin/orders/search?phone=971234567",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_search_by_vendor(
    admin_orders_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {ADMIN_ID: frozenset({"admin"})})
    _seed_search_fixtures(fake_client)

    response = admin_orders_client.get(
        "/admin/orders/search?vendor=lusaka",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_search_by_status(
    admin_orders_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {ADMIN_ID: frozenset({"admin"})})
    _seed_search_fixtures(fake_client)

    response = admin_orders_client.get(
        "/admin/orders/search?status=placed",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["status"] == "placed"


def test_dual_note_enforcement_missing_reason() -> None:
    with pytest.raises(AppError) as exc_info:
        enforce_dual_note(reason="", confirmation_phrase=MANUAL_ESCROW_CONFIRMATION_PHRASE)
    assert exc_info.value.code == "validation_error"


def test_dual_note_enforcement_missing_confirmation() -> None:
    with pytest.raises(AppError):
        enforce_dual_note(reason="Customer dispute hold", confirmation_phrase="")


def test_dual_note_enforcement_wrong_phrase() -> None:
    with pytest.raises(AppError) as exc_info:
        enforce_dual_note(reason="Hold funds", confirmation_phrase="WRONG")
    assert "confirmation_phrase" in exc_info.value.message.lower() or exc_info.value.details


def test_manual_escrow_rejects_missing_confirmation_via_api(
    admin_orders_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {ADMIN_ID: frozenset({"admin"})})
    _mock_audit_insert(monkeypatch)
    _seed_search_fixtures(fake_client)

    response = admin_orders_client.post(
        f"/admin/orders/{ORDER_ID}/escrow",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={
            "operation": "hold",
            "amount_ngwee": 50000,
            "reason": "Manual review",
            "confirmation_phrase": "",
        },
    )
    assert response.status_code == 422


def test_manual_escrow_ledger_balance_stub(
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.routers.admin_orders._load_ledger_post_transaction", lambda: None)
    service_wrapper = MagicMock()
    service_wrapper.client = fake_client
    _seed_search_fixtures(fake_client)

    result = post_manual_escrow_transaction(
        order_id=ORDER_ID,
        operation="hold",
        amount_ngwee=25000,
        reason="Investigate delivery dispute",
        confirmation_phrase=MANUAL_ESCROW_CONFIRMATION_PHRASE,
        actor_id=ADMIN_ID,
        service_client=service_wrapper,
    )
    assert result.manual is True
    assert result.balance_sum_ngwee == 0
    assert len(result.postings) == 2
    assert sum(posting.amount_ngwee for posting in result.postings) == 0


def test_non_admin_forbidden(
    admin_orders_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_verify(monkeypatch, OTHER_USER_ID)
    _mock_roles(monkeypatch, {OTHER_USER_ID: frozenset({"customer"})})
    _seed_search_fixtures(fake_client)

    response = admin_orders_client.get(
        f"/admin/orders/search?order_id={ORDER_ID}",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert response.status_code == 403


def test_illegal_intervention_rejected(
    admin_orders_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.orders.state import OrderTransitionError

    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {ADMIN_ID: frozenset({"admin"})})
    _mock_audit_insert(monkeypatch)
    _seed_search_fixtures(fake_client)

    def raise_illegal(**_kwargs: object) -> None:
        raise OrderTransitionError(
            "No transition for placed + ship",
            from_status="placed",
            event="ship",
            actor_role="admin",
        )

    monkeypatch.setattr("app.routers.admin_orders.transition_order", raise_illegal)

    response = admin_orders_client.post(
        f"/admin/orders/{ORDER_B_ID}/intervene",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={
            "event": "ship",
            "reason": "Force ship from admin",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "order_invalid_transition"


def test_dispatch_records_timeline_note(
    admin_orders_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.orders.state import OrderStatus, TransitionOutcome

    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {ADMIN_ID: frozenset({"admin"})})
    _mock_audit_insert(monkeypatch)
    _seed_search_fixtures(fake_client)

    captured: dict[str, str] = {}

    def fake_transition(**kwargs: object) -> TransitionOutcome:
        captured["note"] = str(kwargs["note"])
        return TransitionOutcome(
            order_id=ORDER_ID,
            from_status=OrderStatus.PROCESSING,
            to_status=OrderStatus.SHIPPED,
            event=OrderEvent.SHIP,
            actor_id=ADMIN_ID,
            note=str(kwargs["note"]),
        )

    monkeypatch.setattr("app.routers.admin_orders.transition_order", fake_transition)
    monkeypatch.setattr(
        "app.services.orders.state.fetch_latest_audit_event",
        lambda _order_id: {
            "actor": ADMIN_ID,
            "from_status": "processing",
            "to_status": "shipped",
            "note": captured.get("note", ""),
            "id": "timeline-event-1",
        },
    )

    response = admin_orders_client.post(
        f"/admin/orders/{ORDER_ID}/dispatch",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={
            "courier": "yango",
            "tracking_note": "Driver en route, plate BAK 1234",
            "event": OrderEvent.SHIP.value,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["to_status"] == "shipped"
    assert payload["timeline_event_id"] == "timeline-event-1"
    assert "[dispatch]" in captured["note"]
    assert "Yango" in captured["note"]
    assert "BAK 1234" in captured["note"]
