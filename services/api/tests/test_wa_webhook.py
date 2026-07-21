from __future__ import annotations

import copy
import hashlib
import hmac
import json
import uuid
from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.deps import get_supabase_client
from app.main import create_app
from app.routers.webhooks_whatsapp import verify_hub_signature
from app.services.notifications.dedupe import build_dedupe_key
from app.supabase_client import SupabaseServiceClient
from fastapi.testclient import TestClient

VERIFY_TOKEN = "test-verify-token"
APP_SECRET = "test-app-secret"
PROFILE_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
PHONE_E164 = "+260971234567"
PHONE_WA = "260971234567"
WAMID = "wamid.HBgLMjYwOTcxMjM0NTY3FQIAERgSQjJDNDVFNkY3ODkwMTIzNDUAA=="


class _FakeQuery:
    def __init__(self, store: InMemoryStore, table: str) -> None:
        self._store = store
        self._table = table
        self._operation = "select"
        self._filters: list[tuple[str, str, Any]] = []
        self._contains: dict[str, Any] | None = None
        self._limit: int | None = None
        self._payload: dict[str, Any] | None = None
        self._single = False

    def select(self, *_columns: str) -> _FakeQuery:
        self._operation = "select"
        return self

    def insert(self, payload: dict[str, Any] | list[dict[str, Any]]) -> _FakeQuery:
        self._operation = "insert"
        if isinstance(payload, list):
            self._payload = payload[0]
        else:
            self._payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> _FakeQuery:
        self._operation = "update"
        self._payload = payload
        return self

    def eq(self, column: str, value: Any) -> _FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def contains(self, column: str, value: dict[str, Any]) -> _FakeQuery:
        self._contains = {column: value}
        return self

    def limit(self, value: int) -> _FakeQuery:
        self._limit = value
        return self

    def maybe_single(self) -> _FakeQuery:
        self._single = True
        return self

    def execute(self) -> MagicMock:
        if self._table == "notification_outbox":
            if self._operation == "insert":
                assert self._payload is not None
                row = self._store.insert_outbox(self._payload)
                return MagicMock(data=[row] if row else None)
            if self._operation == "update":
                assert self._payload is not None
                updated = self._store.update_outbox(self._filters, self._payload)
                return MagicMock(data=updated)
            rows = self._store.select_outbox(
                filters=self._filters,
                contains=self._contains,
                limit=self._limit,
                single=self._single,
            )
            if self._single:
                return MagicMock(data=rows[0] if rows else None)
            return MagicMock(data=rows)

        if self._table == "profiles":
            if self._operation == "update":
                assert self._payload is not None
                updated = self._store.update_profile(self._filters, self._payload)
                return MagicMock(data=updated)
            rows = self._store.select_profiles(self._filters, single=self._single)
            if self._single:
                return MagicMock(data=rows[0] if rows else None)
            return MagicMock(data=rows)

        raise AssertionError(f"Unexpected table: {self._table}")


class InMemoryStore:
    def __init__(self) -> None:
        self.outbox: dict[str, dict[str, Any]] = {}
        self.profiles: dict[str, dict[str, Any]] = {}
        self.outbox_updates = 0
        self.profile_updates = 0
        self.outbox_inserts = 0

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(self, name)

    def insert_outbox(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        dedupe_key = payload["dedupe_key"]
        if any(row["dedupe_key"] == dedupe_key for row in self.outbox.values()):
            return None
        self.outbox_inserts += 1
        row_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        row = {
            "id": row_id,
            "dedupe_key": dedupe_key,
            "channel": payload["channel"],
            "template": payload.get("template"),
            "payload": copy.deepcopy(payload.get("payload", {})),
            "status": payload.get("status", "pending"),
            "attempts": payload.get("attempts", 0),
            "next_retry_at": payload.get("next_retry_at"),
            "created_at": now,
            "updated_at": now,
        }
        self.outbox[row_id] = row
        return copy.deepcopy(row)

    def seed_outbox(
        self,
        *,
        whatsapp_message_id: str,
        status: str = "sent",
        delivery_status: str | None = None,
        recipient_id: str = PROFILE_ID,
        event_type: str = "order_confirmed",
        entity_id: str = "ord-test-1",
    ) -> dict[str, Any]:
        row_id = str(uuid.uuid4())
        payload: dict[str, Any] = {
            "whatsapp_message_id": whatsapp_message_id,
            "recipient_id": recipient_id,
        }
        if delivery_status is not None:
            payload["delivery_status"] = delivery_status
        now = datetime.now(UTC).isoformat()
        row = {
            "id": row_id,
            "dedupe_key": build_dedupe_key(event_type, entity_id, "whatsapp"),
            "channel": "whatsapp",
            "template": "order_confirmed",
            "payload": payload,
            "status": status,
            "attempts": 0,
            "next_retry_at": None,
            "created_at": now,
            "updated_at": now,
        }
        self.outbox[row_id] = row
        return copy.deepcopy(row)

    def seed_profile(
        self,
        *,
        profile_id: str = PROFILE_ID,
        phone: str = PHONE_E164,
        locale: str = "en",
        notif_prefs: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        row = {
            "id": profile_id,
            "phone": phone,
            "locale": locale,
            "notif_prefs": notif_prefs
            or {"whatsapp": True, "sms": True, "email": True},
        }
        self.profiles[profile_id] = row
        return copy.deepcopy(row)

    def select_outbox(
        self,
        *,
        filters: list[tuple[str, str, Any]],
        contains: dict[str, Any] | None,
        limit: int | None,
        single: bool,
    ) -> list[dict[str, Any]]:
        rows = [copy.deepcopy(row) for row in self.outbox.values()]
        for op, column, value in filters:
            if op == "eq":
                rows = [row for row in rows if row.get(column) == value]
        if contains is not None:
            for column, expected in contains.items():
                if column == "payload":
                    rows = [
                        row
                        for row in rows
                        if isinstance(row.get("payload"), dict)
                        and all(
                            row["payload"].get(key) == val for key, val in expected.items()
                        )
                    ]
        if limit is not None:
            rows = rows[:limit]
        if single:
            return rows[:1]
        return rows

    def update_outbox(
        self,
        filters: list[tuple[str, str, Any]],
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        self.outbox_updates += 1
        updated: list[dict[str, Any]] = []
        for row in self.outbox.values():
            if all(row.get(col) == val for op, col, val in filters if op == "eq"):
                row.update(copy.deepcopy(payload))
                if "payload" in payload and isinstance(payload["payload"], dict):
                    merged = dict(row.get("payload", {}))
                    merged.update(payload["payload"])
                    row["payload"] = merged
                updated.append(copy.deepcopy(row))
        return updated

    def select_profiles(
        self,
        filters: list[tuple[str, str, Any]],
        *,
        single: bool,
    ) -> list[dict[str, Any]]:
        rows = [copy.deepcopy(row) for row in self.profiles.values()]
        for op, column, value in filters:
            if op == "eq":
                rows = [row for row in rows if row.get(column) == value]
        if single:
            return rows[:1]
        return rows

    def update_profile(
        self,
        filters: list[tuple[str, str, Any]],
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        self.profile_updates += 1
        updated: list[dict[str, Any]] = []
        for row in self.profiles.values():
            if all(row.get(col) == val for op, col, val in filters if op == "eq"):
                row.update(copy.deepcopy(payload))
                updated.append(copy.deepcopy(row))
        return updated


def _sign_body(body: bytes, secret: str = APP_SECRET) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _status_payload(*, message_id: str = WAMID, status: str = "delivered") -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_ID",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": "123"},
                            "statuses": [
                                {
                                    "id": message_id,
                                    "status": status,
                                    "timestamp": "1710000000",
                                    "recipient_id": PHONE_WA,
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }


def _inbound_payload(
    *,
    body: str,
    sender: str = PHONE_WA,
    message_id: str = "wamid.inbound",
) -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_ID",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": "123"},
                            "contacts": [{"profile": {"name": "Test"}, "wa_id": sender}],
                            "messages": [
                                {
                                    "from": sender,
                                    "id": message_id,
                                    "timestamp": "1710000001",
                                    "text": {"body": body},
                                    "type": "text",
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def webhook_client(
    store: InMemoryStore,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", VERIFY_TOKEN)
    monkeypatch.setenv("WHATSAPP_APP_SECRET", APP_SECRET)

    service_wrapper = MagicMock(spec=SupabaseServiceClient)
    service_wrapper.client = store

    app = create_app()
    app.dependency_overrides[get_supabase_client] = lambda: service_wrapper

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client

    app.dependency_overrides.clear()


def test_verify_token_handshake(webhook_client: TestClient) -> None:
    response = webhook_client.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": VERIFY_TOKEN,
            "hub.challenge": "1234567890",
        },
    )
    assert response.status_code == 200
    assert response.text == "1234567890"


def test_verify_token_rejects_bad_token(webhook_client: TestClient) -> None:
    response = webhook_client.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong",
            "hub.challenge": "1234567890",
        },
    )
    assert response.status_code == 403


def test_forged_post_rejected_nothing_applied(
    webhook_client: TestClient,
    store: InMemoryStore,
) -> None:
    store.seed_outbox(whatsapp_message_id=WAMID)
    store.seed_profile()
    body = json.dumps(_status_payload()).encode("utf-8")

    response = webhook_client.post(
        "/webhooks/whatsapp",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": "sha256=deadbeef",
        },
    )

    assert response.status_code == 403
    assert store.outbox_updates == 0
    assert store.profile_updates == 0
    row = next(iter(store.outbox.values()))
    assert row["status"] == "sent"
    assert store.profiles[PROFILE_ID]["notif_prefs"] == {
        "whatsapp": True,
        "sms": True,
        "email": True,
    }


def test_stop_disables_all_channels(
    webhook_client: TestClient,
    store: InMemoryStore,
) -> None:
    store.seed_profile()
    body = json.dumps(_inbound_payload(body="STOP")).encode("utf-8")

    response = webhook_client.post(
        "/webhooks/whatsapp",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": _sign_body(body),
        },
    )

    assert response.status_code == 200
    prefs = store.profiles[PROFILE_ID]["notif_prefs"]
    assert prefs == {"whatsapp": False, "sms": False, "email": False}


def test_stop_inbound_enqueues_stop_confirmation(
    webhook_client: TestClient,
    store: InMemoryStore,
) -> None:
    store.seed_profile()
    inbound_id = "wamid.stop-ack-1"
    body = json.dumps(_inbound_payload(body="STOP", message_id=inbound_id)).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Hub-Signature-256": _sign_body(body),
    }

    response = webhook_client.post("/webhooks/whatsapp", content=body, headers=headers)

    assert response.status_code == 200
    ack_rows = [
        row
        for row in store.outbox.values()
        if row.get("template") == "compliance_confirmation"
    ]
    assert len(ack_rows) == 1
    ack = ack_rows[0]
    assert ack["dedupe_key"] == build_dedupe_key("whatsapp_opt_stop", inbound_id, "whatsapp")
    assert "unsubscribed" in ack["payload"]["confirmation_body"].lower()
    assert ack["payload"]["recipient_id"] == PROFILE_ID


def test_start_inbound_enqueues_start_confirmation(
    webhook_client: TestClient,
    store: InMemoryStore,
) -> None:
    store.seed_profile(notif_prefs={"whatsapp": False, "sms": False, "email": False})
    inbound_id = "wamid.start-ack-1"
    body = json.dumps(_inbound_payload(body="start", message_id=inbound_id)).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Hub-Signature-256": _sign_body(body),
    }

    response = webhook_client.post("/webhooks/whatsapp", content=body, headers=headers)

    assert response.status_code == 200
    ack_rows = [
        row
        for row in store.outbox.values()
        if row.get("template") == "compliance_confirmation"
    ]
    assert len(ack_rows) == 1
    ack = ack_rows[0]
    assert ack["dedupe_key"] == build_dedupe_key("whatsapp_opt_start", inbound_id, "whatsapp")
    assert "subscribed" in ack["payload"]["confirmation_body"].lower()


def test_duplicate_stop_inbound_does_not_double_enqueue_confirmation(
    webhook_client: TestClient,
    store: InMemoryStore,
) -> None:
    store.seed_profile()
    inbound_id = "wamid.stop-dup"
    body = json.dumps(_inbound_payload(body="STOP", message_id=inbound_id)).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Hub-Signature-256": _sign_body(body),
    }

    first = webhook_client.post("/webhooks/whatsapp", content=body, headers=headers)
    second = webhook_client.post("/webhooks/whatsapp", content=body, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    ack_rows = [
        row
        for row in store.outbox.values()
        if row.get("template") == "compliance_confirmation"
    ]
    assert len(ack_rows) == 1
    assert store.outbox_inserts == 1


def test_start_reenables_all_channels(
    webhook_client: TestClient,
    store: InMemoryStore,
) -> None:
    store.seed_profile(
        notif_prefs={"whatsapp": False, "sms": False, "email": False},
    )
    body = json.dumps(_inbound_payload(body="start")).encode("utf-8")

    response = webhook_client.post(
        "/webhooks/whatsapp",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": _sign_body(body),
        },
    )

    assert response.status_code == 200
    prefs = store.profiles[PROFILE_ID]["notif_prefs"]
    assert prefs == {"whatsapp": True, "sms": True, "email": True}


def test_duplicate_status_events_are_idempotent(
    webhook_client: TestClient,
    store: InMemoryStore,
) -> None:
    store.seed_outbox(whatsapp_message_id=WAMID, status="sent", delivery_status="delivered")
    body = json.dumps(_status_payload(status="delivered")).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Hub-Signature-256": _sign_body(body),
    }

    first = webhook_client.post("/webhooks/whatsapp", content=body, headers=headers)
    second = webhook_client.post("/webhooks/whatsapp", content=body, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert store.outbox_updates == 0
    row = next(iter(store.outbox.values()))
    assert row["status"] == "sent"
    assert row["payload"]["delivery_status"] == "delivered"


def test_status_callback_updates_outbox(
    webhook_client: TestClient,
    store: InMemoryStore,
) -> None:
    store.seed_outbox(whatsapp_message_id=WAMID, status="sent")
    store.seed_profile()
    body = json.dumps(_status_payload(status="failed")).encode("utf-8")

    response = webhook_client.post(
        "/webhooks/whatsapp",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": _sign_body(body),
        },
    )

    assert response.status_code == 200
    assert store.outbox_updates == 1
    row = next(row for row in store.outbox.values() if row["channel"] == "whatsapp")
    assert row["status"] == "failed"
    assert row["payload"]["delivery_status"] == "failed"


def test_failed_status_webhook_enqueues_sms_fallback(
    webhook_client: TestClient,
    store: InMemoryStore,
) -> None:
    store.seed_outbox(whatsapp_message_id=WAMID, status="sent")
    store.seed_profile()
    body = json.dumps(_status_payload(status="failed")).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Hub-Signature-256": _sign_body(body),
    }

    response = webhook_client.post("/webhooks/whatsapp", content=body, headers=headers)

    assert response.status_code == 200
    sms_rows = [row for row in store.outbox.values() if row["channel"] == "sms"]
    assert len(sms_rows) == 1
    sms = sms_rows[0]
    assert sms["dedupe_key"] == build_dedupe_key("order_confirmed", "ord-test-1", "sms")
    assert sms["status"] == "pending"
    assert sms["payload"]["recipient_id"] == PROFILE_ID
    assert sms["payload"]["fallback"]["to_channel"] == "sms"


def test_duplicate_failed_status_webhook_does_not_double_enqueue_fallback(
    webhook_client: TestClient,
    store: InMemoryStore,
) -> None:
    store.seed_outbox(whatsapp_message_id=WAMID, status="sent")
    store.seed_profile()
    body = json.dumps(_status_payload(status="failed")).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Hub-Signature-256": _sign_body(body),
    }

    first = webhook_client.post("/webhooks/whatsapp", content=body, headers=headers)
    second = webhook_client.post("/webhooks/whatsapp", content=body, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    sms_rows = [row for row in store.outbox.values() if row["channel"] == "sms"]
    assert len(sms_rows) == 1
    assert store.outbox_inserts == 1


def test_failed_status_skips_sms_fallback_when_all_channels_disabled(
    webhook_client: TestClient,
    store: InMemoryStore,
) -> None:
    store.seed_outbox(whatsapp_message_id=WAMID, status="sent")
    store.seed_profile(
        notif_prefs={"whatsapp": False, "sms": False, "email": False},
    )
    body = json.dumps(_status_payload(status="failed")).encode("utf-8")

    response = webhook_client.post(
        "/webhooks/whatsapp",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": _sign_body(body),
        },
    )

    assert response.status_code == 200
    assert [row for row in store.outbox.values() if row["channel"] == "sms"] == []
    assert store.outbox_inserts == 0


def test_undelivered_status_webhook_enqueues_sms_fallback(
    webhook_client: TestClient,
    store: InMemoryStore,
) -> None:
    store.seed_outbox(whatsapp_message_id=WAMID, status="sent")
    store.seed_profile()
    body = json.dumps(_status_payload(status="undelivered")).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Hub-Signature-256": _sign_body(body),
    }

    response = webhook_client.post("/webhooks/whatsapp", content=body, headers=headers)

    assert response.status_code == 200
    whatsapp_row = next(row for row in store.outbox.values() if row["channel"] == "whatsapp")
    assert whatsapp_row["status"] == "failed"
    assert whatsapp_row["payload"]["delivery_status"] == "undelivered"
    sms_rows = [row for row in store.outbox.values() if row["channel"] == "sms"]
    assert len(sms_rows) == 1


def test_delivered_status_webhook_enqueues_no_fallback(
    webhook_client: TestClient,
    store: InMemoryStore,
) -> None:
    store.seed_outbox(whatsapp_message_id=WAMID, status="sent")
    store.seed_profile()
    body = json.dumps(_status_payload(status="delivered")).encode("utf-8")

    response = webhook_client.post(
        "/webhooks/whatsapp",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": _sign_body(body),
        },
    )

    assert response.status_code == 200
    sms_rows = [row for row in store.outbox.values() if row["channel"] == "sms"]
    assert sms_rows == []
    assert store.outbox_inserts == 0


def test_unknown_sender_logged_and_200(
    webhook_client: TestClient,
    store: InMemoryStore,
    caplog: pytest.LogCaptureFixture,
) -> None:
    body = json.dumps(_inbound_payload(body="Hello support", sender="260999999999")).encode(
        "utf-8"
    )

    with caplog.at_level("INFO"):
        response = webhook_client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": _sign_body(body),
            },
        )

    assert response.status_code == 200
    assert store.profile_updates == 0
    assert any(
        "whatsapp support inbound" in record.message
        and record.__dict__.get("event") == "unknown_inbound"
        for record in caplog.records
    ) or any("unknown_inbound" in str(record.__dict__) for record in caplog.records)


def test_verify_hub_signature_unit() -> None:
    body = b'{"test":true}'
    signature = _sign_body(body)
    assert verify_hub_signature(raw_body=body, signature_header=signature, app_secret=APP_SECRET)
    assert not verify_hub_signature(
        raw_body=body,
        signature_header="sha256=deadbeef",
        app_secret=APP_SECRET,
    )
