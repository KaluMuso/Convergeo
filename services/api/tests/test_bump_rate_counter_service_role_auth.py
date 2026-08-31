"""bump_rate_counter authorization (20260829120000).

Run #55's aftermath proved GET /discovery/home failing because
bump_rate_counter's service-role check read the legacy flattened
`request.jwt.claim.role` GUC, which the current hosted platform no longer
populates — rejecting even a genuine service_role caller. These tests
exercise the real SQL function's authorization branch directly (not a
mocked Supabase client), the same way test_vendor_lifecycle_guards.py
proves its guard triggers. Skips when Postgres is unreachable or
migrations cannot apply — CI with the full Supabase stack exercises them.

Role impersonation MUST run `SET LOCAL role ...` and the probed statement in
the SAME connection/transaction for `SET LOCAL` to have any effect at all —
issuing them as two separate PgConn.run() calls (each its own psql
subprocess/connection) silently no-ops the role switch, leaving every probe
running as whichever role the DSN itself connects as. `_run_as_role` below
uses PgConn.run_script() (one psql invocation, stdin-fed) specifically to
avoid that trap; verified against a real local Postgres that this genuinely
changes current_user/auth.role() while session_user (the trusted-session
bypass) correctly stays fixed to the connecting role throughout.

anon/authenticated have no EXECUTE grant on bump_rate_counter at all (this
migration revokes all and grants only to service_role) — a genuine role
switch to anon/authenticated is rejected by Postgres's own function-privilege
check ("permission denied for function bump_rate_counter") before the
function body's own service-role check ever runs; that internal check is
only reachable by a caller holding the service_role DB role (so it clears
the EXECUTE grant) whose claims don't actually assert service_role —
test_service_role_without_matching_claims_rejected isolates exactly that.
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


def _bump_sql(key: str, limit: int = 1000) -> str:
    return (
        "SELECT allowed, retry_after_seconds FROM public.bump_rate_counter("
        f"'{SCOPE}', '{key}', interval '1 hour', {limit});"
    )


def _claims_do_block(claims_json: str | None) -> str:
    if claims_json is None:
        return "DO $$ BEGIN PERFORM set_config('request.jwt.claims', '', true); END $$;"
    escaped = claims_json.replace("'", "''")
    return f"DO $$ BEGIN PERFORM set_config('request.jwt.claims', '{escaped}', true); END $$;"


def _run_as_role(
    conn: PgConn, role: str, claims_json: str | None, sql: str, *, commit: bool = False
) -> SqlResult:
    """Runs `sql` impersonating `role`, all in ONE connection/transaction so
    SET LOCAL and the transaction-local claims GUC actually apply to it."""
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


class TestBumpRateCounterServiceRoleAuth:
    def test_service_role_allowed(self, db: PgConn) -> None:
        result = _run_as_role(
            db, "service_role", '{"role":"service_role"}', _bump_sql("svc-allow-1")
        )
        assert result.ok, result.error
        assert result.rows and result.rows[0].startswith("t")

    def test_postgres_trusted_session_allowed(self, db: PgConn) -> None:
        # session_user can never be changed by SET ROLE (a deliberate Postgres
        # property — that immutability is exactly what makes checking
        # session_user, not current_user, a real trust boundary). This is
        # only exercisable when the resolved DSN's own connecting login role
        # is literally 'postgres'/'supabase_admin' (the real Supabase-shaped
        # Postgres CI's `rls` job connects as); a local peer-auth fallback
        # may connect as a different superuser, in which case this correctly
        # skips rather than asserting a bypass that cannot apply.
        session_user = db.run("SELECT session_user;")
        assert session_user.ok, session_user.error
        if session_user.rows[0] not in ("postgres", "supabase_admin"):
            pytest.skip(
                f"connecting session_user={session_user.rows[0]!r} is not a trusted "
                "identity in this environment — cannot exercise the bypass"
            )
        result = db.run(_bump_sql("trusted-postgres-1"))
        assert result.ok, result.error
        assert result.rows and result.rows[0].startswith("t")

    def test_anon_rejected(self, db: PgConn) -> None:
        result = _run_as_role(db, "anon", None, _bump_sql("anon-reject-1"))
        assert not result.ok
        assert "permission denied for function bump_rate_counter" in (result.error or "")

    def test_authenticated_rejected(self, db: PgConn) -> None:
        result = _run_as_role(
            db,
            "authenticated",
            '{"role":"authenticated","sub":"11111111-1111-1111-1111-111111111111"}',
            _bump_sql("authenticated-reject-1"),
        )
        assert not result.ok
        assert "permission denied for function bump_rate_counter" in (result.error or "")

    def test_service_role_without_matching_claims_rejected(self, db: PgConn) -> None:
        """Isolates the function's OWN check from the EXECUTE-grant check: a
        caller holding the service_role DB role (so it clears the EXECUTE
        grant) but whose JWT claims do not assert 'service_role' must still
        be rejected by bump_rate_counter() itself — this is the exact shape
        of the historical defect (a genuine service_role session whose
        claims the old GUC check could not see)."""
        result = _run_as_role(
            db, "service_role", '{"role":"authenticated"}', _bump_sql("svc-badclaims-1")
        )
        assert not result.ok
        assert "bump_rate_counter requires service role" in (result.error or "")

    def test_invalid_scope_rejected_even_for_service_role(self, db: PgConn) -> None:
        result = _run_as_role(
            db,
            "service_role",
            '{"role":"service_role"}',
            "SELECT allowed FROM public.bump_rate_counter("
            "'not_a_registered_scope', 'k', interval '1 hour', 10);",
        )
        assert not result.ok
        assert "invalid rate counter scope" in (result.error or "")

    def test_service_role_call_still_enforces_limit(self, db: PgConn) -> None:
        key = "svc-enforce-1"
        try:
            first = _run_as_role(
                db,
                "service_role",
                '{"role":"service_role"}',
                _bump_sql(key, limit=1),
                commit=True,
            )
            assert first.ok, first.error
            assert first.rows[0].startswith("t")

            second = _run_as_role(
                db,
                "service_role",
                '{"role":"service_role"}',
                _bump_sql(key, limit=1),
                commit=True,
            )
            assert second.ok, second.error
            assert second.rows[0].startswith("f")
        finally:
            _run_as_role(
                db,
                "service_role",
                '{"role":"service_role"}',
                f"DELETE FROM public.rate_counters WHERE scope = '{SCOPE}' AND key = '{key}';",
                commit=True,
            )
