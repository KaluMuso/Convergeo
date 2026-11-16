"""Multi-branch businesses at the database (migration 20261116120000).

Proves, against the real migrated schema:
  * backfill: every vendor is a business (same id) with one primary approved branch;
  * RLS: owners read only their own business / branch rows; duplicate flags are
    admin-only; clients cannot write any new table or the server-controlled
    branch columns on ``vendors``;
  * anti-duplication + limits (failure paths): unregistered single shop, plan shop
    allowance, PACRA uniqueness + certificate rule, sibling GPS distance (admin-
    editable), payout never shared across owners, same-owner shared payout ->
    review flag + payout hold, fuzzy duplicate scan (name / phone / photo hash),
    staff seat cap;
  * guarded state machine: no raw branch_status writes, evidence before review,
    approval blocked by open flags / missing owner KYC, approval inherits KYC.

Every scenario runs in one transaction that is rolled back, so the shared
matrix seed is untouched.
"""

# ruff: noqa: E501 — long inline SQL scenarios read better unwrapped.
from __future__ import annotations

import json
import subprocess
from collections.abc import Generator
from typing import Any

import pytest
from tests.rls.conftest import Persona, PgConn, RoleSession, SqlResult, _extract_sqlstate

VENDOR_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"  # owner 3333…, East Park Mall
VENDOR_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"  # owner 4444…
OWNER_A = "33333333-3333-3333-3333-333333333333"
OWNER_B = "44444444-4444-4444-4444-444444444444"
ADMIN = "66666666-6666-6666-6666-666666666666"
KYC_A = "a5000000-0000-0000-0000-00000000000a"
FLAG_SEED = "a5000000-0000-0000-0000-0000000000f1"

# ~1.1 km from shop A's seeded location (-15.4167, 28.2833).
FAR = {"lat": -15.4067, "lng": 28.2833, "landmark": "Manda Hill, Lusaka"}
NEAR = {"lat": -15.41672, "lng": 28.28332, "landmark": "East Park Mall, next door"}


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


def _payload(
    name: str, payout: str, *, loc: dict[str, object] | None = None, **extra: object
) -> str:
    body: dict[str, object] = {
        "display_name": name,
        "slug": name.lower().replace(" ", "-"),
        "branch_kind": "physical",
        "contact_phone": "0971111111",
        "payout_msisdn": payout,
        "payout_rail": "mtn",
        **(loc or FAR),
        **extra,
    }
    return json.dumps(body).replace("'", "''")


def _create(name: str, payout: str, **kw: Any) -> str:
    return (
        f"SELECT public.create_vendor_branch('{VENDOR_A}', '{OWNER_A}', "
        f"'{_payload(name, payout, **kw)}'::jsonb) ->> 'id';"
    )


SETUP = f"""
BEGIN;
UPDATE public.feature_flags SET enabled = true WHERE flag = 'multi_branch';
INSERT INTO public.kyc_records (id, vendor_id, tier, status, reviewed_by, reviewed_at)
  VALUES ('{KYC_A}', '{VENDOR_A}', 2, 'approved', '{ADMIN}', now())
  ON CONFLICT (id) DO NOTHING;
UPDATE public.vendors SET payout_msisdn = '260970000001' WHERE id = '{VENDOR_A}';
UPDATE public.vendors SET payout_msisdn = '260960000002' WHERE id = '{VENDOR_B}';
"""

REGISTER_A = f"""
UPDATE public.vendor_businesses
   SET registration_type = 'company', pacra_number = '120190012345',
       pacra_cert_path = 'businesses/{VENDOR_A}/pacra-1.jpg'
 WHERE id = '{VENDOR_A}';
"""


def _plan_a(plan: str) -> str:
    return f"""
INSERT INTO public.vendor_plan_assignments (vendor_id, plan_key)
  VALUES ('{VENDOR_A}', '{plan}')
  ON CONFLICT (vendor_id) DO UPDATE SET plan_key = excluded.plan_key;
"""


def _run(db: PgConn, body: str) -> SqlResult:
    return _script(db, SETUP + body + "\nROLLBACK;\n")


def _err(result: SqlResult, token: str) -> None:
    assert not result.ok, f"expected failure {token}, got rows {result.rows}"
    assert token in (result.error or ""), result.error


def _last(result: SqlResult) -> str:
    assert result.ok, result.error
    assert result.rows, "no rows"
    return result.rows[-1]


# ---------------------------------------------------------------------------
# Backfill + RLS isolation
# ---------------------------------------------------------------------------
def test_backfill_every_vendor_is_a_business_with_one_primary_branch(db: PgConn) -> None:
    result = db.run(
        "SELECT count(*) FROM public.vendors v "
        "LEFT JOIN public.vendor_businesses b ON b.id = v.business_id "
        "WHERE b.id IS NULL OR b.owner_user_id <> v.owner_user_id"
    )
    assert result.rows == ["0"]
    assert db.run(
        f"SELECT business_id::text || ',' || is_primary_branch::text || ',' || branch_status "
        f"FROM public.vendors WHERE id = '{VENDOR_A}'"
    ).rows == [f"{VENDOR_A},true,approved"]


@pytest.fixture(scope="module")
def flag_seed(db: PgConn) -> Generator[PgConn, None, None]:
    result = _script(
        db,
        f"""
        DELETE FROM public.vendor_branch_flags WHERE id = '{FLAG_SEED}';
        INSERT INTO public.vendor_branch_flags (id, vendor_id, kind, matched_vendor_id)
          VALUES ('{FLAG_SEED}', '{VENDOR_A}', 'name_similar', '{VENDOR_B}');
        """,
    )
    assert result.ok, result.error
    yield db
    _script(db, f"DELETE FROM public.vendor_branch_flags WHERE id = '{FLAG_SEED}';")


def _as(db: PgConn, persona: Persona) -> RoleSession:
    return RoleSession(db, persona)


def test_owner_sees_only_own_business(db: PgConn) -> None:
    sql = "SELECT coalesce(string_agg(id::text, ','), 'none') FROM public.vendor_businesses"
    assert _as(db, Persona.VENDOR).execute(sql).rows[-1] == VENDOR_A
    assert _as(db, Persona.OTHER_VENDOR).execute(sql).rows[-1] == VENDOR_B
    assert _as(db, Persona.CUSTOMER).execute(sql).rows[-1] == "none"
    admin = _as(db, Persona.ADMIN).execute(
        f"SELECT count(*) FROM public.vendor_businesses WHERE id IN ('{VENDOR_A}', '{VENDOR_B}')"
    )
    assert admin.rows[-1] == "2"


def test_duplicate_flags_are_admin_only(flag_seed: PgConn) -> None:
    sql = f"SELECT count(*) FROM public.vendor_branch_flags WHERE id = '{FLAG_SEED}'"
    # Even the flagged branch's own owner must not see who it was matched with.
    assert _as(flag_seed, Persona.VENDOR).execute(sql).rows[-1] == "0"
    assert _as(flag_seed, Persona.OTHER_VENDOR).execute(sql).rows[-1] == "0"
    assert _as(flag_seed, Persona.ADMIN).execute(sql).rows[-1] == "1"


@pytest.mark.parametrize(
    "statement",
    [
        f"UPDATE public.vendor_businesses SET pacra_number = 'X1234' WHERE id = '{VENDOR_A}'",
        f"INSERT INTO public.vendor_businesses (owner_user_id, legal_name) VALUES ('{OWNER_A}', 'x')",
        f"INSERT INTO public.vendor_business_staff (business_id, display_name, invite_msisdn) "
        f"VALUES ('{VENDOR_A}', 'x', '260971234567')",
        f"DELETE FROM public.vendor_branch_events WHERE vendor_id = '{VENDOR_A}'",
        f"UPDATE public.vendors SET branch_status = 'rejected' WHERE id = '{VENDOR_A}'",
        f"UPDATE public.vendors SET business_id = '{VENDOR_B}' WHERE id = '{VENDOR_A}'",
        f"UPDATE public.vendors SET is_primary_branch = false WHERE id = '{VENDOR_A}'",
        f"INSERT INTO public.vendors (owner_user_id, slug, display_name) "
        f"VALUES ('{OWNER_A}', 'second-shop-direct', 'Second')",
    ],
)
def test_owner_cannot_write_branch_state(db: PgConn, statement: str) -> None:
    result = _as(db, Persona.VENDOR).execute(statement + ";")
    assert not result.ok, f"owner write succeeded: {statement}"
    assert result.sqlstate == "42501", result.error


# ---------------------------------------------------------------------------
# Limits (failure paths first)
# ---------------------------------------------------------------------------
def test_flag_off_refuses_branch_creation(db: PgConn) -> None:
    result = _script(
        db,
        "BEGIN; UPDATE public.feature_flags SET enabled = false WHERE flag = 'multi_branch';"
        + _create("Flag Off Shop", "0970000011")
        + " ROLLBACK;",
    )
    _err(result, "multi_branch_disabled")


def test_owner_kyc_required(db: PgConn) -> None:
    result = _run(
        db,
        f"DELETE FROM public.kyc_records WHERE id = '{KYC_A}';"
        + REGISTER_A
        + _create("No Kyc Shop", "0970000012"),
    )
    _err(result, "branch_owner_kyc_required")


def test_unregistered_trader_is_limited_to_one_shop(db: PgConn) -> None:
    result = _run(db, _plan_a("enterprise") + _create("Second Stall", "0970000013"))
    _err(result, "branch_limit_unregistered")


def test_free_plan_sells_no_extra_shop(db: PgConn) -> None:
    result = _run(db, REGISTER_A + _plan_a("free") + _create("Free Second", "0970000014"))
    _err(result, "branch_limit_plan")


def test_starter_extra_shop_is_a_paid_addon(db: PgConn) -> None:
    result = _run(
        db,
        REGISTER_A
        + _plan_a("starter")
        + f"SELECT (public.create_vendor_branch('{VENDOR_A}', '{OWNER_A}', "
        f"'{_payload('Starter Two', '0970000015')}'::jsonb)) ->> 'addon_price_ngwee';",
    )
    assert _last(result) == "9900"


def test_chain_includes_five_shops_then_addon(db: PgConn) -> None:
    steps = "".join(
        f"SELECT public.create_vendor_branch('{VENDOR_A}', '{OWNER_A}', "
        f"'{_payload(f'Chain {i}', f'097000010{i}', loc={'lat': -15.40 + i * 0.01, 'lng': 28.30, 'landmark': f'Spot {i}'})}'::jsonb) "
        f"->> 'branch_billing_role';"
        for i in range(1, 6)
    )
    result = _run(db, REGISTER_A + _plan_a("chain") + steps)
    assert result.ok, result.error
    # Primary + 4 included, the 6th shop is an add-on.
    assert result.rows[-5:] == ["included", "included", "included", "included", "addon"]


def test_pacra_number_unique_and_normalised(db: PgConn) -> None:
    result = _run(
        db,
        REGISTER_A
        + f"""
        UPDATE public.vendor_businesses
           SET registration_type = 'company', pacra_number = ' 1201 9001 2345 ',
               pacra_cert_path = 'businesses/{VENDOR_B}/pacra-1.jpg'
         WHERE id = '{VENDOR_B}';
        """,
    )
    _err(result, "vendor_businesses_pacra_number_key")


def test_registered_company_needs_certificate(db: PgConn) -> None:
    result = _run(
        db,
        f"UPDATE public.vendor_businesses SET registration_type = 'company', "
        f"pacra_number = '120190099999' WHERE id = '{VENDOR_A}';",
    )
    _err(result, "vendor_businesses_registered_needs_pacra")


def test_certificate_path_pinned_to_own_business(db: PgConn) -> None:
    result = _run(
        db,
        f"UPDATE public.vendor_businesses SET registration_type = 'company', "
        f"pacra_number = '120190099998', pacra_cert_path = 'businesses/{VENDOR_B}/x.jpg' "
        f"WHERE id = '{VENDOR_A}';",
    )
    _err(result, "vendor_businesses_cert_path_pinned")


def test_sibling_branch_closer_than_minimum_is_refused(db: PgConn) -> None:
    result = _run(
        db, REGISTER_A + _plan_a("business") + _create("Too Close", "0970000016", loc=NEAR)
    )
    _err(result, "branch_too_close_to_sibling")


def test_sibling_distance_is_admin_editable(db: PgConn) -> None:
    # FAR is ~1.1 km away: allowed at 50 m, refused once an admin sets 2 km.
    result = _run(
        db,
        REGISTER_A
        + _plan_a("business")
        + "UPDATE public.platform_config SET value = '2000'::jsonb "
        "WHERE key = 'branch_min_sibling_distance_m';" + _create("Two Km Rule", "0970000017"),
    )
    _err(result, "branch_too_close_to_sibling")


def test_payout_number_never_shared_across_owners(db: PgConn) -> None:
    result = _run(db, REGISTER_A + _plan_a("business") + _create("Borrowed Momo", "0960000002"))
    _err(result, "payout_msisdn_other_owner")


def test_payout_change_to_other_owners_number_is_refused(db: PgConn) -> None:
    result = _run(
        db, f"UPDATE public.vendors SET payout_msisdn = '0960000002' WHERE id = '{VENDOR_A}';"
    )
    _err(result, "payout_msisdn_other_owner")


def test_staff_seat_cap(db: PgConn) -> None:
    free = _run(
        db,
        _plan_a("free")
        + f"INSERT INTO public.vendor_business_staff (business_id, display_name, invite_msisdn) "
        f"VALUES ('{VENDOR_A}', 'Mutale', '260971234567');",
    )
    _err(free, "staff_seat_limit")
    starter = _run(
        db,
        _plan_a("starter")
        + "".join(
            f"INSERT INTO public.vendor_business_staff (business_id, display_name, invite_msisdn) "
            f"VALUES ('{VENDOR_A}', 'Staff {i}', '26097123456{i}');"
            for i in range(3)
        ),
    )
    _err(starter, "staff_seat_limit")


# ---------------------------------------------------------------------------
# Same-owner shared payout, dedup scan, state machine
# ---------------------------------------------------------------------------
def test_same_owner_shared_payout_is_flagged_held_and_blocks_approval(db: PgConn) -> None:
    body = (
        REGISTER_A
        + _plan_a("business")
        + f"""
        CREATE TEMP TABLE b AS SELECT (public.create_vendor_branch('{VENDOR_A}', '{OWNER_A}',
          '{_payload("Shared Momo Shop", "0970000001")}'::jsonb) ->> 'id')::uuid AS id;
        INSERT INTO public.vendor_branch_evidence (vendor_id, kind, proof_type, storage_path)
          SELECT id, 'storefront_photo', null, 'branches/{VENDOR_A}/' || id || '/storefront_photo-1.jpg' FROM b
          UNION ALL
          SELECT id, 'premises_proof', 'lease', 'branches/{VENDOR_A}/' || id || '/premises_proof-1.jpg' FROM b;
        SELECT (payout_hold_until > now() + interval '1 year')::text FROM public.vendors WHERE id = (SELECT id FROM b);
        SELECT count(*) FROM public.vendor_branch_flags
          WHERE vendor_id = (SELECT id FROM b) AND kind = 'payout_shared_same_owner' AND status = 'open';
        SELECT public.transition_vendor_branch((SELECT id FROM b), 'pending_review', '{OWNER_A}', null) ->> 'to';
        SELECT public.transition_vendor_branch((SELECT id FROM b), 'approved', '{ADMIN}', null);
        """
    )
    result = _run(db, body)
    _err(result, "branch_open_flags")


def test_cleared_flag_allows_approval_and_inherits_owner_kyc(db: PgConn) -> None:
    body = (
        REGISTER_A
        + _plan_a("business")
        + f"""
        CREATE TEMP TABLE b AS SELECT (public.create_vendor_branch('{VENDOR_A}', '{OWNER_A}',
          '{_payload("Clean Branch", "0970000001")}'::jsonb) ->> 'id')::uuid AS id;
        INSERT INTO public.vendor_branch_evidence (vendor_id, kind, proof_type, storage_path)
          SELECT id, 'storefront_photo', null, 'branches/{VENDOR_A}/' || id || '/storefront_photo-1.jpg' FROM b
          UNION ALL
          SELECT id, 'premises_proof', 'utility_bill', 'branches/{VENDOR_A}/' || id || '/premises_proof-1.jpg' FROM b;
        SELECT public.transition_vendor_branch((SELECT id FROM b), 'pending_review', '{OWNER_A}', null) ->> 'to';
        UPDATE public.vendor_branch_flags SET status = 'cleared', resolved_at = now(), resolved_by = '{ADMIN}'
          WHERE vendor_id = (SELECT id FROM b) AND status = 'open';
        SELECT public.transition_vendor_branch((SELECT id FROM b), 'approved', '{ADMIN}', 'ok') ->> 'to';
        SELECT status || ',' || branch_status || ',' || kyc_tier FROM public.vendors WHERE id = (SELECT id FROM b);
        SELECT count(*) FROM public.kyc_records
          WHERE vendor_id = (SELECT id FROM b) AND status = 'approved' AND tier = 2;
        SELECT count(*) FROM public.vendor_branch_events WHERE vendor_id = (SELECT id FROM b);
        """
    )
    result = _run(db, body)
    assert result.ok, result.error
    assert result.rows[-4:] == ["approved", "active,approved,2", "1", "3"]


def test_submit_requires_evidence_for_physical_branch(db: PgConn) -> None:
    result = _run(
        db,
        REGISTER_A
        + _plan_a("business")
        + f"""
        CREATE TEMP TABLE b AS SELECT (public.create_vendor_branch('{VENDOR_A}', '{OWNER_A}',
          '{_payload("No Proof Shop", "0970000021")}'::jsonb) ->> 'id')::uuid AS id;
        SELECT public.transition_vendor_branch((SELECT id FROM b), 'pending_review', '{OWNER_A}', null);
        """,
    )
    _err(result, "branch_evidence_required")


@pytest.mark.parametrize(
    ("to_status", "note", "token"),
    [
        ("approved", "null", "branch_invalid_transition"),  # draft -> approved skips review
        ("rejected", "null", "branch_invalid_transition"),
    ],
)
def test_invalid_transitions_from_draft(db: PgConn, to_status: str, note: str, token: str) -> None:
    result = _run(
        db,
        REGISTER_A
        + _plan_a("business")
        + f"""
        CREATE TEMP TABLE b AS SELECT (public.create_vendor_branch('{VENDOR_A}', '{OWNER_A}',
          '{_payload("Skip Review", "0970000022")}'::jsonb) ->> 'id')::uuid AS id;
        SELECT public.transition_vendor_branch((SELECT id FROM b), '{to_status}', '{ADMIN}', {note});
        """,
    )
    _err(result, token)


def test_reject_requires_a_note_and_raw_status_update_is_blocked(db: PgConn) -> None:
    online = _payload("Online Only", "0970000023", loc={}, branch_kind="online")
    base = (
        REGISTER_A
        + _plan_a("business")
        + f"""
        CREATE TEMP TABLE b AS SELECT (public.create_vendor_branch('{VENDOR_A}', '{OWNER_A}',
          '{online}'::jsonb) ->> 'id')::uuid AS id;
        SELECT public.transition_vendor_branch((SELECT id FROM b), 'pending_review', '{OWNER_A}', null);
        """
    )
    _err(
        _run(
            db,
            base
            + f"SELECT public.transition_vendor_branch((SELECT id FROM b), 'rejected', '{ADMIN}', '  ');",
        ),
        "branch_note_required",
    )
    _err(
        _run(
            db,
            base
            + "UPDATE public.vendors SET branch_status = 'approved' WHERE id = (SELECT id FROM b);",
        ),
        "branch_status changes only via transition_vendor_branch",
    )


def test_primary_branch_is_not_reviewable(db: PgConn) -> None:
    result = _run(
        db,
        f"SELECT public.transition_vendor_branch('{VENDOR_A}', 'pending_review', '{OWNER_A}', null);",
    )
    _err(result, "branch_primary_not_reviewable")


def test_dedup_scan_flags_name_phone_and_photo(db: PgConn) -> None:
    body = (
        REGISTER_A
        + _plan_a("business")
        + f"""
        UPDATE public.vendors SET contact_phone = '260975550000' WHERE id = '{VENDOR_B}';
        INSERT INTO public.vendor_branch_evidence (vendor_id, kind, storage_path, content_sha256)
          VALUES ('{VENDOR_B}', 'storefront_photo',
                  'branches/{VENDOR_B}/{VENDOR_B}/storefront_photo-1.jpg', repeat('a', 64));
        CREATE TEMP TABLE b AS SELECT (public.create_vendor_branch('{VENDOR_A}', '{OWNER_A}',
          '{_payload("Zed Fashion House", "0970000024", contact_phone="0975550000")}'::jsonb) ->> 'id')::uuid AS id;
        INSERT INTO public.vendor_branch_evidence (vendor_id, kind, storage_path, content_sha256)
          SELECT id, 'storefront_photo', 'branches/{VENDOR_A}/' || id || '/storefront_photo-1.jpg', repeat('a', 64) FROM b;
        SELECT public.vendor_branch_dedup_scan((SELECT id FROM b));
        SELECT string_agg(kind, ',' ORDER BY kind) FROM public.vendor_branch_flags
          WHERE vendor_id = (SELECT id FROM b) AND matched_vendor_id = '{VENDOR_B}' AND status = 'open';
        """
    )
    result = _run(db, body)
    assert _last(result) == "image_duplicate,name_similar,phone_match"


def test_dedup_scan_flags_other_owner_at_same_spot(db: PgConn) -> None:
    # Shop B's owner opens a stall 5 m from shop A: different owners, same plot.
    body = f"""
        INSERT INTO public.vendor_locations (vendor_id, lat, lng, landmark)
          VALUES ('{VENDOR_B}', -15.41672, 28.28332, 'East Park Mall stall');
        SELECT public.vendor_branch_dedup_scan('{VENDOR_B}');
        SELECT count(*) FROM public.vendor_branch_flags
          WHERE vendor_id = '{VENDOR_B}' AND kind = 'gps_near_other_owner'
            AND matched_vendor_id = '{VENDOR_A}';
    """
    assert _last(_run(db, body)) == "1"
