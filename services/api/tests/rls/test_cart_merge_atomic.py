"""Database contract for the cross-worker login cart-merge transaction."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx
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
  %(authority)s::jsonb,
  %(proposal)s::jsonb,
  %(removed)s::jsonb,
  %(resolution)s::jsonb
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
    listings = db.run("select id::text from public.vendor_listings order by id limit 3")
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
            "pickup_location_id": None,
            "rfq_thread_id": None,
        },
        {
            "listing_id": guest_listing_id,
            "qty": 1,
            "unit_price_ngwee": 20000,
            "wholesale": False,
            "pickup_location_id": None,
            "rfq_thread_id": None,
        },
    ]
    authority_result = db.run(
        "select public.cart_merge_authority("
        f"'{user_id}'::uuid, "
        f"array['{user_listing_id}','{guest_listing_id}']::uuid[], "
        "array[]::uuid[])::text"
    )
    assert authority_result.ok, authority_result.error
    return {
        "user_id": user_id,
        "user_cart_id": user_cart_id,
        "guest_cart_id": guest_cart_id,
        "guest_token": guest_token,
        "user_snapshot": json.dumps(user_snapshot),
        "guest_snapshot": json.dumps(guest_snapshot),
        "authority": authority_result.rows[0],
        "proposal": json.dumps(proposal),
        "removed": "[]",
        "resolution": "{}",
        "expected_listings": {user_listing_id, guest_listing_id},
        "user_line_id": user_line_id,
        "guest_line_id": guest_line_id,
        "user_listing_id": user_listing_id,
        "guest_listing_id": guest_listing_id,
        "concurrent_listing_id": concurrent_listing_id,
    }


def _service_error(db: _PsycopgDb, params: dict[str, Any]) -> tuple[str | None, str]:
    try:
        _service_call(db.dsn, params, threading.Barrier(1))
    except psycopg.Error as exc:
        return exc.sqlstate, str(exc)
    raise AssertionError("merge unexpectedly succeeded")


def _authority(db: _PsycopgDb, user_id: str, listing_ids: list[str]) -> str:
    ids = ",".join(f"'{listing_id}'" for listing_id in listing_ids)
    result = db.run(
        "select public.cart_merge_authority("
        f"'{user_id}'::uuid, array[{ids}]::uuid[], array[]::uuid[])::text"
    )
    assert result.ok, result.error
    return result.rows[0]


def _wait_for_lock_wait(db: _PsycopgDb, pid: int) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = db.run(
            "select count(*)::text from pg_stat_activity "
            f"where pid = {pid} and wait_event_type = 'Lock'"
        )
        assert result.ok, result.error
        if int(result.rows[0]) > 0:
            return
    raise AssertionError(f"connection {pid} did not reach a lock wait")


def test_unrelated_cart_and_authority_progress_during_merge(atomic_db: _PsycopgDb) -> None:
    params = _seed_merge_case(atomic_db)
    other_cart = str(uuid.uuid4())
    other_line = str(uuid.uuid4())
    seeded = atomic_db.run(
        f"insert into public.carts (id, guest_token, status) "
        f"values ('{other_cart}', 'unrelated-{other_cart}', 'active')"
    )
    assert seeded.ok, seeded.error

    def unrelated_write() -> None:
        with psycopg.connect(atomic_db.dsn) as conn, conn.cursor() as cursor:
            cursor.execute("set local role service_role")
            cursor.execute("set local statement_timeout = '5s'")
            cursor.execute(
                "insert into public.cart_items "
                "(id, cart_id, listing_id, qty, unit_price_ngwee, wholesale) "
                "values (%s, %s, %s, 1, 30000, false)",
                (other_line, other_cart, params["concurrent_listing_id"]),
            )
            cursor.execute(
                "update public.vendor_listings set price_ngwee = price_ngwee + 1 where id = %s",
                (params["concurrent_listing_id"],),
            )

    with psycopg.connect(atomic_db.dsn) as merge_conn, merge_conn.cursor() as cursor:
        cursor.execute("set local role service_role")
        cursor.execute(_RPC_SQL, params)
        assert json.loads(str(cursor.fetchone()[0]))["outcome"] == "applied"
        with ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(unrelated_write).result(timeout=10)
        merge_conn.commit()

    result = atomic_db.run(
        f"select count(*)::text from public.cart_items where id = '{other_line}'"
    )
    assert result.ok and result.rows == ["1"], result.error


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
    assert "applied" in outcomes
    assert outcomes.issubset({"applied", "stale_snapshot", "already_converted"})
    # A non-waiting scoped lock may reject the simultaneous caller. Retrying
    # after the winner commits must find the same receipt, never insert twice.
    assert (
        json.loads(_service_call(atomic_db.dsn, params, threading.Barrier(1)))["outcome"]
        == "already_converted"
    )

    final = atomic_db.run(
        "select listing_id::text from public.cart_items "
        f"where cart_id = '{params['user_cart_id']}' order by listing_id"
    )
    assert final.ok, final.error
    assert set(final.rows) == params["expected_listings"]
    assert len(final.rows) == 2

    converted_sql = f"select status from public.carts where id = '{params['guest_cart_id']}'"
    converted = atomic_db.run(converted_sql)
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

    guest = atomic_db.run(f"select status from public.carts where id = '{params['guest_cart_id']}'")
    assert guest.ok, guest.error
    assert guest.rows == ["active"]

    params["user_snapshot"] = json.dumps(
        [
            *json.loads(params["user_snapshot"]),
            {
                "id": concurrent_line_id,
                "listing_id": params["concurrent_listing_id"],
                "qty": 1,
                "unit_price_ngwee": 30000,
                "wholesale": False,
                "pickup_location_id": None,
                "rfq_thread_id": None,
            },
        ]
    )
    params["proposal"] = json.dumps(
        [
            *json.loads(params["proposal"]),
            {
                "listing_id": params["concurrent_listing_id"],
                "qty": 1,
                "unit_price_ngwee": 30000,
                "wholesale": False,
                "pickup_location_id": None,
                "rfq_thread_id": None,
            },
        ]
    )
    params["authority"] = _authority(
        atomic_db,
        params["user_id"],
        [
            params["user_listing_id"],
            params["guest_listing_id"],
            params["concurrent_listing_id"],
        ],
    )
    # The wire snapshot is canonical by row id, including newly appended rows.
    params["user_snapshot"] = json.dumps(
        sorted(json.loads(params["user_snapshot"]), key=lambda row: row["id"])
    )
    retry = _service_call(atomic_db.dsn, params, threading.Barrier(1))
    assert json.loads(retry)["outcome"] == "applied"


def test_empty_guest_cart_preserves_account_lines(atomic_db: _PsycopgDb) -> None:
    params = _seed_merge_case(atomic_db)
    deleted = atomic_db.run(f"delete from public.cart_items where id = '{params['guest_line_id']}'")
    assert deleted.ok, deleted.error
    params["guest_snapshot"] = "[]"
    params["proposal"] = json.dumps([json.loads(params["user_snapshot"])[0]])
    params["authority"] = _authority(atomic_db, params["user_id"], [params["user_listing_id"]])

    result = _service_call(atomic_db.dsn, params, threading.Barrier(1))
    assert json.loads(result)["outcome"] == "applied"
    final = atomic_db.run(
        f"select listing_id::text from public.cart_items where cart_id = '{params['user_cart_id']}'"
    )
    assert final.rows == [params["user_listing_id"]]


def test_same_sku_quantities_are_conserved(atomic_db: _PsycopgDb) -> None:
    params = _seed_merge_case(atomic_db)
    changed = atomic_db.run(
        "update public.cart_items "
        f"set listing_id = '{params['user_listing_id']}' "
        f"where id = '{params['guest_line_id']}'"
    )
    assert changed.ok, changed.error
    guest = json.loads(params["guest_snapshot"])[0]
    guest["listing_id"] = params["user_listing_id"]
    params["guest_snapshot"] = json.dumps([guest])
    proposal = json.loads(params["proposal"])[0]
    proposal["qty"] = 2
    params["proposal"] = json.dumps([proposal])
    params["authority"] = _authority(atomic_db, params["user_id"], [params["user_listing_id"]])

    result = _service_call(atomic_db.dsn, params, threading.Barrier(1))
    assert json.loads(result)["outcome"] == "applied"
    final = atomic_db.run(
        f"select qty::text from public.cart_items where cart_id = '{params['user_cart_id']}'"
    )
    assert final.rows == ["2"]


def test_rpc_refuses_silent_item_loss_and_rolls_back(atomic_db: _PsycopgDb) -> None:
    params = _seed_merge_case(atomic_db)
    params["proposal"] = json.dumps([json.loads(params["user_snapshot"])[0]])

    sqlstate, message = _service_error(atomic_db, params)
    assert sqlstate == "PT409"
    assert "conserve or explicitly remove" in message
    guest = atomic_db.run(f"select status from public.carts where id = '{params['guest_cart_id']}'")
    assert guest.rows == ["active"]
    account = atomic_db.run(
        f"select count(*)::text from public.cart_items where cart_id = '{params['user_cart_id']}'"
    )
    assert account.rows == ["1"]


def test_pickup_location_cannot_be_dropped_and_is_preserved(atomic_db: _PsycopgDb) -> None:
    params = _seed_merge_case(atomic_db)
    locations = atomic_db.run("select id::text from public.vendor_locations order by id limit 1")
    assert locations.ok and locations.rows, locations.error
    location_id = locations.rows[0]
    changed = atomic_db.run(
        "update public.cart_items "
        f"set pickup_location_id = '{location_id}' "
        f"where id = '{params['guest_line_id']}'"
    )
    assert changed.ok, changed.error
    guest = json.loads(params["guest_snapshot"])[0]
    guest["pickup_location_id"] = location_id
    params["guest_snapshot"] = json.dumps([guest])

    sqlstate, message = _service_error(atomic_db, params)
    assert sqlstate == "PT409"
    assert "pickup location must be preserved" in message

    proposal = json.loads(params["proposal"])
    proposal[1]["pickup_location_id"] = location_id
    params["proposal"] = json.dumps(proposal)
    result = _service_call(atomic_db.dsn, params, threading.Barrier(1))
    assert json.loads(result)["outcome"] == "applied"
    final = atomic_db.run(
        "select pickup_location_id::text from public.cart_items "
        f"where cart_id = '{params['user_cart_id']}' "
        f"and listing_id = '{params['guest_listing_id']}'"
    )
    assert final.rows == [location_id]


def test_different_pickups_require_recorded_resolution(atomic_db: _PsycopgDb) -> None:
    params = _seed_merge_case(atomic_db)
    locations = atomic_db.run("select id::text from public.vendor_locations order by id limit 2")
    if len(locations.rows) < 2:
        pytest.skip("fixture needs two vendor locations")
    location_a, location_b = locations.rows
    changed = atomic_db.run(
        "update public.cart_items "
        f"set pickup_location_id = '{location_a}' "
        f"where id = '{params['user_line_id']}'; "
        "update public.cart_items "
        f"set listing_id = '{params['user_listing_id']}', pickup_location_id = '{location_b}' "
        f"where id = '{params['guest_line_id']}'"
    )
    assert changed.ok, changed.error
    user = json.loads(params["user_snapshot"])[0]
    guest = json.loads(params["guest_snapshot"])[0]
    user["pickup_location_id"] = location_a
    guest["listing_id"] = params["user_listing_id"]
    guest["pickup_location_id"] = location_b
    params["user_snapshot"] = json.dumps([user])
    params["guest_snapshot"] = json.dumps([guest])
    proposal = json.loads(params["proposal"])[0]
    proposal["qty"] = 2
    proposal["pickup_location_id"] = location_b
    params["proposal"] = json.dumps([proposal])
    params["authority"] = _authority(atomic_db, params["user_id"], [params["user_listing_id"]])

    sqlstate, _ = _service_error(atomic_db, params)
    assert sqlstate == "PT409"
    params["resolution"] = json.dumps(
        {"pickup_location_choices": {params["user_listing_id"]: location_b}}
    )
    result = _service_call(atomic_db.dsn, params, threading.Barrier(1))
    assert json.loads(result)["outcome"] == "applied"
    receipt = atomic_db.run(
        "select resolution -> 'pickup_location_choices' ->> "
        f"'{params['user_listing_id']}' from public.cart_merge_receipts "
        f"where guest_cart_id = '{params['guest_cart_id']}'"
    )
    assert receipt.rows == [location_b]


def test_authority_change_returns_stale_without_consuming_guest(
    atomic_db: _PsycopgDb,
) -> None:
    params = _seed_merge_case(atomic_db)
    changed = atomic_db.run(
        "update public.vendor_listings set price_ngwee = price_ngwee + 1 "
        f"where id = '{params['guest_listing_id']}'"
    )
    assert changed.ok, changed.error

    result = _service_call(atomic_db.dsn, params, threading.Barrier(1))
    assert json.loads(result)["outcome"] == "stale_authority"
    guest = atomic_db.run(f"select status from public.carts where id = '{params['guest_cart_id']}'")
    assert guest.rows == ["active"]


def test_service_role_works_through_real_postgrest_and_anon_is_denied(
    atomic_db: _PsycopgDb,
) -> None:
    rest_url = os.environ.get("SUPABASE_REST_URL")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    anon_key = os.environ.get("SUPABASE_ANON_KEY")
    if not rest_url or not service_key or not anon_key:
        pytest.skip("real PostgREST credentials were not provided")
    params = _seed_merge_case(atomic_db)
    payload = {
        "p_user_id": params["user_id"],
        "p_user_cart_id": params["user_cart_id"],
        "p_guest_cart_id": params["guest_cart_id"],
        "p_guest_token": params["guest_token"],
        "p_expected_user_items": json.loads(params["user_snapshot"]),
        "p_expected_guest_items": json.loads(params["guest_snapshot"]),
        "p_expected_authority": json.loads(params["authority"]),
        "p_merged_items": json.loads(params["proposal"]),
        "p_removed_items": [],
        "p_resolution": {},
    }
    with httpx.Client(timeout=10) as client:
        denied = client.post(
            f"{rest_url}/rpc/apply_login_cart_merge",
            headers={"apikey": anon_key, "Authorization": f"Bearer {anon_key}"},
            json=payload,
        )
        accepted = client.post(
            f"{rest_url}/rpc/apply_login_cart_merge",
            headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
            json=payload,
        )

    assert denied.status_code in {401, 403, 404}
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["outcome"] == "applied"


def test_guest_insert_waiting_behind_merge_fails_instead_of_being_lost(
    atomic_db: _PsycopgDb,
) -> None:
    params = _seed_merge_case(atomic_db)
    insert_started = threading.Event()
    insert_pid: list[int] = []
    late_line_id = str(uuid.uuid4())

    def late_guest_insert() -> str | None:
        try:
            with psycopg.connect(atomic_db.dsn) as conn, conn.cursor() as cursor:
                cursor.execute("set local role service_role")
                cursor.execute("select pg_backend_pid()")
                insert_pid.append(int(cursor.fetchone()[0]))
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
            cursor.execute(_RPC_SQL, params)
            row = cursor.fetchone()
            assert row is not None and json.loads(str(row[0]))["outcome"] == "applied"

            with ThreadPoolExecutor(max_workers=1) as executor:
                late_insert = executor.submit(late_guest_insert)
                assert insert_started.wait(timeout=10)
                _wait_for_lock_wait(atomic_db, insert_pid[0])
                merge_conn.commit()
                assert late_insert.result(timeout=10) == "PT409"

    account = atomic_db.run(
        f"select listing_id::text from public.cart_items where cart_id = '{params['user_cart_id']}'"
    )
    assert account.ok, account.error
    assert set(account.rows) == params["expected_listings"]

    late_guest_sql = f"select count(*) from public.cart_items where id = '{late_line_id}'"
    late_guest_line = atomic_db.run(late_guest_sql)
    assert late_guest_line.ok, late_guest_line.error
    assert late_guest_line.rows == ["0"]


def test_account_insert_waiting_behind_merge_commits_afterward(
    atomic_db: _PsycopgDb,
) -> None:
    params = _seed_merge_case(atomic_db)
    insert_started = threading.Event()
    insert_pid: list[int] = []
    late_line_id = str(uuid.uuid4())

    def late_account_insert() -> str | None:
        try:
            with psycopg.connect(atomic_db.dsn) as conn, conn.cursor() as cursor:
                cursor.execute("set local role service_role")
                cursor.execute("select pg_backend_pid()")
                insert_pid.append(int(cursor.fetchone()[0]))
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
            cursor.execute(_RPC_SQL, params)
            row = cursor.fetchone()
            assert row is not None and json.loads(str(row[0]))["outcome"] == "applied"

            with ThreadPoolExecutor(max_workers=1) as executor:
                late_insert = executor.submit(late_account_insert)
                assert insert_started.wait(timeout=10)
                _wait_for_lock_wait(atomic_db, insert_pid[0])
                merge_conn.commit()
                assert late_insert.result(timeout=10) is None

    account = atomic_db.run(
        f"select listing_id::text from public.cart_items where cart_id = '{params['user_cart_id']}'"
    )
    assert account.ok, account.error
    assert set(account.rows) == {
        *params["expected_listings"],
        params["concurrent_listing_id"],
    }


@pytest.mark.parametrize(
    ("mutation_sql", "expected_rows"),
    [
        ("update public.cart_items set qty = 7 where id = '{line_id}'", ["7"]),
        ("delete from public.cart_items where id = '{line_id}'", []),
    ],
    ids=["simultaneous-update", "simultaneous-delete"],
)
def test_account_mutations_wait_and_apply_after_merge(
    atomic_db: _PsycopgDb,
    mutation_sql: str,
    expected_rows: list[str],
) -> None:
    params = _seed_merge_case(atomic_db)
    started = threading.Event()
    mutation_pid: list[int] = []

    def mutate() -> str | None:
        try:
            with psycopg.connect(atomic_db.dsn) as conn, conn.cursor() as cursor:
                cursor.execute("set local role service_role")
                cursor.execute("select pg_backend_pid()")
                mutation_pid.append(int(cursor.fetchone()[0]))
                started.set()
                cursor.execute(mutation_sql.format(line_id=params["user_line_id"]))
        except psycopg.Error as exc:
            return exc.sqlstate
        return None

    with psycopg.connect(atomic_db.dsn) as merge_conn, merge_conn.cursor() as cursor:
        cursor.execute("set local role service_role")
        cursor.execute(_RPC_SQL, params)
        assert json.loads(str(cursor.fetchone()[0]))["outcome"] == "applied"
        with ThreadPoolExecutor(max_workers=1) as executor:
            mutation = executor.submit(mutate)
            assert started.wait(timeout=10)
            _wait_for_lock_wait(atomic_db, mutation_pid[0])
            merge_conn.commit()
            assert mutation.result(timeout=10) is None

    final = atomic_db.run(
        f"select qty::text from public.cart_items where id = '{params['user_line_id']}'"
    )
    assert final.rows == expected_rows


def test_authority_writer_precedes_merge_and_forces_recompute(
    atomic_db: _PsycopgDb,
) -> None:
    params = _seed_merge_case(atomic_db)
    merge_started = threading.Event()

    def merge() -> str:
        merge_started.set()
        return _service_call(atomic_db.dsn, params, threading.Barrier(1))

    with psycopg.connect(atomic_db.dsn) as authority_conn, authority_conn.cursor() as cursor:
        cursor.execute(
            "update public.vendor_listings set price_ngwee = price_ngwee + 1 where id = %s",
            (params["guest_listing_id"],),
        )
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending_merge = executor.submit(merge)
            assert merge_started.wait(timeout=10)
            outcome = json.loads(pending_merge.result(timeout=10))["outcome"]
            authority_conn.commit()

    assert outcome == "stale_authority"


def test_concurrent_first_login_creates_one_account_cart(atomic_db: _PsycopgDb) -> None:
    user_id = str(uuid.uuid4())
    inserted = atomic_db.run(
        "insert into auth.users (instance_id,id,aud,role,email,encrypted_password,"
        "email_confirmed_at,raw_app_meta_data,raw_user_meta_data,created_at,updated_at) values ("
        f"'00000000-0000-0000-0000-000000000000','{user_id}','authenticated',"
        f"'authenticated','{user_id}@merge.test','hash',timezone('utc',now()),"
        "'{}'::jsonb,'{}'::jsonb,timezone('utc',now()),timezone('utc',now()))"
    )
    assert inserted.ok, inserted.error
    barrier = threading.Barrier(4)

    def ensure() -> str:
        with psycopg.connect(atomic_db.dsn) as conn, conn.cursor() as cursor:
            cursor.execute("set local role service_role")
            barrier.wait(timeout=10)
            cursor.execute("select public.ensure_account_cart(%s)::text", (user_id,))
            return str(cursor.fetchone()[0])

    with ThreadPoolExecutor(max_workers=4) as executor:
        cart_ids = list(executor.map(lambda _index: ensure(), range(4)))
    assert len(set(cart_ids)) == 1
    count = atomic_db.run(
        f"select count(*)::text from public.carts where user_id = '{user_id}' and status = 'active'"
    )
    assert count.rows == ["1"]


def test_rpc_execute_is_service_role_only(atomic_db: _PsycopgDb) -> None:
    signature = (
        "public.apply_login_cart_merge(uuid,uuid,uuid,text,jsonb,jsonb,jsonb,jsonb,jsonb,jsonb)"
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
        "set local role service_role; select public.apply_login_cart_merge("
        f"'{params['user_id']}'::uuid, "
        f"'{params['user_cart_id']}'::uuid, "
        f"'{params['guest_cart_id']}'::uuid, "
        "'wrong-token', '[]'::jsonb, '[]'::jsonb, '{}'::jsonb, "
        "'[]'::jsonb, '[]'::jsonb, '{}'::jsonb)"
    )
    assert not result.ok
    assert result.sqlstate == "42501"
    assert result.error is not None and "guest cart identity mismatch" in result.error


def test_product_writer_conflicts_without_waiting_and_refreshes_authority(
    atomic_db: _PsycopgDb,
) -> None:
    params = _seed_merge_case(atomic_db)
    row = atomic_db.run(
        "select product_id::text from public.vendor_listings "
        f"where id = '{params['guest_listing_id']}'"
    )
    product_id = row.rows[0]
    # Test the product-derived display name, not a listing title override.
    assert atomic_db.run(
        "update public.vendor_listings set title_override = null "
        f"where id = '{params['guest_listing_id']}'"
    ).ok
    params["authority"] = _authority(
        atomic_db, params["user_id"], list(params["expected_listings"])
    )
    with psycopg.connect(atomic_db.dsn) as writer:
        writer.execute(
            "update public.products set name = name || ' revised' where id = %s", (product_id,)
        )
        with ThreadPoolExecutor(max_workers=1) as executor:
            result = executor.submit(_service_call, atomic_db.dsn, params, threading.Barrier(1))
            assert json.loads(result.result(timeout=3))["outcome"] == "stale_authority"
        writer.commit()
    assert (
        json.loads(_service_call(atomic_db.dsn, params, threading.Barrier(1)))["outcome"]
        == "stale_authority"
    )
    params["authority"] = _authority(
        atomic_db, params["user_id"], list(params["expected_listings"])
    )
    assert (
        json.loads(_service_call(atomic_db.dsn, params, threading.Barrier(1)))["outcome"]
        == "applied"
    )


def test_product_writer_serializes_after_merge_and_unrelated_product_progresses(
    atomic_db: _PsycopgDb,
) -> None:
    params = _seed_merge_case(atomic_db)
    product_id = atomic_db.run(
        "select product_id::text from public.vendor_listings "
        f"where id = '{params['guest_listing_id']}'"
    ).rows[0]
    unrelated = str(uuid.uuid4())
    seeded = atomic_db.run(
        "insert into public.products (id, name, slug, category_id) "
        f"select '{unrelated}', 'Unrelated merge product', 'unrelated-{unrelated}', "
        f"category_id from public.products where id = '{product_id}'"
    )
    assert seeded.ok, seeded.error
    started = threading.Event()
    pid: list[int] = []

    def edit() -> None:
        with psycopg.connect(atomic_db.dsn) as writer:
            pid.append(writer.execute("select pg_backend_pid()").fetchone()[0])
            started.set()
            writer.execute(
                "update public.products set name = name || ' later' where id = %s", (product_id,)
            )

    with psycopg.connect(atomic_db.dsn) as merge:
        merge.execute("set local role service_role")
        assert json.loads(merge.execute(_RPC_SQL, params).fetchone()[0])["outcome"] == "applied"
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(edit)
            try:
                assert started.wait(3)
                _wait_for_lock_wait(atomic_db, pid[0])
                with psycopg.connect(atomic_db.dsn) as other:
                    other.execute("set local statement_timeout = '2s'")
                    other.execute(
                        "update public.products set name = name where id = %s", (unrelated,)
                    )
                    other.execute(
                        "insert into public.carts (guest_token, status) values (%s, 'active')",
                        (str(uuid.uuid4()),),
                    )
            finally:
                merge.commit()
            future.result(timeout=3)
