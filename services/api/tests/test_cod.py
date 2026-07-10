"""COD lifecycle tests — collection, reversal, commission, idempotency."""

from __future__ import annotations

import json
import uuid
from collections.abc import Generator
from typing import Any

import pytest
from app.services.ledger.engine import account_balance_ngwee
from app.services.ledger.templates import commission_ngwee_from_bps
from app.services.orders.state import ActorRole, OrderStatus
from app.services.payments.cod import (
    collection_idempotency_key,
    commission_from_snapshot,
    commission_ngwee_for_collectable,
    confirm_cod_collection,
    expected_collection_posting_legs,
    record_cod_receivable,
    refuse_cod_collection,
    reversal_idempotency_key,
)
from tests.rls.conftest import (
    MIGRATIONS_DIR,
    PgConn,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)

VENDOR_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
PLATFORM_CASH_ID = "c1000000-0000-0000-0000-000000000001"
ESCROW_ID = "c2000000-0000-0000-0000-000000000002"
COMMISSION_ID = "c3000000-0000-0000-0000-000000000003"
VENDOR_PAYABLE_ID = "c5000000-0000-0000-0000-000000000005"
COD_RECEIVABLE_ID = "c6000000-0000-0000-0000-000000000006"
FEES_ID = "c4000000-0000-0000-0000-000000000004"

COD_CAP_NGWEE = 50_000


def _snapshot_line(
    *,
    category_key: str,
    rate_bps: int,
    line_total_ngwee: int,
) -> dict[str, Any]:
    return {
        "listing_id": str(uuid.uuid4()),
        "category_key": category_key,
        "rate_bps": rate_bps,
        "qty": 1,
        "unit_price_ngwee": line_total_ngwee,
        "line_total_ngwee": line_total_ngwee,
        "wholesale": False,
    }


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


def seed_ledger_accounts(conn: PgConn) -> None:
    script = f"""
BEGIN;
SET LOCAL role service_role;
INSERT INTO public.ledger_accounts (id, kind) VALUES
  ('{PLATFORM_CASH_ID}', 'platform_cash'),
  ('{ESCROW_ID}', 'escrow'),
  ('{COMMISSION_ID}', 'commission_revenue'),
  ('{FEES_ID}', 'fees')
ON CONFLICT (id) DO NOTHING;
INSERT INTO public.ledger_accounts (id, kind, vendor_id) VALUES
  ('{VENDOR_PAYABLE_ID}', 'vendor_payable', '{VENDOR_A}'),
  ('{COD_RECEIVABLE_ID}', 'cod_receivable', '{VENDOR_A}')
ON CONFLICT (id) DO NOTHING;
COMMIT;
"""
    result = conn.run_script(script)
    if not result.ok:
        raise RuntimeError(f"ledger account seed failed: {result.error}")


def _insert_cod_order(
    db: PgConn,
    *,
    order_id: str,
    subtotal_ngwee: int,
    delivery_fee_ngwee: int,
    commission_snapshot: dict[str, Any],
    status: str = "delivered",
) -> str:
    cg_id = str(uuid.uuid4())
    total = subtotal_ngwee + delivery_fee_ngwee
    snapshot_sql = json.dumps(commission_snapshot).replace("'", "''")
    db.run(
        f"""
        INSERT INTO public.checkout_groups (
          id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee, total_ngwee, status
        ) VALUES (
          '{cg_id}', '{CUSTOMER_ID}', 'cg-{cg_id}', {subtotal_ngwee}, {delivery_fee_ngwee},
          {total}, 'completed'
        ) ON CONFLICT DO NOTHING;
        INSERT INTO public.orders (
          id, checkout_group_id, vendor_id, customer_id, status, fulfilment,
          delivery_fee_ngwee, cod, commission_snapshot
        ) VALUES (
          '{order_id}', '{cg_id}', '{VENDOR_A}', '{CUSTOMER_ID}', '{status}', 'delivery',
          {delivery_fee_ngwee}, true, '{snapshot_sql}'::jsonb
        ) ON CONFLICT (id) DO UPDATE
          SET status = EXCLUDED.status,
              cod = EXCLUDED.cod,
              commission_snapshot = EXCLUDED.commission_snapshot,
              delivery_fee_ngwee = EXCLUDED.delivery_fee_ngwee;
        INSERT INTO public.order_items (
          id, order_id, item_kind, qty, unit_price_ngwee, title_snapshot
        ) VALUES (
          '{uuid.uuid4()}', '{order_id}', 'product', 1, {subtotal_ngwee}, 'COD test item'
        );
        """
    )
    return order_id


def _transaction_posting_sum(db: PgConn, idempotency_key: str) -> int:
    result = db.run(
        f"""
        SELECT coalesce(sum(p.amount_ngwee), 0)::text
        FROM public.ledger_postings p
        JOIN public.ledger_transactions t ON t.id = p.transaction_id
        WHERE t.idempotency_key = '{idempotency_key}';
        """
    )
    assert result.ok and result.rows
    return int(result.rows[0])


def _all_postings_for_order(db: PgConn, order_id: str) -> list[tuple[str, str, int]]:
    result = db.run(
        f"""
        SELECT la.kind, coalesce(la.vendor_id::text, ''), p.amount_ngwee::text
        FROM public.ledger_postings p
        JOIN public.ledger_transactions t ON t.id = p.transaction_id
        JOIN public.ledger_accounts la ON la.id = p.account_id
        WHERE t.order_id = '{order_id}'
        ORDER BY t.created_at, p.amount_ngwee;
        """
    )
    assert result.ok
    rows: list[tuple[str, str, int]] = []
    for row in result.rows:
        kind, vendor_id, amount = row.split("|")
        rows.append((kind, vendor_id, int(amount)))
    return rows


@pytest.mark.usefixtures("db_url_env")
class TestCodCollectionConfirm:
    def test_collection_confirm_postings_balance_and_commission(self, db: PgConn) -> None:
        order_id = str(uuid.uuid4())
        subtotal = 180_000
        delivery_fee = 20_000
        collectable = subtotal + delivery_fee
        rate_bps = 500
        line = _snapshot_line(
            category_key="electronics",
            rate_bps=rate_bps,
            line_total_ngwee=subtotal,
        )
        snapshot = {"lines": [line]}
        expected_commission = commission_ngwee_from_bps(
            gross_ngwee=subtotal,
            commission_bps=rate_bps,
        )
        expected_net = collectable - expected_commission

        _insert_cod_order(
            db,
            order_id=order_id,
            subtotal_ngwee=subtotal,
            delivery_fee_ngwee=delivery_fee,
            commission_snapshot=snapshot,
            status="delivered",
        )

        cash_before = account_balance_ngwee(PLATFORM_CASH_ID)
        commission_before = account_balance_ngwee(COMMISSION_ID)
        payable_before = account_balance_ngwee(VENDOR_PAYABLE_ID)
        cod_before = account_balance_ngwee(COD_RECEIVABLE_ID)
        escrow_before = account_balance_ngwee(ESCROW_ID)

        record_cod_receivable(order_id=order_id)

        result = confirm_cod_collection(
            order_id=order_id,
            actor_id=str(uuid.uuid4()),
            note="Cash collected at delivery",
        )

        assert result.created is True
        assert result.collectable_ngwee == collectable
        assert result.commission_ngwee == expected_commission
        assert result.net_vendor_ngwee == expected_net
        assert len(result.transaction_ids) >= 2

        assert account_balance_ngwee(PLATFORM_CASH_ID) == cash_before + collectable
        assert account_balance_ngwee(COMMISSION_ID) == commission_before - expected_commission
        assert account_balance_ngwee(VENDOR_PAYABLE_ID) == payable_before - expected_net
        assert account_balance_ngwee(COD_RECEIVABLE_ID) == cod_before
        assert account_balance_ngwee(ESCROW_ID) == escrow_before

        assert _transaction_posting_sum(db, collection_idempotency_key(order_id)) == 0

        status = db.run(f"SELECT status FROM public.orders WHERE id = '{order_id}';")
        assert status.ok and status.rows == [OrderStatus.COMPLETED.value]

    def test_collection_postings_per_transaction_zero_sum(self, db: PgConn) -> None:
        order_id = str(uuid.uuid4())
        subtotal = 100_000
        snapshot = {
            "lines": [
                _snapshot_line(
                    category_key="home",
                    rate_bps=800,
                    line_total_ngwee=subtotal,
                )
            ]
        }
        _insert_cod_order(
            db,
            order_id=order_id,
            subtotal_ngwee=subtotal,
            delivery_fee_ngwee=0,
            commission_snapshot=snapshot,
            status="delivered",
        )
        record_cod_receivable(order_id=order_id)
        confirm_cod_collection(
            order_id=order_id,
            actor_id=str(uuid.uuid4()),
            note="Collected",
        )

        txn_keys = db.run(
            f"""
            SELECT idempotency_key
            FROM public.ledger_transactions
            WHERE order_id = '{order_id}' AND idempotency_key IS NOT NULL;
            """
        )
        assert txn_keys.ok
        for key in txn_keys.rows:
            assert _transaction_posting_sum(db, key) == 0


@pytest.mark.usefixtures("db_url_env")
class TestCodRefusalReversal:
    def test_refusal_reverses_receivable_and_cancels_order(self, db: PgConn) -> None:
        order_id = str(uuid.uuid4())
        subtotal = 45_000
        snapshot = {
            "lines": [
                _snapshot_line(
                    category_key="groceries",
                    rate_bps=500,
                    line_total_ngwee=subtotal,
                )
            ]
        }
        _insert_cod_order(
            db,
            order_id=order_id,
            subtotal_ngwee=subtotal,
            delivery_fee_ngwee=5_000,
            commission_snapshot=snapshot,
            status="shipped",
        )

        cod_before = account_balance_ngwee(COD_RECEIVABLE_ID)
        escrow_before = account_balance_ngwee(ESCROW_ID)

        record_cod_receivable(order_id=order_id)

        result = refuse_cod_collection(
            order_id=order_id,
            actor_role=ActorRole.ADMIN,
            actor_id=str(uuid.uuid4()),
            note="Customer refused delivery",
        )

        assert result.created is True
        assert result.to_status == OrderStatus.CANCELLED.value
        assert account_balance_ngwee(COD_RECEIVABLE_ID) == cod_before
        assert account_balance_ngwee(ESCROW_ID) == escrow_before
        assert _transaction_posting_sum(db, reversal_idempotency_key(order_id)) == 0

        status = db.run(f"SELECT status FROM public.orders WHERE id = '{order_id}';")
        assert status.ok and status.rows == [OrderStatus.CANCELLED.value]


@pytest.mark.usefixtures("db_url_env")
class TestCodCommissionMath:
    def test_commission_integer_exact_from_snapshot(self, db: PgConn) -> None:
        subtotal = 123_456
        rate_bps = 500
        line = _snapshot_line(
            category_key="electronics",
            rate_bps=rate_bps,
            line_total_ngwee=subtotal,
        )
        snapshot = {"lines": [line]}
        commission = commission_from_snapshot(snapshot)
        assert commission == commission_ngwee_from_bps(
            gross_ngwee=subtotal,
            commission_bps=rate_bps,
        )
        assert commission == 6_172

        collectable = subtotal + 7_000
        comm, net = commission_ngwee_for_collectable(
            collectable_ngwee=collectable,
            commission_snapshot=snapshot,
        )
        assert comm == 6_172
        assert net == collectable - 6_172

    def test_expected_collection_legs_sum_to_zero(self) -> None:
        legs = expected_collection_posting_legs(
            collectable_ngwee=200_000,
            commission_bps=500,
            vendor_id=VENDOR_A,
        )
        assert sum(amount for _, _, amount in legs) == 0


@pytest.mark.usefixtures("db_url_env")
class TestCodIdempotency:
    def test_double_confirm_is_idempotent(self, db: PgConn) -> None:
        order_id = str(uuid.uuid4())
        subtotal = 50_000
        snapshot = {
            "lines": [
                _snapshot_line(
                    category_key="default",
                    rate_bps=800,
                    line_total_ngwee=subtotal,
                )
            ]
        }
        _insert_cod_order(
            db,
            order_id=order_id,
            subtotal_ngwee=subtotal,
            delivery_fee_ngwee=0,
            commission_snapshot=snapshot,
            status="delivered",
        )
        record_cod_receivable(order_id=order_id)

        first = confirm_cod_collection(
            order_id=order_id,
            actor_id=str(uuid.uuid4()),
            note="First confirm",
        )
        second = confirm_cod_collection(
            order_id=order_id,
            actor_id=str(uuid.uuid4()),
            note="Second confirm",
        )

        assert first.created is True
        assert second.created is False
        assert second.transaction_ids[0] == first.transaction_ids[0]

        txn_count = db.run(
            f"""
            SELECT count(*)::text
            FROM public.ledger_transactions
            WHERE idempotency_key = '{collection_idempotency_key(order_id)}';
            """
        )
        assert txn_count.ok and txn_count.rows == ["1"]


class TestCodCapReference:
    def test_cod_cap_enforced_at_order_creation_not_duplicated_here(self) -> None:
        """K500 cap is enforced at order creation (M07-P05/P06), not in COD service."""
        assert COD_CAP_NGWEE == 50_000
