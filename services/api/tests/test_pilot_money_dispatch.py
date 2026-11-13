"""Pilot money / dispatch fixes (COD Lusaka pilot, Nov 2026) — real Postgres.

Uses a disposable, fully migrated database (``ORDER_TEST_DB_URL`` when CI hands
one over, else a throwaway DB on 127.0.0.1:5432), like the order-integrity tests.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from app.routers.internal_order_jobs import _list_auto_confirm_candidates
from app.services.ledger.engine import account_balance_ngwee
from app.services.payments.cod import (
    CodError,
    collection_idempotency_key,
    confirm_cod_collection,
)
from tests.rls.conftest import PgConn, apply_migrations, seed_matrix_fixtures

CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
VENDOR_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
ADMIN_ID = "66666666-6666-6666-6666-666666666666"
PLATFORM_CASH_ID = "c1000000-0000-0000-0000-000000000001"
ESCROW_ID = "c2000000-0000-0000-0000-000000000002"
DELIVERY_REVENUE_ID = "c7000000-0000-0000-0000-000000000007"
ITEMS_NGWEE = 30_000
FEE_NGWEE = 4_500
RATE_BPS = 1_000
_DB_NAME = "vergeo5_pilot_money_dispatch_test"


@pytest.fixture(scope="module")
def db() -> Generator[PgConn, None, None]:
    if isolated_url := os.environ.get("ORDER_TEST_DB_URL"):
        conn = PgConn(isolated_url)
        ready = conn.run("SELECT 1 FROM public.orders LIMIT 1")
        assert ready.ok, ready.error
        seed_matrix_fixtures(conn)
        conn.run(f"SELECT public.ensure_vendor_ledger_accounts('{VENDOR_A}'::uuid);")
        yield conn
        return
    admin = PgConn("postgresql://postgres:postgres@127.0.0.1:5432/postgres")
    if not admin.run("SELECT 1").ok:
        pytest.skip("Postgres not reachable on 127.0.0.1:5432")
    admin.run(f"DROP DATABASE IF EXISTS {_DB_NAME} WITH (FORCE);")
    admin.run(f"CREATE DATABASE {_DB_NAME};")
    conn = PgConn(f"postgresql://postgres:postgres@127.0.0.1:5432/{_DB_NAME}")
    conn.run("DROP SCHEMA IF EXISTS public CASCADE")
    conn.run("CREATE SCHEMA public")
    conn.run("DROP SCHEMA IF EXISTS auth CASCADE")
    apply_migrations(conn)
    seed_matrix_fixtures(conn)
    conn.run(f"SELECT public.ensure_vendor_ledger_accounts('{VENDOR_A}'::uuid);")
    yield conn


@pytest.fixture(autouse=True)
def db_url_env(db: PgConn) -> Generator[None, None, None]:
    previous = os.environ.get("SUPABASE_DB_URL")
    os.environ["SUPABASE_DB_URL"] = db.dsn
    yield
    if previous is None:
        os.environ.pop("SUPABASE_DB_URL", None)
    else:
        os.environ["SUPABASE_DB_URL"] = previous


def _scalar(conn: PgConn, sql: str) -> str:
    result = conn.run(sql)
    assert result.ok and result.rows, result.error
    return result.rows[0]


def _account_id(conn: PgConn, kind: str, vendor_id: str | None = None) -> str:
    vendor_sql = f"= '{vendor_id}'::uuid" if vendor_id else "IS NULL"
    return _scalar(
        conn,
        f"SELECT id::text FROM public.ledger_accounts WHERE kind = '{kind}' "
        f"AND vendor_id {vendor_sql};",
    )


def _snapshot() -> dict[str, Any]:
    return {
        "lines": [
            {
                "listing_id": str(uuid.uuid4()),
                "category_key": "electronics",
                "rate_bps": RATE_BPS,
                "qty": 1,
                "unit_price_ngwee": ITEMS_NGWEE,
                "line_total_ngwee": ITEMS_NGWEE,
                "wholesale": False,
            }
        ]
    }


def _insert_order(
    conn: PgConn,
    *,
    status: str,
    cod: bool,
    fulfilment: str = "delivery",
    fee_ngwee: int = FEE_NGWEE,
) -> str:
    order_id = str(uuid.uuid4())
    group_id = str(uuid.uuid4())
    snapshot_sql = json.dumps(_snapshot()).replace("'", "''")
    result = conn.run_script(
        f"""
        INSERT INTO public.checkout_groups (
          id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee, total_ngwee, status
        ) VALUES (
          '{group_id}', '{CUSTOMER_ID}', 'cg-{group_id}', {ITEMS_NGWEE}, {fee_ngwee},
          {ITEMS_NGWEE + fee_ngwee}, 'completed'
        );
        INSERT INTO public.orders (
          id, checkout_group_id, vendor_id, customer_id, status, fulfilment,
          delivery_fee_ngwee, cod, commission_snapshot
        ) VALUES (
          '{order_id}', '{group_id}', '{VENDOR_A}', '{CUSTOMER_ID}', '{status}',
          '{fulfilment}', {fee_ngwee}, {str(cod).lower()}, '{snapshot_sql}'::jsonb
        );
        INSERT INTO public.order_items (
          id, order_id, item_kind, qty, unit_price_ngwee, title_snapshot
        ) VALUES (
          '{uuid.uuid4()}', '{order_id}', 'product', 1, {ITEMS_NGWEE}, 'Pilot item'
        );
        """
    )
    assert result.ok, result.error
    return order_id


def _insert_event(conn: PgConn, order_id: str, to_status: str, at: datetime) -> None:
    result = conn.run(
        f"""
        INSERT INTO public.order_events (id, order_id, actor, from_status, to_status, created_at)
        VALUES ('{uuid.uuid4()}', '{order_id}', '{ADMIN_ID}', NULL, '{to_status}',
                '{at.astimezone(UTC).isoformat()}'::timestamptz);
        """
    )
    assert result.ok, result.error


def _order_postings_sum(conn: PgConn, order_id: str) -> int:
    return int(
        _scalar(
            conn,
            "SELECT coalesce(sum(p.amount_ngwee), 0)::text FROM public.ledger_postings p "
            "JOIN public.ledger_transactions t ON t.id = p.transaction_id "
            f"WHERE t.order_id = '{order_id}';",
        )
    )


# ---------------------------------------------------------------------------
# Finding 2 — delivered COD orders must not auto-complete before cash is booked
# ---------------------------------------------------------------------------


class TestCodAutoConfirm:
    def test_uncollected_cod_order_is_not_an_auto_confirm_candidate(self, db: PgConn) -> None:
        now = datetime.now(UTC)
        cod_order = _insert_order(db, status="delivered", cod=True)
        prepaid_order = _insert_order(db, status="delivered", cod=False)
        for order_id in (cod_order, prepaid_order):
            _insert_event(db, order_id, "delivered", now - timedelta(hours=72))

        candidates = _list_auto_confirm_candidates(limit=200, cursor=None, now=now)

        assert prepaid_order in candidates
        assert cod_order not in candidates

    def test_cod_order_with_booked_collection_stays_a_candidate(self, db: PgConn) -> None:
        now = datetime.now(UTC)
        order_id = _insert_order(db, status="delivered", cod=True)
        _insert_event(db, order_id, "delivered", now - timedelta(hours=72))
        db.run(
            "INSERT INTO public.ledger_transactions (kind, idempotency_key, order_id) "
            f"VALUES ('cod_collected', '{collection_idempotency_key(order_id)}', '{order_id}');"
        )

        candidates = _list_auto_confirm_candidates(limit=200, cursor=None, now=now)

        assert order_id in candidates

    def test_customer_confirmed_cod_order_can_still_book_its_cash(self, db: PgConn) -> None:
        # delivered → completed by the customer before ops confirmed the cash.
        order_id = _insert_order(db, status="completed", cod=True)

        result = confirm_cod_collection(order_id=order_id, actor_id=ADMIN_ID, note="Rider remitted")

        assert result.created is True
        assert result.collectable_ngwee == ITEMS_NGWEE + FEE_NGWEE
        assert _order_postings_sum(db, order_id) == 0
        assert _scalar(db, f"SELECT status FROM public.orders WHERE id = '{order_id}';") == (
            "completed"
        )

    def test_cancelled_cod_order_still_refuses_collection(self, db: PgConn) -> None:
        order_id = _insert_order(db, status="cancelled", cod=True)

        with pytest.raises(CodError) as excinfo:
            confirm_cod_collection(order_id=order_id, actor_id=ADMIN_ID, note="x")

        assert excinfo.value.code == "cod_invalid_status"


# ---------------------------------------------------------------------------
# Finding 1 — delivery fee is platform revenue on the COD path (real ledger)
# ---------------------------------------------------------------------------


class TestCodDeliveryFeeToPlatform:
    def test_vendor_payable_excludes_delivery_fee(self, db: PgConn) -> None:
        order_id = _insert_order(db, status="delivered", cod=True)
        payable_id = _account_id(db, "vendor_payable", VENDOR_A)
        payable_before = account_balance_ngwee(payable_id)
        delivery_before = account_balance_ngwee(DELIVERY_REVENUE_ID)
        escrow_before = account_balance_ngwee(ESCROW_ID)
        commission = ITEMS_NGWEE * RATE_BPS // 10_000

        result = confirm_cod_collection(order_id=order_id, actor_id=ADMIN_ID, note="Cash in")

        assert result.net_vendor_ngwee == ITEMS_NGWEE - commission
        assert account_balance_ngwee(payable_id) == payable_before - (ITEMS_NGWEE - commission)
        assert account_balance_ngwee(DELIVERY_REVENUE_ID) == delivery_before - FEE_NGWEE
        assert account_balance_ngwee(ESCROW_ID) == escrow_before
        assert _order_postings_sum(db, order_id) == 0

    def test_pickup_cod_order_posts_no_delivery_capture(self, db: PgConn) -> None:
        order_id = _insert_order(db, status="delivered", cod=True, fulfilment="pickup", fee_ngwee=0)
        delivery_before = account_balance_ngwee(DELIVERY_REVENUE_ID)

        confirm_cod_collection(order_id=order_id, actor_id=ADMIN_ID, note="Paid at counter")

        assert account_balance_ngwee(DELIVERY_REVENUE_ID) == delivery_before
        assert _scalar(
            db,
            "SELECT count(*)::text FROM public.ledger_transactions "
            f"WHERE idempotency_key = 'delivery-fee-{order_id}';",
        ) == "0"
        assert _order_postings_sum(db, order_id) == 0


# ---------------------------------------------------------------------------
# Finding 3 / C02 — who holds COD cash decides who may confirm it and the ledger
# ---------------------------------------------------------------------------


def _audit_after(conn: PgConn, order_id: str) -> dict[str, Any]:
    raw = _scalar(
        conn,
        "SELECT after::text FROM public.audit_log WHERE action = 'cod.collection_confirmed' "
        f"AND entity_id = '{order_id}'::uuid;",
    )
    loaded = json.loads(raw)
    assert isinstance(loaded, dict)
    return loaded


class TestCodCashHolder:
    def test_vendor_cannot_confirm_rider_collected_cash(self, db: PgConn) -> None:
        from app.services.orders.state import ActorRole

        order_id = _insert_order(db, status="delivered", cod=True)

        with pytest.raises(CodError) as excinfo:
            confirm_cod_collection(
                order_id=order_id,
                actor_id=VENDOR_A,
                note="I got the cash",
                actor_role=ActorRole.VENDOR,
            )

        assert excinfo.value.code == "cod_platform_collects"
        assert excinfo.value.http_status == 403
        assert _scalar(
            db,
            f"SELECT count(*)::text FROM public.ledger_transactions WHERE order_id = '{order_id}';",
        ) == "0"
        assert _scalar(db, f"SELECT status FROM public.orders WHERE id = '{order_id}';") == (
            "delivered"
        )

    def test_admin_confirms_rider_cash_and_is_recorded(self, db: PgConn) -> None:
        order_id = _insert_order(db, status="delivered", cod=True)
        cash_before = account_balance_ngwee(PLATFORM_CASH_ID)

        confirm_cod_collection(order_id=order_id, actor_id=ADMIN_ID, note="Remitted by rider")

        assert account_balance_ngwee(PLATFORM_CASH_ID) == cash_before + ITEMS_NGWEE + FEE_NGWEE
        after = _audit_after(db, order_id)
        assert after["collected_by"] == "platform_courier"
        assert after["actor_role"] == "admin"
        assert _scalar(
            db,
            "SELECT actor::text FROM public.audit_log WHERE action = 'cod.collection_confirmed' "
            f"AND entity_id = '{order_id}'::uuid;",
        ) == ADMIN_ID

    def test_pickup_cash_held_by_vendor_never_becomes_platform_cash(self, db: PgConn) -> None:
        from app.services.orders.state import ActorRole

        order_id = _insert_order(db, status="delivered", cod=True, fulfilment="pickup", fee_ngwee=0)
        payable_id = _account_id(db, "vendor_payable", VENDOR_A)
        cash_before = account_balance_ngwee(PLATFORM_CASH_ID)
        payable_before = account_balance_ngwee(payable_id)
        escrow_before = account_balance_ngwee(ESCROW_ID)
        commission = ITEMS_NGWEE * RATE_BPS // 10_000

        result = confirm_cod_collection(
            order_id=order_id,
            actor_id=VENDOR_A,
            note="Paid at the counter",
            actor_role=ActorRole.VENDOR,
        )
        replay = confirm_cod_collection(
            order_id=order_id,
            actor_id=VENDOR_A,
            note="Paid at the counter",
            actor_role=ActorRole.VENDOR,
        )

        assert result.created is True and replay.created is False
        # The vendor holds the cash: platform cash is untouched and the vendor's
        # payable shows the commission it owes (debit-positive), not a payout.
        assert account_balance_ngwee(PLATFORM_CASH_ID) == cash_before
        assert account_balance_ngwee(payable_id) == payable_before + commission
        assert account_balance_ngwee(ESCROW_ID) == escrow_before
        assert _order_postings_sum(db, order_id) == 0
        after = _audit_after(db, order_id)
        assert after["collected_by"] == "vendor"
        assert after["actor_role"] == "vendor"
        assert _scalar(db, f"SELECT status FROM public.orders WHERE id = '{order_id}';") == (
            "completed"
        )


class TestEscrowSummaryCountsDeliveryCapture:
    """A released order with a captured fee has no escrow left (refunds not blocked)."""

    def test_released_prepaid_order_with_fee_has_zero_remaining_escrow(self, db: PgConn) -> None:
        from app.services.escrow.order_money_gate import claim_release_gate
        from app.services.escrow.release import evaluate_and_release
        from app.services.escrow.release_accounting import (
            remaining_escrow_ngwee,
            summarize_order_release_ledger,
        )
        from app.services.ledger.engine import post_transaction
        from app.services.ledger.templates import LedgerTemplate

        order_id = _insert_order(db, status="completed", cod=False)
        result = db.run(
            f"""
            INSERT INTO public.order_events (id, order_id, actor, from_status, to_status)
            VALUES ('{uuid.uuid4()}', '{order_id}', '{CUSTOMER_ID}', 'delivered', 'completed');
            """
        )
        assert result.ok, result.error
        post_transaction(
            idempotency_key=f"escrow-hold-{order_id}",
            template=LedgerTemplate.ESCROW_HOLD,
            order_id=order_id,
            order_amount_ngwee=ITEMS_NGWEE + FEE_NGWEE,
        )

        released = evaluate_and_release(None, order_id)  # type: ignore[arg-type]

        assert released.outcome == "released"
        summary = summarize_order_release_ledger(order_id)
        assert summary.delivery_fee_captured_ngwee == FEE_NGWEE
        assert summary.balanced is True
        assert remaining_escrow_ngwee(order_id) == 0
        claim_release_gate(order_id)  # idempotent re-claim still ok


# ---------------------------------------------------------------------------
# Finding 4 — prepaid shipped-timer release must respect the courier dispatch
# ---------------------------------------------------------------------------


def _insert_dispatch(conn: PgConn, order_id: str, status: str) -> None:
    partner_id = str(uuid.uuid4())
    result = conn.run_script(
        f"""
        INSERT INTO public.courier_partners (id, name, contact_email)
        VALUES ('{partner_id}', 'Pilot riders {partner_id[:8]}', 'riders@example.com');
        INSERT INTO public.dispatch_requests (order_id, courier_partner_id, status)
        VALUES ('{order_id}', '{partner_id}', '{status}');
        """
    )
    assert result.ok, result.error


class TestAutoReleaseRespectsDispatch:
    def _shipped_prepaid_order(self, db: PgConn, *, days_ago: int = 8) -> str:
        from app.services.ledger.engine import post_transaction
        from app.services.ledger.templates import LedgerTemplate

        order_id = _insert_order(db, status="shipped", cod=False)
        _insert_event(db, order_id, "shipped", datetime.now(UTC) - timedelta(days=days_ago))
        post_transaction(
            idempotency_key=f"escrow-hold-{order_id}",
            template=LedgerTemplate.ESCROW_HOLD,
            order_id=order_id,
            order_amount_ngwee=ITEMS_NGWEE + FEE_NGWEE,
        )
        return order_id

    @pytest.mark.parametrize("dispatch_status", ["failed", "cancelled"])
    def test_failed_or_cancelled_dispatch_blocks_shipped_fallback(
        self, db: PgConn, dispatch_status: str
    ) -> None:
        from app.routers.internal_order_jobs import _list_auto_release_candidates
        from app.services.escrow.release import evaluate_and_release

        order_id = self._shipped_prepaid_order(db)
        _insert_dispatch(db, order_id, dispatch_status)

        candidates = _list_auto_release_candidates(limit=200, cursor=None, now=datetime.now(UTC))
        result = evaluate_and_release(None, order_id)  # type: ignore[arg-type]

        assert order_id not in candidates
        assert result.outcome == "held"
        assert result.reason == f"dispatch_{dispatch_status}"
        assert _scalar(
            db,
            "SELECT count(*)::text FROM public.ledger_transactions "
            f"WHERE idempotency_key = 'release-{order_id}';",
        ) == "0"

    def test_in_flight_dispatch_still_releases_on_the_shipped_timer(self, db: PgConn) -> None:
        from app.routers.internal_order_jobs import _list_auto_release_candidates
        from app.services.escrow.release import evaluate_and_release

        order_id = self._shipped_prepaid_order(db)
        _insert_dispatch(db, order_id, "picked_up")

        candidates = _list_auto_release_candidates(limit=200, cursor=None, now=datetime.now(UTC))
        result = evaluate_and_release(None, order_id)  # type: ignore[arg-type]

        assert order_id in candidates
        assert result.outcome == "released"
        assert result.rule == "shipped_fallback"


# ---------------------------------------------------------------------------
# Finding 6 — one shipping path: courier dispatch vs vendor `ship`
# ---------------------------------------------------------------------------


class TestCourierDispatchOwnsShipping:
    def test_in_flight_dispatch_owns_shipping(self, db: PgConn) -> None:
        from app.routers.vendor_orders import courier_dispatch_owns_shipping

        order_id = _insert_order(db, status="processing", cod=True)
        assert courier_dispatch_owns_shipping(order_id) is False

        _insert_dispatch(db, order_id, "requested")

        assert courier_dispatch_owns_shipping(order_id) is True

    def test_flag_on_owns_shipping_for_every_delivery_order(self, db: PgConn) -> None:
        from app.routers.vendor_orders import courier_dispatch_owns_shipping

        order_id = _insert_order(db, status="processing", cod=True)
        db.run(
            "INSERT INTO public.feature_flags (flag, enabled) VALUES ('courier_dispatch', true) "
            "ON CONFLICT (flag) DO UPDATE SET enabled = true;"
        )
        try:
            assert courier_dispatch_owns_shipping(order_id) is True
            assert courier_dispatch_owns_shipping() is True
        finally:
            db.run(
                "UPDATE public.feature_flags SET enabled = false WHERE flag = 'courier_dispatch';"
            )


# ---------------------------------------------------------------------------
# Review fixes — refunds after the delivery fee became platform revenue
# ---------------------------------------------------------------------------


def _insert_refund(
    conn: PgConn, order_id: str, *, lane: int, status: str, breakdown: dict[str, Any]
) -> str:
    refund_id = str(uuid.uuid4())
    payload = json.dumps(breakdown).replace("'", "''")
    result = conn.run(
        "INSERT INTO public.refunds (id, order_id, source_key, lane, breakdown, amount_ngwee, "
        f"status) VALUES ('{refund_id}', '{order_id}', 'review-{refund_id}', {lane}, "
        f"'{payload}'::jsonb, 1000, '{status}');"
    )
    assert result.ok, result.error
    return refund_id


class TestRefundDeliveryFee:
    def test_post_release_lane1_refund_takes_fee_from_delivery_revenue(self, db: PgConn) -> None:
        from app.services.refunds.execute import _post_post_release_clawback
        from app.services.refunds.state import reverse_refund_ledger

        order_id = _insert_order(db, status="delivered", cod=True)
        confirm_cod_collection(order_id=order_id, actor_id=ADMIN_ID, note="Cash in")
        payable_id = _account_id(db, "vendor_payable", VENDOR_A)
        payable_before = account_balance_ngwee(payable_id)
        delivery_before = account_balance_ngwee(DELIVERY_REVENUE_ID)
        cash_before = account_balance_ngwee(PLATFORM_CASH_ID)
        refund_id = _insert_refund(
            db, order_id, lane=1, status="processing", breakdown={"phase": "post_release"}
        )

        _post_post_release_clawback(
            refund_id=refund_id,
            ledger_key_base=f"review-{refund_id}",
            order_id=order_id,
            vendor_id=VENDOR_A,
            clawback_ngwee=ITEMS_NGWEE + FEE_NGWEE,
            refunded_delivery_fee_ngwee=FEE_NGWEE,
        )

        # The vendor never received the fee, so only the items are clawed back.
        assert account_balance_ngwee(payable_id) == payable_before + ITEMS_NGWEE
        assert account_balance_ngwee(DELIVERY_REVENUE_ID) == delivery_before + FEE_NGWEE
        assert account_balance_ngwee(PLATFORM_CASH_ID) == cash_before - ITEMS_NGWEE - FEE_NGWEE
        assert _order_postings_sum(db, order_id) == 0

        # A definitive payout failure reverses every leg, fee included.
        reverse_refund_ledger(refund_id=refund_id, order_id=order_id)
        assert account_balance_ngwee(payable_id) == payable_before
        assert account_balance_ngwee(DELIVERY_REVENUE_ID) == delivery_before
        assert account_balance_ngwee(PLATFORM_CASH_ID) == cash_before

    def test_refunded_fee_counts_only_live_pre_release_lane1_refunds(self, db: PgConn) -> None:
        from app.services.escrow.release_accounting import delivery_fee_refunded_ngwee

        order_id = _insert_order(db, status="delivered", cod=False)
        fee_part = {"phase": "pre_release", "delivery_fee_ngwee": FEE_NGWEE}
        _insert_refund(db, order_id, lane=1, status="completed", breakdown=fee_part)
        _insert_refund(db, order_id, lane=1, status="failed", breakdown=fee_part)
        _insert_refund(
            db,
            order_id,
            lane=1,
            status="completed",
            breakdown={"phase": "post_release", "delivery_fee_ngwee": FEE_NGWEE},
        )
        _insert_refund(
            db,
            order_id,
            lane=2,
            status="completed",
            breakdown={"phase": "pre_release", "outbound_delivery_ngwee": FEE_NGWEE},
        )

        assert delivery_fee_refunded_ngwee(order_id) == FEE_NGWEE
