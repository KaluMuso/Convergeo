"""Vendor storefront collections — ownership guard and CRUD."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from tests.rls.conftest import (
    PgConn,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)

OWNER_A = "33333333-3333-3333-3333-333333333333"
OWNER_B = "44444444-4444-4444-4444-444444444444"
VENDOR_A = "d9a00000-0000-0000-0000-00000000000a"
VENDOR_B = "d9b00000-0000-0000-0000-00000000000b"
LISTING_A = "d9100000-0000-0000-0000-00000000000a"
LISTING_B = "d9100000-0000-0000-0000-00000000000b"
COLLECTION_A = "d9200000-0000-0000-0000-00000000000a"


def _seed_collections(db: PgConn) -> None:
    script = (
        "BEGIN;\n"
        "SET LOCAL role service_role;\n"
        'SET LOCAL "request.jwt.claims" = \'{"role":"service_role"}\';\n'
    )
    for vid, owner, slug in [
        (VENDOR_A, OWNER_A, "collections-a"),
        (VENDOR_B, OWNER_B, "collections-b"),
    ]:
        script += f"""
INSERT INTO public.vendors (id, owner_user_id, slug, display_name, status, kyc_tier)
VALUES ('{vid}', '{owner}', '{slug}', 'Collections {slug}', 'active', 1)
ON CONFLICT (id) DO NOTHING;
"""
    for lid, vid, title in [
        (LISTING_A, VENDOR_A, "Collection Listing A"),
        (LISTING_B, VENDOR_B, "Collection Listing B"),
    ]:
        script += f"""
INSERT INTO public.vendor_listings (
  id, vendor_id, title_override, price_ngwee, condition, stock_mode, status
) VALUES ('{lid}', '{vid}', '{title}', 25000, 'new', 'always_available', 'active')
ON CONFLICT (id) DO NOTHING;
"""
    script += f"""
INSERT INTO public.vendor_storefront_collections (
  id, vendor_id, title, slug, sort_order, status
) VALUES (
  '{COLLECTION_A}', '{VENDOR_A}', 'Featured', 'featured', 0, 'active'
) ON CONFLICT (id) DO NOTHING;
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
    _seed_collections(conn)
    yield conn


def test_collection_cannot_contain_another_vendors_listing(db: PgConn) -> None:
    script = f"""
BEGIN;
SET LOCAL role service_role;
SET LOCAL "request.jwt.claims" = '{{"role":"service_role"}}';
INSERT INTO public.vendor_storefront_collection_items (collection_id, listing_id, sort_order)
VALUES ('{COLLECTION_A}', '{LISTING_B}', 0);
COMMIT;
"""
    result = db.run(script)
    assert not result.ok
    assert result.error is not None
    assert "does not belong" in result.error.lower() or "check_violation" in result.error.lower()


def test_collection_accepts_own_listing(db: PgConn) -> None:
    script = f"""
BEGIN;
SET LOCAL role service_role;
SET LOCAL "request.jwt.claims" = '{{"role":"service_role"}}';
DELETE FROM public.vendor_storefront_collection_items
  WHERE collection_id = '{COLLECTION_A}' AND listing_id = '{LISTING_A}';
INSERT INTO public.vendor_storefront_collection_items (collection_id, listing_id, sort_order)
VALUES ('{COLLECTION_A}', '{LISTING_A}', 0);
COMMIT;
"""
    result = db.run(script)
    assert result.ok, result.error
