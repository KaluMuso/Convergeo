"""Ask Vergeo service-role checks use auth.role() (20261126190000).

Production showed every POST /ask falling back because
reserve_ask_quota_daily rejected the genuine service-role key: it read the
legacy flattened GUC request.jwt.claim.role, which hosted Supabase no longer
sets. After all migrations apply, none of the Ask functions may still read
that GUC. Skips when Postgres is unreachable (CI's DB jobs are authoritative).
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from tests.rls.conftest import PgConn, apply_migrations, resolve_db_url, schema_ready

ASK_FUNCTIONS = (
    "ask_quota_status",
    "reserve_ask_quota",
    "reserve_ask_quota_daily",
    "finalize_ask_answer",
    "release_ask_reservation",
    "reset_ask_kill_switch",
    "guard_ask_usage_mutation",
    "guard_ask_spend_monthly_mutation",
)


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


@pytest.mark.parametrize("name", ASK_FUNCTIONS)
def test_ask_function_uses_auth_role_not_legacy_guc(db: PgConn, name: str) -> None:
    result = db.run(
        "SELECT prosrc FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        f"WHERE n.nspname = 'public' AND p.proname = '{name}';"
    )
    assert result.ok, result.error
    body = "\n".join(result.rows)
    assert body.strip(), f"{name} missing"
    assert "current_setting('request.jwt.claim.role'" not in body
    assert "auth.role()" in body
