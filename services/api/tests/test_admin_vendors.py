"""Admin vendor KYC moderation endpoints (Day 35–36)."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.main import create_app
from fastapi.testclient import TestClient

MODERATOR_ID = "11111111-1111-1111-1111-111111111111"
VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
KYC_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
VALID_TOKEN = "valid.jwt.token"


class FakeQuery:
    def __init__(self, parent: "FakeTable", filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | None = None

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
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

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self._pending_op = "update"
        self._payload = payload
        return self

    def execute(self) -> MagicMock:
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

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).update(payload)


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "vendors": FakeTable(),
            "kyc_records": FakeTable(),
            "audit_log": FakeTable(),
            "notification_outbox": FakeTable(),
        }

    def table(self, name: str) -> FakeTable:
        return self.tables[name]


@pytest.fixture
def api_client() -> Generator[TestClient, None, None]:
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> FakeSupabaseClient:
    client = FakeSupabaseClient()
    wrapper = MagicMock()
    wrapper.client = client
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: wrapper)
    monkeypatch.setattr("app.routers.admin_vendors.get_supabase_client", lambda: wrapper)
    monkeypatch.setattr("app.routers.admin_kyc.get_supabase_client", lambda: wrapper)
    monkeypatch.setattr(
        "app.services.kyc.state_machine.get_supabase_service_client",
        lambda: wrapper,
    )
    return client


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {VALID_TOKEN}"}


def _mock_auth(monkeypatch: pytest.MonkeyPatch, roles: frozenset[str]) -> None:
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": MODERATOR_ID, "exp": 9_999_999_999},
    )
    monkeypatch.setattr(
        "app.core.auth._load_user_roles",
        lambda user_id, service_client: roles if user_id == MODERATOR_ID else frozenset(),
    )


def _mock_audit_insert(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeQuery:
        def __init__(self, row: dict[str, Any]) -> None:
            self._row = row

        def execute(self) -> MagicMock:
            return MagicMock(data=[{**self._row, "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}])

    class FakeTable:
        def insert(self, row: dict[str, Any]) -> FakeQuery:
            return FakeQuery(row)

    service_client = MagicMock()

    def table_side_effect(name: str) -> Any:
        if name == "audit_log":
            return FakeTable()
        return MagicMock()

    service_client.client.table.side_effect = table_side_effect
    monkeypatch.setattr(
        "app.core.admin_audit.get_supabase_service_client",
        lambda: service_client,
    )


def _seed_vendor_queue(fake: FakeSupabaseClient) -> None:
    now = datetime.now(UTC).isoformat()
    fake.tables["vendors"].rows.append(
        {
            "id": VENDOR_ID,
            "owner_user_id": MODERATOR_ID,
            "slug": "acme-shop",
            "display_name": "Acme Shop",
            "status": "pending_kyc",
            "kyc_tier": None,
            "updated_at": now,
        }
    )
    fake.tables["kyc_records"].rows.append(
        {
            "id": KYC_ID,
            "vendor_id": VENDOR_ID,
            "tier": 1,
            "status": "submitted",
            "doc_storage_paths": ["kyc/nrc.jpg"],
            "momo_name_match": None,
            "reviewer_notes": None,
            "reviewed_by": None,
            "reviewed_at": None,
            "decision_reason": None,
            "lifecycle_reason": None,
            "updated_at": now,
        }
    )


def test_list_pending_vendors(
    api_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_auth(monkeypatch, frozenset({"moderator"}))
    _seed_vendor_queue(fake_client)

    response = api_client.get("/admin/vendors?status=pending", headers=_auth_headers())
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["vendor_id"] == VENDOR_ID
    assert body[0]["kyc_record_id"] == KYC_ID


def test_patch_vendor_approve_dispatches_n8n(
    api_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_auth(monkeypatch, frozenset({"superadmin"}))
    _mock_audit_insert(monkeypatch)
    _seed_vendor_queue(fake_client)
    scheduled: list[tuple[str, dict[str, Any]]] = []

    def capture_schedule(
        background_tasks: Any,
        *,
        event: str,
        data: dict[str, Any],
        settings: Any = None,
    ) -> None:
        _ = background_tasks, settings
        scheduled.append((event, data))

    monkeypatch.setattr("app.routers.admin_vendors.schedule_n8n_webhook", capture_schedule)
    monkeypatch.setattr(
        "app.routers.admin_vendors.transition_approve",
        lambda **kwargs: {
            "vendor": {"id": VENDOR_ID, "status": "active", "kyc_tier": 1},
            "kyc_record": {"id": KYC_ID, "status": "approved", "tier": 1},
        },
    )
    monkeypatch.setattr(
        "app.routers.admin_vendors._handle_kyc_decision",
        lambda **kwargs: type(
            "Resp",
            (),
            {
                "kyc_record_id": KYC_ID,
                "vendor_id": VENDOR_ID,
                "vendor_status": "active",
                "kyc_record_status": "approved",
                "notification_enqueued": True,
            },
        )(),
    )

    response = api_client.patch(
        f"/admin/vendors/{VENDOR_ID}/status",
        headers=_auth_headers(),
        json={"action": "approve"},
    )
    assert response.status_code == 200
    assert scheduled
    assert scheduled[0][0] == "vendor.kyc_updated"
    assert scheduled[0][1]["status"] == "approved"


def test_patch_vendor_reject_requires_reason(
    api_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_auth(monkeypatch, frozenset({"moderator"}))
    _mock_audit_insert(monkeypatch)
    _seed_vendor_queue(fake_client)

    response = api_client.patch(
        f"/admin/vendors/{VENDOR_ID}/status",
        headers=_auth_headers(),
        json={"action": "reject"},
    )
    assert response.status_code == 422


def test_vendor_endpoints_forbid_customer(
    api_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_auth(monkeypatch, frozenset({"customer"}))
    _seed_vendor_queue(fake_client)

    assert api_client.get("/admin/vendors?status=pending", headers=_auth_headers()).status_code == 403
    assert (
        api_client.patch(
            f"/admin/vendors/{VENDOR_ID}/status",
            headers=_auth_headers(),
            json={"action": "approve"},
        ).status_code
        == 403
    )
