"""Commission engine and sequential invoicing tests."""

from __future__ import annotations

import concurrent.futures
import json
import uuid
from collections.abc import Generator
from typing import Any

import pytest
from app.services.commissions.engine import (
    SUPPLIES_STACK_BPS,
    capture_order_commission,
    commission_ngwee_for_line,
    compute_order_commission,
    effective_rate_bps,
)
from app.services.invoicing.allocation import allocate_invoice_number
from app.services.invoicing.builder import (
    VAT_ENABLED_AT_LAUNCH,
    InvoiceInputLine,
    build_invoice_payload,
    issue_receipt,
    issue_tax_invoice,
)
from app.services.invoicing.vsdc import submit_to_vsdc_stub
from app.services.ledger.engine import account_balance_ngwee, post_transaction
from app.services.ledger.templates import LedgerTemplate
from tests.rls.conftest import (
    MIGRATIONS_DIR,
    PgConn,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)

VENDOR_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
PLATFORM_CASH_ID = "c1000000-0000-0000-0000-000000000001"
ESCROW_ID = "c2000000-0000-0000-0000-000000000002"
COMMISSION_ID = "c3000000-0000-0000-0000-000000000003"
VENDOR_PAYABLE_ID = "c5000000-0000-0000-0000-000000000005"

D4_MATRIX: tuple[tuple[str, int, int, int], ...] = (
    ("electronics", 500, 1_000_000, 50_000),
    ("home", 800, 500_000, 40_000),
    ("fashion_beauty", 1_000, 250_000, 25_000),
    ("services", 1_200, 100_000, 12_000),
    ("event_tickets", 500, 200_000, 10_000),
    ("supplies", 300, 1_000_000, 30_000),
    ("groceries", 500, 80_000, 4_000),
    ("default", 800, 125_000, 10_000),
    ("free_events", 0, 50_000, 0),
)


def _snapshot_line(
    *,
    category_key: str,
    rate_bps: int,
    line_total_ngwee: int,
    wholesale: bool = False,
    listing_id: str | None = None,
) -> dict[str, Any]:
    return {
        "listing_id": listing_id or str(uuid.uuid4()),
        "category_key": category_key,
        "rate_bps": rate_bps,
        "qty": 1,
        "unit_price_ngwee": line_total_ngwee,
        "line_total_ngwee": line_total_ngwee,
        "wholesale": wholesale,
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


def _insert_order(db: PgConn, order_id: str | None = None) -> str:
    oid = order_id or str(uuid.uuid4())
    cg_id = str(uuid.uuid4())
    customer_id = "11111111-1111-1111-1111-111111111111"
    db.run(
        f"""
        INSERT INTO public.checkout_groups (
          id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee, total_ngwee, status
        ) VALUES (
          '{cg_id}', '{customer_id}', 'cg-{cg_id}', 10000, 0, 10000, 'completed'
        ) ON CONFLICT DO NOTHING;
        INSERT INTO public.orders (
          id, checkout_group_id, vendor_id, customer_id, status, fulfilment
        ) VALUES (
          '{oid}', '{cg_id}', '{VENDOR_A}', '{customer_id}', 'placed', 'pickup'
        ) ON CONFLICT DO NOTHING;
        """
    )
    return oid


class TestCommissionMath:
    def test_commission_matrix_d4_categories(self) -> None:
        for category_key, rate_bps, line_total, expected in D4_MATRIX:
            snapshot = {
                "lines": [
                    _snapshot_line(
                        category_key=category_key,
                        rate_bps=rate_bps,
                        line_total_ngwee=line_total,
                    )
                ]
            }
            result = compute_order_commission(snapshot)
            assert result.commission_ngwee == expected, category_key
            assert commission_ngwee_for_line(
                line_total_ngwee=line_total,
                rate_bps=rate_bps,
            ) == expected

    def test_supplies_wholesale_stacks_three_percent(self) -> None:
        line_total = 1_000_000
        base_rate = 500
        stacked = base_rate + SUPPLIES_STACK_BPS
        snapshot = {
            "lines": [
                _snapshot_line(
                    category_key="electronics",
                    rate_bps=base_rate,
                    line_total_ngwee=line_total,
                    wholesale=True,
                )
            ]
        }
        result = compute_order_commission(snapshot)
        assert effective_rate_bps(
            base_rate_bps=base_rate,
            category_key="electronics",
            wholesale=True,
        ) == stacked
        assert result.lines[0].effective_rate_bps == stacked
        assert result.commission_ngwee == (line_total * stacked) // 10_000

    def test_supplies_category_wholesale_double_stack(self) -> None:
        line_total = 2_000_000
        base_rate = 300
        stacked = base_rate + SUPPLIES_STACK_BPS
        snapshot = {
            "lines": [
                _snapshot_line(
                    category_key="supplies",
                    rate_bps=base_rate,
                    line_total_ngwee=line_total,
                    wholesale=True,
                )
            ]
        }
        result = compute_order_commission(snapshot)
        assert result.commission_ngwee == (line_total * stacked) // 10_000

    def test_free_events_zero_commission(self) -> None:
        snapshot = {
            "lines": [
                _snapshot_line(
                    category_key="free_events",
                    rate_bps=0,
                    line_total_ngwee=99_999,
                )
            ]
        }
        assert compute_order_commission(snapshot).commission_ngwee == 0

    @pytest.mark.usefixtures("db", "db_url_env")
    def test_snapshot_immune_to_live_rate_change(self, db: PgConn) -> None:
        snapshot = {
            "lines": [
                _snapshot_line(
                    category_key="electronics",
                    rate_bps=500,
                    line_total_ngwee=450_000,
                )
            ]
        }
        before = compute_order_commission(snapshot).commission_ngwee
        db.run(
            "UPDATE public.commission_rates SET rate_bps = 9999 "
            "WHERE category_key = 'electronics';"
        )
        after = compute_order_commission(snapshot).commission_ngwee
        assert before == after == 22_500

    def test_multi_line_mixed_rates_integer_exact(self) -> None:
        snapshot = {
            "lines": [
                _snapshot_line(
                    category_key="electronics",
                    rate_bps=500,
                    line_total_ngwee=100_000,
                ),
                _snapshot_line(
                    category_key="fashion_beauty",
                    rate_bps=1_000,
                    line_total_ngwee=50_000,
                ),
            ]
        }
        result = compute_order_commission(snapshot)
        assert result.commission_ngwee == 5_000 + 5_000
        assert result.gross_ngwee == 150_000


@pytest.mark.usefixtures("db", "db_url_env")
class TestCommissionCapture:
    def test_capture_posts_commission_capture_per_line(self, db: PgConn) -> None:
        order_id = _insert_order(db)
        gross = 200_000
        suffix = uuid.uuid4()
        post_transaction(
            idempotency_key=f"fund-{suffix}",
            template=LedgerTemplate.CHARGE_RECEIVED,
            gross_ngwee=gross,
        )
        commission_before = account_balance_ngwee(COMMISSION_ID)
        snapshot = {
            "lines": [
                _snapshot_line(
                    category_key="electronics",
                    rate_bps=500,
                    line_total_ngwee=gross,
                )
            ]
        }
        captured = capture_order_commission(
            order_id=order_id,
            commission_snapshot=snapshot,
            idempotency_key_prefix=f"cap-{suffix}",
        )
        assert captured.commission.commission_ngwee == 10_000
        assert len(captured.posted_transaction_ids) == 1
        assert account_balance_ngwee(COMMISSION_ID) == commission_before - 10_000


@pytest.mark.usefixtures("db", "db_url_env")
class TestInvoicingGapless:
    def test_concurrent_invoice_issuance_gapless_sequence(self, db: PgConn) -> None:
        series = f"GAP-{uuid.uuid4().hex[:8]}"
        workers = 12

        def allocate() -> int:
            return allocate_invoice_number(series)

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            numbers = list(executor.map(lambda _: allocate(), range(workers)))

        assert len(numbers) == workers
        assert len(set(numbers)) == workers
        assert sorted(numbers) == list(range(1, workers + 1))

        counter = db.run(
            f"SELECT next_no::text FROM public.invoice_counters WHERE series = '{series}';"
        )
        assert counter.ok and counter.rows == [str(workers + 1)]

    def test_receipt_and_tax_invoice_persist_gapless(self, db: PgConn) -> None:
        order_id = _insert_order(db)
        payment_id = str(uuid.uuid4())
        lines = (InvoiceInputLine(description="Phone", qty=1, unit_price_ngwee=450_000),)

        receipt = issue_receipt(order_id=order_id, lines=lines, payment_id=payment_id)
        tax_invoice = issue_tax_invoice(
            order_id=order_id,
            lines=lines,
            seller_tpin="1000000000",
        )

        assert receipt.kind == "receipt"
        assert receipt.invoice_no >= 1
        assert tax_invoice.kind == "tax_invoice"
        assert tax_invoice.invoice_no >= 1
        assert receipt.series != tax_invoice.series

        rows = db.run(
            f"""
            SELECT series, no::text
            FROM public.invoices
            WHERE order_id = '{order_id}'
            ORDER BY series, no;
            """
        )
        assert rows.ok
        persisted = {(parts[0], int(parts[1])) for parts in (r.split("|") for r in rows.rows)}
        assert (receipt.series, receipt.invoice_no) in persisted
        assert (tax_invoice.series, tax_invoice.invoice_no) in persisted


class TestInvoicingVatOff:
    def test_vat_off_compliant_non_vat_invoice(self) -> None:
        assert VAT_ENABLED_AT_LAUNCH is False
        payload = build_invoice_payload(
            kind="tax_invoice",
            series="TAX",
            invoice_no=42,
            order_id=str(uuid.uuid4()),
            lines=(
                InvoiceInputLine(description="Chitenge", qty=2, unit_price_ngwee=85_000),
            ),
            seller_tpin="2000000000",
            vat_flag=False,
        )
        assert payload.vat_flag is False
        assert payload.vat_ngwee == 0
        assert payload.total_ngwee == payload.subtotal_ngwee == 170_000
        for line in payload.lines:
            assert line.vat_rate_bps == 0
            assert line.vat_ngwee == 0

        vsdc = submit_to_vsdc_stub(payload.to_snapshot())
        assert vsdc.fiscal_code == "VSDC-STUB-TAX-42"
        assert vsdc.submitted is False

    def test_invoice_snapshot_json_serializable(self) -> None:
        payload = build_invoice_payload(
            kind="receipt",
            series="RCP",
            invoice_no=1,
            order_id=str(uuid.uuid4()),
            lines=(InvoiceInputLine(description="Item", qty=1, unit_price_ngwee=1_000),),
        )
        encoded = json.dumps(payload.to_snapshot())
        decoded = json.loads(encoded)
        assert decoded["vat_flag"] is False
        assert decoded["vat_ngwee"] == 0
