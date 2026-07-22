"""Public config read endpoints — commission rates for marketing surfaces."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.main import create_app
from fastapi.testclient import TestClient

SEED_COMMISSION_RATES: list[dict[str, Any]] = [
    {
        "category_key": "default",
        "rate_bps": 800,
        "updated_at": "2026-01-01T00:00:00+00:00",
    },
    {
        "category_key": "electronics",
        "rate_bps": 500,
        "updated_at": "2026-01-02T00:00:00+00:00",
    },
    {
        "category_key": "event_tickets",
        "rate_bps": 500,
        "updated_at": "2026-01-01T00:00:00+00:00",
    },
    {
        "category_key": "fashion_beauty",
        "rate_bps": 1000,
        "updated_at": "2026-01-01T00:00:00+00:00",
    },
    {
        "category_key": "free_events",
        "rate_bps": 0,
        "updated_at": "2026-01-01T00:00:00+00:00",
    },
    {
        "category_key": "groceries",
        "rate_bps": 500,
        "updated_at": "2026-01-01T00:00:00+00:00",
    },
    {
        "category_key": "home",
        "rate_bps": 800,
        "updated_at": "2026-01-01T00:00:00+00:00",
    },
    {
        "category_key": "services",
        "rate_bps": 1200,
        "updated_at": "2026-01-01T00:00:00+00:00",
    },
    {
        "category_key": "supplies",
        "rate_bps": 300,
        "updated_at": "2026-01-01T00:00:00+00:00",
    },
]


class FakeQuery:
    def __init__(self, parent: FakeCommissionRatesTable) -> None:
        self._parent = parent
        self._columns = "*"
        self._order: tuple[str, bool] | None = None

    def select(self, columns: str) -> FakeQuery:
        self._columns = columns
        return self

    def order(self, column: str, *, desc: bool = False) -> FakeQuery:
        self._order = (column, desc)
        return self

    def execute(self) -> MagicMock:
        rows = [dict(row) for row in self._parent.rows]
        if self._order is not None:
            col, desc = self._order
            rows.sort(key=lambda row: row.get(col, ""), reverse=desc)
        return MagicMock(data=rows)


class FakeCommissionRatesTable:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def select(self, columns: str) -> FakeQuery:
        return FakeQuery(self).select(columns)


class FakeSupabaseClient:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    @property
    def client(self) -> MagicMock:
        client = MagicMock()

        def table(name: str) -> FakeCommissionRatesTable:
            if name != "commission_rates":
                raise AssertionError(f"unexpected table: {name}")
            return FakeCommissionRatesTable(self._rows)

        client.table.side_effect = table
        return client


CommissionStore = list[dict[str, Any]]
PublicConfigClientFixture = Generator[tuple[TestClient, CommissionStore], None, None]


@pytest.fixture
def public_config_client(monkeypatch: pytest.MonkeyPatch) -> PublicConfigClientFixture:
    store = [dict(row) for row in SEED_COMMISSION_RATES]
    monkeypatch.setattr(
        "app.deps.get_supabase_service_client",
        lambda: FakeSupabaseClient(store),
    )
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, store


def test_commission_rates_returns_seeded_values_without_auth(
    public_config_client: tuple[TestClient, CommissionStore],
) -> None:
    client, _store = public_config_client
    response = client.get("/public/config/commission-rates")

    assert response.status_code == 200
    body = response.json()
    assert "rates" in body
    assert "updated_at" in body

    by_key = {row["category_key"]: row["rate_pct"] for row in body["rates"]}
    assert by_key["electronics"] == 5
    assert by_key["home"] == 8
    assert by_key["fashion_beauty"] == 10
    assert by_key["services"] == 12
    assert by_key["supplies"] == 3
    assert by_key["free_events"] == 0
    assert len(body["rates"]) == len(SEED_COMMISSION_RATES)


def test_commission_rates_sets_cache_control_header(
    public_config_client: tuple[TestClient, CommissionStore],
) -> None:
    client, _store = public_config_client
    response = client.get("/public/config/commission-rates")

    assert response.status_code == 200
    cache_control = response.headers.get("cache-control", "")
    assert "s-maxage=300" in cache_control


def test_commission_rates_reflects_updated_fixture_row(
    public_config_client: tuple[TestClient, CommissionStore],
) -> None:
    client, store = public_config_client
    updated_at = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)
    for row in store:
        if row["category_key"] == "electronics":
            row["rate_bps"] = 650
            row["updated_at"] = updated_at.isoformat()
            break

    response = client.get("/public/config/commission-rates")
    assert response.status_code == 200

    body = response.json()
    electronics = next(
        row for row in body["rates"] if row["category_key"] == "electronics"
    )
    assert electronics["rate_pct"] == 6.5
    assert datetime.fromisoformat(body["updated_at"].replace("Z", "+00:00")) == updated_at
