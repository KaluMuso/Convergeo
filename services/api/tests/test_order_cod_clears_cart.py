"""A placed COD order must take its lines out of the customer's cart.

Nothing emptied the cart after ``POST /orders``: the buyer landed on the
confirmation page with the badge still counting the items they had just bought,
and a second trip through checkout placed the same cash-on-delivery order again.
The ordered lines are now deleted in the same transaction that creates the
orders, so a rollback keeps the cart and a commit never leaves a stale line.
"""

from __future__ import annotations

import uuid

import pytest
from app.services.orders.create import (
    CartLineInput,
    VendorFulfilmentInput,
    create_orders_atomic,
)
from app.services.stock.claim import claim_reservation
from app.supabase_client import SupabaseServiceClient
from tests.rls.conftest import PgConn
from tests.test_order_creation import (
    CUSTOMER_ID,
    VENDOR_A,
    _insert_checkout_group,
    _insert_tracked_listing,
    _load_ids,
    _order_count,
    db,  # noqa: F401  (module-scoped fixture reuse)
    db_url_env,  # noqa: F401
    pg_service,  # noqa: F401
)

PRICE = 40_000


def _seed_cart(conn: PgConn, *, listing_ids: list[str]) -> tuple[str, dict[str, str]]:
    """Give the shared customer one active cart holding ``listing_ids``."""
    cleared = conn.run(f"DELETE FROM public.carts WHERE user_id = '{CUSTOMER_ID}';")
    assert cleared.ok, cleared.error
    cart_id = str(uuid.uuid4())
    created = conn.run(
        f"INSERT INTO public.carts (id, user_id, status) "
        f"VALUES ('{cart_id}', '{CUSTOMER_ID}', 'active');"
    )
    assert created.ok, created.error
    item_ids: dict[str, str] = {}
    for listing_id in listing_ids:
        item_id = str(uuid.uuid4())
        inserted = conn.run(
            f"""
            INSERT INTO public.cart_items (
              id, cart_id, listing_id, qty, unit_price_ngwee, wholesale
            ) VALUES ('{item_id}', '{cart_id}', '{listing_id}', 1, {PRICE}, false);
            """
        )
        assert inserted.ok, inserted.error
        item_ids[listing_id] = item_id
    return cart_id, item_ids


def _cart_listing_ids(conn: PgConn, cart_id: str) -> set[str]:
    result = conn.run(
        f"SELECT listing_id::text FROM public.cart_items WHERE cart_id = '{cart_id}';"
    )
    assert result.ok, result.error
    return {row for row in result.rows if row}


def _prepare_session(conn: PgConn, listing_id: str) -> str:
    session_id = str(uuid.uuid4())
    _insert_tracked_listing(
        conn,
        listing_id=listing_id,
        vendor_id=VENDOR_A,
        product_id=_load_ids()["products"]["phone"],
        stock_qty=3,
        price_ngwee=PRICE,
    )
    _insert_checkout_group(
        conn,
        session_id=session_id,
        idempotency_key=f"chk-{session_id}",
        subtotal=PRICE,
        delivery_fee=0,
        total=PRICE,
    )
    claim_reservation(listing_id=listing_id, checkout_group_id=session_id, qty=1, ttl_minutes=15)
    return session_id


def _place(
    pg_service: SupabaseServiceClient,  # noqa: F811
    *,
    session_id: str,
    listing_id: str,
    cart_item_id: str,
    payment_method: str,
    inject_failure: str | None = None,
) -> None:
    create_orders_atomic(
        client=pg_service.client,
        customer_id=CUSTOMER_ID,
        session_id=session_id,
        idempotency_key=f"cart-clear-{uuid.uuid4()}",
        payment_method=payment_method,  # type: ignore[arg-type]
        cart_lines=[
            CartLineInput(
                cart_item_id=cart_item_id,
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
        inject_failure=inject_failure,
    )


def test_cod_order_removes_only_the_ordered_lines(
    db: PgConn,  # noqa: F811
    db_url_env: None,  # noqa: F811
    pg_service: SupabaseServiceClient,  # noqa: F811
) -> None:
    ordered = str(uuid.uuid4())
    added_later = str(uuid.uuid4())
    session_id = _prepare_session(db, ordered)
    _insert_tracked_listing(
        db,
        listing_id=added_later,
        vendor_id=VENDOR_A,
        product_id=_load_ids()["products"]["phone"],
        stock_qty=3,
        price_ngwee=PRICE,
    )
    cart_id, item_ids = _seed_cart(db, listing_ids=[ordered, added_later])

    _place(
        pg_service,
        session_id=session_id,
        listing_id=ordered,
        cart_item_id=item_ids[ordered],
        payment_method="cod",
    )

    assert _order_count(db, session_id) == 1
    # The line added in another tab after checkout started was never ordered.
    assert _cart_listing_ids(db, cart_id) == {added_later}


def test_failed_cod_order_keeps_the_cart(
    db: PgConn,  # noqa: F811
    db_url_env: None,  # noqa: F811
    pg_service: SupabaseServiceClient,  # noqa: F811
) -> None:
    listing_id = str(uuid.uuid4())
    session_id = _prepare_session(db, listing_id)
    cart_id, item_ids = _seed_cart(db, listing_ids=[listing_id])

    with pytest.raises(RuntimeError, match="order creation failed"):
        _place(
            pg_service,
            session_id=session_id,
            listing_id=listing_id,
            cart_item_id=item_ids[listing_id],
            payment_method="cod",
            inject_failure="before_commit",
        )

    assert _order_count(db, session_id) == 0
    assert _cart_listing_ids(db, cart_id) == {listing_id}


def test_cod_order_never_deletes_another_customers_line(
    db: PgConn,  # noqa: F811
    db_url_env: None,  # noqa: F811
    pg_service: SupabaseServiceClient,  # noqa: F811
) -> None:
    listing_id = str(uuid.uuid4())
    session_id = _prepare_session(db, listing_id)
    _seed_cart(db, listing_ids=[listing_id])
    other_cart = str(uuid.uuid4())
    other_item = str(uuid.uuid4())
    seeded = db.run(
        f"""
        INSERT INTO public.carts (id, guest_token, status)
        VALUES ('{other_cart}', 'guest-{other_cart}', 'active');
        INSERT INTO public.cart_items (id, cart_id, listing_id, qty, unit_price_ngwee, wholesale)
        VALUES ('{other_item}', '{other_cart}', '{listing_id}', 1, {PRICE}, false);
        """
    )
    assert seeded.ok, seeded.error

    # A forged cart_item_id that belongs to somebody else's cart is left alone.
    _place(
        pg_service,
        session_id=session_id,
        listing_id=listing_id,
        cart_item_id=other_item,
        payment_method="cod",
    )

    assert _cart_listing_ids(db, other_cart) == {listing_id}
