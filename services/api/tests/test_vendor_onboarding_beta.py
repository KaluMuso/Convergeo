"""VENDOR-BETA-01: invite/concierge seller onboarding bootstrap + authz."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.main import create_app
from fastapi.testclient import TestClient

CUSTOMER_ID = "22222222-2222-2222-2222-222222222222"
OTHER_ID = "33333333-3333-3333-3333-333333333333"
VENDOR_ROLE_ID = "44444444-4444-4444-4444-444444444444"
VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VALID_TOKEN = "valid.jwt.token"


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | None = None

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        _ = columns, count
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
            if "created_at" not in row:
                row["created_at"] = datetime.now(UTC).isoformat()
            if "preferred_badge" not in row:
                row["preferred_badge"] = False
            if "kyc_tier" not in row:
                row["kyc_tier"] = None
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
            rows = sorted(rows, key=lambda row: row.get(column, 0) or 0, reverse=desc)
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


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "vendors": FakeTable(),
            "kyc_records": FakeTable(),
            "audit_log": FakeTable(),
            "notification_outbox": FakeTable(),
            "user_roles": FakeTable(),
            "vendor_listings": FakeTable(),
            "products": FakeTable(),
            "categories": FakeTable(),
            "platform_config": FakeTable(),
            "vendor_quotas": FakeTable(),
        }

    def table(self, name: str) -> FakeTable:
        return self.tables.setdefault(name, FakeTable())


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> FakeSupabaseClient:
    client = FakeSupabaseClient()
    wrapper = MagicMock()
    wrapper.client = client
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: wrapper)
    monkeypatch.setattr("app.routers.kyc.get_supabase_client", lambda: wrapper)
    monkeypatch.setattr("app.routers.vendor_listings.get_supabase_client", lambda: wrapper)
    monkeypatch.setattr(
        "app.services.kyc.state_machine.get_supabase_service_client",
        lambda: wrapper,
    )
    return client


@pytest.fixture
def api_client() -> Generator[TestClient, None, None]:
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        yield client


def _mock_verify(monkeypatch: pytest.MonkeyPatch, user_id: str) -> None:
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": user_id, "exp": 9_999_999_999},
    )


def _mock_roles(monkeypatch: pytest.MonkeyPatch, roles_by_user: dict[str, frozenset[str]]) -> None:
    def fake_load(user_id: str, service_client: Any) -> frozenset[str]:
        _ = service_client
        return roles_by_user.get(user_id, frozenset())

    monkeypatch.setattr("app.core.auth._load_user_roles", fake_load)


def test_customer_can_bootstrap_and_resume_own_draft(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_verify(monkeypatch, CUSTOMER_ID)
    _mock_roles(monkeypatch, {CUSTOMER_ID: frozenset({"customer"})})

    first = api_client.post(
        "/kyc/bootstrap",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={"business_name": "Lusaka Spares", "archetype": "electronics"},
    )
    assert first.status_code == 200
    body = first.json()
    assert body["created"] is True
    assert body["vendor_status"] == "draft"
    assert body["application_status"] == "draft"
    assert body["business_name"] == "Lusaka Spares"
    assert body["archetype"] == "electronics"
    vendor_id = body["vendor_id"]
    assert len(fake_client.tables["vendors"].rows) == 1
    assert fake_client.tables["user_roles"].rows == []

    # Status works for customer without vendor role once draft exists.
    status = api_client.get(
        "/kyc/status",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert status.status_code == 200
    assert status.json()["business_name"] == "Lusaka Spares"

    # Idempotent bootstrap resumes the same draft.
    second = api_client.post(
        "/kyc/bootstrap",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={},
    )
    assert second.status_code == 200
    resumed = second.json()
    assert resumed["created"] is False
    assert resumed["vendor_id"] == vendor_id
    assert len(fake_client.tables["vendors"].rows) == 1
    assert resumed["business_name"] == "Lusaka Spares"


def test_duplicate_bootstrap_is_safe_and_patch_persists_basics(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_verify(monkeypatch, CUSTOMER_ID)
    _mock_roles(monkeypatch, {CUSTOMER_ID: frozenset({"customer"})})

    created = api_client.post(
        "/kyc/bootstrap",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={},
    )
    assert created.status_code == 200
    vendor_id = created.json()["vendor_id"]

    again = api_client.post(
        "/kyc/bootstrap",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={"business_name": "Chipata Market", "archetype": "groceries"},
    )
    assert again.status_code == 200
    assert again.json()["created"] is False
    assert again.json()["vendor_id"] == vendor_id
    assert again.json()["business_name"] == "Chipata Market"
    assert again.json()["archetype"] == "groceries"
    assert len(fake_client.tables["vendors"].rows) == 1

    patched = api_client.patch(
        "/kyc/draft",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={"business_name": "Chipata Fresh", "archetype": "groceries"},
    )
    assert patched.status_code == 200
    assert patched.json()["business_name"] == "Chipata Fresh"
    assert fake_client.tables["vendors"].rows[0]["display_name"] == "Chipata Fresh"


def test_another_user_cannot_access_draft(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_verify(monkeypatch, CUSTOMER_ID)
    _mock_roles(monkeypatch, {CUSTOMER_ID: frozenset({"customer"})})
    owned = api_client.post(
        "/kyc/bootstrap",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={"business_name": "Owner Shop", "archetype": "home"},
    )
    assert owned.status_code == 200
    owner_vendor_id = owned.json()["vendor_id"]

    _mock_verify(monkeypatch, OTHER_ID)
    _mock_roles(monkeypatch, {OTHER_ID: frozenset({"customer"})})

    status = api_client.get(
        "/kyc/status",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert status.status_code == 403

    other_bootstrap = api_client.post(
        "/kyc/bootstrap",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={},
    )
    assert other_bootstrap.status_code == 200
    assert other_bootstrap.json()["vendor_id"] != owner_vendor_id
    assert other_bootstrap.json()["business_name"] is None
    # Owner's row untouched.
    owner_row = next(
        row for row in fake_client.tables["vendors"].rows if row["id"] == owner_vendor_id
    )
    assert owner_row["display_name"] == "Owner Shop"
    assert owner_row["owner_user_id"] == CUSTOMER_ID


def test_draft_customer_cannot_create_listings(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_verify(monkeypatch, CUSTOMER_ID)
    _mock_roles(monkeypatch, {CUSTOMER_ID: frozenset({"customer"})})
    bootstrap = api_client.post(
        "/kyc/bootstrap",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={"business_name": "Pending Seller", "archetype": "other"},
    )
    assert bootstrap.status_code == 200

    listing = api_client.post(
        "/vendor/listings",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={
            "mode": "quick_list",
            "title_override": "Should fail",
            "price_ngwee": 10_000,
            "condition": "new",
            "stock_mode": "always_available",
        },
    )
    assert listing.status_code == 403
    assert fake_client.tables["vendor_listings"].rows == []


def test_approved_active_vendor_status_unchanged(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_verify(monkeypatch, VENDOR_ROLE_ID)
    _mock_roles(monkeypatch, {VENDOR_ROLE_ID: frozenset({"vendor"})})
    fake_client.tables["vendors"].rows.append(
        {
            "id": VENDOR_ID,
            "owner_user_id": VENDOR_ROLE_ID,
            "slug": "active-shop",
            "display_name": "Active Shop",
            "status": "active",
            "kyc_tier": 2,
            "preferred_badge": False,
            "archetype": "electronics",
        }
    )
    fake_client.tables["kyc_records"].rows.append(
        {
            "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
            "vendor_id": VENDOR_ID,
            "tier": 2,
            "status": "approved",
            "doc_storage_paths": ["kyc/nrc.jpg"],
            "momo_name_match": None,
            "reviewer_notes": None,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )

    status_before = api_client.get(
        "/kyc/status",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert status_before.status_code == 200
    before = status_before.json()
    assert before["vendor_status"] == "active"
    assert before["is_auditable_approved"] is True

    bootstrap = api_client.post(
        "/kyc/bootstrap",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={},
    )
    assert bootstrap.status_code == 200
    after = bootstrap.json()
    assert after["created"] is False
    assert after["vendor_id"] == VENDOR_ID
    assert after["vendor_status"] == "active"
    assert after["business_name"] == "Active Shop"
    assert after["is_auditable_approved"] is True
    assert len(fake_client.tables["vendors"].rows) == 1

    # Active vendors cannot mutate business basics via draft patch.
    locked = api_client.patch(
        "/kyc/draft",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={"business_name": "Hijack Name"},
    )
    assert locked.status_code == 409
    assert fake_client.tables["vendors"].rows[0]["display_name"] == "Active Shop"
