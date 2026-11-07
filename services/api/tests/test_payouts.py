"""M08-P09 payout tests — balance race, resolve-mismatch, retry, velocity caps."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Generator
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.errors import AppError
from app.main import create_app
from app.services.payments.base import (
    InitiatePayoutResult,
    ProviderOutcome,
    ProviderResult,
    ResolveAccountResult,
    TransferStatus,
)
from app.services.payments.money import ngwee_to_major_str
from app.services.payouts.eligibility import (
    _vendor_lock,
    assert_payout_eligible,
    check_payout_eligible_unlocked,
    compute_eligibility,
)
from app.services.payouts.execution import (
    PayoutOutcome,
    _insert_payout_row,
    execute_vendor_payout,
)
from app.services.payouts.obligation import PayoutObservationMismatch
from app.services.payouts.resolve_check import VendorPayoutProfile, run_resolve_name_check
from app.services.payouts.retry import retry_payout_row, retry_pending_payouts
from app.services.refunds.payout_port import initiate_customer_refund_payout
from fastapi.testclient import TestClient

VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
OWNER_ID = "11111111-1111-1111-1111-111111111111"
RELEASED_NGWEE = 100_000


def _momo_obligation(
    reference: str,
    amount_ngwee: int,
    phone: str,
    operator: str,
) -> dict[str, Any]:
    return {
        "merchant_reference": reference,
        "amount_ngwee": amount_ngwee,
        "currency": "ZMW",
        "debit_account_id": "lenco-acct-1",
        "destination": {
            "type": "mobile-money",
            "phone": phone,
            "operator": operator,
        },
    }


def _processing_payout_row(
    *,
    reference: str,
    amount_ngwee: int = 30_000,
    phone: str = "0961111111",
    operator: str = "mtn",
) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "vendor_id": VENDOR_ID,
        "amount_ngwee": amount_ngwee,
        "rail": operator,
        "lenco_reference": reference,
        "status": "processing",
        "resolve_snapshot": {
            "matched": True,
            "obligation": _momo_obligation(
                reference,
                amount_ngwee,
                phone,
                operator,
            ),
            "dispatch": {"state": "pending"},
        },
    }


def _fake_column_value(row: dict[str, Any], column: str) -> Any:
    """Model the one JSON-path equality used by the real PostgREST claim."""
    if column == "resolve_snapshot->dispatch->>state":
        snapshot = row.get("resolve_snapshot")
        dispatch = snapshot.get("dispatch") if isinstance(snapshot, dict) else None
        return dispatch.get("state") if isinstance(dispatch, dict) else None
    return row.get(column)


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | list[dict[str, Any]] | None = None
        self._count_exact = False

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        if count == "exact":
            self._count_exact = True
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._filters.append(("in", column, values))
        return self

    def gte(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("gte", column, value))
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
                row["id"] = str(uuid.uuid4())
            if "created_at" not in row:
                row["created_at"] = datetime.now(UTC).isoformat()
            self._parent.rows.append(row)
            return MagicMock(data=[row], count=None)

        if self._pending_op == "update":
            assert isinstance(self._payload, dict)
            updated: list[dict[str, Any]] = []
            for row in self._parent.rows:
                if all(
                    _fake_column_value(row, column) == value
                    for op, column, value in self._filters
                    if op == "eq"
                ):
                    row.update(self._payload)
                    updated.append(dict(row))
            return MagicMock(data=updated, count=len(updated))

        rows = self._apply_filters(self._parent.rows)
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: row.get(column, ""), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None, count=len(rows))
        count = len(rows) if self._count_exact else None
        return MagicMock(data=rows, count=count)

    def _apply_filters(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        filtered = rows
        for op, column, value in self._filters:
            if op == "eq":
                filtered = [row for row in filtered if _fake_column_value(row, column) == value]
            elif op == "in":
                allowed = set(value)
                filtered = [row for row in filtered if row.get(column) in allowed]
            elif op == "gte":
                filtered = [
                    row for row in filtered if str(row.get(column, "")) >= str(value)
                ]
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
            "vendor_quotas": FakeTable(),
            "payouts": FakeTable(),
            "audit_log": FakeTable(),
            "notification_outbox": FakeTable(),
            "refunds": FakeTable(),
        }

    def table(self, name: str) -> FakeTable:
        return self.tables[name]


class FakeServiceClient:
    def __init__(self, fake: FakeSupabaseClient) -> None:
        self.client = fake


def _reserve_payout_for_test(
    fake_client: FakeSupabaseClient,
    service_client: FakeServiceClient,
    **kwargs: Any,
) -> None:
    """In-process shim while unit tests mock balances (reservation uses SQL in prod)."""
    with _vendor_lock(kwargs["vendor_id"]):
        check_payout_eligible_unlocked(
            service_client,
            vendor_id=kwargs["vendor_id"],
            amount_ngwee=kwargs["amount_ngwee"],
        )
        _insert_payout_row(service_client, **kwargs)


def _seed_vendor(fake: FakeSupabaseClient, *, kyc_tier: int = 2) -> None:
    fake.tables["vendors"].rows.append(
        {
            "id": VENDOR_ID,
            "owner_user_id": OWNER_ID,
            "status": "active",
            "kyc_tier": kyc_tier,
        }
    )
    fake.tables["kyc_records"].rows.append(
        {
            "id": str(uuid.uuid4()),
            "vendor_id": VENDOR_ID,
            "tier": kyc_tier,
            "status": "approved",
            "momo_name_match": {
                "phone": "0961111111",
                "operator": "mtn",
                "legal_name": "Jane Phiri",
                "matched": True,
                "match_score": 0.95,
            },
        }
    )
    fake.tables["vendor_quotas"].rows.append(
        {
            "tier": kyc_tier,
            "max_listings": 9999,
            "first_orders_cap_ngwee": None,
            "first_orders_count": None,
            "payout_velocity": {},
        }
    )


@pytest.fixture
def fake_client() -> FakeSupabaseClient:
    fake = FakeSupabaseClient()
    _seed_vendor(fake, kyc_tier=2)
    return fake


@pytest.fixture
def service_client(fake_client: FakeSupabaseClient) -> FakeServiceClient:
    return FakeServiceClient(fake_client)


@pytest.fixture(autouse=True)
def _shim_reserve_payout_row(
    fake_client: FakeSupabaseClient,
    service_client: FakeServiceClient,
) -> Generator[None, None, None]:
    """``reserve_payout_row`` runs SQL (advisory lock + balance check) against Postgres in
    prod; these unit tests mock balances with in-memory fakes. Shim it for the whole module
    so any test that drives ``execute_vendor_payout`` reserves against the fake and never
    reaches the real DB — this is the safety net that stops a new test from silently hitting
    live SQL in the DB-less CI job just because it forgot to patch the reservation."""
    with patch(
        "app.services.payouts.execution.reserve_payout_row",
        side_effect=lambda **kwargs: _reserve_payout_for_test(
            fake_client, service_client, **kwargs
        ),
    ):
        yield


@pytest.fixture(autouse=True)
def _enable_payouts_for_execution_tests(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[None, None, None]:
    """Payout execution unit tests opt into the kill switch and skip the 48h escrow SQL guard."""
    monkeypatch.setenv("PAYOUTS_ENABLED", "true")
    with patch("app.services.payouts.hold.assert_escrow_minimum_hold_elapsed"):
        yield


@pytest.fixture
def matched_resolve() -> AsyncMock:
    return AsyncMock(
        return_value=ResolveAccountResult(
            account_name="Jane Phiri",
            raw={"accountName": "Jane Phiri"},
        )
    )


@pytest.fixture
def successful_momo_payout() -> AsyncMock:
    async def _success(request: Any) -> InitiatePayoutResult:
        return InitiatePayoutResult(
            reference=request.reference,
            provider_reference="lenco-ref-1",
            status=TransferStatus.SUCCESSFUL,
            amount_major=ngwee_to_major_str(request.amount_ngwee),
            debit_account_id=request.account_id,
            destination={
                "type": "mobile-money",
                "phone": request.phone,
                "operator": request.operator,
            },
        )

    return AsyncMock(side_effect=_success)


@pytest.fixture
def bank_payout_mock() -> AsyncMock:
    return AsyncMock()


@pytest.mark.asyncio
async def test_balance_race_two_concurrent_payouts_never_exceed_released(
    service_client: FakeServiceClient,
    fake_client: FakeSupabaseClient,
    matched_resolve: AsyncMock,
    successful_momo_payout: AsyncMock,
    bank_payout_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two concurrent payout attempts on the same released balance → total never exceeds it."""
    monkeypatch.setenv("LENCO_ACCOUNT_ID", "lenco-acct-1")

    released = RELEASED_NGWEE
    attempt_amount = 60_000
    balance_state = {"ngwee": -released}

    def _mock_balance(_vendor_id: str) -> int:
        return balance_state["ngwee"]

    def _mock_ledger_post(**kwargs: Any) -> str:
        balance_state["ngwee"] += int(kwargs["amount_ngwee"])
        return "ledger-txn-1"

    with (
        patch(
            "app.services.payouts.eligibility.vendor_payable_balance_ngwee",
            side_effect=_mock_balance,
        ),
        patch(
            "app.services.payouts.execution._post_payout_ledger",
            side_effect=_mock_ledger_post,
        ),
    ):

        async def _attempt() -> int | None:
            try:
                result = await execute_vendor_payout(
                    service_client,
                    vendor_id=VENDOR_ID,
                    amount_ngwee=attempt_amount,
                    resolve_account=matched_resolve,
                    initiate_momo_payout=successful_momo_payout,
                    initiate_bank_payout=bank_payout_mock,
                    skip_velocity=True,
                )
                if result.outcome == PayoutOutcome.PAID:
                    return result.amount_ngwee
            except AppError:
                return None
            return None

        outcomes = await asyncio.gather(_attempt(), _attempt())
        paid_amounts = [amount for amount in outcomes if amount is not None]
        total_paid = sum(paid_amounts)

        assert total_paid <= released
        assert len(paid_amounts) == 1
        assert successful_momo_payout.await_count == 1

        payout_rows = fake_client.tables["payouts"].rows
        paid_rows = [row for row in payout_rows if row.get("status") == "paid"]
        assert sum(int(row["amount_ngwee"]) for row in paid_rows) <= released


@pytest.mark.asyncio
async def test_resolve_mismatch_held_and_not_sent(
    service_client: FakeServiceClient,
    fake_client: FakeSupabaseClient,
    bank_payout_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Name mismatch → payout held (pending) and Lenco send never called."""
    monkeypatch.setenv("LENCO_ACCOUNT_ID", "lenco-acct-1")
    mismatch_resolve = AsyncMock(
        return_value=ResolveAccountResult(account_name="John Banda", raw={})
    )
    momo_payout = AsyncMock()

    with patch(
        "app.services.payouts.eligibility.vendor_payable_balance_ngwee",
        return_value=-RELEASED_NGWEE,
    ):
        result = await execute_vendor_payout(
            service_client,
            vendor_id=VENDOR_ID,
            amount_ngwee=25_000,
            resolve_account=mismatch_resolve,
            initiate_momo_payout=momo_payout,
            initiate_bank_payout=bank_payout_mock,
            skip_velocity=True,
        )

    assert result.outcome == PayoutOutcome.HELD
    assert result.status == "pending"
    momo_payout.assert_not_called()

    payout_row = fake_client.tables["payouts"].rows[0]
    snapshot = payout_row["resolve_snapshot"]
    assert snapshot["held"] is True
    assert snapshot["hold_reason"] == "name_mismatch"
    assert snapshot["matched"] is False
    assert len(fake_client.tables["notification_outbox"].rows) == 1


@pytest.mark.asyncio
async def test_retry_after_timeout_status_requery_no_double_pay(
    service_client: FakeServiceClient,
    fake_client: FakeSupabaseClient,
    bank_payout_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Status re-query before re-send — successful provider status completes without re-send."""
    monkeypatch.setenv("LENCO_ACCOUNT_ID", "lenco-acct-1")
    payout_id = str(uuid.uuid4())
    lenco_ref = "pay-retry-test"
    fake_client.tables["payouts"].rows.append(
        {
            "id": payout_id,
            "vendor_id": VENDOR_ID,
            "amount_ngwee": 30_000,
            "rail": "mtn",
            "lenco_reference": lenco_ref,
            "status": "processing",
            "resolve_snapshot": {
                "matched": True,
                "obligation": _momo_obligation(
                    lenco_ref,
                    30_000,
                    "0961111111",
                    "mtn",
                ),
                "dispatch": {"state": "possibly_sent"},
            },
        }
    )

    query_client = MagicMock()
    query_client.query_transfer_status = AsyncMock(
        return_value=ProviderResult(
            requested_reference=lenco_ref,
            outcome=ProviderOutcome.SUCCESSFUL,
            reference=lenco_ref,
            status="successful",
            amount_major="300.00",
            currency="ZMW",
            provider_reference="lenco-1",
            debit_account_id="lenco-acct-1",
            destination={
                "type": "mobile-money",
                "phone": "0961111111",
                "operator": "mtn",
            },
        )
    )
    momo_payout = AsyncMock()

    with patch(
        "app.services.payouts.retry._post_payout_ledger",
        return_value="ledger-retry-1",
    ) as ledger_mock:
        outcome = await retry_payout_row(
            service_client,
            fake_client.tables["payouts"].rows[0],
            query_transfer_status=query_client,
            initiate_momo_payout=momo_payout,
            initiate_bank_payout=bank_payout_mock,
        )

    assert outcome == "completed"
    momo_payout.assert_not_called()
    query_client.query_transfer_status.assert_awaited_once_with(lenco_ref)
    ledger_mock.assert_called_once()

    updated = fake_client.tables["payouts"].rows[0]
    assert updated["status"] == "paid"
    assert updated["resolve_snapshot"]["reconciled_via"] == "status_requery"


@pytest.mark.asyncio
async def test_customer_refund_payout_sends_to_customer_and_skips_vendor_ledger(
    service_client: FakeServiceClient,
    fake_client: FakeSupabaseClient,
    bank_payout_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A customer-refund payout row (M08-P10) is sent to the customer momo, NOT the
    vendor, and does NOT post the vendor `payout_executed` ledger (refund legs were
    already posted by execute_refund). No vendor row is seeded — the customer-refund
    branch must not touch load_vendor_payout_profile."""
    monkeypatch.setenv("LENCO_ACCOUNT_ID", "lenco-acct-1")
    customer_momo = "260971234567"
    payout_id = str(uuid.uuid4())
    fake_client.tables["payouts"].rows.append(
        {
            "id": payout_id,
            "vendor_id": VENDOR_ID,
            "amount_ngwee": 42_000,
            "rail": "mtn",
            "lenco_reference": "rfd-abc123",
            "status": "pending",
            "resolve_snapshot": {
                "kind": "customer_refund",
                "refund_id": "rf-1",
                "customer_momo": customer_momo,
                "rail": "mtn",
                "retry_attempts": 0,
                "dispatch": {"state": "never_sent"},
            },
        }
    )

    # Never sent yet → claim first, then send without an unsafe preflight query.
    query_client = MagicMock()
    query_client.query_transfer_status = AsyncMock()
    momo_payout = AsyncMock(
        return_value=InitiatePayoutResult(
            reference="rfd-abc123",
            provider_reference="lenco-rfd-1",
            status=TransferStatus.SUCCESSFUL,
            amount_major="420.00",
            debit_account_id="lenco-acct-1",
            destination={
                "type": "mobile-money",
                "phone": customer_momo,
                "operator": "mtn",
            },
        )
    )

    with patch("app.services.payouts.retry._post_payout_ledger") as ledger_mock:
        outcome = await retry_payout_row(
            service_client,
            fake_client.tables["payouts"].rows[0],
            query_transfer_status=query_client,
            initiate_momo_payout=momo_payout,
            initiate_bank_payout=bank_payout_mock,
        )

    assert outcome == "completed"
    # Sent to the CUSTOMER's momo, not the vendor.
    momo_payout.assert_awaited_once()
    assert momo_payout.await_args is not None
    sent_request = momo_payout.await_args.args[0]
    assert sent_request.phone == customer_momo
    assert sent_request.amount_ngwee == 42_000
    query_client.query_transfer_status.assert_not_awaited()
    # Refund payout must NOT post the vendor payout_executed ledger.
    ledger_mock.assert_not_called()

    updated = fake_client.tables["payouts"].rows[0]
    assert updated["status"] == "paid"
    assert "ledger_transaction_id" not in updated["resolve_snapshot"]


@pytest.mark.asyncio
async def test_retry_pending_batch_dispatches_customer_refund_to_customer(
    service_client: FakeServiceClient,
    fake_client: FakeSupabaseClient,
    bank_payout_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end wiring: the batch dispatch (retry_pending_payouts, driven by
    POST /internal/payouts/retry) selects a `pending` customer-refund row and
    sends it to the customer momo — no separate dispatch job needed."""
    from app.services.payouts.retry import retry_pending_payouts

    monkeypatch.setenv("LENCO_ACCOUNT_ID", "lenco-acct-1")
    monkeypatch.setenv("PAYOUTS_ENABLED", "true")
    customer_momo = "260955550000"
    fake_client.tables["payouts"].rows.append(
        {
            "id": str(uuid.uuid4()),
            "vendor_id": VENDOR_ID,
            "amount_ngwee": 30_000,
            "rail": "mtn",
            "lenco_reference": "rfd-batch-1",
            "status": "pending",
            "resolve_snapshot": {
                "kind": "customer_refund",
                "customer_momo": customer_momo,
                "rail": "mtn",
                "retry_attempts": 0,
                "dispatch": {"state": "never_sent"},
            },
        }
    )
    query_client = MagicMock()
    query_client.query_transfer_status = AsyncMock()
    momo_payout = AsyncMock(
        return_value=InitiatePayoutResult(
            reference="rfd-batch-1",
            provider_reference="lenco-rfd-batch",
            status=TransferStatus.SUCCESSFUL,
            amount_major="300.00",
            debit_account_id="lenco-acct-1",
            destination={
                "type": "mobile-money",
                "phone": customer_momo,
                "operator": "mtn",
            },
        )
    )

    with patch("app.services.payouts.retry._post_payout_ledger") as ledger_mock:
        stats = await retry_pending_payouts(
            service_client,
            query_transfer_status=query_client,
            initiate_momo_payout=momo_payout,
            initiate_bank_payout=bank_payout_mock,
        )

    assert stats.scanned == 1
    assert stats.completed == 1
    momo_payout.assert_awaited_once()
    assert momo_payout.await_args is not None
    assert momo_payout.await_args.args[0].phone == customer_momo
    query_client.query_transfer_status.assert_not_awaited()
    ledger_mock.assert_not_called()
    assert fake_client.tables["payouts"].rows[0]["status"] == "paid"


@pytest.mark.asyncio
async def test_retry_pending_batch_fails_closed_before_database_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.payouts.gate import PayoutsDisabledError
    from app.services.payouts.retry import retry_pending_payouts

    monkeypatch.delenv("PAYOUTS_ENABLED", raising=False)
    service_client = MagicMock()
    with pytest.raises(PayoutsDisabledError):
        await retry_pending_payouts(
            service_client,
            query_transfer_status=MagicMock(),
            initiate_momo_payout=AsyncMock(),
            initiate_bank_payout=AsyncMock(),
        )
    service_client.client.table.assert_not_called()


@pytest.mark.asyncio
async def test_customer_refund_requery_paid_skips_vendor_ledger(
    service_client: FakeServiceClient,
    fake_client: FakeSupabaseClient,
    bank_payout_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requery says a customer-refund transfer already succeeded → mark paid without
    posting the vendor ledger and without re-sending; linked refund becomes completed."""
    monkeypatch.setenv("LENCO_ACCOUNT_ID", "lenco-acct-1")
    lenco_ref = "rfd-req-1"
    payout_id = str(uuid.uuid4())
    refund_id = str(uuid.uuid4())
    fake_client.tables["payouts"].rows.append(
        {
            "id": payout_id,
            "vendor_id": VENDOR_ID,
            "amount_ngwee": 15_000,
            "rail": "airtel",
            "lenco_reference": lenco_ref,
            "status": "processing",
            "resolve_snapshot": {
                "kind": "customer_refund",
                "refund_id": refund_id,
                "customer_momo": "260961112222",
                "rail": "airtel",
                "obligation": _momo_obligation(
                    lenco_ref,
                    15_000,
                    "260961112222",
                    "airtel",
                ),
                "dispatch": {"state": "pending"},
            },
        }
    )
    fake_client.tables["refunds"].rows.append(
        {
            "id": refund_id,
            "order_id": str(uuid.uuid4()),
            "source_key": "refund-test-key",
            "lane": 1,
            "amount_ngwee": 15_000,
            "status": "awaiting_payout",
            "payout_ref": payout_id,
            "breakdown": {},
        }
    )
    query_client = MagicMock()
    query_client.query_transfer_status = AsyncMock(
        return_value=ProviderResult(
            requested_reference=lenco_ref,
            outcome=ProviderOutcome.SUCCESSFUL,
            reference=lenco_ref,
            status="successful",
            amount_major="150.00",
            currency="ZMW",
            provider_reference="lenco-9",
            debit_account_id="lenco-acct-1",
            destination={
                "type": "mobile-money",
                "phone": "260961112222",
                "operator": "airtel",
            },
        )
    )
    momo_payout = AsyncMock()

    with patch("app.services.payouts.retry._post_payout_ledger") as ledger_mock:
        outcome = await retry_payout_row(
            service_client,
            fake_client.tables["payouts"].rows[0],
            query_transfer_status=query_client,
            initiate_momo_payout=momo_payout,
            initiate_bank_payout=bank_payout_mock,
        )

    assert outcome == "completed"
    momo_payout.assert_not_called()
    ledger_mock.assert_not_called()
    assert fake_client.tables["payouts"].rows[0]["status"] == "paid"
    assert fake_client.tables["refunds"].rows[0]["status"] == "completed"


@pytest.mark.asyncio
async def test_provider_pending_is_polled_without_another_transfer_post(
    service_client: FakeServiceClient,
    fake_client: FakeSupabaseClient,
    bank_payout_mock: AsyncMock,
) -> None:
    row = _processing_payout_row(reference="pay-pending-1")
    fake_client.tables["payouts"].rows.append(row)
    query_client = MagicMock()
    query_client.query_transfer_status = AsyncMock(
        return_value=ProviderResult(
            requested_reference="pay-pending-1",
            outcome=ProviderOutcome.PENDING,
            reference="pay-pending-1",
            status="pending",
            amount_major="300.00",
            currency="ZMW",
            provider_reference="lenco-pending-1",
        )
    )
    momo_payout = AsyncMock()

    outcome = await retry_payout_row(
        service_client,
        row,
        query_transfer_status=query_client,
        initiate_momo_payout=momo_payout,
        initiate_bank_payout=bank_payout_mock,
    )

    assert outcome == "retried"
    momo_payout.assert_not_awaited()
    assert row["status"] == "processing"
    assert row["resolve_snapshot"]["dispatch"]["state"] == "pending"


@pytest.mark.parametrize(
    ("outcome", "reason"),
    [
        (ProviderOutcome.FAILED, "provider_failed_reference_reuse_unconfirmed"),
        (ProviderOutcome.NOT_FOUND, "not_found_after_dispatch"),
    ],
)
@pytest.mark.asyncio
async def test_attempted_transfer_failed_or_not_found_is_held_without_resend(
    service_client: FakeServiceClient,
    fake_client: FakeSupabaseClient,
    bank_payout_mock: AsyncMock,
    outcome: ProviderOutcome,
    reason: str,
) -> None:
    row = _processing_payout_row(reference="pay-held-1")
    fake_client.tables["payouts"].rows.append(row)
    query_client = MagicMock()
    query_client.query_transfer_status = AsyncMock(
        return_value=ProviderResult(
            requested_reference="pay-held-1",
            outcome=outcome,
            reference="pay-held-1" if outcome == ProviderOutcome.FAILED else None,
            status="failed" if outcome == ProviderOutcome.FAILED else None,
            failure_reason="declined" if outcome == ProviderOutcome.FAILED else None,
        )
    )
    momo_payout = AsyncMock()

    result = await retry_payout_row(
        service_client,
        row,
        query_transfer_status=query_client,
        initiate_momo_payout=momo_payout,
        initiate_bank_payout=bank_payout_mock,
    )

    assert result == "manual"
    momo_payout.assert_not_awaited()
    assert row["status"] == "processing"
    assert row["resolve_snapshot"]["held"] is True
    assert row["resolve_snapshot"]["hold_reason"] == reason


@pytest.mark.parametrize(
    ("field", "bad_value", "reason"),
    [
        ("reference", "pay-other", "merchant_reference"),
        ("amount_major", "301.00", "amount"),
        ("currency", "USD", "currency"),
        ("debit_account_id", None, "debit_account_missing"),
        ("debit_account_id", "other-account", "debit_account"),
        (
            "destination",
            {"type": "mobile-money", "phone": "0969999999", "operator": "mtn"},
            "destination",
        ),
        ("provider_reference", "other-provider-ref", "provider_reference"),
    ],
)
@pytest.mark.asyncio
async def test_success_identity_mismatch_never_completes_or_posts_ledger(
    service_client: FakeServiceClient,
    fake_client: FakeSupabaseClient,
    bank_payout_mock: AsyncMock,
    field: str,
    bad_value: Any,
    reason: str,
) -> None:
    row = _processing_payout_row(reference="pay-identity-1")
    row["resolve_snapshot"]["provider_reference"] = "lenco-identity-1"
    fake_client.tables["payouts"].rows.append(row)
    result = ProviderResult(
        requested_reference="pay-identity-1",
        outcome=ProviderOutcome.SUCCESSFUL,
        reference="pay-identity-1",
        status="successful",
        amount_major="300.00",
        currency="ZMW",
        provider_reference="lenco-identity-1",
        debit_account_id="lenco-acct-1",
        destination={
            "type": "mobile-money",
            "phone": "0961111111",
            "operator": "mtn",
        },
    ).model_copy(update={field: bad_value})
    query_client = MagicMock()
    query_client.query_transfer_status = AsyncMock(return_value=result)

    with patch("app.services.payouts.retry._post_payout_ledger") as ledger:
        with pytest.raises(PayoutObservationMismatch) as exc_info:
            await retry_payout_row(
                service_client,
                row,
                query_transfer_status=query_client,
                initiate_momo_payout=AsyncMock(),
                initiate_bank_payout=bank_payout_mock,
            )

    assert exc_info.value.details["reason"] == reason
    ledger.assert_not_called()
    assert row["status"] == "processing"
    assert row["resolve_snapshot"]["held"] is True


@pytest.mark.asyncio
async def test_concurrent_first_dispatch_claims_send_once(
    service_client: FakeServiceClient,
    fake_client: FakeSupabaseClient,
    bank_payout_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LENCO_ACCOUNT_ID", "lenco-acct-1")
    row: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "vendor_id": VENDOR_ID,
        "amount_ngwee": 30_000,
        "rail": "mtn",
        "lenco_reference": "rfd-concurrent-1",
        "status": "pending",
        "resolve_snapshot": {
            "kind": "customer_refund",
            "customer_momo": "260955551111",
            "rail": "mtn",
            "dispatch": {"state": "never_sent"},
        },
    }
    fake_client.tables["payouts"].rows.append(row)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def pending_transfer(request: Any) -> InitiatePayoutResult:
        entered.set()
        await release.wait()
        return InitiatePayoutResult(
            reference=request.reference,
            provider_reference="lenco-concurrent-1",
            status=TransferStatus.PENDING,
            amount_major="300.00",
            debit_account_id=request.account_id,
            destination={
                "type": "mobile-money",
                "phone": request.phone,
                "operator": request.operator,
            },
        )

    momo_payout = AsyncMock(side_effect=pending_transfer)
    query_client = MagicMock()
    query_client.query_transfer_status = AsyncMock()
    # Both workers read independent snapshots before either claims the row.
    # Never pair a post-claim dispatch marker with a fabricated pending status.
    first_snapshot = deepcopy(row)
    second_snapshot = deepcopy(row)
    first = asyncio.create_task(
        retry_payout_row(
            service_client,
            first_snapshot,
            query_transfer_status=query_client,
            initiate_momo_payout=momo_payout,
            initiate_bank_payout=bank_payout_mock,
        )
    )
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        assert row["status"] == "processing"
        assert second_snapshot["status"] == "pending"
        assert second_snapshot["resolve_snapshot"]["dispatch"] == {"state": "never_sent"}
        second = await retry_payout_row(
            service_client,
            second_snapshot,
            query_transfer_status=query_client,
            initiate_momo_payout=momo_payout,
            initiate_bank_payout=bank_payout_mock,
        )
    finally:
        release.set()
        first_result = await asyncio.wait_for(first, timeout=5)

    assert {first_result, second} == {"retried", "skipped"}
    assert momo_payout.await_count == 1
    query_client.query_transfer_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_ledger_failure_keeps_verified_payout_processing_for_idempotent_replay(
    service_client: FakeServiceClient,
    fake_client: FakeSupabaseClient,
    bank_payout_mock: AsyncMock,
) -> None:
    row = _processing_payout_row(reference="pay-ledger-rollback-1")
    fake_client.tables["payouts"].rows.append(row)
    successful = ProviderResult(
        requested_reference="pay-ledger-rollback-1",
        outcome=ProviderOutcome.SUCCESSFUL,
        reference="pay-ledger-rollback-1",
        status="successful",
        amount_major="300.00",
        currency="ZMW",
        provider_reference="lenco-ledger-1",
        debit_account_id="lenco-acct-1",
        destination={
            "type": "mobile-money",
            "phone": "0961111111",
            "operator": "mtn",
        },
    )
    query_client = MagicMock()
    query_client.query_transfer_status = AsyncMock(return_value=successful)

    with patch(
        "app.services.payouts.retry._post_payout_ledger",
        side_effect=RuntimeError("ledger transaction rolled back"),
    ):
        with pytest.raises(RuntimeError, match="rolled back"):
            await retry_payout_row(
                service_client,
                row,
                query_transfer_status=query_client,
                initiate_momo_payout=AsyncMock(),
                initiate_bank_payout=bank_payout_mock,
            )

    assert row["status"] == "processing"

    with patch(
        "app.services.payouts.retry._post_payout_ledger",
        return_value="ledger-replayed-1",
    ) as ledger:
        outcome = await retry_payout_row(
            service_client,
            row,
            query_transfer_status=query_client,
            initiate_momo_payout=AsyncMock(),
            initiate_bank_payout=bank_payout_mock,
        )
        replay = await retry_payout_row(
            service_client,
            row,
            query_transfer_status=query_client,
            initiate_momo_payout=AsyncMock(),
            initiate_bank_payout=bank_payout_mock,
        )

    assert outcome == "completed"
    assert replay == "skipped"
    ledger.assert_called_once()
    assert row["status"] == "paid"


@pytest.mark.asyncio
async def test_batch_isolates_failed_query_and_completes_healthy_first_send(
    service_client: FakeServiceClient,
    fake_client: FakeSupabaseClient,
    bank_payout_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LENCO_ACCOUNT_ID", "lenco-acct-1")
    broken = _processing_payout_row(reference="pay-broken-1")
    healthy = {
        "id": str(uuid.uuid4()),
        "vendor_id": VENDOR_ID,
        "amount_ngwee": 25_000,
        "rail": "mtn",
        "lenco_reference": "rfd-healthy-1",
        "status": "pending",
        "created_at": "2026-09-28T00:00:01+00:00",
        "resolve_snapshot": {
            "kind": "customer_refund",
            "customer_momo": "260955552222",
            "rail": "mtn",
            "dispatch": {"state": "never_sent"},
        },
    }
    broken["created_at"] = "2026-09-28T00:00:00+00:00"
    fake_client.tables["payouts"].rows.extend([broken, healthy])
    query_client = MagicMock()
    query_client.query_transfer_status = AsyncMock(
        side_effect=RuntimeError("provider query unavailable")
    )

    async def success(request: Any) -> InitiatePayoutResult:
        return InitiatePayoutResult(
            reference=request.reference,
            provider_reference="lenco-healthy-1",
            status=TransferStatus.SUCCESSFUL,
            amount_major="250.00",
            debit_account_id=request.account_id,
            destination={
                "type": "mobile-money",
                "phone": request.phone,
                "operator": request.operator,
            },
        )

    stats = await retry_pending_payouts(
        service_client,
        query_transfer_status=query_client,
        initiate_momo_payout=AsyncMock(side_effect=success),
        initiate_bank_payout=bank_payout_mock,
    )

    assert stats.scanned == 2
    assert stats.errors == 1
    assert stats.completed == 1
    assert broken["status"] == "processing"
    assert healthy["status"] == "paid"


def test_refund_reference_replay_rejects_changed_obligation(
    service_client: FakeServiceClient,
    fake_client: FakeSupabaseClient,
) -> None:
    first = initiate_customer_refund_payout(
        service_client=service_client,
        refund_id=str(uuid.uuid4()),
        reference_key="immutable-refund-1",
        vendor_id=VENDOR_ID,
        amount_ngwee=12_500,
        rail="mtn",
        customer_momo="260971111111",
    )

    with pytest.raises(AppError) as exc_info:
        initiate_customer_refund_payout(
            service_client=service_client,
            refund_id=str(uuid.uuid4()),
            reference_key="immutable-refund-1",
            vendor_id=VENDOR_ID,
            amount_ngwee=12_501,
            rail="mtn",
            customer_momo="260971111111",
        )

    assert exc_info.value.code == "refund_payout_obligation_mismatch"
    assert len(fake_client.tables["payouts"].rows) == 1
    assert fake_client.tables["payouts"].rows[0]["id"] == first.payout_id


@pytest.mark.asyncio
async def test_velocity_cap_boundary_at_cap_ok_plus_one_deferred(
    service_client: FakeServiceClient,
    fake_client: FakeSupabaseClient,
    matched_resolve: AsyncMock,
    successful_momo_payout: AsyncMock,
    bank_payout_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """At velocity cap the payout is allowed; the next one is deferred."""
    monkeypatch.setenv("LENCO_ACCOUNT_ID", "lenco-acct-1")
    fake_client.tables["vendor_quotas"].rows = [
        {
            "tier": 1,
            "max_listings": 30,
            "first_orders_cap_ngwee": 50_000,
            "first_orders_count": 5,
            "payout_velocity": {
                "max_payouts_per_day": 1,
                "max_amount_ngwee_per_day": 200_000,
            },
        }
    ]
    fake_client.tables["vendors"].rows[0]["kyc_tier"] = 1
    # Cap tier must come from the approved KYC record, not the bare column.
    fake_client.tables["kyc_records"].rows[0]["tier"] = 1

    with (
        patch(
            "app.services.payouts.eligibility.vendor_payable_balance_ngwee",
            return_value=-RELEASED_NGWEE,
        ),
        patch(
            "app.services.payouts.execution._post_payout_ledger",
            return_value="ledger-1",
        ),
    ):
        first = await execute_vendor_payout(
            service_client,
            vendor_id=VENDOR_ID,
            amount_ngwee=20_000,
            resolve_account=matched_resolve,
            initiate_momo_payout=successful_momo_payout,
            initiate_bank_payout=bank_payout_mock,
        )
        second = await execute_vendor_payout(
            service_client,
            vendor_id=VENDOR_ID,
            amount_ngwee=15_000,
            resolve_account=matched_resolve,
            initiate_momo_payout=successful_momo_payout,
            initiate_bank_payout=bank_payout_mock,
        )

    assert first.outcome == PayoutOutcome.PAID
    assert second.outcome == PayoutOutcome.DEFERRED
    assert second.status == "deferred"
    assert second.payout_id == ""
    # Soft deferral must not park a reserving payouts row (would freeze balance).
    assert all(row.get("status") != "deferred" for row in fake_client.tables["payouts"].rows)
    assert len([r for r in fake_client.tables["payouts"].rows if r["status"] == "pending"]) == 0
    assert successful_momo_payout.await_count == 1


def test_assert_payout_eligible_rejects_over_balance(
    service_client: FakeServiceClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LENCO_ACCOUNT_ID", "lenco-acct-1")
    with patch(
        "app.services.payouts.eligibility.vendor_payable_balance_ngwee",
        return_value=-50_000,
    ):
        with pytest.raises(AppError) as exc:
            assert_payout_eligible(service_client, vendor_id=VENDOR_ID, amount_ngwee=60_000)
        assert exc.value.code == "insufficient_released_balance"


def test_compute_eligibility_accounts_for_reserved_payouts(
    service_client: FakeServiceClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with patch(
        "app.services.payouts.eligibility.vendor_payable_balance_ngwee",
        return_value=-100_000,
    ):
        fake_client = service_client.client
        fake_client.tables["payouts"].rows.append(
            {
                "id": str(uuid.uuid4()),
                "vendor_id": VENDOR_ID,
                "amount_ngwee": 40_000,
                "status": "processing",
            }
        )
        snapshot = compute_eligibility(service_client, VENDOR_ID)
        assert snapshot.released_balance_ngwee == 100_000
        assert snapshot.reserved_ngwee == 40_000
        assert snapshot.available_ngwee == 60_000


def test_compute_eligibility_excludes_customer_refund_and_deferred_rows(
    service_client: FakeServiceClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Customer-refund + legacy deferred pending rows must not freeze vendor available."""
    with patch(
        "app.services.payouts.eligibility.vendor_payable_balance_ngwee",
        return_value=-100_000,
    ):
        fake_client = service_client.client
        fake_client.tables["payouts"].rows.extend(
            [
                {
                    "id": str(uuid.uuid4()),
                    "vendor_id": VENDOR_ID,
                    "amount_ngwee": 30_000,
                    "status": "pending",
                    "resolve_snapshot": {"kind": "customer_refund"},
                },
                {
                    "id": str(uuid.uuid4()),
                    "vendor_id": VENDOR_ID,
                    "amount_ngwee": 25_000,
                    "status": "pending",
                    "resolve_snapshot": {"deferred": True, "hold_reason": "velocity_cap"},
                },
                {
                    "id": str(uuid.uuid4()),
                    "vendor_id": VENDOR_ID,
                    "amount_ngwee": 10_000,
                    "status": "processing",
                    "resolve_snapshot": {"matched": True},
                },
            ]
        )
        snapshot = compute_eligibility(service_client, VENDOR_ID)
        assert snapshot.reserved_ngwee == 10_000
        assert snapshot.available_ngwee == 90_000


@pytest.mark.asyncio
async def test_run_resolve_name_check_scores_match(
    matched_resolve: AsyncMock,
) -> None:
    profile = VendorPayoutProfile(
        vendor_id=VENDOR_ID,
        owner_user_id=OWNER_ID,
        phone="0961111111",
        operator="mtn",
        legal_name="Jane Phiri",
        rail="mtn",
    )
    result = await run_resolve_name_check(profile, resolve_account=matched_resolve)
    assert result.matched is True
    assert result.held is False


@pytest.fixture
def internal_client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("INTERNAL_PAYOUTS_TOKEN", "test-payouts-token")
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_internal_payouts_tick_requires_token(internal_client: TestClient) -> None:
    response = internal_client.post("/internal/payouts/tick")
    assert response.status_code == 401


def test_internal_payouts_execute_requires_token(internal_client: TestClient) -> None:
    response = internal_client.post(
        "/internal/payouts/execute",
        json={"vendor_id": VENDOR_ID, "amount_ngwee": 1000},
    )
    assert response.status_code == 401


@pytest.mark.parametrize("endpoint", ["tick", "retry"])
def test_scheduled_payout_routes_fail_closed_when_disabled(
    internal_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    endpoint: str,
) -> None:
    monkeypatch.delenv("PAYOUTS_ENABLED", raising=False)
    response = internal_client.post(
        f"/internal/payouts/{endpoint}",
        headers={"X-Internal-Token": "test-payouts-token"},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "payouts_disabled"


@pytest.mark.parametrize("endpoint", ["tick", "retry"])
def test_scheduled_payout_routes_respect_staging_suppression(
    internal_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    endpoint: str,
) -> None:
    monkeypatch.setenv("PAYOUTS_ENABLED", "true")
    monkeypatch.setenv("ENV", "staging")
    monkeypatch.delenv("STAGING_ALLOW_PAYOUTS", raising=False)
    response = internal_client.post(
        f"/internal/payouts/{endpoint}",
        headers={"X-Internal-Token": "test-payouts-token"},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "payouts_suppressed_on_staging"


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", list(ProviderOutcome))
async def test_historical_pending_queries_original_reference_without_reposting(
    service_client: FakeServiceClient,
    fake_client: FakeSupabaseClient,
    bank_payout_mock: AsyncMock,
    outcome: ProviderOutcome,
) -> None:
    """Upgrade crash window: pending without dispatch provenance may already be sent."""
    row = _processing_payout_row(reference="pay-historical-crash")
    row["status"] = "pending"
    row["resolve_snapshot"].pop("dispatch")
    fake_client.tables["payouts"].rows.append(row)
    query = MagicMock()
    query.query_transfer_status = AsyncMock(return_value=ProviderResult(
        requested_reference=row["lenco_reference"], outcome=outcome,
        reference=row["lenco_reference"], provider_reference="provider-historical-crash",
        status=outcome.value, amount_major="300.00", currency="ZMW",
        debit_account_id="lenco-acct-1",
        destination={"type": "mobile-money", "phone": "0961111111", "operator": "mtn"},
    ))
    post = AsyncMock()
    with patch(
        "app.services.payouts.retry._post_payout_ledger", return_value="ledger-old"
    ) as ledger:
        result = await retry_payout_row(
            service_client, row, query_transfer_status=query,
            initiate_momo_payout=post, initiate_bank_payout=bank_payout_mock,
        )
    query.query_transfer_status.assert_awaited_once_with(row["lenco_reference"])
    post.assert_not_awaited()
    bank_payout_mock.assert_not_awaited()
    if outcome == ProviderOutcome.SUCCESSFUL:
        assert result == "completed" and row["status"] == "paid"
        ledger.assert_called_once()
    else:
        ledger.assert_not_called()
        assert row["status"] != "paid"
        if outcome in {ProviderOutcome.FAILED, ProviderOutcome.NOT_FOUND}:
            assert result == "manual" and row["resolve_snapshot"]["held"] is True


@pytest.mark.asyncio
async def test_historical_pending_query_timeout_never_creates_dispatch_marker(
    service_client: FakeServiceClient, fake_client: FakeSupabaseClient,
    bank_payout_mock: AsyncMock,
) -> None:
    row = _processing_payout_row(reference="pay-historical-timeout")
    row["status"] = "pending"
    row["resolve_snapshot"].pop("dispatch")
    fake_client.tables["payouts"].rows.append(row)
    query = MagicMock()
    query.query_transfer_status = AsyncMock(side_effect=TimeoutError("synthetic timeout"))
    post = AsyncMock()
    with pytest.raises(TimeoutError):
        await retry_payout_row(service_client, row, query_transfer_status=query,
                               initiate_momo_payout=post, initiate_bank_payout=bank_payout_mock)
    post.assert_not_awaited()
    assert row["status"] == "processing"
    assert row["resolve_snapshot"]["dispatch"]["state"] == "possibly_sent"


@pytest.mark.parametrize("snapshot", [
    {}, {"retry_attempts": 0},
    {"dispatch": {"state": "never_sent"}, "retry_attempts": 1},
    {"dispatch": {"state": "never_sent"}, "retry_attempts": False},
    {"dispatch": {"state": "never_sent"}, "last_error": "lost response"},
    {"dispatch": {"state": "never_sent", "claimed_at": "earlier"}},
])
def test_first_dispatch_requires_unconsumed_server_provenance(snapshot: dict[str, Any]) -> None:
    from app.services.payouts.retry import _has_never_sent_provenance

    assert not _has_never_sent_provenance(snapshot)
    assert _has_never_sent_provenance({"dispatch": {"state": "never_sent"}})


def test_first_dispatch_cas_rechecks_database_marker(
    service_client: FakeServiceClient, fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.payouts.retry import _claim_first_dispatch

    monkeypatch.setenv("LENCO_ACCOUNT_ID", "lenco-acct-1")
    row = _processing_payout_row(reference="pay-stale-marker")
    row["status"] = "pending"
    stale = {**row["resolve_snapshot"], "dispatch": {"state": "never_sent"}}
    # Stored marker changed between the caller's read and its conditional UPDATE.
    fake_client.tables["payouts"].rows.append(row)
    profile = VendorPayoutProfile(vendor_id=VENDOR_ID, owner_user_id=OWNER_ID,
                                 phone="0961111111", operator="mtn",
                                 legal_name="Synthetic", rail="mtn")
    assert _claim_first_dispatch(service_client, payout_row=row, snapshot=stale,
                                 profile=profile, clock=datetime.now(UTC)) is None
    assert row["resolve_snapshot"]["dispatch"]["state"] == "pending"
