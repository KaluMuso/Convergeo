from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.main import create_app
from app.services.notifications.dedupe import build_dedupe_key
from fastapi.testclient import TestClient

ADMIN_ID = "66666666-6666-6666-6666-666666666666"
OTHER_USER_ID = "22222222-2222-2222-2222-222222222222"
CUSTOMER_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
ORDER_ID = "30303030-3030-3030-3030-303030303030"
VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VALID_TOKEN = "valid.jwt.token"
SUPPORT_EVENT_TYPE = "admin-support-reply"


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

    def like(self, column: str, pattern: str) -> FakeQuery:
        self._filters.append(("like", column, pattern))
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

    def execute(self) -> MagicMock:
        if self._pending_op == "insert":
            assert isinstance(self._payload, dict)
            row = dict(self._payload)
            if "id" not in row:
                row["id"] = f"{len(self._parent.rows):08x}-fake-fake-fake-fakefakefake"
            if "created_at" not in row:
                row["created_at"] = datetime.now(UTC).isoformat()
            if "at" not in row:
                row["at"] = datetime.now(UTC).isoformat()
            self._parent.rows.append(row)
            return MagicMock(data=[row])

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
            elif op == "like":
                prefix = value.rstrip("%")
                filtered = [
                    row
                    for row in filtered
                    if str(row.get(column, "")).startswith(prefix)
                ]
        return filtered


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self, []).select(columns, count=count)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).insert(payload)


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "profiles": FakeTable(),
            "orders": FakeTable(),
            "vendors": FakeTable(),
            "notification_outbox": FakeTable(),
            "audit_log": FakeTable(),
        }

    def table(self, name: str) -> FakeTable:
        return self.tables[name]


@pytest.fixture
def admin_support_app() -> Any:
    return create_app()


@pytest.fixture
def admin_support_client(admin_support_app: Any) -> Generator[TestClient, None, None]:
    with TestClient(admin_support_app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> FakeSupabaseClient:
    client = FakeSupabaseClient()
    service_wrapper = MagicMock()
    service_wrapper.client = client
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: service_wrapper)
    monkeypatch.setattr("app.routers.admin_support.get_supabase_client", lambda: service_wrapper)
    monkeypatch.setattr(
        "app.core.admin_audit.get_supabase_service_client",
        lambda: service_wrapper,
    )
    monkeypatch.setattr(
        "app.routers.admin_support.bump_rate_counter",
        lambda **kwargs: (True, 0),
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


def _seed_lookup_fixtures(fake: FakeSupabaseClient) -> None:
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
            "locale": "en",
            "notif_prefs": {"whatsapp": False, "sms": True, "email": True},
        }
    )
    fake.tables["orders"].rows.append(
        {
            "id": ORDER_ID,
            "status": "processing",
            "vendor_id": VENDOR_ID,
            "customer_id": CUSTOMER_ID,
            "created_at": "2026-01-01T10:00:00+00:00",
        }
    )


def test_lookup_partial_phone_finds_customer_and_order(
    admin_support_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {ADMIN_ID: frozenset({"admin"})})
    _seed_lookup_fixtures(fake_client)

    response = admin_support_client.get(
        "/admin/support/lookup?q=712345",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["matches"]) == 1
    match = body["matches"][0]
    assert match["customer"]["id"] == CUSTOMER_ID
    assert match["customer"]["phone"] == "+260971234567"
    assert len(match["orders"]) == 1
    assert match["orders"][0]["id"] == ORDER_ID


def test_canned_send_enqueues_outbox_with_channel_fallback(
    admin_support_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {ADMIN_ID: frozenset({"admin"})})
    _mock_audit_insert(monkeypatch)
    _seed_lookup_fixtures(fake_client)

    response = admin_support_client.post(
        "/admin/support/send",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={
            "customer_id": CUSTOMER_ID,
            "order_id": ORDER_ID,
            "template_key": "delivery_eta",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["channel"] == "sms"
    assert payload["template_key"] == "delivery_eta"
    assert payload["deduped"] is False

    outbox = fake_client.tables["notification_outbox"].rows
    assert len(outbox) == 1
    row = outbox[0]
    assert row["channel"] == "sms"
    assert row["template"] == "admin-support-reply"
    assert row["dedupe_key"] == build_dedupe_key(SUPPORT_EVENT_TYPE, CUSTOMER_ID, "sms")
    assert row["payload"]["customer_id"] == CUSTOMER_ID
    assert row["payload"]["kind"] == "canned"
    assert row["payload"]["template_key"] == "delivery_eta"


def test_free_text_send_writes_audit_log_row(
    admin_support_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {ADMIN_ID: frozenset({"admin"})})
    audit_rows = _mock_audit_insert(monkeypatch)
    _seed_lookup_fixtures(fake_client)

    message = "Please call us back about your delivery window."
    response = admin_support_client.post(
        "/admin/support/send",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={
            "customer_id": CUSTOMER_ID,
            "free_text": message,
        },
    )
    assert response.status_code == 200

    assert len(audit_rows) == 1
    audit = audit_rows[0]
    assert audit["action"] == "admin.support.send_free_text"
    assert audit["entity_type"] == "customer"
    assert audit["entity_id"] == CUSTOMER_ID
    assert audit["after"]["body"] == message
    assert audit["after"]["kind"] == "free_text"


def test_non_admin_forbidden(
    admin_support_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_verify(monkeypatch, OTHER_USER_ID)
    _mock_roles(monkeypatch, {OTHER_USER_ID: frozenset({"customer"})})
    _seed_lookup_fixtures(fake_client)

    response = admin_support_client.get(
        "/admin/support/lookup?q=712345",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert response.status_code == 403
