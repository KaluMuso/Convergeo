from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.main import create_app
from app.routers.privacy import (
    DELETE_CONFIRMATION_PHRASE,
    EXPORT_BUNDLE_KEYS,
    anonymize_and_delete_account,
    assemble_export_bundle,
)
from app.supabase_client import SupabaseServiceClient
from fastapi import FastAPI
from fastapi.testclient import TestClient

USER_A = "11111111-1111-1111-1111-111111111111"
USER_B = "22222222-2222-2222-2222-222222222222"
VALID_TOKEN = "valid.jwt.token"
OTHER_TOKEN = "other.jwt.token"


class FakeQuery:
    def __init__(self, table: str, store: dict[str, list[dict[str, Any]]]) -> None:
        self._table = table
        self._store = store
        self._filters: list[tuple[str, str, Any]] = []
        self._in_filters: list[tuple[str, list[Any]]] = []
        self._maybe_single = False
        self._update_payload: dict[str, Any] | None = None
        self._delete = False

    def select(self, *_columns: str) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._in_filters.append((column, values))
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self._update_payload = payload
        return self

    def delete(self) -> FakeQuery:
        self._delete = True
        return self

    def execute(self) -> MagicMock:
        rows = list(self._store.get(self._table, []))

        for op, column, value in self._filters:
            if op == "eq":
                rows = [row for row in rows if row.get(column) == value]

        for column, values in self._in_filters:
            allowed = set(values)
            rows = [row for row in rows if row.get(column) in allowed]

        if self._delete:
            remaining = [row for row in self._store.get(self._table, []) if row not in rows]
            self._store[self._table] = remaining
            return MagicMock(data=[])

        if self._update_payload is not None:
            for row in rows:
                row.update(self._update_payload)
            return MagicMock(data=rows)

        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None)

        return MagicMock(data=rows)


class FakeClient:
    def __init__(self, store: dict[str, list[dict[str, Any]]]) -> None:
        self._store = store
        self.auth = MagicMock()
        self.storage = MagicMock()

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(name, self._store)


def _sample_store(user_id: str) -> dict[str, list[dict[str, Any]]]:
    order_id = "order-1"
    order_item_id = "item-1"
    checkout_group_id = "cg-1"
    return {
        "profiles": [
            {
                "id": user_id,
                "phone": "+260971234567",
                "display_name": "Alice",
                "locale": "en",
                "notif_prefs": {"whatsapp": True},
                "deleted_at": None,
            }
        ],
        "addresses": [
            {
                "id": "addr-1",
                "user_id": user_id,
                "label": "Home",
                "landmark": "Near mall",
                "phone": "+260971234567",
            }
        ],
        "checkout_groups": [
            {
                "id": checkout_group_id,
                "customer_id": user_id,
                "subtotal_ngwee": 10000,
                "total_ngwee": 10000,
            }
        ],
        "orders": [
            {
                "id": order_id,
                "customer_id": user_id,
                "checkout_group_id": checkout_group_id,
                "address_id": "addr-1",
                "delivery_zone": "Lusaka",
            }
        ],
        "order_items": [{"id": order_item_id, "order_id": order_id, "qty": 1}],
        "reviews": [
            {
                "id": "rev-1",
                "order_item_id": order_item_id,
                "body": "Great",
                "photos": ["p.jpg"],
            }
        ],
        "disputes": [
            {
                "id": "disp-1",
                "order_id": order_id,
                "opener_user_id": user_id,
                "evidence_paths": ["evidence.jpg"],
            }
        ],
        "returns": [{"id": "ret-1", "order_item_id": order_item_id, "evidence_paths": ["ret.jpg"]}],
        "payments": [
            {
                "id": "pay-1",
                "checkout_group_id": checkout_group_id,
                "raw": {"customer_name": "Alice", "amount_ngwee": 10000},
            }
        ],
        "invoices": [
            {
                "id": "inv-1",
                "order_id": order_id,
                "snapshot": {"customer_name": "Alice", "phone": "+260971234567"},
            }
        ],
        "flags": [{"id": "flag-1", "reporter_user_id": user_id, "reason": "spam"}],
        "ledger_transactions": [{"id": "lt-1", "order_id": order_id, "kind": "capture"}],
        "ledger_postings": [{"id": "lp-1", "transaction_id": "lt-1", "amount_ngwee": 10000}],
    }


@pytest.fixture
def privacy_app() -> FastAPI:
    return create_app()


@pytest.fixture
def privacy_client(privacy_app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(privacy_app, raise_server_exceptions=False) as test_client:
        yield test_client


def _override_current_user(app: FastAPI, user_id: str, token: str) -> None:
    async def _current_user() -> CurrentUser:
        return CurrentUser(id=user_id, roles=frozenset({"customer"}), token=token)

    app.dependency_overrides[get_current_user] = _current_user


def _override_service(app: FastAPI, store: dict[str, list[dict[str, Any]]]) -> FakeClient:
    fake_client = FakeClient(store)
    service = SupabaseServiceClient(fake_client)  # type: ignore[arg-type]

    def _service_dep() -> Generator[SupabaseServiceClient, None, None]:
        yield service

    app.dependency_overrides[get_supabase_client] = _service_dep
    return fake_client


def test_export_bundle_contains_every_user_linked_table() -> None:
    store = _sample_store(USER_A)
    bundle = assemble_export_bundle(FakeClient(store), USER_A)  # type: ignore[arg-type]

    for key in EXPORT_BUNDLE_KEYS:
        assert key in bundle, f"missing export section: {key}"


def test_export_returns_signed_download_url(
    privacy_app: FastAPI,
    privacy_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _sample_store(USER_A)
    _override_current_user(privacy_app, USER_A, VALID_TOKEN)
    fake_service = _override_service(privacy_app, store)

    monkeypatch.setattr(
        "app.routers.privacy.get_user_client",
        lambda token, settings: FakeClient(store),
    )

    bucket = MagicMock()
    bucket.upload.return_value = MagicMock(error=None)
    bucket.create_signed_url.return_value = MagicMock(
        data={"signedURL": "https://example.supabase.co/signed/export.json?token=abc"}
    )
    fake_service.storage.from_.return_value = bucket

    response = privacy_client.post(
        "/account/export",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["download_url"].startswith("https://")
    assert body["expires_in_seconds"] == 900
    assert body["export_id"]


def test_deletion_cascade_per_table(
    privacy_app: FastAPI,
    privacy_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _sample_store(USER_A)
    _override_current_user(privacy_app, USER_A, VALID_TOKEN)
    fake_service = _override_service(privacy_app, store)

    monkeypatch.setattr("app.routers.privacy.verify_reauth_otp", lambda **kwargs: None)

    response = privacy_client.post(
        "/account/delete",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={"confirmation_phrase": DELETE_CONFIRMATION_PHRASE, "otp": "123456"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "deleted"

    assert store["addresses"] == []

    profile = store["profiles"][0]
    assert profile["display_name"] == "Deleted User"
    assert profile["phone"] is None
    assert profile["notif_prefs"] == {}
    assert profile["deleted_at"] is not None

    order = store["orders"][0]
    assert order["address_id"] is None
    assert order["delivery_zone"] is None
    assert order["id"] == "order-1"

    review = store["reviews"][0]
    assert review["body"] is None
    assert review["photos"] == []

    dispute = store["disputes"][0]
    assert dispute["evidence_paths"] == []

    returned = store["returns"][0]
    assert returned["evidence_paths"] == []

    invoice = store["invoices"][0]
    assert invoice["snapshot"]["customer_name"] == "[redacted]"
    assert invoice["snapshot"]["phone"] == "[redacted]"

    payment = store["payments"][0]
    assert payment["raw"]["customer_name"] == "[redacted]"

    assert store["ledger_transactions"][0]["kind"] == "capture"
    assert store["ledger_postings"][0]["amount_ngwee"] == 10000

    fake_service.auth.admin.delete_user.assert_called_once_with(USER_A)


def test_deletion_requires_valid_otp(
    privacy_app: FastAPI,
    privacy_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.errors import AppError

    store = _sample_store(USER_A)
    _override_current_user(privacy_app, USER_A, VALID_TOKEN)
    _override_service(privacy_app, store)

    def _reject_otp(**kwargs: Any) -> None:
        raise AppError(code="reauth_failed", message="Invalid or expired OTP", http_status=403)

    monkeypatch.setattr("app.routers.privacy.verify_reauth_otp", _reject_otp)

    response = privacy_client.post(
        "/account/delete",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={"confirmation_phrase": DELETE_CONFIRMATION_PHRASE, "otp": "000000"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "reauth_failed"
    assert store["profiles"][0]["display_name"] == "Alice"


def test_deletion_requires_confirmation_phrase(
    privacy_app: FastAPI,
    privacy_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _sample_store(USER_A)
    _override_current_user(privacy_app, USER_A, VALID_TOKEN)
    _override_service(privacy_app, store)
    monkeypatch.setattr("app.routers.privacy.verify_reauth_otp", lambda **kwargs: None)

    response = privacy_client.post(
        "/account/delete",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={"confirmation_phrase": "WRONG PHRASE", "otp": "123456"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "confirmation_required"


def test_user_cannot_delete_without_auth(privacy_client: TestClient) -> None:
    response = privacy_client.post(
        "/account/delete",
        json={"confirmation_phrase": DELETE_CONFIRMATION_PHRASE, "otp": "123456"},
    )
    assert response.status_code == 401


def test_export_scoped_to_authenticated_user_only(
    privacy_app: FastAPI,
    privacy_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store_a = _sample_store(USER_A)
    store_b = _sample_store(USER_B)

    _override_current_user(privacy_app, USER_A, VALID_TOKEN)
    fake_service = _override_service(privacy_app, store_a)

    def _user_client(token: str, settings: Any) -> FakeClient:
        assert token == VALID_TOKEN
        return FakeClient(store_a)

    monkeypatch.setattr("app.routers.privacy.get_user_client", _user_client)

    bucket = MagicMock()
    bucket.upload.return_value = MagicMock(error=None)
    bucket.create_signed_url.return_value = MagicMock(
        data={"signedURL": "https://example.supabase.co/signed/export-a.json"}
    )
    fake_service.storage.from_.return_value = bucket

    response = privacy_client.post(
        "/account/export",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert response.status_code == 200

    bundle = assemble_export_bundle(FakeClient(store_b), USER_B)  # type: ignore[arg-type]
    assert bundle["profile"]["id"] == USER_B
    assert bundle["profile"]["id"] != USER_A


def test_anonymize_is_idempotent_when_already_deleted() -> None:
    store = _sample_store(USER_A)
    store["profiles"][0]["deleted_at"] = "2026-01-01T00:00:00+00:00"
    service = SupabaseServiceClient(FakeClient(store))  # type: ignore[arg-type]

    anonymize_and_delete_account(service, user_id=USER_A)

    assert store["addresses"][0]["id"] == "addr-1"
    assert store["profiles"][0]["display_name"] == "Alice"
