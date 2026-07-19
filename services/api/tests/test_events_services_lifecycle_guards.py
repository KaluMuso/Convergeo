"""Clients must not self-publish events or self-activate services (0058).

Mirrors test_vendor_lifecycle_guards.py. These are TRUST-critical RLS trigger
tests. They skip when Postgres is unreachable or migrations cannot apply
(e.g. missing pgvector in a bare local Postgres). CI with the full Supabase
stack exercises them.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from tests.rls.conftest import (
    PgConn,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)

VENDOR_OWNER_ID = "33333333-3333-3333-3333-333333333333"
OTHER_VENDOR_OWNER_ID = "44444444-4444-4444-4444-444444444444"
SHOP_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SHOP_B_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
EVENT_ID = "e0000000-0000-0000-0000-000000000001"
SERVICE_ID = "f0000000-0000-0000-0000-000000000001"


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


def _as_authenticated(conn: PgConn, user_id: str) -> None:
    claims = (
        '{"role":"authenticated","sub":"'
        + user_id
        + '","aal":"aal1"}'
    ).replace("'", "''")
    conn.run("BEGIN;")
    conn.run("SET LOCAL role authenticated;")
    conn.run(
        f"DO $$ BEGIN PERFORM set_config('request.jwt.claims', '{claims}', true); END $$;"
    )


def _as_anon(conn: PgConn) -> None:
    conn.run("BEGIN;")
    conn.run("SET LOCAL role anon;")
    conn.run(
        "DO $$ BEGIN PERFORM set_config('request.jwt.claims', "
        "'{\"role\":\"anon\"}', true); END $$;"
    )


def _rollback(conn: PgConn) -> None:
    conn.run("ROLLBACK;")


class TestEventLifecycleClientGuards:
    def test_owner_cannot_insert_published_event(self, db: PgConn) -> None:
        event_id = str(uuid.uuid4())
        slug = f"evil-{event_id[:8]}"
        _as_authenticated(db, OTHER_VENDOR_OWNER_ID)
        result = db.run(
            f"""
            INSERT INTO public.events (
              id, organiser_vendor_id, title, slug, status
            ) VALUES (
              '{event_id}', '{SHOP_B_ID}', 'Evil Fest', '{slug}', 'published'
            );
            """
        )
        _rollback(db)
        assert not result.ok
        assert result.error is not None
        assert "server-controlled" in result.error

    def test_owner_can_insert_draft_event(self, db: PgConn) -> None:
        event_id = str(uuid.uuid4())
        slug = f"draft-{event_id[:8]}"
        _as_authenticated(db, OTHER_VENDOR_OWNER_ID)
        result = db.run(
            f"""
            INSERT INTO public.events (
              id, organiser_vendor_id, title, slug, status
            ) VALUES (
              '{event_id}', '{SHOP_B_ID}', 'Draft Fest', '{slug}', 'draft'
            );
            """
        )
        _rollback(db)
        if not result.ok:
            assert "server-controlled" not in (result.error or "")

    def test_owner_cannot_patch_event_to_published(self, db: PgConn) -> None:
        # Seed a draft event as service_role, then try client publish.
        draft_id = str(uuid.uuid4())
        slug = f"patch-{draft_id[:8]}"
        seed = db.run(
            f"""
            BEGIN;
            SET LOCAL role service_role;
            SET LOCAL "request.jwt.claims" = '{{"role":"service_role"}}';
            INSERT INTO public.events (
              id, organiser_vendor_id, title, slug, status
            ) VALUES (
              '{draft_id}', '{SHOP_B_ID}', 'Patch Fest', '{slug}', 'draft'
            );
            COMMIT;
            """
        )
        if not seed.ok:
            pytest.skip(f"could not seed draft event: {seed.error}")

        _as_authenticated(db, OTHER_VENDOR_OWNER_ID)
        result = db.run(
            f"UPDATE public.events SET status = 'published' WHERE id = '{draft_id}';"
        )
        _rollback(db)
        # Cleanup draft outside the rolled-back client txn.
        db.run(
            f"""
            BEGIN;
            SET LOCAL role service_role;
            SET LOCAL "request.jwt.claims" = '{{"role":"service_role"}}';
            DELETE FROM public.events WHERE id = '{draft_id}';
            COMMIT;
            """
        )
        assert not result.ok
        assert result.error is not None
        assert "server-controlled" in result.error

    def test_public_select_hides_published_when_organiser_inactive(
        self, db: PgConn
    ) -> None:
        # Suspend organiser, then anon must not see the published seed event.
        suspend = db.run(
            f"""
            BEGIN;
            SET LOCAL role service_role;
            SET LOCAL "request.jwt.claims" = '{{"role":"service_role"}}';
            UPDATE public.vendors SET status = 'suspended' WHERE id = '{SHOP_B_ID}';
            COMMIT;
            """
        )
        if not suspend.ok:
            pytest.skip(f"could not suspend organiser: {suspend.error}")

        try:
            _as_anon(db)
            result = db.run(
                f"SELECT id::text FROM public.events WHERE id = '{EVENT_ID}';"
            )
            _rollback(db)
            assert result.ok
            assert result.rows == []
        finally:
            db.run(
                f"""
                BEGIN;
                SET LOCAL role service_role;
                SET LOCAL "request.jwt.claims" = '{{"role":"service_role"}}';
                UPDATE public.vendors SET status = 'active' WHERE id = '{SHOP_B_ID}';
                COMMIT;
                """
            )


class TestServiceLifecycleClientGuards:
    def test_owner_cannot_insert_active_service(self, db: PgConn) -> None:
        service_id = str(uuid.uuid4())
        _as_authenticated(db, VENDOR_OWNER_ID)
        result = db.run(
            f"""
            INSERT INTO public.services (
              id, vendor_id, category, title, status
            ) VALUES (
              '{service_id}', '{SHOP_A_ID}', 'plumbing', 'Evil Plumber', 'active'
            );
            """
        )
        _rollback(db)
        assert not result.ok
        assert result.error is not None
        assert "server-controlled" in result.error

    def test_owner_can_insert_draft_service(self, db: PgConn) -> None:
        service_id = str(uuid.uuid4())
        _as_authenticated(db, VENDOR_OWNER_ID)
        result = db.run(
            f"""
            INSERT INTO public.services (
              id, vendor_id, category, title, status
            ) VALUES (
              '{service_id}', '{SHOP_A_ID}', 'plumbing', 'Draft Plumber', 'draft'
            );
            """
        )
        _rollback(db)
        if not result.ok:
            assert "server-controlled" not in (result.error or "")

    def test_owner_cannot_patch_service_to_active(self, db: PgConn) -> None:
        draft_id = str(uuid.uuid4())
        seed = db.run(
            f"""
            BEGIN;
            SET LOCAL role service_role;
            SET LOCAL "request.jwt.claims" = '{{"role":"service_role"}}';
            INSERT INTO public.services (
              id, vendor_id, category, title, status
            ) VALUES (
              '{draft_id}', '{SHOP_A_ID}', 'plumbing', 'Patch Plumber', 'draft'
            );
            COMMIT;
            """
        )
        if not seed.ok:
            pytest.skip(f"could not seed draft service: {seed.error}")

        _as_authenticated(db, VENDOR_OWNER_ID)
        result = db.run(
            f"UPDATE public.services SET status = 'active' WHERE id = '{draft_id}';"
        )
        _rollback(db)
        db.run(
            f"""
            BEGIN;
            SET LOCAL role service_role;
            SET LOCAL "request.jwt.claims" = '{{"role":"service_role"}}';
            DELETE FROM public.services WHERE id = '{draft_id}';
            COMMIT;
            """
        )
        assert not result.ok
        assert result.error is not None
        assert "server-controlled" in result.error

    def test_public_select_hides_active_when_provider_inactive(self, db: PgConn) -> None:
        suspend = db.run(
            f"""
            BEGIN;
            SET LOCAL role service_role;
            SET LOCAL "request.jwt.claims" = '{{"role":"service_role"}}';
            UPDATE public.vendors SET status = 'suspended' WHERE id = '{SHOP_A_ID}';
            COMMIT;
            """
        )
        if not suspend.ok:
            pytest.skip(f"could not suspend provider: {suspend.error}")

        try:
            _as_anon(db)
            result = db.run(
                f"SELECT id::text FROM public.services WHERE id = '{SERVICE_ID}';"
            )
            _rollback(db)
            assert result.ok
            assert result.rows == []
        finally:
            db.run(
                f"""
                BEGIN;
                SET LOCAL role service_role;
                SET LOCAL "request.jwt.claims" = '{{"role":"service_role"}}';
                UPDATE public.vendors SET status = 'active' WHERE id = '{SHOP_A_ID}';
                COMMIT;
                """
            )
