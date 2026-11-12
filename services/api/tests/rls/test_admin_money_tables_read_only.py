"""Administrators read the money tables; only the service role writes them.

2026-11 analytics/RBAC audit, finding S1. Before migration
20261113100000_admin_money_tables_read_only.sql, a user holding the `admin` role could
use their own browser token against PostgREST to insert a balanced ledger transaction,
delete ledger accounts, or rewrite payment, payout and refund rows — bypassing the API's
state machines, payout guards and audit_log. This suite fails on that earlier schema.
"""

from __future__ import annotations

import pytest
from tests.rls.conftest import PgConn, RoleSession

MONEY_TABLES: tuple[str, ...] = (
    "ledger_accounts",
    "ledger_transactions",
    "ledger_postings",
    "payments",
    "payouts",
    "refunds",
)
WRITE_PRIVILEGES: tuple[str, ...] = ("INSERT", "UPDATE", "DELETE", "TRUNCATE")
PERMISSION_DENIED = "42501"


@pytest.mark.parametrize("table", MONEY_TABLES)
def test_admin_can_still_read(as_admin: RoleSession, table: str) -> None:
    result = as_admin.execute(f"SELECT count(*)::int FROM public.{table}")
    assert result.ok, f"{table}: admin read must keep working: {result.error}"


@pytest.mark.parametrize("table", MONEY_TABLES)
@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO public.{table} DEFAULT VALUES",
        "UPDATE public.{table} SET id = id",
        "DELETE FROM public.{table}",
    ],
    ids=["insert", "update", "delete"],
)
def test_admin_cannot_write(as_admin: RoleSession, table: str, statement: str) -> None:
    result = as_admin.execute(statement.format(table=table))
    assert not result.ok, f"{table}: admin write unexpectedly succeeded"
    assert result.sqlstate == PERMISSION_DENIED, f"{table}: {result.sqlstate} {result.error}"


def test_admin_cannot_fabricate_a_balanced_ledger_transaction(
    as_admin: RoleSession, db: PgConn
) -> None:
    """The exact move executed during the audit: a zero-sum pair passes the ledger
    trigger, so only the privilege layer stands between an admin token and the books."""
    before = db.run("SELECT count(*)::int FROM public.ledger_transactions")
    assert before.ok, before.error
    result = as_admin.execute(
        """
        WITH t AS (
          INSERT INTO public.ledger_transactions (kind, idempotency_key)
          VALUES ('escrow_release', 'rbac-audit-s1-probe') RETURNING id
        ),
        a AS (
          SELECT id, row_number() OVER (ORDER BY id) AS rn
          FROM public.ledger_accounts LIMIT 2
        )
        INSERT INTO public.ledger_postings (transaction_id, account_id, amount_ngwee)
        SELECT t.id, a.id, CASE a.rn WHEN 1 THEN 100000 ELSE -100000 END FROM t, a
        """
    )
    assert not result.ok and result.sqlstate == PERMISSION_DENIED, result.error
    after = db.run("SELECT count(*)::int FROM public.ledger_transactions")
    assert after.ok and after.rows == before.rows


@pytest.mark.parametrize("table", MONEY_TABLES)
def test_catalogue_shape(db: PgConn, table: str) -> None:
    policies = db.run(
        "SELECT policyname || '|' || cmd FROM pg_policies "
        f"WHERE schemaname = 'public' AND tablename = '{table}' "
        "AND policyname LIKE '%\\_admin\\_%' ORDER BY 1"
    )
    assert policies.ok, policies.error
    assert policies.rows == [f"{table}_admin_select|SELECT"], policies.rows

    for role in ("anon", "authenticated"):
        for privilege in WRITE_PRIVILEGES:
            held = db.run(
                f"SELECT has_table_privilege('{role}', 'public.{table}', '{privilege}')::int"
            )
            assert held.ok, held.error
            assert held.rows == ["0"], f"{role} still holds {privilege} on {table}"

    # The API's writer is untouched.
    for privilege in ("SELECT", "INSERT", "UPDATE"):
        held = db.run(
            f"SELECT has_table_privilege('service_role', 'public.{table}', '{privilege}')::int"
        )
        assert held.ok and held.rows == ["1"], f"service_role lost {privilege} on {table}"
