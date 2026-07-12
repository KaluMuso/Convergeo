"""M12-P10 vendor analytics — aggregate correctness, window boundaries, empty, scope.

DB-backed: aggregates run through `run_sql_script` (psql) against the seeded RLS
matrix schema, exactly as the production endpoint does. Sales/orders reconcile
with the seeded `orders`/`order_items` rows; views come from `funnel_events`.

Dedicated test vendors/listings are created so no matrix-seeded orders leak into
the aggregates — the deltas asserted here are exactly the fixtures inserted below.
"""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from app.routers.vendor_analytics import compute_vendor_analytics
from tests.rls.conftest import (
    PgConn,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)

OWNER_A = "33333333-3333-3333-3333-333333333333"  # vendor_a_owner (seeded profile)
OWNER_B = "44444444-4444-4444-4444-444444444444"  # vendor_b_owner (seeded profile)
CUSTOMER_A = "11111111-1111-1111-1111-111111111111"

# Dedicated analytics-test vendors — zero matrix-seeded orders/funnel touch them.
VENDOR_A = "a9a00000-0000-0000-0000-00000000000a"
VENDOR_B = "a9b00000-0000-0000-0000-00000000000b"
VENDOR_EMPTY = "a9e00000-0000-0000-0000-00000000000e"
LISTING_A = "a9100000-0000-0000-0000-00000000000a"
LISTING_B = "a9100000-0000-0000-0000-00000000000b"
LISTING_EMPTY = "a9100000-0000-0000-0000-00000000000e"

CHECKOUT_GROUP = "a9c00000-0000-0000-0000-0000000000cc"

# Vendor A orders (non-cancelled sales inside the 7-day window):
#   A1 today       qty 2 @ 50_000 = 100_000
#   A2 3 days ago  qty 1 @ 30_000 =  30_000
# Excluded from the 7-day window:
#   A3 cancelled today (qty 5 @ 100_000)   -> excluded (cancelled)
#   A4 10 days ago qty 1 @ 40_000          -> inside 30-day window only
ORDER_A1 = "a9200000-0000-0000-0000-000000000001"
ORDER_A2 = "a9200000-0000-0000-0000-000000000002"
ORDER_A3 = "a9200000-0000-0000-0000-000000000003"
ORDER_A4 = "a9200000-0000-0000-0000-000000000004"
ORDER_B1 = "a9200000-0000-0000-0000-0000000000b1"

ITEM_A1 = "a9300000-0000-0000-0000-000000000001"
ITEM_A2 = "a9300000-0000-0000-0000-000000000002"
ITEM_A3 = "a9300000-0000-0000-0000-000000000003"
ITEM_A4 = "a9300000-0000-0000-0000-000000000004"
ITEM_B1 = "a9300000-0000-0000-0000-0000000000b1"

SALES_A_7 = 130_000
ORDERS_A_7 = 2
SALES_A_30 = 170_000
ORDERS_A_30 = 3


def _seed_analytics(db: PgConn) -> None:
    # Run as service_role: order delete/insert triggers are server-controlled.
    script = (
        "BEGIN;\n"
        "SET LOCAL role service_role;\n"
        'SET LOCAL "request.jwt.claims" = \'{"role":"service_role"}\';\n'
    )
    # Idempotent cleanup — keyed off the fixture idempotency_key + test listings so
    # residue from any prior run (whatever ids it used) is removed.
    script += f"""
DELETE FROM public.funnel_events
  WHERE snapshot::text LIKE '%{LISTING_A}%'
     OR snapshot::text LIKE '%{LISTING_B}%';
DELETE FROM public.order_item_products WHERE order_item_id IN (
  SELECT id FROM public.order_items WHERE order_id IN (
    SELECT id FROM public.orders WHERE checkout_group_id IN (
      SELECT id FROM public.checkout_groups WHERE idempotency_key LIKE 'analytics-fixture%')));
DELETE FROM public.order_items WHERE order_id IN (
  SELECT id FROM public.orders WHERE checkout_group_id IN (
    SELECT id FROM public.checkout_groups WHERE idempotency_key LIKE 'analytics-fixture%'));
DELETE FROM public.orders WHERE checkout_group_id IN (
  SELECT id FROM public.checkout_groups WHERE idempotency_key LIKE 'analytics-fixture%');
DELETE FROM public.checkout_groups WHERE idempotency_key = 'analytics-fixture';
"""
    vendors = [
        (VENDOR_A, OWNER_A, "analytics-a", "Analytics Vendor A"),
        (VENDOR_B, OWNER_B, "analytics-b", "Analytics Vendor B"),
        (VENDOR_EMPTY, OWNER_A, "analytics-empty", "Analytics Vendor Empty"),
    ]
    for vid, owner, slug, name in vendors:
        script += f"""
INSERT INTO public.vendors (id, owner_user_id, slug, display_name, status, kyc_tier)
VALUES ('{vid}', '{owner}', '{slug}', '{name}', 'active', 1)
ON CONFLICT (id) DO NOTHING;
"""
    listings = [
        (LISTING_A, VENDOR_A, "Analytics Phone A"),
        (LISTING_B, VENDOR_B, "Analytics Chitenge B"),
        (LISTING_EMPTY, VENDOR_EMPTY, "Analytics Idle Listing"),
    ]
    for lid, vid, title in listings:
        script += f"""
INSERT INTO public.vendor_listings (
  id, vendor_id, title_override, price_ngwee, condition, stock_mode, status
) VALUES ('{lid}', '{vid}', '{title}', 50000, 'new', 'always_available', 'active')
ON CONFLICT (id) DO NOTHING;
"""

    orders = [
        (ORDER_A1, VENDOR_A, "delivered", "now()"),
        (ORDER_A2, VENDOR_A, "delivered", "now() - interval '3 days'"),
        (ORDER_A3, VENDOR_A, "cancelled", "now()"),
        (ORDER_A4, VENDOR_A, "delivered", "now() - interval '10 days'"),
        (ORDER_B1, VENDOR_B, "delivered", "now()"),
    ]
    # One checkout group per order. Migration 0031 adds a UNIQUE index on
    # orders(checkout_group_id, vendor_id) — the production invariant that a
    # checkout produces at most one order per vendor. The fixture must therefore
    # give each order its own checkout group rather than sharing one.
    for idx, (oid, vid, status, created) in enumerate(orders):
        cg = f"a9c00000-0000-0000-0000-0000000000{idx:02d}"
        script += f"""
INSERT INTO public.checkout_groups (
  id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee, total_ngwee, status
) VALUES (
  '{cg}', '{CUSTOMER_A}', 'analytics-fixture-{idx}', 0, 0, 0, 'completed'
);
INSERT INTO public.orders (
  id, checkout_group_id, vendor_id, customer_id, status, fulfilment, created_at
) VALUES (
  '{oid}', '{cg}', '{vid}', '{CUSTOMER_A}', '{status}', 'delivery',
  timezone('utc', {created})
);
"""

    # (item_id, order, qty, unit_price_ngwee, listing)
    items = [
        (ITEM_A1, ORDER_A1, 2, 50_000, LISTING_A),
        (ITEM_A2, ORDER_A2, 1, 30_000, LISTING_A),
        (ITEM_A3, ORDER_A3, 5, 100_000, LISTING_A),
        (ITEM_A4, ORDER_A4, 1, 40_000, LISTING_A),
        (ITEM_B1, ORDER_B1, 1, 20_000, LISTING_B),
    ]
    for item_id, oid, qty, price, listing in items:
        script += f"""
INSERT INTO public.order_items (
  id, order_id, item_kind, qty, unit_price_ngwee, title_snapshot
) VALUES (
  '{item_id}', '{oid}', 'product', {qty}, {price}, 'snap'
);
INSERT INTO public.order_item_products (order_item_id, listing_id, product_id)
VALUES ('{item_id}', '{listing}', NULL);
"""

    # Funnel views: two for vendor A's listing, one for vendor B's (must not count for A).
    views = [
        (LISTING_A, "now()"),
        (LISTING_A, "now() - interval '2 days'"),
        (LISTING_B, "now()"),
    ]
    for listing, created in views:
        script += f"""
INSERT INTO public.funnel_events (stage, checkout_group_id, snapshot, created_at)
VALUES (
  'cart_add', null,
  '{{"lines":[{{"listing_id":"{listing}","qty":1}}]}}'::jsonb,
  timezone('utc', {created})
);
"""
    script += "COMMIT;"

    result = db.run(script)
    assert result.ok, f"seed failed: {result.error}"


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
    _seed_analytics(conn)
    yield conn


@pytest.fixture(autouse=True)
def db_url_env(db: PgConn) -> Generator[None, None, None]:
    previous = os.environ.get("SUPABASE_DB_URL")
    os.environ["SUPABASE_DB_URL"] = db.dsn
    yield
    if previous is None:
        os.environ.pop("SUPABASE_DB_URL", None)
    else:
        os.environ["SUPABASE_DB_URL"] = previous


def test_sales_orders_reconcile_with_orders_truth() -> None:
    result = compute_vendor_analytics(VENDOR_A, 7)

    assert len(result.days) == 7
    assert len(result.sales_ngwee_by_day) == 7
    assert len(result.orders_by_day) == 7
    # Sales/orders match the seeded non-cancelled order rows exactly.
    assert sum(result.sales_ngwee_by_day) == SALES_A_7
    assert sum(result.orders_by_day) == ORDERS_A_7
    # Today bucket (last element) holds A1 only; A3 is cancelled and excluded.
    assert result.sales_ngwee_by_day[-1] == 100_000
    assert result.orders_by_day[-1] == 1


def test_top_listings_and_views_and_conversion() -> None:
    result = compute_vendor_analytics(VENDOR_A, 7)

    assert len(result.top_listings) == 1
    top = result.top_listings[0]
    assert top.listing_id == LISTING_A
    assert top.title == "Analytics Phone A"
    assert top.units == 3  # 2 (A1) + 1 (A2)
    assert top.revenue_ngwee == SALES_A_7

    # Two funnel events reference vendor A's listing; vendor B's event is ignored.
    assert sum(result.views_by_day) == 2
    assert result.conversion_hint.orders_total == ORDERS_A_7
    assert result.conversion_hint.views_total == 2
    assert result.conversion_hint.conversion_pct == 100.0


def test_window_boundary_7_vs_30() -> None:
    seven = compute_vendor_analytics(VENDOR_A, 7)
    thirty = compute_vendor_analytics(VENDOR_A, 30)

    assert len(thirty.days) == 30
    # A4 (10 days ago, 40_000) enters the 30-day window but not the 7-day one.
    assert sum(seven.sales_ngwee_by_day) == SALES_A_7
    assert sum(thirty.sales_ngwee_by_day) == SALES_A_30
    assert sum(thirty.orders_by_day) == ORDERS_A_30
    assert thirty.top_listings[0].units == 4  # 2 + 1 + 1
    assert thirty.top_listings[0].revenue_ngwee == SALES_A_30


def test_empty_history_returns_zeros_not_error() -> None:
    result = compute_vendor_analytics(VENDOR_EMPTY, 7)

    assert len(result.days) == 7
    assert result.sales_ngwee_by_day == [0] * 7
    assert result.orders_by_day == [0] * 7
    assert result.views_by_day == [0] * 7
    assert result.top_listings == []
    assert result.conversion_hint.orders_total == 0
    assert result.conversion_hint.views_total == 0
    assert result.conversion_hint.conversion_pct == 0.0


def test_vendor_scope_isolation() -> None:
    a = compute_vendor_analytics(VENDOR_A, 7)
    b = compute_vendor_analytics(VENDOR_B, 7)

    # Vendor A never sees vendor B's order (20_000, its listing) or views.
    a_listing_ids = {row.listing_id for row in a.top_listings}
    assert LISTING_B not in a_listing_ids
    assert sum(a.sales_ngwee_by_day) == SALES_A_7

    # Vendor B sees only its own single order and view.
    assert sum(b.sales_ngwee_by_day) == 20_000
    assert sum(b.orders_by_day) == 1
    assert sum(b.views_by_day) == 1
    assert {row.listing_id for row in b.top_listings} == {LISTING_B}
