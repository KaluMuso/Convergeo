"""Actual PostgreSQL controls; no table doubles and no production connection.

Run only on a disposable migrated local DB with MERCHANT_STOCK_ISOLATED_DB=1.
The unchanged test_location_stock.py remains a separate required gate.
"""

import concurrent.futures
import json
import os
import threading
import uuid
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest
from app.services.stock.claim import claim_reservation
from app.services.stock.release import release_reservation
from tests.rls.conftest import (
    PgConn,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)
from tests.test_location_stock import (
    VENDOR_ID,
    _branch_stock_qty,
    _insert_branch,
    _insert_branch_stock,
    _insert_checkout_group,
    _insert_tracked_listing,
    _legacy_stock_qty,
)

ACTOR = "33333333-3333-3333-3333-333333333333"


@pytest.fixture(scope="module")
def db() -> Generator[PgConn, None, None]:
    assert os.environ.get("MERCHANT_STOCK_ISOLATED_DB") == "1", "Disposable DB attestation required"
    url = resolve_db_url()
    assert urlparse(url).hostname in {"127.0.0.1", "localhost", "::1", None}, "Local DB only"
    conn = PgConn(url)
    assert conn.run("SELECT 1").ok, "Actual PostgreSQL is required; do not replace with doubles"
    if not schema_ready(conn):
        apply_migrations(conn)
    present = conn.run("SELECT to_regclass('public.vendor_stock_operations')::text")
    assert present.ok
    if not present.rows:
        migration = (
            Path(__file__).resolve().parents[3]
            / "supabase/migrations/20260930170100_vendor_stock_adjustment_authority.sql"
        )
        result = conn.run(migration.read_text())
        assert result.ok, result.error
    seed_matrix_fixtures(conn)
    old = os.environ.get("SUPABASE_DB_URL")
    os.environ["SUPABASE_DB_URL"] = url
    yield conn
    if old is None:
        os.environ.pop("SUPABASE_DB_URL", None)
    else:
        os.environ["SUPABASE_DB_URL"] = old


@pytest.fixture
def item(db: PgConn) -> tuple[str, str, str]:
    listing, a, b = (str(uuid.uuid4()) for _ in range(3))
    _insert_tracked_listing(db, listing_id=listing, stock_qty=90)
    for branch in (a, b):
        _insert_branch(db, location_id=branch, lat=-15.4, lng=28.3, landmark="Stock test")
        _insert_branch_stock(db, listing_id=listing, location_id=branch, stock_qty=10)
    assert _branch_stock_qty(db, listing, a) == 10
    return listing, a, b


def adjust(
    db: PgConn,
    listing: str,
    location: str | None,
    delta: int,
    operation: str | None = None,
    actor: str = ACTOR,
    reason: str = "delivery",
    unit: str = "each",
) -> dict[str, Any]:
    operation = operation or str(uuid.uuid4())
    loc = f"'{location}'::uuid" if location else "null::uuid"
    reason_sql = reason.replace("'", "''")
    result = db.run(f"""BEGIN;
      SET LOCAL ROLE service_role;
      SET LOCAL lock_timeout = '3s';
      SET LOCAL statement_timeout = '10s';
      SELECT public.adjust_vendor_stock('{actor}', '{VENDOR_ID}', '{listing}', {loc},
        '{operation}', {delta}, '{reason_sql}', '{unit}', 1000)::text;
      COMMIT;""")
    assert result.ok, result.error
    outcome = json.loads(result.rows[-1])
    assert isinstance(outcome, dict)
    return outcome


def race(*calls: Callable[[], Any]) -> list[Any]:
    barrier = threading.Barrier(len(calls))

    def run(call: Callable[[], Any]) -> Any:
        barrier.wait(timeout=10)
        return call()

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(calls)) as pool:
        futures = [pool.submit(run, call) for call in calls]
        return [future.result(timeout=20) for future in futures]


def test_reserve_vs_adjust_and_release_conserve_physical_units(
    db: PgConn, item: tuple[str, str, str]
) -> None:
    listing, a, b = item
    group = str(uuid.uuid4())
    _insert_checkout_group(db, group)
    results = race(
        lambda: claim_reservation(
            listing_id=listing, checkout_group_id=group, qty=3, ttl_minutes=15, location_id=a
        ),
        lambda: adjust(db, listing, a, 5),
    )
    assert results[0].claimed and results[1]["ok"]
    assert _branch_stock_qty(db, listing, a) == 12
    assert _branch_stock_qty(db, listing, b) == 10
    assert _legacy_stock_qty(db, listing) == 90
    assert release_reservation(listing_id=listing, checkout_group_id=group).released
    assert not release_reservation(listing_id=listing, checkout_group_id=group).released
    assert _branch_stock_qty(db, listing, a) == 15


def test_simultaneous_adjustments_and_duplicate_operation(
    db: PgConn, item: tuple[str, str, str]
) -> None:
    listing, a, _ = item
    operation = str(uuid.uuid4())
    outcomes = race(
        lambda: adjust(db, listing, a, 2, operation), lambda: adjust(db, listing, a, 2, operation)
    )
    assert outcomes[0] == outcomes[1]
    assert outcomes[0]["old_qty"] == 10 and outcomes[0]["new_qty"] == 12
    assert _branch_stock_qty(db, listing, a) == 12
    results = race(lambda: adjust(db, listing, a, 3), lambda: adjust(db, listing, a, -2))
    assert all(result["ok"] for result in results)
    assert _branch_stock_qty(db, listing, a) == 13


@pytest.mark.parametrize("changed", ["delta", "reason", "location", "unit"])
def test_changed_payload_replay_is_rejected(
    db: PgConn, item: tuple[str, str, str], changed: str
) -> None:
    listing, a, b = item
    operation = str(uuid.uuid4())
    original = adjust(db, listing, a, 2, operation)
    result = adjust(
        db,
        listing,
        b if changed == "location" else a,
        3 if changed == "delta" else 2,
        operation,
        reason="changed" if changed == "reason" else "delivery",
        unit="kg" if changed == "unit" else "each",
    )
    assert result["code"] == "stock.operation_conflict"
    assert adjust(db, listing, a, 2, operation) == original
    assert _branch_stock_qty(db, listing, a) == 12
    assert _branch_stock_qty(db, listing, b) == 10


def test_last_item_adjust_vs_reserve_exactly_one_wins(
    db: PgConn, item: tuple[str, str, str]
) -> None:
    listing, a, _ = item
    assert adjust(db, listing, a, -9)["ok"]
    group = str(uuid.uuid4())
    _insert_checkout_group(db, group)
    claimed, adjusted = race(
        lambda: claim_reservation(
            listing_id=listing, checkout_group_id=group, qty=1, ttl_minutes=15, location_id=a
        ),
        lambda: adjust(db, listing, a, -1),
    )
    assert int(claimed.claimed) + int(adjusted["ok"]) == 1
    assert _branch_stock_qty(db, listing, a) == 0


@pytest.mark.parametrize(
    "case", ["empty", "inactive", "foreign_location", "foreign_actor", "missing_location"]
)
def test_rejections_never_change_branch_or_pool(
    db: PgConn, item: tuple[str, str, str], case: str
) -> None:
    listing, a, b = item
    target = a
    if case == "inactive":
        assert db.run(f"UPDATE public.vendor_locations SET status='closed' WHERE id='{a}'").ok
    if case == "foreign_location":
        target = str(uuid.uuid4())
        assert db.run(
            "INSERT INTO public.vendor_locations(id,vendor_id,lat,lng,landmark) VALUES "
            f"('{target}','bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',-15.4,28.3,'Other vendor')"
        ).ok
    if case == "empty":
        assert adjust(db, listing, a, -10)["ok"]
    before = _branch_stock_qty(db, listing, a)
    result = adjust(
        db,
        listing,
        None if case == "missing_location" else target,
        -1 if case == "empty" else 1,
        actor="44444444-4444-4444-4444-444444444444" if case == "foreign_actor" else ACTOR,
    )
    assert not result["ok"]
    assert _branch_stock_qty(db, listing, a) == before
    assert _branch_stock_qty(db, listing, b) == 10
    assert _legacy_stock_qty(db, listing) == 90


def test_legacy_pool_adjustment_uses_same_replay_authority(db: PgConn) -> None:
    listing = str(uuid.uuid4())
    _insert_tracked_listing(db, listing_id=listing, stock_qty=10)
    operation = str(uuid.uuid4())
    first = adjust(db, listing, None, -3, operation)
    assert first["ok"] and first["new_qty"] == 7
    assert adjust(db, listing, None, -3, operation) == first
    assert _legacy_stock_qty(db, listing) == 7


def test_browser_role_cannot_write_inventory_or_invoke_service_rpc(
    db: PgConn, item: tuple[str, str, str]
) -> None:
    listing, a, _ = item
    denied = db.run_as(
        "authenticated",
        f"UPDATE public.vendor_listings SET stock_qty=999 WHERE id='{listing}'",
        user_id=ACTOR,
    )
    assert not denied.ok
    denied = db.run_as(
        "authenticated",
        "UPDATE public.listing_location_stock SET stock_qty=999 "
        f"WHERE listing_id='{listing}' AND location_id='{a}'",
        user_id=ACTOR,
    )
    assert not denied.ok
    denied = db.run_as(
        "authenticated",
        f"SELECT public.adjust_vendor_stock('{ACTOR}', '{VENDOR_ID}', '{listing}', '{a}', "
        f"'{uuid.uuid4()}', 1, 'test', 'each', 1000)",
        user_id=ACTOR,
    )
    assert not denied.ok
    assert _branch_stock_qty(db, listing, a) == 10


def test_stocked_location_cannot_be_deleted_or_reassigned(
    db: PgConn, item: tuple[str, str, str]
) -> None:
    listing, a, _ = item
    result = db.run_as(
        "authenticated", f"DELETE FROM public.vendor_locations WHERE id='{a}'", user_id=ACTOR
    )
    assert not result.ok
    result = db.run(
        "UPDATE public.vendor_locations SET vendor_id='bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb' "
        f"WHERE id='{a}'"
    )
    assert not result.ok
    assert _branch_stock_qty(db, listing, a) == 10


def test_rejected_operation_keeps_original_outcome_after_stock_changes(
    db: PgConn, item: tuple[str, str, str]
) -> None:
    listing, a, _ = item
    operation = str(uuid.uuid4())
    rejected = adjust(db, listing, a, -11, operation)
    assert rejected["code"] == "stock.insufficient"
    assert adjust(db, listing, a, 5)["ok"]
    assert adjust(db, listing, a, -11, operation) == rejected
    assert _branch_stock_qty(db, listing, a) == 15


def test_unrelated_branch_progresses_while_other_branch_is_locked(
    db: PgConn, item: tuple[str, str, str]
) -> None:
    import psycopg

    listing, a, b = item
    with psycopg.connect(db.dsn) as connection:
        connection.execute(
            "SELECT 1 FROM public.listing_location_stock "
            "WHERE listing_id=%s AND location_id=%s FOR UPDATE",
            (listing, a),
        )
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(adjust, db, listing, b, 2).result(timeout=5)
        assert result["ok"]
        assert _branch_stock_qty(db, listing, b) == 12


def test_sql_failure_rolls_back_inventory_and_operation_claim(
    db: PgConn, item: tuple[str, str, str]
) -> None:
    listing, a, b = item
    operation = str(uuid.uuid4())
    name = "stock_test_" + uuid.uuid4().hex
    installed = db.run(f"""
      CREATE FUNCTION public.{name}() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN IF NEW.listing_id = '{listing}'::uuid THEN
        RAISE EXCEPTION 'test failure after stock update'; END IF; RETURN NEW; END; $$;
      CREATE TRIGGER {name} AFTER UPDATE ON public.listing_location_stock
        FOR EACH ROW EXECUTE FUNCTION public.{name}();
    """)
    assert installed.ok, installed.error
    try:
        with pytest.raises(AssertionError, match="test failure after stock update"):
            adjust(db, listing, a, 2, operation)
        assert _branch_stock_qty(db, listing, a) == 10
        assert _branch_stock_qty(db, listing, b) == 10
        assert _legacy_stock_qty(db, listing) == 90
        count = db.run(
            f"SELECT count(*) FROM public.vendor_stock_operations WHERE operation_id='{operation}'"
        )
        assert count.ok and count.rows == ["0"]
    finally:
        cleaned = db.run(
            f"DROP TRIGGER {name} ON public.listing_location_stock; DROP FUNCTION public.{name}();"
        )
        assert cleaned.ok, cleaned.error
