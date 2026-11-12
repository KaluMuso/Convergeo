"""Real-Postgres checks for catalog moderation holds (no table doubles).

Runs only against a disposable migrated LOCAL database with
CATALOG_MODERATION_ISOLATED_DB=1 (e.g. SUPABASE_DB_URL=postgresql:///vergeo5_ads_test).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from urllib.parse import urlparse

import pytest
from tests.rls.conftest import (
    PgConn,
    SqlResult,
    apply_migrations,
    schema_ready,
    seed_matrix_fixtures,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("CATALOG_MODERATION_ISOLATED_DB") != "1",
    reason="Disposable DB attestation required (CATALOG_MODERATION_ISOLATED_DB=1)",
)

ACTOR = "66666666-6666-6666-6666-666666666666"


@pytest.fixture(scope="module")
def db() -> Generator[PgConn, None, None]:
    url = os.environ.get("SUPABASE_DB_URL", "postgresql:///vergeo5_ads_test")
    assert urlparse(url).hostname in {"127.0.0.1", "localhost", "::1", None}, "Local DB only"
    conn = PgConn(url)
    assert conn.run("SELECT 1").ok, "Actual PostgreSQL is required"
    if not schema_ready(conn):
        apply_migrations(conn)
    seed_matrix_fixtures(conn)
    yield conn


SERVICE_ROLE = (
    "DO $$ BEGIN PERFORM set_config('request.jwt.claims', '{\"role\":\"service_role\"}', false); "
    "END $$; "
)


def _svc(db: PgConn, sql: str) -> SqlResult:
    """Run as the API does: service-role JWT claims (lifecycle guards admit it)."""
    result = db.run(SERVICE_ROLE + sql)
    result.rows = [row for row in result.rows if row != "DO"]
    return result


def _one(db: PgConn, sql: str) -> str:
    result = _svc(db, sql)
    assert result.ok, result.error
    assert result.rows, sql
    return result.rows[0]


def _active_vendor(db: PgConn) -> str:
    vendor_id = str(uuid.uuid4())
    owner = _one(db, "SELECT owner_user_id FROM public.vendors WHERE status = 'active' LIMIT 1")
    _one(
        db,
        "INSERT INTO public.vendors (id, owner_user_id, slug, display_name, status, kyc_tier) "
        f"VALUES ('{vendor_id}', '{owner}', 'mod-{vendor_id[:8]}', 'Moderation test', "
        "'active', 1) RETURNING id",
    )
    _one(
        db,
        "INSERT INTO public.kyc_records (vendor_id, tier, status) "
        f"VALUES ('{vendor_id}', 1, 'approved') RETURNING id",
    )
    return vendor_id


def _listing(db: PgConn, vendor_id: str) -> str:
    template = _one(
        db,
        "SELECT product_id || '|' || condition FROM public.vendor_listings "
        "WHERE status = 'active' AND product_id IS NOT NULL LIMIT 1",
    )
    product_id, condition = template.split("|")
    listing_id = str(uuid.uuid4())
    _one(
        db,
        "INSERT INTO public.vendor_listings (id, vendor_id, product_id, title_override, "
        "price_ngwee, condition, stock_mode, stock_qty, status) VALUES "
        f"('{listing_id}', '{vendor_id}', '{product_id}', 'Moderated', 1000, '{condition}', "
        "'tracked', 5, 'active') RETURNING id",
    )
    return listing_id


def _status(db: PgConn, table: str, entity_id: str) -> str:
    return _one(db, f"SELECT status FROM public.{table} WHERE id = '{entity_id}'")


def test_hide_then_restore_listing_returns_previous_status(db: PgConn) -> None:
    listing = _listing(db, _active_vendor(db))
    _one(
        db,
        f"SELECT id FROM public.moderate_catalog_entity('listing', '{listing}', 'hide', "
        f"'{ACTOR}', 'Counterfeit report')",
    )
    assert _status(db, "vendor_listings", listing) == "paused"
    _one(
        db,
        f"SELECT id FROM public.release_catalog_moderation('listing', '{listing}', "
        f"'{ACTOR}', 'Cleared after review')",
    )
    assert _status(db, "vendor_listings", listing) == "active"


def test_held_listing_cannot_be_reactivated_by_any_other_writer(db: PgConn) -> None:
    listing = _listing(db, _active_vendor(db))
    _one(
        db,
        f"SELECT id FROM public.moderate_catalog_entity('listing', '{listing}', 'hide', "
        f"'{ACTOR}', 'Policy review')",
    )
    # The vendor API runs as the service role; a raw UPDATE must still be refused.
    result = _svc(db, f"UPDATE public.vendor_listings SET status = 'active' WHERE id = '{listing}'")
    assert not result.ok
    assert "catalog_moderation_hold" in (result.error or "")
    assert _status(db, "vendor_listings", listing) == "paused"


def test_block_escalates_hide_and_keeps_original_restore_target(db: PgConn) -> None:
    listing = _listing(db, _active_vendor(db))
    _one(db, f"SELECT id FROM public.moderate_catalog_entity('listing', '{listing}', 'hide', '{ACTOR}', 'first')")
    _one(db, f"SELECT id FROM public.moderate_catalog_entity('listing', '{listing}', 'block', '{ACTOR}', 'second')")
    assert _status(db, "vendor_listings", listing) == "removed"
    assert (
        _one(
            db,
            "SELECT action || '|' || from_status FROM public.catalog_moderation_holds "
            f"WHERE entity_id = '{listing}' AND released_at IS NULL",
        )
        == "block|active"
    )


def test_reason_is_required(db: PgConn) -> None:
    listing = _listing(db, _active_vendor(db))
    result = _svc(
        db,
        f"SELECT public.moderate_catalog_entity('listing', '{listing}', 'hide', '{ACTOR}', ' ')"
    )
    assert not result.ok
    assert _status(db, "vendor_listings", listing) == "active"


def test_vendor_block_and_reinstate_requires_approved_kyc(db: PgConn) -> None:
    vendor = _active_vendor(db)
    _one(db, f"SELECT id FROM public.moderate_catalog_entity('vendor', '{vendor}', 'block', '{ACTOR}', 'Fraud')")
    assert _status(db, "vendors", vendor) == "suspended"
    blocked = _svc(db, f"UPDATE public.vendors SET status = 'active' WHERE id = '{vendor}'")
    assert not blocked.ok
    _one(
        db,
        "INSERT INTO public.kyc_records (vendor_id, tier, status, created_at) "
        f"VALUES ('{vendor}', 1, 'rejected', now() + interval '1 second') RETURNING id",
    )
    refused = _svc(
        db,
        f"SELECT public.release_catalog_moderation('vendor', '{vendor}', '{ACTOR}', 'appeal')"
    )
    assert not refused.ok
    assert _status(db, "vendors", vendor) == "suspended"


def test_vendor_reinstate_after_flag_suspension_without_hold(db: PgConn) -> None:
    vendor = _active_vendor(db)
    _one(db, f"UPDATE public.vendors SET status = 'suspended' WHERE id = '{vendor}' RETURNING id")
    _one(db, f"SELECT id FROM public.release_catalog_moderation('vendor', '{vendor}', '{ACTOR}', 'appeal ok')")
    assert _status(db, "vendors", vendor) == "active"


def test_restore_without_hold_is_refused(db: PgConn) -> None:
    listing = _listing(db, _active_vendor(db))
    result = _svc(
        db,
        f"SELECT public.release_catalog_moderation('listing', '{listing}', '{ACTOR}', 'nothing')"
    )
    assert not result.ok


def test_clients_cannot_read_or_call(db: PgConn) -> None:
    for role in ("anon", "authenticated"):
        assert (
            _one(
                db,
                f"SELECT has_table_privilege('{role}', 'public.catalog_moderation_holds', "
                "'select')::text",
            )
            == "false"
        )
        for signature in (
            "public.moderate_catalog_entity(text, uuid, text, uuid, text)",
            "public.release_catalog_moderation(text, uuid, uuid, text)",
        ):
            granted = _one(
                db, f"SELECT has_function_privilege('{role}', '{signature}', 'execute')::text"
            )
            assert granted == "false"


def test_ad_target_pair_constraint(db: PgConn) -> None:
    result = _svc(
        db,
        "INSERT INTO public.ad_placements (advertiser_kind, advertiser_name, placement_type, "
        "image_public_id, headline, cta_href, starts_at, ends_at, target_kind) VALUES "
        "('external', 'Acme', 'feed_slot', 'img/a', 'Hello', '/', now(), now() + interval '1 day', "
        "'listing')"
    )
    assert not result.ok
