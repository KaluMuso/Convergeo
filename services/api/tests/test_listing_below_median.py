"""below_median search boost signal (0034).

0009's `search_apply_boost` gives a +0.05 RRF lift when
`boost_signals->>'below_median'` is true, but the projection hard-coded the
signal to false, so it never fired. 0034 computes it as "priced below the median
of all active/publishable listings for the SAME canonical product".

These tests require a real Postgres (the migration chain + triggers) and skip
otherwise. The suite is isolation-clean: every test seeds its own product +
listings and tears them down (shared PG).
"""

from __future__ import annotations

import shutil
import uuid
from collections.abc import Generator
from dataclasses import dataclass, field

import pytest
from tests.rls.conftest import (
    MIGRATIONS_DIR,
    PgConn,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)

# Active, KYC-T2 vendor seeded by seed_matrix_fixtures.
VENDOR_SHOP_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


@pytest.fixture(scope="module")
def db() -> Generator[PgConn, None, None]:
    if shutil.which("psql") is None:
        pytest.skip("psql not available")
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
    yield conn


@dataclass
class Scratch:
    """Test-owned product + listings, cleaned up on teardown."""

    product_id: str
    listing_ids: list[str] = field(default_factory=list)


def _category_id(conn: PgConn) -> str:
    result = conn.run("SELECT id FROM public.categories ORDER BY created_at LIMIT 1")
    assert result.ok and result.rows, result.error
    return result.rows[0]


def _new_product(conn: PgConn, scratch: Scratch) -> None:
    cat = _category_id(conn)
    result = conn.run(
        f"""
        INSERT INTO public.products (id, name, slug, category_id, status)
        VALUES ('{scratch.product_id}', 'BM Test',
                'bm-test-{scratch.product_id[:8]}', '{cat}', 'active');
        """
    )
    assert result.ok, result.error


def _add_listing(
    conn: PgConn,
    scratch: Scratch,
    *,
    price: int,
    standalone: bool = False,
    stock_qty: int = 5,
) -> str:
    """Add an active listing; attaches to the scratch product unless standalone."""
    lid = str(uuid.uuid4())
    prod = "NULL" if standalone else f"'{scratch.product_id}'"
    result = conn.run(
        f"""
        INSERT INTO public.vendor_listings (
          id, vendor_id, product_id, title_override, price_ngwee,
          condition, stock_mode, stock_qty, status
        ) VALUES (
          '{lid}', '{VENDOR_SHOP_A}', {prod}, 'L{price}', {price},
          'new', 'tracked', {stock_qty}, 'active'
        );
        """
    )
    assert result.ok, result.error
    scratch.listing_ids.append(lid)
    return lid


def _project(conn: PgConn, listing_id: str) -> None:
    """Force a steady-state projection against the full current peer set."""
    result = conn.run(f"SELECT public.search_upsert_listing('{listing_id}')")
    assert result.ok, result.error


def _signal(conn: PgConn, listing_id: str, key: str) -> str | None:
    result = conn.run(
        f"""
        SELECT boost_signals->>'{key}'
        FROM public.search_documents
        WHERE entity_kind = 'listing' AND entity_id = '{listing_id}'
        """
    )
    assert result.ok, result.error
    return result.rows[0] if result.rows else None


def _teardown(conn: PgConn, scratch: Scratch) -> None:
    if scratch.listing_ids:
        ids = ", ".join(f"'{i}'" for i in scratch.listing_ids)
        # search_documents rows are removed by the vendor_listings delete cascade
        # via the sync trigger; delete listings then the product.
        conn.run(f"DELETE FROM public.vendor_listings WHERE id IN ({ids});")
    conn.run(f"DELETE FROM public.products WHERE id = '{scratch.product_id}';")


# ---------------------------------------------------------------------------
# Migration presence
# ---------------------------------------------------------------------------


def test_migration_0034_shipped_and_replaces_projection(db: PgConn) -> None:
    """0034 exists and the live function body actually computes the median."""
    assert MIGRATIONS_DIR.joinpath("0034_listing_below_median.sql").exists()
    body = db.run(
        "SELECT pg_get_functiondef('public.search_upsert_listing(uuid)'::regprocedure)"
    )
    assert body.ok, body.error
    src = "\n".join(body.rows)  # pg_get_functiondef spans many lines
    assert "percentile_cont" in src
    assert "below_median" in src
    # The dead constant is gone: below_median is no longer hard-set to false.
    assert "'below_median', false" not in src


# ---------------------------------------------------------------------------
# below_median computation
# ---------------------------------------------------------------------------


def test_below_median_true_for_cheaper_than_product_median(db: PgConn) -> None:
    """Prices 100/200/300 -> median 200 -> only the 100 offer is below median."""
    scratch = Scratch(product_id=str(uuid.uuid4()))
    try:
        _new_product(db, scratch)
        l100 = _add_listing(db, scratch, price=100)
        l200 = _add_listing(db, scratch, price=200)
        l300 = _add_listing(db, scratch, price=300)

        # Steady-state: reproject each against the full peer set.
        for lid in (l100, l200, l300):
            _project(db, lid)

        assert _signal(db, l100, "below_median") == "true"
        assert _signal(db, l200, "below_median") == "false"  # equals median, not below
        assert _signal(db, l300, "below_median") == "false"
        # sanity: other signals still populated (not clobbered to null)
        assert _signal(db, l100, "in_stock") == "true"
    finally:
        _teardown(db, scratch)


def test_price_update_reprojects_below_median_via_trigger(db: PgConn) -> None:
    """Dropping a listing's price below the new median flips its signal on write."""
    scratch = Scratch(product_id=str(uuid.uuid4()))
    try:
        _new_product(db, scratch)
        _add_listing(db, scratch, price=100)
        _add_listing(db, scratch, price=200)
        top = _add_listing(db, scratch, price=300)
        for lid in scratch.listing_ids:
            _project(db, lid)
        assert _signal(db, top, "below_median") == "false"

        # UPDATE fires vendor_listings_search_sync -> search_upsert_listing(top).
        # New set {100, 200, 40} -> median 100 -> 40 < 100 -> true.
        upd = db.run(
            f"UPDATE public.vendor_listings SET price_ngwee = 40 WHERE id = '{top}'"
        )
        assert upd.ok, upd.error
        assert _signal(db, top, "below_median") == "true"
    finally:
        _teardown(db, scratch)


def test_single_offer_is_not_below_its_own_median(db: PgConn) -> None:
    """A product's only listing equals the median and must not be boosted."""
    scratch = Scratch(product_id=str(uuid.uuid4()))
    try:
        _new_product(db, scratch)
        only = _add_listing(db, scratch, price=500)
        _project(db, only)
        assert _signal(db, only, "below_median") == "false"
    finally:
        _teardown(db, scratch)


def test_standalone_listing_has_no_below_median(db: PgConn) -> None:
    """A listing with no canonical product has no price-comparison peer set."""
    scratch = Scratch(product_id=str(uuid.uuid4()))
    try:
        _new_product(db, scratch)  # created but unused by the standalone listing
        standalone = _add_listing(db, scratch, price=1, standalone=True)
        _project(db, standalone)
        assert _signal(db, standalone, "below_median") == "false"
    finally:
        _teardown(db, scratch)
