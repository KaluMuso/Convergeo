from __future__ import annotations

import concurrent.futures
import json
import uuid
from collections.abc import Generator
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import pytest
from app.services.stock.claim import claim_reservation
from app.services.stock.release import release_reservation
from app.services.stock.revalidate import CartLineSnapshot, revalidate_lines
from app.services.stock.sweep import sweep_expired_reservations
from tests.rls.conftest import (
    PgConn,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "demo"
CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _load_ids() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES_DIR / "ids.json").read_text()))


@pytest.fixture(scope="module")
def db() -> Generator[PgConn, None, None]:
    url = resolve_db_url()
    conn = PgConn(url)
    if not conn.run("SELECT 1").ok:
        pytest.skip(f"Postgres not reachable at {url}")
    if not schema_ready(conn):
        conn.run("DROP SCHEMA IF EXISTS public CASCADE")
        conn.run("CREATE SCHEMA public")
        conn.run("DROP SCHEMA IF EXISTS auth CASCADE")
        apply_migrations(conn)
    seed_matrix_fixtures(conn)
    yield conn


@pytest.fixture(autouse=True)
def db_url_env(db: PgConn) -> Generator[None, None, None]:
    import os

    previous = os.environ.get("SUPABASE_DB_URL")
    os.environ["SUPABASE_DB_URL"] = db.dsn
    yield
    if previous is None:
        os.environ.pop("SUPABASE_DB_URL", None)
    else:
        os.environ["SUPABASE_DB_URL"] = previous


def _insert_checkout_group(conn: PgConn, group_id: str) -> None:
    conn.run(
        f"""
        INSERT INTO public.checkout_groups (
          id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee, total_ngwee
        ) VALUES (
          '{group_id}', '{CUSTOMER_ID}', 'idem-{group_id}', 0, 0, 0
        );
        """
    )


def _insert_tracked_listing(
    conn: PgConn,
    *,
    listing_id: str,
    stock_qty: int,
    stock_mode: str = "tracked",
) -> None:
    ids = _load_ids()
    conn.run(
        f"""
        INSERT INTO public.vendor_listings (
          id, vendor_id, product_id, price_ngwee, condition, stock_mode, stock_qty, status
        ) VALUES (
          '{listing_id}', '{VENDOR_ID}', '{ids["products"]["phone"]}', 10000,
          'new', '{stock_mode}', {stock_qty if stock_mode == 'tracked' else 'NULL'}, 'active'
        );
        """
    )


def _stock_qty(conn: PgConn, listing_id: str) -> int:
    result = conn.run(
        f"SELECT stock_qty::text FROM public.vendor_listings WHERE id = '{listing_id}';"
    )
    assert result.ok and result.rows
    return int(result.rows[0])


def _reservation_count(conn: PgConn, listing_id: str) -> int:
    result = conn.run(
        f"SELECT count(*)::text FROM public.stock_reservations WHERE listing_id = '{listing_id}';"
    )
    assert result.ok and result.rows
    return int(result.rows[0])


class TestConcurrentClaim:
    def test_two_concurrent_claims_last_unit_exactly_one_succeeds(self, db: PgConn) -> None:
        listing_id = str(uuid.uuid4())
        group_a = str(uuid.uuid4())
        group_b = str(uuid.uuid4())
        _insert_tracked_listing(db, listing_id=listing_id, stock_qty=1)
        _insert_checkout_group(db, group_a)
        _insert_checkout_group(db, group_b)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_a = executor.submit(
                claim_reservation,
                listing_id=listing_id,
                checkout_group_id=group_a,
                qty=1,
                ttl_minutes=15,
            )
            future_b = executor.submit(
                claim_reservation,
                listing_id=listing_id,
                checkout_group_id=group_b,
                qty=1,
                ttl_minutes=15,
            )
            results = [future_a.result(), future_b.result()]

        successes = [result for result in results if result.claimed]
        failures = [result for result in results if not result.claimed]

        assert len(successes) == 1
        assert len(failures) == 1
        assert _stock_qty(db, listing_id) == 0
        assert _stock_qty(db, listing_id) >= 0
        assert _reservation_count(db, listing_id) == 1


class TestSweeper:
    def test_sweeper_idempotent_and_restock_exactly_once(self, db: PgConn) -> None:
        listing_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        _insert_tracked_listing(db, listing_id=listing_id, stock_qty=2)
        _insert_checkout_group(db, group_id)

        claimed = claim_reservation(
            listing_id=listing_id,
            checkout_group_id=group_id,
            qty=1,
            ttl_minutes=15,
        )
        assert claimed.claimed
        assert _stock_qty(db, listing_id) == 1

        db.run(
            f"""
            UPDATE public.stock_reservations
            SET expires_at = timezone('utc', now()) - interval '1 minute'
            WHERE listing_id = '{listing_id}' AND checkout_group_id = '{group_id}';
            """
        )

        first = sweep_expired_reservations()
        second = sweep_expired_reservations()

        assert first.released == 1
        assert second.released == 0
        assert _stock_qty(db, listing_id) == 2
        assert _reservation_count(db, listing_id) == 0

    def test_ttl_boundary_keeps_active_expires_sweeps_expired(self, db: PgConn) -> None:
        listing_id = str(uuid.uuid4())
        active_group = str(uuid.uuid4())
        expired_group = str(uuid.uuid4())
        _insert_tracked_listing(db, listing_id=listing_id, stock_qty=5)
        _insert_checkout_group(db, active_group)
        _insert_checkout_group(db, expired_group)

        claim_reservation(
            listing_id=listing_id,
            checkout_group_id=active_group,
            qty=1,
            ttl_minutes=15,
        )
        claim_reservation(
            listing_id=listing_id,
            checkout_group_id=expired_group,
            qty=1,
            ttl_minutes=15,
        )

        db.run(
            f"""
            UPDATE public.stock_reservations
            SET expires_at = timezone('utc', now()) - interval '1 minute'
            WHERE checkout_group_id = '{expired_group}';
            """
        )

        sweep_expired_reservations()

        assert _reservation_count(db, listing_id) == 1
        assert _stock_qty(db, listing_id) == 4


class TestAlwaysAvailable:
    def test_always_available_skips_reservation(self, db: PgConn) -> None:
        listing_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        _insert_tracked_listing(
            db,
            listing_id=listing_id,
            stock_qty=0,
            stock_mode="always_available",
        )
        _insert_checkout_group(db, group_id)

        result = claim_reservation(
            listing_id=listing_id,
            checkout_group_id=group_id,
            qty=2,
            ttl_minutes=15,
        )

        assert result.claimed
        assert result.skipped
        assert _reservation_count(db, listing_id) == 0


class TestRelease:
    def test_release_restock_exactly_once(self, db: PgConn) -> None:
        listing_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        _insert_tracked_listing(db, listing_id=listing_id, stock_qty=3)
        _insert_checkout_group(db, group_id)

        claim_reservation(
            listing_id=listing_id,
            checkout_group_id=group_id,
            qty=2,
            ttl_minutes=15,
        )

        first = release_reservation(listing_id=listing_id, checkout_group_id=group_id)
        second = release_reservation(listing_id=listing_id, checkout_group_id=group_id)

        assert first.released and first.restocked
        assert not second.released
        assert _stock_qty(db, listing_id) == 3


class TestRevalidate:
    def test_revalidation_notice_payloads(self, db: PgConn) -> None:
        listing_price = str(uuid.uuid4())
        listing_oos = str(uuid.uuid4())
        listing_qty = str(uuid.uuid4())

        _insert_tracked_listing(db, listing_id=listing_price, stock_qty=5)
        _insert_tracked_listing(db, listing_id=listing_oos, stock_qty=0)
        _insert_tracked_listing(db, listing_id=listing_qty, stock_qty=2)

        db.run(
            f"""
            UPDATE public.vendor_listings
            SET price_ngwee = 12000
            WHERE id = '{listing_price}';
            """
        )

        lines = [
            CartLineSnapshot(listing_id=listing_price, qty=1, unit_price_ngwee=10_000),
            CartLineSnapshot(listing_id=listing_oos, qty=1, unit_price_ngwee=10_000),
            CartLineSnapshot(listing_id=listing_qty, qty=5, unit_price_ngwee=10_000),
        ]

        result = revalidate_lines(lines)

        kinds = {notice.listing_id: notice.kind for notice in result.notices}
        assert kinds[listing_price] == "price_changed"
        assert kinds[listing_oos] == "out_of_stock"
        assert kinds[listing_qty] == "qty_reduced"
        assert result.has_changes


class TestInternalSweeperEndpoint:
    def test_tick_requires_internal_token(self, client: Any) -> None:
        from fastapi.testclient import TestClient

        app_client: TestClient = client
        denied = app_client.post("/internal/stock-sweeper/tick")
        assert denied.status_code == 401

        with patch(
            "app.routers.internal_stock_sweeper.sweep_expired_reservations",
            return_value=type(
                "Stats",
                (),
                {"scanned": 0, "released": 0, "restocked_qty": 0},
            )(),
        ):
            allowed = app_client.post(
                "/internal/stock-sweeper/tick",
                headers={"X-Internal-Token": "dev-internal-stock-sweeper"},
            )
        assert allowed.status_code == 200
        assert allowed.json() == {"scanned": 0, "released": 0, "restocked_qty": 0}
