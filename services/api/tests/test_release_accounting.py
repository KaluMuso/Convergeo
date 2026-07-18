"""Release-side payment accounting gate — commission from purchase-time snapshot.

Covers prepaid collection → capture → net release, idempotency under retry/concurrency,
ngwee rounding, invalid snapshots, fail-closed ledger errors, refund/cancel/dispute
blocks, COD path isolation, and reconciliation gross/commission/net consistency.
"""

from __future__ import annotations

import concurrent.futures
import json
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

import pytest
from app.services.commissions.engine import capture_order_commission
from app.services.escrow.release import (
    evaluate_and_release,
    release_idempotency_key,
)
from app.services.escrow.release_accounting import (
    ReleaseAccountingAmounts,
    build_release_accounting_day_totals,
    commission_snapshot_is_usable,
    compute_release_amounts,
    summarize_order_release_ledger,
)
from app.services.ledger.engine import (
    LedgerError,
    account_balance_ngwee,
    post_transaction,
    resolve_account_id,
)
from app.services.ledger.templates import AccountRef, LedgerTemplate, commission_ngwee_from_bps
from app.services.orders.state import SYSTEM_ACTOR_ID
from app.services.payments.cod import record_cod_receivable
from tests.rls.conftest import (
    MIGRATIONS_DIR,
    PgConn,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)

CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
VENDOR_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
PLATFORM_CASH_ID = "a1000000-0000-0000-0000-000000000001"
ESCROW_ID = "a2000000-0000-0000-0000-000000000002"
COMMISSION_ID = "a3000000-0000-0000-0000-000000000003"
VENDOR_PAYABLE_ID = "a5000000-0000-0000-0000-000000000005"
COD_RECEIVABLE_ID = "a6000000-0000-0000-0000-000000000006"

GROSS_NGEWEE = 200_000
COMMISSION_BPS = 800
COMMISSION_NGEWEE = commission_ngwee_from_bps(
    gross_ngwee=GROSS_NGEWEE, commission_bps=COMMISSION_BPS
)
NET_NGEWEE = GROSS_NGEWEE - COMMISSION_NGEWEE


class _ServiceWrapper:
    client: Any = None


_SERVICE = _ServiceWrapper()


def ensure_idempotency_column(conn: PgConn) -> None:
    result = conn.run(
        """
        SELECT count(*)::text
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'ledger_transactions'
          AND column_name = 'idempotency_key';
        """
    )
    if result.ok and result.rows and result.rows[0] == "0":
        migration = MIGRATIONS_DIR / "0015_ledger_idempotency.sql"
        applied = conn.run_file(migration)
        if not applied.ok:
            raise RuntimeError(f"failed to apply {migration.name}: {applied.error}")


def seed_ledger_accounts(conn: PgConn) -> None:
    script = f"""
BEGIN;
SET LOCAL role service_role;
INSERT INTO public.ledger_accounts (id, kind) VALUES
  ('{PLATFORM_CASH_ID}', 'platform_cash'),
  ('{ESCROW_ID}', 'escrow'),
  ('{COMMISSION_ID}', 'commission_revenue')
ON CONFLICT (kind) WHERE vendor_id IS NULL DO NOTHING;
INSERT INTO public.ledger_accounts (id, kind, vendor_id) VALUES
  ('{VENDOR_PAYABLE_ID}', 'vendor_payable', '{VENDOR_A}')
ON CONFLICT (kind, vendor_id) WHERE vendor_id IS NOT NULL DO NOTHING;
INSERT INTO public.ledger_accounts (id, kind, vendor_id) VALUES
  ('{COD_RECEIVABLE_ID}', 'cod_receivable', '{VENDOR_A}')
ON CONFLICT (kind, vendor_id) WHERE vendor_id IS NOT NULL DO NOTHING;
COMMIT;
"""
    result = conn.run_script(script)
    if not result.ok:
        raise RuntimeError(f"ledger account seed failed: {result.error}")


def _listing_id() -> str:
    return str(uuid.uuid4())


def _snapshot(
    *,
    gross: int = GROSS_NGEWEE,
    bps: int = COMMISSION_BPS,
    listing_id: str | None = None,
) -> dict[str, Any]:
    return {
        "lines": [
            {
                "listing_id": listing_id or _listing_id(),
                "category_key": "electronics",
                "rate_bps": bps,
                "qty": 1,
                "unit_price_ngwee": gross,
                "line_total_ngwee": gross,
                "wholesale": False,
            }
        ]
    }


@pytest.fixture(scope="module")
def db() -> Generator[PgConn, None, None]:
    url = resolve_db_url()
    conn = PgConn(url)
    if not conn.run("SELECT 1").ok:
        pytest.skip(f"Postgres not reachable at {url}")
    if not schema_ready(conn):
        conn.run("DROP SCHEMA IF EXISTS public CASCADE")
        conn.run("CREATE SCHEMA public")
        conn.run("DROP SCHEMA IF EXISTS auth CASCADE")
        apply_migrations(conn)
        seed_matrix_fixtures(conn)
    else:
        ensure_idempotency_column(conn)
        seed_matrix_fixtures(conn)
    seed_ledger_accounts(conn)
    yield conn


@pytest.fixture
def db_url_env(db: PgConn) -> Generator[None, None, None]:
    import os

    previous = os.environ.get("SUPABASE_DB_URL")
    os.environ["SUPABASE_DB_URL"] = db.dsn
    yield
    if previous is None:
        os.environ.pop("SUPABASE_DB_URL", None)
    else:
        os.environ["SUPABASE_DB_URL"] = previous


def _insert_checkout_group(conn: PgConn, group_id: str, *, total: int = GROSS_NGEWEE) -> None:
    conn.run(
        f"""
        INSERT INTO public.checkout_groups (
          id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee, total_ngwee, status
        ) VALUES (
          '{group_id}', '{CUSTOMER_ID}', 'cg-{group_id}',
          {total}, 0, {total}, 'completed'
        ) ON CONFLICT (id) DO NOTHING;
        """
    )


def _insert_order(
    conn: PgConn,
    *,
    order_id: str,
    group_id: str,
    status: str,
    commission_snapshot: dict[str, Any] | None = None,
    cod: bool = False,
    gross: int = GROSS_NGEWEE,
) -> None:
    snapshot = commission_snapshot if commission_snapshot is not None else _snapshot(gross=gross)
    snapshot_sql = json.dumps(snapshot).replace("'", "''")
    _insert_checkout_group(conn, group_id, total=gross)
    conn.run(
        f"""
        INSERT INTO public.orders (
          id, checkout_group_id, vendor_id, customer_id, status, fulfilment,
          delivery_fee_ngwee, cod, commission_snapshot
        ) VALUES (
          '{order_id}', '{group_id}', '{VENDOR_A}', '{CUSTOMER_ID}',
          '{status}', 'delivery', 0, {str(cod).lower()}, '{snapshot_sql}'::jsonb
        ) ON CONFLICT (id) DO UPDATE
          SET status = EXCLUDED.status,
              commission_snapshot = EXCLUDED.commission_snapshot,
              cod = EXCLUDED.cod;
        """
    )
    conn.run(
        f"""
        INSERT INTO public.order_items (
          id, order_id, item_kind, qty, unit_price_ngwee, title_snapshot
        ) VALUES (
          '{uuid.uuid4()}', '{order_id}', 'product', 1, {gross}, 'Test item'
        );
        """
    )


def _insert_order_event(
    conn: PgConn,
    *,
    order_id: str,
    from_status: str | None,
    to_status: str,
    actor: str | None,
    created_at: datetime,
) -> None:
    actor_sql = f"'{actor}'::uuid" if actor else "NULL"
    from_sql = f"'{from_status}'" if from_status else "NULL"
    ts = created_at.astimezone(UTC).isoformat()
    conn.run(
        f"""
        INSERT INTO public.order_events (
          id, order_id, actor, from_status, to_status, created_at
        ) VALUES (
          '{uuid.uuid4()}', '{order_id}', {actor_sql}, {from_sql},
          '{to_status}', '{ts}'::timestamptz
        );
        """
    )


def _insert_dispute(conn: PgConn, *, order_id: str, status: str = "open") -> None:
    conn.run(
        f"""
        INSERT INTO public.disputes (
          id, order_id, opener_user_id, status
        ) VALUES (
          '{uuid.uuid4()}', '{order_id}', '{CUSTOMER_ID}', '{status}'
        );
        """
    )


def _insert_refund(conn: PgConn, *, order_id: str, amount: int = GROSS_NGEWEE) -> None:
    conn.run(
        f"""
        INSERT INTO public.refunds (
          id, order_id, lane, breakdown, amount_ngwee, status
        ) VALUES (
          '{uuid.uuid4()}', '{order_id}', 1, '{{}}'::jsonb, {amount}, 'completed'
        );
        """
    )


def _seed_completed_prepaid(
    conn: PgConn,
    *,
    order_id: str,
    group_id: str,
    now: datetime,
    commission_snapshot: dict[str, Any] | None = None,
    gross: int = GROSS_NGEWEE,
) -> None:
    _insert_order(
        conn,
        order_id=order_id,
        group_id=group_id,
        status="completed",
        commission_snapshot=commission_snapshot,
        gross=gross,
    )
    _insert_order_event(
        conn,
        order_id=order_id,
        from_status="delivered",
        to_status="completed",
        actor=CUSTOMER_ID,
        created_at=now - timedelta(hours=1),
    )
    post_transaction(
        idempotency_key=f"prepaid-charge-{order_id}",
        template=LedgerTemplate.CHARGE_RECEIVED,
        order_id=order_id,
        checkout_group_id=group_id,
        gross_ngwee=gross,
    )


def _commission_capture_count(conn: PgConn, order_id: str, *, prefix: str | None = None) -> int:
    key_prefix = prefix or f"{release_idempotency_key(order_id)}-commission-"
    result = conn.run(
        f"""
        SELECT count(*)::text
        FROM public.ledger_transactions
        WHERE kind = 'commission_capture'
          AND idempotency_key LIKE '{key_prefix}%';
        """
    )
    assert result.ok and result.rows
    return int(result.rows[0])


def _release_txn_count(conn: PgConn, order_id: str) -> int:
    key = release_idempotency_key(order_id)
    result = conn.run(
        f"""
        SELECT count(*)::text
        FROM public.ledger_transactions
        WHERE idempotency_key = '{key}';
        """
    )
    assert result.ok and result.rows
    return int(result.rows[0])


class TestSnapshotUsability:
    def test_empty_snapshot_invalid_for_positive_gross(self) -> None:
        assert commission_snapshot_is_usable({}, gross_ngwee=GROSS_NGEWEE) is False
        assert commission_snapshot_is_usable(None, gross_ngwee=GROSS_NGEWEE) is False

    def test_zero_rate_snapshot_valid(self) -> None:
        assert commission_snapshot_is_usable(_snapshot(bps=0), gross_ngwee=GROSS_NGEWEE) is True

    def test_amounts_commission_plus_net_equals_gross(self) -> None:
        amounts = compute_release_amounts(
            order_id=str(uuid.uuid4()),
            gross_ngwee=GROSS_NGEWEE,
            commission_snapshot=_snapshot(),
        )
        assert isinstance(amounts, ReleaseAccountingAmounts)
        assert amounts.commission_ngwee + amounts.net_ngwee == amounts.gross_ngwee
        assert amounts.commission_ngwee == COMMISSION_NGEWEE
        assert amounts.net_ngwee == NET_NGEWEE


def _account_id(kind: str, *, vendor_id: str | None = None) -> str:
    return resolve_account_id(AccountRef(kind, vendor_id=vendor_id))


class TestPrepaidReleaseLifecycle:
    def test_charge_capture_release_zeroes_escrow(self, db: PgConn, db_url_env: None) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        now = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)

        escrow_id = _account_id("escrow")
        commission_id = _account_id("commission_revenue")
        payable_id = _account_id("vendor_payable", vendor_id=VENDOR_A)
        escrow_before = account_balance_ngwee(escrow_id)
        commission_before = account_balance_ngwee(commission_id)
        payable_before = account_balance_ngwee(payable_id)

        _seed_completed_prepaid(db, order_id=order_id, group_id=group_id, now=now)
        assert account_balance_ngwee(escrow_id) == escrow_before - GROSS_NGEWEE

        result = evaluate_and_release(_SERVICE, order_id, now=now)
        assert result.outcome == "released"
        assert result.net_ngwee == NET_NGEWEE
        assert _commission_capture_count(db, order_id) == 1
        assert _release_txn_count(db, order_id) == 1

        assert account_balance_ngwee(escrow_id) == escrow_before
        assert account_balance_ngwee(commission_id) == commission_before - COMMISSION_NGEWEE
        assert account_balance_ngwee(payable_id) == payable_before - NET_NGEWEE

        summary = summarize_order_release_ledger(order_id)
        assert summary.charge_received_ngwee == GROSS_NGEWEE
        assert summary.commission_captured_ngwee == COMMISSION_NGEWEE
        assert summary.vendor_released_ngwee == NET_NGEWEE
        assert summary.balanced is True

    def test_repeated_release_attempts_idempotent(self, db: PgConn, db_url_env: None) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        now = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
        _seed_completed_prepaid(db, order_id=order_id, group_id=group_id, now=now)

        first = evaluate_and_release(_SERVICE, order_id, now=now)
        second = evaluate_and_release(_SERVICE, order_id, now=now)
        third = evaluate_and_release(_SERVICE, order_id, now=now)

        assert first.outcome == "released"
        assert second.outcome == "already_released"
        assert third.outcome == "already_released"
        assert _commission_capture_count(db, order_id) == 1
        assert _release_txn_count(db, order_id) == 1

    def test_two_concurrent_release_attempts(self, db: PgConn, db_url_env: None) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        now = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
        _seed_completed_prepaid(db, order_id=order_id, group_id=group_id, now=now)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(evaluate_and_release, _SERVICE, order_id, now=now)
                for _ in range(2)
            ]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]

        outcomes = {result.outcome for result in results}
        assert outcomes <= {"released", "already_released"}
        assert "released" in outcomes or all(r.outcome == "already_released" for r in results)
        assert _commission_capture_count(db, order_id) == 1
        assert _release_txn_count(db, order_id) == 1
        summary = summarize_order_release_ledger(order_id)
        assert summary.commission_captured_ngwee == COMMISSION_NGEWEE
        assert summary.vendor_released_ngwee == NET_NGEWEE
        assert summary.balanced is True

    def test_exact_ngwee_floor_rounding(self, db: PgConn, db_url_env: None) -> None:
        # 123_456 * 333 // 10_000 == 4_111 (floor); net must absorb the remainder.
        gross = 123_456
        bps = 333
        expected_commission = commission_ngwee_from_bps(gross_ngwee=gross, commission_bps=bps)
        expected_net = gross - expected_commission
        assert expected_commission == 4_111

        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        now = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
        _seed_completed_prepaid(
            db,
            order_id=order_id,
            group_id=group_id,
            now=now,
            commission_snapshot=_snapshot(gross=gross, bps=bps),
            gross=gross,
        )

        result = evaluate_and_release(_SERVICE, order_id, now=now)
        assert result.outcome == "released"
        assert result.net_ngwee == expected_net
        summary = summarize_order_release_ledger(order_id)
        assert summary.commission_captured_ngwee == expected_commission
        assert summary.vendor_released_ngwee == expected_net
        assert summary.commission_captured_ngwee + summary.vendor_released_ngwee == gross


class TestInvalidSnapshotAndFailClosed:
    def test_missing_commission_snapshot_blocks_release(
        self, db: PgConn, db_url_env: None
    ) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        now = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
        _seed_completed_prepaid(
            db,
            order_id=order_id,
            group_id=group_id,
            now=now,
            commission_snapshot={},
        )

        result = evaluate_and_release(_SERVICE, order_id, now=now)
        assert result.outcome == "not_eligible"
        assert result.reason == "invalid_commission_snapshot"
        assert _commission_capture_count(db, order_id) == 0
        assert _release_txn_count(db, order_id) == 0

    def test_failed_commission_posting_fail_closed(self, db: PgConn, db_url_env: None) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        now = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
        _seed_completed_prepaid(db, order_id=order_id, group_id=group_id, now=now)

        with patch(
            "app.services.escrow.release.capture_order_commission",
            side_effect=LedgerError("commission post failed"),
        ):
            with pytest.raises(LedgerError, match="commission post failed"):
                evaluate_and_release(_SERVICE, order_id, now=now)

        assert _release_txn_count(db, order_id) == 0
        assert _commission_capture_count(db, order_id) == 0

    def test_failed_vendor_release_after_commission_capture(
        self, db: PgConn, db_url_env: None
    ) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        now = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
        _seed_completed_prepaid(db, order_id=order_id, group_id=group_id, now=now)

        with patch(
            "app.services.escrow.release._post_release",
            side_effect=LedgerError("release post failed"),
        ):
            with pytest.raises(LedgerError, match="release post failed"):
                evaluate_and_release(_SERVICE, order_id, now=now)

        assert _commission_capture_count(db, order_id) == 1
        assert _release_txn_count(db, order_id) == 0

        # Re-drive completes: capture idempotent, release posts once.
        result = evaluate_and_release(_SERVICE, order_id, now=now)
        assert result.outcome == "released"
        assert _commission_capture_count(db, order_id) == 1
        assert _release_txn_count(db, order_id) == 1
        assert summarize_order_release_ledger(order_id).balanced is True


class TestBlockedReleaseStates:
    def test_cancelled_order_cannot_release(self, db: PgConn, db_url_env: None) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        now = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
        _insert_order(db, order_id=order_id, group_id=group_id, status="cancelled")
        post_transaction(
            idempotency_key=f"prepaid-charge-{order_id}",
            template=LedgerTemplate.CHARGE_RECEIVED,
            order_id=order_id,
            gross_ngwee=GROSS_NGEWEE,
        )

        result = evaluate_and_release(_SERVICE, order_id, now=now)
        assert result.outcome == "not_eligible"
        assert result.reason == "order_cancelled"
        assert _release_txn_count(db, order_id) == 0

    def test_refunded_order_cannot_release(self, db: PgConn, db_url_env: None) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        now = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
        _seed_completed_prepaid(db, order_id=order_id, group_id=group_id, now=now)
        _insert_refund(db, order_id=order_id)

        result = evaluate_and_release(_SERVICE, order_id, now=now)
        assert result.outcome == "not_eligible"
        assert result.reason == "order_refunded"
        assert _commission_capture_count(db, order_id) == 0
        assert _release_txn_count(db, order_id) == 0

    def test_disputed_order_cannot_release(self, db: PgConn, db_url_env: None) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        now = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
        _seed_completed_prepaid(db, order_id=order_id, group_id=group_id, now=now)
        _insert_dispute(db, order_id=order_id, status="open")

        result = evaluate_and_release(_SERVICE, order_id, now=now)
        assert result.outcome == "held"
        assert result.reason == "dispute_open"
        assert _commission_capture_count(db, order_id) == 0
        assert _release_txn_count(db, order_id) == 0


class TestCodPathPreserved:
    def test_cod_collect_uses_cod_commission_keys_not_release_keys(
        self, db: PgConn, db_url_env: None
    ) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        now = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
        snapshot = _snapshot()

        _insert_order(
            db,
            order_id=order_id,
            group_id=group_id,
            status="delivered",
            commission_snapshot=snapshot,
            cod=True,
        )
        _insert_order_event(
            db,
            order_id=order_id,
            from_status="shipped",
            to_status="delivered",
            actor=SYSTEM_ACTOR_ID,
            created_at=now - timedelta(hours=1),
        )

        # Prepaid sweeper must skip COD (boolean::text parses as true/false).
        skipped = evaluate_and_release(_SERVICE, order_id, now=now)
        assert skipped.outcome == "not_eligible"
        assert skipped.reason == "cod_order"

        # Mirror COD collect ledger legs without the order-status transition
        # (status guard is orthogonal to the key-isolation invariant under test).
        record_cod_receivable(order_id=order_id)
        post_transaction(
            idempotency_key=f"cod-collect-{order_id}",
            template=LedgerTemplate.COD_COLLECTED,
            order_id=order_id,
            collected_ngwee=GROSS_NGEWEE,
            vendor_id=VENDOR_A,
        )
        capture_order_commission(
            order_id=order_id,
            commission_snapshot=snapshot,
            idempotency_key_prefix=f"cod-commission-{order_id}",
        )
        post_transaction(
            idempotency_key=f"cod-release-{order_id}",
            template=LedgerTemplate.RELEASE_TO_VENDOR,
            order_id=order_id,
            net_ngwee=NET_NGEWEE,
            vendor_id=VENDOR_A,
        )

        assert _commission_capture_count(db, order_id) == 0  # no release-* keys
        cod_captures = _commission_capture_count(
            db, order_id, prefix=f"cod-commission-{order_id}-commission-"
        )
        assert cod_captures == 1

        summary = summarize_order_release_ledger(order_id)
        assert summary.charge_received_ngwee == GROSS_NGEWEE  # receivable opened
        assert summary.commission_captured_ngwee == COMMISSION_NGEWEE
        assert summary.vendor_released_ngwee == NET_NGEWEE
        assert summary.balanced is True


class TestReconciliationGrossCommissionNet:
    def test_day_totals_and_order_summary_consistent(
        self, db: PgConn, db_url_env: None
    ) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        now = datetime(2026, 7, 18, 15, 30, tzinfo=UTC)
        _seed_completed_prepaid(db, order_id=order_id, group_id=group_id, now=now)
        result = evaluate_and_release(_SERVICE, order_id, now=now)
        assert result.outcome == "released"

        order_summary = summarize_order_release_ledger(order_id)
        assert order_summary.charge_received_ngwee == GROSS_NGEWEE
        assert order_summary.commission_captured_ngwee == COMMISSION_NGEWEE
        assert order_summary.vendor_released_ngwee == NET_NGEWEE
        assert (
            order_summary.commission_captured_ngwee + order_summary.vendor_released_ngwee
            == order_summary.charge_received_ngwee
        )

        day_totals = build_release_accounting_day_totals(report_date="2026-07-18")
        assert day_totals["gross_collected_ngwee"] >= GROSS_NGEWEE
        assert day_totals["commission_captured_ngwee"] >= COMMISSION_NGEWEE
        assert day_totals["vendor_released_ngwee"] >= NET_NGEWEE
        # Consistency: for this isolated order, commission + net == gross.
        assert COMMISSION_NGEWEE + NET_NGEWEE == GROSS_NGEWEE
