from __future__ import annotations

import copy
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.main import create_app
from fastapi.testclient import TestClient

USER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_USER_ID = "22222222-2222-2222-2222-222222222222"
VALID_TOKEN = "valid.jwt.token"

PARENT_ID = "c0000001-0000-4000-8000-000000000001"
CHILD_ID = "d0000001-0000-4000-8000-000000000001"
OTHER_PARENT_ID = "c0000002-0000-4000-8000-000000000002"


@pytest.fixture
def config_app() -> Any:
    return create_app()


@pytest.fixture
def config_client(config_app: Any) -> Generator[TestClient, None, None]:
    with TestClient(config_app, raise_server_exceptions=False) as test_client:
        yield test_client


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


class FakeConfigStore:
    def __init__(self) -> None:
        self.commission_rates: list[dict[str, Any]] = [
            {"category_key": "electronics", "rate_bps": 500},
            {"category_key": "default", "rate_bps": 800},
        ]
        self.delivery_zones: list[dict[str, Any]] = [
            {
                "zone_key": "lusaka_a",
                "label": "Lusaka Band A",
                "fee_ngwee": 3000,
                "active": True,
            }
        ]
        self.platform_config: list[dict[str, Any]] = [
            {
                "key": "cod_cap_ngwee",
                "value": 50000,
                "description": "COD cap",
            },
            {
                "key": "release_after_delivered_hours",
                "value": 48,
                "description": "Release hours",
            },
        ]
        self.feature_flags: list[dict[str, Any]] = [
            {"flag": "wallet", "enabled": False, "description": "Wallet"},
        ]
        self.categories: list[dict[str, Any]] = [
            {
                "id": PARENT_ID,
                "parent_id": None,
                "name": "Groceries",
                "slug": "groceries-staples",
                "path": "groceries-staples",
                "commission_key": "groceries",
                "prohibited": False,
                "position": 0,
            },
            {
                "id": CHILD_ID,
                "parent_id": PARENT_ID,
                "name": "Rice",
                "slug": "rice-grains",
                "path": "groceries-staples/rice-grains",
                "commission_key": "groceries",
                "prohibited": False,
                "position": 0,
            },
            {
                "id": OTHER_PARENT_ID,
                "parent_id": None,
                "name": "Electronics",
                "slug": "electronics",
                "path": "electronics",
                "commission_key": "electronics",
                "prohibited": False,
                "position": 1,
            },
        ]
        self.orders: list[dict[str, Any]] = [
            {
                "id": "o0000001-0000-4000-8000-000000000001",
                "commission_snapshot": {"rate_bps": 500},
            }
        ]

    def table(self, name: str) -> FakeTableQuery:
        return FakeTableQuery(self, name)


class FakeTableQuery:
    def __init__(self, store: FakeConfigStore, name: str) -> None:
        self._store = store
        self._name = name
        self._filters: list[tuple[str, Any]] = []
        self._in_filter: tuple[str, list[Any]] | None = None
        self._update_payload: dict[str, Any] | None = None
        self._order_key: str | None = None

    def select(self, _columns: str) -> FakeTableQuery:
        return self

    def order(self, key: str) -> FakeTableQuery:
        self._order_key = key
        return self

    def eq(self, key: str, value: Any) -> FakeTableQuery:
        self._filters.append((key, value))
        return self

    def in_(self, key: str, values: list[Any]) -> FakeTableQuery:
        self._in_filter = (key, values)
        return self

    def update(self, payload: dict[str, Any]) -> FakeTableQuery:
        self._update_payload = payload
        return self

    def _rows(self) -> list[dict[str, Any]]:
        if self._name == "commission_rates":
            return copy.deepcopy(self._store.commission_rates)
        if self._name == "delivery_zones":
            return copy.deepcopy(self._store.delivery_zones)
        if self._name == "platform_config":
            return copy.deepcopy(self._store.platform_config)
        if self._name == "feature_flags":
            return copy.deepcopy(self._store.feature_flags)
        if self._name == "categories":
            return copy.deepcopy(self._store.categories)
        if self._name == "orders":
            return copy.deepcopy(self._store.orders)
        return []

    def _apply_filters(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        filtered = rows
        if self._in_filter is not None:
            key, values = self._in_filter
            filtered = [row for row in filtered if row.get(key) in values]
        for key, value in self._filters:
            filtered = [row for row in filtered if str(row.get(key)) == str(value)]
        if self._order_key:
            filtered = sorted(filtered, key=lambda row: row.get(self._order_key or "", ""))
        return filtered

    def execute(self) -> MagicMock:
        rows = self._rows()
        if self._update_payload is not None:
            updated: list[dict[str, Any]] = []
            source = self._source_table()
            for row in source:
                if any(str(row.get(k)) == str(v) for k, v in self._filters):
                    row.update(self._update_payload)
                    updated.append(copy.deepcopy(row))
            return MagicMock(data=updated)

        filtered = self._apply_filters(rows)
        return MagicMock(data=filtered)

    def _source_table(self) -> list[dict[str, Any]]:
        if self._name == "commission_rates":
            return self._store.commission_rates
        if self._name == "delivery_zones":
            return self._store.delivery_zones
        if self._name == "platform_config":
            return self._store.platform_config
        if self._name == "feature_flags":
            return self._store.feature_flags
        if self._name == "categories":
            return self._store.categories
        if self._name == "orders":
            return self._store.orders
        return []


@pytest.fixture
def config_store(monkeypatch: pytest.MonkeyPatch) -> FakeConfigStore:
    store = FakeConfigStore()
    audit_rows: list[dict[str, Any]] = []

    class FakeAuditQuery:
        def __init__(self, row: dict[str, Any]) -> None:
            self._row = row

        def execute(self) -> MagicMock:
            audit_rows.append(self._row)
            return MagicMock(data=[{**self._row, "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}])

    class FakeAuditTable:
        def insert(self, row: dict[str, Any]) -> FakeAuditQuery:
            return FakeAuditQuery(row)

    class FakeServiceClient:
        def __init__(self) -> None:
            self.client = MagicMock()
            self.audit_rows = audit_rows

            def table(name: str) -> Any:
                if name == "audit_log":
                    return FakeAuditTable()
                return store.table(name)

            self.client.table.side_effect = table

    service_client = FakeServiceClient()
    store.audit_rows = audit_rows  # type: ignore[attr-defined]
    monkeypatch.setattr(
        "app.deps.get_supabase_service_client",
        lambda: service_client,
    )
    monkeypatch.setattr(
        "app.core.admin_audit.get_supabase_service_client",
        lambda: service_client,
    )
    return store


def _admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {VALID_TOKEN}"}


# ---------------------------------------------------------------------------
# Validation bounds
# ---------------------------------------------------------------------------
def test_rate_bps_above_2000_rejected(
    config_client: TestClient,
    config_store: FakeConfigStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"admin"})})

    response = config_client.patch(
        "/admin/config/commissions/electronics",
        headers=_admin_headers(),
        json={"rate_bps": 2500},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert config_store.commission_rates[0]["rate_bps"] == 500


def test_negative_ngwee_rejected(
    config_client: TestClient,
    config_store: FakeConfigStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"admin"})})
    _mock_audit_insert(monkeypatch)

    response = config_client.patch(
        "/admin/config/delivery-zones/lusaka_a",
        headers=_admin_headers(),
        json={"fee_ngwee": -100},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert config_store.delivery_zones[0]["fee_ngwee"] == 3000


def test_bad_release_window_rejected(
    config_client: TestClient,
    config_store: FakeConfigStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"admin"})})
    _mock_audit_insert(monkeypatch)

    response = config_client.patch(
        "/admin/config/platform/release_after_delivered_hours",
        headers=_admin_headers(),
        json={"value": 999},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert config_store.platform_config[1]["value"] == 48


# ---------------------------------------------------------------------------
# Category tree integrity
# ---------------------------------------------------------------------------
def test_move_parent_without_children_prompt_rejected(
    config_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    config_store: FakeConfigStore,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"admin"})})

    response = config_client.patch(
        f"/admin/config/categories/{PARENT_ID}",
        headers=_admin_headers(),
        json={"parent_id": OTHER_PARENT_ID, "move_children": False},
    )

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "orphan_children"
    assert CHILD_ID in body["error"]["details"]["child_ids"]
    assert config_store.categories[0]["parent_id"] is None


def test_move_parent_with_children_succeeds(
    config_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    config_store: FakeConfigStore,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"admin"})})

    response = config_client.patch(
        f"/admin/config/categories/{PARENT_ID}",
        headers=_admin_headers(),
        json={"parent_id": OTHER_PARENT_ID, "move_children": True},
    )

    assert response.status_code == 200
    parent = next(row for row in config_store.categories if row["id"] == PARENT_ID)
    child = next(row for row in config_store.categories if row["id"] == CHILD_ID)
    assert parent["parent_id"] == OTHER_PARENT_ID
    assert parent["path"] == "electronics/groceries-staples"
    assert child["path"] == "electronics/groceries-staples/rice-grains"


# ---------------------------------------------------------------------------
# Audit diff
# ---------------------------------------------------------------------------
def test_commission_mutation_writes_audit_diff(
    config_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    config_store: FakeConfigStore,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"admin"})})

    response = config_client.patch(
        "/admin/config/commissions/electronics",
        headers=_admin_headers(),
        json={"rate_bps": 600},
    )

    assert response.status_code == 200
    inserted = config_store.audit_rows  # type: ignore[attr-defined]
    assert len(inserted) == 1
    audit_row = inserted[0]
    assert audit_row["action"] == "config.commission.update"
    assert audit_row["entity_type"] == "commission_rate"
    assert audit_row["before"]["rate_bps"] == 500
    assert audit_row["after"]["rate_bps"] == 600
    assert config_store.commission_rates[0]["rate_bps"] == 600


# ---------------------------------------------------------------------------
# Non-admin 403
# ---------------------------------------------------------------------------
def test_non_admin_config_mutation_returns_403(
    config_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_verify(monkeypatch, user_id=OTHER_USER_ID)
    _mock_roles(monkeypatch, {OTHER_USER_ID: frozenset({"vendor"})})

    response = config_client.patch(
        "/admin/config/commissions/electronics",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={"rate_bps": 600},
    )

    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "forbidden"


# ---------------------------------------------------------------------------
# Snapshot immunity (M08-P12 integration point)
# ---------------------------------------------------------------------------
def test_commission_change_does_not_alter_order_snapshots(
    config_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    config_store: FakeConfigStore,
) -> None:
    """Commission rates are snapshotted onto orders at checkout (orders.commission_snapshot).

    Admin config edits update commission_rates only — existing order snapshots stay immutable.
  Integration: M08-P12 commissions/engine.py reads snapshot, not live config.
    """
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"admin"})})
    _mock_audit_insert(monkeypatch)

    original_snapshot = copy.deepcopy(config_store.orders[0]["commission_snapshot"])

    response = config_client.patch(
        "/admin/config/commissions/electronics",
        headers=_admin_headers(),
        json={"rate_bps": 1500},
    )

    assert response.status_code == 200
    assert config_store.commission_rates[0]["rate_bps"] == 1500
    assert config_store.orders[0]["commission_snapshot"] == original_snapshot
    assert config_store.orders[0]["commission_snapshot"]["rate_bps"] == 500
