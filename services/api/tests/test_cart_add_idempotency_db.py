"""Disposable PostgreSQL contract test for the cart add transaction.

Run with CART_IDEMPOTENCY_TEST_DATABASE_URL pointing at a local cart_idem_test
database and a unique CART_IDEMPOTENCY_TEST_CLUSTER_NAME configured on the
server. An owned Unix socket may be explicitly allowed with
CART_IDEMPOTENCY_TEST_SOCKET_DIRECTORY. Routing overrides and mismatched actual
clusters are rejected before destructive fixture DDL.
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import psycopg
import pytest

DATABASE_URL = os.environ.get("CART_IDEMPOTENCY_TEST_DATABASE_URL", "")
SOCKET_DIRECTORY = os.environ.get("CART_IDEMPOTENCY_TEST_SOCKET_DIRECTORY", "")
CLUSTER_NAME = os.environ.get("CART_IDEMPOTENCY_TEST_CLUSTER_NAME", "")
MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "supabase/migrations/20261009110000_cart_add_idempotency.sql"
)


def _validated_target(url: str) -> dict[str, str | int | None]:
    target = urlparse(url)
    if target.scheme not in {"postgres", "postgresql"} or target.query:
        pytest.fail("Cart idempotency DB test refuses URI query overrides")
    info = psycopg.conninfo.conninfo_to_dict(url)
    allowed_hosts = {"127.0.0.1", "localhost"}
    if SOCKET_DIRECTORY and Path(SOCKET_DIRECTORY).is_absolute():
        allowed_hosts.add(SOCKET_DIRECTORY)
    if info.get("host") not in allowed_hosts or info.get("dbname") != "cart_idem_test":
        pytest.fail("Cart idempotency DB test requires an explicit disposable local target")
    if any(os.environ.get(key) for key in ("PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE")):
        pytest.fail("Cart idempotency DB test refuses inherited libpq routing overrides")
    return info


def _connection() -> psycopg.Connection[Any]:
    _validated_target(DATABASE_URL)
    return psycopg.connect(DATABASE_URL)


@pytest.fixture(scope="module", autouse=True)
def disposable_schema() -> None:
    if not DATABASE_URL:
        pytest.skip("Set CART_IDEMPOTENCY_TEST_DATABASE_URL for local PostgreSQL contract test")
    _validated_target(DATABASE_URL)
    if not CLUSTER_NAME.startswith("cart_idem_test-") or len(CLUSTER_NAME) < 32:
        pytest.fail("Set a unique disposable CART_IDEMPOTENCY_TEST_CLUSTER_NAME")
    with _connection() as conn, conn.cursor() as cur:
        # Bind destructive fixture DDL to the actual freshly owned cluster,
        # rather than trusting URI spelling or an inherited connection option.
        cur.execute("select current_database(), current_setting('cluster_name')")
        if cur.fetchone() != ("cart_idem_test", CLUSTER_NAME):
            pytest.fail("Cart idempotency DB fixture refuses an unverified cluster")
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
        cur.execute("grant usage on schema public to anon, authenticated")
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
    conn: psycopg.Connection[Any],
    *,
    cart_id: str,
    user_id: str | None,
    guest_token: str | None,
    listing_id: str,
    key: str,
    qty: int = 2,
    expected_qty: int | None = None,
    expected_location_id: str | None = None,
    location_id: str | None = None,
    body: dict[str, Any] | None = None,
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
                expected_location_id,
                1500,
                False,
                location_id,
            ),
        )
        row = cur.fetchone()
        assert row is not None
        return str(row[0])


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


def _claims(cart_id: str) -> int:
    with _connection() as conn, conn.cursor() as cur:
        cur.execute("select count(*) from public.cart_add_requests where cart_id=%s", (cart_id,))
        row = cur.fetchone()
        assert row is not None
        return int(row[0])


def test_same_key_replay_mismatch_and_cart_scope() -> None:
    cart_id, user_id, guest_token = _new_cart()
    other_cart, other_user, _ = _new_cart()
    listing_id = str(uuid4())
    with _connection() as conn:
        assert (
            _call(
                conn,
                cart_id=cart_id,
                user_id=user_id,
                guest_token=guest_token,
                listing_id=listing_id,
                key="retry-1",
            )
            == "applied"
        )
        assert (
            _call(
                conn,
                cart_id=cart_id,
                user_id=user_id,
                guest_token=guest_token,
                listing_id=listing_id,
                key="retry-1",
            )
            == "replayed"
        )
    with _connection() as conn:
        with pytest.raises(psycopg.Error, match="cart.idempotency_mismatch"):
            _call(
                conn,
                cart_id=cart_id,
                user_id=user_id,
                guest_token=guest_token,
                listing_id=listing_id,
                key="retry-1",
                qty=3,
            )
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
    assert _qty(cart_id, listing_id) == 2
    assert _claims(cart_id) == 1
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
    assert _claims(cart_id) == 2


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
        cur.execute(
            "select relrowsecurity, relforcerowsecurity from pg_class "
            "where oid='public.cart_add_requests'::regclass"
        )
        assert cur.fetchone() == (True, True)
        cur.execute(
            "select prosecdef, proconfig from pg_proc "
            "where oid='public.apply_cart_add_idempotent(uuid,uuid,text,text,jsonb,uuid,"
            "integer,integer,uuid,bigint,boolean,uuid)'::regprocedure"
        )
        assert cur.fetchone() == (False, ['search_path=""'])
        cur.execute(
            "select has_table_privilege('service_role','public.cart_add_requests','select'), "
            "has_table_privilege('service_role','public.cart_add_requests','insert'), "
            "has_table_privilege('authenticated','public.cart_add_requests','select')"
        )
        assert cur.fetchone() == (True, True, False)
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


@pytest.mark.parametrize(
    ("guest", "owner_kind", "error"),
    [
        (True, "wrong_guest", "cart.owner_mismatch"),
        (False, "guest_on_user_cart", "cart.owner_mismatch"),
        (False, "both", "cart.owner_invalid"),
        (False, "neither", "cart.owner_invalid"),
        (False, "inactive", "cart.owner_mismatch"),
    ],
)
def test_rejects_wrong_or_inactive_owner(
    guest: bool,
    owner_kind: str,
    error: str,
) -> None:
    cart_id, user_id, guest_token = _new_cart(guest=guest)
    listing_id = str(uuid4())
    if owner_kind == "wrong_guest":
        guest_token = "another-guest"
    elif owner_kind == "guest_on_user_cart":
        user_id, guest_token = None, "guest-test"
    elif owner_kind == "both":
        guest_token = "guest-test"
    elif owner_kind == "neither":
        user_id = None
    elif owner_kind == "inactive":
        with _connection() as conn, conn.cursor() as cur:
            cur.execute("update public.carts set status='converted' where id=%s", (cart_id,))
    with _connection() as conn:
        with pytest.raises(psycopg.Error, match=error):
            _call(
                conn,
                cart_id=cart_id,
                user_id=user_id,
                guest_token=guest_token,
                listing_id=listing_id,
                key="owner-check",
            )
    assert _qty(cart_id, listing_id) == 0
    assert _claims(cart_id) == 0


@pytest.mark.parametrize("key", ["", "unsafe key", "x" * 129])
def test_rejects_malformed_keys_without_writing(key: str) -> None:
    cart_id, user_id, guest_token = _new_cart()
    listing_id = str(uuid4())
    with _connection() as conn:
        with pytest.raises(psycopg.Error, match="cart.idempotency_key_invalid"):
            _call(
                conn,
                cart_id=cart_id,
                user_id=user_id,
                guest_token=guest_token,
                listing_id=listing_id,
                key=key,
            )
    assert _qty(cart_id, listing_id) == 0
    assert _claims(cart_id) == 0


def test_authenticated_role_cannot_execute_rpc() -> None:
    cart_id, user_id, guest_token = _new_cart()
    listing_id = str(uuid4())
    with _connection() as conn:
        with conn.cursor() as cur:
            cur.execute("set local role authenticated")
        with pytest.raises(psycopg.Error, match="permission denied for function"):
            _call(
                conn,
                cart_id=cart_id,
                user_id=user_id,
                guest_token=guest_token,
                listing_id=listing_id,
                key="client-blocked",
            )
    assert _claims(cart_id) == 0


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://postgres@localhost/cart_idem_test?host=other-host",
        "postgresql://postgres@localhost/cart_idem_test?dbname=another_database",
        "postgresql://postgres@localhost/cart_idem_test?service=another_service",
        "postgresql://postgres@other-host/cart_idem_test",
    ],
)
def test_target_guard_rejects_transport_overrides_before_connect(url: str) -> None:
    with pytest.raises(pytest.fail.Exception):
        _validated_target(url)


def test_stale_location_snapshot_does_not_claim_or_increment() -> None:
    cart_id, user_id, guest_token = _new_cart()
    listing_id, location_id = str(uuid4()), str(uuid4())
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            "insert into public.cart_items (cart_id,listing_id,qty,unit_price_ngwee,"
            "wholesale,pickup_location_id) values (%s,%s,2,1500,false,%s)",
            (cart_id, listing_id, location_id),
        )
    with _connection() as conn:
        assert (
            _call(
                conn,
                cart_id=cart_id,
                user_id=user_id,
                guest_token=guest_token,
                listing_id=listing_id,
                key="stale-location",
                expected_qty=2,
                expected_location_id=None,
                location_id=location_id,
            )
            == "stale"
        )
    assert _qty(cart_id, listing_id) == 2
    assert _claims(cart_id) == 0


def test_canonical_api_body_accepts_uppercase_uuid_rpc_input() -> None:
    cart_id, user_id, guest_token = _new_cart()
    listing_id = str(uuid4())
    canonical_body = {"listing_id": listing_id, "qty": 2}
    with _connection() as conn:
        assert (
            _call(
                conn,
                cart_id=cart_id,
                user_id=user_id,
                guest_token=guest_token,
                listing_id=listing_id.upper(),
                key="canonical-uuid",
                body=canonical_body,
            )
            == "applied"
        )
        assert (
            _call(
                conn,
                cart_id=cart_id,
                user_id=user_id,
                guest_token=guest_token,
                listing_id=listing_id,
                key="canonical-uuid",
                body=canonical_body,
            )
            == "replayed"
        )
    assert _qty(cart_id, listing_id) == 2
    assert _claims(cart_id) == 1
