"""Convergeo Intelligence 1A-02: analytics_event_log schema, ACL and flags (live DB).

Complements the matrix row (which can only probe UPDATE as a no-op) with direct
effective-ACL assertions, plus the idempotent-ingest and default-OFF flag contract.
"""

from __future__ import annotations

from tests.rls.conftest import PgConn

TABLE = "public.analytics_event_log"
EVENT_ID = "e1e1e1e1-e1e1-4e1e-8e1e-e1e1e1e1e1e1"


def _one(db: PgConn, sql: str) -> str:
    result = db.run(sql)
    assert result.ok, result.error
    assert result.rows, sql
    return result.rows[0]


def test_no_client_role_has_any_privilege(db: PgConn) -> None:
    for role in ("anon", "authenticated"):
        for verb in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            got = _one(db, f"SELECT has_table_privilege('{role}', '{TABLE}', '{verb}')::text")
            assert got == "false", f"{role} has {verb} on {TABLE}"


def test_rls_enabled_and_forced(db: PgConn) -> None:
    got = _one(
        db,
        "SELECT relrowsecurity::text || ',' || relforcerowsecurity::text "
        "FROM pg_class WHERE oid = 'public.analytics_event_log'::regclass",
    )
    assert got == "true,true"


def test_only_pk_and_brin_indexes(db: PgConn) -> None:
    result = db.run(
        "SELECT indexname FROM pg_indexes "
        "WHERE schemaname = 'public' AND tablename = 'analytics_event_log' ORDER BY 1"
    )
    assert result.ok, result.error
    assert result.rows == ["analytics_event_log_pkey", "analytics_event_log_received_at_brin"]


def test_flags_exist_and_default_off(db: PgConn) -> None:
    result = db.run(
        "SELECT flag || '=' || enabled::text FROM public.feature_flags "
        "WHERE flag LIKE 'analytics_v2_%' ORDER BY flag"
    )
    assert result.ok, result.error
    assert result.rows == ["analytics_v2_collect=false", "analytics_v2_rollups=false"]


def test_event_id_conflict_is_idempotent_and_constraints_hold(db: PgConn) -> None:
    insert = (
        f"INSERT INTO {TABLE} (event_id, event_name, source_app, page_key, props) "
        f"VALUES ('{EVENT_ID}', 'page_view', 'customer', 'pdp', '{{}}'::jsonb) "
        "ON CONFLICT (event_id) DO NOTHING"
    )
    count = f"SELECT 'n=' || count(*)::text FROM {TABLE} WHERE event_id = '{EVENT_ID}'"
    result = db.run_script(f"BEGIN;\n{insert};\n{insert};\n{count};\nROLLBACK;\n")
    assert result.ok, result.error
    assert "n=1" in result.rows

    bad_rows = (
        "(gen_random_uuid(), 'Bad-Name', 'customer', 'pdp')",
        "(gen_random_uuid(), 'page_view', 'browser', 'pdp')",
        "(gen_random_uuid(), 'page_view', 'customer', '/en/p/slug')",
    )
    for values in bad_rows:
        res = db.run_script(
            "BEGIN;\n"
            f"INSERT INTO {TABLE} (event_id, event_name, source_app, page_key) VALUES {values};\n"
            "ROLLBACK;\n"
        )
        assert not res.ok, values
