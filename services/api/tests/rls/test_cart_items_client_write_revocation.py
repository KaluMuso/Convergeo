"""Grant-level regression for migration 0086 cart_items client write revocation.

The RLS matrix probes INSERT/UPDATE with DEFAULT VALUES / WHERE false. Those
prove the effective denial path but do not assert the underlying GRANT revoke
that 0086 installs (CAN-ORD-002). This module closes that gap with explicit
privilege checks and real-row DML against a customer-owned cart line.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from tests.rls.conftest import PgConn, RoleSession
from tests.rls.test_matrix import _is_permission_denied

CART_ID = "c0ffee00-0000-4000-8000-00000000c001"
CART_ITEM_ID = "c0ffee00-0000-4000-8000-00000000c002"


def _migration_0086_applied(db: PgConn) -> bool:
    result = db.run(
        """
        SELECT count(*)::int
        FROM information_schema.role_table_grants
        WHERE table_schema = 'public'
          AND table_name = 'cart_items'
          AND grantee IN ('authenticated', 'anon')
          AND privilege_type IN ('INSERT', 'UPDATE')
        """
    )
    assert result.ok, result.error
    return int(result.rows[0]) == 0


@pytest.fixture
def require_0086(db: PgConn) -> None:
    if not _migration_0086_applied(db):
        pytest.skip("migration 0086 not applied — cart_items client INSERT/UPDATE still granted")


def _seed_customer_cart(db: PgConn, *, customer_id: str, listing_id: str) -> None:
    result = db.run(
        f"""
BEGIN;
SET LOCAL role service_role;
DELETE FROM public.cart_items WHERE cart_id = '{CART_ID}';
DELETE FROM public.carts WHERE id = '{CART_ID}';
INSERT INTO public.carts (id, user_id, status)
VALUES ('{CART_ID}', '{customer_id}', 'active');
INSERT INTO public.cart_items (
  id, cart_id, listing_id, qty, unit_price_ngwee, wholesale
) VALUES (
  '{CART_ITEM_ID}', '{CART_ID}', '{listing_id}', 1, 10000, false
);
COMMIT;
"""
    )
    assert result.ok, result.error


def _cleanup_cart(db: PgConn) -> None:
    db.run(
        f"""
BEGIN;
SET LOCAL role service_role;
DELETE FROM public.cart_items WHERE cart_id = '{CART_ID}';
DELETE FROM public.carts WHERE id = '{CART_ID}';
COMMIT;
"""
    )


def test_cart_items_client_insert_update_grants_revoked(db: PgConn, require_0086: None) -> None:
    result = db.run(
        """
        SELECT grantee, privilege_type
        FROM information_schema.role_table_grants
        WHERE table_schema = 'public'
          AND table_name = 'cart_items'
          AND grantee IN ('anon', 'authenticated')
          AND privilege_type IN ('INSERT', 'UPDATE', 'SELECT', 'DELETE')
        ORDER BY grantee, privilege_type
        """
    )
    assert result.ok, result.error
    rows = {tuple(row.split("|")) for row in result.rows} if result.rows else set()
    assert ("anon", "INSERT") not in rows
    assert ("anon", "UPDATE") not in rows
    assert ("authenticated", "INSERT") not in rows
    assert ("authenticated", "UPDATE") not in rows
    assert ("authenticated", "SELECT") in rows
    assert ("authenticated", "DELETE") in rows


def test_authenticated_cannot_insert_cart_item_row(
    db: PgConn,
    as_customer: RoleSession,
    fixture_ids: dict[str, Any],
    require_0086: None,
) -> None:
    customer_id = fixture_ids["users"]["customer_a"]
    listing_id = fixture_ids["listings"]["phone_a"]
    other_listing = fixture_ids["listings"]["chitenge_b"]
    _seed_customer_cart(db, customer_id=customer_id, listing_id=listing_id)
    try:
        insert = as_customer.execute(
            f"""
INSERT INTO public.cart_items (
  id, cart_id, listing_id, qty, unit_price_ngwee, wholesale
) VALUES (
  '{uuid.uuid4()}', '{CART_ID}', '{other_listing}', 1, 1, false
)
"""
        )
        assert _is_permission_denied(insert), insert.error
        assert insert.sqlstate == "42501", insert.error
    finally:
        _cleanup_cart(db)


def test_authenticated_cannot_update_cart_item_row(
    db: PgConn,
    as_customer: RoleSession,
    fixture_ids: dict[str, Any],
    require_0086: None,
) -> None:
    customer_id = fixture_ids["users"]["customer_a"]
    listing_id = fixture_ids["listings"]["phone_a"]
    _seed_customer_cart(db, customer_id=customer_id, listing_id=listing_id)
    try:
        update = as_customer.execute(
            f"UPDATE public.cart_items SET qty = 99 WHERE id = '{CART_ITEM_ID}'"
        )
        assert _is_permission_denied(update), update.error
        assert update.sqlstate == "42501", update.error

        unchanged = db.run(
            f"SELECT qty::text FROM public.cart_items WHERE id = '{CART_ITEM_ID}'"
        )
        assert unchanged.ok and unchanged.rows == ["1"]
    finally:
        _cleanup_cart(db)


def test_authenticated_may_delete_own_cart_item_row(
    db: PgConn,
    as_customer: RoleSession,
    fixture_ids: dict[str, Any],
    require_0086: None,
) -> None:
    customer_id = fixture_ids["users"]["customer_a"]
    listing_id = fixture_ids["listings"]["phone_a"]
    _seed_customer_cart(db, customer_id=customer_id, listing_id=listing_id)
    try:
        deleted = as_customer.execute(
            f"DELETE FROM public.cart_items WHERE id = '{CART_ITEM_ID}'"
        )
        assert deleted.ok, deleted.error

        remaining = db.run(
            f"SELECT count(*)::int FROM public.cart_items WHERE id = '{CART_ITEM_ID}'"
        )
        assert remaining.ok and remaining.rows == ["0"]
    finally:
        _cleanup_cart(db)


def test_service_role_may_insert_cart_item_row(
    db: PgConn,
    fixture_ids: dict[str, Any],
    require_0086: None,
) -> None:
    customer_id = fixture_ids["users"]["customer_a"]
    listing_id = fixture_ids["listings"]["phone_a"]
    _seed_customer_cart(db, customer_id=customer_id, listing_id=listing_id)
    new_item_id = "c0ffee00-0000-4000-8000-00000000c003"
    try:
        insert = db.run(
            f"""
BEGIN;
SET LOCAL role service_role;
INSERT INTO public.cart_items (
  id, cart_id, listing_id, qty, unit_price_ngwee, wholesale
) VALUES (
  '{new_item_id}', '{CART_ID}', '{listing_id}', 2, 20000, false
);
COMMIT;
"""
        )
        assert insert.ok, insert.error

        count = db.run(
            f"SELECT count(*)::int FROM public.cart_items WHERE cart_id = '{CART_ID}'"
        )
        assert count.ok and int(count.rows[0]) >= 2
    finally:
        _cleanup_cart(db)
