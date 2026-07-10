from __future__ import annotations

import concurrent.futures
import uuid
from collections.abc import Generator

import pytest
from app.services.orders.state import (
    SYSTEM_ACTOR_ID,
    TRANSITION_TABLE,
    ActorRole,
    OrderEvent,
    OrderStatus,
    OrderTransitionError,
    RefundPathRequiredError,
    all_matrix_cases,
    count_audit_events,
    fetch_latest_audit_event,
    resolve_transition,
    transition_order,
)
from tests.rls.conftest import (
    PgConn,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)

CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
VENDOR_ID = "33333333-3333-3333-3333-333333333333"
ADMIN_ID = "66666666-6666-6666-6666-666666666666"
SHOP_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


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


def _insert_checkout_group(conn: PgConn, group_id: str, *, key_suffix: str = "") -> None:
    conn.run(
        f"""
        INSERT INTO public.checkout_groups (
          id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee, total_ngwee
        ) VALUES (
          '{group_id}', '{CUSTOMER_ID}', 'idem-{group_id}{key_suffix}', 10000, 0, 10000
        )
        ON CONFLICT (id) DO NOTHING;
        """
    )


def _insert_order(
    conn: PgConn,
    *,
    order_id: str,
    checkout_group_id: str,
    status: str = "placed",
    fulfilment: str = "delivery",
    cod: bool = False,
) -> None:
    _insert_checkout_group(conn, checkout_group_id)
    conn.run(
        f"""
        INSERT INTO public.orders (
          id, checkout_group_id, vendor_id, customer_id, status, fulfilment, cod
        ) VALUES (
          '{order_id}', '{checkout_group_id}', '{SHOP_A}', '{CUSTOMER_ID}',
          '{status}', '{fulfilment}', {'true' if cod else 'false'}
        )
        ON CONFLICT (id) DO UPDATE
          SET status = EXCLUDED.status,
              fulfilment = EXCLUDED.fulfilment,
              cod = EXCLUDED.cod,
              checkout_group_id = EXCLUDED.checkout_group_id;
        """
    )


def _insert_payment(conn: PgConn, *, payment_id: str, checkout_group_id: str, status: str) -> None:
    conn.run(
        f"""
        INSERT INTO public.payments (
          id, checkout_group_id, provider, rail, lenco_reference, amount_ngwee, status
        ) VALUES (
          '{payment_id}', '{checkout_group_id}', 'lenco', 'mtn',
          'pay-{payment_id}', 10000, '{status}'
        )
        ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status;
        """
    )


def _order_status(conn: PgConn, order_id: str) -> str:
    result = conn.run(f"SELECT status FROM public.orders WHERE id = '{order_id}';")
    assert result.ok and result.rows
    return result.rows[0]


LEGAL_TRANSITION_CASES = [
    (OrderStatus.PLACED, OrderEvent.CONFIRM, ActorRole.VENDOR, "delivery", OrderStatus.CONFIRMED),
    (OrderStatus.PLACED, OrderEvent.CANCEL, ActorRole.CUSTOMER, "delivery", OrderStatus.CANCELLED),
    (
        OrderStatus.CONFIRMED,
        OrderEvent.START_PROCESSING,
        ActorRole.VENDOR,
        "delivery",
        OrderStatus.PROCESSING,
    ),
    (OrderStatus.PROCESSING, OrderEvent.SHIP, ActorRole.VENDOR, "delivery", OrderStatus.SHIPPED),
    (
        OrderStatus.PROCESSING,
        OrderEvent.READY_FOR_PICKUP,
        ActorRole.VENDOR,
        "pickup",
        OrderStatus.READY,
    ),
    (
        OrderStatus.READY,
        OrderEvent.VERIFY_PICKUP,
        ActorRole.VENDOR,
        "pickup",
        OrderStatus.DELIVERED,
    ),
    (
        OrderStatus.SHIPPED,
        OrderEvent.MARK_DELIVERED,
        ActorRole.VENDOR,
        "delivery",
        OrderStatus.DELIVERED,
    ),
    (
        OrderStatus.DELIVERED,
        OrderEvent.CONFIRM_RECEIVED,
        ActorRole.CUSTOMER,
        "delivery",
        OrderStatus.COMPLETED,
    ),
    (
        OrderStatus.SHIPPED,
        OrderEvent.AUTO_RELEASE,
        ActorRole.SYSTEM,
        "delivery",
        OrderStatus.COMPLETED,
    ),
    (
        OrderStatus.DELIVERED,
        OrderEvent.AUTO_CONFIRM,
        ActorRole.SYSTEM,
        "delivery",
        OrderStatus.COMPLETED,
    ),
]

_MATRIX_CASES = all_matrix_cases()
_MATRIX_IDS = [
    f"{s.value}-{e.value}-{a.value}-{f}-{'ok' if ok else 'no'}" for s, e, a, f, ok in _MATRIX_CASES
]


class TestTransitionMatrix:
    @pytest.mark.parametrize(
        ("from_status", "event", "actor", "fulfilment", "expected"),
        _MATRIX_CASES,
        ids=_MATRIX_IDS,
    )
    def test_resolve_transition_matrix(
        self,
        from_status: OrderStatus,
        event: OrderEvent,
        actor: ActorRole,
        fulfilment: str,
        expected: bool,
    ) -> None:
        result = resolve_transition(
            from_status=from_status,
            event=event,
            actor_role=actor,
            fulfilment=fulfilment,  # type: ignore[arg-type]
        )
        assert result.permitted is expected

    def test_transition_table_covers_all_legal_edges(self) -> None:
        for spec in TRANSITION_TABLE:
            for actor in spec.actors:
                fulfilment = spec.fulfilment or "delivery"
                result = resolve_transition(
                    from_status=spec.from_status,
                    event=spec.event,
                    actor_role=actor,
                    fulfilment=fulfilment,
                )
                assert result.permitted
                assert result.to_status == spec.to_status


@pytest.mark.usefixtures("db", "db_url_env")
class TestLegalTransitions:
    @pytest.mark.parametrize(
        ("from_status", "event", "actor", "fulfilment", "to_status"),
        LEGAL_TRANSITION_CASES,
    )
    def test_legal_transition_permitted_with_audit(
        self,
        db: PgConn,
        from_status: OrderStatus,
        event: OrderEvent,
        actor: ActorRole,
        fulfilment: str,
        to_status: OrderStatus,
    ) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        _insert_order(
            db,
            order_id=order_id,
            checkout_group_id=group_id,
            status=from_status.value,
            fulfilment=fulfilment,
        )
        before_count = count_audit_events(order_id)

        actor_id = {
            ActorRole.VENDOR: VENDOR_ID,
            ActorRole.CUSTOMER: CUSTOMER_ID,
            ActorRole.ADMIN: ADMIN_ID,
            ActorRole.SYSTEM: SYSTEM_ACTOR_ID,
        }[actor]

        outcome = transition_order(
            order_id=order_id,
            event=event,
            actor_role=actor,
            actor_id=actor_id,
            note=f"test {event.value}",
        )

        assert outcome.to_status == to_status
        assert _order_status(db, order_id) == to_status.value
        assert count_audit_events(order_id) == before_count + 1

        audit = fetch_latest_audit_event(order_id)
        assert audit is not None
        assert audit["actor"] == actor_id
        assert audit["from_status"] == from_status.value
        assert audit["to_status"] == to_status.value
        assert audit["note"] == f"test {event.value}"


@pytest.mark.usefixtures("db", "db_url_env")
class TestIllegalTransitions:
    def test_wrong_actor_rejected(self, db: PgConn) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        _insert_order(db, order_id=order_id, checkout_group_id=group_id, status="placed")

        with pytest.raises(OrderTransitionError):
            transition_order(
                order_id=order_id,
                event=OrderEvent.CONFIRM,
                actor_role=ActorRole.CUSTOMER,
                actor_id=CUSTOMER_ID,
                note="customer cannot confirm",
            )

    def test_wrong_fulfilment_rejected(self, db: PgConn) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        _insert_order(
            db,
            order_id=order_id,
            checkout_group_id=group_id,
            status="processing",
            fulfilment="pickup",
        )

        with pytest.raises(OrderTransitionError):
            transition_order(
                order_id=order_id,
                event=OrderEvent.SHIP,
                actor_role=ActorRole.VENDOR,
                actor_id=VENDOR_ID,
                note="cannot ship pickup order",
            )


@pytest.mark.usefixtures("db", "db_url_env")
class TestCancellationPaymentRules:
    def test_unpaid_cancel_succeeds_without_refund_path(self, db: PgConn) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        _insert_order(db, order_id=order_id, checkout_group_id=group_id, status="placed")

        transition_order(
            order_id=order_id,
            event=OrderEvent.CANCEL,
            actor_role=ActorRole.CUSTOMER,
            actor_id=CUSTOMER_ID,
            note="changed mind",
        )
        assert _order_status(db, order_id) == "cancelled"

    def test_paid_cancel_requires_refund_path(self, db: PgConn) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        _insert_order(db, order_id=order_id, checkout_group_id=group_id, status="placed")
        payment_id = str(uuid.uuid4())
        _insert_payment(
            db, payment_id=payment_id, checkout_group_id=group_id, status="success"
        )

        with pytest.raises(RefundPathRequiredError):
            transition_order(
                order_id=order_id,
                event=OrderEvent.CANCEL,
                actor_role=ActorRole.CUSTOMER,
                actor_id=CUSTOMER_ID,
                note="cancel paid order",
            )

    def test_paid_cancel_with_refund_path_flag_succeeds(self, db: PgConn) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        _insert_order(db, order_id=order_id, checkout_group_id=group_id, status="placed")
        payment_id = str(uuid.uuid4())
        _insert_payment(
            db, payment_id=payment_id, checkout_group_id=group_id, status="success"
        )

        transition_order(
            order_id=order_id,
            event=OrderEvent.CANCEL,
            actor_role=ActorRole.CUSTOMER,
            actor_id=CUSTOMER_ID,
            note="cancel with refund queued",
            refund_path=True,
        )
        assert _order_status(db, order_id) == "cancelled"

    def test_cod_treated_as_unpaid_for_cancel(self, db: PgConn) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        _insert_order(
            db,
            order_id=order_id,
            checkout_group_id=group_id,
            status="placed",
            cod=True,
        )
        payment_id = str(uuid.uuid4())
        _insert_payment(
            db, payment_id=payment_id, checkout_group_id=group_id, status="success"
        )

        transition_order(
            order_id=order_id,
            event=OrderEvent.CANCEL,
            actor_role=ActorRole.CUSTOMER,
            actor_id=CUSTOMER_ID,
            note="cod cancel",
        )
        assert _order_status(db, order_id) == "cancelled"


@pytest.mark.usefixtures("db", "db_url_env")
class TestConcurrentTransitions:
    def test_row_lock_one_winner_one_loser(self, db: PgConn) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        _insert_order(db, order_id=order_id, checkout_group_id=group_id, status="placed")

        def confirm() -> object:
            try:
                return transition_order(
                    order_id=order_id,
                    event=OrderEvent.CONFIRM,
                    actor_role=ActorRole.VENDOR,
                    actor_id=VENDOR_ID,
                    note="confirm race",
                )
            except OrderTransitionError:
                return None

        def cancel() -> object:
            try:
                return transition_order(
                    order_id=order_id,
                    event=OrderEvent.CANCEL,
                    actor_role=ActorRole.CUSTOMER,
                    actor_id=CUSTOMER_ID,
                    note="cancel race",
                )
            except OrderTransitionError:
                return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(confirm), executor.submit(cancel)]
            results = [future.result() for future in futures]

        final_status = _order_status(db, order_id)
        assert final_status in {"confirmed", "cancelled"}
        assert count_audit_events(order_id) == 1
        successes = [result for result in results if result is not None]
        assert len(successes) == 1


@pytest.mark.usefixtures("db", "db_url_env")
class TestGuardTrigger:
    def test_non_service_role_cannot_flip_status(self, db: PgConn) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        _insert_order(db, order_id=order_id, checkout_group_id=group_id, status="placed")

        claims = (
            '{"sub": "33333333-3333-3333-3333-333333333333", '
            '"role": "authenticated", "user_role": "vendor"}'
        )
        result = db.run(
            f"""
            SET SESSION AUTHORIZATION vergeo_rls_tester;
            DO $$ BEGIN PERFORM set_config('request.jwt.claims', '{claims}', true); END $$;
            SET LOCAL ROLE authenticated;
            UPDATE public.orders SET status = 'confirmed' WHERE id = '{order_id}';
            """
        )
        db.run("RESET SESSION AUTHORIZATION;")
        # RLS denies vendor UPDATE (0 rows) before the guard trigger; status must stay put.
        assert _order_status(db, order_id) == "placed"
        if result.ok:
            assert "UPDATE 0" in result.rows or result.rows == ["UPDATE 0"]
        else:
            assert "order status is server-controlled" in (result.error or "")


@pytest.mark.usefixtures("db", "db_url_env")
class TestMigration0014:
    def test_guc_enriched_audit_replays_clean(self, db: PgConn) -> None:
        result = db.run(
            """
            SELECT prosrc LIKE '%app.order_actor%'
            FROM pg_proc
            WHERE proname = 'audit_orders_status_change';
            """
        )
        assert result.ok and result.rows
        assert result.rows[0] == "t"
