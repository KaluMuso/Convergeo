"""Escrow release rules engine tests — timer matrix, dispute hold, idempotency."""

from __future__ import annotations

import json
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

import pytest
from app.services.escrow.release import (
    DEFAULT_RELEASE_AFTER_DELIVERED_HOURS,
    DEFAULT_RELEASE_AFTER_SHIPPED_DAYS,
    compute_net_ngwee,
    evaluate_and_release,
    evaluate_release_rules,
    release_idempotency_key,
    sweep_escrow_releases,
)
from app.services.ledger.engine import account_balance_ngwee, post_transaction
from app.services.ledger.templates import LedgerTemplate, commission_ngwee_from_bps
from app.services.orders.state import SYSTEM_ACTOR_ID
from fastapi.testclient import TestClient
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
PLATFORM_CASH_ID = "c1000000-0000-0000-0000-000000000001"
ESCROW_ID = "c2000000-0000-0000-0000-000000000002"
COMMISSION_ID = "c3000000-0000-0000-0000-000000000003"
VENDOR_PAYABLE_ID = "c5000000-0000-0000-0000-000000000005"

GROSS_NGEWEE = 200_000
COMMISSION_BPS = 800
COMMISSION_NGEWEE = commission_ngwee_from_bps(
    gross_ngwee=GROSS_NGEWEE, commission_bps=COMMISSION_BPS
)
NET_NGEWEE = GROSS_NGEWEE - COMMISSION_NGEWEE

COMMISSION_SNAPSHOT = {
    "lines": [
        {
            "listing_id": str(uuid.uuid4()),
            "category_key": "electronics",
            "rate_bps": COMMISSION_BPS,
            "qty": 1,
            "unit_price_ngwee": GROSS_NGEWEE,
            "line_total_ngwee": GROSS_NGEWEE,
            "wholesale": False,
        }
    ]
}


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
ON CONFLICT (id) DO NOTHING;
INSERT INTO public.ledger_accounts (id, kind, vendor_id) VALUES
  ('{VENDOR_PAYABLE_ID}', 'vendor_payable', '{VENDOR_A}')
ON CONFLICT (id) DO NOTHING;
COMMIT;
"""
    result = conn.run_script(script)
    if not result.ok:
        raise RuntimeError(f"ledger account seed failed: {result.error}")


def seed_escrow_for_order(conn: PgConn, *, suffix: str) -> None:
    """Fund escrow with the collection charge ONLY.

    Since M08-P08b, ``evaluate_and_release`` captures commission itself, so the test
    must NOT pre-post ``COMMISSION_CAPTURE`` — doing so would double-capture and leave
    escrow unbalanced. The single charge leg mirrors the M08 prepaid collection.
    """
    post_transaction(
        idempotency_key=f"charge-{suffix}",
        template=LedgerTemplate.CHARGE_RECEIVED,
        gross_ngwee=GROSS_NGEWEE,
    )


def _commission_capture_count(conn: PgConn, order_id: str) -> int:
    prefix = f"{release_idempotency_key(order_id)}-commission-"
    result = conn.run(
        f"""
        SELECT count(*)::text
        FROM public.ledger_transactions
        WHERE kind = 'commission_capture'
          AND idempotency_key LIKE '{prefix}%';
        """
    )
    assert result.ok and result.rows
    return int(result.rows[0])


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


def _insert_checkout_group(conn: PgConn, group_id: str) -> None:
    conn.run(
        f"""
        INSERT INTO public.checkout_groups (
          id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee, total_ngwee, status
        ) VALUES (
          '{group_id}', '{CUSTOMER_ID}', 'cg-{group_id}',
          {GROSS_NGEWEE}, 0, {GROSS_NGEWEE}, 'completed'
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
) -> None:
    snapshot = commission_snapshot or COMMISSION_SNAPSHOT
    snapshot_sql = json.dumps(snapshot).replace("'", "''")
    _insert_checkout_group(conn, group_id)
    conn.run(
        f"""
        INSERT INTO public.orders (
          id, checkout_group_id, vendor_id, customer_id, status, fulfilment,
          delivery_fee_ngwee, cod, commission_snapshot
        ) VALUES (
          '{order_id}', '{group_id}', '{VENDOR_A}', '{CUSTOMER_ID}',
          '{status}', 'delivery', 0, false, '{snapshot_sql}'::jsonb
        ) ON CONFLICT (id) DO UPDATE
          SET status = EXCLUDED.status,
              commission_snapshot = EXCLUDED.commission_snapshot;
        """
    )
    conn.run(
        f"""
        INSERT INTO public.order_items (
          id, order_id, item_kind, qty, unit_price_ngwee, title_snapshot
        ) VALUES (
          '{uuid.uuid4()}', '{order_id}', 'product', 1, {GROSS_NGEWEE}, 'Test item'
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


def _insert_dispute(
    conn: PgConn,
    *,
    order_id: str,
    status: str = "open",
) -> None:
    conn.run(
        f"""
        INSERT INTO public.disputes (
          id, order_id, opener_user_id, status
        ) VALUES (
          '{uuid.uuid4()}', '{order_id}', '{CUSTOMER_ID}', '{status}'
        );
        """
    )


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


def _set_platform_config(conn: PgConn, key: str, value: int) -> None:
    conn.run(
        f"""
        UPDATE public.platform_config
        SET value = '{value}'::jsonb
        WHERE key = '{key}';
        """
    )


class TestReleaseRuleMatrix:
    def test_buyer_confirm_releases_early(self, db: PgConn, db_url_env: None) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        now = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
        delivered_at = now - timedelta(hours=1)

        _insert_order(db, order_id=order_id, group_id=group_id, status="completed")
        _insert_order_event(
            db,
            order_id=order_id,
            from_status="shipped",
            to_status="delivered",
            actor=SYSTEM_ACTOR_ID,
            created_at=delivered_at,
        )
        _insert_order_event(
            db,
            order_id=order_id,
            from_status="delivered",
            to_status="completed",
            actor=CUSTOMER_ID,
            created_at=now - timedelta(minutes=30),
        )
        seed_escrow_for_order(db, suffix=order_id)

        payable_before = account_balance_ngwee(VENDOR_PAYABLE_ID)
        result = evaluate_and_release(_SERVICE, order_id, now=now)

        assert result.outcome == "released"
        assert result.rule == "buyer_confirm"
        assert result.net_ngwee == NET_NGEWEE
        assert _release_txn_count(db, order_id) == 1
        assert account_balance_ngwee(VENDOR_PAYABLE_ID) == payable_before - NET_NGEWEE

    def test_auto_release_after_delivered_window(self, db: PgConn, db_url_env: None) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        now = datetime(2026, 7, 12, 0, 0, tzinfo=UTC)
        delivered_at = now - timedelta(hours=DEFAULT_RELEASE_AFTER_DELIVERED_HOURS)

        _insert_order(db, order_id=order_id, group_id=group_id, status="delivered")
        _insert_order_event(
            db,
            order_id=order_id,
            from_status="shipped",
            to_status="delivered",
            actor=SYSTEM_ACTOR_ID,
            created_at=delivered_at,
        )
        seed_escrow_for_order(db, suffix=order_id)

        result = evaluate_and_release(_SERVICE, order_id, now=now)

        assert result.outcome == "released"
        assert result.rule == "auto_delivered"
        assert _release_txn_count(db, order_id) == 1

    def test_shipped_fallback_after_seven_days(self, db: PgConn, db_url_env: None) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        now = datetime(2026, 7, 20, 0, 0, tzinfo=UTC)
        shipped_at = now - timedelta(days=DEFAULT_RELEASE_AFTER_SHIPPED_DAYS)

        _insert_order(db, order_id=order_id, group_id=group_id, status="shipped")
        _insert_order_event(
            db,
            order_id=order_id,
            from_status="processing",
            to_status="shipped",
            actor=VENDOR_A,
            created_at=shipped_at,
        )
        seed_escrow_for_order(db, suffix=order_id)

        result = evaluate_and_release(_SERVICE, order_id, now=now)

        assert result.outcome == "released"
        assert result.rule == "shipped_fallback"
        assert _release_txn_count(db, order_id) == 1


class TestDisputeHold:
    def test_open_dispute_holds_before_timers(self, db: PgConn, db_url_env: None) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        now = datetime(2026, 7, 20, 0, 0, tzinfo=UTC)

        _insert_order(db, order_id=order_id, group_id=group_id, status="completed")
        _insert_order_event(
            db,
            order_id=order_id,
            from_status="delivered",
            to_status="completed",
            actor=CUSTOMER_ID,
            created_at=now - timedelta(days=1),
        )
        _insert_dispute(db, order_id=order_id, status="open")
        seed_escrow_for_order(db, suffix=order_id)

        result = evaluate_and_release(_SERVICE, order_id, now=now)

        assert result.outcome == "held"
        assert result.reason == "dispute_open"
        assert _release_txn_count(db, order_id) == 0

    def test_resolved_dispute_allows_release(self, db: PgConn, db_url_env: None) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        now = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)

        _insert_order(db, order_id=order_id, group_id=group_id, status="completed")
        _insert_order_event(
            db,
            order_id=order_id,
            from_status="delivered",
            to_status="completed",
            actor=CUSTOMER_ID,
            created_at=now - timedelta(hours=1),
        )
        _insert_dispute(db, order_id=order_id, status="resolved_release")
        seed_escrow_for_order(db, suffix=order_id)

        result = evaluate_and_release(_SERVICE, order_id, now=now)

        assert result.outcome == "released"
        assert _release_txn_count(db, order_id) == 1


class TestIdempotency:
    def test_double_run_posts_once(self, db: PgConn, db_url_env: None) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        now = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)

        _insert_order(db, order_id=order_id, group_id=group_id, status="completed")
        _insert_order_event(
            db,
            order_id=order_id,
            from_status="delivered",
            to_status="completed",
            actor=CUSTOMER_ID,
            created_at=now - timedelta(hours=1),
        )
        seed_escrow_for_order(db, suffix=order_id)

        first = evaluate_and_release(_SERVICE, order_id, now=now)
        second = evaluate_and_release(_SERVICE, order_id, now=now)
        sweep = sweep_escrow_releases(_SERVICE, now=now)

        assert first.outcome == "released"
        assert second.outcome == "already_released"
        assert sweep.already_released >= 1
        assert _release_txn_count(db, order_id) == 1


class TestConfigWindows:
    def test_shortened_delivered_window_respected(self, db: PgConn, db_url_env: None) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        now = datetime(2026, 7, 10, 6, 0, tzinfo=UTC)
        delivered_at = now - timedelta(hours=2)

        _set_platform_config(db, "release_after_delivered_hours", 1)
        _insert_order(db, order_id=order_id, group_id=group_id, status="delivered")
        _insert_order_event(
            db,
            order_id=order_id,
            from_status="shipped",
            to_status="delivered",
            actor=SYSTEM_ACTOR_ID,
            created_at=delivered_at,
        )
        seed_escrow_for_order(db, suffix=order_id)

        too_early = evaluate_and_release(
            _SERVICE,
            order_id,
            now=delivered_at + timedelta(minutes=30),
        )
        assert too_early.outcome == "not_eligible"

        released = evaluate_and_release(_SERVICE, order_id, now=now)
        assert released.outcome == "released"
        assert _release_txn_count(db, order_id) == 1

        _set_platform_config(db, "release_after_delivered_hours", 48)


class TestReleaseCapturesCommission:
    """M08-P08b: release captures commission before paying the vendor net."""

    def _seed_completed_order(
        self,
        db: PgConn,
        *,
        order_id: str,
        group_id: str,
        now: datetime,
        commission_snapshot: dict[str, Any] | None = None,
    ) -> None:
        _insert_order(
            db,
            order_id=order_id,
            group_id=group_id,
            status="completed",
            commission_snapshot=commission_snapshot,
        )
        _insert_order_event(
            db,
            order_id=order_id,
            from_status="delivered",
            to_status="completed",
            actor=CUSTOMER_ID,
            created_at=now - timedelta(hours=1),
        )

    def test_release_captures_commission_and_zeroes_escrow(
        self, db: PgConn, db_url_env: None
    ) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        now = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
        self._seed_completed_order(db, order_id=order_id, group_id=group_id, now=now)

        escrow_before = account_balance_ngwee(ESCROW_ID)
        commission_before = account_balance_ngwee(COMMISSION_ID)
        payable_before = account_balance_ngwee(VENDOR_PAYABLE_ID)

        seed_escrow_for_order(db, suffix=order_id)  # CHARGE_RECEIVED only (escrow −gross)
        assert account_balance_ngwee(ESCROW_ID) == escrow_before - GROSS_NGEWEE

        result = evaluate_and_release(_SERVICE, order_id, now=now)
        assert result.outcome == "released"
        assert result.net_ngwee == NET_NGEWEE

        assert _commission_capture_count(db, order_id) == 1
        assert _release_txn_count(db, order_id) == 1

        # Lifecycle balances: charge(−gross) + capture(+commission) + release(+net) == 0.
        assert account_balance_ngwee(ESCROW_ID) == escrow_before
        # Commission recognized as revenue (credit-negative); vendor owed net.
        assert account_balance_ngwee(COMMISSION_ID) == commission_before - COMMISSION_NGEWEE
        assert account_balance_ngwee(VENDOR_PAYABLE_ID) == payable_before - NET_NGEWEE

    def test_double_run_captures_commission_once(self, db: PgConn, db_url_env: None) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        now = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
        self._seed_completed_order(db, order_id=order_id, group_id=group_id, now=now)

        escrow_before = account_balance_ngwee(ESCROW_ID)
        seed_escrow_for_order(db, suffix=order_id)

        first = evaluate_and_release(_SERVICE, order_id, now=now)
        second = evaluate_and_release(_SERVICE, order_id, now=now)

        assert first.outcome == "released"
        assert second.outcome == "already_released"
        assert _commission_capture_count(db, order_id) == 1
        assert _release_txn_count(db, order_id) == 1
        assert account_balance_ngwee(ESCROW_ID) == escrow_before

    def test_zero_commission_releases_full_gross_no_capture(
        self, db: PgConn, db_url_env: None
    ) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        now = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
        zero_snapshot = {
            "lines": [
                {
                    "listing_id": str(uuid.uuid4()),
                    "category_key": "free_events",
                    "rate_bps": 0,
                    "qty": 1,
                    "unit_price_ngwee": GROSS_NGEWEE,
                    "line_total_ngwee": GROSS_NGEWEE,
                    "wholesale": False,
                }
            ]
        }
        self._seed_completed_order(
            db,
            order_id=order_id,
            group_id=group_id,
            now=now,
            commission_snapshot=zero_snapshot,
        )
        escrow_before = account_balance_ngwee(ESCROW_ID)
        payable_before = account_balance_ngwee(VENDOR_PAYABLE_ID)
        seed_escrow_for_order(db, suffix=order_id)

        result = evaluate_and_release(_SERVICE, order_id, now=now)
        assert result.outcome == "released"
        assert result.net_ngwee == GROSS_NGEWEE
        assert _commission_capture_count(db, order_id) == 0
        assert account_balance_ngwee(ESCROW_ID) == escrow_before
        assert account_balance_ngwee(VENDOR_PAYABLE_ID) == payable_before - GROSS_NGEWEE


class TestPureRuleEvaluation:
    def test_dispute_beats_buyer_confirm(self) -> None:
        now = datetime(2026, 7, 10, tzinfo=UTC)
        outcome, reason, rule = evaluate_release_rules(
            status="completed",
            cod=False,
            has_open_dispute=True,
            already_released=False,
            buyer_confirmed=True,
            delivered_at=now - timedelta(days=1),
            shipped_at=now - timedelta(days=2),
            release_after_delivered_hours=48,
            release_after_shipped_days=7,
            now=now,
        )
        assert outcome == "held"
        assert reason == "dispute_open"
        assert rule is None


class TestNetNgweeMath:
    def test_net_is_gross_minus_commission(self) -> None:
        assert compute_net_ngwee(
            gross_ngwee=GROSS_NGEWEE,
            commission_snapshot=COMMISSION_SNAPSHOT,
        ) == NET_NGEWEE


class TestInternalReleaseRouter:
    def test_tick_requires_internal_token(self) -> None:
        from app.main import create_app

        app = create_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            denied = client.post("/internal/release-job/tick")
            assert denied.status_code == 401

            with patch(
                "app.routers.internal_release_job.sweep_escrow_releases",
                return_value=type(
                    "S",
                    (),
                    {
                        "scanned": 2,
                        "released": 1,
                        "held": 0,
                        "already_released": 1,
                        "not_eligible": 0,
                    },
                )(),
            ):
                ok = client.post(
                    "/internal/release-job/tick",
                    headers={"X-Internal-Token": "dev-internal-release-job"},
                )
            assert ok.status_code == 200
            assert ok.json() == {
                "scanned": 2,
                "released": 1,
                "held": 0,
                "already_released": 1,
                "not_eligible": 0,
            }
