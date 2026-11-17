# ruff: noqa: E501 — long inline SQL fixtures read better unwrapped.
"""Convergeo Points + weekly seller digest on real Postgres (migrations 20261117010100/020100).

Disposable-database contract as test_offers_order_db.py: ``ORDER_TEST_DB_URL`` = a
fully migrated database, else a local 5432 Postgres that this module migrates.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Generator

import pytest
from tests.rls.conftest import PgConn, apply_migrations, seed_matrix_fixtures

# Fresh buyer per run: the day cap is per Lusaka day, so reruns must not share one.
CUSTOMER_ID = str(uuid.uuid4())
VENDOR_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VENDOR_A_OWNER = "33333333-3333-3333-3333-333333333333"
_DB_NAME = "vergeo5_points_test"
NOW = "2026-11-16 10:00:00+00"


@pytest.fixture(scope="module")
def db() -> Generator[PgConn, None, None]:
    if isolated_url := os.environ.get("ORDER_TEST_DB_URL"):
        conn = PgConn(isolated_url)
        ready = conn.run("SELECT 1 FROM public.points_ledger LIMIT 1")
        assert ready.ok, ready.error
        seed_matrix_fixtures(conn)
    else:
        admin = PgConn("postgresql://postgres:postgres@127.0.0.1:5432/postgres")
        if not admin.run("SELECT 1").ok:
            pytest.skip("Postgres not reachable on 127.0.0.1:5432")
        admin.run(f"DROP DATABASE IF EXISTS {_DB_NAME};")
        admin.run(f"CREATE DATABASE {_DB_NAME};")
        conn = PgConn(f"postgresql://postgres:postgres@127.0.0.1:5432/{_DB_NAME}")
        apply_migrations(conn)
        seed_matrix_fixtures(conn)
    _ok(conn, f"INSERT INTO auth.users (id) VALUES ('{CUSTOMER_ID}');")
    _ok(
        conn,
        "UPDATE public.feature_flags SET enabled = true WHERE flag IN ('loyalty_points', 'vendor_weekly_digest');",
    )
    yield conn
    conn.run(
        "UPDATE public.feature_flags SET enabled = false WHERE flag IN ('loyalty_points', 'vendor_weekly_digest');"
    )


def _ok(conn: PgConn, sql: str) -> list[str]:
    result = conn.run(sql)
    assert result.ok, result.error
    return result.rows


def _scalar(conn: PgConn, sql: str) -> str:
    rows = _ok(conn, sql)
    assert rows, sql
    return rows[0]


def _order(
    conn: PgConn,
    *,
    customer: str = CUSTOMER_ID,
    vendor: str = VENDOR_A,
    amount: int = 12_345,
    delivered_hours_ago: int = 100,
    cod: bool = True,
    status: str = "delivered",
    title: str = "Phone case",
    qty: int = 1,
) -> str:
    group, order = str(uuid.uuid4()), str(uuid.uuid4())
    _ok(
        conn,
        f"""
        INSERT INTO public.checkout_groups (id, customer_id, idempotency_key, subtotal_ngwee,
          delivery_fee_ngwee, total_ngwee, status)
        VALUES ('{group}', '{customer}', 'pts-{group}', {amount * qty}, 0, {amount * qty}, 'completed');
        INSERT INTO public.orders (id, checkout_group_id, vendor_id, customer_id, status,
          fulfilment, cod, created_at)
        VALUES ('{order}', '{group}', '{vendor}', '{customer}', '{status}', 'pickup', {str(cod).lower()},
          timestamptz '{NOW}' - interval '{delivered_hours_ago + 24} hours');
        INSERT INTO public.order_items (order_id, item_kind, qty, unit_price_ngwee, title_snapshot)
        VALUES ('{order}', 'product', {qty}, {amount}, '{title}');
        INSERT INTO public.order_events (order_id, from_status, to_status, created_at)
        VALUES ('{order}', 'shipped', 'delivered',
          timestamptz '{NOW}' - interval '{delivered_hours_ago} hours');
        """,
    )
    return order


def _award(conn: PgConn, order: str, now: str = NOW) -> str:
    return _scalar(conn, f"SELECT private.points_award_order('{order}', '{now}');")


def _points(conn: PgConn, order: str) -> int:
    return int(
        _scalar(
            conn,
            f"SELECT coalesce(sum(points),0) FROM public.points_ledger WHERE order_id = '{order}';",
        )
    )


def test_earn_only_after_return_window(db: PgConn) -> None:
    order = _order(db, delivered_hours_ago=10)
    assert _award(db, order) == "not_yet"
    assert _points(db, order) == 0
    # 48h default window passed (10h + 39h).
    assert _award(db, order, "2026-11-18 01:00:00+00") == "awarded"
    assert _points(db, order) == 123  # K123.45 -> 123 points (floor, 1 per K1)
    outbox = _scalar(
        db,
        "SELECT count(*) FROM public.notification_outbox o JOIN public.points_ledger p "
        "ON o.dedupe_key = 'points_earned:' || p.id || ':whatsapp' "
        f"WHERE p.order_id = '{order}' AND o.template = 'points_earned';",
    )
    assert outbox == "1"
    inapp = _scalar(
        db,
        "SELECT count(*) FROM public.in_app_notifications "
        f"WHERE recipient_user_id = '{CUSTOMER_ID}' AND type = 'points_earned';",
    )
    assert int(inapp) >= 1


def test_prepaid_waits_for_escrow_release(db: PgConn) -> None:
    order = _order(db, cod=False)
    assert _award(db, order) == "not_yet"


def test_idempotent_double_award(db: PgConn) -> None:
    order = _order(db)
    assert _award(db, order) == "awarded"
    assert _award(db, order) == "already_awarded"
    assert (
        _scalar(db, f"SELECT count(*) FROM public.points_ledger WHERE order_id = '{order}';") == "1"
    )
    swept = json.loads(_scalar(db, f"SELECT private.points_sweep('{NOW}')::text;"))
    assert swept["enabled"] is True
    assert (
        _scalar(db, f"SELECT count(*) FROM public.points_ledger WHERE order_id = '{order}';") == "1"
    )


def test_reversal_on_refund_is_idempotent(db: PgConn) -> None:
    order = _order(db, amount=50_000)
    assert _award(db, order) == "awarded"
    assert _points(db, order) == 500
    _ok(
        db,
        f"INSERT INTO public.refunds (order_id, lane, amount_ngwee, status, source_key) VALUES ('{order}', 1, 20000, 'completed', 'pts-a-{order}');",
    )
    assert _points(db, order) == 300  # trigger reversed 200
    assert _scalar(db, f"SELECT private.points_reverse_order('{order}');") == "0"
    _ok(
        db,
        f"INSERT INTO public.refunds (order_id, lane, amount_ngwee, status, source_key) VALUES ('{order}', 1, 30000, 'pending', 'pts-b-{order}');",
    )
    assert _points(db, order) == 300  # pending refund reverses nothing
    _ok(
        db,
        f"UPDATE public.refunds SET status = 'completed' WHERE order_id = '{order}' AND status = 'pending';",
    )
    assert _points(db, order) == 0
    json.loads(_scalar(db, f"SELECT private.points_sweep('{NOW}')::text;"))
    assert _points(db, order) == 0


def test_per_order_and_per_day_caps(db: PgConn) -> None:
    OTHER_USER = str(uuid.uuid4())  # noqa: N806 — fresh buyer so the day cap starts at 0
    _ok(db, f"INSERT INTO auth.users (id) VALUES ('{OTHER_USER}');")
    big = _order(db, customer=OTHER_USER, amount=900_000)  # 9000 points before cap
    assert _award(db, big) == "awarded"
    assert _points(db, big) == 2000  # points_cap_per_order
    for _ in range(2):
        assert _award(db, _order(db, customer=OTHER_USER, amount=900_000)) == "awarded"
    capped = _order(db, customer=OTHER_USER, amount=900_000)
    # 2000 + 2000 + 1000 = 5000 (points_cap_per_day), then nothing.
    assert _award(db, capped) == "capped"
    assert _points(db, capped) == 0
    assert _award(db, capped) == "already_awarded"
    day = _scalar(db, f"SELECT private.points_day_earned('{OTHER_USER}', '{NOW}');")
    assert day == "5000"


def test_no_earn_on_own_vendor_order(db: PgConn) -> None:
    order = _order(db, customer=VENDOR_A_OWNER)
    assert _award(db, order) == "not_eligible:self_order"
    assert _points(db, order) == 0


def test_flag_off_earns_nothing(db: PgConn) -> None:
    order = _order(db)
    _ok(db, "UPDATE public.feature_flags SET enabled = false WHERE flag = 'loyalty_points';")
    try:
        assert _award(db, order) == "flag_off"
    finally:
        _ok(db, "UPDATE public.feature_flags SET enabled = true WHERE flag = 'loyalty_points';")


def test_review_reward_ignores_rating(db: PgConn) -> None:
    order = _order(db)
    item = _scalar(db, f"SELECT id FROM public.order_items WHERE order_id = '{order}';")
    review = _scalar(
        db,
        f"INSERT INTO public.reviews (order_item_id, rating) VALUES ('{item}', 1) RETURNING id;",
    )
    pts = _scalar(db, f"SELECT points FROM public.points_ledger WHERE review_id = '{review}';")
    assert pts == "30"
    assert _scalar(db, f"SELECT private.points_award_review('{review}');") == "already_awarded"


def test_ledger_append_only_and_rls_isolation(db: PgConn) -> None:
    order = _order(db)
    _award(db, order)
    upd = db.run(f"UPDATE public.points_ledger SET points = 9999 WHERE order_id = '{order}';")
    assert not upd.ok
    own = db.run_as(
        "authenticated", "SELECT count(*) FROM public.points_ledger;", user_id=CUSTOMER_ID
    )
    other = db.run_as(
        "authenticated",
        f"SELECT count(*) FROM public.points_ledger WHERE user_id = '{CUSTOMER_ID}';",
        user_id=VENDOR_A_OWNER,
    )
    assert own.ok and int(own.rows[0]) >= 1
    assert other.ok and other.rows[0] == "0"
    write = db.run_as(
        "authenticated",
        f"INSERT INTO public.points_ledger (user_id, points, reason, idempotency_key) "
        f"VALUES ('{CUSTOMER_ID}', 100, 'admin_adjust', 'forged-1');",
        user_id=CUSTOMER_ID,
    )
    assert not write.ok
    call = db.run_as(
        "authenticated", f"SELECT private.points_award_order('{order}');", user_id=CUSTOMER_ID
    )
    assert not call.ok
    anon = db.run_as("anon", "SELECT count(*) FROM public.points_ledger;")
    assert not anon.ok or anon.rows[0] == "0"


def test_liability_report(db: PgConn) -> None:
    raw = json.loads(_scalar(db, "SELECT public.points_liability()::text;"))
    assert raw["ngwee_per_point"] == 5
    assert raw["liability_ngwee"] == raw["points_outstanding"] * 5


def test_vendor_weekly_digest_numbers_and_skip(db: PgConn) -> None:
    vendor = str(uuid.uuid4())
    quiet = str(uuid.uuid4())
    owner = _scalar(db, f"SELECT owner_user_id FROM public.vendors WHERE id = '{VENDOR_A}';")
    _ok(
        db,
        f"""
        INSERT INTO public.vendors (id, owner_user_id, slug, display_name, status)
        VALUES ('{vendor}', '{owner}', 'digest-{vendor[:8]}', 'Digest Shop', 'active'),
               ('{quiet}', '{owner}', 'quiet-{quiet[:8]}', 'Quiet Shop', 'active');
        """,
    )
    _order(db, vendor=vendor, amount=10_000, qty=3, title="Case", delivered_hours_ago=24)
    _order(db, vendor=vendor, amount=50_000, qty=1, title="Charger", delivered_hours_ago=48)
    _order(db, vendor=vendor, amount=99_999, status="cancelled", delivered_hours_ago=24)
    _order(db, vendor=vendor, amount=70_000, delivered_hours_ago=24 * 9)  # older than 7 days
    _ok(
        db,
        f"""
        INSERT INTO public.vendor_follows (user_id, vendor_id, created_at)
        VALUES ('{CUSTOMER_ID}', '{vendor}', timestamptz '{NOW}' - interval '1 day');
        INSERT INTO public.payouts (vendor_id, amount_ngwee, rail, lenco_reference, status)
        VALUES ('{vendor}', 29000, 'mtn', 'po-{vendor[:8]}', 'pending');
        """,
    )
    rows = [
        json.loads(r)
        for r in _ok(db, f"SELECT d::text FROM private.vendor_weekly_digest('{NOW}', true) d;")
    ]
    mine = [r for r in rows if r["vendor_id"] == vendor]
    assert [r for r in rows if r["vendor_id"] == quiet] == []
    assert len(mine) == 1
    d = mine[0]
    assert d["orders"] == 2
    assert d["sales_ngwee"] == 80_000
    assert d["top_item"] == "Case"
    assert d["new_followers"] == 1
    assert d["pending_actions"] == 0
    assert d["next_payout_ngwee"] == 29000
    # Re-run is idempotent: one outbox row per vendor-week.
    _ok(db, f"SELECT count(*) FROM private.vendor_weekly_digest('{NOW}', true);")
    sent = _scalar(
        db,
        "SELECT count(*) FROM public.notification_outbox "
        f"WHERE template = 'vendor_weekly_digest' AND payload->>'vendor_id' = '{vendor}';",
    )
    assert sent == "1"
