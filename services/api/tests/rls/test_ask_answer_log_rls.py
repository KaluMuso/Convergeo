"""Ask Vergeo answer log + findings — RLS (20261127090000).

Live Postgres (``supabase db reset`` first), same harness as the other RLS suites.
Admins read every answer and finding; a customer reads only their own answers and no
findings; nobody but the service role can write.
"""

from __future__ import annotations

import uuid
from typing import Any

from tests.rls.conftest import PgConn, RoleSession


def _seed(db: PgConn, *, owner: str) -> tuple[str, str]:
    answer_id, finding_id = str(uuid.uuid4()), str(uuid.uuid4())
    result = db.run(
        f"""
        BEGIN;
        INSERT INTO public.ask_answers (id, user_id, query, answer_text, source)
        VALUES ('{answer_id}', '{owner}', 'pixel', 'Pixel for K5', 'ai');
        INSERT INTO public.ask_answer_findings (id, answer_id, rule, severity, reason)
        VALUES ('{finding_id}', '{answer_id}', 'price_below_category_floor', 'critical', 'cheap');
        COMMIT;
        """
    )
    assert result.ok, result.error
    return answer_id, finding_id


def _cleanup(db: PgConn, answer_id: str) -> None:
    db.run(f"BEGIN; DELETE FROM public.ask_answers WHERE id = '{answer_id}'; COMMIT;")


def test_both_tables_force_rls(db: PgConn) -> None:
    for table in ("ask_answers", "ask_answer_findings"):
        result = db.run(
            f"SELECT relforcerowsecurity FROM pg_class WHERE oid = 'public.{table}'::regclass"
        )
        assert result.ok and result.rows == ["t"], table


def test_customer_reads_only_their_own_answers(
    db: PgConn,
    as_customer: RoleSession,
    as_other_customer: RoleSession,
    fixture_ids: dict[str, Any],
) -> None:
    answer_id, _ = _seed(db, owner=fixture_ids["users"]["customer_a"])
    try:
        mine = as_customer.execute(f"SELECT id FROM public.ask_answers WHERE id = '{answer_id}'")
        theirs = as_other_customer.execute(
            f"SELECT id FROM public.ask_answers WHERE id = '{answer_id}'"
        )
        assert mine.ok and mine.rows == [answer_id]
        assert theirs.ok and theirs.rows == []
    finally:
        _cleanup(db, answer_id)


def test_admin_reads_every_answer_and_finding_but_customers_see_no_findings(
    db: PgConn,
    as_admin: RoleSession,
    as_customer: RoleSession,
    fixture_ids: dict[str, Any],
) -> None:
    answer_id, finding_id = _seed(db, owner=fixture_ids["users"]["customer_a"])
    try:
        answers = as_admin.execute(f"SELECT id FROM public.ask_answers WHERE id = '{answer_id}'")
        findings = as_admin.execute(
            f"SELECT id FROM public.ask_answer_findings WHERE id = '{finding_id}'"
        )
        own_findings = as_customer.execute(
            f"SELECT id FROM public.ask_answer_findings WHERE id = '{finding_id}'"
        )
        assert answers.ok and answers.rows == [answer_id]
        assert findings.ok and findings.rows == [finding_id]
        assert own_findings.ok and own_findings.rows == []
    finally:
        _cleanup(db, answer_id)


def test_clients_cannot_write_answers_or_findings(
    db: PgConn, as_customer: RoleSession, as_admin: RoleSession, fixture_ids: dict[str, Any]
) -> None:
    owner = fixture_ids["users"]["customer_a"]
    for session in (as_customer, as_admin):
        insert = session.execute(
            "INSERT INTO public.ask_answers (user_id, query, answer_text, source) "
            f"VALUES ('{owner}', 'q', 'a', 'ai')"
        )
        assert not insert.ok, "client INSERT into ask_answers must be denied"
    answer_id, finding_id = _seed(db, owner=owner)
    try:
        for session in (as_customer, as_admin):
            update = session.execute(
                f"UPDATE public.ask_answers SET audit_status = 'passed' WHERE id = '{answer_id}'"
            )
            delete = session.execute(
                f"DELETE FROM public.ask_answer_findings WHERE id = '{finding_id}'"
            )
            assert not update.ok and not delete.ok
    finally:
        _cleanup(db, answer_id)


def test_flagging_an_answer_notifies_admins_once(db: PgConn, fixture_ids: dict[str, Any]) -> None:
    answer_id, _ = _seed(db, owner=fixture_ids["users"]["customer_a"])
    try:
        flagged = db.run(
            f"""
            BEGIN;
            UPDATE public.ask_answers SET audit_status = 'flagged', audit_severity = 'critical'
              WHERE id = '{answer_id}';
            UPDATE public.ask_answers SET audit_severity = 'critical' WHERE id = '{answer_id}';
            COMMIT;
            """
        )
        assert flagged.ok, flagged.error
        count = db.run(
            "SELECT count(*) FROM public.in_app_notifications "
            f"WHERE dedupe_key = 'ask_answer_flagged:{answer_id}' AND audience = 'admin' "
            "GROUP BY recipient_user_id HAVING count(*) > 1"
        )
        assert count.ok and count.rows == []
        any_row = db.run(
            "SELECT count(*) > 0 FROM public.in_app_notifications "
            f"WHERE dedupe_key = 'ask_answer_flagged:{answer_id}' AND link_path = '/ask-audit'"
        )
        assert any_row.ok and any_row.rows == ["t"]
    finally:
        db.run(
            f"BEGIN; DELETE FROM public.in_app_notifications "
            f"WHERE dedupe_key = 'ask_answer_flagged:{answer_id}'; COMMIT;"
        )
        _cleanup(db, answer_id)
