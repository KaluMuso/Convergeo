"""Trigger test for the orders.commission_snapshot immutability guard (migration 0069).

commission_snapshot is the purchase-time commission basis and the sole input to
release/payout math. It is written once on the order INSERT and never updated. The
0069 BEFORE UPDATE trigger freezes it for every application role (service_role and
admin included) so the commission basis can never be silently rewritten; only the DB
owner / superuser keeps an escape hatch.

Since 20261113163000 (2026-11 RBAC D1) no browser token can UPDATE orders at all —
`admin` lost orders_admin_all and the dead UPDATE grant — so the trigger is proved
with the API's own writer, `service_role`, and admin is checked at the privilege layer.

DB-backed (mirrors the RLS matrix harness); skips when Postgres is unavailable.
"""

from __future__ import annotations

from typing import Any

from tests.rls.conftest import PgConn, RoleSession


def _snapshot(db: PgConn, order_id: str) -> str | None:
    result = db.run(f"SELECT commission_snapshot::text FROM public.orders WHERE id = '{order_id}'")
    return result.rows[0] if result.ok and result.rows else None


def test_commission_snapshot_is_immutable_for_app_roles(
    db: PgConn,
    as_admin: RoleSession,
    fixture_ids: dict[str, Any],
) -> None:
    order_id = fixture_ids["orders"]["paid"]
    original = _snapshot(db, order_id)
    assert original is not None, "fixture order should exist"

    try:
        # D1: an admin browser token holds no UPDATE on orders at all.
        tamper = as_admin.execute(
            f"UPDATE public.orders SET commission_snapshot = '{{\"tampered\": true}}'::jsonb "
            f"WHERE id = '{order_id}'"
        )
        assert not tamper.ok, "admin must not be able to rewrite commission_snapshot"
        assert tamper.sqlstate == "42501", tamper.error
        assert _snapshot(db, order_id) == original, "snapshot must be unchanged after the block"

        # The 0069 guard still fires for the privileged app writer (service_role).
        service = db.run(
            "BEGIN; SET LOCAL ROLE service_role; "
            "DO $$ BEGIN PERFORM set_config('request.jwt.claims', "
            '\'{"role": "service_role"}\', true); END $$; '
            f"UPDATE public.orders SET commission_snapshot = '{{\"tampered\": true}}'::jsonb "
            f"WHERE id = '{order_id}'; ROLLBACK;"
        )
        assert not service.ok, "service_role must not be able to rewrite commission_snapshot"
        assert "immutable" in (service.error or ""), service.error
        assert _snapshot(db, order_id) == original

        # The DB owner / superuser keeps an escape hatch (migrations, audited fixes).
        owner_fix = db.run(
            "BEGIN; "
            f"UPDATE public.orders SET commission_snapshot = '{{\"corrected\": true}}'::jsonb "
            f"WHERE id = '{order_id}'; "
            "COMMIT;"
        )
        assert owner_fix.ok, f"owner correction should pass the guard: {owner_fix.error}"
        assert _snapshot(db, order_id) == '{"corrected": true}'
    finally:
        # Restore the shared fixture row for other tests in the session-scoped DB.
        db.run(
            f"BEGIN; UPDATE public.orders SET commission_snapshot = '{original}'::jsonb "
            f"WHERE id = '{order_id}'; COMMIT;"
        )
