"""Disposable-Postgres contract tests for the in-app notification center migration.

Proves (against the real migration chain, not a fake client):

* outbox enqueues and the registry-silent domain transitions create in-app rows
  in the same transaction — incl. the vendor-driven ``order_status_changed``
  rows that previously reached the customer on no channel at all;
* params are allow-listed (no pickup PIN / notes copied from the outbox);
* admin rows fan out per admin user;
* RLS: a user reads and marks only their own rows; content columns are
  immutable; seen/read timestamps never clear.

Run with ``IN_APP_NOTIF_TEST_DATABASE_URL`` pointing at a disposable local
database whose name ends in ``_test`` (it is wiped and re-migrated), e.g.
``postgresql://postgres:postgres@127.0.0.1:5432/vergeo5_notif_test``.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from urllib.parse import urlsplit

import pytest
from tests.rls.conftest import (
    PgConn,
    apply_migrations,
    seed_matrix_fixtures,
)

DATABASE_URL = os.environ.get("IN_APP_NOTIF_TEST_DATABASE_URL", "")

CUSTOMER_A = "11111111-1111-1111-1111-111111111111"
CUSTOMER_B = "22222222-2222-2222-2222-222222222222"
VENDOR_A_OWNER = "33333333-3333-3333-3333-333333333333"
ADMIN = "66666666-6666-6666-6666-666666666666"
VENDOR_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
ORDER_PENDING = "c2000000-0000-0000-0000-000000000002"
ORDER_PAID = "c2000000-0000-0000-0000-000000000001"
INSTANCE = "e1000000-0000-0000-0000-000000000001"
TICKET_TYPE = "e2000000-0000-0000-0000-000000000001"

SEEDED_A = "aa000000-0000-4000-8000-00000000000a"
SEEDED_B = "bb000000-0000-4000-8000-00000000000b"


@pytest.fixture(scope="module")
def db() -> Iterator[PgConn]:
    if not DATABASE_URL:
        pytest.skip("Set IN_APP_NOTIF_TEST_DATABASE_URL to a disposable *_test database")
    parsed = urlsplit(DATABASE_URL)
    if parsed.hostname not in {"127.0.0.1", "localhost"} or not parsed.path.endswith("_test"):
        pytest.fail("In-app notification DB test requires a local disposable *_test database")
    # Fresh database every run: the migration chain owns several schemas, so a
    # public-only reset would replay into leftovers.
    dbname = parsed.path.lstrip("/")
    admin = PgConn(DATABASE_URL.replace(parsed.path, "/postgres", 1))
    for statement in (
        f"DROP DATABASE IF EXISTS {dbname} WITH (FORCE)",
        f"CREATE DATABASE {dbname}",
    ):
        recreated = admin.run(statement)
        assert recreated.ok, recreated.error
    conn = PgConn(DATABASE_URL)
    apply_migrations(conn)
    seed_matrix_fixtures(conn)
    seeded = conn.run(
        f"""
        INSERT INTO public.in_app_notifications
          (id, recipient_user_id, audience, type, i18n_key, params, link_path, dedupe_key)
        VALUES
          ('{SEEDED_A}', '{CUSTOMER_A}', 'customer', 'order_shipped',
           'notifications.inApp.order_shipped', '{{"ref":"AAAA0000"}}',
           '/account/orders/x', 'seed:a'),
          ('{SEEDED_B}', '{CUSTOMER_B}', 'customer', 'order_shipped',
           'notifications.inApp.order_shipped', '{{"ref":"BBBB0000"}}',
           '/account/orders/y', 'seed:b');
        INSERT INTO public.web_push_subscriptions (user_id, audience, endpoint, p256dh, auth_secret)
        VALUES ('{CUSTOMER_A}', 'customer', 'https://push.example.test/a',
                'p256dh-key-material-aaaa', 'auth-aaaa');
        """
    )
    assert seeded.ok, seeded.error
    yield conn


def _tx(db: PgConn, body: str) -> list[str]:
    """Run ``body`` in a rolled-back transaction as postgres; return output rows."""
    result = db.run_script(f"BEGIN;\n{body}\nROLLBACK;\n")
    assert result.ok, result.error
    return [row for row in result.rows if row not in {"BEGIN", "ROLLBACK", "INSERT 0 1"}]


def _outbox(dedupe: str, template: str, payload: str) -> str:
    return (
        "INSERT INTO public.notification_outbox (dedupe_key, channel, template, payload) "
        f"VALUES ('{dedupe}', 'whatsapp', '{template}', '{payload}'::jsonb);"
    )


def test_vendor_status_change_notifies_customer_in_app(db: PgConn) -> None:
    rows = _tx(
        db,
        _outbox(
            f"order-status-changed:{ORDER_PAID}:shipped:whatsapp",
            "order_status_changed",
            f'{{"order_id":"{ORDER_PAID}","customer_id":"{CUSTOMER_A}",'
            '"from_status":"confirmed","to_status":"shipped","note":"Courier 0977 123456"}',
        )
        + f"""
        SELECT recipient_user_id || '|' || audience || '|' || type || '|' || i18n_key
               || '|' || link_path || '|' || params::text
        FROM public.in_app_notifications WHERE dedupe_key = 'order_shipped:{ORDER_PAID}';
        """,
    )
    assert rows == [
        f"{CUSTOMER_A}|customer|order_shipped|notifications.inApp.order_shipped"
        f'|/account/orders/{ORDER_PAID}|{{"ref": "C2000000"}}'
    ]


@pytest.mark.parametrize(
    ("to_status", "expected_type"),
    [
        ("confirmed", "order_confirmed"),
        ("cancelled", "order_rejected"),
        ("processing", "order_packed"),
        ("ready", "order_ready_pickup"),
    ],
)
def test_each_vendor_transition_maps_to_customer_type(
    db: PgConn, to_status: str, expected_type: str
) -> None:
    rows = _tx(
        db,
        _outbox(
            f"order-status-changed:{ORDER_PAID}:{to_status}:whatsapp",
            "order_status_changed",
            f'{{"order_id":"{ORDER_PAID}","to_status":"{to_status}"}}',
        )
        + f"SELECT string_agg(type || '/' || audience, ',') FROM public.in_app_notifications "
        f"WHERE dedupe_key LIKE '%:{ORDER_PAID}';",
    )
    assert rows == [f"{expected_type}/customer"]


def test_order_placed_notifies_vendor_and_customer(db: PgConn) -> None:
    rows = _tx(
        db,
        _outbox(
            f"order_placed:{ORDER_PENDING}:whatsapp",
            "vendor_new_order",
            f'{{"order_id":"{ORDER_PENDING}","recipient_id":"{VENDOR_A_OWNER}"}}',
        )
        + f"""
        SELECT string_agg(audience || ':' || recipient_user_id || ':' || link_path, ','
                          ORDER BY audience)
        FROM public.in_app_notifications WHERE dedupe_key = 'order_placed:{ORDER_PENDING}';
        """,
    )
    assert rows == [
        f"customer:{CUSTOMER_A}:/account/orders/{ORDER_PENDING},"
        f"vendor:{VENDOR_A_OWNER}:/orders/{ORDER_PENDING}"
    ]


def test_twin_lifecycle_rows_dedupe_and_pickup_secrets_are_not_copied(db: PgConn) -> None:
    rows = _tx(
        db,
        _outbox(
            f"order-status-changed:{ORDER_PAID}:ready:whatsapp",
            "order_status_changed",
            f'{{"order_id":"{ORDER_PAID}","to_status":"ready"}}',
        )
        + _outbox(
            f"order_ready_pickup:{ORDER_PAID}:whatsapp",
            "order_ready_pickup",
            f'{{"order_id":"{ORDER_PAID}","recipient_id":"{CUSTOMER_A}",'
            '"pickup_pin":"482913","pickup_qr_token":"qr-secret","pickup_details":"PIN 482913"}',
        )
        + f"""
        SELECT count(*) || '|' || bool_or(params::text LIKE '%482913%')::text
        FROM public.in_app_notifications WHERE dedupe_key = 'order_ready_pickup:{ORDER_PAID}';
        """,
    )
    assert rows == ["1|false"]


def test_unknown_order_and_unmapped_template_are_noops(db: PgConn) -> None:
    rows = _tx(
        db,
        _outbox(
            "order-status-changed:x:shipped:whatsapp",
            "order_status_changed",
            '{"order_id":"not-a-uuid","to_status":"shipped"}',
        )
        + _outbox("beta:x:whatsapp", "beta_feedback", "{}")
        + "SELECT count(*) FROM public.in_app_notifications WHERE dedupe_key NOT LIKE 'seed:%';",
    )
    assert rows == ["0"]


def test_kyc_submitted_notifies_vendor_and_fans_out_to_admins(db: PgConn) -> None:
    rows = _tx(
        db,
        f"""
        INSERT INTO public.kyc_records (vendor_id, tier, status)
        VALUES ('{VENDOR_A}', 1, 'submitted');
        SELECT string_agg(audience || ':' || recipient_user_id, ',' ORDER BY audience)
        FROM public.in_app_notifications WHERE type = 'kyc_submitted';
        """,
    )
    assert rows == [f"admin:{ADMIN},vendor:{VENDOR_A_OWNER}"]


def test_kyc_decision_from_outbox_reaches_vendor_owner(db: PgConn) -> None:
    rows = _tx(
        db,
        _outbox(
            "kyc-approved:k1:whatsapp",
            "kyc_approved",
            f'{{"vendor_id":"{VENDOR_A}","owner_user_id":"{VENDOR_A_OWNER}"}}',
        )
        + "SELECT recipient_user_id || '|' || audience FROM public.in_app_notifications "
        "WHERE type = 'kyc_approved';",
    )
    assert rows == [f"{VENDOR_A_OWNER}|vendor"]


def test_dispute_opened_notifies_admins_and_vendor(db: PgConn) -> None:
    rows = _tx(
        db,
        f"""
        INSERT INTO public.disputes (order_id, opener_user_id)
        VALUES ('{ORDER_PAID}', '{CUSTOMER_A}');
        SELECT string_agg(audience || ':' || recipient_user_id, ',' ORDER BY audience)
        FROM public.in_app_notifications WHERE type = 'dispute_opened';
        """,
    )
    assert rows == [f"admin:{ADMIN},vendor:{VENDOR_A_OWNER}"]


def test_ticket_issued_notifies_holder(db: PgConn) -> None:
    rows = _tx(
        db,
        f"""
        INSERT INTO public.tickets (instance_id, ticket_type_id, holder_user_id, status)
        VALUES ('{INSTANCE}', '{TICKET_TYPE}', '{CUSTOMER_B}', 'issued');
        SELECT recipient_user_id || '|' || link_path FROM public.in_app_notifications
        WHERE type = 'ticket_issued';
        """,
    )
    assert rows == [f"{CUSTOMER_B}|/account/tickets"]


# --- RLS -----------------------------------------------------------------------


def _as(db: PgConn, user_id: str, sql: str) -> tuple[bool, list[str], str | None]:
    result = db.run_as("authenticated", sql, user_id=user_id)
    return result.ok, result.rows, result.error


def test_user_reads_only_own_rows(db: PgConn) -> None:
    ok, rows, error = _as(
        db, CUSTOMER_A, "SELECT string_agg(id::text, ',') FROM public.in_app_notifications;"
    )
    assert ok, error
    assert rows == [SEEDED_A]
    ok, rows, error = _as(
        db,
        CUSTOMER_B,
        f"SELECT count(*) FROM public.in_app_notifications WHERE id = '{SEEDED_A}';",
    )
    assert ok, error
    assert rows == ["0"]


def test_anon_cannot_read(db: PgConn) -> None:
    result = db.run_as("anon", "SELECT count(*) FROM public.in_app_notifications;")
    assert not result.ok
    assert "permission denied" in (result.error or "").lower()


def test_user_marks_only_own_rows_seen(db: PgConn) -> None:
    ok, rows, error = _as(
        db,
        CUSTOMER_B,
        "WITH u AS (UPDATE public.in_app_notifications SET seen_at = now() "
        f"WHERE id = '{SEEDED_A}' RETURNING 1) SELECT count(*) FROM u;",
    )
    assert ok, error
    assert rows == ["0"]
    ok, rows, error = _as(
        db,
        CUSTOMER_A,
        "WITH u AS (UPDATE public.in_app_notifications SET read_at = now() "
        f"WHERE id = '{SEEDED_A}' RETURNING seen_at IS NOT NULL) SELECT * FROM u;",
    )
    assert ok, error
    assert rows == ["t"]


def test_content_columns_are_not_client_writable(db: PgConn) -> None:
    ok, _rows, error = _as(
        db,
        CUSTOMER_A,
        f"UPDATE public.in_app_notifications SET link_path = '/evil' WHERE id = '{SEEDED_A}';",
    )
    assert not ok
    assert "permission denied" in (error or "").lower()
    ok, _rows, error = _as(
        db,
        CUSTOMER_A,
        "INSERT INTO public.in_app_notifications (recipient_user_id, audience, type, i18n_key, "
        f"dedupe_key) VALUES ('{CUSTOMER_A}', 'customer', 'x_y', 'notifications.inApp.x_y', 'k');",
    )
    assert not ok
    assert "permission denied" in (error or "").lower()


def test_seen_timestamp_never_clears(db: PgConn) -> None:
    rows = _tx(
        db,
        f"""
        UPDATE public.in_app_notifications SET seen_at = now() WHERE id = '{SEEDED_A}';
        UPDATE public.in_app_notifications SET seen_at = NULL WHERE id = '{SEEDED_A}';
        SELECT (seen_at IS NOT NULL)::text FROM public.in_app_notifications WHERE id = '{SEEDED_A}';
        """,
    )
    assert rows[-1] == "true"


def test_push_subscriptions_are_owner_only(db: PgConn) -> None:
    ok, rows, error = _as(db, CUSTOMER_B, "SELECT count(*) FROM public.web_push_subscriptions;")
    assert ok, error
    assert rows == ["0"]
    ok, rows, error = _as(db, CUSTOMER_A, "SELECT count(*) FROM public.web_push_subscriptions;")
    assert ok, error
    assert rows == ["1"]


def test_web_push_flag_defaults_off(db: PgConn) -> None:
    result = db.run("SELECT enabled::text FROM public.feature_flags WHERE flag = 'web_push';")
    assert result.ok, result.error
    assert result.rows == ["false"]
