"""Convergeo Intelligence 1B-02: dashboard counts are not truncated at 1,000 rows.

The previous implementation selected ``status`` through PostgREST, which Supabase caps at
``max_rows`` (1,000), so tiles under-reported once a table grew. The counts are now SQL
``count(*) FILTER (...)`` aggregates; this seeds 1,500 orders and 1,500 checkout groups
and asserts every count exactly (as a delta over whatever the shared DB already holds).
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from app.routers.admin_dashboards import _funnel_snapshot, _orders_by_status
from app.services.db import reset_pools
from tests.rls.conftest import PgConn

CUSTOMER = "11111111-1111-1111-1111-111111111111"
PREFIX = "zz-1b02-"


def _cleanup(db: PgConn) -> None:
    db.run_script(
        "BEGIN;\n"
        "DELETE FROM public.orders o USING public.checkout_groups g "
        f"WHERE o.checkout_group_id = g.id AND g.idempotency_key LIKE '{PREFIX}%';\n"
        f"DELETE FROM public.checkout_groups WHERE idempotency_key LIKE '{PREFIX}%';\n"
        "COMMIT;\n"
    )


@pytest.fixture
def live(db: PgConn, monkeypatch: pytest.MonkeyPatch) -> Generator[PgConn, None, None]:
    monkeypatch.setenv("SUPABASE_DB_URL", db.dsn)
    _cleanup(db)
    yield db
    _cleanup(db)
    reset_pools()


def _seed(db: PgConn) -> None:
    vendor = db.run("SELECT id::text FROM public.vendors ORDER BY id LIMIT 1")
    assert vendor.ok and vendor.rows, vendor.error
    vid = vendor.rows[0]
    script = f"""
BEGIN;
INSERT INTO public.checkout_groups
  (customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee, total_ngwee, status)
SELECT '{CUSTOMER}', '{PREFIX}' || n, 1000, 0, 1000,
       CASE WHEN n <= 700 THEN 'pending' WHEN n <= 1150 THEN 'completed' ELSE 'abandoned' END
FROM generate_series(1, 1500) AS n;
INSERT INTO public.orders (checkout_group_id, vendor_id, customer_id, status, fulfilment)
SELECT g.id, '{vid}', '{CUSTOMER}',
       CASE WHEN s.n <= 1000 THEN 'placed' WHEN s.n <= 1300 THEN 'completed' ELSE 'cancelled' END,
       'pickup'
FROM generate_series(1, 1500) AS s(n)
JOIN public.checkout_groups g ON g.idempotency_key = '{PREFIX}' || s.n;
COMMIT;
"""
    result = db.run_script(script)
    assert result.ok, result.error


def test_counts_exceed_postgrest_max_rows_exactly(live: PgConn) -> None:
    before_orders = _orders_by_status()
    before_funnel = _funnel_snapshot()
    _seed(live)
    after_orders = _orders_by_status()
    after_funnel = _funnel_snapshot()

    assert after_orders.placed - before_orders.placed == 1000
    assert after_orders.completed - before_orders.completed == 300
    assert after_orders.cancelled - before_orders.cancelled == 200
    assert after_funnel.checkout_started - before_funnel.checkout_started == 1500
    assert after_funnel.checkout_completed - before_funnel.checkout_completed == 450
    assert after_funnel.orders_placed - before_funnel.orders_placed == 1300
    assert after_funnel.orders_completed - before_funnel.orders_completed == 300
