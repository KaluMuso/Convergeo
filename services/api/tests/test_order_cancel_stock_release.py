"""Cancelled / vendor-rejected orders return the stock they consumed — exactly once.

Real Postgres: order creation records per-line consumption and the
``orders_release_cancelled_stock`` trigger restores it inside the same
transaction as the guarded status update (migration 20261113071000).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator

import pytest
from app.services.orders.create import (
    CartLineInput,
    VendorFulfilmentInput,
    create_orders_atomic,
)
from app.services.orders.state import (
    ActorRole,
    OrderEvent,
    OrderTransitionError,
    transition_order,
)
from app.services.stock.claim import claim_reservation
from app.supabase_client import SupabaseServiceClient
from tests.rls.conftest import PgConn, apply_migrations, seed_matrix_fixtures
from tests.test_order_creation import _insert_checkout_group, _load_ids, _PgClient

CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
VENDOR_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VENDOR_A_OWNER = "33333333-3333-3333-3333-333333333333"
ADMIN_ID = "66666666-6666-6666-6666-666666666666"
PRICE = 40_000
_DB_NAME = "vergeo5_order_stock_release_test"


@pytest.fixture(scope="module")
def db() -> Generator[PgConn, None, None]:
    # CI / callers may hand over a disposable, fully migrated database.
    if isolated_url := os.environ.get("ORDER_TEST_DB_URL"):
        conn = PgConn(isolated_url)
        ready = conn.run("SELECT 1 FROM public.orders LIMIT 1")
        assert ready.ok, ready.error
        seed_matrix_fixtures(conn)
        yield conn
        return
    admin = PgConn("postgresql://postgres:postgres@127.0.0.1:5432/postgres")
    if not admin.run("SELECT 1").ok:
        pytest.skip("Postgres not reachable on 127.0.0.1:5432")
    admin.run(f"DROP DATABASE IF EXISTS {_DB_NAME};")
    admin.run(f"CREATE DATABASE {_DB_NAME};")
    conn = PgConn(f"postgresql://postgres:postgres@127.0.0.1:5432/{_DB_NAME}")
    conn.run("DROP SCHEMA IF EXISTS public CASCADE")
    conn.run("CREATE SCHEMA public")
    conn.run("DROP SCHEMA IF EXISTS auth CASCADE")
    apply_migrations(conn)
    seed_matrix_fixtures(conn)
    yield conn


@pytest.fixture
def db_url_env(db: PgConn) -> Generator[None, None, None]:
    previous = os.environ.get("SUPABASE_DB_URL")
    os.environ["SUPABASE_DB_URL"] = db.dsn
    yield
    if previous is None:
        os.environ.pop("SUPABASE_DB_URL", None)
    else:
        os.environ["SUPABASE_DB_URL"] = previous


@pytest.fixture
def service(db: PgConn) -> SupabaseServiceClient:
    return SupabaseServiceClient(_PgClient(db))  # type: ignore[arg-type]


def _scalar(conn: PgConn, sql: str) -> str:
    result = conn.run(sql)
    assert result.ok, result.error
    assert result.rows, sql
    return result.rows[0]


def _listing(conn: PgConn, *, stock_qty: int) -> str:
    listing_id = str(uuid.uuid4())
    product_id = _load_ids()["products"]["phone"]
    result = conn.run(
        f"""
        INSERT INTO public.vendor_listings (
          id, vendor_id, product_id, price_ngwee, condition, stock_mode, stock_qty, status
        ) VALUES (
          '{listing_id}', '{VENDOR_A}', '{product_id}', {PRICE},
          'new', 'tracked', {stock_qty}, 'active'
        );
        """
    )
    assert result.ok, result.error
    return listing_id


def _variant(conn: PgConn, *, listing_id: str, stock_qty: int) -> str:
    product_id = _load_ids()["products"]["phone"]
    product_variant_id = str(uuid.uuid4())
    variant_id = str(uuid.uuid4())
    result = conn.run(
        f"""
        INSERT INTO public.product_variants (id, product_id, sku)
        VALUES ('{product_variant_id}', '{product_id}', 'SKU-{variant_id[:8]}');
        INSERT INTO public.vendor_listing_variants (
          id, listing_id, product_variant_id, price_ngwee, stock_qty, status
        ) VALUES (
          '{variant_id}', '{listing_id}', '{product_variant_id}', {PRICE},
          {stock_qty}, 'active'
        );
        """
    )
    assert result.ok, result.error
    return variant_id


def _listing_stock(conn: PgConn, listing_id: str) -> int:
    return int(
        _scalar(conn, f"SELECT stock_qty::text FROM public.vendor_listings WHERE id='{listing_id}'")
    )


def _variant_stock(conn: PgConn, variant_id: str) -> int:
    return int(
        _scalar(
            conn,
            f"SELECT stock_qty::text FROM public.vendor_listing_variants WHERE id='{variant_id}'",
        )
    )


def _place_order(
    conn: PgConn,
    service: SupabaseServiceClient,
    *,
    listing_id: str,
    qty: int,
    variant_id: str | None = None,
) -> str:
    """Claim a hold and place a COD pickup order for one line; return the order id."""
    session_id = str(uuid.uuid4())
    subtotal = PRICE * qty
    _insert_checkout_group(
        conn,
        session_id=session_id,
        idempotency_key=f"chk-{session_id}",
        subtotal=subtotal,
        delivery_fee=0,
        total=subtotal,
    )
    claimed = claim_reservation(
        listing_id=listing_id, checkout_group_id=session_id, qty=qty, ttl_minutes=15
    )
    assert claimed.claimed
    result = create_orders_atomic(
        client=service.client,
        customer_id=CUSTOMER_ID,
        session_id=session_id,
        idempotency_key=f"idem-{session_id}",
        payment_method="cod",
        cart_lines=[
            CartLineInput(
                cart_item_id=str(uuid.uuid4()),
                listing_id=listing_id,
                vendor_id=VENDOR_A,
                qty=qty,
                unit_price_ngwee=PRICE,
                title_snapshot="Phone",
                listing_variant_id=variant_id,
                variant_snapshot={"listing_variant_id": variant_id} if variant_id else None,
            )
        ],
        vendor_groups=[
            VendorFulfilmentInput(
                vendor_id=VENDOR_A,
                fulfilment="pickup",
                delivery_zone=None,
                delivery_fee_ngwee=0,
                subtotal_ngwee=subtotal,
            )
        ],
    )
    assert len(result.orders) == 1
    return result.orders[0].order_id


def _set_status(conn: PgConn, order_id: str, status: str) -> None:
    # Fixture shortcut to put an order mid-lifecycle (not a production path).
    result = conn.run(f"UPDATE public.orders SET status='{status}' WHERE id='{order_id}';")
    assert result.ok, result.error


def _release_audits(conn: PgConn, order_id: str) -> int:
    return int(
        _scalar(
            conn,
            "SELECT count(*)::text FROM public.audit_log "
            f"WHERE action='order.stock_released' AND entity_id='{order_id}'",
        )
    )


@pytest.mark.usefixtures("db_url_env")
class TestCancelReleasesStock:
    def test_order_creation_records_consumed_stock(
        self, db: PgConn, service: SupabaseServiceClient
    ) -> None:
        listing_id = _listing(db, stock_qty=5)
        order_id = _place_order(db, service, listing_id=listing_id, qty=2)

        assert _listing_stock(db, listing_id) == 3
        row = _scalar(
            db,
            "SELECT listing_qty::text || '|' || coalesce(location_id::text,'') || '|' "
            "|| (released_at IS NULL)::text FROM public.order_item_stock_consumption "
            f"WHERE order_id='{order_id}'",
        )
        assert row == "2||true"

    def test_customer_cancel_returns_stock_once_with_audit(
        self, db: PgConn, service: SupabaseServiceClient
    ) -> None:
        listing_id = _listing(db, stock_qty=5)
        order_id = _place_order(db, service, listing_id=listing_id, qty=2)

        transition_order(
            order_id=order_id,
            event=OrderEvent.CANCEL,
            actor_role=ActorRole.CUSTOMER,
            actor_id=CUSTOMER_ID,
            note="changed mind",
        )
        assert _listing_stock(db, listing_id) == 5
        assert _release_audits(db, order_id) == 1
        actor = _scalar(
            db,
            "SELECT actor::text FROM public.audit_log "
            f"WHERE action='order.stock_released' AND entity_id='{order_id}'",
        )
        assert actor == CUSTOMER_ID

        # A retried cancel is refused by the state machine and restores nothing.
        with pytest.raises(OrderTransitionError):
            transition_order(
                order_id=order_id,
                event=OrderEvent.CANCEL,
                actor_role=ActorRole.CUSTOMER,
                actor_id=CUSTOMER_ID,
                note="changed mind (retry)",
            )
        assert _listing_stock(db, listing_id) == 5
        assert _release_audits(db, order_id) == 1

    def test_vendor_reject_returns_listing_and_variant_stock(
        self, db: PgConn, service: SupabaseServiceClient
    ) -> None:
        listing_id = _listing(db, stock_qty=6)
        variant_id = _variant(db, listing_id=listing_id, stock_qty=4)
        order_id = _place_order(db, service, listing_id=listing_id, qty=3, variant_id=variant_id)
        assert _listing_stock(db, listing_id) == 3
        assert _variant_stock(db, variant_id) == 1

        transition_order(
            order_id=order_id,
            event=OrderEvent.REJECT,
            actor_role=ActorRole.VENDOR,
            actor_id=VENDOR_A_OWNER,
            note="out of stock at the shop",
        )
        assert _listing_stock(db, listing_id) == 6
        assert _variant_stock(db, variant_id) == 4

    def test_release_is_idempotent_if_the_trigger_fires_again(
        self, db: PgConn, service: SupabaseServiceClient
    ) -> None:
        listing_id = _listing(db, stock_qty=5)
        order_id = _place_order(db, service, listing_id=listing_id, qty=1)
        transition_order(
            order_id=order_id,
            event=OrderEvent.CANCEL,
            actor_role=ActorRole.CUSTOMER,
            actor_id=CUSTOMER_ID,
            note="first",
        )
        assert _listing_stock(db, listing_id) == 5
        # Force the order back into a pre-dispatch state and cancel again: the
        # consumption rows are already released, so nothing is restored twice.
        _set_status(db, order_id, "confirmed")
        _set_status(db, order_id, "cancelled")
        assert _listing_stock(db, listing_id) == 5
        assert _release_audits(db, order_id) == 1

    def test_admin_cancel_after_shipping_restores_nothing(
        self, db: PgConn, service: SupabaseServiceClient
    ) -> None:
        listing_id = _listing(db, stock_qty=5)
        order_id = _place_order(db, service, listing_id=listing_id, qty=2)
        _set_status(db, order_id, "shipped")

        transition_order(
            order_id=order_id,
            event=OrderEvent.CANCEL,
            actor_role=ActorRole.ADMIN,
            actor_id=ADMIN_ID,
            note="lost in transit",
        )
        assert _listing_stock(db, listing_id) == 3
        assert _release_audits(db, order_id) == 0
        unreleased = _scalar(
            db,
            "SELECT count(*)::text FROM public.order_item_stock_consumption "
            f"WHERE order_id='{order_id}' AND released_at IS NULL",
        )
        assert unreleased == "1"

    def test_cancel_of_processing_order_returns_branch_stock(
        self, db: PgConn, service: SupabaseServiceClient
    ) -> None:
        listing_id = _listing(db, stock_qty=0)
        location_id = str(uuid.uuid4())
        setup = db.run(
            f"""
            INSERT INTO public.vendor_locations (
              id, vendor_id, lat, lng, landmark, status, is_primary
            ) VALUES (
              '{location_id}', '{VENDOR_A}', -15.41, 28.28, 'Cairo Road', 'active', false
            );
            INSERT INTO public.listing_location_stock (listing_id, location_id, stock_qty)
            VALUES ('{listing_id}', '{location_id}', 4);
            """
        )
        assert setup.ok, setup.error
        session_id = str(uuid.uuid4())
        _insert_checkout_group(
            db,
            session_id=session_id,
            idempotency_key=f"chk-{session_id}",
            subtotal=PRICE,
            delivery_fee=0,
            total=PRICE,
        )
        assert claim_reservation(
            listing_id=listing_id,
            checkout_group_id=session_id,
            qty=1,
            ttl_minutes=15,
            location_id=location_id,
        ).claimed
        result = create_orders_atomic(
            client=service.client,
            customer_id=CUSTOMER_ID,
            session_id=session_id,
            idempotency_key=f"idem-{session_id}",
            payment_method="cod",
            cart_lines=[
                CartLineInput(
                    cart_item_id=str(uuid.uuid4()),
                    listing_id=listing_id,
                    vendor_id=VENDOR_A,
                    qty=1,
                    unit_price_ngwee=PRICE,
                    title_snapshot="Phone",
                )
            ],
            vendor_groups=[
                VendorFulfilmentInput(
                    vendor_id=VENDOR_A,
                    fulfilment="pickup",
                    delivery_zone=None,
                    delivery_fee_ngwee=0,
                    subtotal_ngwee=PRICE,
                )
            ],
        )
        order_id = result.orders[0].order_id

        def branch_stock() -> int:
            return int(
                _scalar(
                    db,
                    "SELECT stock_qty::text FROM public.listing_location_stock "
                    f"WHERE listing_id='{listing_id}' AND location_id='{location_id}'",
                )
            )

        assert branch_stock() == 3
        _set_status(db, order_id, "processing")
        transition_order(
            order_id=order_id,
            event=OrderEvent.CANCEL,
            actor_role=ActorRole.VENDOR,
            actor_id=VENDOR_A_OWNER,
            note="branch closed",
        )
        assert branch_stock() == 4
        assert _listing_stock(db, listing_id) == 0
