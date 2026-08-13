"""FIX-A: concurrency + oversell guards for create_orders_atomic.

Covers review findings #2 (concurrent checkout must not create duplicate order
sets) and #4 (a hold reclaimed between pre-check and tx must abort, never
oversell). Runs against a real Postgres so the in-tx FOR UPDATE lock, the status
recheck, the conditional hold consumption, and the 0031 unique index are all
exercised for real.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor

import pytest
from app.errors import AppError
from app.services.orders.create import (
    CartLineInput,
    CreateOrdersResult,
    VendorFulfilmentInput,
    create_orders_atomic,
)
from app.services.stock.claim import claim_reservation
from app.supabase_client import SupabaseServiceClient
from tests.rls.conftest import PgConn, apply_migrations, seed_matrix_fixtures
from tests.test_order_creation import (
    ADDRESS_ID,
    CUSTOMER_ID,
    VENDOR_A,
    VENDOR_B,
    _build_lines,
    _insert_checkout_group,
    _insert_tracked_listing,
    _load_ids,
    _order_count,
    _PgClient,
    _reservation_count,
)


@pytest.fixture(scope="module")
def db() -> Generator[PgConn, None, None]:
    admin = PgConn("postgresql://postgres:postgres@127.0.0.1:5432/postgres")
    if not admin.run("SELECT 1").ok:
        pytest.skip("Postgres not reachable on 127.0.0.1:5432")
    admin.run("DROP DATABASE IF EXISTS vergeo5_order_concurrency_test;")
    admin.run("CREATE DATABASE vergeo5_order_concurrency_test;")

    url = "postgresql://postgres:postgres@127.0.0.1:5432/vergeo5_order_concurrency_test"
    conn = PgConn(url)
    conn.run("DROP SCHEMA IF EXISTS public CASCADE")
    conn.run("CREATE SCHEMA public")
    conn.run("DROP SCHEMA IF EXISTS auth CASCADE")
    apply_migrations(conn)
    seed_matrix_fixtures(conn)
    yield conn


@pytest.fixture
def db_url_env(db: PgConn) -> Generator[None, None, None]:
    import os

    previous = os.environ.get("SUPABASE_DB_URL")
    os.environ["SUPABASE_DB_URL"] = db.dsn
    yield
    if previous is None:
        os.environ.pop("SUPABASE_DB_URL", None)
    else:
        os.environ["SUPABASE_DB_URL"] = previous


@pytest.fixture
def pg_service(db: PgConn) -> SupabaseServiceClient:
    return SupabaseServiceClient(_PgClient(db))  # type: ignore[arg-type]


def _stock_qty(conn: PgConn, listing_id: str) -> int:
    result = conn.run(
        f"SELECT stock_qty::text FROM public.vendor_listings WHERE id = '{listing_id}';"
    )
    assert result.ok and result.rows
    return int(result.rows[0])


def _insert_made_to_order_listing(
    conn: PgConn,
    *,
    listing_id: str,
    product_class: str,
    capacity_per_week: int | None,
    price_ngwee: int,
) -> None:
    capacity_sql = str(capacity_per_week) if capacity_per_week is not None else "NULL"
    result = conn.run(
        f"""
        INSERT INTO public.vendor_listings (
          id, vendor_id, product_id, title_override, price_ngwee, condition,
          stock_mode, stock_qty, status, fulfilment_mode, lead_time_days,
          product_class, vendor_capacity_per_week
        ) VALUES (
          '{listing_id}', '{VENDOR_A}', NULL, 'Made-to-order test item',
          {price_ngwee}, 'new', 'tracked', 0, 'active', 'made_to_order', 7,
          '{product_class}', {capacity_sql}
        );
        """
    )
    assert result.ok, result.error


def _single_listing_inputs(
    *, listing_id: str, qty: int, price_ngwee: int
) -> tuple[list[CartLineInput], list[VendorFulfilmentInput]]:
    return (
        [
            CartLineInput(
                cart_item_id=str(uuid.uuid4()),
                listing_id=listing_id,
                vendor_id=VENDOR_A,
                qty=qty,
                unit_price_ngwee=price_ngwee,
                title_snapshot="Made-to-order test item",
            )
        ],
        [
            VendorFulfilmentInput(
                vendor_id=VENDOR_A,
                fulfilment="pickup",
                delivery_zone=None,
                delivery_fee_ngwee=0,
                subtotal_ngwee=qty * price_ngwee,
            )
        ],
    )


def _two_vendor_groups(
    price_a: int, delivery_a: int, price_b: int, delivery_b: int
) -> list[VendorFulfilmentInput]:
    return [
        VendorFulfilmentInput(
            vendor_id=VENDOR_A,
            fulfilment="delivery",
            delivery_zone="lusaka_a",
            delivery_fee_ngwee=delivery_a,
            subtotal_ngwee=price_a,
        ),
        VendorFulfilmentInput(
            vendor_id=VENDOR_B,
            fulfilment="pickup",
            delivery_zone=None,
            delivery_fee_ngwee=delivery_b,
            subtotal_ngwee=price_b,
        ),
    ]


class TestConcurrentSubmit:
    def test_two_class_e_checkouts_serialize_at_weekly_capacity(
        self, db: PgConn, db_url_env: None, pg_service: SupabaseServiceClient
    ) -> None:
        listing_id = str(uuid.uuid4())
        price = 90_000
        _insert_made_to_order_listing(
            db,
            listing_id=listing_id,
            product_class="E",
            capacity_per_week=1,
            price_ngwee=price,
        )

        session_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
        for session_id in session_ids:
            _insert_checkout_group(
                db,
                session_id=session_id,
                idempotency_key=f"chk-{session_id}",
                subtotal=price,
                delivery_fee=0,
                total=price,
            )
        lines, groups = _single_listing_inputs(
            listing_id=listing_id,
            qty=1,
            price_ngwee=price,
        )

        def _submit(session_id: str) -> CreateOrdersResult | AppError:
            try:
                return create_orders_atomic(
                    client=pg_service.client,
                    customer_id=CUSTOMER_ID,
                    session_id=session_id,
                    idempotency_key=f"class-e-{session_id}",
                    payment_method="momo",
                    cart_lines=lines,
                    vendor_groups=groups,
                )
            except AppError as exc:
                return exc

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(_submit, session_ids))

        created = [item for item in outcomes if isinstance(item, CreateOrdersResult)]
        rejected = [item for item in outcomes if isinstance(item, AppError)]
        assert len(created) == 1
        assert len(rejected) == 1
        assert rejected[0].code == "cart.class_e_capacity_exceeded"
        assert rejected[0].http_status == 409
        assert rejected[0].details["listing_id"] == listing_id
        assert rejected[0].details["remaining"] == 0
        assert rejected[0].details["requested_qty"] == 1

        total_orders = db.run(
            "SELECT count(*)::text FROM public.order_item_products "
            f"WHERE listing_id = '{listing_id}';"
        )
        assert total_orders.ok and total_orders.rows == ["1"]
        statuses = db.run(
            "SELECT status FROM public.checkout_groups "
            f"WHERE id IN ('{session_ids[0]}', '{session_ids[1]}') ORDER BY status;"
        )
        assert statuses.ok and statuses.rows == ["completed", "pending"]

    def test_legacy_made_to_order_does_not_require_stock_hold_or_capacity(
        self, db: PgConn, db_url_env: None, pg_service: SupabaseServiceClient
    ) -> None:
        listing_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        price = 45_000
        _insert_made_to_order_listing(
            db,
            listing_id=listing_id,
            product_class="A",
            capacity_per_week=None,
            price_ngwee=price,
        )
        _insert_checkout_group(
            db,
            session_id=session_id,
            idempotency_key=f"chk-{session_id}",
            subtotal=price,
            delivery_fee=0,
            total=price,
        )
        lines, groups = _single_listing_inputs(
            listing_id=listing_id,
            qty=1,
            price_ngwee=price,
        )

        result = create_orders_atomic(
            client=pg_service.client,
            customer_id=CUSTOMER_ID,
            session_id=session_id,
            idempotency_key=f"legacy-mto-{session_id}",
            payment_method="momo",
            cart_lines=lines,
            vendor_groups=groups,
        )

        assert result.replayed is False
        assert _order_count(db, session_id) == 1
        assert _reservation_count(db, session_id) == 0

    def test_two_concurrent_submits_persist_one_order_set(
        self, db: PgConn, db_url_env: None, pg_service: SupabaseServiceClient
    ) -> None:
        ids = _load_ids()
        session_id = str(uuid.uuid4())
        listing_a = str(uuid.uuid4())
        listing_b = str(uuid.uuid4())
        price_a = 150_000
        price_b = 85_000
        subtotal = price_a + price_b
        delivery_a = 3_000
        total = subtotal + delivery_a
        idem_key = f"concurrent-{uuid.uuid4()}"

        _insert_tracked_listing(
            db,
            listing_id=listing_a,
            vendor_id=VENDOR_A,
            product_id=ids["products"]["phone"],
            stock_qty=5,
            price_ngwee=price_a,
        )
        _insert_tracked_listing(
            db,
            listing_id=listing_b,
            vendor_id=VENDOR_B,
            product_id=ids["products"]["chitenge"],
            stock_qty=5,
            price_ngwee=price_b,
        )
        _insert_checkout_group(
            db,
            session_id=session_id,
            idempotency_key=f"chk-{session_id}",
            subtotal=subtotal,
            delivery_fee=delivery_a,
            total=total,
        )
        claim_reservation(listing_id=listing_a, checkout_group_id=session_id, qty=1, ttl_minutes=15)
        claim_reservation(listing_id=listing_b, checkout_group_id=session_id, qty=1, ttl_minutes=15)

        lines = _build_lines(listing_a, listing_b, 1, 1, price_a, price_b)
        groups = _two_vendor_groups(price_a, delivery_a, price_b, 0)

        def _submit() -> CreateOrdersResult:
            return create_orders_atomic(
                client=pg_service.client,
                customer_id=CUSTOMER_ID,
                session_id=session_id,
                idempotency_key=idem_key,
                payment_method="momo",
                cart_lines=lines,
                vendor_groups=groups,
                address_id=ADDRESS_ID,
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(_submit), pool.submit(_submit)]
            results = [f.result() for f in futures]

        # Exactly ONE order set of two per-vendor orders — never four.
        assert _order_count(db, session_id) == 2
        # Both calls resolve to the same checkout group; exactly one is the writer.
        assert {r.checkout_group_id for r in results} == {session_id}
        assert sum(1 for r in results if not r.replayed) == 1
        assert sum(1 for r in results if r.replayed) == 1
        # Idempotent: both return the identical order set.
        assert results[0].idempotency_key == results[1].idempotency_key == idem_key
        assert {o.order_id for o in results[0].orders} == {o.order_id for o in results[1].orders}
        # Stock consumed once (5 - 1 each), never double-decremented.
        assert _stock_qty(db, listing_a) == 4
        assert _stock_qty(db, listing_b) == 4

    def test_hold_reclaimed_before_tx_rejects_no_oversell(
        self, db: PgConn, db_url_env: None, pg_service: SupabaseServiceClient
    ) -> None:
        ids = _load_ids()
        session_id = str(uuid.uuid4())
        listing_id = str(uuid.uuid4())
        price = 120_000
        idem_key = f"oversell-{uuid.uuid4()}"

        _insert_tracked_listing(
            db,
            listing_id=listing_id,
            vendor_id=VENDOR_A,
            product_id=ids["products"]["phone"],
            stock_qty=1,
            price_ngwee=price,
        )
        _insert_checkout_group(
            db,
            session_id=session_id,
            idempotency_key=f"chk-{session_id}",
            subtotal=price,
            delivery_fee=0,
            total=price,
        )
        # Claim decrements stock 1 -> 0 and writes the hold.
        claim_reservation(
            listing_id=listing_id, checkout_group_id=session_id, qty=1, ttl_minutes=15
        )
        assert _stock_qty(db, listing_id) == 0
        assert _reservation_count(db, session_id) == 1

        # A sweeper reclaims the expired hold between pre-check and tx: the hold row
        # is removed and the stock restocked (now buyable by someone else).
        db.run(f"DELETE FROM public.stock_reservations WHERE checkout_group_id = '{session_id}';")
        db.run(
            "UPDATE public.vendor_listings SET stock_qty = stock_qty + 1 "
            f"WHERE id = '{listing_id}';"
        )
        assert _stock_qty(db, listing_id) == 1

        lines = [
            CartLineInput(
                cart_item_id=str(uuid.uuid4()),
                listing_id=listing_id,
                vendor_id=VENDOR_A,
                qty=1,
                unit_price_ngwee=price,
                title_snapshot="Phone",
            )
        ]
        groups = [
            VendorFulfilmentInput(
                vendor_id=VENDOR_A,
                fulfilment="pickup",
                delivery_zone=None,
                delivery_fee_ngwee=0,
                subtotal_ngwee=price,
            )
        ]

        with pytest.raises(AppError) as excinfo:
            create_orders_atomic(
                client=pg_service.client,
                customer_id=CUSTOMER_ID,
                session_id=session_id,
                idempotency_key=idem_key,
                payment_method="momo",
                cart_lines=lines,
                vendor_groups=groups,
                address_id=ADDRESS_ID,
            )

        assert excinfo.value.code == "checkout.reservation_expired"
        # Whole tx rolled back: no order, group still pending, stock never negative.
        assert _order_count(db, session_id) == 0
        assert _stock_qty(db, listing_id) == 1
        status = db.run(f"SELECT status FROM public.checkout_groups WHERE id = '{session_id}';")
        assert status.ok and status.rows and status.rows[0] == "pending"

    def test_sequential_double_submit_is_idempotent(
        self, db: PgConn, db_url_env: None, pg_service: SupabaseServiceClient
    ) -> None:
        ids = _load_ids()
        session_id = str(uuid.uuid4())
        listing_a = str(uuid.uuid4())
        listing_b = str(uuid.uuid4())
        price_a = 200_000
        price_b = 50_000
        subtotal = price_a + price_b
        delivery_a = 5_000
        total = subtotal + delivery_a
        idem_key = f"double-{uuid.uuid4()}"

        _insert_tracked_listing(
            db,
            listing_id=listing_a,
            vendor_id=VENDOR_A,
            product_id=ids["products"]["phone"],
            stock_qty=3,
            price_ngwee=price_a,
        )
        _insert_tracked_listing(
            db,
            listing_id=listing_b,
            vendor_id=VENDOR_B,
            product_id=ids["products"]["chitenge"],
            stock_qty=3,
            price_ngwee=price_b,
        )
        _insert_checkout_group(
            db,
            session_id=session_id,
            idempotency_key=f"chk-{session_id}",
            subtotal=subtotal,
            delivery_fee=delivery_a,
            total=total,
        )
        claim_reservation(listing_id=listing_a, checkout_group_id=session_id, qty=1, ttl_minutes=15)
        claim_reservation(listing_id=listing_b, checkout_group_id=session_id, qty=1, ttl_minutes=15)

        lines = _build_lines(listing_a, listing_b, 1, 1, price_a, price_b)
        groups = _two_vendor_groups(price_a, delivery_a, price_b, 0)

        first = create_orders_atomic(
            client=pg_service.client,
            customer_id=CUSTOMER_ID,
            session_id=session_id,
            idempotency_key=idem_key,
            payment_method="cod",
            cart_lines=lines,
            vendor_groups=groups,
            address_id=ADDRESS_ID,
        )
        second = create_orders_atomic(
            client=pg_service.client,
            customer_id=CUSTOMER_ID,
            session_id=session_id,
            idempotency_key=idem_key,
            payment_method="cod",
            cart_lines=lines,
            vendor_groups=groups,
            address_id=ADDRESS_ID,
        )

        assert first.replayed is False
        assert second.replayed is True
        assert _order_count(db, session_id) == 2
        assert {o.order_id for o in first.orders} == {o.order_id for o in second.orders}
