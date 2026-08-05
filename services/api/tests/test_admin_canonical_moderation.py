"""Admin canonical product moderation endpoints (Day 35–36)."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.main import create_app
from app.routers.admin_products import transition_canonical_moderation
from fastapi.testclient import TestClient

MODERATOR_ID = "11111111-1111-1111-1111-111111111111"
PRODUCT_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
LISTING_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
VENDOR_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
CATEGORY_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
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

    def delete(self) -> FakeQuery:
        self._pending_op = "delete"
        return self

    def execute(self) -> MagicMock:
        if self._pending_op == "update":
            assert isinstance(self._payload, dict)
            updated: list[dict[str, Any]] = []
            for row in self._parent.rows:
                if self._matches(row):
                    row.update(self._payload)
                    updated.append(dict(row))
            return MagicMock(data=updated)

        if self._pending_op == "delete":
            remaining: list[dict[str, Any]] = []
            deleted: list[dict[str, Any]] = []
            for row in self._parent.rows:
                if self._matches(row):
                    deleted.append(dict(row))
                else:
                    remaining.append(row)
            self._parent.rows[:] = remaining
            return MagicMock(data=deleted)

        rows = self._apply_filters(self._parent.rows)
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: row.get(column, ""), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=rows)

    def _matches(self, row: dict[str, Any]) -> bool:
        for op, column, value in self._filters:
            if op == "eq" and row.get(column) != value:
                return False
            if op == "in" and row.get(column) not in set(value):
                return False
        return True

    def _apply_filters(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [row for row in rows if self._matches(row)]


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self, []).select(columns, count=count)

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).update(payload)

    def delete(self) -> FakeQuery:
        return FakeQuery(self, []).delete()


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "products": FakeTable(),
            "vendor_listings": FakeTable(),
            "listing_images": FakeTable(),
            "audit_log": FakeTable(),
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
    monkeypatch.setattr("app.routers.admin_products.get_supabase_client", lambda: wrapper)
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


def _seed_pending_product(fake: FakeSupabaseClient) -> None:
    now = datetime.now(UTC).isoformat()
    fake.tables["products"].rows.append(
        {
            "id": PRODUCT_ID,
            "name": "Test Phone",
            "slug": "test-phone",
            "brand": "Tecno",
            "category_id": CATEGORY_ID,
            "status": "pending_moderation",
            "aliases": [],
            "merged_into_id": None,
            "updated_at": now,
        }
    )
    fake.tables["vendor_listings"].rows.append(
        {
            "id": LISTING_ID,
            "vendor_id": VENDOR_ID,
            "product_id": PRODUCT_ID,
            "status": "draft",
            "created_at": now,
            "vendors": {"display_name": "Acme Shop"},
        }
    )
    fake.tables["listing_images"].rows.append(
        {
            "listing_id": LISTING_ID,
            "cloudinary_public_id": "vergeo5/products/phone-1",
            "position": 0,
        }
    )


def test_list_pending_canonical_products(
    api_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_auth(monkeypatch, frozenset({"moderator"}))
    _seed_pending_product(fake_client)
    monkeypatch.setattr(
        "app.routers.admin_products.get_settings",
        lambda: MagicMock(cloudinary_cloud_name="demo"),
    )

    response = api_client.get(
        "/admin/products/canonical?status=pending_moderation",
        headers=_auth_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == PRODUCT_ID
    assert body[0]["image_urls"]


def test_patch_canonical_approve_activates_product(
    api_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_auth(monkeypatch, frozenset({"superadmin"}))
    _mock_audit_insert(monkeypatch)
    _seed_pending_product(fake_client)

    response = api_client.patch(
        f"/admin/products/canonical/{PRODUCT_ID}/status",
        headers=_auth_headers(),
        json={"status": "active"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "active"
    assert fake_client.tables["products"].rows[0]["status"] == "active"
    assert fake_client.tables["vendor_listings"].rows[0]["status"] == "active"


def test_patch_canonical_reject_requires_reason(
    api_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_auth(monkeypatch, frozenset({"moderator"}))
    _mock_audit_insert(monkeypatch)
    _seed_pending_product(fake_client)

    response = api_client.patch(
        f"/admin/products/canonical/{PRODUCT_ID}/status",
        headers=_auth_headers(),
        json={"status": "rejected"},
    )
    assert response.status_code == 422


def test_transition_canonical_reject_deletes_product(fake_client: FakeSupabaseClient) -> None:
    _seed_pending_product(fake_client)
    wrapper = MagicMock()
    wrapper.client = fake_client
    result, idempotent = transition_canonical_moderation(
        product_id=PRODUCT_ID,
        target_status="rejected",
        reason="Duplicate of existing SKU",
        service_client=wrapper,
    )
    assert idempotent is False
    assert result["status"] == "rejected"
    assert fake_client.tables["products"].rows == []
    assert fake_client.tables["vendor_listings"].rows[0]["status"] == "removed"


def test_canonical_endpoints_forbid_vendor(
    api_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_auth(monkeypatch, frozenset({"vendor"}))
    _seed_pending_product(fake_client)

    assert (
        api_client.get(
            "/admin/products/canonical?status=pending_moderation",
            headers=_auth_headers(),
        ).status_code
        == 403
    )
