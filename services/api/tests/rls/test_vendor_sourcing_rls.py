"""Vendor sourcing hub: made-in-Zambia guard and account-erasure invariants (20261127100000).

Live Postgres, same harness as the other RLS suites.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from tests.rls.conftest import PgConn, RoleSession

VENDOR_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
LISTING_A = "b1000000-0000-0000-0000-000000000001"  # shop_a (owner 3333...)
ADMIN = "66666666-6666-6666-6666-666666666666"


@pytest.fixture(autouse=True)
def _owner_update_grant(db: PgConn) -> Iterator[None]:
    """Owners have no direct UPDATE on vendor_listings today (20261001120000).

    The guard trigger is defense in depth: it must still hold if that grant is ever
    restored, so the tests re-grant it for their own duration only.
    """
    assert db.run("GRANT UPDATE ON public.vendor_listings TO authenticated").ok
    yield
    assert db.run("REVOKE UPDATE ON public.vendor_listings FROM authenticated").ok


def _reset(db: PgConn) -> None:
    result = db.run(
        f"""
        BEGIN; SET LOCAL ROLE postgres;
        UPDATE public.vendor_listings
           SET made_in_zambia_status = NULL
         WHERE id = '{LISTING_A}';
        COMMIT;
        """
    )
    assert result.ok, result.error


def _approve(db: PgConn) -> None:
    _reset(db)
    result = db.run(
        f"""
        BEGIN; SET LOCAL ROLE postgres;
        UPDATE public.vendor_listings
           SET made_in_zambia_status = 'approved',
               made_in_zambia_reference = 'PACRA-1',
               made_in_zambia_claimed_at = timezone('utc', now()),
               made_in_zambia_reviewed_by = '{ADMIN}',
               made_in_zambia_reviewed_at = timezone('utc', now())
         WHERE id = '{LISTING_A}';
        COMMIT;
        """
    )
    assert result.ok, result.error


def _state(db: PgConn) -> list[str]:
    result = db.run(
        "SELECT made_in_zambia_status || '|' || coalesce(made_in_zambia_reference, '') || '|' "
        "|| (made_in_zambia_reviewed_by IS NOT NULL)::text "
        f"FROM public.vendor_listings WHERE id = '{LISTING_A}'"
    )
    assert result.ok, result.error
    return result.rows


def test_owner_editing_reference_after_approval_drops_claim_back_to_claimed(
    db: PgConn, as_vendor: RoleSession
) -> None:
    _approve(db)
    assert _state(db) == ["approved|PACRA-1|true"]
    result = as_vendor.execute(
        f"UPDATE public.vendor_listings SET made_in_zambia_reference = 'FORGED-2' "
        f"WHERE id = '{LISTING_A}'"
    )
    assert result.ok, result.error
    assert _state(db) == ["claimed|FORGED-2|false"]
    _reset(db)


def test_owner_editing_claimed_at_after_approval_drops_claim_back_to_claimed(
    db: PgConn, as_vendor: RoleSession
) -> None:
    _approve(db)
    result = as_vendor.execute(
        f"UPDATE public.vendor_listings SET made_in_zambia_claimed_at = now() "
        f"WHERE id = '{LISTING_A}'"
    )
    assert result.ok, result.error
    assert _state(db)[0].startswith("claimed|")
    _reset(db)


def test_owner_cannot_self_approve_or_touch_review_fields(
    db: PgConn, as_vendor: RoleSession
) -> None:
    _reset(db)
    result = as_vendor.execute(
        f"UPDATE public.vendor_listings SET made_in_zambia_status = 'approved' "
        f"WHERE id = '{LISTING_A}'"
    )
    assert not result.ok and result.sqlstate == "42501"
    _approve(db)
    result = as_vendor.execute(
        f"UPDATE public.vendor_listings SET made_in_zambia_review_note = 'looks fine' "
        f"WHERE id = '{LISTING_A}'"
    )
    assert not result.ok and result.sqlstate == "42501"
    assert _state(db) == ["approved|PACRA-1|true"]
    _reset(db)


def test_privileged_edit_of_approved_claim_keeps_approval(db: PgConn) -> None:
    _approve(db)
    result = db.run(
        "BEGIN; SET LOCAL ROLE postgres; UPDATE public.vendor_listings "
        "SET made_in_zambia_reference = 'PACRA-2' "
        f"WHERE id = '{LISTING_A}'; COMMIT;"
    )
    assert result.ok, result.error
    assert _state(db) == ["approved|PACRA-2|true"]
    _reset(db)


def test_account_erasure_is_not_blocked_by_import_requests_or_quotes(db: PgConn) -> None:
    user, req, quote = (str(uuid.uuid4()) for _ in range(3))
    result = db.run(
        f"""
        BEGIN; SET LOCAL ROLE postgres;
        INSERT INTO auth.users (id, email, created_at)
        VALUES ('{user}', '{user}@erasure.test', timezone('utc', now()));
        INSERT INTO public.import_requests (id, vendor_id, requested_by, title, quantity)
        VALUES ('{req}', '{VENDOR_A}', '{user}', 'Solar panels', 10);
        INSERT INTO public.import_request_quotes
          (id, request_id, quoted_by, product_ngwee, freight_ngwee, duty_ngwee, clearing_ngwee)
        VALUES ('{quote}', '{req}', '{user}', 100, 10, 5, 5);
        DELETE FROM auth.users WHERE id = '{user}';
        COMMIT;
        """
    )
    assert result.ok, result.error
    rows = db.run(
        "SELECT (SELECT requested_by IS NULL FROM public.import_requests "
        f"WHERE id = '{req}')::text || '|' || "
        "(SELECT quoted_by IS NULL FROM public.import_request_quotes "
        f"WHERE id = '{quote}')::text"
    )
    assert rows.rows == ["true|true"]
    db.run(f"BEGIN; DELETE FROM public.import_requests WHERE id = '{req}'; COMMIT;")
