"""Convergeo Intelligence 1A-08: analytics_session_links ACL, idempotent link, purge (live DB)."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from app.services.analytics.session_links import link_session, purge_expired_links
from app.services.db import reset_pools
from tests.rls.conftest import PgConn

TABLE = "public.analytics_session_links"
SESSION = "c8c8c8c8-c8c8-4c8c-8c8c-c8c8c8c8c8c8"
OLD_SESSION = "c9c9c9c9-c9c9-4c9c-8c9c-c9c9c9c9c9c9"


def _one(db: PgConn, sql: str) -> str:
    result = db.run(sql)
    assert result.ok, result.error
    assert result.rows, sql
    return result.rows[0]


def _cleanup(db: PgConn) -> None:
    db.run(f"DELETE FROM {TABLE} WHERE session_id IN ('{SESSION}', '{OLD_SESSION}')")


@pytest.fixture
def live(db: PgConn, monkeypatch: pytest.MonkeyPatch) -> Generator[PgConn, None, None]:
    monkeypatch.setenv("SUPABASE_DB_URL", db.dsn)
    _cleanup(db)
    yield db
    _cleanup(db)
    reset_pools()


def test_no_client_role_has_any_privilege_and_rls_is_forced(db: PgConn) -> None:
    for role in ("anon", "authenticated"):
        for verb in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            got = _one(db, f"SELECT has_table_privilege('{role}', '{TABLE}', '{verb}')::text")
            assert got == "false", f"{role} has {verb} on {TABLE}"
    assert (
        _one(
            db,
            "SELECT relrowsecurity::text || ',' || relforcerowsecurity::text "
            f"FROM pg_class WHERE oid = '{TABLE}'::regclass",
        )
        == "true,true"
    )


def test_link_is_idempotent_first_claim_wins_and_purges_at_30_days(live: PgConn) -> None:
    users = live.run("SELECT id::text FROM auth.users ORDER BY id LIMIT 2")
    assert users.ok and len(users.rows) == 2, "needs two seeded auth.users"
    first, second = users.rows

    assert link_session(user_id=first, session_id=SESSION) is True
    assert link_session(user_id=first, session_id=SESSION) is True
    assert link_session(user_id=second, session_id=SESSION) is False
    assert _one(live, f"SELECT count(*)::text FROM {TABLE} WHERE session_id = '{SESSION}'") == "1"
    assert _one(live, f"SELECT user_id::text FROM {TABLE} WHERE session_id = '{SESSION}'") == first

    assert live.run(
        f"INSERT INTO {TABLE} (session_id, user_id, linked_at) "
        f"VALUES ('{OLD_SESSION}', '{first}', now() - interval '31 days')"
    ).ok
    deleted, complete = purge_expired_links()
    assert complete and deleted >= 1
    assert (
        _one(live, f"SELECT count(*)::text FROM {TABLE} WHERE session_id = '{OLD_SESSION}'") == "0"
    )
    assert _one(live, f"SELECT count(*)::text FROM {TABLE} WHERE session_id = '{SESSION}'") == "1"
