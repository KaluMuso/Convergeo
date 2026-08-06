"""Tests for automated background sweepers (escrow, cart, daily summary)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Generator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from app.services.ledger.engine import post_transaction
from app.services.ledger.templates import LedgerTemplate, commission_ngwee_from_bps
from app.services.orders.state import SYSTEM_ACTOR_ID
from app.services.payments.fulfillment import escrow_hold_idempotency_key
from app.services.stock.claim import claim_reservation
from app.settings import Settings
from app.tasks.sweepers import (
    dispatch_daily_summary,
    sweep_expired_cart_reservations,
    sweep_expired_escrows,
)
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
    status: str = "completed",
) -> None:
    snapshot_sql = json.dumps(COMMISSION_SNAPSHOT).replace("'", "''")
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


def _insert_escrow_hold_backdated(
    conn: PgConn,
    *,
    order_id: str,
    created_at: datetime,
) -> None:
    post_transaction(
        idempotency_key=escrow_hold_idempotency_key(order_id),
        template=LedgerTemplate.ESCROW_HOLD,
        order_id=order_id,
        order_amount_ngwee=GROSS_NGEWEE,
    )
    ts = created_at.astimezone(UTC).isoformat()
    conn.run(
        f"""
        UPDATE public.ledger_transactions
        SET created_at = '{ts}'::timestamptz
        WHERE order_id = '{order_id}'::uuid
          AND kind = 'escrow_hold';
        """
    )


def _release_txn_count(conn: PgConn, order_id: str) -> int:
    result = conn.run(
        f"""
        SELECT count(*)::text
        FROM public.ledger_transactions
        WHERE idempotency_key = 'release-{order_id}';
        """
    )
    assert result.ok and result.rows
    return int(result.rows[0])


def _seed_eligible_order_with_escrow_hold(
    conn: PgConn,
    *,
    hold_age: timedelta,
    now: datetime,
) -> str:
    order_id = str(uuid.uuid4())
    group_id = str(uuid.uuid4())
    _insert_order(conn, order_id=order_id, group_id=group_id, status="completed")
    _insert_order_event(
        conn,
        order_id=order_id,
        from_status="shipped",
        to_status="delivered",
        actor=SYSTEM_ACTOR_ID,
        created_at=now - timedelta(hours=72),
    )
    _insert_order_event(
        conn,
        order_id=order_id,
        from_status="delivered",
        to_status="completed",
        actor=CUSTOMER_ID,
        created_at=now - timedelta(hours=50),
    )
    _insert_escrow_hold_backdated(
        conn,
        order_id=order_id,
        created_at=now - hold_age,
    )
    return order_id


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


class TestEscrowAgeSweep:
    def test_49_hour_hold_is_released_but_47_hour_is_ignored(
        self,
        db: PgConn,
        db_url_env: None,
    ) -> None:
        now = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
        released_order = _seed_eligible_order_with_escrow_hold(
            db,
            hold_age=timedelta(hours=49),
            now=now,
        )
        ignored_order = _seed_eligible_order_with_escrow_hold(
            db,
            hold_age=timedelta(hours=47),
            now=now,
        )

        result = sweep_expired_escrows(_SERVICE, now=now)

        assert result.released == 1
        assert result.scanned == 1
        assert _release_txn_count(db, released_order) == 1
        assert _release_txn_count(db, ignored_order) == 0

    def test_open_dispute_blocks_release(
        self,
        db: PgConn,
        db_url_env: None,
    ) -> None:
        now = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
        order_id = _seed_eligible_order_with_escrow_hold(
            db,
            hold_age=timedelta(hours=50),
            now=now,
        )
        db.run(
            f"""
            INSERT INTO public.disputes (
              id, order_id, opener_user_id, status
            ) VALUES (
              '{uuid.uuid4()}', '{order_id}', '{CUSTOMER_ID}', 'open'
            );
            """
        )

        result = sweep_expired_escrows(_SERVICE, now=now)

        assert result.released == 0
        assert result.scanned == 0
        assert _release_txn_count(db, order_id) == 0


class TestCartReservationSweep:
    def test_expired_reservation_restocked_after_15_minutes(
        self,
        db: PgConn,
        db_url_env: None,
    ) -> None:
        listing_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        ids_fixture = json.loads(
            (Path(__file__).resolve().parent / "fixtures" / "demo" / "ids.json").read_text()
        )
        category_id = ids_fixture["category_id"]
        db.run(
            f"""
            INSERT INTO public.vendor_listings (
              id, vendor_id, category_id, title, slug, stock_mode, stock_qty, status
            ) VALUES (
              '{listing_id}', '{VENDOR_A}', '{category_id}',
              'Sweep listing', 'sweep-{listing_id[:8]}',
              'tracked', 5, 'active'
            );
            """
        )
        db.run(
            f"""
            INSERT INTO public.checkout_groups (
              id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee, total_ngwee
            ) VALUES (
              '{group_id}', '{CUSTOMER_ID}', 'idem-{group_id}', 0, 0, 0
            );
            """
        )
        claim_reservation(
            listing_id=listing_id,
            checkout_group_id=group_id,
            qty=2,
        )
        db.run(
            f"""
            UPDATE public.stock_reservations
            SET created_at = timezone('utc', now()) - interval '16 minutes',
                expires_at = timezone('utc', now()) - interval '1 minute'
            WHERE listing_id = '{listing_id}'::uuid
              AND checkout_group_id = '{group_id}'::uuid;
            """
        )

        result = sweep_expired_cart_reservations()

        assert result.scanned == 1
        assert result.released == 1
        assert result.restocked_qty == 2
        stock = db.run(
            f"SELECT stock_qty::text FROM public.vendor_listings WHERE id = '{listing_id}'::uuid;"
        )
        assert stock.ok and stock.rows
        assert int(stock.rows[0]) == 5


class TestDailySummaryDispatch:
    def test_posts_daily_metrics_to_n8n_webhook(self) -> None:
        settings = Settings(
            SUPABASE_URL="https://example.supabase.co",
            SUPABASE_SERVICE_ROLE_KEY="dev",
            SUPABASE_ANON_KEY="dev",
            N8N_WEBHOOK_URL="https://n8n.example/webhook/daily",
        )
        report_day = date(2026, 8, 5)

        with (
            patch(
                "app.tasks.sweepers._compute_daily_gmv_ngwee",
                return_value=150_000,
            ),
            patch(
                "app.tasks.sweepers._count_daily_orders",
                return_value=12,
            ),
            patch(
                "app.tasks.sweepers._count_daily_new_users",
                return_value=3,
            ),
            patch("app.tasks.sweepers.post_n8n_webhook") as post_mock,
        ):
            result = dispatch_daily_summary(
                _SERVICE,
                report_date=report_day,
                settings=settings,
            )

        assert result.gmv_ngwee == 150_000
        assert result.total_orders == 12
        assert result.new_users == 3
        assert result.dispatched is True
        post_mock.assert_called_once()
        payload = post_mock.call_args.args[0]
        assert payload["event"] == "daily.summary"
        assert payload["report_date"] == "2026-08-05"
        assert payload["gmv_ngwee"] == 150_000
        assert payload["total_orders"] == 12
        assert payload["new_users"] == 3

    def test_daily_summary_tick_requires_internal_token(self) -> None:
        from app.main import create_app

        app = create_app()
        client = TestClient(app)
        response = client.post("/internal/sweepers/daily-summary")
        assert response.status_code == 401


class TestInternalSweepersRouter:
    def test_escrow_tick_returns_counts(self) -> None:
        from app.main import create_app

        app = create_app()
        client = TestClient(app)
        with (
            patch(
                "app.routers.internal_sweepers.sweep_expired_escrows",
                return_value=MagicMock(
                    scanned=2,
                    released=1,
                    held=0,
                    already_released=0,
                    not_eligible=1,
                    payout_vendors_queued=1,
                ),
            ),
            patch(
                "app.routers.internal_sweepers.run_payout_batch",
                return_value=(MagicMock(payouts_attempted=1), []),
            ),
        ):
            response = client.post(
                "/internal/sweepers/escrow",
                headers={"X-Internal-Token": "dev-internal-sweepers"},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["scanned"] == 2
        assert body["released"] == 1
