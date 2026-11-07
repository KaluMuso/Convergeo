"""Real, isolated PostgreSQL regressions for merchant review M1–M4."""

from __future__ import annotations

import concurrent.futures
import json
import os
import threading
import time
import uuid
from collections.abc import Generator
from typing import Any
from urllib.parse import urlparse

import psycopg
import pytest
from app.services.stock.claim import claim_reservation
from app.services.stock.release import release_reservation
from app.services.stock.sweep import sweep_expired_reservations
from tests.rls.conftest import PgConn, SqlResult, resolve_db_url, seed_matrix_fixtures
from tests.rls.test_cart_merge_atomic import (
    _RPC_SQL,
    _PsycopgDb,
    _seed_merge_case,
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
from tests.test_vendor_stock_adjustment_db import ACTOR, adjust, race


@pytest.fixture(scope="module")
def db() -> Generator[PgConn, None, None]:
    assert os.environ.get("MERCHANT_STOCK_ISOLATED_DB") == "1"
    url = resolve_db_url()
    assert urlparse(url).hostname in {"127.0.0.1", "localhost", "::1"}
    conn = PgConn(url)
    installed = conn.run("SELECT to_regclass('public.stock_claim_identities')::text")
    assert installed.ok and installed.rows == ["stock_claim_identities"]
    seed_matrix_fixtures(conn)
    previous = os.environ.get("SUPABASE_DB_URL")
    os.environ["SUPABASE_DB_URL"] = url
    yield conn
    if previous is None:
        os.environ.pop("SUPABASE_DB_URL", None)
    else:
        os.environ["SUPABASE_DB_URL"] = previous


def insert_sql(listing: str, vendor: str = VENDOR_ID, qty: int = 10) -> str:
    return f"""INSERT INTO public.vendor_listings
      (id,vendor_id,product_id,price_ngwee,condition,stock_mode,stock_qty,status)
      VALUES('{listing}','{vendor}','b0000000-0000-0000-0000-000000000001',
        10000,'new','tracked',{qty},'draft')"""


def _service_write(db: PgConn, statement: str) -> SqlResult:
    return db.run("BEGIN; SET LOCAL ROLE service_role; " + statement + "; COMMIT;")


@pytest.mark.parametrize("owner", [ACTOR, "44444444-4444-4444-4444-444444444444"])
def test_browser_roles_cannot_seed_stock_or_bypass_wholesale(db: PgConn, owner: str) -> None:
    listing = str(uuid.uuid4())
    service = _service_write(db, insert_sql(listing))
    assert service.ok, service.error
    for statement in (
        insert_sql(str(uuid.uuid4())),
        f"UPDATE public.vendor_listings SET wholesale=true, "
        f"price_tiers='[{{\"min_qty\":2,\"price_ngwee\":9000}}]' WHERE id='{listing}'",
        f"UPDATE public.vendor_listings SET price_ngwee=12000 WHERE id='{listing}'",
    ):
        denied = db.run_as("authenticated", statement + ";", user_id=owner)
        assert not denied.ok and "permission denied" in (denied.error or ""), denied.error
    stored = db.run(
        f"SELECT stock_qty,wholesale,price_ngwee FROM public.vendor_listings WHERE id='{listing}'"
    )
    assert stored.ok and stored.rows == ["10|f|10000"]
    unchanged = _service_write(
        db, f"UPDATE public.vendor_listings SET price_ngwee=12000 WHERE id='{listing}'"
    )
    assert unchanged.ok, unchanged.error
    assert db.run(
        f"SELECT stock_qty,price_ngwee FROM public.vendor_listings WHERE id='{listing}'"
    ).rows == ["10|12000"]


@pytest.mark.parametrize("unit,step,minimum", [("each", 1000, 1), ("kg", 250, 4)])
def test_minimum_is_frozen_and_price_only_service_save_passes(
    db: PgConn, unit: str, step: int, minimum: int
) -> None:
    listing = str(uuid.uuid4())
    seeded = db.run(
        insert_sql(listing)
        .replace("status)", "status,sale_unit,unit_step_milli,min_steps)")
        .replace("10,'draft')", f"10,'draft','{unit}',{step},{minimum})")
    )
    assert seeded.ok, seeded.error
    rejected = _service_write(
        db,
        f"UPDATE public.vendor_listings SET min_steps={minimum + 1} WHERE id='{listing}'",
    )
    assert not rejected.ok and "stock.units_immutable" in (rejected.error or "")
    same = _service_write(
        db,
        f"UPDATE public.vendor_listings SET min_steps={minimum},price_ngwee=11000 "
        f"WHERE id='{listing}'",
    )
    assert same.ok, same.error
    assert db.run(
        f"SELECT min_steps,stock_qty FROM public.vendor_listings WHERE id='{listing}'"
    ).rows == [f"{minimum}|10"]


def test_effective_client_acl_and_definer_catalog(db: PgConn) -> None:
    catalog = db.run("""SELECT
      has_table_privilege('authenticated','public.vendor_listings','SELECT'),
      has_table_privilege('authenticated','public.vendor_listings','INSERT'),
      has_table_privilege('authenticated','public.vendor_listings','UPDATE'),
      has_table_privilege('authenticated','public.vendor_listings','DELETE'),
      has_function_privilege('authenticated','public.claim_stock_reservation(uuid,uuid,integer,uuid,timestamptz)','EXECUTE'),
      has_function_privilege('service_role','public.claim_stock_reservation(uuid,uuid,integer,uuid,timestamptz)','EXECUTE');""")
    assert catalog.ok and catalog.rows == ["t|f|f|f|f|t"]
    invisible = _service_write(db, "SELECT * FROM public.stock_claim_identities")
    assert not invisible.ok
    metadata = db.run("""SELECT p.prosecdef,r.rolsuper OR r.rolbypassrls,p.proconfig::text,
      c.relrowsecurity,c.relforcerowsecurity FROM pg_proc p
      JOIN pg_roles r ON r.oid=p.proowner
      JOIN pg_class c ON c.oid='public.stock_claim_identities'::regclass
      WHERE p.oid=
        'public.claim_stock_reservation(uuid,uuid,integer,uuid,timestamptz)'::regprocedure;""")
    assert metadata.ok and metadata.rows == ['t|t|{"search_path=pg_catalog, public"}|t|t']


def test_atomic_admission_waits_and_recounts_last_slot(db: PgConn) -> None:
    vendor, first, second = (str(uuid.uuid4()) for _ in range(3))
    seeded = db.run(
        f"INSERT INTO public.vendors(id,owner_user_id,slug,display_name,status) "
        f"VALUES('{vendor}','{ACTOR}','quota-{vendor}','Quota test','active')"
    )
    assert seeded.ok, seeded.error
    previous = db.run("SELECT max_listings FROM public.vendor_quotas WHERE tier=1").rows[0]
    assert db.run("UPDATE public.vendor_quotas SET max_listings=1 WHERE tier=1").ok
    entered = threading.Event()
    backend: list[int] = []

    def competing_insert() -> str:
        with psycopg.connect(db.dsn) as connection:
            backend.append(connection.info.backend_pid)
            entered.set()
            try:
                connection.execute(insert_sql(second, vendor))
                connection.commit()
                return "accepted"
            except psycopg.Error as exc:
                connection.rollback()
                return str(exc)

    try:
        with psycopg.connect(db.dsn) as first_connection:
            first_connection.execute(insert_sql(first, vendor))
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                pending = pool.submit(competing_insert)
                assert entered.wait(5)
                waiting = False
                for _ in range(100):
                    state = db.run(
                        f"SELECT wait_event_type FROM pg_stat_activity WHERE pid={backend[0]}"
                    )
                    if state.rows == ["Lock"]:
                        waiting = True
                        break
                    time.sleep(0.01)
                assert waiting, "Second admission must contend on the vendor boundary"
                first_connection.commit()
                assert "listing_cap_exceeded" in pending.result(timeout=10)
        assert db.run(
            f"SELECT count(*) FROM public.vendor_listings WHERE vendor_id='{vendor}'"
        ).rows == ["1"]
        # Reimport/price-only updates use the existing slot.
        assert _service_write(
            db,
            f"UPDATE public.vendor_listings SET title_override='Reimport',price_ngwee=12000 "
            f"WHERE id='{first}'",
        ).ok
        # A failed transaction frees its admission; no maintained counter leaks.
        assert db.run(f"DELETE FROM public.vendor_listings WHERE id='{first}'").ok
        failed = db.run(insert_sql(first, vendor, -1))
        assert not failed.ok
        assert db.run(insert_sql(second, vendor)).ok
    finally:
        assert db.run(f"UPDATE public.vendor_quotas SET max_listings={previous} WHERE tier=1").ok


@pytest.fixture
def claim_item(db: PgConn) -> Generator[tuple[str, str, str, str], None, None]:
    listing, a, b, group = (str(uuid.uuid4()) for _ in range(4))
    _insert_tracked_listing(db, listing_id=listing, stock_qty=10)
    for location in (a, b):
        _insert_branch(db, location_id=location, lat=-15.4, lng=28.3, landmark="Replay test")
        _insert_branch_stock(db, listing_id=listing, location_id=location, stock_qty=10)
    _insert_checkout_group(db, group)
    yield listing, a, b, group
    assert db.run(f"DELETE FROM public.vendor_listings WHERE id='{listing}'").ok


@pytest.mark.parametrize("branch", [False, True])
def test_same_claim_replay_and_release_conserve(db: PgConn, branch: bool) -> None:
    listing, location, group = (str(uuid.uuid4()) for _ in range(3))
    _insert_tracked_listing(db, listing_id=listing, stock_qty=10)
    if branch:
        _insert_branch(db, location_id=location, lat=-15.4, lng=28.3, landmark="Replay test")
        _insert_branch_stock(db, listing_id=listing, location_id=location, stock_qty=10)
    _insert_checkout_group(db, group)
    parameters: dict[str, Any] = dict(
        listing_id=listing,
        checkout_group_id=group,
        qty=3,
        ttl_minutes=15,
        location_id=location if branch else None,
    )
    first = claim_reservation(**parameters)
    second = claim_reservation(**parameters)
    assert first.claimed and second == first
    quantity = (
        _branch_stock_qty(db, listing, location) if branch else _legacy_stock_qty(db, listing)
    )
    assert quantity == 7
    assert not claim_reservation(**{**parameters, "qty": 4}).claimed
    assert release_reservation(listing_id=listing, checkout_group_id=group).released
    assert not claim_reservation(**parameters).claimed
    quantity = (
        _branch_stock_qty(db, listing, location) if branch else _legacy_stock_qty(db, listing)
    )
    assert quantity == 10
    assert db.run(f"DELETE FROM public.vendor_listings WHERE id='{listing}'").ok


def test_duplicate_claim_race_and_changed_branch_no_double_consume(
    db: PgConn, claim_item: tuple[str, str, str, str]
) -> None:
    listing, a, b, group = claim_item
    parameters: dict[str, Any] = dict(
        listing_id=listing, checkout_group_id=group, qty=3, ttl_minutes=15, location_id=a
    )
    results = race(lambda: claim_reservation(**parameters), lambda: claim_reservation(**parameters))
    assert results[0] == results[1] and results[0].claimed
    assert not claim_reservation(**{**parameters, "location_id": b}).claimed
    assert _branch_stock_qty(db, listing, a) == 7
    assert _branch_stock_qty(db, listing, b) == 10
    assert db.run(
        f"SELECT count(*),sum(qty) FROM public.stock_reservations WHERE listing_id='{listing}'"
    ).rows == ["1|3"]


@pytest.mark.parametrize("sweep", [False, True])
def test_replay_vs_release_or_sweep_conserves(
    db: PgConn, claim_item: tuple[str, str, str, str], sweep: bool
) -> None:
    listing, a, _, group = claim_item
    parameters: dict[str, Any] = dict(
        listing_id=listing, checkout_group_id=group, qty=3, ttl_minutes=15, location_id=a
    )
    assert claim_reservation(**parameters).claimed
    if sweep:
        assert db.run(
            f"UPDATE public.stock_reservations SET expires_at=now()-interval '1 minute', "
            f"created_at=now()-interval '16 minutes' WHERE listing_id='{listing}'"
        ).ok
    race(
        lambda: claim_reservation(**parameters),
        sweep_expired_reservations
        if sweep
        else lambda: release_reservation(listing_id=listing, checkout_group_id=group),
    )
    assert _branch_stock_qty(db, listing, a) == 10
    assert db.run(
        f"SELECT count(*) FROM public.stock_reservations WHERE listing_id='{listing}'"
    ).rows == ["0"]
    assert not claim_reservation(**parameters).claimed


def test_claim_adjustment_release_conservation(
    db: PgConn, claim_item: tuple[str, str, str, str]
) -> None:
    listing, a, _, group = claim_item
    results = race(
        lambda: claim_reservation(
            listing_id=listing, checkout_group_id=group, qty=3, ttl_minutes=15, location_id=a
        ),
        lambda: adjust(db, listing, a, 5),
    )
    assert results[0].claimed and results[1]["ok"]
    assert _branch_stock_qty(db, listing, a) == 12
    assert release_reservation(listing_id=listing, checkout_group_id=group).released
    assert _branch_stock_qty(db, listing, a) == 15


def test_claim_failure_rolls_back_identity_and_stock(
    db: PgConn, claim_item: tuple[str, str, str, str]
) -> None:
    listing, a, _, group = claim_item
    name = "claim_failure_" + uuid.uuid4().hex
    assert db.run(f"""CREATE FUNCTION public.{name}() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN IF NEW.listing_id='{listing}'::uuid THEN
        RAISE EXCEPTION 'claim injected failure'; END IF;
      RETURN NEW; END; $$;
      CREATE TRIGGER {name} BEFORE INSERT ON public.stock_reservations
        FOR EACH ROW EXECUTE FUNCTION public.{name}();""").ok
    try:
        with pytest.raises(RuntimeError, match="claim injected failure"):
            claim_reservation(
                listing_id=listing, checkout_group_id=group, qty=3, ttl_minutes=15, location_id=a
            )
        assert _branch_stock_qty(db, listing, a) == 10
        assert db.run(
            f"SELECT count(*) FROM public.stock_claim_identities WHERE listing_id='{listing}'"
        ).rows == ["0"]
    finally:
        assert db.run(
            f"DROP TRIGGER {name} ON public.stock_reservations; DROP FUNCTION public.{name}();"
        ).ok


@pytest.mark.parametrize("merge_first", [True, False])
def test_real_cart_merge_and_claim_preserve_lock_order(db: PgConn, merge_first: bool) -> None:
    # Small random UUIDs make these three isolated rows sort ahead of the
    # retained fixture rows used by the real SQL cart-merge fixture helper.
    listings = sorted(str(uuid.UUID(int=int(uuid.uuid4().hex[:12], 16))) for _ in range(3))
    for index, listing in enumerate(listings):
        seeded = db.run(
            insert_sql(listing)
            .replace("10000,'new'", f"{(index + 1) * 10000},'new'")
            .replace("'draft'", "'active'")
        )
        assert seeded.ok, seeded.error
    atomic = _PsycopgDb(db.dsn)
    parameters = _seed_merge_case(atomic)
    assert parameters["user_listing_id"] == listings[0]
    group = str(uuid.uuid4())
    _insert_checkout_group(db, group)
    claim_sql = "SELECT public.claim_stock_reservation(%s,%s,1,null,now()+interval '15 minutes')"
    if merge_first:
        entered = threading.Event()
        backend: list[int] = []

        def competing_claim() -> int:
            with psycopg.connect(db.dsn) as connection:
                connection.execute("SET LOCAL ROLE service_role")
                backend.append(connection.info.backend_pid)
                entered.set()
                row = connection.execute(claim_sql, (listings[0], group)).fetchone()
                assert row is not None
                return int(row[0])

        with psycopg.connect(db.dsn) as merge:
            merge.execute("SET LOCAL ROLE service_role")
            applied = merge.execute(_RPC_SQL, parameters).fetchone()
            assert applied and json.loads(str(applied[0]))["outcome"] == "applied"
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                pending = pool.submit(competing_claim)
                assert entered.wait(5)
                waiting = False
                for _ in range(100):
                    observed = db.run(
                        f"SELECT wait_event_type FROM pg_stat_activity WHERE pid={backend[0]}"
                    )
                    if observed.rows == ["Lock"]:
                        waiting = True
                        break
                    time.sleep(0.01)
                assert waiting, "Claim must serialize behind the held merge authority"
                merge.commit()
                assert pending.result(timeout=10) == 9
    else:
        with psycopg.connect(db.dsn) as claim:
            claim.execute("SET LOCAL ROLE service_role")
            assert claim.execute(claim_sql, (listings[0], group)).fetchone() == (9,)
            with psycopg.connect(db.dsn) as merge:
                merge.execute("SET LOCAL ROLE service_role")
                outcome = merge.execute(_RPC_SQL, parameters).fetchone()
                assert outcome and json.loads(str(outcome[0]))["outcome"] == "stale_authority"
            # The real RPC returns its supported recompute outcome without
            # waiting for the writer's row lock or changing either cart.
            claim.commit()
    assert _legacy_stock_qty(db, listings[0]) == 9
    assert release_reservation(listing_id=listings[0], checkout_group_id=group).released
    assert _legacy_stock_qty(db, listings[0]) == 10
    assert not claim_reservation(
        listing_id=listings[0], checkout_group_id=group, qty=1, ttl_minutes=15
    ).claimed
    # Remove only this test's disposable receipts/carts before its catalog rows.
    assert db.run(
        f"DELETE FROM public.cart_merge_receipts WHERE user_cart_id='{parameters['user_cart_id']}'"
    ).ok
    assert db.run(
        f"DELETE FROM public.carts WHERE id IN "
        f"('{parameters['user_cart_id']}','{parameters['guest_cart_id']}')"
    ).ok
    for listing in listings:
        assert db.run(f"DELETE FROM public.vendor_listings WHERE id='{listing}'").ok


@pytest.mark.parametrize("qty", [3, 6])
def test_distinct_pooled_claims_keep_parent_fk_locks_compatible(db: PgConn, qty: int) -> None:
    """Both FK references must exist before either pooled lock is upgraded."""
    listing, first_group, second_group = (str(uuid.uuid4()) for _ in range(3))
    inserted = db.run(insert_sql(listing))
    assert inserted.ok, inserted.error
    for group in (first_group, second_group):
        _insert_checkout_group(db, group)
    name = "zz_claim_parent_gate_" + uuid.uuid4().hex
    gate = int(uuid.uuid4().hex[:12], 16)
    installed = db.run(f"""
      CREATE FUNCTION public.{name}() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF NEW.listing_id='{listing}'::uuid THEN
          PERFORM pg_advisory_xact_lock_shared({gate});
        END IF;
        RETURN NEW;
      END; $$;
      CREATE TRIGGER {name} AFTER INSERT ON public.stock_claim_identities
        FOR EACH ROW EXECUTE FUNCTION public.{name}();
    """)
    assert installed.ok, installed.error
    backends: list[int] = []
    backend_lock = threading.Lock()

    def claim(group: str) -> tuple[str | None, int | None]:
        try:
            with psycopg.connect(db.dsn) as connection:
                connection.execute("SET LOCAL ROLE service_role")
                connection.execute("SET LOCAL statement_timeout='10s'")
                with backend_lock:
                    backends.append(connection.info.backend_pid)
                row = connection.execute(
                    "SELECT public.claim_stock_reservation(%s,%s,%s,null,"
                    "now()+interval '15 minutes')",
                    (listing, group, qty),
                ).fetchone()
                assert row is not None
                return None, row[0]
        except psycopg.Error as exc:
            return exc.sqlstate, None

    try:
        with psycopg.connect(db.dsn) as control:
            control.execute("SELECT pg_advisory_xact_lock(%s)", (gate,))
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(claim, group) for group in (first_group, second_group)]
                waiting = False
                for _ in range(200):
                    with backend_lock:
                        observed_pids = list(backends)
                    if len(observed_pids) == 2:
                        states = db.run(
                            "SELECT count(*) FROM pg_stat_activity WHERE pid IN "
                            f"({observed_pids[0]},{observed_pids[1]}) "
                            "AND wait_event_type='Lock' AND wait_event='advisory'"
                        )
                        if states.rows == ["2"]:
                            waiting = True
                            break
                    time.sleep(0.01)
                # Always release the barrier before joining workers, including
                # on a failed assertion, so the control itself cannot hang.
                control.commit()
                outcomes = [future.result(timeout=15) for future in futures]
                assert waiting, "Both independent FK-backed identities must reach the gate"
                assert all(state is None for state, _ in outcomes), outcomes
        expected_claims = 2 if qty == 3 else 1
        assert sum(remaining is not None for _, remaining in outcomes) == expected_claims
        assert _legacy_stock_qty(db, listing) == 10 - expected_claims * qty
        reservations = db.run(
            f"SELECT count(*),coalesce(sum(qty),0) FROM public.stock_reservations "
            f"WHERE listing_id='{listing}'"
        )
        assert reservations.ok and reservations.rows == [
            f"{expected_claims}|{expected_claims * qty}"
        ]
        for group in (first_group, second_group):
            release_reservation(listing_id=listing, checkout_group_id=group)
        assert _legacy_stock_qty(db, listing) == 10
    finally:
        assert db.run(
            f"DROP TRIGGER {name} ON public.stock_claim_identities; DROP FUNCTION public.{name}();"
        ).ok
        assert db.run(f"DELETE FROM public.vendor_listings WHERE id='{listing}'").ok


def test_pooled_claim_can_upgrade_behind_waiting_adjustment(db: PgConn) -> None:
    """A stronger adjustment waiter must not trap the FK-holding claim."""
    listing, group = (str(uuid.uuid4()) for _ in range(2))
    assert db.run(insert_sql(listing)).ok
    _insert_checkout_group(db, group)
    name = "zz_claim_adjust_gate_" + uuid.uuid4().hex
    gate = int(uuid.uuid4().hex[:12], 16)
    assert db.run(f"""
      CREATE FUNCTION public.{name}() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN IF NEW.listing_id='{listing}'::uuid THEN
        PERFORM pg_advisory_xact_lock_shared({gate}); END IF; RETURN NEW; END; $$;
      CREATE TRIGGER {name} AFTER INSERT ON public.stock_claim_identities
        FOR EACH ROW EXECUTE FUNCTION public.{name}();
    """).ok
    backends: dict[str, int] = {}
    backend_lock = threading.Lock()

    def write(kind: str) -> object:
        with psycopg.connect(db.dsn) as connection:
            connection.execute("SET LOCAL ROLE service_role")
            connection.execute("SET LOCAL statement_timeout='10s'")
            with backend_lock:
                backends[kind] = connection.info.backend_pid
            if kind == "claim":
                row = connection.execute(
                    "SELECT public.claim_stock_reservation(%s,%s,3,null,"
                    "now()+interval '15 minutes')",
                    (listing, group),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT public.adjust_vendor_stock(%s,%s,%s,null,%s,2,'delivery','each',1000)",
                    (ACTOR, VENDOR_ID, listing, str(uuid.uuid4())),
                ).fetchone()
            assert row is not None
            return row[0]

    def wait_for_lock(kind: str, advisory: bool) -> None:
        for _ in range(200):
            with backend_lock:
                pid = backends.get(kind)
            if pid is not None:
                extra = " AND wait_event='advisory'" if advisory else ""
                observed = db.run(
                    f"SELECT count(*) FROM pg_stat_activity WHERE pid={pid} "
                    f"AND wait_event_type='Lock'{extra}"
                )
                if observed.rows == ["1"]:
                    return
            time.sleep(0.01)
        raise AssertionError(f"{kind} did not reach its expected lock wait")

    try:
        with psycopg.connect(db.dsn) as control:
            control.execute("SELECT pg_advisory_xact_lock(%s)", (gate,))
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                claim = pool.submit(write, "claim")
                try:
                    wait_for_lock("claim", True)
                    adjustment = pool.submit(write, "adjust")
                    wait_for_lock("adjust", False)
                finally:
                    control.commit()
                assert claim.result(timeout=15) == 7
                outcome = adjustment.result(timeout=15)
                assert isinstance(outcome, dict) and outcome["ok"]
                assert (outcome["old_qty"], outcome["new_qty"]) == (7, 9)
        assert _legacy_stock_qty(db, listing) == 9
        assert release_reservation(listing_id=listing, checkout_group_id=group).released
        assert _legacy_stock_qty(db, listing) == 12
    finally:
        assert db.run(
            f"DROP TRIGGER {name} ON public.stock_claim_identities; DROP FUNCTION public.{name}();"
        ).ok
        assert db.run(f"DELETE FROM public.vendor_listings WHERE id='{listing}'").ok
