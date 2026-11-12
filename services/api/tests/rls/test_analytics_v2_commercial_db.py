"""Convergeo Intelligence 1B-03: paid orders / GMV only from orders + payments (live DB).

Seeds one fixed past UTC day with checkouts, orders, items and payments whose totals are
known to the ngwee, then asserts ``analytics_commercial_daily``, ``metrics.py`` and the
daily rollup all equal direct SQL over the same tables, and that the payment
reconciliation flag fires when payments and checkout totals disagree.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import date

import pytest
from app.services.analytics.metrics import average_ngwee, commercial_daily, commercial_summary
from app.services.analytics.rollup import rollup_day
from app.services.db import reset_pools
from tests.rls.conftest import PgConn

DAY = date(2026, 1, 16)
CUSTOMER = "11111111-1111-1111-1111-111111111111"
VENDOR_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VENDOR_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
G = "1b03a000-0000-4000-8000-00000000000"  # + 1..4
ORD = "1b03b000-0000-4000-8000-00000000000"  # + 1..5
SERVICE = 'SET LOCAL "request.jwt.claims" = \'{"role":"service_role"}\';\n'
TS = f"'{DAY.isoformat()} 12:00:00+00'"


def _cleanup(db: PgConn) -> None:
    result = db.run_script(
        "BEGIN;\n"
        + SERVICE
        + f"DELETE FROM public.payments WHERE checkout_group_id::text LIKE '{G}%';\n"
        f"DELETE FROM public.order_items WHERE order_id::text LIKE '{ORD}%';\n"
        f"DELETE FROM public.orders WHERE id::text LIKE '{ORD}%';\n"
        f"DELETE FROM public.checkout_groups WHERE id::text LIKE '{G}%';\n"
        f"DELETE FROM public.analytics_daily_rollup WHERE day = '{DAY.isoformat()}';\n"
        f"DELETE FROM public.analytics_rollup_runs WHERE day = '{DAY.isoformat()}';\n"
        "COMMIT;\n"
    )
    assert result.ok, result.error


@pytest.fixture
def live(db: PgConn, monkeypatch: pytest.MonkeyPatch) -> Generator[PgConn, None, None]:
    monkeypatch.setenv("SUPABASE_DB_URL", db.dsn)
    _cleanup(db)
    yield db
    _cleanup(db)
    reset_pools()


def _group(n: int, total: int, status: str) -> str:
    return (
        "INSERT INTO public.checkout_groups (id, customer_id, idempotency_key, subtotal_ngwee, "
        f"delivery_fee_ngwee, total_ngwee, status, created_at) VALUES ('{G}{n}', '{CUSTOMER}', "
        f"'zz-1b03-{n}', {total}, 0, {total}, '{status}', {TS});"
    )


def _order(
    n: int, group: int, vendor: str, status: str, fee: int, items: list[tuple[int, int]]
) -> str:
    sql = (
        "INSERT INTO public.orders (id, checkout_group_id, vendor_id, customer_id, status, "
        f"fulfilment, delivery_fee_ngwee, created_at) VALUES ('{ORD}{n}', '{G}{group}', "
        f"'{vendor}', '{CUSTOMER}', '{status}', 'delivery', {fee}, {TS});"
    )
    for qty, price in items:
        sql += (
            "\nINSERT INTO public.order_items (order_id, item_kind, qty, unit_price_ngwee) "
            f"VALUES ('{ORD}{n}', 'product', {qty}, {price});"
        )
    return sql


def _payment(group: int, ref: str, amount: int, status: str) -> str:
    return (
        "INSERT INTO public.payments (checkout_group_id, provider, rail, lenco_reference, "
        f"amount_ngwee, status, created_at) VALUES ('{G}{group}', 'lenco', 'mtn', "
        f"'pay-zz1b03-{ref}', {amount}, '{status}', {TS});"
    )


def _seed(db: PgConn) -> None:
    statements = [
        # G1: two vendors; 2 x 10,000 + 1,500 delivery and 1 x 4,050 → 25,550, paid.
        _group(1, 25_550, "completed"),
        _order(1, 1, VENDOR_A, "placed", 1_500, [(2, 10_000)]),
        _order(2, 1, VENDOR_B, "placed", 0, [(1, 4_050)]),
        _payment(1, "g1-fail", 25_550, "failed"),
        _payment(1, "g1-ok", 25_550, "success"),
        # G2: paid but the order was cancelled → paid, excluded from GMV.
        _group(2, 12_345, "completed"),
        _order(3, 2, VENDOR_A, "cancelled", 0, [(1, 12_345)]),
        _payment(2, "g2-ok", 12_345, "success"),
        # G3: payment failed → placed, not paid.
        _group(3, 999, "pending"),
        _order(4, 3, VENDOR_A, "placed", 0, [(1, 999)]),
        _payment(3, "g3-fail", 999, "failed"),
        # G4: 3 x 333 + 7 delivery = 1,006, completed and paid.
        _group(4, 1_006, "completed"),
        _order(5, 4, VENDOR_A, "completed", 7, [(3, 333)]),
        _payment(4, "g4-ok", 1_006, "success"),
    ]
    result = db.run_script("BEGIN;\n" + SERVICE + "\n".join(statements) + "\nCOMMIT;\n")
    assert result.ok, result.error


def _direct(db: PgConn, sql: str) -> int:
    result = db.run(sql)
    assert result.ok and result.rows, result.error
    return int(result.rows[0])


def test_commercial_day_exact_ngwee(live: PgConn) -> None:
    _seed(live)
    (day,) = commercial_daily(DAY, DAY)
    assert day.checkouts_started == 4
    assert day.orders_placed == 5
    assert day.orders_cancelled == 1
    assert day.orders_paid == 4  # O1, O2 (G1), O3 (G2, cancelled), O5 (G4)
    assert day.paid_checkouts == 3
    assert day.payments_succeeded == 3
    assert day.payments_succeeded_ngwee == 25_550 + 12_345 + 1_006
    assert day.paid_checkout_total_ngwee == 25_550 + 12_345 + 1_006
    assert day.gmv_paid_ngwee == 25_550 + 1_006
    assert not day.payment_mismatch


def test_paid_orders_reconcile_to_payments_by_direct_sql(live: PgConn) -> None:
    _seed(live)
    (day,) = commercial_daily(DAY, DAY)
    window = (
        f"o.created_at >= '{DAY.isoformat()}'::date AND "
        f"o.created_at < '{DAY.isoformat()}'::date + 1 AND o.id::text LIKE '{ORD}%'"
    )
    paid = (
        "EXISTS (SELECT 1 FROM public.payments p WHERE p.checkout_group_id = o.checkout_group_id "
        "AND p.status = 'success')"
    )
    assert day.orders_paid == _direct(
        live, f"SELECT count(*) FROM public.orders o WHERE {window} AND {paid}"
    )
    assert day.gmv_paid_ngwee == _direct(
        live,
        "SELECT coalesce(sum(o.delivery_fee_ngwee + (SELECT coalesce(sum(i.qty * "
        "i.unit_price_ngwee), 0) FROM public.order_items i WHERE i.order_id = o.id)), 0) "
        f"FROM public.orders o WHERE {window} AND {paid} AND o.status <> 'cancelled'",
    )
    assert day.payments_succeeded_ngwee == _direct(
        live,
        "SELECT coalesce(sum(amount_ngwee), 0) FROM public.payments "
        f"WHERE status = 'success' AND checkout_group_id::text LIKE '{G}%'",
    )


def test_amount_mismatch_raises_reconciliation_flag(live: PgConn) -> None:
    # One success per group is enforced by payments_checkout_group_success_uniq, so the
    # realistic drift is an amount mismatch (e.g. a group total edited after payment).
    _seed(live)
    assert live.run_script(
        "BEGIN;\n"
        f"UPDATE public.checkout_groups SET total_ngwee = 1100, subtotal_ngwee = 1100 "
        f"WHERE id = '{G}4';\n"
        "COMMIT;\n"
    ).ok
    summary = commercial_summary(DAY, DAY)
    assert summary.reconciled is False
    assert summary.mismatch_days == [DAY]
    assert summary.payments_succeeded == summary.paid_checkouts == 3
    assert rollup_day(DAY).ok
    flag = live.run(
        "SELECT value::text FROM public.analytics_daily_rollup "
        f"WHERE day = '{DAY.isoformat()}' AND metric = 'dq_payment_mismatch'"
    )
    assert flag.rows == ["1"]


def test_summary_aov_is_integer_ngwee(live: PgConn) -> None:
    _seed(live)
    summary = commercial_summary(DAY, DAY)
    assert summary.gmv_paid_ngwee == 26_556
    assert summary.aov_ngwee == 8_852  # 26,556 / 3 paid checkouts
    assert isinstance(summary.aov_ngwee, int)
    assert summary.reconciled is True


def test_rollup_stores_the_same_commercial_numbers(live: PgConn) -> None:
    _seed(live)
    assert rollup_day(DAY).ok
    rows = live.run(
        "SELECT metric || '=' || value FROM public.analytics_daily_rollup "
        f"WHERE day = '{DAY.isoformat()}' AND metric IN ('orders_paid', 'gmv_paid_ngwee', "
        "'payments_succeeded_ngwee', 'paid_checkouts', 'dq_payment_mismatch') ORDER BY 1"
    )
    assert rows.rows == [
        "dq_payment_mismatch=0",
        "gmv_paid_ngwee=26556",
        "orders_paid=4",
        "paid_checkouts=3",
        "payments_succeeded_ngwee=38901",
    ]
    # Idempotent: a second run yields identical commercial totals.
    assert rollup_day(DAY).ok
    assert (
        live.run(
            "SELECT metric || '=' || value FROM public.analytics_daily_rollup "
            f"WHERE day = '{DAY.isoformat()}' AND metric IN ('orders_paid', 'gmv_paid_ngwee', "
            "'payments_succeeded_ngwee', 'paid_checkouts', 'dq_payment_mismatch') ORDER BY 1"
        ).rows
        == rows.rows
    )


def test_average_ngwee_rounds_half_up_without_floats() -> None:
    assert average_ngwee(10, 4) == 3  # 2.5 → 3
    assert average_ngwee(9, 4) == 2  # 2.25 → 2
    assert average_ngwee(0, 0) is None
    assert average_ngwee(10**15 + 1, 2) == 5 * 10**14 + 1
