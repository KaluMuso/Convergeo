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
from unittest.mock import MagicMock

import psycopg
import pytest
from app.core.env_guards import StagingIsolationError
from app.services.orders.state import ActorRole, OrderEvent, OrderStatus, resolve_transition
from app.services.stock.claim import ClaimResult
from app.staging import transactional as txn
from app.staging.seed_sql import build_cleanup_sql
from app.staging.synthetic_contract import (
    SEED_PREFIX,
    VENDOR_LOCATIONS,
    persona_by_key,
    product_fixture,
)
from psycopg import sql
from tests.rls.conftest import PgConn
from tests.test_order_creation import _PgClient, _Query
from tests.test_seed_staging import _seed
from tests.test_seed_staging import migrated_db as migrated_db


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

    def eq(self, column: str, value: Any) -> _FakeQuery:
        self._recorder["filters"].append((self._table, column, value))
        return self

    def maybe_single(self) -> _FakeQuery:
        return self

    def execute(self) -> Any:
        return type("_Resp", (), {"data": self._existing})()


class _FakeClient:
    """Records table writes; never performs any."""

    def __init__(self, existing_group: Any = None, existing_reservation: Any = None) -> None:
        self.calls: dict[str, list[Any]] = {"upsert": [], "insert": [], "filters": []}
        self.tables: list[str] = []
        self._existing_group = existing_group
        self._existing_reservation = existing_reservation

    def table(self, name: str) -> _FakeQuery:
        self.tables.append(name)
        existing = self._existing_group if name == "checkout_groups" else None
        if name == "stock_reservations":
            existing = self._existing_reservation
        return _FakeQuery(name, self.calls, existing)


@pytest.fixture
def captured_claim(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def claim(**kwargs: Any) -> ClaimResult:
        calls.append(kwargs)
        return ClaimResult(
            claimed=True,
            listing_id=kwargs["listing_id"],
            checkout_group_id=kwargs["checkout_group_id"],
            qty=kwargs["qty"],
            location_id=kwargs["location_id"],
        )

    monkeypatch.setattr("app.services.stock.claim.claim_reservation", claim)
    monkeypatch.setattr("app.services.stock.claim.load_reservation_ttl_minutes", lambda: 15)
    return calls


@pytest.fixture
def captured_create(
    monkeypatch: pytest.MonkeyPatch, captured_claim: list[dict[str, Any]]
) -> dict[str, Any]:
    """Replace create_orders_atomic with a recorder returning a plausible result."""
    captured: dict[str, Any] = {}

    def _fake_create_orders_atomic(**kwargs: Any) -> Any:
        captured.update(kwargs)
        captured["claim_count_at_create"] = len(captured_claim)
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
    captured_claim: list[dict[str, Any]],
) -> None:
    client = _FakeClient(existing_group={"id": txn.COD_CHECKOUT_GROUP_ID, "status": "completed"})
    txn.apply_cod_placed(client)
    # No second checkout session is inserted; the service replays by key.
    assert client.calls["insert"] == []
    assert captured_create["idempotency_key"] == txn.COD_IDEMPOTENCY_KEY
    assert captured_claim == []
    assert "stock_reservations" not in client.tables


@pytest.mark.parametrize("existing_group", [None, {"status": "pending"}])
def test_claim_precedes_order_creation_with_exact_canonical_binding(
    existing_group: Any,
    captured_create: dict[str, Any],
    captured_claim: list[dict[str, Any]],
) -> None:
    client = _FakeClient(existing_group=existing_group)
    txn.apply_cod_placed(client)
    fixture = txn.cod_placed_fixture()
    location = next(loc for loc in VENDOR_LOCATIONS if loc.vendor_key == "APPROVED_VENDOR_A")
    assert captured_create["claim_count_at_create"] == 1
    assert captured_claim == [
        {
            "listing_id": fixture.listing_id,
            "checkout_group_id": txn.COD_CHECKOUT_GROUP_ID,
            "qty": txn.COD_ORDER_QTY,
            "location_id": location.location_id,
            "ttl_minutes": 15,
        }
    ]
    assert fixture.listing_id == "f1000000-0000-4000-8000-000000000003"
    assert location.location_id == "12000000-0000-4000-8000-000000000004"
    assert ("stock_reservations", "listing_id", fixture.listing_id) in client.calls["filters"]
    assert ("stock_reservations", "checkout_group_id", txn.COD_CHECKOUT_GROUP_ID) in client.calls[
        "filters"
    ]


def test_existing_hold_is_not_claimed_twice(
    captured_create: dict[str, Any], captured_claim: list[dict[str, Any]]
) -> None:
    location = next(loc for loc in VENDOR_LOCATIONS if loc.vendor_key == "APPROVED_VENDOR_A")
    client = _FakeClient(
        existing_group={"status": "pending"},
        existing_reservation={"qty": txn.COD_ORDER_QTY, "location_id": location.location_id},
    )
    txn.apply_cod_placed(client)
    assert captured_claim == []
    assert captured_create["session_id"] == txn.COD_CHECKOUT_GROUP_ID
    assert client.calls["insert"] == []


def test_absent_maybe_single_response_still_claims_before_create(
    monkeypatch: pytest.MonkeyPatch,
    captured_create: dict[str, Any],
    captured_claim: list[dict[str, Any]],
) -> None:
    original_execute = _FakeQuery.execute

    def execute(query: _FakeQuery) -> Any:
        return None if query._table == "stock_reservations" else original_execute(query)

    monkeypatch.setattr(_FakeQuery, "execute", execute)
    txn.apply_cod_placed(_FakeClient())
    assert len(captured_claim) == captured_create["claim_count_at_create"] == 1


@pytest.mark.parametrize("skipped", [False, True])
def test_failed_or_skipped_claim_blocks_order_creation(
    monkeypatch: pytest.MonkeyPatch, captured_create: dict[str, Any], skipped: bool
) -> None:
    fixture = txn.cod_placed_fixture()
    monkeypatch.setattr(
        "app.services.stock.claim.claim_reservation",
        lambda **kwargs: ClaimResult(
            claimed=skipped,
            skipped=skipped,
            listing_id=fixture.listing_id,
            checkout_group_id=fixture.checkout_group_id,
            qty=fixture.qty,
        ),
    )
    with pytest.raises(StagingIsolationError, match="reservation"):
        txn.apply_cod_placed(_FakeClient())
    assert captured_create == {}


def test_claim_error_blocks_order_creation(
    monkeypatch: pytest.MonkeyPatch, captured_create: dict[str, Any]
) -> None:
    def fail(**kwargs: Any) -> ClaimResult:
        raise RuntimeError("reservation transport failed")

    monkeypatch.setattr("app.services.stock.claim.claim_reservation", fail)
    with pytest.raises(RuntimeError, match="reservation transport failed"):
        txn.apply_cod_placed(_FakeClient())
    assert captured_create == {}


@pytest.mark.parametrize(
    "reservation",
    [
        {"qty": 2, "location_id": "12000000-0000-4000-8000-000000000004"},
        {"qty": txn.COD_ORDER_QTY, "location_id": "12000000-0000-4000-8000-000000000005"},
    ],
)
def test_mismatched_hold_fails_without_reclaim_or_order(
    reservation: dict[str, Any],
    captured_create: dict[str, Any],
    captured_claim: list[dict[str, Any]],
) -> None:
    with pytest.raises(StagingIsolationError, match="reservation"):
        txn.apply_cod_placed(_FakeClient(existing_reservation=reservation))
    assert captured_claim == []
    assert captured_create == {}


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


class _FixtureQuery(_Query):
    """Extend the existing SQL-backed read adapter with buyer-input writes only."""

    def insert(self, payload: dict[str, Any]) -> _FixtureQuery:
        assert self.table == "checkout_groups"
        self.payload, self.operation = payload, "insert"
        return self

    def upsert(self, payload: dict[str, Any]) -> _FixtureQuery:
        assert self.table == "addresses"
        self.payload, self.operation = payload, "upsert"
        return self

    def execute(self) -> MagicMock:
        if self.operation not in {"insert", "upsert"}:
            return super().execute()
        assert self.payload is not None
        columns = list(self.payload)
        statement = sql.SQL("INSERT INTO public.{} ({}) VALUES ({})").format(
            sql.Identifier(self.table),
            sql.SQL(", ").join(map(sql.Identifier, columns)),
            sql.SQL(", ").join(sql.Placeholder() for _ in columns),
        )
        if self.operation == "upsert":
            statement += sql.SQL(" ON CONFLICT (id) DO UPDATE SET ") + sql.SQL(", ").join(
                sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(key), sql.Identifier(key))
                for key in columns
                if key != "id"
            )
        with psycopg.connect(self.conn.dsn) as connection:
            connection.execute(statement, list(self.payload.values()))
        return MagicMock(data=[])


class _FixtureClient(_PgClient):
    def table(self, name: str) -> _FixtureQuery:
        return _FixtureQuery(conn=self._conn, table=name)


@pytest.mark.parametrize("resume_after_claim", [False, True])
def test_fresh_seed_real_hold_is_consumed_by_cod_order_and_replay_is_stock_neutral(
    migrated_db: PgConn, monkeypatch: pytest.MonkeyPatch, resume_after_claim: bool
) -> None:
    from app.services.orders import create as order_service
    from app.services.stock import claim as stock_service

    cleaned = migrated_db.run_script(build_cleanup_sql())
    assert cleaned.ok, cleaned.error
    seeded = _seed(migrated_db)
    assert seeded.ok, seeded.error
    monkeypatch.setenv("SUPABASE_DB_URL", migrated_db.dsn)
    fixture = txn.cod_placed_fixture()
    location = next(loc for loc in VENDOR_LOCATIONS if loc.vendor_key == "APPROVED_VENDOR_A")
    client = _FixtureClient(migrated_db)
    original_claim = stock_service.claim_reservation
    original_create = order_service.create_orders_atomic
    claims: list[ClaimResult] = []

    def stock_qty() -> list[str]:
        result = migrated_db.run(
            "SELECT stock_qty FROM public.listing_location_stock "
            f"WHERE listing_id = '{fixture.listing_id}' AND location_id = '{location.location_id}'"
        )
        assert result.ok, result.error
        return result.rows

    def claim(**kwargs: Any) -> ClaimResult:
        result = original_claim(**kwargs)
        claims.append(result)
        return result

    def create_with_hold_proof(**kwargs: Any) -> Any:
        hold = migrated_db.run(
            "SELECT qty, location_id, expires_at > now() FROM public.stock_reservations "
            f"WHERE listing_id = '{fixture.listing_id}' "
            f"AND checkout_group_id = '{fixture.checkout_group_id}'"
        )
        assert hold.ok, hold.error
        assert hold.rows == [f"{fixture.qty}|{location.location_id}|t"]
        assert stock_qty() == ["39"]
        if resume_after_claim:
            raise InterruptedError("order creation interrupted after real hold")
        return original_create(**kwargs)

    assert stock_qty() == ["40"]
    monkeypatch.setattr(stock_service, "claim_reservation", claim)
    monkeypatch.setattr(order_service, "create_orders_atomic", create_with_hold_proof)
    if resume_after_claim:
        with pytest.raises(InterruptedError, match="after real hold"):
            txn.apply_cod_placed(client)
        resume_after_claim = False
    outcome = txn.apply_cod_placed(client)
    assert len(claims) == 1
    assert claims[0].claimed and not claims[0].skipped
    assert claims[0].location_id == location.location_id
    assert outcome["replayed"] is False
    assert outcome["total_ngwee"] == 8750
    placed = migrated_db.run(
        "SELECT status, cod, fulfilment FROM public.orders "
        f"WHERE checkout_group_id = '{fixture.checkout_group_id}'"
    )
    assert placed.ok and placed.rows == ["placed|t|delivery"]
    holds = migrated_db.run(
        "SELECT count(*) FROM public.stock_reservations "
        f"WHERE checkout_group_id = '{fixture.checkout_group_id}'"
    )
    assert holds.ok and holds.rows == ["0"]
    monkeypatch.setattr(order_service, "create_orders_atomic", original_create)
    replay = txn.apply_cod_placed(client)
    assert replay["replayed"] is True
    assert replay["orders"] == outcome["orders"]
    assert len(claims) == 1
    assert stock_qty() == ["39"]
