"""Tests for the Lenco webhook ingestion endpoint."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from app.deps import get_supabase_client
from app.main import create_app
from app.services.payments.webhook_verify import (
    LENCO_PROVIDER,
    SIGNATURE_HEADER,
    WebhookIngestionFlag,
    verify_lenco_webhook,
)
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

TOKEN = "test-lenco-webhook-token"
WEBHOOK_PATH = "/webhooks/lenco"


def _sign_body(raw_body: bytes, *, token: str = TOKEN) -> str:
    signing_key = hashlib.sha256(token.encode("utf-8")).hexdigest().encode("utf-8")
    return hmac.new(signing_key, raw_body, hashlib.sha512).hexdigest()


def _collection_payload(
    *,
    event: str = "collection.successful",
    event_id: str = "evt-collection-1",
    status: str = "successful",
    reference: str = "ord-order-1-attempt-1",
) -> dict[str, Any]:
    return {
        "event": event,
        "data": {
            "id": event_id,
            "reference": reference,
            "status": status,
            "amount": "13.00",
            "currency": "ZMW",
        },
    }


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | None = None

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        self._pending_op = "insert"
        self._payload = payload
        return self

    def execute(self) -> MagicMock:
        if self._pending_op != "insert" or self._payload is None:
            msg = "only insert is supported in webhook fake query"
            raise NotImplementedError(msg)

        row = dict(self._payload)
        if "id" not in row:
            row["id"] = str(uuid4())

        for existing in self._parent.rows:
            if (
                existing.get("provider") == row.get("provider")
                and existing.get("event_id") == row.get("event_id")
            ):
                raise APIError(
                    {
                        "message": "duplicate key value violates unique constraint",
                        "code": "23505",
                        "details": "webhook_events_provider_event_id_key",
                        "hint": None,
                    }
                )

        self._parent.rows.append(row)
        return MagicMock(data=[row], count=None)


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).insert(payload)


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {"webhook_events": FakeTable()}

    def table(self, name: str) -> FakeTable:
        return self.tables[name]


@pytest.fixture
def webhook_client(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[TestClient, FakeSupabaseClient], None, None]:
    monkeypatch.setenv("LENCO_API_TOKEN", TOKEN)
    fake = FakeSupabaseClient()
    app = create_app()

    class FakeServiceClient:
        def __init__(self, client: FakeSupabaseClient) -> None:
            self._client = client

        @property
        def client(self) -> FakeSupabaseClient:
            return self._client

    service_wrapper = FakeServiceClient(fake)
    app.dependency_overrides[get_supabase_client] = lambda: service_wrapper

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client, fake


def _post_webhook(
    client: TestClient,
    payload: bytes | dict[str, Any],
    *,
    signature: str | None = None,
    token: str = TOKEN,
) -> Any:
    raw_body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
    sig = signature if signature is not None else _sign_body(raw_body, token=token)
    headers = {SIGNATURE_HEADER: sig}
    return client.post(WEBHOOK_PATH, content=raw_body, headers=headers)


def test_duplicate_webhook_is_idempotent_noop(
    webhook_client: tuple[TestClient, FakeSupabaseClient],
) -> None:
    client, fake = webhook_client
    payload = _collection_payload(event_id="evt-dup-1")
    first = _post_webhook(client, payload)
    second = _post_webhook(client, payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == {"status": "accepted"}
    assert second.json() == {"status": "accepted"}

    rows = fake.tables["webhook_events"].rows
    assert len(rows) == 1
    assert rows[0]["event_id"] == "evt-dup-1"
    assert rows[0]["provider"] == LENCO_PROVIDER


def test_replayed_webhook_has_no_double_effect(
    webhook_client: tuple[TestClient, FakeSupabaseClient],
) -> None:
    client, fake = webhook_client
    payload = _collection_payload(event_id="evt-replay-1")
    for _ in range(3):
        response = _post_webhook(client, payload)
        assert response.status_code == 200

    rows = fake.tables["webhook_events"].rows
    assert len(rows) == 1


def test_out_of_order_webhooks_stored_faithfully(
    webhook_client: tuple[TestClient, FakeSupabaseClient],
) -> None:
    client, fake = webhook_client
    failed = _collection_payload(
        event="collection.failed",
        event_id="evt-out-of-order-1",
        status="failed",
    )
    success = _collection_payload(
        event="collection.successful",
        event_id="evt-out-of-order-2",
        status="successful",
        reference="ord-order-1-attempt-1",
    )

    assert _post_webhook(client, success).status_code == 200
    assert _post_webhook(client, failed).status_code == 200

    rows = fake.tables["webhook_events"].rows
    assert len(rows) == 2
    stored_events = {row["raw"]["event"] for row in rows}
    assert stored_events == {"collection.successful", "collection.failed"}
    assert all(row["processed_at"] is None for row in rows)


def test_forged_signature_returns_401_and_does_not_store(
    webhook_client: tuple[TestClient, FakeSupabaseClient],
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, fake = webhook_client
    payload = _collection_payload(event_id="evt-forged-1")
    raw_body = json.dumps(payload).encode("utf-8")

    with caplog.at_level("ERROR"):
        response = _post_webhook(client, raw_body, signature="deadbeef")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_webhook_signature"
    assert fake.tables["webhook_events"].rows == []
    assert any(
        "Lenco webhook signature verification failed" in record.getMessage()
        for record in caplog.records
    )


def test_missing_signature_returns_401_and_does_not_store(
    webhook_client: tuple[TestClient, FakeSupabaseClient],
    caplog: pytest.LogCaptureFixture,
) -> None:
    # OWASP audit finding F2: an unsigned webhook must be a clean 4xx, not a 500.
    client, fake = webhook_client
    payload = _collection_payload(event_id="evt-unsigned-1")
    raw_body = json.dumps(payload).encode("utf-8")

    with caplog.at_level("WARNING"):
        response = client.post(WEBHOOK_PATH, content=raw_body)  # no signature header

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "missing_webhook_signature"
    assert fake.tables["webhook_events"].rows == []
    assert any(
        "missing signature header" in record.getMessage() for record in caplog.records
    )


def test_missing_signature_is_401_even_without_token_configured(
    webhook_client: tuple[TestClient, FakeSupabaseClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Regression for OWASP F2: with the Lenco API token absent (the pentest env),
    # an unsigned request previously 500'd on get_api_token()'s KeyError. The
    # handler must short-circuit to 401 before ever reaching that path.
    client, fake = webhook_client
    monkeypatch.delenv("LENCO_API_TOKEN", raising=False)
    payload = _collection_payload(event_id="evt-unsigned-2")
    raw_body = json.dumps(payload).encode("utf-8")

    response = client.post(WEBHOOK_PATH, content=raw_body)  # no signature, no token

    assert response.status_code == 401  # not 500 — KeyError path never reached
    assert response.json()["error"]["code"] == "missing_webhook_signature"
    assert fake.tables["webhook_events"].rows == []


def test_whitespace_only_signature_returns_401(
    webhook_client: tuple[TestClient, FakeSupabaseClient],
) -> None:
    client, fake = webhook_client
    payload = _collection_payload(event_id="evt-unsigned-3")
    raw_body = json.dumps(payload).encode("utf-8")

    response = client.post(WEBHOOK_PATH, content=raw_body, headers={SIGNATURE_HEADER: "   "})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "missing_webhook_signature"
    assert fake.tables["webhook_events"].rows == []


def test_malformed_json_with_valid_signature_is_stored_and_flagged(
    webhook_client: tuple[TestClient, FakeSupabaseClient],
) -> None:
    client, fake = webhook_client
    raw_body = b"not-json"
    response = _post_webhook(client, raw_body)

    assert response.status_code == 200
    rows = fake.tables["webhook_events"].rows
    assert len(rows) == 1
    assert WebhookIngestionFlag.MALFORMED_JSON.value in rows[0]["raw"]["_ingestion"]["flags"]
    assert rows[0]["raw"]["_ingestion"]["raw_body"] == "not-json"


def test_unknown_event_type_is_stored_and_flagged(
    webhook_client: tuple[TestClient, FakeSupabaseClient],
) -> None:
    client, fake = webhook_client
    payload = _collection_payload(event="collection.unknown", event_id="evt-unknown-1")
    response = _post_webhook(client, payload)

    assert response.status_code == 200
    rows = fake.tables["webhook_events"].rows
    assert len(rows) == 1
    assert WebhookIngestionFlag.UNKNOWN_EVENT_TYPE.value in rows[0]["raw"]["_ingestion"]["flags"]
    assert rows[0]["raw"]["event"] == "collection.unknown"


def test_verify_lenco_webhook_rejects_before_json_parse() -> None:
    raw_body = b"{not-json"
    result = verify_lenco_webhook(
        raw_body=raw_body,
        signature="deadbeef",
        api_token=TOKEN,
    )
    assert result.valid is False
    assert result.event_id is None
    assert result.raw is None


def test_verify_lenco_webhook_extracts_event_id() -> None:
    payload = _collection_payload(event_id="evt-unit-1")
    raw_body = json.dumps(payload).encode("utf-8")
    result = verify_lenco_webhook(
        raw_body=raw_body,
        signature=_sign_body(raw_body),
        api_token=TOKEN,
    )
    assert result.valid is True
    assert result.event_id == "evt-unit-1"
    assert result.flags == []
