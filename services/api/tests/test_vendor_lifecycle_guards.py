"""Client must not self-activate vendors or set trust signals (0057).

These are MONEY/TRUST-critical RLS trigger tests. They skip when Postgres is
unreachable or migrations cannot apply (e.g. missing pgvector in a bare local
Postgres). CI with the full Supabase stack exercises them.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from tests.rls.conftest import (
    PgConn,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)

CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
VENDOR_OWNER_ID = "33333333-3333-3333-3333-333333333333"


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
        try:
            apply_migrations(conn)
        except Exception as exc:  # noqa: BLE001 — surface skip for missing extensions
            pytest.skip(f"migrations unavailable: {exc}")
    seed_matrix_fixtures(conn)
    yield conn


def _as_authenticated(conn: PgConn, user_id: str) -> None:
    claims = (
        '{"role":"authenticated","sub":"'
        + user_id
        + '","aal":"aal1"}'
    ).replace("'", "''")
    conn.run("BEGIN;")
    conn.run("SET LOCAL role authenticated;")
    conn.run(
        f"DO $$ BEGIN PERFORM set_config('request.jwt.claims', '{claims}', true); END $$;"
    )


def _rollback(conn: PgConn) -> None:
    conn.run("ROLLBACK;")


class TestVendorLifecycleClientGuards:
    def test_owner_cannot_insert_active_vendor(self, db: PgConn) -> None:
        vendor_id = str(uuid.uuid4())
        slug = f"evil-{vendor_id[:8]}"
        _as_authenticated(db, CUSTOMER_ID)
        result = db.run(
            f"""
            INSERT INTO public.vendors (
              id, owner_user_id, slug, display_name, status, kyc_tier, preferred_badge
            ) VALUES (
              '{vendor_id}', '{CUSTOMER_ID}', '{slug}', 'Evil Shop',
              'active', 3, true
            );
            """
        )
        _rollback(db)
        assert not result.ok
        assert result.error is not None
        assert "server-controlled" in result.error

    def test_owner_can_insert_draft_without_trust_signals(self, db: PgConn) -> None:
        vendor_id = str(uuid.uuid4())
        slug = f"draft-{vendor_id[:8]}"
        _as_authenticated(db, CUSTOMER_ID)
        result = db.run(
            f"""
            INSERT INTO public.vendors (
              id, owner_user_id, slug, display_name, status
            ) VALUES (
              '{vendor_id}', '{CUSTOMER_ID}', '{slug}', 'Draft Shop', 'draft'
            );
            """
        )
        _rollback(db)
        # RLS may still deny customer insert in some personas; trigger must not
        # be the failure mode for a legitimate draft row.
        if not result.ok:
            assert "server-controlled" not in (result.error or "")

    def test_owner_cannot_patch_preferred_badge(self, db: PgConn) -> None:
        vendor_id_row = db.run(
            "SELECT id::text FROM public.vendors "
            f"WHERE owner_user_id = '{VENDOR_OWNER_ID}' LIMIT 1;"
        )
        if not vendor_id_row.ok or not vendor_id_row.rows:
            pytest.skip("seed has no vendor-owned storefront")
        vendor_id = vendor_id_row.rows[0]
        _as_authenticated(db, VENDOR_OWNER_ID)
        result = db.run(
            f"UPDATE public.vendors SET preferred_badge = true WHERE id = '{vendor_id}';"
        )
        _rollback(db)
        assert not result.ok
        assert result.error is not None
        assert "server-controlled" in result.error
