"""Vendor / platform funded delivery is booked to delivery_revenue at release (real Postgres).

Logistics phase 1: the customer pays the delivery fee by default; a vendor "free
delivery" charges the fee to the vendor payable, the automatic free-delivery rule
reclassifies it out of commission. Either way the ledger nets to zero and every
delivered order books its delivery cost as delivery_revenue.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.services.escrow.release import evaluate_and_release
from app.services.escrow.release_accounting import (
    delivery_funding_idempotency_key,
    post_order_delivery_funding,
)
from app.services.ledger.engine import account_balance_ngwee
from app.services.ledger.templates import (
    delivery_fee_platform_subsidy,
    delivery_fee_vendor_charge,
)
from app.services.orders.state import SYSTEM_ACTOR_ID
from tests import test_release as _release_tests
from tests.rls.conftest import PgConn
from tests.test_release import (
    _SERVICE,
    COMMISSION_ID,
    COMMISSION_NGEWEE,
    CUSTOMER_ID,
    NET_NGEWEE,
    VENDOR_A,
    VENDOR_PAYABLE_ID,
    _insert_order,
    _insert_order_event,
    seed_escrow_for_order,
)

# Reuse the release suite's module-scoped real-Postgres fixtures.
db = _release_tests.db
db_url_env = _release_tests.db_url_env

DELIVERY_REVENUE_ID = "c7000000-0000-0000-0000-000000000007"
FEE = 4_500


def _set_funding(conn: PgConn, order_id: str, funding: str, funded: int) -> None:
    result = conn.run(
        f"UPDATE public.orders SET delivery_funding = '{funding}', "
        f"delivery_funded_ngwee = {funded} WHERE id = '{order_id}';"
    )
    assert result.ok, result.error


def _released_order(conn: PgConn, *, funding: str, funded: int) -> str:
    order_id = str(uuid.uuid4())
    _insert_order(conn, order_id=order_id, group_id=str(uuid.uuid4()), status="completed")
    _set_funding(conn, order_id, funding, funded)
    now = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
    _insert_order_event(
        conn,
        order_id=order_id,
        from_status="shipped",
        to_status="delivered",
        actor=SYSTEM_ACTOR_ID,
        created_at=now - timedelta(hours=2),
    )
    _insert_order_event(
        conn,
        order_id=order_id,
        from_status="delivered",
        to_status="completed",
        actor=CUSTOMER_ID,
        created_at=now - timedelta(hours=1),
    )
    seed_escrow_for_order(conn, suffix=order_id)
    return order_id


def _ledger_net(conn: PgConn) -> int:
    result = conn.run("SELECT coalesce(sum(amount_ngwee), 0)::text FROM public.ledger_postings;")
    assert result.ok and result.rows
    return int(result.rows[0])


def _funding_txns(conn: PgConn, order_id: str) -> int:
    key = delivery_funding_idempotency_key(order_id)
    result = conn.run(
        f"SELECT count(*)::text FROM public.ledger_transactions WHERE idempotency_key = '{key}';"
    )
    assert result.ok and result.rows
    return int(result.rows[0])


class TestDeliveryFundingAtRelease:
    def test_vendor_free_delivery_is_charged_to_vendor_payable(
        self, db: PgConn, db_url_env: None
    ) -> None:
        payable = account_balance_ngwee(VENDOR_PAYABLE_ID)
        revenue = account_balance_ngwee(DELIVERY_REVENUE_ID)
        order_id = _released_order(db, funding="vendor", funded=FEE)
        now = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)

        result = evaluate_and_release(_SERVICE, order_id, now=now)

        assert result.outcome == "released"
        # Vendor is owed items − commission − the delivery it promised for free.
        assert account_balance_ngwee(VENDOR_PAYABLE_ID) == payable - NET_NGEWEE + FEE
        assert account_balance_ngwee(DELIVERY_REVENUE_ID) == revenue - FEE
        assert _funding_txns(db, order_id) == 1
        assert _ledger_net(db) == 0

        # Re-running release (sweeper overlap) never charges the vendor twice.
        evaluate_and_release(_SERVICE, order_id, now=now)
        post_order_delivery_funding(order_id=order_id)
        assert _funding_txns(db, order_id) == 1
        assert account_balance_ngwee(VENDOR_PAYABLE_ID) == payable - NET_NGEWEE + FEE

    def test_automatic_free_delivery_reclassifies_commission(
        self, db: PgConn, db_url_env: None
    ) -> None:
        commission = account_balance_ngwee(COMMISSION_ID)
        revenue = account_balance_ngwee(DELIVERY_REVENUE_ID)
        payable = account_balance_ngwee(VENDOR_PAYABLE_ID)
        order_id = _released_order(db, funding="platform", funded=FEE)

        result = evaluate_and_release(_SERVICE, order_id, now=datetime(2026, 11, 13, tzinfo=UTC))

        assert result.outcome == "released"
        assert account_balance_ngwee(DELIVERY_REVENUE_ID) == revenue - FEE
        # The vendor's payable is untouched by the platform's subsidy.
        assert account_balance_ngwee(VENDOR_PAYABLE_ID) == payable - NET_NGEWEE
        # Commission captured at release (credit), then FEE moved out of it (debit).
        assert account_balance_ngwee(COMMISSION_ID) == commission - COMMISSION_NGEWEE + FEE
        assert _ledger_net(db) == 0

    @pytest.mark.parametrize("funding", ["customer", "vendor_self"])
    def test_customer_and_self_delivery_post_no_funding(
        self, db: PgConn, db_url_env: None, funding: str
    ) -> None:
        order_id = _released_order(db, funding=funding, funded=0)
        evaluate_and_release(_SERVICE, order_id, now=datetime(2026, 11, 13, tzinfo=UTC))
        assert _funding_txns(db, order_id) == 0
        assert _ledger_net(db) == 0

    def test_db_refuses_customer_fee_plus_vendor_charge(self, db: PgConn) -> None:
        order_id = str(uuid.uuid4())
        _insert_order(db, order_id=order_id, group_id=str(uuid.uuid4()), status="placed")
        refused = db.run(
            f"UPDATE public.orders SET delivery_fee_ngwee = 3000, delivery_funding = 'vendor', "
            f"delivery_funded_ngwee = 3000 WHERE id = '{order_id}';"
        )
        assert not refused.ok
        assert "orders_delivery_funding_check" in (refused.error or "")
        refused = db.run(
            f"UPDATE public.orders SET delivery_funding = 'vendor_self', "
            f"delivery_funded_ngwee = 3000 WHERE id = '{order_id}';"
        )
        assert not refused.ok


def test_funding_templates_balance_and_refuse_bad_money() -> None:
    for result in (
        delivery_fee_vendor_charge(funded_ngwee=FEE, vendor_id=VENDOR_A),
        delivery_fee_platform_subsidy(funded_ngwee=FEE),
    ):
        assert sum(leg.amount_ngwee for leg in result.legs) == 0
        assert {leg.account.kind for leg in result.legs} >= {"delivery_revenue"}
    with pytest.raises(ValueError):
        delivery_fee_vendor_charge(funded_ngwee=0, vendor_id=VENDOR_A)
    with pytest.raises((TypeError, ValueError)):
        delivery_fee_platform_subsidy(funded_ngwee=45.0)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        delivery_fee_vendor_charge(funded_ngwee=FEE, vendor_id=None)  # type: ignore[arg-type]
