"""guard_rate_counters_mutation() authorization (20260831050000).

After 20260829120000 fixed bump_rate_counter()'s own outer service-role
check, live staging inspection still showed GET /discovery/home returning
HTTP 500 — now traced to a *different* HTTP 400: "rate_counters is
service-role only". The request cleared bump_rate_counter()'s own check but
then failed inside its INSERT/UPDATE against public.rate_counters, which
fires the BEFORE trigger rate_counters_guard_mutation. That trigger function
still read the legacy flattened `request.jwt.claim.role` GUC — the exact
split-brain defect 20260829120000 fixed in bump_rate_counter() itself, left
behind in this sibling guard.

These tests exercise the trigger directly via raw INSERT/UPDATE/DELETE on
public.rate_counters (not routed through bump_rate_counter), plus one
explicit end-to-end test proving bump_rate_counter's underlying row mutation
actually lands — so this exact split-brain defect (outer check fixed, inner
trigger left stale) cannot recur silently. Skips when Postgres is
unreachable or migrations cannot apply — CI's Python job has no DB service
and correctly skips; a real Supabase-shaped Postgres run is authoritative.

Two mechanics worth flagging, both discovered while writing this file
against a real local Postgres:

1. Role impersonation MUST run `SET LOCAL role ...` and the probed statement
   in the SAME connection/transaction for `SET LOCAL` to have any effect —
   issuing them as two separate PgConn.run() calls (each its own psql
   subprocess/connection) silently no-ops the role switch, leaving every
   probe running as whichever role the DSN itself connects as.
   `_run_as_role` below uses PgConn.run_script() (one psql invocation,
   stdin-fed) specifically to avoid that trap.

2. anon/authenticated have no GRANTs at all on public.rate_counters (0011
   grants INSERT/UPDATE/DELETE/SELECT to service_role only) — so a genuine
   role switch to anon/authenticated is rejected by Postgres's own
   table-privilege check ("permission denied for table rate_counters")
   *before* the trigger ever runs; "rate_counters is service-role only" is
   only reachable by a caller that already has table privilege (service_role
   or a trusted session) but fails the trigger's own role/claims check —
   exactly the historical bug's shape. Both are proven below: the table
   grant as the primary defense, the trigger as the isolated
   defense-in-depth check.
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


def _insert_sql(key: str) -> str:
    return (
        "INSERT INTO public.rate_counters (scope, key, window_start, count, expires_at) "
        f"VALUES ('{SCOPE}', '{key}', now(), 1, now() + interval '1 hour');"
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


def _seed_row(conn: PgConn, key: str) -> None:
    result = _run_as_role(
        conn, "service_role", '{"role":"service_role"}', _insert_sql(key), commit=True
    )
    assert result.ok, result.error


def _delete_row(conn: PgConn, key: str) -> None:
    _run_as_role(
        conn,
        "service_role",
        '{"role":"service_role"}',
        f"DELETE FROM public.rate_counters WHERE scope = '{SCOPE}' AND key = '{key}';",
        commit=True,
    )


class TestGuardRateCountersMutationAuthRole:
    def test_service_role_insert_allowed(self, db: PgConn) -> None:
        result = _run_as_role(
            db, "service_role", '{"role":"service_role"}', _insert_sql("trigger-svc-insert-1")
        )
        assert result.ok, result.error
        assert result.rows == ["INSERT 0 1"]

    def test_postgres_trusted_session_insert_allowed(self, db: PgConn) -> None:
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
        db.run("BEGIN;")
        try:
            result = db.run(_insert_sql("trigger-trusted-insert-1"))
            assert result.ok, result.error
        finally:
            db.run("ROLLBACK;")

    def test_anon_insert_rejected(self, db: PgConn) -> None:
        result = _run_as_role(db, "anon", None, _insert_sql("trigger-anon-insert-1"))
        assert not result.ok
        assert "permission denied for table rate_counters" in (result.error or "")

    def test_authenticated_insert_rejected(self, db: PgConn) -> None:
        result = _run_as_role(
            db,
            "authenticated",
            '{"role":"authenticated","sub":"11111111-1111-1111-1111-111111111111"}',
            _insert_sql("trigger-authenticated-insert-1"),
        )
        assert not result.ok
        assert "permission denied for table rate_counters" in (result.error or "")

    def test_service_role_without_matching_claims_rejected_by_trigger(self, db: PgConn) -> None:
        """Isolates the trigger's OWN check from the table-grant check: a
        caller holding the service_role DB role (so it clears table
        privileges) but whose JWT claims do not assert 'service_role' must
        still be rejected by guard_rate_counters_mutation() itself — this is
        the exact shape of the historical defect (a genuine service_role
        session whose claims the old GUC check could not see)."""
        result = _run_as_role(
            db,
            "service_role",
            '{"role":"authenticated"}',
            _insert_sql("trigger-svc-badclaims-insert-1"),
        )
        assert not result.ok
        assert "rate_counters is service-role only" in (result.error or "")

    def test_service_role_update_allowed(self, db: PgConn) -> None:
        key = "trigger-svc-update-1"
        _seed_row(db, key)
        try:
            result = _run_as_role(
                db,
                "service_role",
                '{"role":"service_role"}',
                f"UPDATE public.rate_counters SET count = count + 1 "
                f"WHERE scope = '{SCOPE}' AND key = '{key}';",
            )
            assert result.ok, result.error
            assert result.rows == ["UPDATE 1"]
        finally:
            _delete_row(db, key)

    def test_anon_update_rejected(self, db: PgConn) -> None:
        key = "trigger-anon-update-1"
        _seed_row(db, key)
        try:
            result = _run_as_role(
                db,
                "anon",
                None,
                f"UPDATE public.rate_counters SET count = count + 1 "
                f"WHERE scope = '{SCOPE}' AND key = '{key}';",
            )
            assert not result.ok
            assert "permission denied for table rate_counters" in (result.error or "")
        finally:
            _delete_row(db, key)

    def test_anon_delete_rejected(self, db: PgConn) -> None:
        key = "trigger-anon-delete-1"
        _seed_row(db, key)
        try:
            result = _run_as_role(
                db,
                "anon",
                None,
                f"DELETE FROM public.rate_counters WHERE scope = '{SCOPE}' AND key = '{key}';",
            )
            assert not result.ok
            assert "permission denied for table rate_counters" in (result.error or "")
        finally:
            _delete_row(db, key)

    def test_bump_rate_counter_end_to_end_row_actually_lands(self, db: PgConn) -> None:
        """Proves BOTH layers together: bump_rate_counter()'s own service-role
        check AND guard_rate_counters_mutation()'s trigger check must both
        allow a service-role call for the underlying row to actually exist —
        this is the exact split-brain scenario (one layer fixed, the other
        still stale) that let GET /discovery/home 500 twice in a row."""
        key = "trigger-e2e-bump-1"
        try:
            result = _run_as_role(
                db,
                "service_role",
                '{"role":"service_role"}',
                "SELECT allowed, retry_after_seconds FROM public.bump_rate_counter("
                f"'{SCOPE}', '{key}', interval '1 hour', 1000);",
                commit=True,
            )
            assert result.ok, result.error
            assert result.rows and result.rows[0].startswith("t")

            row = db.run(
                f"SELECT count FROM public.rate_counters WHERE scope = '{SCOPE}' AND key = '{key}';"
            )
            assert row.ok, row.error
            assert row.rows == ["1"]
        finally:
            _delete_row(db, key)
