"""Ledger engine tests — property balance, goldens, idempotency, balance derivation."""

from __future__ import annotations

import random
import uuid
from collections.abc import Callable, Generator
from typing import Any

import pytest
from app.services.ledger.engine import account_balance_ngwee, post_transaction
from app.services.ledger.templates import (
    ALL_TEMPLATES,
    TEMPLATE_REGISTRY,
    AccountRef,
    LedgerTemplate,
    PostingLeg,
    TemplateResult,
    charge_received,
    commission_ngwee_from_bps,
    refund_lane2,
    release_to_vendor,
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

PLATFORM_CASH_ID = "c1000000-0000-0000-0000-000000000001"
ESCROW_ID = "c2000000-0000-0000-0000-000000000002"
COMMISSION_ID = "c3000000-0000-0000-0000-000000000003"
FEES_ID = "c4000000-0000-0000-0000-000000000004"
VENDOR_PAYABLE_ID = "c5000000-0000-0000-0000-000000000005"
COD_RECEIVABLE_ID = "c6000000-0000-0000-0000-000000000006"


def _sum_legs(result: TemplateResult) -> int:
    return sum(leg.amount_ngwee for leg in result.legs)


def _build_template_args(
    rng: random.Random,
    template: LedgerTemplate,
) -> dict[str, Any]:
    gross = rng.randint(1, 5_000_000)
    match template:
        case LedgerTemplate.CHARGE_RECEIVED:
            return {"gross_ngwee": gross}
        case LedgerTemplate.ESCROW_HOLD:
            return {"order_amount_ngwee": gross}
        case LedgerTemplate.COMMISSION_CAPTURE:
            bps = rng.randint(1, 2_000)
            adjusted_gross = max(gross, 10_000 // bps + 1)
            return {"gross_ngwee": adjusted_gross, "commission_bps": bps}
        case LedgerTemplate.RELEASE_TO_VENDOR:
            return {"net_ngwee": gross, "vendor_id": VENDOR_A}
        case LedgerTemplate.PAYOUT_EXECUTED:
            return {"amount_ngwee": gross, "vendor_id": VENDOR_A}
        case LedgerTemplate.REFUND_LANE1:
            return {"refund_ngwee": gross}
        case LedgerTemplate.REFUND_LANE2:
            refund = rng.randint(1, gross - 2) if gross > 2 else 1
            retained = rng.randint(0, gross - refund)
            restocking = gross - refund - retained
            if restocking <= 0:
                restocking = 1
                retained = max(0, gross - refund - restocking)
            escrow_release = refund + retained + restocking
            return {
                "escrow_release_ngwee": escrow_release,
                "refund_to_customer_ngwee": refund,
                "vendor_retained_ngwee": retained,
                "restocking_fee_ngwee": restocking,
                "vendor_id": VENDOR_A,
            }
        case LedgerTemplate.COD_COLLECTED:
            return {"collected_ngwee": gross, "vendor_id": VENDOR_A}
        case LedgerTemplate.CLAWBACK:
            return {"clawback_ngwee": gross, "vendor_id": VENDOR_A}
        case _:
            raise AssertionError(f"unhandled template {template}")


@pytest.mark.parametrize("template", ALL_TEMPLATES)
def test_template_zero_sum_property(template: LedgerTemplate) -> None:
    """Property: Σ postings = 0 for random amounts across every template."""
    rng = random.Random(0x0805)
    builder: Callable[..., TemplateResult] = TEMPLATE_REGISTRY[template]
    for _ in range(100):
        args = _build_template_args(rng, template)
        result = builder(**args)
        assert _sum_legs(result) == 0, f"{template} unbalanced for args {args}"


def test_commission_bps_integer_exact() -> None:
    assert commission_ngwee_from_bps(gross_ngwee=123_456, commission_bps=500) == 6_172
    assert commission_ngwee_from_bps(gross_ngwee=99, commission_bps=333) == 3
    assert commission_ngwee_from_bps(gross_ngwee=1, commission_bps=1) == 0


def test_charge_received_golden() -> None:
    result = charge_received(gross_ngwee=253_000)
    assert result.kind == LedgerTemplate.CHARGE_RECEIVED
    assert result.legs == (
        PostingLeg(AccountRef("platform_cash"), 253_000),
        PostingLeg(AccountRef("escrow"), -253_000),
    )


def test_release_to_vendor_golden() -> None:
    result = release_to_vendor(net_ngwee=184_000, vendor_id=VENDOR_A)
    assert result.legs == (
        PostingLeg(AccountRef("escrow"), 184_000),
        PostingLeg(AccountRef("vendor_payable", VENDOR_A), -184_000),
    )


def test_refund_lane2_golden() -> None:
    result = refund_lane2(
        escrow_release_ngwee=100_000,
        refund_to_customer_ngwee=70_000,
        vendor_retained_ngwee=20_000,
        restocking_fee_ngwee=10_000,
        vendor_id=VENDOR_A,
    )
    assert _sum_legs(result) == 0
    assert result.legs == (
        PostingLeg(AccountRef("escrow"), 100_000),
        PostingLeg(AccountRef("platform_cash"), -70_000),
        PostingLeg(AccountRef("vendor_payable", VENDOR_A), -20_000),
        PostingLeg(AccountRef("commission_revenue"), -10_000),
    )


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


def test_idempotent_repost(db: PgConn) -> None:
    key = f"idem-{uuid.uuid4()}"
    first = post_transaction(
        idempotency_key=key,
        template=LedgerTemplate.CHARGE_RECEIVED,
        gross_ngwee=50_000,
    )
    assert first.created is True

    second = post_transaction(
        idempotency_key=key,
        template=LedgerTemplate.CHARGE_RECEIVED,
        gross_ngwee=50_000,
    )
    assert second.created is False
    assert second.id == first.id

    count = db.run(
        f"SELECT count(*)::text FROM public.ledger_transactions WHERE idempotency_key = '{key}';"
    )
    assert count.ok and count.rows == ["1"]

    postings = db.run(
        f"""
SELECT count(*)::text
FROM public.ledger_postings p
JOIN public.ledger_transactions t ON t.id = p.transaction_id
WHERE t.idempotency_key = '{key}';
"""
    )
    assert postings.ok and postings.rows == ["2"]


def test_balance_derivation_after_charge(db: PgConn) -> None:
    key = f"bal-{uuid.uuid4()}"
    amount = 77_700
    cash_before = account_balance_ngwee(PLATFORM_CASH_ID)
    escrow_before = account_balance_ngwee(ESCROW_ID)
    post_transaction(
        idempotency_key=key,
        template=LedgerTemplate.CHARGE_RECEIVED,
        gross_ngwee=amount,
    )

    assert account_balance_ngwee(PLATFORM_CASH_ID) == cash_before + amount
    assert account_balance_ngwee(ESCROW_ID) == escrow_before - amount

    posting_sum = db.run(
        f"""
SELECT coalesce(sum(p.amount_ngwee), 0)::text
FROM public.ledger_postings p
JOIN public.ledger_transactions t ON t.id = p.transaction_id
WHERE t.idempotency_key = '{key}';
"""
    )
    assert posting_sum.ok and posting_sum.rows == ["0"]


def test_full_release_pipeline_balances(db: PgConn) -> None:
    gross = 200_000
    bps = 800
    commission = commission_ngwee_from_bps(gross_ngwee=gross, commission_bps=bps)
    net = gross - commission
    suffix = uuid.uuid4()

    escrow_before = account_balance_ngwee(ESCROW_ID)
    commission_before = account_balance_ngwee(COMMISSION_ID)
    payable_before = account_balance_ngwee(VENDOR_PAYABLE_ID)
    cash_before = account_balance_ngwee(PLATFORM_CASH_ID)

    post_transaction(
        idempotency_key=f"pipe-charge-{suffix}",
        template=LedgerTemplate.CHARGE_RECEIVED,
        gross_ngwee=gross,
    )
    post_transaction(
        idempotency_key=f"pipe-commission-{suffix}",
        template=LedgerTemplate.COMMISSION_CAPTURE,
        gross_ngwee=gross,
        commission_bps=bps,
    )
    post_transaction(
        idempotency_key=f"pipe-release-{suffix}",
        template=LedgerTemplate.RELEASE_TO_VENDOR,
        net_ngwee=net,
        vendor_id=VENDOR_A,
    )

    assert account_balance_ngwee(ESCROW_ID) == escrow_before
    assert account_balance_ngwee(COMMISSION_ID) == commission_before - commission
    assert account_balance_ngwee(VENDOR_PAYABLE_ID) == payable_before - net

    post_transaction(
        idempotency_key=f"pipe-payout-{suffix}",
        template=LedgerTemplate.PAYOUT_EXECUTED,
        amount_ngwee=net,
        vendor_id=VENDOR_A,
    )
    assert account_balance_ngwee(VENDOR_PAYABLE_ID) == payable_before
    assert account_balance_ngwee(PLATFORM_CASH_ID) == cash_before + commission


def test_cod_collected_clears_receivable(db: PgConn) -> None:
    suffix = uuid.uuid4()
    amount = 45_000
    cod_before = account_balance_ngwee(COD_RECEIVABLE_ID)
    cash_before = account_balance_ngwee(PLATFORM_CASH_ID)
    post_transaction(
        idempotency_key=f"cod-recv-{suffix}",
        template=LedgerTemplate.COD_COLLECTED,
        collected_ngwee=amount,
        vendor_id=VENDOR_A,
    )
    assert account_balance_ngwee(COD_RECEIVABLE_ID) == cod_before - amount
    assert account_balance_ngwee(PLATFORM_CASH_ID) == cash_before + amount


def test_clawback_reduces_vendor_payable(db: PgConn) -> None:
    suffix = uuid.uuid4()
    net = 90_000
    claw = 15_000
    payable_before = account_balance_ngwee(VENDOR_PAYABLE_ID)
    post_transaction(
        idempotency_key=f"claw-release-{suffix}",
        template=LedgerTemplate.RELEASE_TO_VENDOR,
        net_ngwee=net,
        vendor_id=VENDOR_A,
    )
    post_transaction(
        idempotency_key=f"claw-back-{suffix}",
        template=LedgerTemplate.CLAWBACK,
        clawback_ngwee=claw,
        vendor_id=VENDOR_A,
    )
    assert account_balance_ngwee(VENDOR_PAYABLE_ID) == payable_before - net + claw
