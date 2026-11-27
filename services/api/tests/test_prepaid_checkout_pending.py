"""A prepaid (mobile money / card) checkout stays ``pending`` until it is paid.

Regression: ``create_orders_atomic`` marked every checkout group ``completed`` at
order creation. ``claim_payable_payment`` only claims a ``pending`` group, so the
follow-up ``POST /payments/retry`` that starts the first payment answered
``payment.not_payable`` (409) and no prepaid order could ever be paid.

Now only cash on delivery completes the group when its orders are placed; a
prepaid group completes when ``apply_prepaid_collection_success`` runs. The
idempotency key is persisted either way, and a retried ``POST /orders`` replays
on "orders exist for the group", not on ``status`` alone.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.errors import AppError
from app.routers.checkout import (
    ORDERS_PLACED_KEY,
    _ensure_session_active,
    session_is_ordered,
)
from app.routers.checkout_extras import _require_pending
from app.services.orders import create as create_mod
from app.services.orders.create import (
    CartLineInput,
    VendorFulfilmentInput,
    create_orders_atomic,
    replay_if_completed,
)
from app.services.payments.base import CollectionStatus, InitiateCollectionResult
from app.services.payments.initiate import InitiatePaymentRequest, initiate_checkout_payment
from tests.test_payment_state import (
    ACTOR_ID,
    CHECKOUT_GROUP_ID,
    FakeServiceClient,
    fake_service,  # noqa: F401  (fixture reuse)
)

CUSTOMER = "11111111-1111-1111-1111-111111111111"
VENDOR = "33333333-3333-3333-3333-333333333333"
LISTING = "44444444-4444-4444-4444-444444444444"
PRICE = 25_000


# --------------------------------------------------------------------------- #
# order creation: which statements run for prepaid vs COD
# --------------------------------------------------------------------------- #


def _place(method: str, *, idempotency_key: str = "client-key-1") -> str:
    """Run ``create_orders_atomic`` against a stubbed DB and return the SQL it sent."""
    session_id = str(uuid.uuid4())
    group = {
        "id": session_id,
        "status": "pending",
        "idempotency_key": f"chk-{session_id}",
        "subtotal_ngwee": PRICE,
        "delivery_fee_ngwee": 0,
        "total_ngwee": PRICE,
    }
    sent: list[str] = []

    def fake_run(script: str) -> Any:
        sent.append(script)
        return MagicMock(ok=True, rows=[], error=None)

    client = MagicMock()
    with (
        patch.object(create_mod, "run_sql_script", fake_run),
        patch.object(create_mod, "_fetch_existing_by_idempotency_key", return_value=None),
        patch.object(create_mod, "_fetch_checkout_session", return_value=group),
        patch.object(create_mod, "_session_expired", return_value=False),
        patch.object(create_mod, "_load_commission_rates", return_value={}),
        patch.object(create_mod, "_load_listing_commission_keys", return_value={}),
        patch.object(create_mod, "_load_product_ids", return_value={}),
        patch.object(create_mod, "_load_vendor_owner_ids", return_value={}),
        patch.object(create_mod, "_load_product_names", return_value={}),
        patch.object(create_mod, "_load_orders_for_group", return_value=()),
    ):
        create_orders_atomic(
            client=client,
            customer_id=CUSTOMER,
            session_id=session_id,
            idempotency_key=idempotency_key,
            payment_method=method,  # type: ignore[arg-type]
            cart_lines=[
                CartLineInput(
                    cart_item_id=str(uuid.uuid4()),
                    listing_id=LISTING,
                    vendor_id=VENDOR,
                    qty=1,
                    unit_price_ngwee=PRICE,
                    title_snapshot="Phone",
                )
            ],
            vendor_groups=[
                VendorFulfilmentInput(
                    vendor_id=VENDOR,
                    fulfilment="pickup",
                    delivery_zone=None,
                    delivery_fee_ngwee=0,
                    subtotal_ngwee=PRICE,
                )
            ],
        )
    assert sent, "order creation never reached the database"
    return sent[-1]


def _group_update(script: str) -> str:
    start = script.index("UPDATE public.checkout_groups")
    return script[start : script.index(";", start)]


@pytest.mark.parametrize("method", ["momo", "card"])
def test_prepaid_order_creation_leaves_checkout_pending(method: str) -> None:
    script = _place(method, idempotency_key="prepaid-key")

    update = _group_update(script)
    assert "'completed'" not in update
    assert "status" not in update.split("SET", 1)[1].split("WHERE")[0]
    # The key is still persisted so a retried POST /orders can replay.
    assert "idempotency_key = 'prepaid-key'" in update
    # Prepaid keeps the cart until the payment outcome is known.
    assert "DELETE FROM public.cart_items" not in script


def test_cod_order_creation_still_completes_checkout_and_clears_cart() -> None:
    script = _place("cod", idempotency_key="cod-key")

    update = _group_update(script)
    assert "SET status = 'completed'" in update
    assert "idempotency_key = 'cod-key'" in update
    assert "DELETE FROM public.cart_items" in script


def test_in_transaction_lock_rejects_a_pending_group_that_already_has_orders() -> None:
    """Two concurrent prepaid submits: the loser sees orders, not just 'pending'."""
    script = _place("momo")
    lock = script[script.index("$lock$") :]
    assert "IF v_status <> 'pending'" in lock
    assert "SELECT 1 FROM public.orders WHERE checkout_group_id" in lock
    assert create_mod._ALREADY_COMPLETED_MARKER in lock


# --------------------------------------------------------------------------- #
# idempotent replay of a prepaid (pending, ordered) checkout
# --------------------------------------------------------------------------- #


def _client_with(group: dict[str, Any] | None, *, order_rows: list[dict[str, Any]]) -> MagicMock:
    client = MagicMock()

    def table(name: str) -> MagicMock:
        builder = MagicMock()
        if name == "checkout_groups":
            chain = builder.select.return_value.eq.return_value.eq.return_value
            chain.maybe_single.return_value.execute.return_value = MagicMock(data=group)
        elif name == "orders":
            chain = builder.select.return_value.eq.return_value.limit.return_value
            chain.execute.return_value = MagicMock(data=order_rows)
        return builder

    client.table.side_effect = table
    return client


def _pending_group(key: str) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "status": "pending",
        "idempotency_key": key,
        "subtotal_ngwee": PRICE,
        "delivery_fee_ngwee": 0,
        "total_ngwee": PRICE,
    }


class TestPrepaidReplay:
    def test_same_key_returns_the_existing_orders_without_creating_more(self) -> None:
        group = _pending_group("client-key")
        client = _client_with(group, order_rows=[{"id": "o1"}])
        sentinel = MagicMock(replayed=True)

        with patch.object(create_mod, "_result_from_group", return_value=sentinel) as build:
            result = replay_if_completed(
                client,
                session_id=group["id"],
                customer_id=CUSTOMER,
                idempotency_key="client-key",
            )

        assert result is sentinel
        assert build.call_args.kwargs["replayed"] is True

    def test_create_orders_atomic_replays_instead_of_running_a_second_transaction(self) -> None:
        group = _pending_group("client-key")
        client = _client_with(group, order_rows=[{"id": "o1"}])
        sentinel = MagicMock(replayed=True)

        with (
            patch.object(create_mod, "_fetch_existing_by_idempotency_key", return_value=group),
            patch.object(create_mod, "_result_from_group", return_value=sentinel),
            patch.object(create_mod, "run_sql_script") as run_sql,
        ):
            result = create_orders_atomic(
                client=client,
                customer_id=CUSTOMER,
                session_id=group["id"],
                idempotency_key="client-key",
                payment_method="momo",
                cart_lines=[],
                vendor_groups=[],
            )

        assert result is sentinel
        run_sql.assert_not_called()

    def test_other_key_on_an_ordered_pending_session_conflicts(self) -> None:
        group = _pending_group("client-key")
        client = _client_with(group, order_rows=[{"id": "o1"}])

        with pytest.raises(AppError) as excinfo:
            replay_if_completed(
                client,
                session_id=group["id"],
                customer_id=CUSTOMER,
                idempotency_key="a-different-key",
            )

        assert excinfo.value.code == "orders.session_already_completed"
        assert excinfo.value.http_status == 409

    def test_pending_session_without_orders_is_not_a_replay(self) -> None:
        group = _pending_group("chk-server-token")
        client = _client_with(group, order_rows=[])

        assert (
            replay_if_completed(
                client,
                session_id=group["id"],
                customer_id=CUSTOMER,
                idempotency_key="chk-server-token",
            )
            is None
        )

    def test_abandoned_session_with_orders_is_not_replayed(self) -> None:
        group = {**_pending_group("client-key"), "status": "abandoned"}
        client = _client_with(group, order_rows=[{"id": "o1"}])

        assert (
            replay_if_completed(
                client,
                session_id=group["id"],
                customer_id=CUSTOMER,
                idempotency_key="client-key",
            )
            is None
        )

    def test_race_loser_resolves_to_the_winners_orders(self) -> None:
        group = _pending_group("client-key")
        client = _client_with(group, order_rows=[{"id": "o1"}])
        sentinel = MagicMock(replayed=True)

        with patch.object(create_mod, "_result_from_group", return_value=sentinel):
            result = create_mod._resolve_completed_after_race(
                client,
                session_id=group["id"],
                customer_id=CUSTOMER,
                idempotency_key="client-key",
            )

        assert result is sentinel


# --------------------------------------------------------------------------- #
# step guards must still treat an ordered prepaid session as final
# --------------------------------------------------------------------------- #


def _service(group: dict[str, Any], *, order_rows: list[dict[str, Any]]) -> MagicMock:
    service = MagicMock()
    service.client = _client_with(group, order_rows=order_rows)
    return service


class TestOrderedPendingSessionGuards:
    def test_ensure_session_active_flags_ordered_pending_session_and_never_expires_it(
        self,
    ) -> None:
        group = {**_pending_group("k"), "created_at": "2020-01-01T00:00:00+00:00"}
        service = _service(group, order_rows=[{"id": "o1"}])

        with patch("app.routers.checkout.expire_checkout_group_if_unpaid") as expire:
            active, _ = _ensure_session_active(service, group["id"], CUSTOMER)

        assert active[ORDERS_PLACED_KEY] is True
        assert session_is_ordered(active)
        expire.assert_not_called()

    def test_require_pending_refuses_coupon_changes_after_prepaid_order(self) -> None:
        group = {**_pending_group("k"), ORDERS_PLACED_KEY: True}
        with pytest.raises(AppError) as excinfo:
            _require_pending(group, group["id"])
        assert excinfo.value.code == "orders.session_already_completed"

    def test_require_pending_allows_an_unordered_pending_session(self) -> None:
        _require_pending(_pending_group("k"), "s")


# --------------------------------------------------------------------------- #
# the payment claim after order creation
# --------------------------------------------------------------------------- #


def _strategy() -> MagicMock:
    strategy = MagicMock()
    strategy.initiate_collection = AsyncMock(
        return_value=InitiateCollectionResult(
            provider_reference="240730099",
            status=CollectionStatus.PENDING,
            amount_major="100.00",
        )
    )
    return strategy


def _request() -> InitiatePaymentRequest:
    return InitiatePaymentRequest(
        checkout_group_id=CHECKOUT_GROUP_ID,
        amount_ngwee=10_000,
        rail="mtn",
        phone="+260961111111",
    )


class TestPaymentClaimAfterPrepaidOrder:
    @pytest.mark.asyncio
    async def test_retry_claims_when_checkout_is_still_pending(
        self,
        fake_service: FakeServiceClient,  # noqa: F811
    ) -> None:
        # State order creation now leaves behind for a prepaid checkout.
        assert fake_service.client.tables["checkout_groups"].rows[0]["status"] == "pending"

        result = await initiate_checkout_payment(
            fake_service, _request(), strategy=_strategy(), actor_id=ACTOR_ID
        )

        assert result.status.value == "ussd_pushed"
        assert len(fake_service.client.tables["payments"].rows) == 1

    @pytest.mark.asyncio
    async def test_claim_is_refused_once_the_checkout_has_completed(
        self,
        fake_service: FakeServiceClient,  # noqa: F811
    ) -> None:
        """Failure path: the pre-fix state (completed at order creation) is not payable,
        and neither is a checkout already completed by a successful payment, so a
        second payment cannot be claimed against a paid checkout."""
        fake_service.client.tables["checkout_groups"].rows[0]["status"] = "completed"
        strategy = _strategy()

        with pytest.raises(AppError) as excinfo:
            await initiate_checkout_payment(
                fake_service, _request(), strategy=strategy, actor_id=ACTOR_ID
            )

        assert excinfo.value.code == "payment.not_payable"
        assert excinfo.value.http_status == 409
        assert fake_service.client.tables["payments"].rows == []
        strategy.initiate_collection.assert_not_called()
