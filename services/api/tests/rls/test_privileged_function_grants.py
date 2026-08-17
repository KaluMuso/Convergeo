"""SEC-DB-01 — SECURITY DEFINER EXECUTE grant hardening.

Proves internal trigger guards and backend-only RPCs are not invokable by anon or
authenticated roles, while intentionally public RPCs remain available.
"""

from __future__ import annotations

import pytest
from tests.rls.conftest import PgConn, RoleSession

INTERNAL_TRIGGER_GUARDS: tuple[str, ...] = (
    "clip_products_guard",
    "enquiry_threads_guard",
    "listing_location_stock_guard",
    "rfq_threads_guard",
    "storefront_collection_items_guard",
    "guard_vendor_licence_status_update",
    "guard_kyc_record_integrity",
    "validate_service_review_verified_engagement",
)

SERVICE_ROLE_ONLY_RPCS: tuple[tuple[str, str], ...] = (
    ("clip_bump_counter", "NULL::uuid, 'like_count', 1"),
    (
        "clip_record_spend",
        "'2026-08', 0::bigint, 0, 0::bigint, 1000000::bigint",
    ),
    ("reset_clip_kill_switch", "'2026-08'"),
)

VENDOR_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _client_grantees(db: PgConn, routine_name: str) -> list[str]:
    result = db.run(
        f"""
        SELECT grantee
        FROM information_schema.routine_privileges
        WHERE routine_schema = 'public'
          AND routine_name = '{routine_name}'
          AND privilege_type = 'EXECUTE'
          AND grantee IN ('anon', 'authenticated')
        ORDER BY grantee
        """
    )
    assert result.ok, result.error
    return result.rows


@pytest.mark.parametrize("routine_name", INTERNAL_TRIGGER_GUARDS)
def test_internal_trigger_guards_not_granted_to_clients(
    db: PgConn, routine_name: str
) -> None:
    assert _client_grantees(db, routine_name) == []


@pytest.mark.parametrize("routine_name, _args", SERVICE_ROLE_ONLY_RPCS)
def test_service_role_rpcs_not_granted_to_clients(
    db: PgConn, routine_name: str, _args: str
) -> None:
    assert _client_grantees(db, routine_name) == []


@pytest.mark.parametrize("routine_name, args", SERVICE_ROLE_ONLY_RPCS)
def test_anon_cannot_invoke_service_role_rpcs(
    as_anon: RoleSession, routine_name: str, args: str
) -> None:
    result = as_anon.execute(f"SELECT public.{routine_name}({args})")
    assert not result.ok
    assert result.error is not None
    assert "permission denied" in result.error.lower()


def test_anon_cannot_invoke_internal_trigger_guard(as_anon: RoleSession) -> None:
    result = as_anon.execute("SELECT public.enquiry_threads_guard()")
    assert not result.ok
    assert "permission denied" in (result.error or "").lower()


def test_public_is_verified_business_wrapper_removed(db: PgConn) -> None:
    result = db.run(
        """
        SELECT count(*)::text
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public'
          AND p.proname = 'is_verified_business'
        """
    )
    assert result.ok, result.error
    assert result.rows == ["0"]


def test_private_is_verified_business_not_client_callable(db: PgConn) -> None:
    result = db.run(
        """
        SELECT grantee
        FROM information_schema.routine_privileges
        WHERE routine_schema = 'private'
          AND routine_name = 'is_verified_business'
          AND privilege_type = 'EXECUTE'
          AND grantee IN ('anon', 'authenticated')
        """
    )
    assert result.ok, result.error
    assert result.rows == []


def test_vendor_licence_is_valid_remains_public_rpc(as_anon: RoleSession) -> None:
    """Boolean badge RPC — intentionally callable (0084)."""
    result = as_anon.execute(
        f"SELECT public.vendor_licence_is_valid('{VENDOR_A}'::uuid, 'general')"
    )
    assert result.ok, result.error


def test_vendor_follower_count_authenticated_only(
    as_anon: RoleSession, as_vendor: RoleSession
) -> None:
    denied = as_anon.execute(
        f"SELECT public.vendor_follower_count('{VENDOR_A}'::uuid)"
    )
    assert not denied.ok
    assert "permission denied" in (denied.error or "").lower()

    allowed = as_vendor.execute(
        f"SELECT public.vendor_follower_count('{VENDOR_A}'::uuid)"
    )
    assert allowed.ok, allowed.error


def test_has_role_delegator_still_callable_by_anon(as_anon: RoleSession) -> None:
    """RLS policies evaluate has_role; public wrapper is SECURITY INVOKER (60200)."""
    result = as_anon.execute("SELECT public.has_role('admin')")
    assert result.ok, result.error
    assert result.rows == ["f"]


def test_listing_line_total_ngwee_search_path_pinned(db: PgConn) -> None:
    result = db.run(
        """
        SELECT coalesce(array_to_string(p.proconfig, ','), '')
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public'
          AND p.proname = 'listing_line_total_ngwee'
        """
    )
    assert result.ok, result.error
    assert result.rows
    assert "search_path=public" in result.rows[0]


def test_search_query_facets_not_granted_to_clients(db: PgConn) -> None:
    """Backend search RPC — service_role only after 20260813160200."""
    assert _client_grantees(db, "search_query_facets") == []


def test_pg_trgm_and_vector_live_outside_public(db: PgConn) -> None:
    result = db.run(
        """
        SELECT e.extname || '=' || n.nspname
        FROM pg_extension e
        JOIN pg_namespace n ON n.oid = e.extnamespace
        WHERE e.extname IN ('pg_trgm', 'vector')
        ORDER BY e.extname
        """
    )
    assert result.ok, result.error
    if not result.rows:
        pytest.skip("pg_trgm/vector are not installed in this test database")
    for row in result.rows:
        name, schema = row.split("=", 1)
        assert schema != "public", f"{name} must not remain in public"
