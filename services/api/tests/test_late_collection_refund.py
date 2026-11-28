# ruff: noqa: F811
"""Late Mobile Money collection (order/attempt cancelled) -> automated, idempotent refund.

Real Postgres for the candidate query, ledger and order money gate; the PostgREST-only
tables (refunds / payouts / audit) use the shared in-memory fake from test_refunds.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from app.services.refunds.late_collection import (
    late_collection_auto_refund_enabled,
    late_collection_charge_key,
    late_collection_source_key,
    sweep_late_collection_refunds,
)
from tests.rls.conftest import PgConn
from tests.test_order_jobs import (  # noqa: F401  (fixtures re-exported for this module)
    GROSS_NGEWEE,
    VENDOR_A,
    _insert_order,
    _insert_order_event,
    db,
    db_url_env,
    jobs_client,
)
from tests.test_refunds import FakeServiceClient, FakeSupabaseClient, FakeTable

PAYER_PHONE = "+260971112233"


@pytest.fixture(autouse=True)
def _enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LATE_COLLECTION_AUTO_REFUND_ENABLED", "true")
    monkeypatch.setenv("PAYOUTS_ENABLED", "true")


@pytest.fixture(autouse=True)
def _refund_ledger_without_fk(monkeypatch: pytest.MonkeyPatch) -> None:
    """Refund legs post to the REAL ledger; only the refund_id FK is dropped because the
    refunds table itself is the in-memory fake in this module."""
    from app.services.ledger.engine import post_transaction as real_post

    def _post(**kwargs: Any) -> Any:
        kwargs["refund_id"] = None
        return real_post(**kwargs)

    monkeypatch.setattr("app.services.refunds.execute.post_transaction", _post)


@pytest.fixture(autouse=True)
def _clean_exceptions(db: PgConn) -> Iterator[None]:  # noqa: F811
    db.run("DELETE FROM public.payment_collection_exceptions;")
    # Seeded by the pay-at-door migration; re-assert it so the module also passes on a
    # database whose ledger_accounts were reset by another test.
    seeded = db.run_script(
        "BEGIN; SET LOCAL role service_role; "
        "INSERT INTO public.ledger_accounts (id, kind) VALUES "
        "('c7000000-0000-0000-0000-000000000008', 'door_payment_suspense') "
        "ON CONFLICT DO NOTHING; COMMIT;"
    )
    assert seeded.ok, seeded.error
    yield


def _late_collection(
    db: PgConn,
    *,
    reason: str = "order_cancelled",
    rail: str = "mtn",
    payer_phone: str | None = PAYER_PHONE,
    order_status: str = "cancelled",
    payment_status: str = "initiated",
) -> tuple[str, str, str]:
    """-> (order_id, group_id, payment_id) with an unresolved collection exception."""
    order_id, group_id, payment_id = (str(uuid.uuid4()) for _ in range(3))
    _insert_order(db, order_id=order_id, group_id=group_id, status=order_status)
    raw = f'{{"payer_phone": "{payer_phone}"}}' if payer_phone else "{}"
    paid = db.run(
        "INSERT INTO public.payments (id, checkout_group_id, provider, rail, lenco_reference, "
        f"amount_ngwee, status, raw) VALUES ('{payment_id}', '{group_id}', 'lenco', '{rail}', "
        f"'pay-{payment_id}', {GROSS_NGEWEE}, '{payment_status}', '{raw}'::jsonb);"
    )
    assert paid.ok, paid.error
    exc = db.run(
        "INSERT INTO public.payment_collection_exceptions "
        "(payment_id, provider_reference, reason, first_observation, latest_observation) "
        f"VALUES ('{payment_id}', 'prov-{payment_id}', '{reason}', '{{}}', '{{}}');"
    )
    assert exc.ok, exc.error
    return order_id, group_id, payment_id


def _client(order_id: str, payment_id: str) -> FakeServiceClient:
    fake = FakeSupabaseClient()
    fake.tables["payment_collection_exceptions"] = FakeTable()
    fake.tables["payment_collection_exceptions"].rows.append(
        {"payment_id": payment_id, "resolved_at": None}
    )
    fake.tables["orders"].rows.append(
        {
            "id": order_id,
            "vendor_id": VENDOR_A,
            "delivery_fee_ngwee": 0,
            "status": "cancelled",
            "cod": False,
        }
    )
    return FakeServiceClient(fake)


def _count(db: PgConn, key: str) -> int:
    result = db.run(
        f"SELECT count(*) FROM public.ledger_transactions WHERE idempotency_key = '{key}';"
    )
    assert result.ok and result.rows, result.error
    return int(result.rows[0])


def _rows(client: FakeServiceClient, table: str) -> list[dict[str, Any]]:
    return client.client.tables[table].rows


@pytest.mark.usefixtures("db_url_env")
class TestLateCollectionRefund:
    def test_off_by_default(self, db: PgConn, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LATE_COLLECTION_AUTO_REFUND_ENABLED")
        assert late_collection_auto_refund_enabled() is False
        order_id, _, payment_id = _late_collection(db)
        client = _client(order_id, payment_id)
        outcome = sweep_late_collection_refunds(client)
        assert outcome.enabled is False and outcome.scanned == 0
        assert _count(db, late_collection_charge_key(payment_id)) == 0
        assert _rows(client, "refunds") == []

    def test_blocked_while_payouts_disabled_posts_nothing(
        self, db: PgConn, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("PAYOUTS_ENABLED")
        order_id, _, payment_id = _late_collection(db)
        client = _client(order_id, payment_id)
        outcome = sweep_late_collection_refunds(client)
        assert outcome.enabled is True and outcome.payouts_enabled is False
        assert outcome.scanned == 0
        assert _count(db, late_collection_charge_key(payment_id)) == 0
        assert _rows(client, "refunds") == [] and _rows(client, "payouts") == []

    @pytest.mark.parametrize("reason", ["order_cancelled", "payment_cancelled"])
    def test_refunds_payer_msisdn_through_ledger_payout(self, db: PgConn, reason: str) -> None:
        order_id, _, payment_id = _late_collection(
            db,
            reason=reason,
            rail="airtel",
            order_status="cancelled" if reason == "order_cancelled" else "placed",
            payment_status="cancelled",
        )
        client = _client(order_id, payment_id)
        outcome = sweep_late_collection_refunds(client)
        assert (outcome.refunded, outcome.manual_review, outcome.failed) == (1, 0, 0)

        (refund,) = _rows(client, "refunds")
        assert refund["source_key"] == late_collection_source_key(payment_id)
        assert refund["amount_ngwee"] == GROSS_NGEWEE
        (payout,) = _rows(client, "payouts")
        assert payout["payout_kind"] == "customer_refund"
        assert payout["amount_ngwee"] == GROSS_NGEWEE
        assert payout["rail"] == "airtel"
        assert payout["resolve_snapshot"]["customer_momo"] == PAYER_PHONE
        assert _count(db, late_collection_charge_key(payment_id)) == 1
        assert _count(db, f"{late_collection_source_key(payment_id)}-ledger") == 1
        assert _rows(client, "payment_collection_exceptions")[0]["resolved_at"] is not None

    def test_run_twice_creates_exactly_one_refund(self, db: PgConn) -> None:
        order_id, _, payment_id = _late_collection(db)
        client = _client(order_id, payment_id)
        first = sweep_late_collection_refunds(client)
        # Worst case: the exception was NOT marked resolved (crash after the payout,
        # concurrent worker, manual un-resolve). The deterministic keys still collapse it.
        db.run("UPDATE public.payment_collection_exceptions SET resolved_at = NULL;")
        second = sweep_late_collection_refunds(client)
        third = sweep_late_collection_refunds(client)
        assert first.refunded == 1
        assert (second.refunded, second.already_refunded) == (0, 1)
        assert (third.refunded, third.already_refunded) == (0, 1)
        assert len(_rows(client, "refunds")) == 1
        assert len(_rows(client, "payouts")) == 1
        assert _count(db, late_collection_charge_key(payment_id)) == 1
        assert _count(db, f"{late_collection_source_key(payment_id)}-ledger") == 1

    def test_card_payment_is_left_for_a_human(self, db: PgConn) -> None:
        order_id, _, payment_id = _late_collection(db, rail="card")
        client = _client(order_id, payment_id)
        outcome = sweep_late_collection_refunds(client)
        assert (outcome.refunded, outcome.manual_review) == (0, 1)
        assert _count(db, late_collection_charge_key(payment_id)) == 0
        assert _rows(client, "refunds") == []

    def test_missing_payer_phone_is_left_for_a_human(self, db: PgConn) -> None:
        order_id, _, payment_id = _late_collection(db, payer_phone=None)
        client = _client(order_id, payment_id)
        outcome = sweep_late_collection_refunds(client)
        assert (outcome.refunded, outcome.manual_review) == (0, 1)
        assert _count(db, late_collection_charge_key(payment_id)) == 0

    def test_previously_failed_refund_is_never_retried_automatically(self, db: PgConn) -> None:
        order_id, _, payment_id = _late_collection(db)
        client = _client(order_id, payment_id)
        _rows(client, "refunds").append(
            {
                "id": str(uuid.uuid4()),
                "order_id": order_id,
                "source_key": late_collection_source_key(payment_id),
                "status": "failed",
                "amount_ngwee": GROSS_NGEWEE,
                "breakdown": {},
            }
        )
        outcome = sweep_late_collection_refunds(client)
        assert (outcome.refunded, outcome.manual_review) == (0, 1)
        assert _count(db, late_collection_charge_key(payment_id)) == 0
        assert _rows(client, "payouts") == []

    def test_other_exception_reasons_are_ignored(self, db: PgConn) -> None:
        order_id, _, payment_id = _late_collection(db, reason="sibling_payment_success")
        client = _client(order_id, payment_id)
        outcome = sweep_late_collection_refunds(client)
        assert outcome.scanned == 0
        assert _count(db, late_collection_charge_key(payment_id)) == 0

    def test_live_order_with_order_cancelled_reason_is_ignored(self, db: PgConn) -> None:
        """order_cancelled on a service obligation / non-cancelled order is not ours."""
        order_id, _, payment_id = _late_collection(db, order_status="placed")
        client = _client(order_id, payment_id)
        assert sweep_late_collection_refunds(client).scanned == 0


def _release_vendor_amount(db: PgConn, order_id: str) -> int:
    result = db.run(
        "SELECT coalesce(sum(abs(lp.amount_ngwee)), 0) FROM public.ledger_transactions lt "
        "JOIN public.ledger_postings lp ON lp.transaction_id = lt.id "
        "JOIN public.ledger_accounts la ON la.id = lp.account_id "
        f"WHERE lt.order_id = '{order_id}' AND lt.kind = 'release_to_vendor' "
        "AND la.kind = 'vendor_payable';"
    )
    assert result.ok and result.rows, result.error
    return int(result.rows[0])


def _shipped_and_funded(db: PgConn, order_id: str, now: Any) -> None:
    from datetime import timedelta

    from app.services.ledger.engine import post_transaction
    from app.services.ledger.templates import LedgerTemplate

    _insert_order_event(
        db,
        order_id=order_id,
        from_status="processing",
        to_status="shipped",
        actor=VENDOR_A,
        created_at=now - timedelta(days=8),
    )
    post_transaction(
        idempotency_key=f"escrow-hold-{order_id}",
        template=LedgerTemplate.ESCROW_HOLD,
        order_id=order_id,
        order_amount_ngwee=GROSS_NGEWEE,
    )


class TestLateCashNeverReachesVendor:
    def test_refund_step_failure_then_release_leaves_vendor_amount_unchanged(
        self, db: PgConn, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Duplicate payment on a LIVE order, refund fails, order later released.

        The late cash is parked in door_payment_suspense (never escrow), so the
        release pays the vendor exactly what an identical order without a duplicate
        payment gets.
        """
        from datetime import UTC, datetime

        from app.errors import AppError
        from app.services.escrow.release import evaluate_and_release
        from app.services.escrow.release_accounting import summarize_order_release_ledger

        now = datetime.now(UTC)
        live_order, _, payment_id = _late_collection(
            db, reason="payment_cancelled", order_status="shipped", payment_status="cancelled"
        )
        control_order, control_group = str(uuid.uuid4()), str(uuid.uuid4())
        _insert_order(db, order_id=control_order, group_id=control_group, status="shipped")
        _shipped_and_funded(db, live_order, now)
        _shipped_and_funded(db, control_order, now)

        def boom(**_: Any) -> Any:
            raise AppError("refund_gate_failed", "simulated refund-step failure", 503)

        monkeypatch.setattr("app.services.refunds.late_collection.execute_refund", boom)
        client = _client(live_order, payment_id)
        outcome = sweep_late_collection_refunds(client)
        assert (outcome.refunded, outcome.failed) == (0, 1)
        assert _rows(client, "refunds") == []

        # Cash is booked, but to suspense: no escrow leg exists for the late payment.
        assert _count(db, late_collection_charge_key(payment_id)) == 1
        summary = summarize_order_release_ledger(live_order)
        assert summary.charge_received_ngwee == GROSS_NGEWEE  # only the real escrow hold
        suspense = db.run(
            "SELECT coalesce(sum(lp.amount_ngwee), 0) FROM public.ledger_postings lp "
            "JOIN public.ledger_accounts la ON la.id = lp.account_id "
            "JOIN public.ledger_transactions lt ON lt.id = lp.transaction_id "
            f"WHERE lt.payment_id = '{payment_id}' AND la.kind = 'door_payment_suspense';"
        )
        assert suspense.rows[0] == str(-GROSS_NGEWEE)

        evaluate_and_release(client, live_order, now=now)
        evaluate_and_release(client, control_order, now=now)
        live_amount = _release_vendor_amount(db, live_order)
        assert live_amount > 0
        assert live_amount == _release_vendor_amount(db, control_order)


class TestMultiOrderCheckoutAudit:
    def test_audit_row_records_checkout_group_and_every_order(self, db: PgConn) -> None:
        order_id, group_id, payment_id = _late_collection(db)
        sibling = str(uuid.uuid4())
        # One order per (group, vendor): the sibling belongs to a second shop.
        _insert_order(db, order_id=sibling, group_id=str(uuid.uuid4()), status="placed")
        moved = db.run(
            f"UPDATE public.orders SET checkout_group_id = '{group_id}', "
            f"vendor_id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb' WHERE id = '{sibling}';"
        )
        assert moved.ok, moved.error
        client = _client(order_id, payment_id)
        outcome = sweep_late_collection_refunds(client)
        assert outcome.refunded == 1
        (audit,) = [
            r
            for r in _rows(client, "audit_log")
            if r.get("action") == "payment.late_collection_refund"
        ]
        assert audit["after"]["checkout_group_id"] == group_id
        assert sorted(audit["after"]["checkout_group_order_ids"]) == sorted([order_id, sibling])


class TestLateCollectionEndpoint:
    PATH = "/internal/order-jobs/refund-late-collections"

    def test_requires_internal_token(self, jobs_client: Any) -> None:
        assert jobs_client.post(self.PATH, json={}).status_code == 401

    @pytest.mark.usefixtures("db_url_env")
    def test_disabled_flag_returns_200_and_does_nothing(
        self, jobs_client: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tests.test_order_jobs import INTERNAL_TOKEN

        monkeypatch.delenv("LATE_COLLECTION_AUTO_REFUND_ENABLED")
        response = jobs_client.post(
            self.PATH, json={}, headers={"X-Internal-Token": INTERNAL_TOKEN}
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["enabled"] is False
        assert body["scanned"] == 0 and body["refunded"] == 0
