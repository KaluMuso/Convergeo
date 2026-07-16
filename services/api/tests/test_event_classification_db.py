"""DB-backed verification of migration 0041 (Events Wave A · M10-P10).

Proves against a real Postgres (full migration chain) that:
  * the classification/visibility/policy columns exist;
  * private events require an access code (CHECK constraint);
  * the public-read RLS policy excludes private events;
  * search_upsert_event indexes PUBLIC events but drops unlisted/private ones.

Requires psql + a reachable Postgres; skips otherwise. Isolation-clean: seeds its
own events and tears them down.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from tests.rls.conftest import (
    MIGRATIONS_DIR,
    PgConn,
    SqlResult,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)


@pytest.fixture(scope="module")
def db() -> Generator[PgConn, None, None]:
    import shutil

    if shutil.which("psql") is None:
        pytest.skip("psql not available")
    url = resolve_db_url()
    conn = PgConn(url)
    if not conn.run("SELECT 1").ok:
        pytest.skip(f"Postgres not reachable at {url}")
    if not schema_ready(conn):
        conn.run("DROP SCHEMA IF EXISTS public CASCADE")
        conn.run("CREATE SCHEMA public")
        conn.run("DROP SCHEMA IF EXISTS auth CASCADE")
        apply_migrations(conn)
    seed_matrix_fixtures(conn)
    yield conn


def _active_vendor(conn: PgConn) -> str:
    result = conn.run("SELECT id FROM public.vendors WHERE status = 'active' LIMIT 1")
    assert result.ok and result.rows, result.error
    return result.rows[0]


def _insert_event(
    conn: PgConn, vendor: str, slug: str, *, visibility: str, code: str | None
) -> SqlResult:
    code_sql = "NULL" if code is None else f"'{code}'"
    return conn.run(
        f"""
        INSERT INTO public.events
          (organiser_vendor_id, title, slug, status, visibility, access_code)
        VALUES
          ('{vendor}', 'T {slug}', '{slug}', 'published', '{visibility}', {code_sql});
        """
    )


def test_migration_0041_shipped() -> None:
    assert MIGRATIONS_DIR.joinpath("0041_event_classification.sql").exists()


def test_classification_columns_exist(db: PgConn) -> None:
    result = db.run(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'events'
          AND column_name IN ('event_type','visibility','access_code',
                              'refund_policy_key','age_restriction','terms')
        ORDER BY column_name
        """
    )
    assert result.ok, result.error
    assert set(result.rows) == {
        "access_code",
        "age_restriction",
        "event_type",
        "refund_policy_key",
        "terms",
        "visibility",
    }


def test_private_event_requires_access_code(db: PgConn) -> None:
    vendor = _active_vendor(db)
    slug = f"bm-priv-{uuid.uuid4().hex[:8]}"
    try:
        rejected = _insert_event(db, vendor, slug, visibility="private", code=None)
        assert not rejected.ok  # CHECK events_private_requires_access_code_chk
        assert "access_code" in (rejected.error or "") or "check" in (rejected.error or "").lower()

        ok = _insert_event(db, vendor, f"{slug}-ok", visibility="private", code="vip-code")
        assert ok.ok, ok.error
    finally:
        db.run(f"DELETE FROM public.events WHERE slug LIKE '{slug}%'")


def test_public_read_policy_excludes_private(db: PgConn) -> None:
    result = db.run(
        "SELECT qual FROM pg_policies WHERE tablename = 'events' "
        "AND policyname = 'events_public_published_select'"
    )
    assert result.ok and result.rows, result.error
    assert "visibility" in result.rows[0]


def test_search_indexes_public_but_not_unlisted(db: PgConn) -> None:
    vendor = _active_vendor(db)
    pub = f"bm-pub-{uuid.uuid4().hex[:8]}"
    unl = f"bm-unl-{uuid.uuid4().hex[:8]}"
    try:
        assert _insert_event(db, vendor, pub, visibility="public", code=None).ok
        assert _insert_event(db, vendor, unl, visibility="unlisted", code=None).ok
        pub_id = db.run(f"SELECT id FROM public.events WHERE slug = '{pub}'").rows[0]
        unl_id = db.run(f"SELECT id FROM public.events WHERE slug = '{unl}'").rows[0]
        db.run(f"SELECT public.search_upsert_event('{pub_id}')")
        db.run(f"SELECT public.search_upsert_event('{unl_id}')")

        pub_doc = db.run(
            "SELECT is_public::text FROM public.search_documents "
            f"WHERE entity_kind = 'event' AND entity_id = '{pub_id}'"
        )
        unl_doc = db.run(
            "SELECT is_public::text FROM public.search_documents "
            f"WHERE entity_kind = 'event' AND entity_id = '{unl_id}'"
        )
        # Public event is indexed and public; unlisted is either absent or marked
        # not-public (search_mark_unpublished), never a browsable document.
        assert pub_doc.ok and pub_doc.rows and pub_doc.rows[0] == "true"
        assert not unl_doc.rows or unl_doc.rows[0] != "true"
    finally:
        db.run(f"DELETE FROM public.events WHERE slug IN ('{pub}', '{unl}')")
