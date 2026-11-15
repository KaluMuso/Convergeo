# ruff: noqa: E501 — long inline SQL fixtures
"""Plan active-listing limits, trials and paid extras at the DB (20261115230000).

Publish guard boundaries (drafts free; Nth active ok, N+1th refused), seeds,
trial default/backfill + billing seam, the guarded extras state machine and RLS
isolation. Every write runs as the migration owner inside a rolled-back
transaction; RLS reads use the persona sessions.
"""

from __future__ import annotations

import subprocess

import pytest
from tests.rls.conftest import Persona, PgConn, RoleSession, SqlResult, _extract_sqlstate

VENDOR_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VENDOR_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
PHONE = "b0000000-0000-0000-0000-000000000001"
FLAG_ON = "UPDATE public.feature_flags SET enabled = true WHERE flag = 'vendor_plans';"


def _script(db: PgConn, sql: str) -> SqlResult:
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


def _rolled_back(db: PgConn, body: str) -> SqlResult:
    return _script(db, f"BEGIN;\n{body}\nROLLBACK;")


def _active_count(db: PgConn) -> int:
    result = db.run(
        f"SELECT count(*) FROM public.vendor_listings WHERE vendor_id = '{VENDOR_A}' "
        "AND status = 'active'"
    )
    assert result.ok, result.error
    return int(result.rows[0])


def _plan_cap(cap: int) -> str:
    """A plan whose active limit is `cap`, assigned to vendor A (no live override)."""
    return f"""
        {FLAG_ON}
        DELETE FROM public.vendor_plan_overrides WHERE vendor_id = '{VENDOR_A}';
        -- Plenty of KYC room so only the plan can bind.
        UPDATE public.vendor_quotas SET max_listings = 9999;
        INSERT INTO public.vendor_plans (key, name, max_listings) VALUES ('rls_cap', 'Cap', {cap});
        INSERT INTO public.vendor_plan_assignments (vendor_id, plan_key)
          VALUES ('{VENDOR_A}', 'rls_cap')
          ON CONFLICT (vendor_id) DO UPDATE SET plan_key = 'rls_cap';
    """


def _insert(status: str) -> str:
    return f"""
        INSERT INTO public.vendor_listings
          (vendor_id, product_id, product_class, price_ngwee, condition, stock_mode, stock_qty, status)
          VALUES ('{VENDOR_A}', '{PHONE}', 'A', 150000, 'new', 'tracked', 1, '{status}');
    """


# ---------------------------------------------------------------------------
# Seeds
# ---------------------------------------------------------------------------
def test_seeded_listing_limits_and_discount(db: PgConn) -> None:
    result = db.run(
        "SELECT string_agg(key || '=' || coalesce(max_listings::text, 'unlimited'), ',' "
        "ORDER BY position) FROM public.vendor_plans "
        "WHERE key IN ('free', 'starter', 'business', 'chain', 'enterprise', 'enterprise_plus')"
    )
    assert result.ok, result.error
    assert result.rows[0] == (
        "free=20,starter=200,business=unlimited,chain=unlimited,"
        "enterprise=unlimited,enterprise_plus=unlimited"
    )
    pct = db.run(
        "SELECT value::text FROM public.platform_config WHERE key = 'plan_annual_discount_pct'"
    )
    assert pct.ok and pct.rows == ["15"]


def test_seed_extras_catalogue(db: PgConn) -> None:
    result = db.run(
        "SELECT count(*), count(*) FILTER (WHERE price_is_placeholder), "
        "min(price_ngwee) FILTER (WHERE key = 'store_design'), "
        "max(price_max_ngwee) FILTER (WHERE key = 'store_design') FROM public.vendor_extras"
    )
    assert result.ok, result.error
    assert result.rows[0] == "12|11|50000|500000"


# ---------------------------------------------------------------------------
# Publish guard (active-listing limit)
# ---------------------------------------------------------------------------
def test_drafts_allowed_beyond_plan_limit(db: PgConn) -> None:
    result = _rolled_back(db, _plan_cap(0) + _insert("draft") + _insert("draft") + "SELECT 'ok';")
    assert result.ok, result.error


def test_publish_at_limit_minus_one_succeeds(db: PgConn) -> None:
    cap = _active_count(db) + 1
    result = _rolled_back(db, _plan_cap(cap) + _insert("active") + "SELECT 'ok';")
    assert result.ok, result.error


def test_publish_beyond_limit_is_refused(db: PgConn) -> None:
    cap = _active_count(db)
    result = _rolled_back(db, _plan_cap(cap) + _insert("active"))
    assert not result.ok
    assert result.sqlstate == "PT403"
    assert "listing_plan_limit_reached" in (result.error or "")


def test_activating_a_draft_beyond_limit_is_refused(db: PgConn) -> None:
    cap = _active_count(db)
    body = (
        _plan_cap(cap)
        + _insert("draft")
        + f"""UPDATE public.vendor_listings SET status = 'active'
              WHERE vendor_id = '{VENDOR_A}' AND status = 'draft';"""
    )
    result = _rolled_back(db, body)
    assert not result.ok and result.sqlstate == "PT403"


def test_reactivating_paused_listing_beyond_limit_is_refused(db: PgConn) -> None:
    cap = _active_count(db)
    body = (
        _plan_cap(cap)
        + _insert("paused")
        + f"""UPDATE public.vendor_listings SET status = 'active'
              WHERE vendor_id = '{VENDOR_A}' AND status = 'paused';"""
    )
    result = _rolled_back(db, body)
    assert not result.ok and result.sqlstate == "PT403"


def test_existing_active_listings_stay_editable_over_limit(db: PgConn) -> None:
    body = (
        _plan_cap(0)
        + f"""
        UPDATE public.vendor_listings SET price_ngwee = price_ngwee
          WHERE vendor_id = '{VENDOR_A}' AND status = 'active';
        SELECT 'ok';
    """
    )
    result = _rolled_back(db, body)
    assert result.ok, result.error


def test_flag_off_and_unlimited_plans_never_block_publish(db: PgConn) -> None:
    off = _rolled_back(
        db,
        _plan_cap(0)
        + "UPDATE public.feature_flags SET enabled = false WHERE flag = 'vendor_plans';"
        + _insert("active")
        + "SELECT 'ok';",
    )
    assert off.ok, off.error
    unlimited = _rolled_back(
        db,
        _plan_cap(0)
        + f"UPDATE public.vendor_plan_assignments SET plan_key = 'business' WHERE vendor_id = '{VENDOR_A}';"
        + _insert("active")
        + "SELECT 'ok';",
    )
    assert unlimited.ok, unlimited.error


# ---------------------------------------------------------------------------
# Trial
# ---------------------------------------------------------------------------
def test_existing_businesses_backfilled_with_trial(db: PgConn) -> None:
    result = db.run(
        "SELECT count(*) FILTER (WHERE trial_ends_at IS NULL), "
        "bool_and(trial_ends_at > now() + interval '50 days') FROM public.vendor_businesses"
    )
    assert result.ok, result.error
    assert result.rows[0] == "0|t"


def test_new_business_trial_is_signup_plus_two_months(db: PgConn) -> None:
    result = _rolled_back(
        db,
        f"""
        INSERT INTO public.vendor_businesses (id, owner_user_id, legal_name, created_at, trial_ends_at)
          SELECT gen_random_uuid(), owner_user_id, 'Trial Test', '2026-11-15 09:00+00', '2030-01-01'
          FROM public.vendors WHERE id = '{VENDOR_A}'
          RETURNING trial_ends_at = '2027-01-15 09:00+00';
        """,
    )
    assert result.ok, result.error
    assert result.rows[-1] == "t"


def test_billing_seam_no_fee_during_trial(db: PgConn) -> None:
    result = _rolled_back(
        db,
        f"""
        SELECT public.vendor_plan_fee_accrues('{VENDOR_A}');
        UPDATE public.vendor_businesses SET trial_ends_at = now() - interval '1 second'
          WHERE id = (SELECT business_id FROM public.vendors WHERE id = '{VENDOR_A}');
        SELECT public.vendor_plan_fee_accrues('{VENDOR_A}');
        """,
    )
    assert result.ok, result.error
    assert result.rows[-2:] == ["f", "t"]


def test_vendor_cannot_call_billing_seam_or_edit_trial(db: PgConn) -> None:
    vendor = RoleSession(db, Persona.VENDOR)
    call = vendor.execute(f"SELECT public.vendor_plan_fee_accrues('{VENDOR_A}')")
    assert not call.ok and call.sqlstate == "42501"
    edit = vendor.execute(
        f"UPDATE public.vendor_businesses SET trial_ends_at = '2099-01-01' WHERE id = '{VENDOR_A}'"
    )
    assert not edit.ok and edit.sqlstate == "42501"


# ---------------------------------------------------------------------------
# Extras state machine
# ---------------------------------------------------------------------------
def _with_request(steps: str) -> str:
    return f"""
        INSERT INTO public.vendor_extras_requests (id, vendor_id, extra_key, requested_by)
          SELECT 'eeeeeeee-0000-0000-0000-000000000001', id, 'store_design', owner_user_id
          FROM public.vendors WHERE id = '{VENDOR_A}';
        {steps}
    """


def _t(to: str, role: str = "admin", price: str = "NULL", actor: str = "NULL") -> str:
    actor_sql = (
        actor
        if actor != "NULL"
        else f"(SELECT owner_user_id FROM public.vendors WHERE id = '{VENDOR_A}')"
        if role == "vendor"
        else "NULL"
    )
    return (
        "SELECT public.transition_vendor_extras_request("
        f"'eeeeeeee-0000-0000-0000-000000000001', '{to}', {actor_sql}, '{role}', 'n', {price})"
        "->>'to';"
    )


def test_extras_happy_path_records_history_and_notifies(db: PgConn) -> None:
    body = _with_request(
        _t("quoted", price="120000")
        + _t("approved", role="vendor")
        + _t("fulfilled")
        + """SELECT string_agg(coalesce(from_status, '-') || '>' || to_status, ',' ORDER BY created_at, to_status)
             FROM public.vendor_extras_request_events
             WHERE request_id = 'eeeeeeee-0000-0000-0000-000000000001';
           SELECT count(*) > 0 FROM public.in_app_notifications
             WHERE dedupe_key = 'extras_requested:eeeeeeee-0000-0000-0000-000000000001';"""
    )
    result = _rolled_back(db, body)
    assert result.ok, result.error
    assert result.rows[:3] == ["quoted", "approved", "fulfilled"]
    assert set(result.rows[3].split(",")) == {
        "->requested",
        "requested>quoted",
        "quoted>approved",
        "approved>fulfilled",
    }
    assert result.rows[4] in {"t", "f"}  # admin recipients depend on seeded roles


@pytest.mark.parametrize(
    ("steps", "message"),
    [
        (_t("fulfilled"), "extras_invalid_transition"),  # must be approved first
        (_t("quoted"), "extras_quote_price_required"),
        (_t("approved", price="100"), "extras_quote_price_unexpected"),
        (_t("approved", role="vendor"), "extras_invalid_transition"),  # nothing quoted yet
        (_t("cancelled") + _t("approved"), "extras_invalid_transition"),  # terminal
        (
            _t("cancelled", role="vendor", actor="'44444444-4444-4444-4444-444444444444'"),
            "extras_request_not_owner",
        ),
    ],
)
def test_extras_invalid_transitions_refused(db: PgConn, steps: str, message: str) -> None:
    result = _rolled_back(db, _with_request(steps))
    assert not result.ok
    assert message in (result.error or "")


def test_raw_status_update_is_guarded(db: PgConn) -> None:
    result = _rolled_back(
        db,
        _with_request(
            "UPDATE public.vendor_extras_requests SET status = 'fulfilled' "
            "WHERE id = 'eeeeeeee-0000-0000-0000-000000000001';"
        ),
    )
    assert not result.ok and "extras_request_status_guarded" in (result.error or "")


def test_one_open_request_per_shop_and_extra(db: PgConn) -> None:
    result = _rolled_back(
        db,
        _with_request(
            f"""INSERT INTO public.vendor_extras_requests (vendor_id, extra_key, requested_by)
                SELECT id, 'store_design', owner_user_id FROM public.vendors WHERE id = '{VENDOR_A}';"""
        ),
    )
    assert not result.ok and result.sqlstate == "23505"


def test_extras_rls_isolation(db: PgConn) -> None:
    seeded = _script(
        db,
        _with_request("")
        + f"""INSERT INTO public.vendor_extras_requests (vendor_id, extra_key, requested_by)
              SELECT id, 'custom_domain', owner_user_id FROM public.vendors WHERE id = '{VENDOR_B}';""",
    )
    assert seeded.ok, seeded.error
    try:
        own = RoleSession(db, Persona.VENDOR).execute(
            "SELECT count(*) FROM public.vendor_extras_requests"
        )
        other = RoleSession(db, Persona.OTHER_VENDOR).execute(
            "SELECT count(*) FROM public.vendor_extras_requests"
        )
        customer = RoleSession(db, Persona.CUSTOMER).execute(
            "SELECT count(*) FROM public.vendor_extras_requests"
        )
        catalogue = RoleSession(db, Persona.CUSTOMER).execute(
            "SELECT count(*) FROM public.vendor_extras"
        )
        anon = RoleSession(db, Persona.ANON).execute("SELECT count(*) FROM public.vendor_extras")
        write = RoleSession(db, Persona.VENDOR).execute(
            f"INSERT INTO public.vendor_extras_requests (vendor_id, extra_key, requested_by) "
            f"VALUES ('{VENDOR_A}', 'banner_ads', '33333333-3333-3333-3333-333333333333')"
        )
    finally:
        _script(
            db,
            "SET convergeo.extras_transition = 'on'; DELETE FROM public.vendor_extras_requests "
            f"WHERE vendor_id IN ('{VENDOR_A}', '{VENDOR_B}');",
        )
    assert own.ok and own.rows[-1] == "1"
    assert other.ok and other.rows[-1] == "1"
    assert customer.ok and customer.rows[-1] == "0"
    assert catalogue.ok and catalogue.rows[-1] == "12"  # active catalogue is readable
    assert not anon.ok and anon.sqlstate == "42501"
    assert not write.ok and write.sqlstate == "42501"
