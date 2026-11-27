"""Vendor payout columns and dispute/return client inserts are locked (20261128000000).

Skips when Postgres is unreachable or migrations cannot apply; CI's DB jobs are
authoritative. A static check of the migration text always runs.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from tests.rls.conftest import (
    PgConn,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)

MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "supabase/migrations/20261128000000_lock_vendor_payout_columns_and_client_inserts.sql"
)
VENDOR_OWNER_ID = "33333333-3333-3333-3333-333333333333"
LOCKED_COLUMNS = (
    "payout_msisdn",
    "payout_rail",
    "payout_hold_until",
    "commercial_tier",
    "caps_snapshot",
    "owner_user_id",
)


def test_migration_text_locks_columns_and_drops_insert_policies() -> None:
    sql = MIGRATION.read_text()
    for column in LOCKED_COLUMNS:
        assert f"new.{column} is distinct from old.{column}" in sql
    assert "drop policy if exists disputes_opener_insert on public.disputes" in sql
    assert "drop policy if exists returns_customer_insert on public.returns" in sql
    assert "revoke insert on table public.disputes from anon, authenticated" in sql
    assert "revoke insert on table public.returns from anon, authenticated" in sql
    assert "REVERSAL" in sql


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


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("payout_msisdn", "'260971234567'"),
        ("payout_rail", "'mtn'"),
        ("payout_hold_until", "now() + interval '1 day'"),
        ("commercial_tier", "'pro'"),
        ("caps_snapshot", "'{\"x\": 1}'::jsonb"),
        ("owner_user_id", "'11111111-1111-1111-1111-111111111111'"),
    ],
)
def test_owner_cannot_patch_locked_vendor_column(db: PgConn, column: str, value: str) -> None:
    row = db.run(
        f"SELECT id::text FROM public.vendors WHERE owner_user_id = '{VENDOR_OWNER_ID}' LIMIT 1;"
    )
    if not row.ok or not row.rows:
        pytest.skip("seed has no vendor-owned storefront")
    result = db.run_as(
        "authenticated",
        f"UPDATE public.vendors SET {column} = {value} WHERE id = '{row.rows[0]}';",
        user_id=VENDOR_OWNER_ID,
    )
    assert not result.ok
    assert "server-controlled" in (result.error or "")


def test_dispute_and_return_insert_policies_and_grants_are_gone(db: PgConn) -> None:
    policies = db.run(
        "SELECT policyname FROM pg_policies WHERE schemaname = 'public' "
        "AND policyname IN ('disputes_opener_insert', 'returns_customer_insert');"
    )
    assert policies.ok, policies.error
    assert policies.rows == []
    for table in ("disputes", "returns"):
        for role in ("anon", "authenticated"):
            grant = db.run(f"SELECT has_table_privilege('{role}', 'public.{table}', 'INSERT');")
            assert grant.ok, grant.error
            assert grant.rows == ["f"], f"{role} still has INSERT on {table}"
        service = db.run(f"SELECT has_table_privilege('service_role', 'public.{table}', 'INSERT');")
        assert service.rows == ["t"]
