"""Vendor analytics summary — listing views + orders + GMV over 30 days."""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from app.routers.vendor_analytics import compute_vendor_analytics_summary
from app.services.analytics.listing_views import record_listing_views
from tests.rls.conftest import (
    PgConn,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)

OWNER_A = "33333333-3333-3333-3333-333333333333"
CUSTOMER_A = "11111111-1111-1111-1111-111111111111"
VENDOR_A = "c9a00000-0000-0000-0000-00000000000a"
VENDOR_B = "c9b00000-0000-0000-0000-00000000000b"
LISTING_A = "c9100000-0000-0000-0000-00000000000a"
LISTING_B = "c9100000-0000-0000-0000-00000000000b"
ORDER_A1 = "c9200000-0000-0000-0000-000000000001"
ORDER_B1 = "c9200000-0000-0000-0000-0000000000b1"
ITEM_A1 = "c9300000-0000-0000-0000-000000000001"
ITEM_B1 = "c9300000-0000-0000-0000-0000000000b1"
SESSION_A = "c9s00000-0000-0000-0000-00000000000a"
SESSION_B = "c9s00000-0000-0000-0000-00000000000b"


def _seed_summary(db: PgConn) -> None:
    script = (
        "BEGIN;\n"
        "SET LOCAL role service_role;\n"
        'SET LOCAL "request.jwt.claims" = \'{"role":"service_role"}\';\n'
    )
    script += f"""
DELETE FROM public.listing_view_dedup
  WHERE listing_id IN ('{LISTING_A}', '{LISTING_B}');
DELETE FROM public.listing_analytics
  WHERE listing_id IN ('{LISTING_A}', '{LISTING_B}');
DELETE FROM public.order_item_products WHERE order_item_id IN (
  SELECT id FROM public.order_items WHERE order_id IN ('{ORDER_A1}', '{ORDER_B1}'));
DELETE FROM public.order_items WHERE order_id IN ('{ORDER_A1}', '{ORDER_B1}');
DELETE FROM public.orders WHERE id IN ('{ORDER_A1}', '{ORDER_B1}');
DELETE FROM public.checkout_groups WHERE idempotency_key LIKE 'summary-fixture%';
"""
    for vid, owner, slug in [
        (VENDOR_A, OWNER_A, "summary-a"),
        (VENDOR_B, "44444444-4444-4444-4444-444444444444", "summary-b"),
    ]:
        script += f"""
INSERT INTO public.vendors (id, owner_user_id, slug, display_name, status, kyc_tier)
VALUES ('{vid}', '{owner}', '{slug}', 'Summary {slug}', 'active', 1)
ON CONFLICT (id) DO NOTHING;
"""
    for lid, vid, title in [
        (LISTING_A, VENDOR_A, "Summary Phone A"),
        (LISTING_B, VENDOR_B, "Summary Phone B"),
    ]:
        script += f"""
INSERT INTO public.vendor_listings (
  id, vendor_id, title_override, price_ngwee, condition, stock_mode, status
) VALUES ('{lid}', '{vid}', '{title}', 50000, 'new', 'always_available', 'active')
ON CONFLICT (id) DO NOTHING;
"""
    script += f"""
INSERT INTO public.checkout_groups (
  id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee, total_ngwee, status
) VALUES (
  'c9c00000-0000-0000-0000-000000000001', '{CUSTOMER_A}', 'summary-fixture-1', 0, 0, 0, 'completed'
);
INSERT INTO public.orders (
  id, checkout_group_id, vendor_id, customer_id, status, fulfilment, created_at
) VALUES (
  '{ORDER_A1}', 'c9c00000-0000-0000-0000-000000000001', '{VENDOR_A}', '{CUSTOMER_A}',
  'delivered', 'delivery', timezone('utc', now())
);
INSERT INTO public.order_items (
  id, order_id, item_kind, qty, unit_price_ngwee, title_snapshot
) VALUES ('{ITEM_A1}', '{ORDER_A1}', 'product', 2, 50000, 'snap');
INSERT INTO public.order_item_products (order_item_id, listing_id, product_id)
VALUES ('{ITEM_A1}', '{LISTING_A}', NULL);

INSERT INTO public.checkout_groups (
  id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee, total_ngwee, status
) VALUES (
  'c9c00000-0000-0000-0000-000000000002', '{CUSTOMER_A}', 'summary-fixture-2', 0, 0, 0, 'completed'
);
INSERT INTO public.orders (
  id, checkout_group_id, vendor_id, customer_id, status, fulfilment, created_at
) VALUES (
  '{ORDER_B1}', 'c9c00000-0000-0000-0000-000000000002', '{VENDOR_B}', '{CUSTOMER_A}',
  'delivered', 'delivery', timezone('utc', now())
);
INSERT INTO public.order_items (
  id, order_id, item_kind, qty, unit_price_ngwee, title_snapshot
) VALUES ('{ITEM_B1}', '{ORDER_B1}', 'product', 1, 20000, 'snap');
INSERT INTO public.order_item_products (order_item_id, listing_id, product_id)
VALUES ('{ITEM_B1}', '{LISTING_B}', NULL);
COMMIT;
"""
    result = db.run(script)
    assert result.ok, result.error


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
    _seed_summary(conn)
    yield conn


@pytest.fixture
def db_url_env(db: PgConn) -> Generator[None, None, None]:
    previous = os.environ.get("SUPABASE_DB_URL")
    os.environ["SUPABASE_DB_URL"] = db.dsn
    yield
    if previous is None:
        os.environ.pop("SUPABASE_DB_URL", None)
    else:
        os.environ["SUPABASE_DB_URL"] = previous


def test_summary_aggregates_views_orders_gmv(db_url_env: None) -> None:
    record_listing_views(
        session_id=SESSION_A,
        listing_ids=[LISTING_A],
        view_kind="impression",
    )
    record_listing_views(
        session_id=SESSION_A,
        listing_ids=[LISTING_A],
        view_kind="pdp_view",
    )
    # Vendor B views must not leak into vendor A summary.
    record_listing_views(
        session_id=SESSION_B,
        listing_ids=[LISTING_B],
        view_kind="impression",
    )

    summary = compute_vendor_analytics_summary(VENDOR_A)

    assert summary.window_days == 30
    assert summary.impressions == 1
    assert summary.pdp_views == 1
    assert summary.total_views == 2
    assert summary.total_orders == 1
    assert summary.gmv_ngwee == 100_000
