"""Re-entrant canonical migration replay on rehearsal-shaped schema."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from tests.rls.conftest import PgConn, apply_migrations, resolve_db_url, schema_ready

if shutil.which("psql") is None:
    pytest.skip("psql required for canonical migration replay tests", allow_module_level=True)

REPO_ROOT = Path(__file__).resolve().parents[3]
CANONICAL_MIGRATIONS = (
    "20260813160000_rate_counter_scope_manifest.sql",
    "20260813160100_listing_view_surface_telemetry.sql",
    "20260813160200_security_definer_hardening.sql",
)


@pytest.fixture(scope="module")
def db() -> PgConn:
    url = resolve_db_url()
    conn = PgConn(url)
    if not conn.run("SELECT 1").ok:
        pytest.skip(f"Postgres not reachable at {url}")
    if not schema_ready(conn):
        conn.run("DROP SCHEMA IF EXISTS public CASCADE")
        conn.run("CREATE SCHEMA public")
        conn.run("DROP SCHEMA IF EXISTS auth CASCADE")
        apply_migrations(conn)
    return conn


def test_canonical_migrations_reentrant_on_rehearsal_listing_view(db: PgConn) -> None:
    """Rehearsal overload lacks p_surface default; 60100 must restore canonical defaults."""
    drop_existing = """
DROP FUNCTION IF EXISTS public.record_listing_view(uuid, uuid, date, text, text, uuid);
DROP FUNCTION IF EXISTS public.record_listing_view(uuid, uuid, date, text);
"""
    rehearsal_fn = """
CREATE OR REPLACE FUNCTION public.record_listing_view(
  p_session_id uuid,
  p_listing_id uuid,
  p_day date,
  p_view_kind text,
  p_surface text,
  p_viewer_user_id uuid DEFAULT NULL::uuid
)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions
AS $$
BEGIN
  RETURN 0;
END;
$$;
"""
    assert db.run(drop_existing).ok, db.run(drop_existing).error
    assert db.run(rehearsal_fn).ok, db.run(rehearsal_fn).error

    before = db.run(
        "SELECT pg_get_function_arguments(p.oid) "
        "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'public' AND p.proname = 'record_listing_view';"
    )
    assert before.ok and before.rows
    assert "p_surface text," in before.rows[0] or "p_surface text " in before.rows[0]
    assert "p_surface text default" not in before.rows[0].lower()

    for filename in CANONICAL_MIGRATIONS:
        path = REPO_ROOT / "supabase" / "migrations" / filename
        assert db.run_file(path).ok, db.run_file(path).error

    after = db.run(
        "SELECT pg_get_function_arguments(p.oid) "
        "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'public' AND p.proname = 'record_listing_view';"
    )
    assert after.ok and after.rows
    lowered = after.rows[0].lower()
    assert "p_surface text default 'unknown'" in lowered
    assert "p_viewer_user_id uuid default null" in lowered


def test_record_listing_view_four_arg_rpc_succeeds(db: PgConn) -> None:
    """API boundary uses four positional args; PostgreSQL defaults must satisfy the call."""
    signature = db.run(
        "SELECT pg_get_function_arguments(p.oid) "
        "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'public' AND p.proname = 'record_listing_view';"
    )
    assert signature.ok and signature.rows
    lowered = signature.rows[0].lower()
    assert "p_surface text default 'unknown'" in lowered

    prepare = db.run(
        """
PREPARE record_listing_view_four_arg AS
  SELECT public.record_listing_view($1::uuid, $2::uuid, $3::date, $4::text);
"""
    )
    assert prepare.ok, prepare.error
    dealloc = db.run("DEALLOCATE record_listing_view_four_arg;")
    assert dealloc.ok, dealloc.error
