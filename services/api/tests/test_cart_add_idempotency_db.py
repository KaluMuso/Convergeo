"""Disposable PostgreSQL contract test for the cart add transaction.

Run with CART_IDEMPOTENCY_TEST_DATABASE_URL pointing at a local cart_idem_test
database. The guard deliberately refuses any other database.
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from urllib.parse import urlparse
from uuid import uuid4

import psycopg
import pytest

DATABASE_URL = os.environ.get("CART_IDEMPOTENCY_TEST_DATABASE_URL", "")
MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "supabase/migrations/20261009110000_cart_add_idempotency.sql"
)


def _connection() -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL)


@pytest.fixture(scope="module", autouse=True)
def disposable_schema() -> None:
    if not DATABASE_URL:
        pytest.skip("Set CART_IDEMPOTENCY_TEST_DATABASE_URL for local PostgreSQL contract test")
    target = urlparse(DATABASE_URL)
    if target.hostname not in {"127.0.0.1", "localhost"} or target.path != "/cart_idem_test":
        pytest.fail("Cart idempotency DB test requires a loopback cart_idem_test database")
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            "drop function if exists public.apply_cart_add_idempotent("
            "uuid,uuid,text,text,jsonb,uuid,integer,integer,uuid,bigint,boolean,uuid)"
        )
        cur.execute(
            "drop table if exists public.cart_add_requests, public.cart_items, public.carts"
        )
        for role, suffix in (("anon", ""), ("authenticated", ""), ("service_role", "bypassrls")):
            cur.execute("select 1 from pg_roles where rolname=%s", (role,))
            if not cur.fetchone():
                cur.execute(f"create role {role} nologin {suffix}")
        cur.execute("grant usage on schema public to service_role")
        cur.execute(
            "create table public.carts (id uuid primary key, user_id uuid, guest_token text, "
            "status text not null default 'active')"
        )
        cur.execute(
            "create table public.cart_items (id uuid primary key default gen_random_uuid(), "
            "cart_id uuid not null references public.carts(id), listing_id uuid not null, "
            "qty integer not null, unit_price_ngwee bigint not null, wholesale boolean not null, "
            "pickup_location_id uuid, unique(cart_id, listing_id))"
        )
        cur.execute(
            "grant select, insert, update on public.carts, public.cart_items to service_role"
        )
        cur.execute(MIGRATION.read_text())


def _call(
    conn: psycopg.Connection,
    *,
    cart_id: str,
    user_id: str | None,
    guest_token: str | None,
    listing_id: str,
    key: str,
    qty: int = 2,
    expected_qty: int | None = None,
    body: dict | None = None,
) -> str:
    body = body or {"listing_id": listing_id, "qty": qty}
    with conn.cursor() as cur:
        cur.execute(
            "select public.apply_cart_add_idempotent(%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s)",
            (
                cart_id,
                user_id,
                guest_token,
                key,
                json.dumps(body),
                listing_id,
                qty,
                expected_qty,
                None,
                1500,
                False,
                None,
            ),
        )
        return cur.fetchone()[0]


def _new_cart(*, guest: bool = False) -> tuple[str, str | None, str | None]:
    cart_id, user_id = str(uuid4()), str(uuid4())
    guest_token = "guest-test" if guest else None
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            "insert into public.carts(id,user_id,guest_token) values(%s,%s,%s)",
            (cart_id, None if guest else user_id, guest_token),
        )
    return cart_id, None if guest else user_id, guest_token


def _qty(cart_id: str, listing_id: str) -> int:
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            "select qty from public.cart_items where cart_id=%s and listing_id=%s",
            (cart_id, listing_id),
        )
        row = cur.fetchone()
        return row[0] if row else 0


def test_same_key_replay_mismatch_and_cart_scope() -> None:
    cart_id, user_id, guest_token = _new_cart()
    other_cart, other_user, _ = _new_cart()
    listing_id = str(uuid4())
    with _connection() as conn:
        args = dict(
            cart_id=cart_id,
            user_id=user_id,
            guest_token=guest_token,
            listing_id=listing_id,
            key="retry-1",
        )
        assert _call(conn, **args) == "applied"
        assert _call(conn, **args) == "replayed"
    with _connection() as conn:
        with pytest.raises(psycopg.Error, match="cart.idempotency_mismatch"):
            _call(conn, **{**args, "qty": 3})
    assert _qty(cart_id, listing_id) == 2
    with _connection() as conn:
        assert (
            _call(
                conn,
                cart_id=other_cart,
                user_id=other_user,
                guest_token=None,
                listing_id=listing_id,
                key="retry-1",
            )
            == "applied"
        )
    assert _qty(other_cart, listing_id) == 2


def test_concurrent_same_key_commits_once() -> None:
    cart_id, user_id, guest_token = _new_cart(guest=True)
    listing_id = str(uuid4())
    barrier = Barrier(2)

    def attempt() -> str:
        with _connection() as conn:
            barrier.wait()
            return _call(
                conn,
                cart_id=cart_id,
                user_id=user_id,
                guest_token=guest_token,
                listing_id=listing_id,
                key="same-key",
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(results) == ["applied", "replayed"]
    assert _qty(cart_id, listing_id) == 2


def test_distinct_keys_revalidate_stale_snapshot() -> None:
    cart_id, user_id, guest_token = _new_cart()
    listing_id = str(uuid4())
    barrier = Barrier(2)

    def attempt(key: str) -> tuple[str, str]:
        with _connection() as conn:
            barrier.wait()
            result = _call(
                conn,
                cart_id=cart_id,
                user_id=user_id,
                guest_token=guest_token,
                listing_id=listing_id,
                key=key,
            )
            return key, result

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = dict(pool.map(attempt, ("first", "second")))
    assert sorted(outcomes.values()) == ["applied", "stale"]
    stale_key = next(key for key, result in outcomes.items() if result == "stale")
    with _connection() as conn:
        assert (
            _call(
                conn,
                cart_id=cart_id,
                user_id=user_id,
                guest_token=guest_token,
                listing_id=listing_id,
                key=stale_key,
                expected_qty=2,
            )
            == "applied"
        )
    assert _qty(cart_id, listing_id) == 4


def test_rollback_does_not_strand_key_or_increment() -> None:
    cart_id, user_id, guest_token = _new_cart()
    listing_id = str(uuid4())
    conn = _connection()
    try:
        assert (
            _call(
                conn,
                cart_id=cart_id,
                user_id=user_id,
                guest_token=guest_token,
                listing_id=listing_id,
                key="interrupted",
            )
            == "applied"
        )
        conn.rollback()
    finally:
        conn.close()
    assert _qty(cart_id, listing_id) == 0
    with _connection() as conn:
        assert (
            _call(
                conn,
                cart_id=cart_id,
                user_id=user_id,
                guest_token=guest_token,
                listing_id=listing_id,
                key="interrupted",
            )
            == "applied"
        )
    assert _qty(cart_id, listing_id) == 2


def test_owner_and_client_grants() -> None:
    cart_id, user_id, guest_token = _new_cart()
    listing_id = str(uuid4())
    with _connection() as conn:
        with pytest.raises(psycopg.Error, match="cart.owner_mismatch"):
            _call(
                conn,
                cart_id=cart_id,
                user_id=str(uuid4()),
                guest_token=guest_token,
                listing_id=listing_id,
                key="wrong-owner",
            )
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            "select has_table_privilege('anon', 'public.cart_add_requests', 'select'), "
            "has_table_privilege('authenticated', 'public.cart_add_requests', 'insert'), "
            "has_function_privilege('anon', "
            "'public.apply_cart_add_idempotent(uuid,uuid,text,text,jsonb,uuid,"
            "integer,integer,uuid,bigint,boolean,uuid)', "
            "'execute')"
        )
        assert cur.fetchone() == (False, False, False)
    with _connection() as conn:
        with conn.cursor() as cur:
            cur.execute("set local role service_role")
        assert (
            _call(
                conn,
                cart_id=cart_id,
                user_id=user_id,
                guest_token=guest_token,
                listing_id=listing_id,
                key="service-role",
            )
            == "applied"
        )
