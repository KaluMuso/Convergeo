"""M08-P09 payout tests — balance race, resolve-mismatch, retry, velocity caps."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.errors import AppError
from app.main import create_app
from app.services.payments.base import InitiatePayoutResult, ResolveAccountResult, TransferStatus
from app.services.payments.lenco.models import LencoTransferData, LencoTransferStatusResponse
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
from app.services.payouts.resolve_check import VendorPayoutProfile, run_resolve_name_check
from app.services.payouts.retry import retry_payout_row
from fastapi.testclient import TestClient

VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
OWNER_ID = "11111111-1111-1111-1111-111111111111"
RELEASED_NGWEE = 100_000


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
                    row.get(column) == value
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
                filtered = [row for row in filtered if row.get(column) == value]
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
    return AsyncMock(
        return_value=InitiatePayoutResult(
            provider_reference="lenco-ref-1",
            status=TransferStatus.SUCCESSFUL,
            amount_major="1000.00",
        )
    )


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
        patch(
            "app.services.payouts.execution.reserve_payout_row",
            side_effect=lambda **kwargs: _reserve_payout_for_test(
                fake_client, service_client, **kwargs
            ),
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
            "resolve_snapshot": {"matched": True, "retry_attempts": 1},
        }
    )

    query_client = MagicMock()
    query_client.query_transfer_status = AsyncMock(
        return_value=LencoTransferStatusResponse(
            status=True,
            message="ok",
            data=LencoTransferData(
                id="tx-1",
                amount="300.00",
                currency="ZMW",
                reference=lenco_ref,
                lenco_reference="lenco-1",
                status="successful",
            ),
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
            },
        }
    )

    # Never sent yet → provider has no record → proceed to send.
    query_client = MagicMock()
    query_client.query_transfer_status = AsyncMock(
        return_value=LencoTransferStatusResponse(status=True, message="not found", data=None)
    )
    momo_payout = AsyncMock(
        return_value=InitiatePayoutResult(
            provider_reference="lenco-rfd-1",
            status=TransferStatus.SUCCESSFUL,
            amount_major="420.00",
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
    POST /internal/payouts/retry-tick) selects a `pending` customer-refund row and
    sends it to the customer momo — no separate dispatch job needed."""
    from app.services.payouts.retry import retry_pending_payouts

    monkeypatch.setenv("LENCO_ACCOUNT_ID", "lenco-acct-1")
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
            },
        }
    )
    query_client = MagicMock()
    query_client.query_transfer_status = AsyncMock(
        return_value=LencoTransferStatusResponse(status=True, message="none", data=None)
    )
    momo_payout = AsyncMock(
        return_value=InitiatePayoutResult(
            provider_reference="lenco-rfd-batch",
            status=TransferStatus.SUCCESSFUL,
            amount_major="300.00",
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
    ledger_mock.assert_not_called()
    assert fake_client.tables["payouts"].rows[0]["status"] == "paid"


@pytest.mark.asyncio
async def test_customer_refund_requery_paid_skips_vendor_ledger(
    service_client: FakeServiceClient,
    fake_client: FakeSupabaseClient,
    bank_payout_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requery says a customer-refund transfer already succeeded → mark paid without
    posting the vendor ledger and without re-sending."""
    monkeypatch.setenv("LENCO_ACCOUNT_ID", "lenco-acct-1")
    lenco_ref = "rfd-req-1"
    fake_client.tables["payouts"].rows.append(
        {
            "id": str(uuid.uuid4()),
            "vendor_id": VENDOR_ID,
            "amount_ngwee": 15_000,
            "rail": "airtel",
            "lenco_reference": lenco_ref,
            "status": "processing",
            "resolve_snapshot": {
                "kind": "customer_refund",
                "customer_momo": "260961112222",
                "rail": "airtel",
                "retry_attempts": 1,
            },
        }
    )
    query_client = MagicMock()
    query_client.query_transfer_status = AsyncMock(
        return_value=LencoTransferStatusResponse(
            status=True,
            message="ok",
            data=LencoTransferData(
                id="tx-9",
                amount="150.00",
                currency="ZMW",
                reference=lenco_ref,
                lenco_reference="lenco-9",
                status="successful",
            ),
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
    assert second.status == "pending"
    deferred_row = next(
        row for row in fake_client.tables["payouts"].rows if row["id"] == second.payout_id
    )
    assert deferred_row["resolve_snapshot"]["hold_reason"] == "velocity_cap"
    assert deferred_row["resolve_snapshot"]["deferred"] is True
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
