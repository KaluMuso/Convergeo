from __future__ import annotations

import asyncio
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier, Lock
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.core.admin_audit import AdminAuditRecorder
from app.core.auth import CurrentUser
from app.errors import AppError
from app.main import create_app
from app.routers.admin_support import SendRequest, SendResponse, support_send
from app.services.notifications.adapters.base import FailureKind
from app.services.notifications.dedupe import build_dedupe_key
from app.services.notifications.dispatcher import NotificationDispatcher, resolve_channel
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError
from starlette.requests import Request

ADMIN_ID = "66666666-6666-6666-6666-666666666666"
OTHER_USER_ID = "22222222-2222-2222-2222-222222222222"
CUSTOMER_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
ORDER_ID = "30303030-3030-3030-3030-303030303030"
VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VALID_TOKEN = "valid.jwt.token"
SUPPORT_EVENT_TYPE = "admin-support-reply"
FIRST_MESSAGE_ID = "11111111-1111-4111-8111-111111111111"
SECOND_MESSAGE_ID = "22222222-2222-4222-8222-222222222222"
THIRD_MESSAGE_ID = "33333333-3333-4333-8333-333333333333"


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

    def contains(self, column: str, value: dict[str, Any]) -> FakeQuery:
        self._filters.append(("contains", column, value))
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
            if self._parent.insert_barrier is not None:
                self._parent.insert_barrier.wait(timeout=5)
            with self._parent.insert_lock:
                if self._parent.unique_dedupe_key and any(
                    existing["dedupe_key"] == row["dedupe_key"] for existing in self._parent.rows
                ):
                    raise APIError({"code": "23505", "message": "duplicate dedupe_key"})
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
                filtered = [row for row in filtered if needle in str(row.get(column, "")).lower()]
            elif op == "like":
                prefix = value.rstrip("%")
                filtered = [row for row in filtered if str(row.get(column, "")).startswith(prefix)]
            elif op == "contains":
                filtered = [
                    row
                    for row in filtered
                    if isinstance(row.get(column), dict)
                    and all(row[column].get(key) == expected for key, expected in value.items())
                ]
        return filtered


class FakeTable:
    def __init__(self, *, unique_dedupe_key: bool = False) -> None:
        self.rows: list[dict[str, Any]] = []
        self.unique_dedupe_key = unique_dedupe_key
        self.insert_barrier: Barrier | None = None
        self.insert_lock = Lock()

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
            "notification_outbox": FakeTable(unique_dedupe_key=True),
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
    audit_client.client.table.side_effect = lambda name: (
        AuditTable() if name == "audit_log" else MagicMock()
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
            "message_id": FIRST_MESSAGE_ID,
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
    # Dispatch resolves the fixed requested primary channel to SMS using prefs.
    assert row["channel"] == "whatsapp"
    assert row["template"] == "admin-support-reply"
    assert row["dedupe_key"] == build_dedupe_key(SUPPORT_EVENT_TYPE, FIRST_MESSAGE_ID, "whatsapp")
    assert row["payload"]["customer_id"] == CUSTOMER_ID
    assert row["payload"]["recipient_id"] == CUSTOMER_ID
    assert (
        resolve_channel(row["channel"], fake_client.tables["profiles"].rows[0]["notif_prefs"])
        == "sms"
    )
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
            "message_id": FIRST_MESSAGE_ID,
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


def test_distinct_replies_enqueue_once_each_and_same_operation_dedupes(
    admin_support_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {ADMIN_ID: frozenset({"admin"})})
    audit_rows = _mock_audit_insert(monkeypatch)
    _seed_lookup_fixtures(fake_client)

    headers = {"Authorization": f"Bearer {VALID_TOKEN}"}
    canned = {
        "message_id": FIRST_MESSAGE_ID,
        "customer_id": CUSTOMER_ID,
        "order_id": ORDER_ID,
        "template_key": "delivery_eta",
    }
    free_text = {
        "message_id": SECOND_MESSAGE_ID,
        "customer_id": CUSTOMER_ID,
        "free_text": "Your delivery window is tomorrow.",
    }
    first = admin_support_client.post("/admin/support/send", headers=headers, json=canned)
    second = admin_support_client.post("/admin/support/send", headers=headers, json=free_text)
    repeated_template = admin_support_client.post(
        "/admin/support/send",
        headers=headers,
        json={**canned, "message_id": THIRD_MESSAGE_ID},
    )
    # A retry after dispatch has marked the row sent must not make another row.
    fake_client.tables["notification_outbox"].rows[1]["status"] = "sent"
    retry = admin_support_client.post("/admin/support/send", headers=headers, json=free_text)

    assert [response.status_code for response in (first, second, repeated_template, retry)] == [
        200,
        200,
        200,
        200,
    ]
    assert [
        response.json()["deduped"] for response in (first, second, repeated_template, retry)
    ] == [
        False,
        False,
        False,
        True,
    ]
    rows = fake_client.tables["notification_outbox"].rows
    assert len(rows) == 3
    assert len({row["dedupe_key"] for row in rows}) == 3
    assert rows[0]["payload"]["body"] == rows[2]["payload"]["body"]
    assert rows[1]["payload"]["body"] == free_text["free_text"]
    assert len([row for row in audit_rows if row["action"].startswith("admin.support.send_")]) == 3


@pytest.mark.parametrize(
    ("second_text", "expected_statuses"),
    [
        ("Original reply", [200, 200]),
        ("Changed reply", [200, 409]),
    ],
)
def test_concurrent_reuse_has_one_atomic_outbox_reservation(
    fake_client: FakeSupabaseClient,
    second_text: str,
    expected_statuses: list[int],
) -> None:
    _seed_lookup_fixtures(fake_client)
    fake_client.tables["notification_outbox"].insert_barrier = Barrier(2)
    service = MagicMock(client=fake_client)
    actor = CurrentUser(id=ADMIN_ID, roles=frozenset({"admin"}), token=VALID_TOKEN)

    def post_reply(message: str) -> SendResponse | AppError:
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/admin/support/send",
                "headers": [],
                "client": ("127.0.0.1", 1234),
            }
        )
        body = SendRequest.model_validate(
            {
                "message_id": FIRST_MESSAGE_ID,
                "customer_id": CUSTOMER_ID,
                "free_text": message,
            }
        )
        try:
            return asyncio.run(
                support_send(
                    body,
                    request,
                    actor,
                    service,
                    AdminAuditRecorder(ADMIN_ID, service),
                )
            )
        except AppError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(post_reply, "Original reply")
        second = pool.submit(post_reply, second_text)
        responses = [first.result(timeout=10), second.result(timeout=10)]

    assert (
        sorted(
            200 if isinstance(response, SendResponse) else response.http_status
            for response in responses
        )
        == expected_statuses
    )
    outbox = fake_client.tables["notification_outbox"].rows
    assert len(outbox) == 1
    if second_text == "Original reply":
        assert sorted(
            response.deduped for response in responses if isinstance(response, SendResponse)
        ) == [False, True]
    else:
        assert outbox[0]["payload"]["body"] in {"Original reply", "Changed reply"}
        assert sum(isinstance(response, AppError) for response in responses) == 1


def test_reused_message_id_rejects_changed_content_recipient_and_actor(
    admin_support_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {ADMIN_ID: frozenset({"admin"}), OTHER_USER_ID: frozenset({"admin"})})
    _mock_audit_insert(monkeypatch)
    _seed_lookup_fixtures(fake_client)
    other_customer = "cccccccc-cccc-cccc-cccc-cccccccccccc"
    fake_client.tables["profiles"].rows.append(
        {
            "id": other_customer,
            "phone": "+260979999999",
            "locale": "en",
            "notif_prefs": {"sms": True},
        }
    )
    original = {
        "message_id": FIRST_MESSAGE_ID,
        "customer_id": CUSTOMER_ID,
        "free_text": "Original reply",
    }
    headers = {"Authorization": f"Bearer {VALID_TOKEN}"}
    first = admin_support_client.post("/admin/support/send", headers=headers, json=original)
    assert first.status_code == 200

    for changed in (
        {**original, "free_text": "Changed reply"},
        {**original, "free_text": None, "template_key": "delivery_eta"},
        {**original, "customer_id": other_customer},
    ):
        response = admin_support_client.post("/admin/support/send", headers=headers, json=changed)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "idempotency_conflict"

    _mock_verify(monkeypatch, OTHER_USER_ID)
    response = admin_support_client.post("/admin/support/send", headers=headers, json=original)
    assert response.status_code == 409
    _mock_verify(monkeypatch)
    fake_client.tables["profiles"].rows[0]["phone"] = "+260971234568"
    response = admin_support_client.post("/admin/support/send", headers=headers, json=original)
    assert response.status_code == 409
    assert len(fake_client.tables["notification_outbox"].rows) == 1


def test_retry_after_preference_change_and_customer_log_lookup(
    admin_support_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {ADMIN_ID: frozenset({"admin"})})
    audit_rows = _mock_audit_insert(monkeypatch)
    _seed_lookup_fixtures(fake_client)
    headers = {"Authorization": f"Bearer {VALID_TOKEN}"}
    body = {
        "message_id": FIRST_MESSAGE_ID,
        "customer_id": CUSTOMER_ID,
        "template_key": "delivery_eta",
    }
    first = admin_support_client.post("/admin/support/send", headers=headers, json=body)
    assert first.status_code == 200
    fake_client.tables["profiles"].rows[0]["notif_prefs"] = {"whatsapp": True}
    retry = admin_support_client.post("/admin/support/send", headers=headers, json=body)
    assert retry.status_code == 200
    assert retry.json()["deduped"] is True
    assert retry.json()["channel"] == "sms"
    assert len(fake_client.tables["notification_outbox"].rows) == 1

    for index, audit in enumerate(audit_rows):
        fake_client.tables["audit_log"].rows.append(
            {**audit, "id": f"audit-{index}", "at": datetime.now(UTC).isoformat()}
        )
    fake_client.tables["notification_outbox"].rows.append(
        {
            "id": "other-customer-row",
            "dedupe_key": build_dedupe_key(SUPPORT_EVENT_TYPE, SECOND_MESSAGE_ID, "whatsapp"),
            "channel": "whatsapp",
            "payload": {"customer_id": "cccccccc-cccc-cccc-cccc-cccccccccccc"},
            "created_at": datetime.now(UTC).isoformat(),
        }
    )

    log = admin_support_client.get(f"/admin/support/log?customer_id={CUSTOMER_ID}", headers=headers)
    assert log.status_code == 200
    outbox_entries = [entry for entry in log.json() if entry["source"] == "outbox"]
    assert len(outbox_entries) == 1
    assert outbox_entries[0]["channel"] == "sms"
    assert len([entry for entry in log.json() if entry["source"] == "audit_log"]) == 1


def test_support_fallback_preserves_operation_and_customer_log(
    admin_support_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {ADMIN_ID: frozenset({"admin"})})
    _mock_audit_insert(monkeypatch)
    _seed_lookup_fixtures(fake_client)
    headers = {"Authorization": f"Bearer {VALID_TOKEN}"}
    response = admin_support_client.post(
        "/admin/support/send",
        headers=headers,
        json={
            "message_id": FIRST_MESSAGE_ID,
            "customer_id": CUSTOMER_ID,
            "template_key": "delivery_eta",
        },
    )
    assert response.status_code == 200
    primary = fake_client.tables["notification_outbox"].rows[0]
    dispatcher = NotificationDispatcher(MagicMock(client=fake_client), adapters={})
    dispatcher._enqueue_channel_fallback(
        dedupe_key=primary["dedupe_key"],
        channel="sms",
        failure_kind=FailureKind.PERMANENT,
        notif_prefs={"whatsapp": False, "sms": True, "email": True},
        template=primary["template"],
        payload=primary["payload"],
        attempts=1,
    )
    outbox = fake_client.tables["notification_outbox"].rows
    assert len(outbox) == 2
    assert outbox[1]["dedupe_key"] == build_dedupe_key(
        SUPPORT_EVENT_TYPE, FIRST_MESSAGE_ID, "email"
    )
    assert outbox[1]["payload"]["customer_id"] == CUSTOMER_ID

    log = admin_support_client.get(f"/admin/support/log?customer_id={CUSTOMER_ID}", headers=headers)
    assert log.status_code == 200
    assert {entry["channel"] for entry in log.json() if entry["source"] == "outbox"} == {
        "sms",
        "email",
    }


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


def test_send_requires_client_operation_id(
    admin_support_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {ADMIN_ID: frozenset({"admin"})})
    _seed_lookup_fixtures(fake_client)

    response = admin_support_client.post(
        "/admin/support/send",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={"customer_id": CUSTOMER_ID, "template_key": "delivery_eta"},
    )
    assert response.status_code == 422
    assert fake_client.tables["notification_outbox"].rows == []
