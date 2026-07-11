"""M11-P04 service escrow — deposit/balance spine, single-count commission, refund.

MONEY-CRITICAL. Isolation-clean: unique UUIDs per test; ledger balances asserted as
deltas (shared accounts); mutated config/rates restored in finally.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from typing import Any

import pytest
from app.errors import AppError
from app.services.commissions.engine import compute_order_commission
from app.services.ledger.engine import account_balance_ngwee, post_transaction
from app.services.ledger.templates import LedgerTemplate
from app.services.rfq.engagement import (
    DEFAULT_SERVICE_COMMISSION_BPS,
    DEFAULT_SERVICE_DEPOSIT_PCT,
    accept_idempotency_key,
    accept_quote,
    build_service_commission_snapshot,
    compute_deposit_ngwee,
    create_balance_item,
)
from tests.rls.conftest import (
    PgConn,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)

CUSTOMER_A = "11111111-1111-1111-1111-111111111111"
OTHER_CUSTOMER = "22222222-2222-2222-2222-222222222222"

PLATFORM_CASH_ID = "c1000000-0000-0000-0000-000000000001"
ESCROW_ID = "c2000000-0000-0000-0000-000000000002"
COMMISSION_ID = "c3000000-0000-0000-0000-000000000003"


class _ServiceWrapper:
    client: Any = None


_SERVICE = _ServiceWrapper()


def _seed_ledger_accounts(conn: PgConn) -> None:
    conn.run(
        f"""
        INSERT INTO public.ledger_accounts (id, kind) VALUES
          ('{PLATFORM_CASH_ID}', 'platform_cash'),
          ('{ESCROW_ID}', 'escrow'),
          ('{COMMISSION_ID}', 'commission_revenue')
        ON CONFLICT (id) DO NOTHING;
        """
    )


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
    _seed_ledger_accounts(conn)
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


def _any_vendor_id(conn: PgConn) -> str:
    result = conn.run("SELECT id::text FROM public.vendors LIMIT 1")
    assert result.ok and result.rows, "matrix seed must provide a vendor"
    return result.rows[0]


def _seed_job(conn: PgConn, *, job_id: str, customer_id: str, status: str = "quoted") -> None:
    conn.run(
        f"""
        INSERT INTO public.jobs (id, customer_id, category, description, status)
        VALUES ('{job_id}', '{customer_id}', 'home_services', 'Fix a tap', '{status}')
        ON CONFLICT (id) DO NOTHING;
        """
    )


def _seed_quote(
    conn: PgConn,
    *,
    quote_id: str,
    job_id: str,
    vendor_id: str,
    amount_ngwee: int,
    status: str = "submitted",
) -> None:
    conn.run(
        f"""
        INSERT INTO public.job_quotes (id, job_id, provider_vendor_id, amount_ngwee, status)
        VALUES ('{quote_id}', '{job_id}', '{vendor_id}', {amount_ngwee}, '{status}')
        ON CONFLICT (id) DO NOTHING;
        """
    )


def _order_items_gross(conn: PgConn, order_id: str) -> int:
    result = conn.run(
        f"""
        SELECT coalesce(sum(qty * unit_price_ngwee), 0)::text
        FROM public.order_items WHERE order_id = '{order_id}';
        """
    )
    assert result.ok and result.rows
    return int(result.rows[0])


def _load_snapshot(conn: PgConn, order_id: str) -> dict[str, Any]:
    import json

    result = conn.run(
        f"SELECT commission_snapshot::text FROM public.orders WHERE id = '{order_id}';"
    )
    assert result.ok and result.rows
    loaded = json.loads(result.rows[0])
    assert isinstance(loaded, dict)
    return loaded


# ---------------------------------------------------------------------------
# Pure math (no DB)
# ---------------------------------------------------------------------------


class TestDepositMath:
    def test_half_up_integer_and_exact_split(self) -> None:
        for total in (250_000, 100_001, 333_333, 1, 999_999):
            deposit = compute_deposit_ngwee(total_job_ngwee=total, deposit_pct=50)
            balance = total - deposit
            # No float, exact split, deposit never exceeds total.
            assert isinstance(deposit, int)
            assert 0 < deposit <= total
            assert deposit + balance == total
        # Half-up: 50% of an odd ngwee rounds the half up.
        assert compute_deposit_ngwee(total_job_ngwee=101, deposit_pct=50) == 51

    def test_rejects_bad_inputs(self) -> None:
        with pytest.raises(ValueError):
            compute_deposit_ngwee(total_job_ngwee=0, deposit_pct=50)
        with pytest.raises(ValueError):
            compute_deposit_ngwee(total_job_ngwee=100, deposit_pct=0)
        with pytest.raises(ValueError):
            compute_deposit_ngwee(total_job_ngwee=100, deposit_pct=101)

    def test_snapshot_commission_is_twelve_percent_of_total(self) -> None:
        total = 250_000
        snapshot = build_service_commission_snapshot(
            total_job_ngwee=total,
            rate_bps=DEFAULT_SERVICE_COMMISSION_BPS,
            job_id=str(uuid.uuid4()),
            quote_id=str(uuid.uuid4()),
        )
        commission = compute_order_commission(snapshot).commission_ngwee
        assert commission == total * DEFAULT_SERVICE_COMMISSION_BPS // 10_000
        assert commission == 30_000  # 12% of 250,000


# ---------------------------------------------------------------------------
# DB-backed
# ---------------------------------------------------------------------------


class TestAcceptDeposit:
    def test_accept_creates_single_order_and_deposit(self, db: PgConn, db_url_env: None) -> None:
        job_id = str(uuid.uuid4())
        quote_id = str(uuid.uuid4())
        total = 250_000
        _seed_job(db, job_id=job_id, customer_id=CUSTOMER_A)
        _seed_quote(db, quote_id=quote_id, job_id=job_id, vendor_id=_any_vendor_id(db),
                    amount_ngwee=total)

        result = accept_quote(_SERVICE, job_id=job_id, quote_id=quote_id, customer_id=CUSTOMER_A)

        expected_deposit = compute_deposit_ngwee(
            total_job_ngwee=total, deposit_pct=DEFAULT_SERVICE_DEPOSIT_PCT
        )
        assert result.replayed is False
        assert result.deposit_ngwee == expected_deposit
        assert result.balance_ngwee == total - expected_deposit
        assert result.total_job_ngwee == total
        # Exactly ONE order + ONE checkout group for the accepted job.
        orders = db.run(f"SELECT count(*)::text FROM public.orders WHERE id = '{result.order_id}';")
        assert orders.rows and orders.rows[0] == "1"
        # Deposit checkout group is payable = deposit only.
        cg = db.run(
            f"SELECT total_ngwee::text FROM public.checkout_groups "
            f"WHERE id = '{result.checkout_group_id}';"
        )
        assert cg.rows and int(cg.rows[0]) == expected_deposit
        # Job + quote transitioned to accepted.
        job_status = db.run(f"SELECT status FROM public.jobs WHERE id = '{job_id}';")
        assert job_status.rows and job_status.rows[0] == "accepted"
        quote_status = db.run(f"SELECT status FROM public.job_quotes WHERE id = '{quote_id}';")
        assert quote_status.rows and quote_status.rows[0] == "accepted"

    def test_accept_is_idempotent(self, db: PgConn, db_url_env: None) -> None:
        job_id = str(uuid.uuid4())
        quote_id = str(uuid.uuid4())
        _seed_job(db, job_id=job_id, customer_id=CUSTOMER_A)
        _seed_quote(db, quote_id=quote_id, job_id=job_id, vendor_id=_any_vendor_id(db),
                    amount_ngwee=180_000)

        first = accept_quote(_SERVICE, job_id=job_id, quote_id=quote_id, customer_id=CUSTOMER_A)
        second = accept_quote(_SERVICE, job_id=job_id, quote_id=quote_id, customer_id=CUSTOMER_A)

        assert second.replayed is True
        assert second.order_id == first.order_id
        assert second.checkout_group_id == first.checkout_group_id
        assert second.commission_ngwee == first.commission_ngwee
        # Only one checkout group ever created for this quote.
        key = accept_idempotency_key(quote_id)
        cnt = db.run(
            f"SELECT count(*)::text FROM public.checkout_groups WHERE idempotency_key = '{key}';"
        )
        assert cnt.rows and cnt.rows[0] == "1"


class TestTwoLegCommissionSingleCount:
    def test_commission_counted_once_across_both_legs(
        self, db: PgConn, db_url_env: None
    ) -> None:
        job_id = str(uuid.uuid4())
        quote_id = str(uuid.uuid4())
        total = 250_000
        _seed_job(db, job_id=job_id, customer_id=CUSTOMER_A)
        _seed_quote(db, quote_id=quote_id, job_id=job_id, vendor_id=_any_vendor_id(db),
                    amount_ngwee=total)

        result = accept_quote(_SERVICE, job_id=job_id, quote_id=quote_id, customer_id=CUSTOMER_A)
        expected_commission = total * DEFAULT_SERVICE_COMMISSION_BPS // 10_000

        # 12% of the TOTAL, computed once at accept.
        assert result.commission_ngwee == expected_commission

        # Create the balance leg on the SAME order (completion path helper).
        balance = create_balance_item(result.order_id)
        assert balance.created is True
        assert balance.balance_ngwee == result.balance_ngwee

        # Gross across both legs == total; commission from the single snapshot unchanged.
        assert _order_items_gross(db, result.order_id) == total
        snapshot = _load_snapshot(db, result.order_id)
        assert compute_order_commission(snapshot).commission_ngwee == expected_commission

        # Prove NOT double-counted: taxing the deposit AND the total would over-charge.
        double_count = (
            result.deposit_ngwee * DEFAULT_SERVICE_COMMISSION_BPS // 10_000
        ) + expected_commission
        assert result.commission_ngwee < double_count
        assert result.commission_ngwee == expected_commission

        # Idempotent balance creation — no second item, no gross drift.
        again = create_balance_item(result.order_id)
        assert again.created is False
        assert again.balance_order_item_id == balance.balance_order_item_id
        assert _order_items_gross(db, result.order_id) == total


class TestSnapshotImmunity:
    def test_rate_change_after_accept_does_not_alter_order(
        self, db: PgConn, db_url_env: None
    ) -> None:
        job_id = str(uuid.uuid4())
        quote_id = str(uuid.uuid4())
        total = 400_000
        _seed_job(db, job_id=job_id, customer_id=CUSTOMER_A)
        _seed_quote(db, quote_id=quote_id, job_id=job_id, vendor_id=_any_vendor_id(db),
                    amount_ngwee=total)

        result = accept_quote(_SERVICE, job_id=job_id, quote_id=quote_id, customer_id=CUSTOMER_A)
        before = result.commission_ngwee
        assert before == total * DEFAULT_SERVICE_COMMISSION_BPS // 10_000

        try:
            db.run(
                "UPDATE public.commission_rates SET rate_bps = 2000 "
                "WHERE category_key = 'services';"
            )
            snapshot = _load_snapshot(db, result.order_id)
            # Snapshot carries the accept-time rate; live-rate bump is ignored.
            assert snapshot["rate_bps"] == DEFAULT_SERVICE_COMMISSION_BPS
            assert compute_order_commission(snapshot).commission_ngwee == before
        finally:
            db.run(
                f"UPDATE public.commission_rates SET rate_bps = {DEFAULT_SERVICE_COMMISSION_BPS} "
                "WHERE category_key = 'services';"
            )


class TestCancellationRefund:
    def test_deposit_refundable_pre_work_balances_ledger(
        self, db: PgConn, db_url_env: None
    ) -> None:
        job_id = str(uuid.uuid4())
        quote_id = str(uuid.uuid4())
        total = 250_000
        _seed_job(db, job_id=job_id, customer_id=CUSTOMER_A)
        _seed_quote(db, quote_id=quote_id, job_id=job_id, vendor_id=_any_vendor_id(db),
                    amount_ngwee=total)
        result = accept_quote(_SERVICE, job_id=job_id, quote_id=quote_id, customer_id=CUSTOMER_A)
        deposit = result.deposit_ngwee

        escrow_before = account_balance_ngwee(ESCROW_ID)
        cash_before = account_balance_ngwee(PLATFORM_CASH_ID)

        # Deposit paid → held in escrow (standard M08 charge on the deposit checkout group).
        post_transaction(
            idempotency_key=f"charge-{result.checkout_group_id}",
            template=LedgerTemplate.CHARGE_RECEIVED,
            checkout_group_id=result.checkout_group_id,
            gross_ngwee=deposit,
        )
        # Pre-work cancellation → deposit refunded from escrow (lane 1).
        refund = post_transaction(
            idempotency_key=f"rfd-{result.order_id}",
            template=LedgerTemplate.REFUND_LANE1,
            order_id=result.order_id,
            refund_ngwee=deposit,
        )
        assert refund.created is True

        # Round-trip nets to zero — deposit fully returned, ledger balanced.
        assert account_balance_ngwee(ESCROW_ID) == escrow_before
        assert account_balance_ngwee(PLATFORM_CASH_ID) == cash_before

        # Refund is idempotent (Lenco retries) — no double refund.
        replay = post_transaction(
            idempotency_key=f"rfd-{result.order_id}",
            template=LedgerTemplate.REFUND_LANE1,
            order_id=result.order_id,
            refund_ngwee=deposit,
        )
        assert replay.created is False
        assert account_balance_ngwee(ESCROW_ID) == escrow_before


class TestOwnerAuthz:
    def test_non_owner_cannot_accept(self, db: PgConn, db_url_env: None) -> None:
        job_id = str(uuid.uuid4())
        quote_id = str(uuid.uuid4())
        _seed_job(db, job_id=job_id, customer_id=CUSTOMER_A)
        _seed_quote(db, quote_id=quote_id, job_id=job_id, vendor_id=_any_vendor_id(db),
                    amount_ngwee=120_000)

        with pytest.raises(AppError) as exc:
            accept_quote(_SERVICE, job_id=job_id, quote_id=quote_id, customer_id=OTHER_CUSTOMER)
        assert exc.value.http_status == 403
        # No spine created for the non-owner attempt.
        cnt = db.run(
            f"SELECT count(*)::text FROM public.checkout_groups "
            f"WHERE idempotency_key = '{accept_idempotency_key(quote_id)}';"
        )
        assert cnt.rows and cnt.rows[0] == "0"

    def test_quote_from_other_job_is_rejected(self, db: PgConn, db_url_env: None) -> None:
        job_id = str(uuid.uuid4())
        other_job_id = str(uuid.uuid4())
        quote_id = str(uuid.uuid4())
        vendor_id = _any_vendor_id(db)
        _seed_job(db, job_id=job_id, customer_id=CUSTOMER_A)
        _seed_job(db, job_id=other_job_id, customer_id=CUSTOMER_A)
        # Quote belongs to other_job_id, not job_id.
        _seed_quote(db, quote_id=quote_id, job_id=other_job_id, vendor_id=vendor_id,
                    amount_ngwee=90_000)

        with pytest.raises(AppError) as exc:
            accept_quote(_SERVICE, job_id=job_id, quote_id=quote_id, customer_id=CUSTOMER_A)
        assert exc.value.http_status == 422
