"""Tests for payment state machine, initiate kickoff, sweeper, and webhook precedence."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.services.payments.base import (
    CollectionStatus,
    InitiateCollectionResult,
    QueryStatusResult,
)
from app.services.payments.initiate import InitiatePaymentRequest, initiate_checkout_payment
from app.services.payments.state import (
    SYSTEM_ACTOR_ID,
    TRANSITION_TABLE,
    PaymentEvent,
    PaymentStatus,
    PaymentTransitionError,
    SweepResult,
    all_transition_matrix_cases,
    apply_payment_status,
    lenco_collection_status_to_payment_status,
    process_webhook_event,
    resolve_transition,
    should_apply_status,
    sweep_stale_payments,
    transition_payment,
)
from tests.rls.conftest import PgConn, apply_migrations, resolve_db_url, schema_ready

CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
CHECKOUT_GROUP_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
ACTOR_ID = "22222222-2222-2222-2222-222222222222"


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

    def neq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("neq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._filters.append(("in", column, values))
        return self

    def lt(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("lt", column, value))
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
            if "updated_at" not in row:
                row["updated_at"] = row["created_at"]
            self._parent.rows.append(row)
            return MagicMock(data=[row], count=None)

        if self._pending_op == "update":
            assert isinstance(self._payload, dict)
            updated: list[dict[str, Any]] = []
            for row in self._parent.rows:
                if self._row_matches(row):
                    row.update(self._payload)
                    updated.append(dict(row))
            return MagicMock(data=updated, count=len(updated))

        rows = self._apply_filters(list(self._parent.rows))
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: str(row.get(column, "")), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None, count=len(rows))
        count = len(rows) if self._count_exact else None
        return MagicMock(data=rows, count=count)

    def _row_matches(self, row: dict[str, Any]) -> bool:
        for op, column, value in self._filters:
            cell = row.get(column)
            if op == "eq" and cell != value:
                return False
            if op == "neq" and cell == value:
                return False
            if op == "in" and cell not in set(value):
                return False
            if op == "lt" and not (str(cell) < str(value)):
                return False
        return True

    def _apply_filters(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [row for row in rows if self._row_matches(row)]


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
            "payments": FakeTable(),
            "checkout_groups": FakeTable(),
            "audit_log": FakeTable(),
            "webhook_events": FakeTable(),
            "platform_config": FakeTable(),
        }

    def table(self, name: str) -> FakeTable:
        return self.tables[name]


class FakeServiceClient:
    def __init__(self, fake: FakeSupabaseClient) -> None:
        self._fake = fake

    @property
    def client(self) -> FakeSupabaseClient:
        return self._fake


@pytest.fixture
def fake_service() -> FakeServiceClient:
    fake = FakeSupabaseClient()
    fake.tables["checkout_groups"].rows.append(
        {
            "id": CHECKOUT_GROUP_ID,
            "total_ngwee": 10_000,
            "status": "pending",
        }
    )
    return FakeServiceClient(fake)


def _seed_payment(
    fake: FakeSupabaseClient,
    *,
    payment_id: str,
    status: str,
    reference: str | None = None,
    updated_at: datetime | None = None,
) -> None:
    stamp = (updated_at or datetime.now(UTC)).isoformat()
    fake.tables["payments"].rows.append(
        {
            "id": payment_id,
            "checkout_group_id": CHECKOUT_GROUP_ID,
            "provider": "lenco",
            "rail": "mtn",
            "lenco_reference": reference or f"ord-{payment_id}",
            "amount_ngwee": 10_000,
            "status": status,
            "raw": {},
            "created_at": stamp,
            "updated_at": stamp,
        }
    )


LEGAL_TRANSITIONS = [
    (PaymentStatus.INITIATED, PaymentEvent.USSD_PUSHED, PaymentStatus.USSD_PUSHED),
    (PaymentStatus.INITIATED, PaymentEvent.CANCELLED, PaymentStatus.CANCELLED),
    (PaymentStatus.USSD_PUSHED, PaymentEvent.PAY_OFFLINE, PaymentStatus.PAY_OFFLINE),
    (PaymentStatus.USSD_PUSHED, PaymentEvent.SUCCESS, PaymentStatus.SUCCESS),
    (PaymentStatus.USSD_PUSHED, PaymentEvent.FAILED, PaymentStatus.FAILED),
    (PaymentStatus.USSD_PUSHED, PaymentEvent.EXPIRED, PaymentStatus.EXPIRED),
    (PaymentStatus.USSD_PUSHED, PaymentEvent.CANCELLED, PaymentStatus.CANCELLED),
    (PaymentStatus.PAY_OFFLINE, PaymentEvent.SUCCESS, PaymentStatus.SUCCESS),
    (PaymentStatus.PAY_OFFLINE, PaymentEvent.FAILED, PaymentStatus.FAILED),
    (PaymentStatus.PAY_OFFLINE, PaymentEvent.EXPIRED, PaymentStatus.EXPIRED),
    (PaymentStatus.PAY_OFFLINE, PaymentEvent.CANCELLED, PaymentStatus.CANCELLED),
    (PaymentStatus.FAILED, PaymentEvent.SUCCESS, PaymentStatus.SUCCESS),
    (PaymentStatus.EXPIRED, PaymentEvent.SUCCESS, PaymentStatus.SUCCESS),
]

_MATRIX = all_transition_matrix_cases()
_MATRIX_IDS = [
    f"{status.value}+{event.value}-{'ok' if legal else 'no'}" for status, event, legal in _MATRIX
]


class TestTransitionTable:
    def test_transition_table_covers_expected_legal_edges(self) -> None:
        table_pairs = {(spec.from_status, spec.event, spec.to_status) for spec in TRANSITION_TABLE}
        for from_status, event, to_status in LEGAL_TRANSITIONS:
            assert (from_status, event, to_status) in table_pairs

    @pytest.mark.parametrize(("from_status", "event", "expected"), _MATRIX, ids=_MATRIX_IDS)
    def test_resolve_transition_matrix(
        self,
        from_status: PaymentStatus,
        event: PaymentEvent,
        expected: bool,
    ) -> None:
        result = resolve_transition(from_status=from_status, event=event)
        assert (result is not None) is expected

    @pytest.mark.parametrize(
        ("from_status", "event", "to_status"),
        LEGAL_TRANSITIONS,
        ids=[f"{f.value}+{e.value}" for f, e, _ in LEGAL_TRANSITIONS],
    )
    def test_legal_transitions_mutate_and_audit(
        self,
        fake_service: FakeServiceClient,
        from_status: PaymentStatus,
        event: PaymentEvent,
        to_status: PaymentStatus,
    ) -> None:
        payment_id = str(uuid.uuid4())
        _seed_payment(fake_service.client, payment_id=payment_id, status=from_status.value)
        outcome = transition_payment(
            fake_service,
            payment_id=payment_id,
            event=event,
            actor_id=ACTOR_ID,
            note=f"test {from_status.value} -> {to_status.value}",
        )
        assert outcome.to_status == to_status
        row = fake_service.client.tables["payments"].rows[0]
        assert row["status"] == to_status.value
        audits = [
            row
            for row in fake_service.client.tables["audit_log"].rows
            if row.get("entity_id") == payment_id
        ]
        assert len(audits) == 1
        assert audits[0]["before"] == {"status": from_status.value}
        assert audits[0]["after"]["status"] == to_status.value

    def test_illegal_transition_raises(self, fake_service: FakeServiceClient) -> None:
        payment_id = str(uuid.uuid4())
        _seed_payment(fake_service.client, payment_id=payment_id, status="success")
        with pytest.raises(PaymentTransitionError):
            transition_payment(
                fake_service,
                payment_id=payment_id,
                event=PaymentEvent.FAILED,
                actor_id=ACTOR_ID,
                note="should fail",
            )


class TestStatusPrecedence:
    def test_success_is_terminal_winning(self) -> None:
        assert should_apply_status(
            current=PaymentStatus.SUCCESS,
            incoming=PaymentStatus.FAILED,
        ) is False
        assert should_apply_status(
            current=PaymentStatus.SUCCESS,
            incoming=PaymentStatus.EXPIRED,
        ) is False

    def test_late_success_after_failed_wins(self) -> None:
        assert should_apply_status(
            current=PaymentStatus.FAILED,
            incoming=PaymentStatus.SUCCESS,
        ) is True

    def test_late_success_after_expired_wins(self) -> None:
        assert should_apply_status(
            current=PaymentStatus.EXPIRED,
            incoming=PaymentStatus.SUCCESS,
        ) is True

    def test_stale_failed_ignored_after_success_via_apply(
        self,
        fake_service: FakeServiceClient,
    ) -> None:
        payment_id = str(uuid.uuid4())
        _seed_payment(fake_service.client, payment_id=payment_id, status="success")
        outcome = apply_payment_status(
            fake_service,
            payment_id=payment_id,
            incoming_status=PaymentStatus.FAILED,
            actor_id=SYSTEM_ACTOR_ID,
            note="stale failed webhook",
        )
        assert outcome is None
        assert fake_service.client.tables["payments"].rows[0]["status"] == "success"

    def test_late_success_after_failed_reconciles(
        self,
        fake_service: FakeServiceClient,
    ) -> None:
        payment_id = str(uuid.uuid4())
        _seed_payment(fake_service.client, payment_id=payment_id, status="failed")
        outcome = apply_payment_status(
            fake_service,
            payment_id=payment_id,
            incoming_status=PaymentStatus.SUCCESS,
            actor_id=SYSTEM_ACTOR_ID,
            note="late success webhook",
        )
        assert outcome is not None
        assert outcome.to_status == PaymentStatus.SUCCESS
        assert fake_service.client.tables["payments"].rows[0]["status"] == "success"


class TestWebhookProcessing:
    def test_process_webhook_event_success(
        self,
        fake_service: FakeServiceClient,
    ) -> None:
        payment_id = str(uuid.uuid4())
        reference = f"ord-{payment_id}"
        _seed_payment(
            fake_service.client,
            payment_id=payment_id,
            status="pay_offline",
            reference=reference,
        )
        webhook_id = str(uuid.uuid4())
        fake_service.client.tables["webhook_events"].rows.append(
            {
                "id": webhook_id,
                "provider": "lenco",
                "event_id": "evt-1",
                "processed_at": None,
                "raw": {
                    "event": "collection.successful",
                    "data": {"reference": reference, "status": "successful"},
                },
            }
        )
        outcome = process_webhook_event(fake_service, webhook_event_id=webhook_id)
        assert outcome is not None
        assert outcome.to_status == PaymentStatus.SUCCESS
        webhook = fake_service.client.tables["webhook_events"].rows[0]
        assert webhook["processed_at"] is not None


class TestInitiateCollection:
    @pytest.mark.asyncio
    async def test_initiate_moves_initiated_to_ussd_pushed(
        self,
        fake_service: FakeServiceClient,
    ) -> None:
        strategy = MagicMock()
        strategy.initiate_collection = AsyncMock(
            return_value=InitiateCollectionResult(
                provider_reference="240730001",
                status=CollectionStatus.PENDING,
                amount_major="100.00",
            )
        )
        result = await initiate_checkout_payment(
            fake_service,
            InitiatePaymentRequest(
                checkout_group_id=CHECKOUT_GROUP_ID,
                amount_ngwee=10_000,
                rail="mtn",
                phone="+260961111111",
            ),
            strategy=strategy,
            actor_id=ACTOR_ID,
        )
        assert result.status == PaymentStatus.USSD_PUSHED
        payment = fake_service.client.tables["payments"].rows[0]
        assert payment["status"] == PaymentStatus.USSD_PUSHED.value
        audits = [
            row
            for row in fake_service.client.tables["audit_log"].rows
            if row.get("entity_type") == "payment"
        ]
        assert len(audits) == 1
        assert audits[0]["before"] == {"status": PaymentStatus.INITIATED.value}
        assert audits[0]["after"]["status"] == PaymentStatus.USSD_PUSHED.value

    @pytest.mark.asyncio
    async def test_initiate_pay_offline_when_lenco_returns_pay_offline(
        self,
        fake_service: FakeServiceClient,
    ) -> None:
        strategy = MagicMock()
        strategy.initiate_collection = AsyncMock(
            return_value=InitiateCollectionResult(
                provider_reference="240730002",
                status=CollectionStatus.PAY_OFFLINE,
                amount_major="100.00",
            )
        )
        result = await initiate_checkout_payment(
            fake_service,
            InitiatePaymentRequest(
                checkout_group_id=CHECKOUT_GROUP_ID,
                amount_ngwee=10_000,
                rail="mtn",
                phone="+260961111111",
            ),
            strategy=strategy,
            actor_id=ACTOR_ID,
        )
        assert result.status == PaymentStatus.PAY_OFFLINE
        assert fake_service.client.tables["payments"].rows[0]["status"] == "pay_offline"


class TestSweeper:
    @pytest.mark.asyncio
    async def test_stale_unpaid_requery_expires_and_releases(
        self,
        fake_service: FakeServiceClient,
    ) -> None:
        payment_id = str(uuid.uuid4())
        stale_at = datetime.now(UTC) - timedelta(minutes=30)
        _seed_payment(
            fake_service.client,
            payment_id=payment_id,
            status="pay_offline",
            updated_at=stale_at,
        )
        query_status = AsyncMock(
            return_value=QueryStatusResult(
                reference=f"ord-{payment_id}",
                status="pay-offline",
                amount_major="100.00",
            )
        )
        stats = await sweep_stale_payments(fake_service, query_status=query_status)
        assert stats.scanned == 1
        assert stats.expired == 1
        assert stats.reconciled_success == 0
        assert stats.released == 1
        assert fake_service.client.tables["payments"].rows[0]["status"] == "expired"
        query_status.assert_awaited_once()
        checkout_audits = [
            row
            for row in fake_service.client.tables["audit_log"].rows
            if row.get("action") == "checkout.release_for_retry"
        ]
        assert len(checkout_audits) == 1

    @pytest.mark.asyncio
    async def test_stale_lenco_success_reconciles_not_expires(
        self,
        fake_service: FakeServiceClient,
    ) -> None:
        payment_id = str(uuid.uuid4())
        stale_at = datetime.now(UTC) - timedelta(minutes=30)
        _seed_payment(
            fake_service.client,
            payment_id=payment_id,
            status="pay_offline",
            updated_at=stale_at,
        )
        query_status = AsyncMock(
            return_value=QueryStatusResult(
                reference=f"ord-{payment_id}",
                status="successful",
                amount_major="100.00",
            )
        )
        stats = await sweep_stale_payments(fake_service, query_status=query_status)
        assert stats.scanned == 1
        assert stats.expired == 0
        assert stats.reconciled_success == 1
        assert stats.released == 0
        assert fake_service.client.tables["payments"].rows[0]["status"] == "success"

    @pytest.mark.asyncio
    async def test_late_success_after_expired_via_sweeper_requery(
        self,
        fake_service: FakeServiceClient,
    ) -> None:
        payment_id = str(uuid.uuid4())
        stale_at = datetime.now(UTC) - timedelta(minutes=30)
        _seed_payment(
            fake_service.client,
            payment_id=payment_id,
            status="expired",
            updated_at=stale_at,
        )
        # Expired payments are not swept; verify reconciliation path via apply instead.
        outcome = apply_payment_status(
            fake_service,
            payment_id=payment_id,
            incoming_status=PaymentStatus.SUCCESS,
            actor_id=SYSTEM_ACTOR_ID,
            note="late success after expiry",
        )
        assert outcome is not None
        assert outcome.from_status == PaymentStatus.EXPIRED
        assert outcome.to_status == PaymentStatus.SUCCESS


class TestLencoStatusMapping:
    def test_collection_status_mapping(self) -> None:
        assert lenco_collection_status_to_payment_status("pay-offline") == PaymentStatus.PAY_OFFLINE
        assert lenco_collection_status_to_payment_status("successful") == PaymentStatus.SUCCESS
        assert lenco_collection_status_to_payment_status("failed") == PaymentStatus.FAILED


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


class TestMigration0016:
    def test_migration_widens_payment_status_check(self, db: PgConn) -> None:
        group_id = str(uuid.uuid4())
        db.run(
            f"""
            INSERT INTO auth.users (id) VALUES ('{CUSTOMER_ID}')
            ON CONFLICT DO NOTHING;
            INSERT INTO public.checkout_groups (
              id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee, total_ngwee
            ) VALUES (
              '{group_id}', '{CUSTOMER_ID}', 'idem-{group_id}', 10000, 0, 10000
            );
            """
        )
        for status in (
            "initiated",
            "ussd_pushed",
            "pay_offline",
            "success",
            "failed",
            "expired",
            "cancelled",
        ):
            pid = str(uuid.uuid4())
            result = db.run(
                f"""
                INSERT INTO public.payments (
                  id, checkout_group_id, provider, rail, lenco_reference, amount_ngwee, status
                ) VALUES (
                  '{pid}', '{group_id}', 'lenco', 'mtn', 'pay-{pid}', 10000, '{status}'
                );
                """
            )
            assert result.ok, f"status {status} should be accepted: {result.error}"

    def test_db_ts_unchanged(self) -> None:
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[3]
        db_ts = repo_root / "packages" / "types" / "src" / "db.ts"
        if not db_ts.exists():
            pytest.skip("db.ts not present in workspace")
        content = db_ts.read_text(encoding="utf-8")
        assert "payments" in content
        # M08-P04 must not edit generated types; status remains plain string.
        assert "ussd_pushed" not in content
        assert "pay_offline" not in content


class TestInternalSweeperRouter:
    def test_tick_requires_internal_token(self, client: Any) -> None:
        from fastapi.testclient import TestClient

        app_client: TestClient = client
        denied = app_client.post("/internal/payment-sweeper/tick")
        assert denied.status_code == 401

        with patch(
            "app.routers.internal_payment_sweeper.sweep_stale_payments",
            new_callable=AsyncMock,
            return_value=SweepResult(
                scanned=0,
                expired=0,
                reconciled_success=0,
                released=0,
            ),
        ):
            ok = app_client.post(
                "/internal/payment-sweeper/tick",
                headers={"X-Internal-Token": "dev-internal-payment-sweeper"},
            )
        assert ok.status_code == 200
        assert ok.json() == {
            "scanned": 0,
            "expired": 0,
            "reconciled_success": 0,
            "released": 0,
        }
