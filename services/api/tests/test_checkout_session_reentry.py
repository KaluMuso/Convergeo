"""Re-entering checkout, and retrying a placed order, must not strand the buyer.

Three defects, one journey:

* every visit to /checkout opened a new session with its own stock hold and left
  the previous hold in place, so a refresh or a trip back to the cart showed the
  buyer their own last-unit item as out of stock until the hold timed out;
* once the reservation TTL had passed, any call that touched a *completed*
  session flipped it to ``expired`` — so a retried ``POST /orders`` answered
  "reservation expired" for an order that had in fact been placed;
* the fulfilment step would rewrite the totals of a session that already had
  orders.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.errors import AppError
from app.main import create_app
from app.routers.checkout import (
    _ensure_session_active,
    _release_session_holds,
    _supersede_own_pending_sessions,
)
from app.services.orders.create import (
    CartLineInput,
    VendorFulfilmentInput,
    create_orders_atomic,
    replay_if_completed,
)
from app.services.stock.claim import claim_reservation
from app.supabase_client import SupabaseServiceClient
from fastapi.testclient import TestClient
from tests.rls.conftest import PgConn
from tests.test_order_creation import (
    CUSTOMER_ID,
    VENDOR_A,
    _group_status,
    _insert_checkout_group,
    _insert_tracked_listing,
    _load_ids,
    _reservation_count,
    db,  # noqa: F401  (module-scoped fixture reuse)
    db_url_env,  # noqa: F401
    pg_service,  # noqa: F401
)

PRICE = 30_000


def _stock(conn: PgConn, listing_id: str) -> int:
    result = conn.run(
        f"SELECT stock_qty::text FROM public.vendor_listings WHERE id = '{listing_id}';"
    )
    assert result.ok and result.rows, result.error
    return int(result.rows[0])


def _open_session(conn: PgConn, listing_id: str, *, customer_id: str = CUSTOMER_ID) -> str:
    session_id = str(uuid.uuid4())
    if customer_id == CUSTOMER_ID:
        _insert_checkout_group(
            conn,
            session_id=session_id,
            idempotency_key=f"chk-{session_id}",
            subtotal=PRICE,
            delivery_fee=0,
            total=PRICE,
        )
    else:
        inserted = conn.run(
            f"""
            INSERT INTO public.checkout_groups (
              id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee,
              total_ngwee, status
            ) VALUES (
              '{session_id}', '{customer_id}', 'chk-{session_id}', {PRICE}, 0, {PRICE}, 'pending'
            );
            """
        )
        assert inserted.ok, inserted.error
    claimed = claim_reservation(
        listing_id=listing_id, checkout_group_id=session_id, qty=1, ttl_minutes=15
    )
    assert claimed.claimed
    return session_id


def _listing(conn: PgConn, *, stock_qty: int) -> str:
    listing_id = str(uuid.uuid4())
    _insert_tracked_listing(
        conn,
        listing_id=listing_id,
        vendor_id=VENDOR_A,
        product_id=_load_ids()["products"]["phone"],
        stock_qty=stock_qty,
        price_ngwee=PRICE,
    )
    return listing_id


def _other_customer(conn: PgConn) -> str:
    result = conn.run(
        f"SELECT id::text FROM auth.users WHERE id <> '{CUSTOMER_ID}' ORDER BY id LIMIT 1;"
    )
    assert result.ok and result.rows, result.error
    return result.rows[0]


def _clear_pending(conn: PgConn) -> None:
    """Earlier cases leave pending sessions for the shared customer; settle them."""
    _supersede_own_pending_sessions(CUSTOMER_ID)


class TestSupersedeOwnPendingSessions:
    def test_reentering_checkout_frees_the_buyers_own_last_unit(
        self,
        db: PgConn,  # noqa: F811
        db_url_env: None,  # noqa: F811
    ) -> None:
        _clear_pending(db)
        listing_id = _listing(db, stock_qty=1)
        first = _open_session(db, listing_id)
        assert _stock(db, listing_id) == 0

        released = _supersede_own_pending_sessions(CUSTOMER_ID)

        assert released == 1
        assert _stock(db, listing_id) == 1
        assert _reservation_count(db, first) == 0
        assert _group_status(db, first) == "abandoned"
        # The unit is really back: a fresh session can hold it again.
        second = _open_session(db, listing_id)
        assert _reservation_count(db, second) == 1
        assert _stock(db, listing_id) == 0

    def test_leaves_another_buyers_hold_alone(
        self,
        db: PgConn,  # noqa: F811
        db_url_env: None,  # noqa: F811
    ) -> None:
        _clear_pending(db)
        listing_id = _listing(db, stock_qty=2)
        theirs = _open_session(db, listing_id, customer_id=_other_customer(db))

        assert _supersede_own_pending_sessions(CUSTOMER_ID) == 0

        assert _group_status(db, theirs) == "pending"
        assert _reservation_count(db, theirs) == 1
        assert _stock(db, listing_id) == 1

    def test_leaves_an_ordered_session_alone(
        self,
        db: PgConn,  # noqa: F811
        db_url_env: None,  # noqa: F811
        pg_service: SupabaseServiceClient,  # noqa: F811
    ) -> None:
        _clear_pending(db)
        listing_id = _listing(db, stock_qty=2)
        ordered = _open_session(db, listing_id)
        _place_cod(pg_service, ordered, listing_id, key=f"placed-{uuid.uuid4()}")

        assert _supersede_own_pending_sessions(CUSTOMER_ID) == 0

        assert _group_status(db, ordered) == "completed"
        # Sold stock stays sold.
        assert _stock(db, listing_id) == 1

    def test_release_session_holds_restocks_every_line(
        self,
        db: PgConn,  # noqa: F811
        db_url_env: None,  # noqa: F811
    ) -> None:
        _clear_pending(db)
        first_listing = _listing(db, stock_qty=1)
        second_listing = _listing(db, stock_qty=4)
        session_id = _open_session(db, first_listing)
        assert claim_reservation(
            listing_id=second_listing, checkout_group_id=session_id, qty=3, ttl_minutes=15
        ).claimed

        assert _release_session_holds(session_id) == 2

        assert _stock(db, first_listing) == 1
        assert _stock(db, second_listing) == 4
        assert _reservation_count(db, session_id) == 0


def _place_cod(
    pg_service: SupabaseServiceClient,  # noqa: F811
    session_id: str,
    listing_id: str,
    *,
    key: str,
) -> None:
    create_orders_atomic(
        client=pg_service.client,
        customer_id=CUSTOMER_ID,
        session_id=session_id,
        idempotency_key=key,
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


class TestReplayIfCompleted:
    def test_pending_session_is_not_a_replay(
        self,
        db: PgConn,  # noqa: F811
        db_url_env: None,  # noqa: F811
        pg_service: SupabaseServiceClient,  # noqa: F811
    ) -> None:
        _clear_pending(db)
        session_id = _open_session(db, _listing(db, stock_qty=1))

        assert (
            replay_if_completed(
                pg_service.client,
                session_id=session_id,
                customer_id=CUSTOMER_ID,
                idempotency_key="any",
            )
            is None
        )

    def test_same_key_gets_the_placed_orders_back(
        self,
        db: PgConn,  # noqa: F811
        db_url_env: None,  # noqa: F811
        pg_service: SupabaseServiceClient,  # noqa: F811
    ) -> None:
        _clear_pending(db)
        listing_id = _listing(db, stock_qty=1)
        session_id = _open_session(db, listing_id)
        key = f"retry-{uuid.uuid4()}"
        _place_cod(pg_service, session_id, listing_id, key=key)

        replay = replay_if_completed(
            pg_service.client,
            session_id=session_id,
            customer_id=CUSTOMER_ID,
            idempotency_key=key,
        )

        assert replay is not None and replay.replayed is True
        assert len(replay.orders) == 1 and replay.orders[0].cod is True

    def test_other_key_on_a_placed_session_conflicts(
        self,
        db: PgConn,  # noqa: F811
        db_url_env: None,  # noqa: F811
        pg_service: SupabaseServiceClient,  # noqa: F811
    ) -> None:
        _clear_pending(db)
        listing_id = _listing(db, stock_qty=1)
        session_id = _open_session(db, listing_id)
        _place_cod(pg_service, session_id, listing_id, key=f"retry-{uuid.uuid4()}")

        with pytest.raises(AppError) as excinfo:
            replay_if_completed(
                pg_service.client,
                session_id=session_id,
                customer_id=CUSTOMER_ID,
                idempotency_key="a-different-key",
            )
        assert excinfo.value.code == "orders.session_already_completed"
        assert excinfo.value.http_status == 409


def _service_with_group(group: dict[str, Any]) -> MagicMock:
    service = MagicMock()

    def table(name: str) -> MagicMock:
        builder = MagicMock()
        if name == "checkout_groups":
            chain = builder.select.return_value.eq.return_value.eq.return_value
            chain.maybe_single.return_value.execute.return_value = MagicMock(data=group)
        elif name == "stock_reservations":
            chain = builder.select.return_value.eq.return_value.order.return_value
            chain.limit.return_value.execute.return_value = MagicMock(data=[])
        return builder

    service.client.table.side_effect = table
    return service


class TestEnsureSessionActive:
    def test_completed_session_is_never_expired_after_the_ttl(self) -> None:
        long_ago = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        service = _service_with_group(
            {"id": "s", "status": "completed", "created_at": long_ago, "total_ngwee": PRICE}
        )

        with (
            patch("app.routers.checkout.get_reservation_ttl_minutes", return_value=15),
            patch("app.routers.checkout.expire_checkout_group_if_unpaid") as expire,
        ):
            group, _ = _ensure_session_active(service, "s", CUSTOMER_ID)

        assert group["status"] == "completed"
        expire.assert_not_called()

    def test_stale_pending_session_still_expires(self) -> None:
        long_ago = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        service = _service_with_group({"id": "s", "status": "pending", "created_at": long_ago})

        with (
            patch("app.routers.checkout.get_reservation_ttl_minutes", return_value=15),
            patch("app.routers.checkout.expire_checkout_group_if_unpaid") as expire,
            pytest.raises(AppError) as excinfo,
        ):
            _ensure_session_active(service, "s", CUSTOMER_ID)

        assert excinfo.value.code == "checkout.reservation_expired"
        expire.assert_called_once()


@pytest.fixture
def api() -> Generator[tuple[TestClient, MagicMock], None, None]:
    app = create_app()
    service = MagicMock()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=CUSTOMER_ID, roles=frozenset({"customer"}), token="tok"
    )
    app.dependency_overrides[get_supabase_client] = lambda: service
    yield TestClient(app, raise_server_exceptions=False), service


class TestCompletedSessionEndpoints:
    def test_fulfilment_step_refuses_to_rewrite_an_ordered_session(
        self, api: tuple[TestClient, MagicMock]
    ) -> None:
        client, service = api
        completed = ({"id": "s", "status": "completed"}, datetime.now(UTC))
        with patch("app.routers.checkout._ensure_session_active", return_value=completed):
            response = client.post(
                "/checkout/steps/fulfilment",
                json={
                    "session_id": str(uuid.uuid4()),
                    "groups": [{"vendor_id": VENDOR_A, "fulfilment": "pickup"}],
                },
            )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "orders.session_already_completed"
        service.client.table.assert_not_called()

    def test_retried_order_replays_without_reading_the_emptied_cart(
        self, api: tuple[TestClient, MagicMock]
    ) -> None:
        client, _ = api
        session_id = str(uuid.uuid4())
        replay = MagicMock(
            checkout_group_id=session_id,
            idempotency_key="retry-key",
            status="completed",
            subtotal_ngwee=PRICE,
            delivery_fee_ngwee=0,
            total_ngwee=PRICE,
            replayed=True,
            orders=(),
        )
        with (
            patch("app.routers.orders_create._ensure_session_active"),
            patch("app.routers.orders_create.replay_if_completed", return_value=replay),
            patch("app.routers.orders_create.get_user_client") as user_client,
        ):
            response = client.post(
                "/orders",
                json={
                    "session_id": session_id,
                    "idempotency_key": "retry-key",
                    "method": "cod",
                    "groups": [
                        {
                            "vendor_id": VENDOR_A,
                            "fulfilment": "pickup",
                            "delivery_fee_ngwee": 0,
                            "subtotal_ngwee": PRICE,
                        }
                    ],
                },
            )

        assert response.status_code == 200, response.text
        assert response.json()["replayed"] is True
        user_client.assert_not_called()
