"""Tests for reconciliation poller and daily Lenco-vs-ledger report."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.services.payments.base import QueryStatusResult
from app.services.payments.reconcile import (
    DailyReportResult,
    DrainResult,
    LedgerDayRow,
    LencoAccountSnapshot,
    LencoTransactionRow,
    PollResult,
    build_reconciliation_diff,
    drain_pending_webhook_events,
    extract_lenco_reference,
    poll_non_terminal_payments,
    run_daily_reconciliation_report,
)
from app.services.payments.state import SYSTEM_ACTOR_ID, PaymentStatus
from tests.rls.conftest import PgConn, apply_migrations, resolve_db_url, schema_ready

CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
CHECKOUT_GROUP_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | list[dict[str, Any]] | None = None
        self._order_column: str | None = None
        self._order_desc = False
        self._limit: int | None = None

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        _ = columns, count
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._filters.append(("in", column, values))
        return self

    def lt(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("lt", column, value))
        return self

    def is_(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("is", column, value))
        return self

    def order(self, column: str, *, desc: bool = False) -> FakeQuery:
        self._order_column = column
        self._order_desc = desc
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
            row.setdefault("id", str(uuid.uuid4()))
            row.setdefault("created_at", datetime.now(UTC).isoformat())
            self._parent.rows.append(row)
            return MagicMock(data=[row])

        if self._pending_op == "update":
            assert isinstance(self._payload, dict)
            updated: list[dict[str, Any]] = []
            for row in self._parent.rows:
                if self._row_matches(row):
                    row.update(self._payload)
                    updated.append(dict(row))
            return MagicMock(data=updated)

        rows = [row for row in self._parent.rows if self._row_matches(row)]
        if self._order_column is not None:
            rows.sort(
                key=lambda r: str(r.get(self._order_column, "")),
                reverse=self._order_desc,
            )
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=rows)

    def _row_matches(self, row: dict[str, Any]) -> bool:
        for op, column, value in self._filters:
            cell = row.get(column)
            if op == "eq" and cell != value:
                return False
            if op == "in" and cell not in set(value):
                return False
            if op == "lt" and not (str(cell) < str(value)):
                return False
            if op == "is":
                if value == "null" and cell is not None:
                    return False
                if value is None and cell is not None:
                    return False
        return True


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self, []).select(columns, count=count)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).insert(payload)

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).update(payload)


class FakeSupabaseTables:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "payments": FakeTable(),
            "audit_log": FakeTable(),
            "reconciliation_reports": FakeTable(),
        }

    def table(self, name: str) -> FakeTable:
        if name not in self.tables:
            self.tables[name] = FakeTable()
        return self.tables[name]


class FakeServiceClient:
    def __init__(self) -> None:
        self._fake = FakeSupabaseTables()

    @property
    def client(self) -> FakeSupabaseTables:
        return self._fake


@pytest.fixture
def fake_service() -> FakeServiceClient:
    return FakeServiceClient()


class TestExtractReference:
    def test_parses_transfer_narration(self) -> None:
        assert extract_lenco_reference("Transfer / ord-abc-1") == "ord-abc-1"

    def test_parses_client_reference(self) -> None:
        assert extract_lenco_reference("Collection pay-test-99") == "pay-test-99"


class TestBuildReconciliationDiff:
    def test_clean_day_zero_discrepancies(self) -> None:
        diff = build_reconciliation_diff(
            lenco_balance_ngwee=500_000,
            ledger_balance_ngwee=500_000,
            lenco_rows=[
                LencoTransactionRow(
                    id="l1",
                    amount_ngwee=100_000,
                    txn_type="credit",
                    narration="Transfer / ord-match-1",
                    reference="ord-match-1",
                    datetime="2026-07-09T10:00:00Z",
                )
            ],
            ledger_rows=[
                LedgerDayRow(
                    transaction_id="t1",
                    kind="charge_received",
                    payment_id="p1",
                    lenco_reference="ord-match-1",
                    amount_ngwee=100_000,
                    created_at="2026-07-09T10:00:01Z",
                )
            ],
        )
        assert not diff.has_discrepancies
        assert diff.balance_diff_ngwee == 0
        assert diff.orphaned_lenco == ()
        assert diff.ledger_only == ()

    def test_mismatch_detection(self) -> None:
        diff = build_reconciliation_diff(
            lenco_balance_ngwee=600_000,
            ledger_balance_ngwee=500_000,
            lenco_rows=[
                LencoTransactionRow(
                    id="l-orphan",
                    amount_ngwee=50_000,
                    txn_type="credit",
                    narration="Transfer / ord-orphan",
                    reference="ord-orphan",
                    datetime="2026-07-09T11:00:00Z",
                ),
                LencoTransactionRow(
                    id="l-mismatch",
                    amount_ngwee=80_000,
                    txn_type="credit",
                    narration="Transfer / ord-mismatch",
                    reference="ord-mismatch",
                    datetime="2026-07-09T12:00:00Z",
                ),
            ],
            ledger_rows=[
                LedgerDayRow(
                    transaction_id="t-ledger-only",
                    kind="charge_received",
                    payment_id="p2",
                    lenco_reference="ord-ledger-only",
                    amount_ngwee=25_000,
                    created_at="2026-07-09T13:00:00Z",
                ),
                LedgerDayRow(
                    transaction_id="t-mismatch",
                    kind="charge_received",
                    payment_id="p3",
                    lenco_reference="ord-mismatch",
                    amount_ngwee=75_000,
                    created_at="2026-07-09T12:00:01Z",
                ),
            ],
        )
        assert diff.balance_diff_ngwee == 100_000
        assert len(diff.orphaned_lenco) == 1
        assert diff.orphaned_lenco[0]["reference"] == "ord-orphan"
        assert len(diff.ledger_only) == 1
        assert diff.ledger_only[0]["reference"] == "ord-ledger-only"
        assert len(diff.ngwee_mismatches) == 1
        assert diff.ngwee_mismatches[0]["diff_ngwee"] == 5_000


@pytest.mark.asyncio
async def test_poller_closes_webhook_gap_via_state_machine(fake_service: FakeServiceClient) -> None:
    """Stuck non-terminal payment + Lenco success → poller completes via M08-P04."""
    payment_id = str(uuid.uuid4())
    stale_at = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    fake_service.client.tables["payments"].rows.append(
        {
            "id": payment_id,
            "checkout_group_id": CHECKOUT_GROUP_ID,
            "status": PaymentStatus.USSD_PUSHED.value,
            "lenco_reference": "ord-gap-close-1",
            "amount_ngwee": 25_000,
            "rail": "mtn",
            "provider": "lenco",
            "raw": {},
            "updated_at": stale_at,
        }
    )

    async def query_status(request: Any) -> QueryStatusResult:
        assert request.reference == "ord-gap-close-1"
        return QueryStatusResult(
            reference=request.reference,
            status="successful",
            amount_major="250.00",
        )

    result = await poll_non_terminal_payments(
        fake_service,
        query_status=query_status,
        older_than_minutes=1,
    )

    assert result == PollResult(scanned=1, updated=1, unchanged=0, errors=0)
    assert fake_service.client.tables["payments"].rows[0]["status"] == PaymentStatus.SUCCESS.value
    audit_rows = fake_service.client.tables["audit_log"].rows
    assert len(audit_rows) == 1
    assert audit_rows[0]["actor"] == SYSTEM_ACTOR_ID


@pytest.mark.asyncio
async def test_poller_isolates_poison_pill_and_continues_batch(
    fake_service: FakeServiceClient,
) -> None:
    """One illegal transition must not abort the tick; healthy payments still process.

    The poison pill is an INITIATED payment for which Lenco reports ``successful``
    (no INITIATED->success edge). It is logged/skipped while the healthy
    USSD_PUSHED payments in the same batch are reconciled to SUCCESS.
    """
    stale_at = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    payments_table = fake_service.client.tables["payments"]

    poison_id = str(uuid.uuid4())
    payments_table.rows.append(
        {
            "id": poison_id,
            "checkout_group_id": CHECKOUT_GROUP_ID,
            "status": PaymentStatus.INITIATED.value,  # no edge to success
            "lenco_reference": "ord-poison-1",
            "amount_ngwee": 15_000,
            "rail": "mtn",
            "provider": "lenco",
            "raw": {},
            "updated_at": stale_at,
        }
    )

    healthy_ids: list[str] = []
    for idx in range(3):
        healthy_id = str(uuid.uuid4())
        healthy_ids.append(healthy_id)
        payments_table.rows.append(
            {
                "id": healthy_id,
                "checkout_group_id": CHECKOUT_GROUP_ID,
                "status": PaymentStatus.USSD_PUSHED.value,
                "lenco_reference": f"ord-healthy-{idx}",
                "amount_ngwee": 20_000,
                "rail": "mtn",
                "provider": "lenco",
                "raw": {},
                "updated_at": stale_at,
            }
        )

    async def query_status(request: Any) -> QueryStatusResult:
        return QueryStatusResult(
            reference=request.reference,
            status="successful",
            amount_major="200.00",
        )

    result = await poll_non_terminal_payments(
        fake_service,
        query_status=query_status,
        older_than_minutes=1,
    )

    # Tick did NOT abort: all 4 scanned, 3 healthy updated, 1 poison skipped as error.
    assert result == PollResult(scanned=4, updated=3, unchanged=0, errors=1)

    by_id = {row["id"]: row for row in payments_table.rows}
    # Every healthy payment was reconciled to SUCCESS.
    for healthy_id in healthy_ids:
        assert by_id[healthy_id]["status"] == PaymentStatus.SUCCESS.value
    # The poison pill was left untouched (guarded transition refused, no raw UPDATE).
    assert by_id[poison_id]["status"] == PaymentStatus.INITIATED.value

    # Exactly the 3 healthy transitions were audited; the skipped one wrote none.
    audit_rows = fake_service.client.tables["audit_log"].rows
    assert len(audit_rows) == 3
    audited_ids = {row["entity_id"] for row in audit_rows}
    assert audited_ids == set(healthy_ids)


@pytest.mark.asyncio
async def test_poller_idempotent_rerun(fake_service: FakeServiceClient) -> None:
    payment_id = str(uuid.uuid4())
    stale_at = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    fake_service.client.tables["payments"].rows.append(
        {
            "id": payment_id,
            "checkout_group_id": CHECKOUT_GROUP_ID,
            "status": PaymentStatus.SUCCESS.value,
            "lenco_reference": "ord-already-done",
            "amount_ngwee": 10_000,
            "rail": "mtn",
            "provider": "lenco",
            "raw": {},
            "updated_at": stale_at,
        }
    )

    async def query_status(_request: Any) -> QueryStatusResult:
        return QueryStatusResult(
            reference="ord-already-done",
            status="successful",
            amount_major="100.00",
        )

    first = await poll_non_terminal_payments(
        fake_service,
        query_status=query_status,
        older_than_minutes=1,
    )
    second = await poll_non_terminal_payments(
        fake_service,
        query_status=query_status,
        older_than_minutes=1,
    )
    assert first.scanned == 0
    assert second.scanned == 0
    assert len(fake_service.client.tables["audit_log"].rows) == 0


@pytest.mark.asyncio
async def test_daily_report_idempotent_rerun(fake_service: FakeServiceClient) -> None:
    report_date = date(2026, 7, 9)

    async def fetch_account() -> LencoAccountSnapshot:
        return LencoAccountSnapshot(
            account_id="acc-1",
            available_balance_ngwee=100_000,
            ledger_balance_ngwee=100_000,
        )

    async def fetch_transactions(**_kwargs: Any) -> list[LencoTransactionRow]:
        return []

    with (
        patch(
            "app.services.payments.reconcile.fetch_ledger_platform_cash_balance_ngwee",
            return_value=100_000,
        ),
        patch(
            "app.services.payments.reconcile.fetch_ledger_day_rows",
            return_value=[],
        ),
    ):
        first: DailyReportResult = await run_daily_reconciliation_report(
            fake_service,
            report_date=report_date,
            fetch_account=fetch_account,
            fetch_transactions=fetch_transactions,
        )
        second: DailyReportResult = await run_daily_reconciliation_report(
            fake_service,
            report_date=report_date,
            fetch_account=fetch_account,
            fetch_transactions=fetch_transactions,
        )

    assert first.created is True
    assert first.clean is True
    assert second.created is False
    assert second.report_id == first.report_id
    assert len(fake_service.client.tables["reconciliation_reports"].rows) == 1


@pytest.mark.asyncio
async def test_daily_report_flags_injected_mismatch(fake_service: FakeServiceClient) -> None:
    report_date = date(2026, 7, 8)

    async def fetch_account() -> LencoAccountSnapshot:
        return LencoAccountSnapshot(
            account_id="acc-1",
            available_balance_ngwee=200_000,
            ledger_balance_ngwee=200_000,
        )

    async def fetch_transactions(**_kwargs: Any) -> list[LencoTransactionRow]:
        return [
            LencoTransactionRow(
                id="l-orphan",
                amount_ngwee=50_000,
                txn_type="credit",
                narration="Transfer / ord-orphan",
                reference="ord-orphan",
                datetime="2026-07-08T09:00:00Z",
            )
        ]

    with (
        patch(
            "app.services.payments.reconcile.fetch_ledger_platform_cash_balance_ngwee",
            return_value=100_000,
        ),
        patch(
            "app.services.payments.reconcile.fetch_ledger_day_rows",
            return_value=[
                LedgerDayRow(
                    transaction_id="t-only",
                    kind="charge_received",
                    payment_id="p-only",
                    lenco_reference="ord-ledger-only",
                    amount_ngwee=30_000,
                    created_at="2026-07-08T10:00:00Z",
                )
            ],
        ),
    ):
        result = await run_daily_reconciliation_report(
            fake_service,
            report_date=report_date,
            fetch_account=fetch_account,
            fetch_transactions=fetch_transactions,
        )

    assert result.clean is False
    assert result.discrepancies["balance_diff_ngwee"] == 100_000
    assert len(result.discrepancies["orphaned_lenco"]) == 1
    assert len(result.discrepancies["ledger_only"]) == 1


class TestInternalReconciliationRouter:
    def test_poll_tick_requires_internal_token(self, client: Any) -> None:
        denied = client.post("/internal/reconciliation/poll-tick")
        assert denied.status_code == 401

        with patch(
            "app.routers.internal_reconciliation.poll_non_terminal_payments",
            new_callable=AsyncMock,
            return_value=PollResult(scanned=0, updated=0, unchanged=0, errors=0),
        ):
            ok = client.post(
                "/internal/reconciliation/poll-tick",
                headers={"X-Internal-Token": "dev-internal-reconciliation"},
            )
        assert ok.status_code == 200
        assert ok.json() == {
            "scanned": 0,
            "updated": 0,
            "unchanged": 0,
            "errors": 0,
        }

    def test_daily_report_requires_internal_token(self, client: Any) -> None:
        denied = client.post("/internal/reconciliation/daily-report")
        assert denied.status_code == 401


@pytest.fixture(scope="module")
def db() -> Generator[PgConn, None, None]:
    import shutil

    if shutil.which("psql") is None:
        pytest.skip("psql not available")
    url = resolve_db_url()
    conn = PgConn(url)
    if not conn.run("SELECT 1").ok:
        pytest.skip(f"Postgres not reachable at {url}")
    if not schema_ready(conn):
        conn.run("DROP SCHEMA IF EXISTS public CASCADE")
        conn.run("CREATE SCHEMA public")
        conn.run("DROP SCHEMA IF EXISTS auth CASCADE")
        apply_migrations(conn)
    yield conn


class TestMigration0018:
    def test_migration_replays_clean(self, db: PgConn) -> None:
        discrepancies = (
            '{"balance_diff_ngwee": 0, "orphaned_lenco": [], '
            '"ledger_only": [], "ngwee_mismatches": []}'
        )
        result = db.run(
            f"""
            INSERT INTO public.reconciliation_reports (report_date, summary, discrepancies)
            VALUES (
              '2026-07-01',
              '{{"clean": true}}'::jsonb,
              '{discrepancies}'::jsonb
            )
            RETURNING id::text;
            """
        )
        assert result.ok, result.error

        dup = db.run(
            """
            INSERT INTO public.reconciliation_reports (report_date, summary, discrepancies)
            VALUES ('2026-07-01', '{}'::jsonb, '{}'::jsonb);
            """
        )
        assert not dup.ok

    def test_db_ts_includes_reconciliation_reports(self) -> None:
        from pathlib import Path

        db_ts = Path(__file__).resolve().parents[3] / "packages" / "types" / "src" / "db.ts"
        content = db_ts.read_text(encoding="utf-8")
        assert "reconciliation_reports" in content
        assert "report_date" in content
        assert "discrepancies" in content


# --- Webhook drain (MoMo/USSD fast-path confirmation) ------------------------


def _seed_payment(
    fake_service: FakeServiceClient,
    *,
    payment_id: str,
    reference: str,
    status: PaymentStatus,
) -> None:
    fake_service.client.tables["payments"].rows.append(
        {
            "id": payment_id,
            "checkout_group_id": CHECKOUT_GROUP_ID,
            "status": status.value,
            "lenco_reference": reference,
            "amount_ngwee": 25_000,
            "rail": "mtn",
            "provider": "lenco",
            "raw": {},
        }
    )


def _seed_webhook(
    fake_service: FakeServiceClient,
    *,
    event_id: str,
    event: str,
    reference: str,
    status: str,
    created_at: str,
    processed_at: str | None = None,
) -> str:
    row_id = str(uuid.uuid4())
    fake_service.client.table("webhook_events").rows.append(
        {
            "id": row_id,
            "provider": "lenco",
            "event_id": event_id,
            "signature_valid": True,
            "processed_at": processed_at,
            "created_at": created_at,
            "raw": {
                "event": event,
                "data": {"id": event_id, "reference": reference, "status": status},
            },
        }
    )
    return row_id


def test_webhook_drain_applies_stored_success_webhook(fake_service: FakeServiceClient) -> None:
    """A stored collection.successful webhook confirms the USSD payment on drain."""
    payment_id = str(uuid.uuid4())
    _seed_payment(
        fake_service,
        payment_id=payment_id,
        reference="ord-drain-1",
        status=PaymentStatus.USSD_PUSHED,
    )
    webhook_id = _seed_webhook(
        fake_service,
        event_id="evt-drain-1",
        event="collection.successful",
        reference="ord-drain-1",
        status="successful",
        created_at="2026-07-15T10:00:00Z",
    )

    result = drain_pending_webhook_events(fake_service)

    assert result == DrainResult(scanned=1, applied=1, skipped=0, errors=0)
    payments = {row["id"]: row for row in fake_service.client.tables["payments"].rows}
    assert payments[payment_id]["status"] == PaymentStatus.SUCCESS.value
    webhooks = {row["id"]: row for row in fake_service.client.tables["webhook_events"].rows}
    assert webhooks[webhook_id]["processed_at"] is not None
    audit_rows = fake_service.client.tables["audit_log"].rows
    assert len(audit_rows) == 1
    assert audit_rows[0]["actor"] == SYSTEM_ACTOR_ID


def test_webhook_drain_ignores_already_processed_rows(fake_service: FakeServiceClient) -> None:
    """Rows with processed_at set are filtered out server-side — never re-scanned."""
    payment_id = str(uuid.uuid4())
    _seed_payment(
        fake_service,
        payment_id=payment_id,
        reference="ord-drain-done",
        status=PaymentStatus.USSD_PUSHED,
    )
    _seed_webhook(
        fake_service,
        event_id="evt-done",
        event="collection.successful",
        reference="ord-drain-done",
        status="successful",
        created_at="2026-07-15T09:00:00Z",
        processed_at="2026-07-15T09:00:05Z",
    )

    result = drain_pending_webhook_events(fake_service)

    assert result == DrainResult(scanned=0, applied=0, skipped=0, errors=0)
    payments = {row["id"]: row for row in fake_service.client.tables["payments"].rows}
    assert payments[payment_id]["status"] == PaymentStatus.USSD_PUSHED.value


def test_webhook_drain_marks_unmatched_reference_and_is_idempotent(
    fake_service: FakeServiceClient,
) -> None:
    """A webhook for an unknown payment is marked processed (skipped), not re-scanned."""
    _seed_webhook(
        fake_service,
        event_id="evt-orphan",
        event="collection.successful",
        reference="ord-no-such-payment",
        status="successful",
        created_at="2026-07-15T10:00:00Z",
    )

    first = drain_pending_webhook_events(fake_service)
    second = drain_pending_webhook_events(fake_service)

    assert first == DrainResult(scanned=1, applied=0, skipped=1, errors=0)
    assert second == DrainResult(scanned=0, applied=0, skipped=0, errors=0)


def test_webhook_drain_isolates_anomaly_and_continues_batch(
    fake_service: FakeServiceClient,
) -> None:
    """An illegal-transition webhook is logged/skipped; healthy ones still apply.

    The anomaly is a collection.failed webhook for a payment still at INITIATED
    (no INITIATED->failed edge). It must not abort the batch, its row stays
    unprocessed (visible to the re-query poller), and the healthy success webhook
    in the same batch still confirms its payment.
    """
    poison_payment = str(uuid.uuid4())
    _seed_payment(
        fake_service,
        payment_id=poison_payment,
        reference="ord-anomaly",
        status=PaymentStatus.INITIATED,  # no edge to failed
    )
    poison_webhook = _seed_webhook(
        fake_service,
        event_id="evt-anomaly",
        event="collection.failed",
        reference="ord-anomaly",
        status="failed",
        created_at="2026-07-15T10:00:00Z",
    )

    healthy_payment = str(uuid.uuid4())
    _seed_payment(
        fake_service,
        payment_id=healthy_payment,
        reference="ord-healthy",
        status=PaymentStatus.USSD_PUSHED,
    )
    healthy_webhook = _seed_webhook(
        fake_service,
        event_id="evt-healthy",
        event="collection.successful",
        reference="ord-healthy",
        status="successful",
        created_at="2026-07-15T10:00:01Z",
    )

    result = drain_pending_webhook_events(fake_service)

    assert result == DrainResult(scanned=2, applied=1, skipped=0, errors=1)
    payments = {row["id"]: row for row in fake_service.client.tables["payments"].rows}
    assert payments[healthy_payment]["status"] == PaymentStatus.SUCCESS.value
    assert payments[poison_payment]["status"] == PaymentStatus.INITIATED.value
    webhooks = {row["id"]: row for row in fake_service.client.tables["webhook_events"].rows}
    # Healthy row processed; anomalous row left for the poller / admin visibility.
    assert webhooks[healthy_webhook]["processed_at"] is not None
    assert webhooks[poison_webhook]["processed_at"] is None
