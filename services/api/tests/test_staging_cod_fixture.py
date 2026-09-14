"""Coverage for the COD transactional staging fixture (Phase 3A).

The canonical seed creates catalogue identity only — deliberately no orders. The
vendor-sell E2E journey needs exactly one real, shippable order, and a focused
`vendor-auth` run never executes shop-cod.spec.ts, so it cannot inherit one.

`apply_cod_placed` supplies it through the REAL order-creation service. These
tests pin the two properties that make that safe and useful:

  1. the order is created by `create_orders_atomic`, never by a hand-written
     INSERT — the state machine and its audit trail stay authoritative;
  2. the fixture is deterministic and shippable — a single-listing product owned
     by the persona the vendor portal specs authenticate as, on a DELIVERY
     order, because TRANSITION_TABLE allows SHIP only from processing+delivery.
"""

from __future__ import annotations

from typing import Any

import pytest
from app.core.env_guards import StagingIsolationError
from app.services.orders.state import ActorRole, OrderEvent, OrderStatus, resolve_transition
from app.staging import transactional as txn
from app.staging.seed_sql import build_cleanup_sql
from app.staging.synthetic_contract import SEED_PREFIX, persona_by_key, product_fixture


class _FakeQuery:
    def __init__(self, table: str, recorder: dict[str, list[Any]], existing: Any) -> None:
        self._table = table
        self._recorder = recorder
        self._existing = existing

    def upsert(self, payload: dict[str, Any]) -> _FakeQuery:
        self._recorder["upsert"].append((self._table, payload))
        return self

    def insert(self, payload: dict[str, Any]) -> _FakeQuery:
        self._recorder["insert"].append((self._table, payload))
        return self

    def select(self, *_args: Any, **_kwargs: Any) -> _FakeQuery:
        return self

    def eq(self, *_args: Any, **_kwargs: Any) -> _FakeQuery:
        return self

    def maybe_single(self) -> _FakeQuery:
        return self

    def execute(self) -> Any:
        return type("_Resp", (), {"data": self._existing})()


class _FakeClient:
    """Records table writes; never performs any."""

    def __init__(self, existing_group: Any = None) -> None:
        self.calls: dict[str, list[Any]] = {"upsert": [], "insert": []}
        self.tables: list[str] = []
        self._existing_group = existing_group

    def table(self, name: str) -> _FakeQuery:
        self.tables.append(name)
        existing = self._existing_group if name == "checkout_groups" else None
        return _FakeQuery(name, self.calls, existing)


@pytest.fixture
def captured_create(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace create_orders_atomic with a recorder returning a plausible result."""
    captured: dict[str, Any] = {}

    def _fake_create_orders_atomic(**kwargs: Any) -> Any:
        captured.update(kwargs)
        order = type(
            "_Order",
            (),
            {
                "order_id": "11111111-1111-4111-8111-111111111111",
                "vendor_id": kwargs["vendor_groups"][0].vendor_id,
                "cod": True,
            },
        )()
        return type(
            "_Result",
            (),
            {
                "checkout_group_id": kwargs["session_id"],
                "idempotency_key": kwargs["idempotency_key"],
                "subtotal_ngwee": kwargs["vendor_groups"][0].subtotal_ngwee,
                "total_ngwee": kwargs["vendor_groups"][0].subtotal_ngwee,
                "replayed": False,
                "orders": (order,),
            },
        )()

    monkeypatch.setattr(
        "app.services.orders.create.create_orders_atomic", _fake_create_orders_atomic
    )
    return captured


def test_cod_fixture_is_deterministic_and_vendor_scoped() -> None:
    fixture = txn.cod_placed_fixture()
    product = product_fixture("PRODUCT_B")
    vendor = persona_by_key("APPROVED_VENDOR_A")

    # Single listing => the receiving vendor cannot depend on buy-box selection.
    assert len(product.listings) == 1
    assert fixture.listing_id == product.listings[0].listing_id
    assert fixture.vendor_id == vendor.vendor_id
    assert fixture.customer_user_id == persona_by_key("CUSTOMER_A").user_id
    assert fixture.subtotal_ngwee == product.listings[0].price_ngwee * fixture.qty


def test_cod_fixture_lives_in_the_namespace_cleanup_already_owns() -> None:
    fixture = txn.cod_placed_fixture()
    assert fixture.idempotency_key.startswith(txn.CHECKOUT_IDEMPOTENCY_PREFIX)
    assert fixture.idempotency_key.startswith(f"{SEED_PREFIX}-txn-")

    cleanup = build_cleanup_sql()
    namespace = f"LIKE '{SEED_PREFIX}-txn-%'"
    assert namespace in cleanup

    # create_orders_atomic emits order.placed and later transitions may enqueue
    # more notifications. Cleanup must remove only outbox rows linked through
    # this run-scoped checkout/order namespace, before deleting the orders.
    outbox_delete = cleanup.index("DELETE FROM public.notification_outbox")
    payments_delete = cleanup.index("DELETE FROM public.payments")
    order_delete = cleanup.index("DELETE FROM public.orders")
    assert outbox_delete < payments_delete < order_delete
    assert "payload->>'checkout_group_id'" in cleanup
    assert "payload->>'order_id'" in cleanup
    assert cleanup[outbox_delete:payments_delete].count(namespace) == 2


def test_cod_amount_is_within_the_zambia_cod_cap() -> None:
    # COD is capped at K500 (50_000 ngwee) — a fixture above the cap could never
    # be placed by a real buyer.
    assert txn.cod_placed_fixture().subtotal_ngwee <= 50_000


def test_apply_drives_the_real_order_service_not_a_hand_written_insert(
    captured_create: dict[str, Any],
) -> None:
    client = _FakeClient()
    outcome = txn.apply_cod_placed(client)

    # The ONLY direct writes are the buyer inputs a real checkout would have
    # produced: a delivery address and a pending checkout session.
    assert [table for table, _ in client.calls["upsert"]] == ["addresses"]
    assert [table for table, _ in client.calls["insert"]] == ["checkout_groups"]
    # Never an order, order item, or status written by hand.
    assert "orders" not in client.tables
    assert "order_items" not in client.tables

    assert captured_create["payment_method"] == "cod"
    assert captured_create["address_id"] == txn.COD_ADDRESS_ID
    assert outcome["state"] == "cod_placed"
    assert outcome["orders"][0]["cod"] is True


def test_apply_creates_a_delivery_order_so_ship_is_reachable(
    captured_create: dict[str, Any],
) -> None:
    txn.apply_cod_placed(_FakeClient())
    group = captured_create["vendor_groups"][0]
    assert group.fulfilment == "delivery"

    # The reason delivery is mandatory, asserted against the state machine
    # itself rather than restated as a comment.
    assert resolve_transition(
        from_status=OrderStatus.PROCESSING,
        event=OrderEvent.SHIP,
        actor_role=ActorRole.VENDOR,
        fulfilment="delivery",
    ).permitted
    assert not resolve_transition(
        from_status=OrderStatus.PROCESSING,
        event=OrderEvent.SHIP,
        actor_role=ActorRole.VENDOR,
        fulfilment="pickup",
    ).permitted


def test_apply_totals_match_the_session_the_service_validates(
    captured_create: dict[str, Any],
) -> None:
    fixture = txn.cod_placed_fixture()
    client = _FakeClient()
    txn.apply_cod_placed(client)

    # The checkout session the service validates against must agree with the
    # cart lines, or create_orders_atomic raises orders.totals_mismatch.
    _, session = client.calls["insert"][0]
    assert session["subtotal_ngwee"] == fixture.subtotal_ngwee
    assert session["delivery_fee_ngwee"] == 0
    assert session["total_ngwee"] == fixture.subtotal_ngwee
    assert session["status"] == "pending"

    line = captured_create["cart_lines"][0]
    group = captured_create["vendor_groups"][0]
    assert line.qty * line.unit_price_ngwee == fixture.subtotal_ngwee
    assert group.subtotal_ngwee == fixture.subtotal_ngwee
    assert group.delivery_fee_ngwee == 0


def test_apply_is_idempotent_on_an_existing_checkout_group(
    captured_create: dict[str, Any],
) -> None:
    client = _FakeClient(existing_group={"id": txn.COD_CHECKOUT_GROUP_ID, "status": "completed"})
    txn.apply_cod_placed(client)
    # No second checkout session is inserted; the service replays by key.
    assert client.calls["insert"] == []
    assert captured_create["idempotency_key"] == txn.COD_IDEMPOTENCY_KEY


def test_fixture_refuses_a_multi_listing_product(monkeypatch: pytest.MonkeyPatch) -> None:
    multi = product_fixture("PRODUCT_A")  # two listings, two vendors
    monkeypatch.setattr(txn, "product_fixture", lambda _key: multi)
    with pytest.raises(StagingIsolationError, match="exactly one listing"):
        txn.cod_placed_fixture()


def test_fixture_refuses_a_listing_owned_by_another_vendor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wrong = product_fixture("PRODUCT_D")  # single listing, APPROVED_VENDOR_B
    monkeypatch.setattr(txn, "product_fixture", lambda _key: wrong)
    with pytest.raises(StagingIsolationError, match="APPROVED_VENDOR_A"):
        txn.cod_placed_fixture()


def test_only_cod_is_service_drivable_among_order_states() -> None:
    # Guards the premise of the whole fixture: every other transactional state
    # still needs a payment provider, so COD is the one deterministic path.
    assert txn.is_service_drivable(txn.TransactionalState.COD_PLACED)
    assert not txn.is_service_drivable(txn.TransactionalState.PROCESSING)
    assert not txn.is_service_drivable(txn.TransactionalState.DELIVERED)
