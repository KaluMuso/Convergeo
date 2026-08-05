"""Branch-aware stock routing for cart validation and checkout claims (R02-P08)."""

from __future__ import annotations

import concurrent.futures
import uuid
from collections.abc import Generator
from typing import Any

import pytest
from app.errors import AppError
from app.services.inventory.location_stock import (
    available_qty_at_location,
    resolve_stock_location_id,
)
from app.services.listings.class_rules import validate_listing_purchasable_for_cart
from app.services.stock.claim import claim_reservation
from app.services.stock.release import release_reservation
from app.services.stock.sweep import sweep_expired_reservations
from tests.rls.conftest import (
    PgConn,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)

CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


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
    product_class: str = "A",
    fulfilment_mode: str = "stocked",
) -> None:
    conn.run(
        f"""
        INSERT INTO public.vendor_listings (
          id, vendor_id, product_id, price_ngwee, condition, stock_mode, stock_qty, status,
          product_class, fulfilment_mode
        ) VALUES (
          '{listing_id}', '{VENDOR_ID}', 'b0000000-0000-0000-0000-000000000001', 10000,
          'new', '{stock_mode}', {stock_qty if stock_mode == 'tracked' else 'NULL'}, 'active',
          '{product_class}', '{fulfilment_mode}'
        );
        """
    )


def _insert_branch(
    conn: PgConn,
    *,
    location_id: str,
    lat: float,
    lng: float,
    landmark: str,
    is_primary: bool = False,
) -> None:
    conn.run(
        f"""
        INSERT INTO public.vendor_locations (
          id, vendor_id, lat, lng, landmark, status, is_primary
        ) VALUES (
          '{location_id}', '{VENDOR_ID}', {lat}, {lng}, '{landmark}',
          'active', {str(is_primary).lower()}
        )
        ON CONFLICT (id) DO UPDATE SET lat = EXCLUDED.lat, lng = EXCLUDED.lng;
        """
    )


def _insert_branch_stock(
    conn: PgConn,
    *,
    listing_id: str,
    location_id: str,
    stock_qty: int,
) -> None:
    conn.run(
        f"""
        INSERT INTO public.listing_location_stock (listing_id, location_id, stock_qty)
        VALUES ('{listing_id}', '{location_id}', {stock_qty})
        ON CONFLICT (listing_id, location_id) DO UPDATE SET stock_qty = EXCLUDED.stock_qty;
        """
    )


def _branch_stock_qty(conn: PgConn, listing_id: str, location_id: str) -> int:
    result = conn.run(
        f"""
        SELECT stock_qty::text FROM public.listing_location_stock
        WHERE listing_id = '{listing_id}' AND location_id = '{location_id}';
        """
    )
    assert result.ok and result.rows
    return int(result.rows[0])


def _legacy_stock_qty(conn: PgConn, listing_id: str) -> int:
    result = conn.run(
        f"SELECT stock_qty::text FROM public.vendor_listings WHERE id = '{listing_id}';"
    )
    assert result.ok and result.rows
    return int(result.rows[0])


class TestCartBranchValidation:
    def test_pickup_at_empty_branch_blocked_when_other_branch_has_stock(self, db: PgConn) -> None:
        listing_id = str(uuid.uuid4())
        branch_a = str(uuid.uuid4())
        branch_b = str(uuid.uuid4())
        _insert_tracked_listing(db, listing_id=listing_id, stock_qty=5)
        _insert_branch(db, location_id=branch_a, lat=-15.42, lng=28.28, landmark="Branch A")
        _insert_branch(db, location_id=branch_b, lat=-15.39, lng=28.32, landmark="Branch B")
        _insert_branch_stock(db, listing_id=listing_id, location_id=branch_a, stock_qty=0)
        _insert_branch_stock(db, listing_id=listing_id, location_id=branch_b, stock_qty=5)

        listing: dict[str, Any] = {
            "id": listing_id,
            "stock_mode": "tracked",
            "stock_qty": 5,
            "product_class": "A",
            "fulfilment_mode": "stocked",
            "status": "active",
        }

        with pytest.raises(AppError) as exc_info:
            validate_listing_purchasable_for_cart(
                listing=listing,
                qty=1,
                evidence_image_count=0,
                location_id=branch_a,
            )

        err = exc_info.value
        assert err.code == "cart.insufficient_stock"
        assert err.details["location_id"] == branch_a
        assert err.details["available_qty"] == 0

        validate_listing_purchasable_for_cart(
            listing=listing,
            qty=1,
            evidence_image_count=0,
            location_id=branch_b,
        )

    def test_class_e_bypasses_branch_stock_checks(self, db: PgConn) -> None:
        listing_id = str(uuid.uuid4())
        branch_a = str(uuid.uuid4())
        _insert_tracked_listing(
            db,
            listing_id=listing_id,
            stock_qty=0,
            product_class="E",
            fulfilment_mode="made_to_order",
        )
        _insert_branch(db, location_id=branch_a, lat=-15.42, lng=28.28, landmark="Branch A")
        _insert_branch_stock(db, listing_id=listing_id, location_id=branch_a, stock_qty=0)

        listing: dict[str, Any] = {
            "id": listing_id,
            "stock_mode": "tracked",
            "stock_qty": 0,
            "product_class": "E",
            "fulfilment_mode": "made_to_order",
            "vendor_capacity_per_week": 5,
            "lead_time_days": 7,
            "status": "active",
        }

        validate_listing_purchasable_for_cart(
            listing=listing,
            qty=2,
            evidence_image_count=0,
            location_id=branch_a,
        )


class TestBranchClaims:
    def test_claim_at_branch_a_does_not_consume_branch_b(self, db: PgConn) -> None:
        listing_id = str(uuid.uuid4())
        branch_a = str(uuid.uuid4())
        branch_b = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        _insert_tracked_listing(db, listing_id=listing_id, stock_qty=10)
        _insert_branch(db, location_id=branch_a, lat=-15.42, lng=28.28, landmark="Branch A")
        _insert_branch(db, location_id=branch_b, lat=-15.39, lng=28.32, landmark="Branch B")
        _insert_branch_stock(db, listing_id=listing_id, location_id=branch_a, stock_qty=2)
        _insert_branch_stock(db, listing_id=listing_id, location_id=branch_b, stock_qty=5)
        _insert_checkout_group(db, group_id)

        claimed = claim_reservation(
            listing_id=listing_id,
            checkout_group_id=group_id,
            qty=2,
            ttl_minutes=15,
            location_id=branch_a,
        )

        assert claimed.claimed
        assert claimed.location_id == branch_a
        assert _branch_stock_qty(db, listing_id, branch_a) == 0
        assert _branch_stock_qty(db, listing_id, branch_b) == 5

    def test_legacy_listing_without_branch_rows_behaves_as_before(self, db: PgConn) -> None:
        listing_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        _insert_tracked_listing(db, listing_id=listing_id, stock_qty=3)
        _insert_checkout_group(db, group_id)

        claimed = claim_reservation(
            listing_id=listing_id,
            checkout_group_id=group_id,
            qty=2,
            ttl_minutes=15,
        )

        assert claimed.claimed
        assert claimed.location_id is None
        assert _legacy_stock_qty(db, listing_id) == 1

    def test_two_concurrent_claims_at_qty_1_exactly_one_wins(self, db: PgConn) -> None:
        listing_id = str(uuid.uuid4())
        branch_a = str(uuid.uuid4())
        group_a = str(uuid.uuid4())
        group_b = str(uuid.uuid4())
        _insert_tracked_listing(db, listing_id=listing_id, stock_qty=1)
        _insert_branch(db, location_id=branch_a, lat=-15.42, lng=28.28, landmark="Branch A")
        _insert_branch_stock(db, listing_id=listing_id, location_id=branch_a, stock_qty=1)
        _insert_checkout_group(db, group_a)
        _insert_checkout_group(db, group_b)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_a = executor.submit(
                claim_reservation,
                listing_id=listing_id,
                checkout_group_id=group_a,
                qty=1,
                ttl_minutes=15,
                location_id=branch_a,
            )
            future_b = executor.submit(
                claim_reservation,
                listing_id=listing_id,
                checkout_group_id=group_b,
                qty=1,
                ttl_minutes=15,
                location_id=branch_a,
            )
            results = [future_a.result(), future_b.result()]

        successes = [result for result in results if result.claimed]
        failures = [result for result in results if not result.claimed]

        assert len(successes) == 1
        assert len(failures) == 1
        assert _branch_stock_qty(db, listing_id, branch_a) == 0

    def test_release_restock_branch_not_legacy_pool(self, db: PgConn) -> None:
        listing_id = str(uuid.uuid4())
        branch_a = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        _insert_tracked_listing(db, listing_id=listing_id, stock_qty=10)
        _insert_branch(db, location_id=branch_a, lat=-15.42, lng=28.28, landmark="Branch A")
        _insert_branch_stock(db, listing_id=listing_id, location_id=branch_a, stock_qty=3)
        _insert_checkout_group(db, group_id)

        claim_reservation(
            listing_id=listing_id,
            checkout_group_id=group_id,
            qty=2,
            ttl_minutes=15,
            location_id=branch_a,
        )
        assert _branch_stock_qty(db, listing_id, branch_a) == 1
        assert _legacy_stock_qty(db, listing_id) == 10

        released = release_reservation(listing_id=listing_id, checkout_group_id=group_id)
        assert released.released and released.restocked
        assert released.location_id == branch_a
        assert _branch_stock_qty(db, listing_id, branch_a) == 3
        assert _legacy_stock_qty(db, listing_id) == 10

    def test_sweeper_restock_branch_row(self, db: PgConn) -> None:
        listing_id = str(uuid.uuid4())
        branch_a = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        _insert_tracked_listing(db, listing_id=listing_id, stock_qty=10)
        _insert_branch(db, location_id=branch_a, lat=-15.42, lng=28.28, landmark="Branch A")
        _insert_branch_stock(db, listing_id=listing_id, location_id=branch_a, stock_qty=2)
        _insert_checkout_group(db, group_id)

        claim_reservation(
            listing_id=listing_id,
            checkout_group_id=group_id,
            qty=1,
            ttl_minutes=15,
            location_id=branch_a,
        )
        assert _branch_stock_qty(db, listing_id, branch_a) == 1

        db.run(
            f"""
            UPDATE public.stock_reservations
            SET expires_at = timezone('utc', now()) - interval '1 minute'
            WHERE listing_id = '{listing_id}' AND checkout_group_id = '{group_id}';
            """
        )

        sweep = sweep_expired_reservations()
        assert sweep.released == 1
        assert _branch_stock_qty(db, listing_id, branch_a) == 2

        db.run(
            f"""
            DELETE FROM public.stock_reservations
            WHERE listing_id = '{listing_id}' AND checkout_group_id = '{group_id}';
            """
        )


class TestNearestBranchResolution:
    def test_delivery_resolves_nearest_branch(self, db: PgConn) -> None:
        listing_id = str(uuid.uuid4())
        near_branch = str(uuid.uuid4())
        far_branch = str(uuid.uuid4())
        _insert_tracked_listing(db, listing_id=listing_id, stock_qty=10)
        _insert_branch(
            db,
            location_id=near_branch,
            lat=-15.4167,
            lng=28.2833,
            landmark="Near",
        )
        _insert_branch(
            db,
            location_id=far_branch,
            lat=-15.50,
            lng=28.40,
            landmark="Far",
        )
        _insert_branch_stock(db, listing_id=listing_id, location_id=near_branch, stock_qty=3)
        _insert_branch_stock(db, listing_id=listing_id, location_id=far_branch, stock_qty=8)

        resolved = resolve_stock_location_id(
            listing_id,
            fulfilment="delivery",
            delivery_lat=-15.417,
            delivery_lng=28.284,
        )
        assert resolved == near_branch
        assert available_qty_at_location(listing_id, near_branch) == 3
