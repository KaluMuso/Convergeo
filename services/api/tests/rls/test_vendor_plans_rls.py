"""Vendor plans + canonical photos at the database (migrations 20261113235000/235100).

Row isolation (a vendor never sees another vendor's plan assignment or override),
client write denial, and the listing admission trigger's least(KYC, plan) cap.
Runs against the real migrated schema via the RLS harness (`db` fixture).
"""

from __future__ import annotations

import subprocess
from collections.abc import Generator

import pytest
from tests.rls.conftest import Persona, PgConn, RoleSession, SqlResult, _extract_sqlstate

VENDOR_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VENDOR_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
PHONE = "b0000000-0000-0000-0000-000000000001"
HIDDEN_PLAN = "rls_hidden_plan"
WHERE_A = f"WHERE vendor_id = '{VENDOR_A}'"


def _script(db: PgConn, sql: str) -> SqlResult:
    """Multi-statement script as the migration owner: quiet tags, verbose SQLSTATE."""
    proc = subprocess.run(
        ["psql", db.dsn, "-q", "-v", "ON_ERROR_STOP=1", "-v", "VERBOSITY=verbose", "-At"],
        input=sql,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return SqlResult(
            ok=False, rows=[], error=proc.stderr.strip(), sqlstate=_extract_sqlstate(proc.stderr)
        )
    return SqlResult(ok=True, rows=[line for line in proc.stdout.splitlines() if line])


def _q(session: RoleSession, sql: str) -> SqlResult:
    return session.execute(sql)


def _value(result: SqlResult) -> str:
    assert result.ok, result.error
    assert result.rows, "query returned no rows"
    return result.rows[-1]


@pytest.fixture(scope="module")
def seeded(db: PgConn) -> Generator[PgConn, None, None]:
    cleanup = f"""
        DELETE FROM public.vendor_plan_assignments WHERE vendor_id IN ('{VENDOR_A}', '{VENDOR_B}');
        DELETE FROM public.vendor_plan_overrides WHERE vendor_id IN ('{VENDOR_A}', '{VENDOR_B}');
        DELETE FROM public.vendor_plans WHERE key = '{HIDDEN_PLAN}';
        DELETE FROM public.product_images WHERE product_id = '{PHONE}';
    """
    result = _script(
        db,
        cleanup
        + f"""
        INSERT INTO public.vendor_plans (key, name, price_ngwee, max_listings, active)
          VALUES ('{HIDDEN_PLAN}', 'Hidden', 100, 5, false);
        INSERT INTO public.vendor_plan_assignments (vendor_id, plan_key)
          VALUES ('{VENDOR_A}', 'starter'), ('{VENDOR_B}', 'business');
        INSERT INTO public.vendor_plan_overrides (vendor_id, max_listings, expires_at, reason)
          VALUES ('{VENDOR_A}', 40, now() + interval '7 days', 'rls test'),
                 ('{VENDOR_B}', 60, now() + interval '7 days', 'rls test');
        INSERT INTO public.product_images (product_id, cloudinary_public_id, position)
          VALUES ('{PHONE}', 'canonical/phone-1', 1);
        """,
    )
    assert result.ok, result.error
    yield db
    _script(db, cleanup)


def _as(db: PgConn, persona: Persona) -> RoleSession:
    return RoleSession(db, persona)


# ---------------------------------------------------------------------------
# Row isolation
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("table", ["vendor_plan_assignments", "vendor_plan_overrides"])
def test_vendor_sees_only_own_row(seeded: PgConn, table: str) -> None:
    vendor_a = _as(seeded, Persona.VENDOR)
    vendor_b = _as(seeded, Persona.OTHER_VENDOR)
    assert (
        _value(_q(vendor_a, f"SELECT string_agg(vendor_id::text, ',') FROM public.{table}"))
        == VENDOR_A
    )
    assert (
        _value(_q(vendor_b, f"SELECT string_agg(vendor_id::text, ',') FROM public.{table}"))
        == VENDOR_B
    )
    cross = _q(vendor_a, f"SELECT count(*) FROM public.{table} WHERE vendor_id = '{VENDOR_B}'")
    assert _value(cross) == "0"


@pytest.mark.parametrize("table", ["vendor_plan_assignments", "vendor_plan_overrides"])
def test_customer_sees_no_plan_rows_and_admin_sees_all(seeded: PgConn, table: str) -> None:
    customer = _as(seeded, Persona.OTHER_CUSTOMER)
    admin = _as(seeded, Persona.ADMIN)
    assert _value(_q(customer, f"SELECT count(*) FROM public.{table}")) == "0"
    admin_count = _q(
        admin,
        f"SELECT count(*) FROM public.{table} WHERE vendor_id IN ('{VENDOR_A}', '{VENDOR_B}')",
    )
    assert _value(admin_count) == "2"


@pytest.mark.parametrize("table", ["vendor_plan_assignments", "vendor_plan_overrides"])
def test_anon_cannot_read_plan_rows(seeded: PgConn, table: str) -> None:
    result = _q(_as(seeded, Persona.ANON), f"SELECT count(*) FROM public.{table}")
    assert not result.ok
    assert result.sqlstate == "42501"


def test_inactive_plan_hidden_from_vendors_visible_to_admin(seeded: PgConn) -> None:
    sql = f"SELECT count(*) FROM public.vendor_plans WHERE key = '{HIDDEN_PLAN}'"
    assert _value(_q(_as(seeded, Persona.VENDOR), sql)) == "0"
    assert _value(_q(_as(seeded, Persona.ADMIN), sql)) == "1"
    active = (
        "SELECT count(*) FROM public.vendor_plans WHERE key IN ('free','starter','business','pro')"
    )
    assert _value(_q(_as(seeded, Persona.VENDOR), active)) == "4"


@pytest.mark.parametrize(
    "statement",
    [
        f"UPDATE public.vendor_plan_assignments SET plan_key = 'pro' {WHERE_A}",
        f"UPDATE public.vendor_plan_overrides SET max_listings = 9999 {WHERE_A}",
        f"DELETE FROM public.vendor_plan_overrides WHERE vendor_id = '{VENDOR_A}'",
        "UPDATE public.vendor_plans SET price_ngwee = 0 WHERE key = 'pro'",
        "INSERT INTO public.vendor_plan_assignments (vendor_id, plan_key) "
        f"VALUES ('{VENDOR_A}', 'pro')",
        f"DELETE FROM public.product_images WHERE product_id = '{PHONE}'",
    ],
)
@pytest.mark.parametrize("persona", [Persona.VENDOR, Persona.ADMIN, Persona.CUSTOMER])
def test_clients_cannot_write_plans_or_photos(
    seeded: PgConn, statement: str, persona: Persona
) -> None:
    """A vendor cannot self-upgrade; even admins write only through the audited API."""
    result = _q(_as(seeded, persona), statement)
    assert not result.ok
    assert result.sqlstate == "42501", result.error


def test_vendor_cannot_call_plan_cap_resolver(seeded: PgConn) -> None:
    result = _q(_as(seeded, Persona.VENDOR), f"SELECT public.vendor_plan_listing_cap('{VENDOR_B}')")
    assert not result.ok
    assert result.sqlstate == "42501"


def test_product_images_public_for_active_product_only(seeded: PgConn) -> None:
    anon = _as(seeded, Persona.ANON)
    sql = f"SELECT count(*) FROM public.product_images WHERE product_id = '{PHONE}'"
    assert _value(_q(anon, sql)) == "1"
    hidden = _script(
        seeded,
        f"""
        BEGIN;
        UPDATE public.products SET status = 'pending_moderation' WHERE id = '{PHONE}';
        SET LOCAL ROLE vergeo_rls_tester;
        SET LOCAL role anon;
        SELECT count(*) FROM public.product_images WHERE product_id = '{PHONE}';
        ROLLBACK;
        """,
    )
    assert hidden.ok, hidden.error
    assert hidden.rows[-1] == "0"


# ---------------------------------------------------------------------------
# Listing admission trigger: least(KYC cap, plan cap)
# ---------------------------------------------------------------------------
def _counted_listings(db: PgConn, vendor_id: str) -> int:
    result = db.run(
        "SELECT count(*) FROM public.vendor_listings "
        f"WHERE vendor_id = '{vendor_id}' AND status IN ('draft', 'active', 'paused')"
    )
    assert result.ok, result.error
    return int(result.rows[0])


def _admission(db: PgConn, *, setup: str, stock_qty: int = 1) -> SqlResult:
    """Run setup + one listing insert as the migration owner, always rolled back."""
    return _script(
        db,
        f"""
        BEGIN;
        DELETE FROM public.vendor_plan_overrides WHERE vendor_id = '{VENDOR_A}';
        {setup}
        INSERT INTO public.vendor_listings
          (vendor_id, product_id, product_class, price_ngwee, condition, stock_mode,
           stock_qty, status)
          VALUES ('{VENDOR_A}', '{PHONE}', 'A', 150000, 'new', 'tracked', {stock_qty}, 'draft');
        SELECT 'admitted';
        ROLLBACK;
        """,
    )


def _plan_at(count: int) -> str:
    return f"""
        INSERT INTO public.vendor_plans (key, name, max_listings)
          VALUES ('rls_tiny', 'Tiny', {count});
        UPDATE public.vendor_plan_assignments SET plan_key = 'rls_tiny' {WHERE_A};
    """


FLAG_ON = "UPDATE public.feature_flags SET enabled = true WHERE flag = 'vendor_plans';"
FLAG_OFF = "UPDATE public.feature_flags SET enabled = false WHERE flag = 'vendor_plans';"


def test_plan_cap_refuses_new_listing_at_limit(seeded: PgConn) -> None:
    count = _counted_listings(seeded, VENDOR_A)
    result = _admission(seeded, setup=FLAG_ON + _plan_at(count))
    assert not result.ok
    assert result.sqlstate == "PT403"
    assert "listing_cap_exceeded" in (result.error or "")


def test_plan_cap_counts_listings_not_stock(seeded: PgConn) -> None:
    count = _counted_listings(seeded, VENDOR_A)
    result = _admission(seeded, setup=FLAG_ON + _plan_at(count + 1), stock_qty=1_000_000)
    assert result.ok, result.error
    assert result.rows[-1] == "admitted"


def test_flag_off_ignores_plan_cap(seeded: PgConn) -> None:
    count = _counted_listings(seeded, VENDOR_A)
    result = _admission(seeded, setup=FLAG_OFF + _plan_at(count))
    assert result.ok, result.error


def test_unlimited_override_lifts_plan_cap(seeded: PgConn) -> None:
    count = _counted_listings(seeded, VENDOR_A)
    override = f"""
        INSERT INTO public.vendor_plan_overrides (vendor_id, unlimited_listings, expires_at, reason)
          VALUES ('{VENDOR_A}', true, now() + interval '1 day', 'launch promo');
    """
    result = _admission(seeded, setup=FLAG_ON + _plan_at(count) + override)
    assert result.ok, result.error


def test_expired_override_is_ignored(seeded: PgConn) -> None:
    count = _counted_listings(seeded, VENDOR_A)
    override = f"""
        INSERT INTO public.vendor_plan_overrides (vendor_id, unlimited_listings, expires_at, reason)
          VALUES ('{VENDOR_A}', true, now() - interval '1 minute', 'expired promo');
    """
    result = _admission(seeded, setup=FLAG_ON + _plan_at(count) + override)
    assert not result.ok
    assert result.sqlstate == "PT403"


def test_plan_never_lifts_kyc_cap(seeded: PgConn) -> None:
    """An unlimited plan still stops at the KYC trust cap."""
    count = _counted_listings(seeded, VENDOR_A)
    kyc_tier = seeded.run(
        "SELECT coalesce(max(tier), 1) FROM public.kyc_records "
        f"WHERE vendor_id = '{VENDOR_A}' AND status = 'approved'"
    )
    assert kyc_tier.ok, kyc_tier.error
    setup = (
        FLAG_ON
        + f"UPDATE public.vendor_plan_assignments SET plan_key = 'pro' {WHERE_A};"
        + f"UPDATE public.vendor_quotas SET max_listings = {count} WHERE tier = {kyc_tier.rows[0]};"
    )
    result = _admission(seeded, setup=setup)
    assert not result.ok
    assert result.sqlstate == "PT403"


def test_downgrade_never_removes_existing_listings(seeded: PgConn) -> None:
    """Over the limit after a downgrade: existing listings untouched, edits allowed."""
    result = _script(
        seeded,
        f"""
        BEGIN;
        {FLAG_ON}
        {_plan_at(0)}
        UPDATE public.vendor_listings SET price_ngwee = price_ngwee
          WHERE vendor_id = '{VENDOR_A}' AND status IN ('draft', 'active', 'paused');
        SELECT count(*) FROM public.vendor_listings
          WHERE vendor_id = '{VENDOR_A}' AND status IN ('draft', 'active', 'paused');
        ROLLBACK;
        """,
    )
    assert result.ok, result.error
    assert int(result.rows[-1]) == _counted_listings(seeded, VENDOR_A)


def test_product_image_count_guard(seeded: PgConn) -> None:
    inserts = "\n".join(
        f"INSERT INTO public.product_images (product_id, cloudinary_public_id, position) "
        f"VALUES ('{PHONE}', 'canonical/extra-{n}', {n});"
        for n in range(2, 9)
    )
    result = _script(
        seeded,
        f"""
        BEGIN;
        {inserts}
        UPDATE public.product_images SET position = position WHERE product_id = '{PHONE}';
        INSERT INTO public.product_images (product_id, cloudinary_public_id, position)
          VALUES ('{PHONE}', 'canonical/ninth', 8);
        ROLLBACK;
        """,
    )
    assert not result.ok
    assert "more than 8 images" in (result.error or "")


def test_listing_image_sha256_shape_enforced(seeded: PgConn) -> None:
    result = seeded.run(
        "BEGIN; UPDATE public.listing_images SET content_sha256 = 'not-a-hash' "
        "WHERE id = (SELECT id FROM public.listing_images LIMIT 1); ROLLBACK;"
    )
    has_rows = seeded.run("SELECT count(*) FROM public.listing_images")
    if has_rows.ok and has_rows.rows and has_rows.rows[0] == "0":
        pytest.skip("no listing_images seeded")
    assert not result.ok
    assert result.sqlstate == "23514"
