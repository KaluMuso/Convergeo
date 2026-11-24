# ruff: noqa: E501  (inline SQL statements read better unwrapped)
"""Real-Postgres checks for T8 social contacts (20261124120000_social_contacts.sql).

Runs only against a disposable migrated LOCAL database with
SOCIAL_CONTACTS_ISOLATED_DB=1 (e.g.
SUPABASE_DB_URL=postgresql://postgres:postgres@127.0.0.1:5432/vergeo5_social_test).
State is set up through the definer functions as the service role (committed);
reads and refusals are asserted as a real RLS-bound `authenticated` session.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from urllib.parse import urlparse

import pytest
from tests.rls.conftest import (
    PERSONA_UIDS,
    Persona,
    PgConn,
    SqlResult,
    apply_migrations,
    ensure_roles,
    grant_tester_access,
    schema_ready,
    seed_matrix_fixtures,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("SOCIAL_CONTACTS_ISOLATED_DB") != "1",
    reason="Disposable DB attestation required (SOCIAL_CONTACTS_ISOLATED_DB=1)",
)

ALICE = str(PERSONA_UIDS[Persona.CUSTOMER])
BOB = str(PERSONA_UIDS[Persona.OTHER_CUSTOMER])
CAROL = str(PERSONA_UIDS[Persona.VENDOR])
DAVE = str(PERSONA_UIDS[Persona.OTHER_VENDOR])
USERS = (ALICE, BOB, CAROL, DAVE)


@pytest.fixture(scope="module")
def db() -> Generator[PgConn, None, None]:
    url = os.environ.get("SUPABASE_DB_URL", "postgresql:///vergeo5_social_test")
    assert urlparse(url).hostname in {"127.0.0.1", "localhost", "::1", None}, "Local DB only"
    conn = PgConn(url)
    assert conn.run("SELECT 1").ok, "Actual PostgreSQL is required"
    ensure_roles(conn)
    if not schema_ready(conn):
        apply_migrations(conn)
    grant_tester_access(conn)
    seed_matrix_fixtures(conn)
    yield conn


SERVICE_ROLE = (
    "DO $$ BEGIN PERFORM set_config('request.jwt.claims', '{\"role\":\"service_role\"}', false); "
    "END $$; "
)


def _svc(db: PgConn, sql: str) -> SqlResult:
    """Run as the API does: service-role JWT claims."""
    result = db.run(SERVICE_ROLE + sql)
    result.rows = [row for row in result.rows if row != "DO"]
    return result


def _one(db: PgConn, sql: str) -> str:
    result = _svc(db, sql)
    assert result.ok, result.error
    assert result.rows, sql
    return result.rows[0]


def _as(db: PgConn, user_id: str, sql: str) -> SqlResult:
    return db.run_as("authenticated", sql, user_id=user_id)


def _handle() -> str:
    return "t8_" + uuid.uuid4().hex[:12]


@pytest.fixture
def social(db: PgConn) -> dict[str, str]:
    """Clean slate for the four persona users, flag ON, fresh handles."""
    users = ", ".join(f"'{u}'" for u in USERS)
    handles = {u: _handle() for u in USERS}
    values = ", ".join(f"('{u}', '{h}')" for u, h in handles.items())
    result = db.run(
        f"DELETE FROM public.chat_threads WHERE user_a IN ({users}) OR user_b IN ({users}); "
        f"DELETE FROM public.contacts WHERE user_a IN ({users}) OR user_b IN ({users}); "
        f"DELETE FROM public.contact_requests WHERE from_user IN ({users}) OR to_user IN ({users}); "
        f"DELETE FROM public.contact_blocks WHERE blocker IN ({users}) OR blocked IN ({users}); "
        f"DELETE FROM public.phone_discovery WHERE user_id IN ({users}); "
        f"DELETE FROM public.user_handles WHERE user_id IN ({users}); "
        f"INSERT INTO public.user_handles (user_id, handle) VALUES {values}; "
        f"UPDATE public.profiles SET contact_requests_from = 'everyone' WHERE id IN ({users}); "
        "UPDATE public.feature_flags SET enabled = true WHERE flag = 'social_contacts';"
    )
    assert result.ok, result.error
    return handles


def _request(db: PgConn, sender: str, to_handle: str, note: str = "hi") -> SqlResult:
    return _svc(
        db,
        f"SELECT request_id::text || '|' || status FROM public.send_contact_request('{to_handle}', '{note}', '{sender}')",
    )


def _connect(db: PgConn, handles: dict[str, str], a: str, b: str) -> str:
    """a requests b, b accepts; returns the chat thread id."""
    sent = _request(db, a, handles[b])
    assert sent.ok, sent.error
    request_id = sent.rows[0].split("|")[0]
    return _one(
        db,
        f"SELECT thread_id::text FROM public.respond_contact_request('{request_id}', 'accept', '{b}')",
    )


def _send(db: PgConn, sender: str, thread: str, body: str = "hello") -> SqlResult:
    return _svc(
        db,
        f"SELECT message_id::text FROM public.send_chat_message('{thread}', 'text', '{body}', NULL, '{sender}')",
    )


def test_flag_seeded_off_and_tables_force_rls(db: PgConn) -> None:
    for table in (
        "user_handles",
        "contact_requests",
        "contacts",
        "contact_blocks",
        "chat_threads",
        "chat_messages",
        "phone_discovery",
    ):
        assert (
            _one(
                db,
                f"SELECT (relrowsecurity AND relforcerowsecurity)::text FROM pg_class WHERE oid = 'public.{table}'::regclass",
            )
            == "true"
        )
        for verb in ("insert", "update", "delete"):
            for role in ("anon", "authenticated"):
                assert (
                    _one(
                        db,
                        f"SELECT has_table_privilege('{role}', 'public.{table}', '{verb}')::text",
                    )
                    == "false"
                ), (table, role, verb)


def test_functions_disabled_while_flag_off(db: PgConn, social: dict[str, str]) -> None:
    assert db.run(
        "UPDATE public.feature_flags SET enabled = false WHERE flag = 'social_contacts'"
    ).ok
    refused = _request(db, ALICE, social[BOB])
    assert not refused.ok
    assert "social:disabled" in (refused.error or "")


def test_end_to_end_accept_creates_contact_and_thread(db: PgConn, social: dict[str, str]) -> None:
    thread = _connect(db, social, ALICE, BOB)
    assert _send(db, ALICE, thread).ok
    seen = _as(db, BOB, f"SELECT count(*) FROM public.chat_messages WHERE thread_id = '{thread}';")
    assert seen.ok, seen.error
    assert seen.rows == ["1"]
    contacts = _as(db, ALICE, "SELECT count(*) FROM public.contacts;")
    assert contacts.rows == ["1"]


def test_non_party_cannot_read_thread_or_messages(db: PgConn, social: dict[str, str]) -> None:
    thread = _connect(db, social, ALICE, BOB)
    assert _send(db, ALICE, thread).ok
    for table, column in (("chat_threads", "id"), ("chat_messages", "thread_id")):
        result = _as(db, CAROL, f"SELECT count(*) FROM public.{table} WHERE {column} = '{thread}';")
        assert result.ok, result.error
        assert result.rows == ["0"], table
    requests = _as(
        db, CAROL, f"SELECT count(*) FROM public.contact_requests WHERE from_user = '{ALICE}';"
    )
    assert requests.rows == ["0"]
    # A non-party cannot post into the thread either, even through the function.
    intruder = _as(
        db, CAROL, f"SELECT public.send_chat_message('{thread}', 'text', 'hey', NULL, NULL);"
    )
    assert not intruder.ok
    assert "social:not_found" in (intruder.error or "")


def test_user_jwt_cannot_act_for_someone_else(db: PgConn, social: dict[str, str]) -> None:
    result = _as(db, CAROL, f"SELECT public.send_contact_request('{social[BOB]}', 'x', '{ALICE}');")
    assert not result.ok
    assert "social:actor_mismatch" in (result.error or "")


def test_message_after_block_fails_both_ways(db: PgConn, social: dict[str, str]) -> None:
    thread = _connect(db, social, ALICE, BOB)
    assert _send(db, ALICE, thread).ok
    _one(db, f"SELECT public.block_user('{ALICE}', '{BOB}')::text")
    for sender in (ALICE, BOB):
        refused = _send(db, sender, thread)
        assert not refused.ok
        assert "social:not_contact" in (refused.error or "")
    # Hidden from both parties while blocked; the contact is gone.
    for viewer in (ALICE, BOB):
        hidden = _as(
            db, viewer, f"SELECT count(*) FROM public.chat_messages WHERE thread_id = '{thread}';"
        )
        assert hidden.rows == ["0"]
    assert (
        _one(db, f"SELECT count(*) FROM public.contacts WHERE '{ALICE}' IN (user_a, user_b)") == "0"
    )
    # The blocked user cannot find the blocker, nor send a new request.
    card = _as(db, ALICE, f"SELECT count(*) FROM public.lookup_handle_card('{social[BOB]}');")
    assert card.ok, card.error
    assert card.rows == ["0"]
    again = _request(db, ALICE, social[BOB])
    assert not again.ok
    assert "social:unavailable" in (again.error or "")
    # Only the blocker can see the block row.
    assert _as(db, ALICE, "SELECT count(*) FROM public.contact_blocks;").rows == ["0"]
    assert _as(db, BOB, "SELECT count(*) FROM public.contact_blocks;").rows == ["1"]


def test_block_cancels_pending_requests(db: PgConn, social: dict[str, str]) -> None:
    assert _request(db, ALICE, social[BOB]).ok
    _one(db, f"SELECT public.block_user('{ALICE}', '{BOB}')::text")
    assert (
        _one(
            db,
            f"SELECT string_agg(status, ',') FROM public.contact_requests WHERE from_user = '{ALICE}' AND to_user = '{BOB}'",
        )
        == "expired"
    )


def test_request_refused_when_recipient_is_no_one(db: PgConn, social: dict[str, str]) -> None:
    assert db.run(
        f"UPDATE public.profiles SET contact_requests_from = 'no_one' WHERE id = '{BOB}'"
    ).ok
    refused = _request(db, ALICE, social[BOB])
    assert not refused.ok
    assert "social:not_accepting" in (refused.error or "")
    # Same refusal for a real user JWT call.
    direct = _as(db, ALICE, f"SELECT public.send_contact_request('{social[BOB]}', NULL, NULL);")
    assert not direct.ok
    assert "social:not_accepting" in (direct.error or "")


def test_duplicate_pending_refused_and_crossing_request_accepts(
    db: PgConn, social: dict[str, str]
) -> None:
    assert _request(db, ALICE, social[BOB]).ok
    dup = _request(db, ALICE, social[BOB])
    assert not dup.ok
    assert "social:duplicate" in (dup.error or "")
    crossing = _request(db, BOB, social[ALICE])
    assert crossing.ok, crossing.error
    assert crossing.rows[0].endswith("|accepted")
    assert (
        _one(db, f"SELECT count(*) FROM public.chat_threads WHERE '{ALICE}' IN (user_a, user_b)")
        == "1"
    )


def test_ignored_request_is_silent_duplicate(db: PgConn, social: dict[str, str]) -> None:
    request_id = _request(db, ALICE, social[BOB]).rows[0].split("|")[0]
    _one(
        db, f"SELECT status FROM public.respond_contact_request('{request_id}', 'ignore', '{BOB}')"
    )
    again = _request(db, ALICE, social[BOB])
    assert not again.ok
    assert "social:duplicate" in (again.error or "")


def test_only_recipient_can_respond(db: PgConn, social: dict[str, str]) -> None:
    request_id = _request(db, ALICE, social[BOB]).rows[0].split("|")[0]
    for actor in (ALICE, CAROL):
        refused = _svc(
            db, f"SELECT public.respond_contact_request('{request_id}', 'accept', '{actor}')"
        )
        assert not refused.ok
        assert "social:not_found" in (refused.error or "")


def test_note_longer_than_80_refused(db: PgConn, social: dict[str, str]) -> None:
    refused = _request(db, ALICE, social[BOB], note="x" * 81)
    assert not refused.ok
    assert "social:note_too_long" in (refused.error or "")


def test_handle_uniqueness_is_case_insensitive(db: PgConn, social: dict[str, str]) -> None:
    taken = social[BOB].upper()
    db.run(
        f"UPDATE public.user_handles SET changed_at = now() - interval '31 days' WHERE user_id = '{ALICE}'"
    )
    result = _svc(db, f"SELECT public.set_my_handle('@{taken}', '{ALICE}')")
    assert not result.ok
    assert "social:handle_taken" in (result.error or "")
    # A raw mixed-case value can never be stored, so the unique key covers all cases.
    raw = db.run(
        f"INSERT INTO public.user_handles (user_id, handle) VALUES ('{PERSONA_UIDS[Persona.ADMIN]}', '{taken}')"
    )
    assert not raw.ok
    # Lookup is case-insensitive too.
    card = _as(db, ALICE, f"SELECT handle FROM public.lookup_handle_card('{taken}');")
    assert card.rows == [social[BOB]]


def test_handle_change_cooldown(db: PgConn, social: dict[str, str]) -> None:
    refused = _svc(db, f"SELECT public.set_my_handle('{_handle()}', '{ALICE}')")
    assert not refused.ok
    assert "social:handle_cooldown" in (refused.error or "")
    db.run(
        f"UPDATE public.user_handles SET changed_at = now() - interval '31 days' WHERE user_id = '{ALICE}'"
    )
    fresh = _handle()
    assert _one(db, f"SELECT public.set_my_handle('{fresh.upper()}', '{ALICE}')") == fresh


def test_phone_discovery_never_returns_non_opted_in(db: PgConn, social: dict[str, str]) -> None:
    hashes = {u: uuid.uuid4().hex + uuid.uuid4().hex for u in (BOB, CAROL, DAVE)}
    _one(db, f"SELECT public.set_phone_discovery('{BOB}', '{hashes[BOB]}', true)::text")
    _one(db, f"SELECT public.set_phone_discovery('{CAROL}', '{hashes[CAROL]}', false)::text")
    # DAVE opted in but blocked ALICE.
    _one(db, f"SELECT public.set_phone_discovery('{DAVE}', '{hashes[DAVE]}', true)::text")
    _one(db, f"SELECT public.block_user('{ALICE}', '{DAVE}')::text")
    array = "ARRAY[" + ", ".join(f"'{h}'" for h in hashes.values()) + "]"
    found = _one(
        db,
        f"SELECT coalesce(string_agg(user_id::text, ','), '') FROM public.discover_by_phone_hashes({array}, '{ALICE}')",
    )
    assert found == BOB
    # Clients cannot call discovery or read others' phone rows.
    direct = _as(db, ALICE, f"SELECT * FROM public.discover_by_phone_hashes({array}, NULL);")
    assert not direct.ok
    assert _as(db, ALICE, "SELECT count(*) FROM public.phone_discovery;").rows == ["0"]
    too_many = _svc(
        db,
        f"SELECT count(*) FROM public.discover_by_phone_hashes(array_fill('{hashes[BOB]}'::text, ARRAY[201]), '{ALICE}')",
    )
    assert not too_many.ok
    assert "social:too_many_hashes" in (too_many.error or "")


def test_request_rate_limit_failure_path(db: PgConn, social: dict[str, str]) -> None:
    # 30 requests already sent in the last 24 h (synthetic rows to distinct users).
    filler = ", ".join(
        f"('{ALICE}', '{u}', 'expired', now() - interval '1 hour', now())"
        for u in (BOB, CAROL, DAVE)
        for _ in range(10)
    )
    assert db.run(
        f"INSERT INTO public.contact_requests (from_user, to_user, status, created_at, decided_at) VALUES {filler}"
    ).ok
    limited = _request(db, ALICE, social[BOB])
    assert not limited.ok
    assert "social:rate_limited" in (limited.error or "")


def test_message_rate_limit_failure_path(db: PgConn, social: dict[str, str]) -> None:
    thread = _connect(db, social, ALICE, BOB)
    for index in range(20):
        assert _send(db, ALICE, thread, f"m{index}").ok
    limited = _send(db, ALICE, thread, "one too many")
    assert not limited.ok
    assert "social:rate_limited" in (limited.error or "")
    # The other party has their own budget in the thread.
    assert _send(db, BOB, thread).ok


def test_share_card_shape_enforced(db: PgConn, social: dict[str, str]) -> None:
    thread = _connect(db, social, ALICE, BOB)
    ok = _svc(
        db,
        f"SELECT public.send_chat_message('{thread}', 'share_card', NULL, "
        f'\'{{"type": "product", "id": "abc-123"}}\'::jsonb, \'{ALICE}\')',
    )
    assert ok.ok, ok.error
    bad = _svc(
        db,
        f"SELECT public.send_chat_message('{thread}', 'share_card', NULL, "
        f'\'{{"type": "wallet", "id": "x"}}\'::jsonb, \'{ALICE}\')',
    )
    assert not bad.ok
    assert "social:message_invalid" in (bad.error or "")


def test_expire_contact_requests_is_service_role_only(db: PgConn, social: dict[str, str]) -> None:
    assert db.run(
        f"INSERT INTO public.contact_requests (from_user, to_user, created_at) VALUES ('{CAROL}', '{DAVE}', now() - interval '31 days')"
    ).ok
    assert int(_one(db, "SELECT public.expire_contact_requests()")) >= 1
    assert (
        _one(
            db,
            f"SELECT status FROM public.contact_requests WHERE from_user = '{CAROL}' AND to_user = '{DAVE}'",
        )
        == "expired"
    )
    for role in ("anon", "authenticated"):
        assert (
            _one(
                db,
                f"SELECT has_function_privilege('{role}', 'public.expire_contact_requests()', 'execute')::text",
            )
            == "false"
        )
