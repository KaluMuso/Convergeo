"""Regression coverage for PR-F2 (E2E run #52, RC-4): a canonical product's
search document must project its real listing price range instead of a
hardcoded NULL/NULL, without ever fabricating a K0.00 price, and must stay
in sync as listings/vendors change — see
supabase/migrations/20260827020000_search_product_price_projection.sql.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from app.staging.seed_sql import build_seed_sql
from app.staging.synthetic_contract import assert_contract_valid, product_fixture
from tests.rls.conftest import PgConn, apply_migrations, resolve_db_url
from tests.test_seed_staging import MIGRATION_SHIM_SQL

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "supabase/migrations/20260827020000_search_product_price_projection.sql"
)


@pytest.fixture(scope="module")
def migrated_db() -> Generator[PgConn, None, None]:
    url = resolve_db_url()
    conn = PgConn(url)
    if not conn.run("SELECT 1").ok:
        pytest.skip(f"Postgres not reachable at {url}")
    conn.run("DROP SCHEMA IF EXISTS public CASCADE")
    conn.run("CREATE SCHEMA public")
    conn.run("DROP SCHEMA IF EXISTS auth CASCADE")
    shim = conn.run(MIGRATION_SHIM_SQL)
    if not shim.ok:
        pytest.skip(f"migration shim unavailable: {shim.error}")
    try:
        apply_migrations(conn)
    except Exception as exc:  # noqa: BLE001 — skip when extensions/migrations unavailable
        pytest.skip(f"migrations unavailable: {exc}")
    # Mirrors the real hosted Supabase schema (see test_seed_staging.py) —
    # only needed here for TestConfirmedDefectReproduction's build_seed_sql()
    # call, which writes both columns via _auth_users_sql().
    conn.run("ALTER TABLE auth.users ADD COLUMN IF NOT EXISTS phone text")
    conn.run("ALTER TABLE auth.users ADD COLUMN IF NOT EXISTS phone_confirmed_at timestamptz")
    conn.run(
        "ALTER TABLE auth.users ADD COLUMN IF NOT EXISTS confirmed_at timestamptz "
        "GENERATED ALWAYS AS (LEAST(email_confirmed_at, phone_confirmed_at)) STORED"
    )
    yield conn


def _uid() -> str:
    return str(uuid.uuid4())


def _create_category(conn: PgConn, *, name: str = "Test category") -> str:
    cat_id = _uid()
    slug = f"cat-{cat_id[:8]}"
    result = conn.run(
        "INSERT INTO public.categories (id, name, slug, path, commission_key) "
        f"VALUES ('{cat_id}', '{name}', '{slug}', '/{slug}', 'default')"
    )
    assert result.ok, result.error
    return cat_id


def _create_vendor(
    conn: PgConn, *, status: str = "active", display_name: str = "Test Vendor"
) -> str:
    user_id = _uid()
    vendor_id = _uid()
    result = conn.run(
        f"""
BEGIN;
INSERT INTO auth.users (
  instance_id, id, aud, role, email, encrypted_password,
  email_confirmed_at, raw_app_meta_data, raw_user_meta_data, created_at, updated_at
) VALUES (
  '00000000-0000-0000-0000-000000000000', '{user_id}', 'authenticated', 'authenticated',
  '{user_id}@test.example', 'hash', timezone('utc', now()), '{{}}'::jsonb, '{{}}'::jsonb,
  timezone('utc', now()), timezone('utc', now())
);
INSERT INTO public.profiles (id, phone, display_name)
VALUES ('{user_id}', '+260970{user_id[:6]}', '{display_name} owner')
ON CONFLICT (id) DO UPDATE SET phone = EXCLUDED.phone, display_name = EXCLUDED.display_name;
INSERT INTO public.vendors (id, owner_user_id, slug, display_name, status)
VALUES ('{vendor_id}', '{user_id}', 'vend-{vendor_id[:8]}', '{display_name}', '{status}');
COMMIT;
"""
    )
    assert result.ok, result.error
    return vendor_id


def _create_product(
    conn: PgConn, category_id: str, *, status: str = "active", name: str = "Test Product"
) -> str:
    product_id = _uid()
    slug = f"prod-{product_id[:8]}"
    result = conn.run(
        "INSERT INTO public.products (id, name, slug, category_id, status) "
        f"VALUES ('{product_id}', '{name}', '{slug}', '{category_id}', '{status}')"
    )
    assert result.ok, result.error
    return product_id


def _create_listing(
    conn: PgConn,
    *,
    vendor_id: str,
    product_id: str | None,
    price_ngwee: int = 10000,
    status: str = "active",
    wholesale: bool = False,
    stock_mode: str = "always_available",
) -> str:
    listing_id = _uid()
    product_sql = f"'{product_id}'" if product_id else "NULL"
    result = conn.run(
        "INSERT INTO public.vendor_listings "
        "(id, vendor_id, product_id, price_ngwee, condition, stock_mode, wholesale, status) "
        f"VALUES ('{listing_id}', '{vendor_id}', {product_sql}, {price_ngwee}, 'new', "
        f"'{stock_mode}', {'true' if wholesale else 'false'}, '{status}')"
    )
    assert result.ok, result.error
    return listing_id


def _search_doc(conn: PgConn, entity_kind: str, entity_id: str) -> dict[str, Any] | None:
    result = conn.run(
        "SELECT price_min_ngwee::text, price_max_ngwee::text, is_public::text, updated_at::text "
        "FROM public.search_documents "
        f"WHERE entity_kind = '{entity_kind}' AND entity_id = '{entity_id}'"
    )
    assert result.ok, result.error
    if not result.rows:
        return None
    # PgConn.run uses `-At` (unaligned, tuples-only); multiple columns come
    # back pipe-separated by psql's default field separator.
    parts = result.rows[0].split("|")
    return {
        "price_min_ngwee": parts[0] if parts[0] != "" else None,
        "price_max_ngwee": parts[1] if len(parts) > 1 and parts[1] != "" else None,
        "is_public": parts[2] if len(parts) > 2 else None,
        "updated_at": parts[3] if len(parts) > 3 else None,
    }


def _search_doc_or_fail(conn: PgConn, entity_kind: str, entity_id: str) -> dict[str, Any]:
    doc = _search_doc(conn, entity_kind, entity_id)
    assert doc is not None, f"no search_documents row for {entity_kind}:{entity_id}"
    return doc


class TestProductPriceAggregation:
    def test_one_eligible_listing_min_equals_max(self, migrated_db: PgConn) -> None:
        cat = _create_category(migrated_db)
        vendor = _create_vendor(migrated_db)
        product = _create_product(migrated_db, cat)
        _create_listing(migrated_db, vendor_id=vendor, product_id=product, price_ngwee=12500)

        doc = _search_doc(migrated_db, "product", product)
        assert doc is not None
        assert doc["price_min_ngwee"] == "12500"
        assert doc["price_max_ngwee"] == "12500"

    def test_multiple_eligible_listings_correct_min_max(self, migrated_db: PgConn) -> None:
        cat = _create_category(migrated_db)
        vendor_a = _create_vendor(migrated_db, display_name="Vendor A")
        vendor_b = _create_vendor(migrated_db, display_name="Vendor B")
        product = _create_product(migrated_db, cat)
        _create_listing(migrated_db, vendor_id=vendor_a, product_id=product, price_ngwee=12500)
        _create_listing(migrated_db, vendor_id=vendor_b, product_id=product, price_ngwee=14900)

        doc = _search_doc(migrated_db, "product", product)
        assert doc is not None
        assert doc["price_min_ngwee"] == "12500"
        assert doc["price_max_ngwee"] == "14900"

    def test_inactive_listing_excluded(self, migrated_db: PgConn) -> None:
        cat = _create_category(migrated_db)
        vendor = _create_vendor(migrated_db)
        product = _create_product(migrated_db, cat)
        _create_listing(migrated_db, vendor_id=vendor, product_id=product, price_ngwee=12500)
        _create_listing(
            migrated_db, vendor_id=vendor, product_id=product, price_ngwee=99999, status="paused"
        )

        doc = _search_doc(migrated_db, "product", product)
        assert doc is not None
        assert doc["price_min_ngwee"] == "12500"
        assert doc["price_max_ngwee"] == "12500"

    def test_inactive_vendor_listing_excluded(self, migrated_db: PgConn) -> None:
        cat = _create_category(migrated_db)
        vendor_active = _create_vendor(migrated_db, status="active", display_name="Active vendor")
        vendor_suspended = _create_vendor(
            migrated_db, status="suspended", display_name="Suspended vendor"
        )
        product = _create_product(migrated_db, cat)
        _create_listing(
            migrated_db, vendor_id=vendor_active, product_id=product, price_ngwee=12500
        )
        _create_listing(migrated_db, vendor_id=vendor_suspended, product_id=product, price_ngwee=1)

        doc = _search_doc(migrated_db, "product", product)
        assert doc is not None
        assert doc["price_min_ngwee"] == "12500"
        assert doc["price_max_ngwee"] == "12500"

    def test_no_eligible_listings_is_honest_null_not_zero(self, migrated_db: PgConn) -> None:
        cat = _create_category(migrated_db)
        vendor = _create_vendor(migrated_db, status="suspended")
        product = _create_product(migrated_db, cat)
        _create_listing(migrated_db, vendor_id=vendor, product_id=product, price_ngwee=12500)

        doc = _search_doc(migrated_db, "product", product)
        assert doc is not None
        assert doc["price_min_ngwee"] is None
        assert doc["price_max_ngwee"] is None
        # Never a fabricated zero: NULL is distinct from a stored "0".
        assert doc["price_min_ngwee"] != "0"
        assert doc["price_max_ngwee"] != "0"
        # Product stays public — governed by products.status alone, unchanged.
        assert doc["is_public"] == "true"

    def test_listing_level_search_pricing_unchanged(self, migrated_db: PgConn) -> None:
        cat = _create_category(migrated_db)
        vendor = _create_vendor(migrated_db)
        product = _create_product(migrated_db, cat)
        listing = _create_listing(
            migrated_db, vendor_id=vendor, product_id=product, price_ngwee=12500
        )

        doc = _search_doc(migrated_db, "listing", listing)
        assert doc is not None
        assert doc["price_min_ngwee"] == "12500"
        assert doc["price_max_ngwee"] == "12500"
        assert doc["is_public"] == "true"


class TestSyncTriggerRefreshes:
    def test_listing_insert_refreshes_product_document(self, migrated_db: PgConn) -> None:
        cat = _create_category(migrated_db)
        vendor = _create_vendor(migrated_db)
        product = _create_product(migrated_db, cat)

        before = _search_doc(migrated_db, "product", product)
        assert before is not None
        assert before["price_min_ngwee"] is None

        _create_listing(migrated_db, vendor_id=vendor, product_id=product, price_ngwee=8000)

        after = _search_doc(migrated_db, "product", product)
        assert after is not None
        assert after["price_min_ngwee"] == "8000"

    def test_listing_price_change_refreshes_product_document(self, migrated_db: PgConn) -> None:
        cat = _create_category(migrated_db)
        vendor = _create_vendor(migrated_db)
        product = _create_product(migrated_db, cat)
        listing = _create_listing(
            migrated_db, vendor_id=vendor, product_id=product, price_ngwee=8000
        )

        assert _search_doc_or_fail(migrated_db, "product", product)["price_min_ngwee"] == "8000"

        result = migrated_db.run(
            f"UPDATE public.vendor_listings SET price_ngwee = 9500 WHERE id = '{listing}'"
        )
        assert result.ok, result.error

        after = _search_doc_or_fail(migrated_db, "product", product)
        assert after["price_min_ngwee"] == "9500"
        assert after["price_max_ngwee"] == "9500"

    def test_listing_status_change_refreshes_product_document(self, migrated_db: PgConn) -> None:
        cat = _create_category(migrated_db)
        vendor = _create_vendor(migrated_db)
        product = _create_product(migrated_db, cat)
        listing = _create_listing(
            migrated_db, vendor_id=vendor, product_id=product, price_ngwee=8000
        )

        assert _search_doc_or_fail(migrated_db, "product", product)["price_min_ngwee"] == "8000"

        paused = migrated_db.run(
            f"UPDATE public.vendor_listings SET status = 'paused' WHERE id = '{listing}'"
        )
        assert paused.ok, paused.error
        after_pause = _search_doc_or_fail(migrated_db, "product", product)
        assert after_pause["price_min_ngwee"] is None

        reactivated = migrated_db.run(
            f"UPDATE public.vendor_listings SET status = 'active' WHERE id = '{listing}'"
        )
        assert reactivated.ok, reactivated.error
        after_reactivate = _search_doc_or_fail(migrated_db, "product", product)
        assert after_reactivate["price_min_ngwee"] == "8000"

    def test_listing_delete_refreshes_product_document(self, migrated_db: PgConn) -> None:
        cat = _create_category(migrated_db)
        vendor = _create_vendor(migrated_db)
        product = _create_product(migrated_db, cat)
        keep = _create_listing(migrated_db, vendor_id=vendor, product_id=product, price_ngwee=8000)
        drop = _create_listing(migrated_db, vendor_id=vendor, product_id=product, price_ngwee=5000)

        assert _search_doc_or_fail(migrated_db, "product", product)["price_min_ngwee"] == "5000"

        deleted = migrated_db.run(f"DELETE FROM public.vendor_listings WHERE id = '{drop}'")
        assert deleted.ok, deleted.error

        after = _search_doc_or_fail(migrated_db, "product", product)
        assert after["price_min_ngwee"] == "8000"
        assert after["price_max_ngwee"] == "8000"
        # The deleted listing's own document is gone, not just unpublished.
        assert _search_doc(migrated_db, "listing", drop) is None
        assert _search_doc(migrated_db, "listing", keep) is not None

    def test_listing_moved_between_products_refreshes_both(self, migrated_db: PgConn) -> None:
        cat = _create_category(migrated_db)
        vendor = _create_vendor(migrated_db)
        product_a = _create_product(migrated_db, cat, name="Product A")
        product_b = _create_product(migrated_db, cat, name="Product B")
        _create_listing(migrated_db, vendor_id=vendor, product_id=product_a, price_ngwee=3000)
        moving = _create_listing(
            migrated_db, vendor_id=vendor, product_id=product_a, price_ngwee=7000
        )

        assert _search_doc_or_fail(migrated_db, "product", product_a)["price_max_ngwee"] == "7000"
        assert _search_doc_or_fail(migrated_db, "product", product_b)["price_min_ngwee"] is None

        moved = migrated_db.run(
            f"UPDATE public.vendor_listings SET product_id = '{product_b}' WHERE id = '{moving}'"
        )
        assert moved.ok, moved.error

        after_a = _search_doc_or_fail(migrated_db, "product", product_a)
        after_b = _search_doc_or_fail(migrated_db, "product", product_b)
        assert after_a["price_min_ngwee"] == "3000"
        assert after_a["price_max_ngwee"] == "3000"
        assert after_b["price_min_ngwee"] == "7000"
        assert after_b["price_max_ngwee"] == "7000"

    def test_vendor_status_change_refreshes_affected_product_documents(
        self, migrated_db: PgConn
    ) -> None:
        cat = _create_category(migrated_db)
        vendor = _create_vendor(migrated_db, status="active")
        product_a = _create_product(migrated_db, cat, name="Vendor-cascade product A")
        product_b = _create_product(migrated_db, cat, name="Vendor-cascade product B")
        _create_listing(migrated_db, vendor_id=vendor, product_id=product_a, price_ngwee=4000)
        _create_listing(migrated_db, vendor_id=vendor, product_id=product_b, price_ngwee=6000)

        assert _search_doc_or_fail(migrated_db, "product", product_a)["price_min_ngwee"] == "4000"
        assert _search_doc_or_fail(migrated_db, "product", product_b)["price_min_ngwee"] == "6000"

        suspended = migrated_db.run(
            f"UPDATE public.vendors SET status = 'suspended' WHERE id = '{vendor}'"
        )
        assert suspended.ok, suspended.error

        assert _search_doc_or_fail(migrated_db, "product", product_a)["price_min_ngwee"] is None
        assert _search_doc_or_fail(migrated_db, "product", product_b)["price_min_ngwee"] is None

        reactivated = migrated_db.run(
            f"UPDATE public.vendors SET status = 'active' WHERE id = '{vendor}'"
        )
        assert reactivated.ok, reactivated.error

        assert _search_doc_or_fail(migrated_db, "product", product_a)["price_min_ngwee"] == "4000"
        assert _search_doc_or_fail(migrated_db, "product", product_b)["price_min_ngwee"] == "6000"

    def test_listing_reassigned_to_different_vendor_refreshes_product_document(
        self, migrated_db: PgConn
    ) -> None:
        """The price aggregate's JOIN to vendors means vendor_id alone gates
        eligibility: reassigning a listing to a different vendor changes
        whether it counts, even with product_id/price_ngwee/status all
        unchanged. The sync trigger must catch that, not just product_id/
        price/status changes.
        """
        cat = _create_category(migrated_db)
        vendor_a = _create_vendor(migrated_db, status="active", display_name="Vendor A (active)")
        vendor_b = _create_vendor(
            migrated_db, status="suspended", display_name="Vendor B (inactive)"
        )
        product = _create_product(migrated_db, cat, name="Vendor-reassignment product")
        listing = _create_listing(
            migrated_db, vendor_id=vendor_a, product_id=product, price_ngwee=11000
        )

        assert _search_doc_or_fail(migrated_db, "product", product)["price_min_ngwee"] == "11000"

        # Same listing, same product_id/price_ngwee/status — only vendor_id
        # changes, from active Vendor A to inactive Vendor B.
        reassigned = migrated_db.run(
            f"UPDATE public.vendor_listings SET vendor_id = '{vendor_b}' WHERE id = '{listing}'"
        )
        assert reassigned.ok, reassigned.error

        after_reassign = _search_doc_or_fail(migrated_db, "product", product)
        assert after_reassign["price_min_ngwee"] is None
        assert after_reassign["price_max_ngwee"] is None
        # Honest no-offer, never a fabricated zero.
        assert after_reassign["price_min_ngwee"] != "0"
        assert after_reassign["is_public"] == "true"

        # Reassign back to an active vendor — price must return.
        vendor_c = _create_vendor(migrated_db, status="active", display_name="Vendor C (active)")
        reassigned_back = migrated_db.run(
            f"UPDATE public.vendor_listings SET vendor_id = '{vendor_c}' WHERE id = '{listing}'"
        )
        assert reassigned_back.ok, reassigned_back.error

        after_return = _search_doc_or_fail(migrated_db, "product", product)
        assert after_return["price_min_ngwee"] == "11000"
        assert after_return["price_max_ngwee"] == "11000"


class TestBackfillAndReplay:
    def test_existing_broken_document_is_backfilled(self, migrated_db: PgConn) -> None:
        cat = _create_category(migrated_db)
        vendor = _create_vendor(migrated_db)
        product = _create_product(migrated_db, cat, name="Pre-fix broken doc")
        _create_listing(migrated_db, vendor_id=vendor, product_id=product, price_ngwee=12500)
        _create_listing(migrated_db, vendor_id=vendor, product_id=product, price_ngwee=14900)

        # Simulate the pre-fix state the live bug produced: a real, active,
        # multi-seller product whose document still carries the old NULL/NULL.
        broken = migrated_db.run(
            "UPDATE public.search_documents SET price_min_ngwee = NULL, price_max_ngwee = NULL "
            f"WHERE entity_kind = 'product' AND entity_id = '{product}'"
        )
        assert broken.ok, broken.error
        assert _search_doc_or_fail(migrated_db, "product", product)["price_min_ngwee"] is None

        # No manual production SQL step: reapplying the migration file alone
        # (exactly what the backfill DO block inside it does) repairs it.
        replayed = migrated_db.run_file(MIGRATION_PATH)
        assert replayed.ok, replayed.error

        after = _search_doc_or_fail(migrated_db, "product", product)
        assert after["price_min_ngwee"] == "12500"
        assert after["price_max_ngwee"] == "14900"

    def test_migration_replay_is_idempotent(self, migrated_db: PgConn) -> None:
        cat = _create_category(migrated_db)
        vendor = _create_vendor(migrated_db)
        product = _create_product(migrated_db, cat, name="Idempotency check")
        _create_listing(migrated_db, vendor_id=vendor, product_id=product, price_ngwee=5500)

        first = _search_doc_or_fail(migrated_db, "product", product)
        assert first["price_min_ngwee"] == "5500"

        replayed = migrated_db.run_file(MIGRATION_PATH)
        assert replayed.ok, replayed.error

        second = _search_doc_or_fail(migrated_db, "product", product)
        assert second["price_min_ngwee"] == "5500"
        assert second["price_max_ngwee"] == "5500"
        assert second["is_public"] == "true"

        # Replaying a second time must also succeed cleanly (functions are
        # CREATE OR REPLACE, the backfill loop re-converges every time).
        replayed_again = migrated_db.run_file(MIGRATION_PATH)
        assert replayed_again.ok, replayed_again.error


class TestRlsAndSecurityContract:
    def test_public_role_sees_only_is_public_true_product_docs(self, migrated_db: PgConn) -> None:
        cat = _create_category(migrated_db)
        vendor_active = _create_vendor(
            migrated_db, status="active", display_name="RLS visible vendor"
        )
        product_visible = _create_product(
            migrated_db, cat, status="active", name="RLS visible product"
        )
        _create_listing(
            migrated_db, vendor_id=vendor_active, product_id=product_visible, price_ngwee=12500
        )

        product_hidden = _create_product(
            migrated_db, cat, status="pending_moderation", name="RLS hidden product"
        )

        result = migrated_db.run(
            "SET LOCAL ROLE anon; "
            "SELECT entity_id::text FROM public.search_documents "
            "WHERE entity_kind = 'product' AND entity_id IN "
            f"('{product_visible}', '{product_hidden}') "
            "ORDER BY entity_id; RESET ROLE;"
        )
        assert result.ok, result.error
        assert product_visible in result.rows
        assert product_hidden not in result.rows

    def test_anon_cannot_write_search_documents(self, migrated_db: PgConn) -> None:
        cat = _create_category(migrated_db)
        _create_vendor(migrated_db)
        product = _create_product(migrated_db, cat)

        result = migrated_db.run(
            "SET LOCAL ROLE anon; "
            "UPDATE public.search_documents SET price_min_ngwee = 1 "
            f"WHERE entity_kind = 'product' AND entity_id = '{product}'; "
            "RESET ROLE;"
        )
        assert not result.ok, "anon must not be able to write search_documents"

    def test_search_upsert_product_is_still_security_definer_with_pinned_search_path(
        self, migrated_db: PgConn
    ) -> None:
        result = migrated_db.run(
            "SELECT prosecdef::text, "
            "(SELECT array_to_string(proconfig, ',') FROM pg_proc "
            " WHERE proname = 'search_upsert_product') "
            "FROM pg_proc WHERE proname = 'search_upsert_product'"
        )
        assert result.ok, result.error
        row = result.rows[0]
        secdef, config = row.split("|", 1) if "|" in row else (row, "")
        assert secdef == "true"
        assert "search_path=public,extensions" in config.replace(" ", "")

    def test_grants_on_search_documents_unchanged(self, migrated_db: PgConn) -> None:
        for role, expected in (("anon", "true"), ("authenticated", "true")):
            result = migrated_db.run(
                f"SELECT has_table_privilege('{role}', 'public.search_documents', 'SELECT')::text"
            )
            assert result.ok and result.rows == [expected]
            result = migrated_db.run(
                f"SELECT has_table_privilege('{role}', 'public.search_documents', 'INSERT')::text"
            )
            assert result.ok and result.rows == ["false"], f"{role} must not gain write access"

        result = migrated_db.run(
            "SELECT has_table_privilege('service_role', 'public.search_documents', 'UPDATE')::text"
        )
        assert result.ok and result.rows == ["true"]


class TestConfirmedDefectReproduction:
    """Closes the loop on the exact live finding from E2E run #52: the
    canonical multiseller fixture (product A, 2 active listings from 2
    active vendors, 12500/14900 ngwee) seeded via the real
    build_seed_sql() — the same SQL the staging E2E workflow runs — must
    now project 12500/14900, not NULL/NULL."""

    def test_canonical_multiseller_fixture_no_longer_shows_null_null(
        self, migrated_db: PgConn
    ) -> None:
        assert_contract_valid()
        seeded = migrated_db.run_script(build_seed_sql())
        assert seeded.ok, seeded.error or "canonical seed failed"

        product_a = product_fixture("PRODUCT_A")
        doc = _search_doc(migrated_db, "product", product_a.product_id)
        assert doc is not None

        expected_prices = sorted(listing.price_ngwee for listing in product_a.listings)
        assert doc["price_min_ngwee"] == str(expected_prices[0])
        assert doc["price_max_ngwee"] == str(expected_prices[-1])
        assert doc["price_min_ngwee"] != "0"
        assert doc["price_max_ngwee"] != "0"
