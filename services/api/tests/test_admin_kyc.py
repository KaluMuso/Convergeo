from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.main import create_app
from app.routers.admin_kyc import (
    KYC_DOCS_BUCKET,
    SIGNED_URL_TTL_SECONDS,
    compute_sla_badge,
    sign_kyc_documents,
)
from fastapi.testclient import TestClient

USER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_USER_ID = "22222222-2222-2222-2222-222222222222"
VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
KYC_OLD_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
KYC_NEW_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
VENDOR_B_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
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

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        self._selected_columns = columns
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._filters.append(("in", column, values))
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
        for op, column, value in self._filters:
            if op == "eq":
                filtered = [row for row in filtered if row.get(column) == value]
            elif op == "in":
                allowed = set(value)
                filtered = [row for row in filtered if row.get(column) in allowed]
        return filtered


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self, []).select(columns, count=count)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).insert(payload)

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).update(payload)


class FakeStorageBucket:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def create_signed_url(self, path: str, expires_in: int) -> dict[str, Any]:
        self.calls.append((path, expires_in))
        return {
            "signedURL": f"https://example.supabase.co/storage/v1/object/sign/{KYC_DOCS_BUCKET}/{path}?token=abc",
            "expires_in": expires_in,
        }


class FakeStorage:
    def __init__(self) -> None:
        self.bucket = FakeStorageBucket()

    def from_(self, bucket: str) -> FakeStorageBucket:
        assert bucket == KYC_DOCS_BUCKET
        return self.bucket


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "vendors": FakeTable(),
            "kyc_records": FakeTable(),
            "audit_log": FakeTable(),
            "notification_outbox": FakeTable(),
        }
        self.storage = FakeStorage()

    def table(self, name: str) -> FakeTable:
        return self.tables[name]


@pytest.fixture
def admin_kyc_app() -> Any:
    return create_app()


@pytest.fixture
def admin_kyc_client(admin_kyc_app: Any) -> Generator[TestClient, None, None]:
    with TestClient(admin_kyc_app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> FakeSupabaseClient:
    client = FakeSupabaseClient()
    service_wrapper = MagicMock()
    service_wrapper.client = client
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: service_wrapper)
    monkeypatch.setattr("app.routers.admin_kyc.get_supabase_client", lambda: service_wrapper)
    monkeypatch.setattr(
        "app.services.kyc.state_machine.get_supabase_service_client",
        lambda: service_wrapper,
    )
    return client


def _mock_verify(monkeypatch: pytest.MonkeyPatch, user_id: str = USER_ID) -> None:
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

    class FakeQuery:
        def __init__(self, row: dict[str, Any]) -> None:
            self._row = row

        def execute(self) -> MagicMock:
            inserted.append(self._row)
            return MagicMock(data=[{**self._row, "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}])

    class FakeTable:
        def insert(self, row: dict[str, Any]) -> FakeQuery:
            return FakeQuery(row)

    service_client = MagicMock()
    service_client.client.table.side_effect = (
        lambda name: FakeTable() if name == "audit_log" else MagicMock()
    )
    monkeypatch.setattr(
        "app.core.admin_audit.get_supabase_service_client",
        lambda: service_client,
    )
    return inserted


def _seed_pending_queue(fake: FakeSupabaseClient) -> None:
    now = datetime.now(UTC)
    fake.tables["vendors"].rows.extend(
        [
            {
                "id": VENDOR_ID,
                "owner_user_id": USER_ID,
                "slug": "acme-shop",
                "display_name": "Acme Shop",
                "status": "pending_kyc",
                "kyc_tier": None,
            },
            {
                "id": VENDOR_B_ID,
                "owner_user_id": OTHER_USER_ID,
                "slug": "beta-shop",
                "display_name": "Beta Shop",
                "status": "pending_kyc",
                "kyc_tier": None,
            },
        ]
    )
    fake.tables["kyc_records"].rows.extend(
        [
            {
                "id": KYC_OLD_ID,
                "vendor_id": VENDOR_ID,
                "tier": 1,
                "status": "submitted",
                "doc_storage_paths": [
                    "kyc/vendor-a/nrc.jpg",
                    "kyc/vendor-a/selfie.jpg",
                ],
                "momo_name_match": {
                    "phone": "+260971234567",
                    "operator": "mtn",
                    "resolved_name": "John Banda",
                    "legal_name": "John Banda",
                    "match_score": 0.95,
                    "matched": True,
                },
                "reviewer_notes": None,
                "reviewed_by": None,
                "reviewed_at": None,
                "decision_reason": None,
                "lifecycle_reason": None,
                "created_at": (now - timedelta(hours=90)).isoformat(),
                "updated_at": (now - timedelta(hours=80)).isoformat(),
            },
            {
                "id": KYC_NEW_ID,
                "vendor_id": VENDOR_B_ID,
                "tier": 1,
                "status": "submitted",
                "doc_storage_paths": ["kyc/vendor-b/nrc.jpg", "kyc/vendor-b/selfie.jpg"],
                "momo_name_match": {
                    "phone": "+260971234568",
                    "operator": "airtel",
                    "resolved_name": "Jane Phiri",
                    "legal_name": "Jane Phiri",
                    "match_score": 0.91,
                    "matched": True,
                },
                "reviewer_notes": None,
                "reviewed_by": None,
                "reviewed_at": None,
                "decision_reason": None,
                "lifecycle_reason": None,
                "created_at": (now - timedelta(hours=3)).isoformat(),
                "updated_at": (now - timedelta(hours=2)).isoformat(),
            },
        ]
    )


def _seed_single_pending(fake: FakeSupabaseClient, *, kyc_id: str = KYC_NEW_ID) -> None:
    now = datetime.now(UTC)
    fake.tables["vendors"].rows.append(
        {
            "id": VENDOR_B_ID,
            "owner_user_id": OTHER_USER_ID,
            "slug": "beta-shop",
            "display_name": "Beta Shop",
            "status": "pending_kyc",
            "kyc_tier": None,
        }
    )
    fake.tables["kyc_records"].rows.append(
        {
            "id": kyc_id,
            "vendor_id": VENDOR_B_ID,
            "tier": 1,
            "status": "submitted",
            "doc_storage_paths": ["kyc/vendor-b/nrc.jpg", "kyc/vendor-b/selfie.jpg"],
            "momo_name_match": {
                "phone": "+260971234568",
                "operator": "airtel",
                "resolved_name": "Jane Phiri",
                "legal_name": "Jane Phiri",
                "match_score": 0.91,
                "matched": True,
            },
            "reviewer_notes": None,
            "reviewed_by": None,
            "reviewed_at": None,
            "decision_reason": None,
            "lifecycle_reason": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
    )


def test_signed_url_ttl_is_at_most_five_minutes(fake_client: FakeSupabaseClient) -> None:
    service_wrapper = MagicMock()
    service_wrapper.client = fake_client
    documents, docs_available = sign_kyc_documents(
        service_wrapper,
        ["kyc/vendor-a/nrc.jpg", "kyc/vendor-a/selfie.jpg"],
    )
    assert docs_available is True
    assert fake_client.storage.bucket.calls
    for path, expires_in in fake_client.storage.bucket.calls:
        assert path
        assert expires_in <= 300
    for doc in documents:
        assert doc.ttl_seconds <= 300
        assert doc.signed_url is not None
        assert doc.expires_at is not None


def test_signed_url_unusable_after_ttl(fake_client: FakeSupabaseClient) -> None:
    service_wrapper = MagicMock()
    service_wrapper.client = fake_client
    frozen_now = datetime(2026, 7, 9, 12, 0, 0, tzinfo=UTC)
    documents, _ = sign_kyc_documents(
        service_wrapper,
        ["kyc/vendor-a/nrc.jpg"],
        now=frozen_now,
    )
    doc = documents[0]
    assert doc.expires_at == frozen_now + timedelta(seconds=SIGNED_URL_TTL_SECONDS)
    assert doc.expires_at < frozen_now + timedelta(seconds=301)
    expired_at = doc.expires_at + timedelta(seconds=1)
    assert expired_at > frozen_now + timedelta(seconds=SIGNED_URL_TTL_SECONDS)


def test_queue_ordering_oldest_first_and_sla_badge(
    admin_kyc_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"admin"})})
    _seed_pending_queue(fake_client)

    response = admin_kyc_client.get(
        "/admin/kyc",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert payload[0]["id"] == KYC_OLD_ID
    assert payload[1]["id"] == KYC_NEW_ID
    assert payload[0]["sla_badge"] == "overdue"
    assert payload[1]["sla_badge"] == "on_track"


def test_compute_sla_badge_thresholds() -> None:
    now = datetime(2026, 7, 9, 12, 0, 0, tzinfo=UTC)
    on_track, _ = compute_sla_badge(now - timedelta(hours=12), now=now)
    due_soon, _ = compute_sla_badge(now - timedelta(hours=48), now=now)
    overdue, _ = compute_sla_badge(now - timedelta(hours=96), now=now)
    assert on_track == "on_track"
    assert due_soon == "due_soon"
    assert overdue == "overdue"


def test_approve_transitions_vendor_active_and_enqueues_notification(
    admin_kyc_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"admin"})})
    _mock_audit_insert(monkeypatch)
    _seed_single_pending(fake_client)

    response = admin_kyc_client.post(
        f"/admin/kyc/{KYC_NEW_ID}/approve",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={"reviewer_notes": "Looks good"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["vendor_status"] == "active"
    assert body["kyc_record_status"] == "approved"
    assert body["notification_enqueued"] is True

    vendor = next(row for row in fake_client.tables["vendors"].rows if row["id"] == VENDOR_B_ID)
    assert vendor["status"] == "active"
    assert vendor["kyc_tier"] == 1
    kyc_row = next(row for row in fake_client.tables["kyc_records"].rows if row["id"] == KYC_NEW_ID)
    assert kyc_row["status"] == "approved"
    assert kyc_row["reviewed_by"] == USER_ID
    assert kyc_row["reviewed_at"] is not None
    assert kyc_row["decision_reason"] == "Looks good"
    outbox = fake_client.tables["notification_outbox"].rows
    assert len(outbox) == 1
    assert outbox[0]["template"] == "kyc_approved"
    assert outbox[0]["dedupe_key"] == f"kyc_approved:{KYC_NEW_ID}:whatsapp"
    audit_actions = [row["action"] for row in fake_client.tables["audit_log"].rows]
    assert "kyc.approve" in audit_actions


def test_reject_enqueues_notification(
    admin_kyc_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"admin"})})
    _mock_audit_insert(monkeypatch)
    _seed_single_pending(fake_client)

    response = admin_kyc_client.post(
        f"/admin/kyc/{KYC_NEW_ID}/reject",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={"reason_template": "blurry_document", "free_text": "NRC unreadable"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["kyc_record_status"] == "rejected"
    assert body["notification_enqueued"] is True
    outbox = fake_client.tables["notification_outbox"].rows
    assert outbox[0]["template"] == "kyc_rejected"


def test_request_resubmit_enqueues_notification(
    admin_kyc_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"admin"})})
    _mock_audit_insert(monkeypatch)
    _seed_single_pending(fake_client)

    response = admin_kyc_client.post(
        f"/admin/kyc/{KYC_NEW_ID}/request-resubmit",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={
            "reason_template": "incomplete_submission",
            "free_text": "Please re-upload selfie",
            "docs_requested": ["selfie"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["kyc_record_status"] == "rejected"
    assert body["notification_enqueued"] is True
    outbox = fake_client.tables["notification_outbox"].rows
    assert outbox[0]["template"] == "kyc_resubmit_requested"


def test_kyc_detail_returns_signed_documents(
    admin_kyc_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"admin"})})
    _seed_pending_queue(fake_client)

    response = admin_kyc_client.get(
        f"/admin/kyc/{KYC_OLD_ID}",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["docs_available"] is True
    assert len(body["documents"]) == 2
    doc_types = {doc["doc_type"] for doc in body["documents"]}
    assert doc_types == {"nrc", "selfie"}
    assert all(doc["signed_url"] for doc in body["documents"])
    assert all(doc["ttl_seconds"] <= 300 for doc in body["documents"])


def test_non_admin_gets_403(
    admin_kyc_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_verify(monkeypatch, OTHER_USER_ID)
    _mock_roles(monkeypatch, {OTHER_USER_ID: frozenset({"customer"})})
    _seed_single_pending(fake_client)

    response = admin_kyc_client.get(
        "/admin/kyc",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert response.status_code == 403
