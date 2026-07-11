"""Founder digest endpoint tests — internal-token guard + aggregate correctness (M13-P11)."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from app.main import create_app
from app.routers.internal_digest import build_digest
from fastapi.testclient import TestClient

INTERNAL_TOKEN = "test-digest-token"
DIGEST_PATH = "/internal/digest"
REPORT_ID = "77777777-7777-7777-7777-777777777777"


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._maybe_single = False
        self._count: str | None = None

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        self._count = count
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
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

    def execute(self) -> MagicMock:
        rows = [row for row in self._parent.rows if self._row_matches(row)]
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: str(row.get(column, "")), reverse=desc)
        total = len(rows)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None, count=total)
        return MagicMock(data=rows, count=total)

    def _row_matches(self, row: dict[str, Any]) -> bool:
        for op, column, value in self._filters:
            if op == "eq" and row.get(column) != value:
                return False
        return True


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self, []).select(columns, count=count)


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {}

    def table(self, name: str) -> FakeTable:
        if name not in self.tables:
            self.tables[name] = FakeTable()
        return self.tables[name]


def _seed_digest_fixtures(fake: FakeSupabaseClient) -> None:
    fake.table("orders").rows.extend(
        [
            {"id": "o1", "status": "placed"},
            {"id": "o2", "status": "completed"},
            {"id": "o3", "status": "cancelled"},
            {"id": "o4", "status": "shipped"},
        ]
    )
    fake.table("payouts").rows.extend(
        [
            {"id": "py1", "status": "pending", "amount_ngwee": 40_000},
            {"id": "py2", "status": "pending", "amount_ngwee": 10_000},
            {"id": "py3", "status": "paid", "amount_ngwee": 99_999},
        ]
    )
    fake.table("kyc_records").rows.extend(
        [
            {"id": "k1", "status": "pending"},
            {"id": "k2", "status": "pending"},
            {"id": "k3", "status": "approved"},
        ]
    )
    fake.table("flags").rows.extend(
        [
            {"id": "f1", "status": "open"},
            {"id": "f2", "status": "actioned"},
        ]
    )
    fake.table("reconciliation_reports").rows.append(
        {
            "id": REPORT_ID,
            "report_date": "2026-07-10",
            "summary": {"clean": True},
            "discrepancies": {"balance_diff_ngwee": 0, "orphaned_lenco": [], "ledger_only": []},
        }
    )


@pytest.fixture
def digest_client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("INTERNAL_DIGEST_TOKEN", INTERNAL_TOKEN)
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def fake_service(monkeypatch: pytest.MonkeyPatch) -> FakeSupabaseClient:
    fake = FakeSupabaseClient()
    wrapper = MagicMock()
    wrapper.client = fake
    monkeypatch.setattr(
        "app.routers.internal_digest.get_supabase_client",
        lambda: iter([wrapper]),
    )
    return fake


def _auth_headers() -> dict[str, str]:
    return {"X-Internal-Token": INTERNAL_TOKEN}


def test_digest_requires_token(digest_client: TestClient) -> None:
    assert digest_client.post(DIGEST_PATH).status_code == 401
    wrong = digest_client.post(DIGEST_PATH, headers={"X-Internal-Token": "nope"})
    assert wrong.status_code == 401


def test_digest_aggregates_match_fixtures(
    digest_client: TestClient,
    fake_service: FakeSupabaseClient,
) -> None:
    _seed_digest_fixtures(fake_service)
    with patch("app.routers.internal_digest.compute_gmv_ngwee", return_value=72_000):
        response = digest_client.post(DIGEST_PATH, headers=_auth_headers())

    assert response.status_code == 200
    body = response.json()
    assert body["gmv_ngwee"] == 72_000
    assert body["orders"]["total"] == 4
    assert body["orders"]["by_status"]["placed"] == 1
    assert body["orders"]["by_status"]["completed"] == 1
    assert body["orders"]["by_status"]["shipped"] == 1
    assert body["orders"]["by_status"]["cancelled"] == 1
    assert body["payouts_due"]["count"] == 2
    assert body["payouts_due"]["amount_ngwee"] == 50_000
    assert body["reconciliation"]["status"] == "green"
    assert body["reconciliation"]["has_mismatch"] is False
    assert body["reconciliation"]["report_id"] == REPORT_ID
    assert body["kyc_queue_depth"] == 2
    assert body["flags_pending"] == 1


def test_build_digest_flags_reconciliation_mismatch(fake_service: FakeSupabaseClient) -> None:
    _seed_digest_fixtures(fake_service)
    fake_service.table("reconciliation_reports").rows[0]["discrepancies"] = {
        "balance_diff_ngwee": 5_000,
        "orphaned_lenco": [{"reference": "ord-bad"}],
        "ledger_only": [],
    }
    wrapper = MagicMock()
    wrapper.client = fake_service
    with patch("app.routers.internal_digest.compute_gmv_ngwee", return_value=0):
        digest = build_digest(wrapper)

    assert digest.reconciliation.status == "red"
    assert digest.reconciliation.has_mismatch is True
    assert digest.payouts_due.amount_ngwee == 50_000
