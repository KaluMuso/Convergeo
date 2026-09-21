"""Database contract for the cross-worker login cart-merge transaction."""

from __future__ import annotations

import json
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import psycopg
import pytest
from tests.rls.conftest import SqlResult, seed_matrix_fixtures

_RPC_SQL = """
select public.apply_login_cart_merge(
  %(user_id)s::uuid,
  %(user_cart_id)s::uuid,
  %(guest_cart_id)s::uuid,
  %(guest_token)s::text,
  %(user_snapshot)s::jsonb,
  %(guest_snapshot)s::jsonb,
  %(proposal)s::jsonb
)::text
"""


class _PsycopgDb:
    """Windows-compatible DB harness; the broad RLS harness shells out to psql."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def run(self, sql: str) -> SqlResult:
        try:
            with psycopg.connect(self.dsn) as conn, conn.cursor() as cursor:
                cursor.execute(sql)
                rows = [str(row[0]) for row in cursor.fetchall()] if cursor.description else []
                return SqlResult(ok=True, rows=rows)
        except psycopg.Error as exc:
            return SqlResult(
                ok=False,
                rows=[],
                error=str(exc),
                sqlstate=exc.sqlstate,
            )


@pytest.fixture(scope="module")
def atomic_db() -> _PsycopgDb:
    db = _PsycopgDb(
        os.environ.get(
            "SUPABASE_DB_URL",
            "postgresql://postgres:postgres@127.0.0.1:54322/postgres",
        )
    )
    ready = db.run(
        "select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
        "where n.nspname = 'public' and p.proname = 'apply_login_cart_merge'"
    )
    if not ready.ok or ready.rows != ["1"]:
        pytest.skip("atomic cart-merge migration is not present on the local database")
    seed_matrix_fixtures(db)  # type: ignore[arg-type]
    return db


def _service_call(dsn: str, params: dict[str, Any], barrier: threading.Barrier) -> str:
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cursor:
            cursor.execute("set local role service_role")
            cursor.execute("set local request.jwt.claim.role = 'service_role'")
            barrier.wait(timeout=10)
            cursor.execute(_RPC_SQL, params)
            row = cursor.fetchone()
            assert row is not None
            return str(row[0])


def _seed_merge_case(db: _PsycopgDb) -> dict[str, Any]:
    user_id = str(uuid.uuid4())
    user_cart_id = str(uuid.uuid4())
    guest_cart_id = str(uuid.uuid4())
    user_line_id = str(uuid.uuid4())
    guest_line_id = str(uuid.uuid4())
    guest_token = f"merge-test-{uuid.uuid4()}"
    listings = db.run(
        "select id::text from public.vendor_listings order by id limit 3"
    )
    assert listings.ok, listings.error
    assert len(listings.rows) == 3
    user_listing_id, guest_listing_id, concurrent_listing_id = listings.rows

    seeded = db.run(
        f"""
        insert into auth.users (
          instance_id, id, aud, role, email, encrypted_password,
          email_confirmed_at, raw_app_meta_data, raw_user_meta_data, created_at, updated_at
        ) values (
          '00000000-0000-0000-0000-000000000000', '{user_id}',
          'authenticated', 'authenticated', '{user_id}@merge.test', 'hash',
          timezone('utc', now()), '{{}}'::jsonb, '{{}}'::jsonb,
          timezone('utc', now()), timezone('utc', now())
        );
        insert into public.carts (id, user_id, status)
        values ('{user_cart_id}', '{user_id}', 'active');
        insert into public.carts (id, guest_token, status)
        values ('{guest_cart_id}', '{guest_token}', 'active');
        insert into public.cart_items
          (id, cart_id, listing_id, qty, unit_price_ngwee, wholesale)
        values
          ('{user_line_id}', '{user_cart_id}', '{user_listing_id}', 1, 10000, false),
          ('{guest_line_id}', '{guest_cart_id}', '{guest_listing_id}', 1, 20000, false);
        """
    )
    assert seeded.ok, seeded.error

    user_snapshot = [
        {
            "id": user_line_id,
            "listing_id": user_listing_id,
            "qty": 1,
            "unit_price_ngwee": 10000,
            "wholesale": False,
            "pickup_location_id": None,
            "rfq_thread_id": None,
        }
    ]
    guest_snapshot = [
        {
            "id": guest_line_id,
            "listing_id": guest_listing_id,
            "qty": 1,
            "unit_price_ngwee": 20000,
            "wholesale": False,
            "pickup_location_id": None,
            "rfq_thread_id": None,
        }
    ]
    proposal = [
        {
            "listing_id": user_listing_id,
            "qty": 1,
            "unit_price_ngwee": 10000,
            "wholesale": False,
            "rfq_thread_id": None,
        },
        {
            "listing_id": guest_listing_id,
            "qty": 1,
            "unit_price_ngwee": 20000,
            "wholesale": False,
            "rfq_thread_id": None,
        },
    ]
    return {
        "user_id": user_id,
        "user_cart_id": user_cart_id,
        "guest_cart_id": guest_cart_id,
        "guest_token": guest_token,
        "user_snapshot": json.dumps(user_snapshot),
        "guest_snapshot": json.dumps(guest_snapshot),
        "proposal": json.dumps(proposal),
        "expected_listings": {user_listing_id, guest_listing_id},
        "user_listing_id": user_listing_id,
        "concurrent_listing_id": concurrent_listing_id,
    }


def test_two_database_merges_preserve_both_lines_exactly_once(atomic_db: _PsycopgDb) -> None:
    params = _seed_merge_case(atomic_db)
    barrier = threading.Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _index: _service_call(atomic_db.dsn, params, barrier),
                range(2),
            )
        )

    outcomes = {json.loads(result)["outcome"] for result in results}
    assert outcomes == {"applied", "already_converted"}

    final = atomic_db.run(
        "select listing_id::text from public.cart_items "
        f"where cart_id = '{params['user_cart_id']}' order by listing_id"
    )
    assert final.ok, final.error
    assert set(final.rows) == params["expected_listings"]
    assert len(final.rows) == 2

    converted = atomic_db.run(
        "select status from public.carts "
        f"where id = '{params['guest_cart_id']}'"
    )
    assert converted.ok, converted.error
    assert converted.rows == ["converted"]


def test_stale_snapshot_refuses_to_clobber_concurrent_account_line(
    atomic_db: _PsycopgDb,
) -> None:
    params = _seed_merge_case(atomic_db)
    concurrent_line_id = str(uuid.uuid4())
    mutation = atomic_db.run(
        "insert into public.cart_items "
        "(id, cart_id, listing_id, qty, unit_price_ngwee, wholesale) values ("
        f"'{concurrent_line_id}', '{params['user_cart_id']}', "
        f"'{params['concurrent_listing_id']}', 1, 30000, false)"
    )
    assert mutation.ok, mutation.error

    result = _service_call(atomic_db.dsn, params, threading.Barrier(1))
    assert json.loads(result)["outcome"] == "stale_snapshot"

    final = atomic_db.run(
        "select listing_id::text from public.cart_items "
        f"where cart_id = '{params['user_cart_id']}' order by listing_id"
    )
    assert final.ok, final.error
    assert set(final.rows) == {
        params["user_listing_id"],
        params["concurrent_listing_id"],
    }

    guest = atomic_db.run(
        "select status from public.carts "
        f"where id = '{params['guest_cart_id']}'"
    )
    assert guest.ok, guest.error
    assert guest.rows == ["active"]


def test_guest_insert_waiting_behind_merge_fails_instead_of_being_lost(
    atomic_db: _PsycopgDb,
) -> None:
    params = _seed_merge_case(atomic_db)
    insert_started = threading.Event()
    late_line_id = str(uuid.uuid4())

    def late_guest_insert() -> str | None:
        try:
            with psycopg.connect(atomic_db.dsn) as conn, conn.cursor() as cursor:
                cursor.execute("set local role service_role")
                cursor.execute("set local request.jwt.claim.role = 'service_role'")
                insert_started.set()
                cursor.execute(
                    "insert into public.cart_items "
                    "(id, cart_id, listing_id, qty, unit_price_ngwee, wholesale) values ("
                    f"'{late_line_id}', '{params['guest_cart_id']}', "
                    f"'{params['concurrent_listing_id']}', 1, 30000, false)"
                )
        except psycopg.Error as exc:
            return exc.sqlstate
        return None

    with psycopg.connect(atomic_db.dsn) as merge_conn:
        with merge_conn.cursor() as cursor:
            cursor.execute("set local role service_role")
            cursor.execute("set local request.jwt.claim.role = 'service_role'")
            cursor.execute(_RPC_SQL, params)
            row = cursor.fetchone()
            assert row is not None and json.loads(str(row[0]))["outcome"] == "applied"

            with ThreadPoolExecutor(max_workers=1) as executor:
                late_insert = executor.submit(late_guest_insert)
                assert insert_started.wait(timeout=10)
                merge_conn.commit()
                assert late_insert.result(timeout=10) == "40001"

    account = atomic_db.run(
        "select listing_id::text from public.cart_items "
        f"where cart_id = '{params['user_cart_id']}'"
    )
    assert account.ok, account.error
    assert set(account.rows) == params["expected_listings"]

    late_guest_line = atomic_db.run(
        "select count(*) from public.cart_items "
        f"where id = '{late_line_id}'"
    )
    assert late_guest_line.ok, late_guest_line.error
    assert late_guest_line.rows == ["0"]


def test_account_insert_waiting_behind_merge_commits_afterward(
    atomic_db: _PsycopgDb,
) -> None:
    params = _seed_merge_case(atomic_db)
    insert_started = threading.Event()
    late_line_id = str(uuid.uuid4())

    def late_account_insert() -> str | None:
        try:
            with psycopg.connect(atomic_db.dsn) as conn, conn.cursor() as cursor:
                cursor.execute("set local role service_role")
                cursor.execute("set local request.jwt.claim.role = 'service_role'")
                insert_started.set()
                cursor.execute(
                    "insert into public.cart_items "
                    "(id, cart_id, listing_id, qty, unit_price_ngwee, wholesale) values ("
                    f"'{late_line_id}', '{params['user_cart_id']}', "
                    f"'{params['concurrent_listing_id']}', 1, 30000, false)"
                )
        except psycopg.Error as exc:
            return exc.sqlstate
        return None

    with psycopg.connect(atomic_db.dsn) as merge_conn:
        with merge_conn.cursor() as cursor:
            cursor.execute("set local role service_role")
            cursor.execute("set local request.jwt.claim.role = 'service_role'")
            cursor.execute(_RPC_SQL, params)
            row = cursor.fetchone()
            assert row is not None and json.loads(str(row[0]))["outcome"] == "applied"

            with ThreadPoolExecutor(max_workers=1) as executor:
                late_insert = executor.submit(late_account_insert)
                assert insert_started.wait(timeout=10)
                merge_conn.commit()
                assert late_insert.result(timeout=10) is None

    account = atomic_db.run(
        "select listing_id::text from public.cart_items "
        f"where cart_id = '{params['user_cart_id']}'"
    )
    assert account.ok, account.error
    assert set(account.rows) == {
        *params["expected_listings"],
        params["concurrent_listing_id"],
    }


def test_rpc_execute_is_service_role_only(atomic_db: _PsycopgDb) -> None:
    signature = (
        "public.apply_login_cart_merge"
        "(uuid,uuid,uuid,text,jsonb,jsonb,jsonb)"
    )
    privileges = atomic_db.run(
        "select "
        f"has_function_privilege('anon', '{signature}', 'EXECUTE')::text || ',' || "
        f"has_function_privilege('authenticated', '{signature}', 'EXECUTE')::text || ',' || "
        f"has_function_privilege('service_role', '{signature}', 'EXECUTE')::text"
    )
    assert privileges.ok, privileges.error
    assert privileges.rows == ["false,false,true"]

    attributes = atomic_db.run(
        "select p.prosecdef::text || ',' || array_to_string(p.proconfig, ';') "
        "from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
        "where n.nspname = 'public' and p.proname = 'apply_login_cart_merge'"
    )
    assert attributes.ok, attributes.error
    assert attributes.rows == ["false,search_path=pg_catalog, public"]


def test_rpc_rejects_wrong_verified_guest_token(atomic_db: _PsycopgDb) -> None:
    params = _seed_merge_case(atomic_db)
    result = atomic_db.run(
        "select public.apply_login_cart_merge("
        f"'{params['user_id']}'::uuid, "
        f"'{params['user_cart_id']}'::uuid, "
        f"'{params['guest_cart_id']}'::uuid, "
        "'wrong-token', '[]'::jsonb, '[]'::jsonb, '[]'::jsonb)"
    )
    assert not result.ok
    assert result.sqlstate == "42501"
    assert result.error is not None and "guest cart identity mismatch" in result.error
