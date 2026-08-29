"""bump_rate_counter authorization (20260829120000).

Run #55's aftermath proved GET /discovery/home failing because
bump_rate_counter's service-role check read the legacy flattened
`request.jwt.claim.role` GUC, which the current hosted platform no longer
populates — rejecting even a genuine service_role caller. These tests
exercise the real SQL function's authorization branch directly (not a
mocked Supabase client), the same way test_vendor_lifecycle_guards.py
proves its guard triggers. Skips when Postgres is unreachable or
migrations cannot apply — CI with the full Supabase stack exercises them.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from tests.rls.conftest import PgConn, apply_migrations, resolve_db_url, schema_ready

SCOPE = "otp_number"


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
    yield conn


def _bump_sql(key: str, limit: int = 1000) -> str:
    return (
        "SELECT allowed, retry_after_seconds FROM public.bump_rate_counter("
        f"'{SCOPE}', '{key}', interval '1 hour', {limit});"
    )


def _as_role(conn: PgConn, role: str, claims_json: str | None) -> None:
    conn.run("BEGIN;")
    conn.run(f"SET LOCAL role {role};")
    if claims_json is not None:
        escaped = claims_json.replace("'", "''")
        conn.run(
            f"DO $$ BEGIN PERFORM set_config('request.jwt.claims', '{escaped}', true); END $$;"
        )
    else:
        conn.run("DO $$ BEGIN PERFORM set_config('request.jwt.claims', '', true); END $$;")


def _rollback(conn: PgConn) -> None:
    conn.run("ROLLBACK;")


class TestBumpRateCounterServiceRoleAuth:
    def test_service_role_allowed(self, db: PgConn) -> None:
        _as_role(db, "service_role", '{"role":"service_role"}')
        try:
            result = db.run(_bump_sql("svc-allow-1"))
            assert result.ok, result.error
            assert result.rows and result.rows[0].startswith("t")
        finally:
            _rollback(db)

    def test_postgres_trusted_session_allowed(self, db: PgConn) -> None:
        # The module-scoped `db` connection is itself the trusted postgres
        # session (resolve_db_url()'s default) — no role switch needed.
        result = db.run(_bump_sql("trusted-postgres-1"))
        assert result.ok, result.error
        assert result.rows and result.rows[0].startswith("t")

    def test_anon_rejected(self, db: PgConn) -> None:
        _as_role(db, "anon", None)
        try:
            result = db.run(_bump_sql("anon-reject-1"))
            assert not result.ok
            assert "requires service role" in (result.error or "")
        finally:
            _rollback(db)

    def test_authenticated_rejected(self, db: PgConn) -> None:
        _as_role(
            db,
            "authenticated",
            '{"role":"authenticated","sub":"11111111-1111-1111-1111-111111111111"}',
        )
        try:
            result = db.run(_bump_sql("authenticated-reject-1"))
            assert not result.ok
            assert "requires service role" in (result.error or "")
        finally:
            _rollback(db)

    def test_invalid_scope_rejected_even_for_service_role(self, db: PgConn) -> None:
        _as_role(db, "service_role", '{"role":"service_role"}')
        try:
            result = db.run(
                "SELECT allowed FROM public.bump_rate_counter("
                "'not_a_registered_scope', 'k', interval '1 hour', 10);"
            )
            assert not result.ok
            assert "invalid rate counter scope" in (result.error or "")
        finally:
            _rollback(db)

    def test_service_role_call_still_enforces_limit(self, db: PgConn) -> None:
        _as_role(db, "service_role", '{"role":"service_role"}')
        try:
            key = "svc-enforce-1"
            first = db.run(_bump_sql(key, limit=1))
            assert first.ok, first.error
            assert first.rows[0].startswith("t")

            second = db.run(_bump_sql(key, limit=1))
            assert second.ok, second.error
            assert second.rows[0].startswith("f")
        finally:
            _rollback(db)
