"""cleanup_expired_rate_counters() authorization (20260831051000).

Same split-brain defect class as 20260829120000 (bump_rate_counter) and
20260831050000 (guard_rate_counters_mutation): this function's service-role
check still read the legacy flattened `request.jwt.claim.role` GUC, which
the current hosted platform no longer populates. Not proven live-broken via
a direct HTTP call (never invoked destructively against hosted staging), but
it is the identical pattern in the same migration file — left unfixed it
would fail the same way the moment the scheduled n8n/cron cleanup this
function's own comment describes actually calls it.

Role impersonation runs SET LOCAL role and the probed statement in ONE
connection/transaction (PgConn.run_script) — see
test_guard_rate_counters_mutation_auth_role.py's module docstring for why
that matters (two separate psql invocations = two connections = the role
switch silently never applies).
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from tests.rls.conftest import PgConn, SqlResult, apply_migrations, resolve_db_url, schema_ready

SCOPE = "otp_number"

_NOISE_LINES = {"BEGIN", "SET", "DO", "COMMIT", "ROLLBACK"}


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


def _claims_do_block(claims_json: str | None) -> str:
    if claims_json is None:
        return "DO $$ BEGIN PERFORM set_config('request.jwt.claims', '', true); END $$;"
    escaped = claims_json.replace("'", "''")
    return f"DO $$ BEGIN PERFORM set_config('request.jwt.claims', '{escaped}', true); END $$;"


def _run_as_role(
    conn: PgConn, role: str, claims_json: str | None, sql: str, *, commit: bool = False
) -> SqlResult:
    script = "\n".join(
        [
            "BEGIN;",
            f"SET LOCAL role {role};",
            _claims_do_block(claims_json),
            sql,
            "COMMIT;" if commit else "ROLLBACK;",
        ]
    )
    result = conn.run_script(script)
    if not result.ok:
        return result
    data = [row for row in result.rows if row not in _NOISE_LINES]
    return SqlResult(ok=True, rows=data, error=None, sqlstate=None)


def _seed_row(conn: PgConn, key: str, *, expires_offset: str) -> None:
    sql = (
        "INSERT INTO public.rate_counters (scope, key, window_start, count, expires_at) "
        f"VALUES ('{SCOPE}', '{key}', now(), 1, now() {expires_offset});"
    )
    result = _run_as_role(conn, "service_role", '{"role":"service_role"}', sql, commit=True)
    assert result.ok, result.error


def _delete_row(conn: PgConn, key: str) -> None:
    _run_as_role(
        conn,
        "service_role",
        '{"role":"service_role"}',
        f"DELETE FROM public.rate_counters WHERE scope = '{SCOPE}' AND key = '{key}';",
        commit=True,
    )


def _row_exists(conn: PgConn, key: str) -> bool:
    result = conn.run(
        "SELECT count(*)::text FROM public.rate_counters "
        f"WHERE scope = '{SCOPE}' AND key = '{key}';"
    )
    assert result.ok, result.error
    return result.rows == ["1"]


class TestCleanupExpiredRateCountersAuthRole:
    def test_service_role_cleanup_allowed(self, db: PgConn) -> None:
        result = _run_as_role(
            db,
            "service_role",
            '{"role":"service_role"}',
            "SELECT public.cleanup_expired_rate_counters()::text;",
        )
        assert result.ok, result.error

    def test_postgres_trusted_session_cleanup_allowed(self, db: PgConn) -> None:
        # session_user can never be changed by SET ROLE — see sibling test
        # files' identical note. Only exercisable when the resolved DSN's
        # own connecting login role is literally 'postgres'/'supabase_admin'
        # (the real Supabase-shaped Postgres CI's `rls` job connects as);
        # a local peer-auth fallback may connect as a different superuser,
        # in which case this correctly skips.
        session_user = db.run("SELECT session_user;")
        assert session_user.ok, session_user.error
        if session_user.rows[0] not in ("postgres", "supabase_admin"):
            pytest.skip(
                f"connecting session_user={session_user.rows[0]!r} is not a trusted "
                "identity in this environment — cannot exercise the bypass"
            )
        db.run("BEGIN;")
        try:
            result = db.run("SELECT public.cleanup_expired_rate_counters()::text;")
            assert result.ok, result.error
        finally:
            db.run("ROLLBACK;")

    def test_anon_cleanup_rejected(self, db: PgConn) -> None:
        # 0050_revoke_definer_execute_from_public.sql already revokes EXECUTE
        # on this function from anon/authenticated — the function's own
        # service-role check is defense-in-depth, reached only by a caller
        # that already holds EXECUTE (service_role) but whose claims don't
        # assert it (see test_service_role_without_matching_claims_rejected
        # below, which isolates that branch specifically).
        result = _run_as_role(
            db, "anon", None, "SELECT public.cleanup_expired_rate_counters()::text;"
        )
        assert not result.ok
        assert "permission denied for function cleanup_expired_rate_counters" in (
            result.error or ""
        )

    def test_authenticated_cleanup_rejected(self, db: PgConn) -> None:
        result = _run_as_role(
            db,
            "authenticated",
            '{"role":"authenticated","sub":"11111111-1111-1111-1111-111111111111"}',
            "SELECT public.cleanup_expired_rate_counters()::text;",
        )
        assert not result.ok
        assert "permission denied for function cleanup_expired_rate_counters" in (
            result.error or ""
        )

    def test_service_role_without_matching_claims_rejected(self, db: PgConn) -> None:
        """Isolates the function's OWN check from the EXECUTE-grant check: a
        caller holding the service_role DB role (so it clears EXECUTE) but
        whose JWT claims do not assert 'service_role' must still be rejected
        by cleanup_expired_rate_counters() itself."""
        result = _run_as_role(
            db,
            "service_role",
            '{"role":"authenticated"}',
            "SELECT public.cleanup_expired_rate_counters()::text;",
        )
        assert not result.ok
        assert "requires service role" in (result.error or "")

    def test_expired_rows_deleted_non_expired_rows_retained_count_correct(
        self, db: PgConn
    ) -> None:
        expired_key = "cleanup-expired-1"
        active_key = "cleanup-active-1"
        _seed_row(db, expired_key, expires_offset="- interval '1 hour'")
        _seed_row(db, active_key, expires_offset="+ interval '1 hour'")
        try:
            before_count = db.run(
                "SELECT count(*)::text FROM public.rate_counters WHERE expires_at < now();"
            )
            assert before_count.ok, before_count.error
            baseline = int(before_count.rows[0])

            result = _run_as_role(
                db,
                "service_role",
                '{"role":"service_role"}',
                "SELECT public.cleanup_expired_rate_counters()::text;",
                commit=True,
            )
            assert result.ok, result.error
            assert result.rows == [str(baseline)]

            assert not _row_exists(db, expired_key), "expired row must be deleted"
            assert _row_exists(db, active_key), "non-expired row must be retained"
        finally:
            _delete_row(db, active_key)
            _delete_row(db, expired_key)
