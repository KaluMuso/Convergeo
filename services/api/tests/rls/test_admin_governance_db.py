"""2026-11 admin governance, database layer (D1, S5 audit trail, D4, DPA consent).

* D1 — migration 20261113163000: the legacy `admin` role reads but cannot write the
  75 tables that kept the M03 `has_role('admin')` write policies; owners keep writing.
* S5 — migration 20261113163100: audit_log is append-only for every role and records
  the actor's roles at the time of the action.
* D4 — deactivate_admin_account(): revoke every admin role, superadmin-only, audited,
  never self, never the last superadmin.
* DPA — privacy_consents is an append-only log; a courier dispatch is refused for an
  order whose customer has not consented.

These tests fail on the schema before those migrations (the D1 down script in
docs/audit/2026-11-analytics-rbac/d1-down.sql restores it for that check).
"""

from __future__ import annotations

import uuid

import pytest
from tests.rls.conftest import PgConn, RoleSession

PERMISSION_DENIED = "42501"

# The tables the founder named for D1, plus representative config tables.
D1_TABLES: tuple[str, ...] = (
    "orders",
    "order_items",
    "invoices",
    "invoice_counters",
    "kyc_records",
    "vendors",
    "disputes",
    "tickets",
    "profiles",
    "addresses",
    "platform_config",
    "feature_flags",
    "commission_rates",
    "delivery_zones",
    "categories",
    "prohibited_categories",
)

# The fixture admin persona is also a customer with its own profile and owns a vendor;
# owner self-service is legitimate, so the probes look only at other people's rows.
NOT_OWN_ROWS: dict[str, str] = {
    "profiles": "id <> '66666666-6666-6666-6666-666666666666'",
    "vendors": "owner_user_id <> '66666666-6666-6666-6666-666666666666'",
    "addresses": "user_id <> '66666666-6666-6666-6666-666666666666'",
}

ADMIN_UID = "66666666-6666-6666-6666-666666666666"
CUSTOMER_UID = "11111111-1111-1111-1111-111111111111"
PAID_ORDER = "c2000000-0000-0000-0000-000000000001"


@pytest.mark.parametrize("table", D1_TABLES)
def test_admin_still_reads(as_admin: RoleSession, table: str) -> None:
    result = as_admin.execute(f"SELECT count(*)::int FROM public.{table}")
    assert result.ok, f"{table}: admin read must keep working: {result.error}"


@pytest.mark.parametrize("table", D1_TABLES)
@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO public.{table} DEFAULT VALUES",
        "UPDATE public.{table} SET {column} = {column} WHERE {scope}",
        "DELETE FROM public.{table} WHERE {scope}",
    ],
    ids=["insert", "update", "delete"],
)
def test_admin_cannot_write(as_admin: RoleSession, db: PgConn, table: str, statement: str) -> None:
    column = db.run(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' "
        f"AND table_name = '{table}' ORDER BY ordinal_position LIMIT 1"
    )
    assert column.ok and column.rows, column.error
    scope = NOT_OWN_ROWS.get(table, "true")
    digest = (
        "SELECT md5(coalesce(string_agg(t::text, ',' ORDER BY t::text), '')) "
        f"FROM public.{table} t WHERE {scope}"
    )
    before = db.run(digest)
    result = as_admin.execute(statement.format(table=table, column=column.rows[0], scope=scope))
    after = db.run(digest)
    # Either a hard permission error, or RLS filtered every row: nothing changed.
    if result.ok:
        assert statement.startswith(("UPDATE", "DELETE")), f"{table}: admin insert succeeded"
    else:
        assert result.sqlstate in {PERMISSION_DENIED, "23502", "23514"} or (
            "row-level security" in (result.error or "")
        ), f"{table}: {result.sqlstate} {result.error}"
    assert before.rows == after.rows, f"{table}: admin changed rows through a browser token"


def test_no_public_policy_grants_an_admin_write(db: PgConn) -> None:
    leftover = db.run(
        "SELECT tablename || '.' || policyname FROM pg_policies "
        "WHERE schemaname = 'public' AND cmd <> 'SELECT' "
        "AND (coalesce(qual, '') || coalesce(with_check, '')) ~ 'has_role\\(''admin'''"
    )
    assert leftover.ok, leftover.error
    assert leftover.rows == []


@pytest.mark.parametrize(
    "table", ("orders", "invoices", "invoice_counters", "kyc_records", "tickets")
)
def test_dead_client_write_grants_are_revoked(db: PgConn, table: str) -> None:
    for role in ("anon", "authenticated"):
        for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE"):
            held = db.run(
                f"SELECT has_table_privilege('{role}', 'public.{table}', '{privilege}')::int"
            )
            assert held.ok and held.rows == ["0"], f"{role} still holds {privilege} on {table}"
    held = db.run(f"SELECT has_table_privilege('service_role', 'public.{table}', 'INSERT')::int")
    assert held.ok and held.rows == ["1"], f"service_role lost INSERT on {table}"


def test_owner_writes_survive(as_customer: RoleSession) -> None:
    """Customer self-service through owner policies is untouched by D1."""
    profile = as_customer.execute(
        f"UPDATE public.profiles SET display_name = display_name WHERE id = '{CUSTOMER_UID}' "
        "RETURNING id"
    )
    assert profile.ok, profile.error
    address = as_customer.execute(
        "UPDATE public.addresses SET landmark = landmark "
        f"WHERE user_id = '{CUSTOMER_UID}' RETURNING id"
    )
    assert address.ok, address.error


def test_admin_cannot_rewrite_an_order_status(as_admin: RoleSession, db: PgConn) -> None:
    before = db.run(f"SELECT status FROM public.orders WHERE id = '{PAID_ORDER}'")
    result = as_admin.execute(
        f"UPDATE public.orders SET status = 'delivered' WHERE id = '{PAID_ORDER}'"
    )
    assert not result.ok and result.sqlstate == PERMISSION_DENIED, result.error
    after = db.run(f"SELECT status FROM public.orders WHERE id = '{PAID_ORDER}'")
    assert before.rows == after.rows


# ---------------------------------------------------------------------------
# S5 — audit_log append-only + role at time of action
# ---------------------------------------------------------------------------


def test_audit_log_fills_actor_roles_and_refuses_rewrites(db: PgConn) -> None:
    marker = f"test.governance.{uuid.uuid4().hex[:12]}"
    inserted = db.run(
        "INSERT INTO public.audit_log (actor, action, entity_type) "
        f"VALUES ('{ADMIN_UID}', '{marker}', 'test') RETURNING array_to_string(actor_roles, ',')"
    )
    assert inserted.ok, inserted.error
    assert "admin" in inserted.rows[0].split(","), inserted.rows
    outcome = db.run(f"SELECT outcome FROM public.audit_log WHERE action = '{marker}'")
    assert outcome.rows == ["success"]
    for statement in (
        f"UPDATE public.audit_log SET reason = 'x' WHERE action = '{marker}'",
        f"DELETE FROM public.audit_log WHERE action = '{marker}'",
        "TRUNCATE public.audit_log",
    ):
        refused = db.run(statement)  # superuser: only the trigger stands in the way
        assert not refused.ok and refused.sqlstate == PERMISSION_DENIED, statement
    still = db.run(f"SELECT count(*)::int FROM public.audit_log WHERE action = '{marker}'")
    assert still.rows == ["1"]


def test_audit_log_outcome_is_constrained(db: PgConn) -> None:
    bad = db.run(
        "INSERT INTO public.audit_log (action, entity_type, outcome) "
        "VALUES ('test.bad', 'test', 'maybe')"
    )
    assert not bad.ok and bad.sqlstate == "23514"


def test_service_role_cannot_rewrite_audit_rows(db: PgConn) -> None:
    for privilege in ("UPDATE", "DELETE", "TRUNCATE"):
        held = db.run(
            f"SELECT has_table_privilege('service_role', 'public.audit_log', '{privilege}')::int"
        )
        assert held.ok and held.rows == ["0"], privilege


# ---------------------------------------------------------------------------
# D4 — deactivate = revoke every admin role
# ---------------------------------------------------------------------------


def _with_users(db: PgConn, script: str) -> list[str]:
    """Run inside one rolled-back transaction with two throwaway operators."""
    result = db.run_script(
        "BEGIN;\n"
        "INSERT INTO auth.users (id) VALUES "
        "('a1000000-0000-0000-0000-0000000000a1'), ('a1000000-0000-0000-0000-0000000000a2');\n"
        "INSERT INTO public.user_roles (user_id, role) VALUES "
        "('a1000000-0000-0000-0000-0000000000a1', 'superadmin'), "
        "('a1000000-0000-0000-0000-0000000000a2', 'admin'), "
        "('a1000000-0000-0000-0000-0000000000a2', 'moderator') ON CONFLICT DO NOTHING;\n"
        f"{script}\nROLLBACK;\n"
    )
    assert result.ok, result.error
    return _values(result.rows)


def _values(rows: list[str]) -> list[str]:
    """Drop psql command tags (BEGIN, INSERT 0 1, ROLLBACK…) from a script's output."""
    tags = ("BEGIN", "ROLLBACK", "COMMIT", "INSERT ", "UPDATE ", "DELETE ", "SELECT ")
    return [row for row in rows if not row.startswith(tags)]


def test_deactivate_revokes_every_admin_role_and_audits(db: PgConn) -> None:
    rows = _with_users(
        db,
        "SELECT public.deactivate_admin_account('a1000000-0000-0000-0000-0000000000a1', "
        "'a1000000-0000-0000-0000-0000000000a2', 'left the company', 'req-1')::text;\n"
        "SELECT string_agg(role, ',' ORDER BY role) FROM public.user_roles "
        "WHERE user_id = 'a1000000-0000-0000-0000-0000000000a2';\n"
        "SELECT action || '|' || outcome || '|' || reason || '|' || request_id "
        "FROM public.audit_log WHERE entity_id = 'a1000000-0000-0000-0000-0000000000a2' "
        "AND action = 'admin.account.deactivate';",
    )
    assert '"revoked": ["admin", "moderator"]' in rows[-3]
    assert rows[-2] == "customer"  # customer access is kept; only admin roles go
    assert rows[-1] == "admin.account.deactivate|success|left the company|req-1"


@pytest.mark.parametrize(
    "actor,target,reason,sqlstate",
    [
        # a non-superadmin actor
        ("a1000000-0000-0000-0000-0000000000a2", "a1000000-0000-0000-0000-0000000000a1",
         "takeover", "42501"),
        # self-deactivation
        ("a1000000-0000-0000-0000-0000000000a1", "a1000000-0000-0000-0000-0000000000a1",
         "oops", "22023"),
        # missing reason
        ("a1000000-0000-0000-0000-0000000000a1", "a1000000-0000-0000-0000-0000000000a2",
         "", "22023"),
    ],
)  # fmt: skip
def test_deactivate_refusals(
    db: PgConn, actor: str, target: str, reason: str, sqlstate: str
) -> None:
    result = db.run(
        "BEGIN; "
        "INSERT INTO auth.users (id) VALUES "
        "('a1000000-0000-0000-0000-0000000000a1'), ('a1000000-0000-0000-0000-0000000000a2'); "
        "INSERT INTO public.user_roles (user_id, role) VALUES "
        "('a1000000-0000-0000-0000-0000000000a1', 'superadmin'), "
        "('a1000000-0000-0000-0000-0000000000a2', 'admin'); "
        f"SELECT public.deactivate_admin_account('{actor}', '{target}', '{reason}'); "
        "ROLLBACK;"
    )
    assert not result.ok and result.sqlstate == sqlstate, result.error


def test_deactivate_is_not_callable_by_clients(db: PgConn) -> None:
    for role in ("anon", "authenticated"):
        held = db.run(
            f"SELECT has_function_privilege('{role}', "
            "'public.deactivate_admin_account(uuid, uuid, text, text)', 'execute')::int"
        )
        assert held.ok and held.rows == ["0"], role


def test_last_superadmin_cannot_be_deactivated(db: PgConn) -> None:
    # Two superadmins exist only long enough for one to deactivate the other; then the
    # survivor is the last one and the trigger refuses a second removal path.
    result = db.run(
        "BEGIN; "
        "DELETE FROM public.user_roles WHERE role = 'superadmin'; "
        "INSERT INTO auth.users (id) VALUES "
        "('a1000000-0000-0000-0000-0000000000a1'), ('a1000000-0000-0000-0000-0000000000a2'); "
        "INSERT INTO public.user_roles (user_id, role) VALUES "
        "('a1000000-0000-0000-0000-0000000000a1', 'superadmin'), "
        "('a1000000-0000-0000-0000-0000000000a2', 'superadmin'); "
        "SELECT public.deactivate_admin_account('a1000000-0000-0000-0000-0000000000a1', "
        "'a1000000-0000-0000-0000-0000000000a2', 'rotation'); "
        "DELETE FROM public.user_roles WHERE user_id = 'a1000000-0000-0000-0000-0000000000a1'; "
        "ROLLBACK;"
    )
    assert not result.ok and result.sqlstate == "23514", result.error
    assert "last superadmin" in (result.error or "")


# ---------------------------------------------------------------------------
# DPA — delivery-partner consent
# ---------------------------------------------------------------------------


def test_latest_consent_row_wins_and_history_is_append_only(db: PgConn) -> None:
    result = db.run_script(
        "BEGIN;\n"
        "INSERT INTO public.privacy_consents (user_id, purpose, version, granted, source, "
        f"recorded_at) VALUES ('{CUSTOMER_UID}', 'delivery_partner_share', '2026-11-13', "
        "true, 'checkout', now() - interval '1 hour');\n"
        f"SELECT public.has_delivery_partner_consent('{CUSTOMER_UID}')::text;\n"
        "INSERT INTO public.privacy_consents (user_id, purpose, version, granted, source) "
        f"VALUES ('{CUSTOMER_UID}', 'delivery_partner_share', '2026-11-13', false, "
        "'settings');\n"
        f"SELECT public.has_delivery_partner_consent('{CUSTOMER_UID}')::text;\n"
        "ROLLBACK;\n"
    )
    assert result.ok, result.error
    assert _values(result.rows) == ["true", "false"]
    refused = db.run(
        "BEGIN; "
        "INSERT INTO public.privacy_consents (user_id, purpose, version, granted, source) "
        f"VALUES ('{CUSTOMER_UID}', 'delivery_partner_share', '2026-11-13', true, "
        "'settings'); "
        f"UPDATE public.privacy_consents SET granted = false WHERE user_id = '{CUSTOMER_UID}'; "
        "ROLLBACK;"
    )
    assert not refused.ok and refused.sqlstate == PERMISSION_DENIED, refused.error


def test_customer_reads_only_own_consents_and_cannot_write(
    as_customer: RoleSession, as_other_customer: RoleSession
) -> None:
    write = as_customer.execute(
        "INSERT INTO public.privacy_consents (user_id, purpose, version, granted, source) "
        f"VALUES ('{CUSTOMER_UID}', 'delivery_partner_share', '2026-11-13', true, 'settings')"
    )
    assert not write.ok and write.sqlstate == PERMISSION_DENIED
    other = as_other_customer.execute(
        f"SELECT count(*)::int FROM public.privacy_consents WHERE user_id = '{CUSTOMER_UID}'"
    )
    assert other.ok and other.rows[-1] == "0"


def test_dispatch_refused_without_consent(db: PgConn) -> None:
    result = db.run(
        "BEGIN; "
        "INSERT INTO public.dispatch_requests (order_id, courier_partner_id) "
        f"VALUES ('{PAID_ORDER}', gen_random_uuid()); "
        "ROLLBACK;"
    )
    assert not result.ok and result.sqlstate == "23514", result.error
    assert "has not consented" in (result.error or "")


def test_dispatch_trigger_passes_with_consent(db: PgConn) -> None:
    """With consent the consent trigger lets the row through to the next check (the
    random courier id then fails its foreign key, proving the trigger did not refuse)."""
    customer = db.run(f"SELECT customer_id FROM public.orders WHERE id = '{PAID_ORDER}'")
    assert customer.ok and customer.rows, customer.error
    result = db.run(
        "BEGIN; "
        "INSERT INTO public.privacy_consents (user_id, purpose, version, granted, source) "
        f"VALUES ('{customer.rows[-1]}', 'delivery_partner_share', '2026-11-13', true, "
        "'checkout'); "
        "INSERT INTO public.dispatch_requests (order_id, courier_partner_id) "
        f"VALUES ('{PAID_ORDER}', gen_random_uuid()); "
        "ROLLBACK;"
    )
    assert not result.ok and result.sqlstate == "23503", result.error
