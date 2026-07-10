"""M12-P08 vendor payouts view — balances, method hold, statement, authz."""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from app.deps import get_supabase_client
from app.errors import AppError
from app.main import create_app
from app.routers.vendor_payouts import (
    compute_vendor_balances,
    generate_vendor_statement_csv,
    vendor_escrow_held_ngwee,
    vendor_paid_out_ngwee,
)
from app.services.kyc.name_match import MomoNameMatchResult
from app.services.orders.audit import SqlResult
from app.services.payouts.execution import execute_vendor_payout
from app.services.payouts.resolve_check import VendorPayoutProfile
from fastapi.testclient import TestClient

USER_A_ID = "11111111-1111-1111-1111-111111111111"
USER_B_ID = "22222222-2222-2222-2222-222222222222"
VENDOR_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VENDOR_B_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
TOKEN_A = "vendor-a-token"
TOKEN_B = "vendor-b-token"
MIGRATION_0021 = (
    Path(__file__).resolve().parents[3] / "supabase/migrations/0021_vendor_payout_method.sql"
)


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | list[dict[str, Any]] | None = None
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._in_filters: list[tuple[str, list[Any]]] = []

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        _ = count
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._in_filters.append((column, values))
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
                row["id"] = str(uuid4())
            self._parent.rows.append(row)
            return MagicMock(data=[row], count=None)

        if self._pending_op == "update":
            assert isinstance(self._payload, dict)
            updated: list[dict[str, Any]] = []
            for row in self._parent.rows:
                if self._matches(row):
                    row.update(self._payload)
                    updated.append(dict(row))
            return MagicMock(data=updated[0] if updated else None, count=len(updated))

        rows = self._filtered_rows()
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: row.get(column, ""), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None, count=len(rows))
        return MagicMock(data=rows, count=len(rows))

    def _matches(self, row: dict[str, Any]) -> bool:
        for op, column, value in self._filters:
            if op == "eq" and row.get(column) != value:
                return False
        for column, values in self._in_filters:
            if row.get(column) not in values:
                return False
        return True

    def _filtered_rows(self) -> list[dict[str, Any]]:
        rows = list(self._parent.rows)
        for op, column, value in self._filters:
            if op == "eq":
                rows = [row for row in rows if row.get(column) == value]
        for column, values in self._in_filters:
            allowed = set(values)
            rows = [row for row in rows if row.get(column) in allowed]
        return rows


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self, []).select(columns, count=count)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).insert(payload)

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).update(payload)


class FakeRpc:
    def __init__(self, results: dict[str, list[dict[str, Any]]]) -> None:
        self._results = results
        self._fn: str | None = None
        self._params: dict[str, Any] | None = None

    def __call__(self, fn: str, params: dict[str, Any]) -> FakeRpc:
        self._fn = fn
        self._params = params
        return self

    def execute(self) -> MagicMock:
        key = f"{self._params.get('p_scope')}|{self._params.get('p_key')}"
        rows = self._results.get(key, [{"allowed": True, "retry_after_seconds": 0}])
        return MagicMock(data=rows)


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "vendors": FakeTable(),
            "kyc_records": FakeTable(),
            "profiles": FakeTable(),
            "payouts": FakeTable(),
            "notification_outbox": FakeTable(),
        }
        self.rpc_results: dict[str, list[dict[str, Any]]] = {}

    def table(self, name: str) -> FakeTable:
        return self.tables[name]

    def rpc(self, fn: str, params: dict[str, Any]) -> FakeRpc:
        return FakeRpc(self.rpc_results)(fn, params)


def _seed_vendors(fake: FakeSupabaseClient) -> None:
    fake.tables["vendors"].rows.extend(
        [
            {
                "id": VENDOR_A_ID,
                "owner_user_id": USER_A_ID,
                "status": "active",
                "payout_msisdn": None,
                "payout_rail": None,
                "payout_hold_until": None,
            },
            {
                "id": VENDOR_B_ID,
                "owner_user_id": USER_B_ID,
                "status": "active",
                "payout_msisdn": None,
                "payout_rail": None,
                "payout_hold_until": None,
            },
        ]
    )


def _seed_kyc(fake: FakeSupabaseClient, *, vendor_id: str) -> None:
    fake.tables["kyc_records"].rows.append(
        {
            "vendor_id": vendor_id,
            "status": "approved",
            "momo_name_match": {
                "phone": "0977123456",
                "operator": "mtn",
                "legal_name": "Chanda Mwansa",
            },
            "created_at": datetime.now(UTC).isoformat(),
        }
    )


def _seed_profile(fake: FakeSupabaseClient, *, user_id: str, phone: str) -> None:
    fake.tables["profiles"].rows.append({"id": user_id, "phone": phone})


@pytest.fixture
def fake_client() -> FakeSupabaseClient:
    client = FakeSupabaseClient()
    _seed_vendors(client)
    _seed_kyc(client, vendor_id=VENDOR_A_ID)
    _seed_kyc(client, vendor_id=VENDOR_B_ID)
    _seed_profile(client, user_id=USER_A_ID, phone="+260977123456")
    _seed_profile(client, user_id=USER_B_ID, phone="+260977654321")
    return client


@pytest.fixture
def api_client(fake_client: FakeSupabaseClient) -> Generator[TestClient, None, None]:
    app = create_app()
    service_wrapper = MagicMock()
    service_wrapper.client = fake_client

    def _override() -> MagicMock:
        return service_wrapper

    app.dependency_overrides[get_supabase_client] = _override

    with patch(
        "app.core.auth.verify_supabase_jwt",
        side_effect=lambda token, settings: {
            TOKEN_A: {"sub": USER_A_ID, "exp": 9_999_999_999},
            TOKEN_B: {"sub": USER_B_ID, "exp": 9_999_999_999},
        }[token],
    ), patch(
        "app.core.auth._load_user_roles",
        side_effect=lambda user_id, service_client: (
            frozenset({"vendor"}) if user_id in {USER_A_ID, USER_B_ID} else frozenset()
        ),
    ), patch(
        "app.deps.get_supabase_service_client",
        return_value=service_wrapper,
    ), patch(
        "app.supabase_client.get_supabase_service_client",
        return_value=service_wrapper,
    ):
        with TestClient(app) as client:
            yield client

    app.dependency_overrides.clear()


def test_migration_0021_is_additive_and_reversible() -> None:
    text = MIGRATION_0021.read_text(encoding="utf-8")
    assert "add column if not exists payout_msisdn" in text
    assert "add column if not exists payout_rail" in text
    assert "add column if not exists payout_hold_until" in text
    assert "Reversible:" in text
    assert "drop column if exists payout_msisdn" in text


def test_balance_derivation_matches_ledger_accounts(fake_client: FakeSupabaseClient) -> None:
    with (
        patch(
            "app.routers.vendor_payouts.vendor_escrow_held_ngwee",
            return_value=250_000,
        ),
        patch(
            "app.routers.vendor_payouts.vendor_paid_out_ngwee",
            return_value=75_000,
        ),
        patch(
            "app.routers.vendor_payouts.compute_eligibility",
            return_value=MagicMock(available_ngwee=125_000),
        ),
        patch(
            "app.routers.vendor_payouts.vendor_payable_ledger_balance_ngwee",
            return_value=-125_000,
        ),
    ):
        balances = compute_vendor_balances(
            fake_client,
            vendor_id=VENDOR_A_ID,
            payout_msisdn=None,
            payout_rail=None,
            payout_hold_until=None,
        )

    assert balances.escrow_held_ngwee == 250_000
    assert balances.released_available_ngwee == 125_000
    assert balances.paid_out_ngwee == 75_000
    assert balances.payouts_blocked is False
    assert balances.released_available_ngwee == 125_000


def test_method_change_sets_hold_and_blocks_payout(
    fake_client: FakeSupabaseClient,
    api_client: TestClient,
) -> None:
    hold_until = (datetime.now(UTC) + timedelta(hours=24)).isoformat()
    for row in fake_client.tables["vendors"].rows:
        if row["id"] == VENDOR_A_ID:
            row["payout_hold_until"] = hold_until
            row["payout_msisdn"] = "0977999888"
            row["payout_rail"] = "mtn"

    with (
        patch("app.routers.vendor_payouts.vendor_escrow_held_ngwee", return_value=0),
        patch("app.routers.vendor_payouts.vendor_paid_out_ngwee", return_value=0),
        patch(
            "app.routers.vendor_payouts.compute_eligibility",
            return_value=MagicMock(available_ngwee=0),
        ),
    ):
        response = api_client.get(
            "/vendor/payouts",
            headers={"Authorization": f"Bearer {TOKEN_A}"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["payouts_blocked"] is True
    assert body["payout_hold_until"] == hold_until

    profile = VendorPayoutProfile(
        vendor_id=VENDOR_A_ID,
        owner_user_id=USER_A_ID,
        phone="0977123456",
        operator="mtn",
        legal_name="Chanda Mwansa",
        rail="mtn",
    )

    with patch(
        "app.services.payouts.execution.load_vendor_payout_profile",
        return_value=profile,
    ), patch(
        "app.services.payouts.execution.compute_amount_and_eligibility",
        return_value=MagicMock(amount_ngwee=10_000, deferred=False),
    ):
        with pytest.raises(AppError) as exc:
            wrapper = MagicMock()
            wrapper.client = fake_client
            asyncio.run(
                execute_vendor_payout(
                    wrapper,
                    vendor_id=VENDOR_A_ID,
                    resolve_account=AsyncMock(),
                    initiate_momo_payout=AsyncMock(),
                    initiate_bank_payout=AsyncMock(),
                )
            )
    assert exc.value.code == "payout_method_held"


def test_method_change_emits_notification(
    fake_client: FakeSupabaseClient,
    api_client: TestClient,
) -> None:
    with (
        patch("app.routers.vendor_payouts.verify_reauth_otp", return_value=None),
        patch(
            "app.routers.vendor_payouts.resolve_and_score_momo_name",
            new_callable=AsyncMock,
            return_value=MomoNameMatchResult(
                phone="0977888777",
                operator="mtn",
                resolved_name="Chanda Mwansa",
                legal_name="Chanda Mwansa",
                match_score=1.0,
                matched=True,
                recorded_at=datetime.now(UTC).isoformat(),
                raw={},
            ),
        ),
    ):
        response = api_client.post(
            "/vendor/payouts/method",
            headers={"Authorization": f"Bearer {TOKEN_A}"},
            json={
                "payout_msisdn": "0977888777",
                "payout_rail": "mtn",
                "otp": "123456",
            },
        )

    assert response.status_code == 200
    vendor_row = next(row for row in fake_client.tables["vendors"].rows if row["id"] == VENDOR_A_ID)
    assert vendor_row["payout_msisdn"] == "0977888777"
    assert vendor_row["payout_rail"] == "mtn"
    assert vendor_row["payout_hold_until"] is not None

    outbox = fake_client.tables["notification_outbox"].rows
    assert any(
        row.get("template") == "payout_method_changed"
        or str(row.get("dedupe_key", "")).startswith("payout_method_changed:")
        for row in outbox
    )


def test_statement_generation_ngwee_exact() -> None:
    with patch(
        "app.routers.vendor_payouts.run_sql_script",
        return_value=SqlResult(
            ok=True,
            rows=[
                "2026-07-05T10:00:00+00:00|release_to_vendor|ord-1||50000",
                "2026-07-12T11:00:00+00:00|payout_executed||pay-1|-30000",
            ],
        ),
    ):
        csv_text = generate_vendor_statement_csv(vendor_id=VENDOR_A_ID, month="2026-07")

    assert "release_to_vendor" in csv_text
    assert "50000" in csv_text
    assert "-30000" in csv_text
    lines = [line for line in csv_text.strip().splitlines() if line]
    assert lines[0] == "date,kind,order_id,payout_id,amount_ngwee"
    assert lines[1].endswith("50000")
    assert lines[2].endswith("-30000")


def test_authz_cross_vendor_rejected(
    api_client: TestClient,
    fake_client: FakeSupabaseClient,
) -> None:
    response = api_client.get(
        "/vendor/payouts/history",
        headers={"Authorization": f"Bearer {TOKEN_B}"},
    )
    assert response.status_code == 200
    assert response.json()["items"] == []

    fake_client.tables["payouts"].rows.append(
        {
            "id": str(uuid4()),
            "vendor_id": VENDOR_A_ID,
            "amount_ngwee": 50_000,
            "rail": "mtn",
            "status": "paid",
            "lenco_reference": "pay-test-1",
            "created_at": datetime.now(UTC).isoformat(),
        }
    )

    response_b = api_client.get(
        "/vendor/payouts/history",
        headers={"Authorization": f"Bearer {TOKEN_B}"},
    )
    assert response_b.status_code == 200
    assert response_b.json()["items"] == []

    response_a = api_client.get(
        "/vendor/payouts/history",
        headers={"Authorization": f"Bearer {TOKEN_A}"},
    )
    assert response_a.status_code == 200
    assert len(response_a.json()["items"]) == 1


def test_vendor_escrow_and_paid_out_sql_seams() -> None:
    with patch(
        "app.routers.vendor_payouts.run_sql_script",
        side_effect=[
            SqlResult(ok=True, rows=["150000"]),
            SqlResult(ok=True, rows=["90000"]),
        ],
    ):
        assert vendor_escrow_held_ngwee(VENDOR_A_ID) == 150_000
        assert vendor_paid_out_ngwee(VENDOR_A_ID) == 90_000
