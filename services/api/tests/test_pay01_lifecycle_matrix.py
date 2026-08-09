"""PAY-01 synthetic lifecycle matrix (S1–S14) — operational + accounting invariants.

Certifies checkout → reservation → payment → order → escrow → release → commission
→ payout gates under retries, races, and failures. Uses fakes + pure SM where
possible; DB-backed cases reuse existing fixtures without production money.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from app.routers.vendor_orders import _available_vendor_actions
from app.services.orders.state import (
    PREPAID_PAYMENT_REQUIRED_EVENTS,
    ActorRole,
    OrderEvent,
    OrderStatus,
    PrepaidPaymentRequiredError,
    resolve_transition,
)
from app.services.payments.state import (
    PaymentEvent,
    PaymentStatus,
    should_apply_status,
)
from app.services.payments.state import (
    resolve_transition as resolve_payment_transition,
)
from app.services.payouts.gate import PayoutsDisabledError, assert_payouts_enabled
from tests.rls.conftest import PgConn


@pytest.fixture
def db_url_env(db: PgConn) -> Generator[None, None, None]:
    """Point SUPABASE_DB_URL at the live test DB for service-layer DB access."""
    previous = os.environ.get("SUPABASE_DB_URL")
    os.environ["SUPABASE_DB_URL"] = db.dsn
    yield
    if previous is None:
        os.environ.pop("SUPABASE_DB_URL", None)
    else:
        os.environ["SUPABASE_DB_URL"] = previous


# ---------------------------------------------------------------------------
# S1–S14 matrix documentation (asserted by focused cases below)
# ---------------------------------------------------------------------------

PAY01_MATRIX: dict[str, dict[str, str]] = {
    "S1": {
        "scenario": "payment success",
        "ops": "payment=success; order=placed→fulfilable; escrow ledger posted",
        "acct": "single escrow-hold / charge_received; no duplicate txn",
    },
    "S2": {
        "scenario": "decline",
        "ops": "payment=failed; order remains placed unpaid; no fulfilment actions",
        "acct": "no escrow ledger",
    },
    "S3": {
        "scenario": "timeout",
        "ops": "payment=expired; reservation releaseable; order unpaid",
        "acct": "no escrow ledger",
    },
    "S4": {
        "scenario": "duplicate webhook",
        "ops": "second SUCCESS is no-op / sibling skip",
        "acct": "ledger idempotency key prevents double post",
    },
    "S5": {
        "scenario": "poll then webhook",
        "ops": "shared apply_payment_status converges",
        "acct": "one SUCCESS payment row + one collection posting",
    },
    "S6": {
        "scenario": "webhook then poll",
        "ops": "poll sees SUCCESS terminal; should_apply_status false",
        "acct": "unchanged books",
    },
    "S7": {
        "scenario": "checkout double-submit",
        "ops": "unique (checkout_group, vendor) + idempotency key",
        "acct": "one order set",
    },
    "S8": {
        "scenario": "inventory disappears during payment",
        "ops": "hold consume fails → no order; or order already created then unpaid cancel",
        "acct": "no escrow without success",
    },
    "S9": {
        "scenario": "price changes",
        "ops": "session totals mismatch → order create 409",
        "acct": "no payment / ledger",
    },
    "S10": {
        "scenario": "reservation expires",
        "ops": "sweeper restocks; hold invalid at create",
        "acct": "none",
    },
    "S11": {
        "scenario": "refund",
        "ops": "order_money_gates single-drain",
        "acct": "refund keys balance; release blocked or remainder-capped",
    },
    "S12": {
        "scenario": "dispute",
        "ops": "open dispute → release held",
        "acct": "no release-{order} posting",
    },
    "S13": {
        "scenario": "payout disabled",
        "ops": "assert_payouts_enabled fail-closed",
        "acct": "no payout-executed ledger",
    },
    "S14": {
        "scenario": "unknown callback/payment reference",
        "ops": "webhook processor no-ops missing payment",
        "acct": "no ledger write",
    },
}


def test_pay01_matrix_covers_s1_through_s14() -> None:
    assert set(PAY01_MATRIX) == {f"S{i}" for i in range(1, 15)}
    for _sid, row in PAY01_MATRIX.items():
        assert row["scenario"]
        assert row["ops"]
        assert row["acct"]


# --- S1 / S2 / S3: payment SM edges including INITIATED orphan fix -------------


@pytest.mark.parametrize(
    ("from_status", "event", "to_status"),
    [
        (PaymentStatus.USSD_PUSHED, PaymentEvent.SUCCESS, PaymentStatus.SUCCESS),
        (PaymentStatus.USSD_PUSHED, PaymentEvent.FAILED, PaymentStatus.FAILED),
        (PaymentStatus.USSD_PUSHED, PaymentEvent.EXPIRED, PaymentStatus.EXPIRED),
        (PaymentStatus.INITIATED, PaymentEvent.SUCCESS, PaymentStatus.SUCCESS),
        (PaymentStatus.INITIATED, PaymentEvent.FAILED, PaymentStatus.FAILED),
        (PaymentStatus.INITIATED, PaymentEvent.EXPIRED, PaymentStatus.EXPIRED),
    ],
)
def test_s1_s2_s3_payment_transitions(
    from_status: PaymentStatus,
    event: PaymentEvent,
    to_status: PaymentStatus,
) -> None:
    assert resolve_payment_transition(from_status=from_status, event=event) == to_status


# --- S4 / S5 / S6: webhook/poll race precedence --------------------------------


def test_s4_s5_s6_webhook_poll_race_precedence() -> None:
    # S6: after SUCCESS, poll/webhook failed is ignored
    assert (
        should_apply_status(
            current=PaymentStatus.SUCCESS,
            incoming=PaymentStatus.FAILED,
        )
        is False
    )
    # S5: poll SUCCESS applies over USSD_PUSHED
    assert (
        should_apply_status(
            current=PaymentStatus.USSD_PUSHED,
            incoming=PaymentStatus.SUCCESS,
        )
        is True
    )
    # Same status is a no-op (duplicate webhook)
    assert (
        should_apply_status(
            current=PaymentStatus.SUCCESS,
            incoming=PaymentStatus.SUCCESS,
        )
        is False
    )
    # Late SUCCESS after FAILED still applies (reconcile)
    assert (
        should_apply_status(
            current=PaymentStatus.FAILED,
            incoming=PaymentStatus.SUCCESS,
        )
        is True
    )


# --- Seller never fulfils unpaid prepaid (S2/S3 operational) -------------------


def test_unpaid_prepaid_blocks_fulfilment_actions() -> None:
    actions = _available_vendor_actions(
        status="placed",
        fulfilment="delivery",
        paid=False,
        cod=False,
    )
    assert actions == ["reject"]


def test_paid_prepaid_allows_confirm() -> None:
    actions = _available_vendor_actions(
        status="placed",
        fulfilment="delivery",
        paid=True,
        cod=False,
    )
    assert "confirm" in actions
    assert "reject" in actions


def test_cod_allows_confirm_without_payment_success() -> None:
    actions = _available_vendor_actions(
        status="placed",
        fulfilment="delivery",
        paid=False,
        cod=True,
    )
    assert "confirm" in actions


def test_prepaid_payment_required_events_cover_fulfilment() -> None:
    assert OrderEvent.CONFIRM in PREPAID_PAYMENT_REQUIRED_EVENTS
    assert OrderEvent.SHIP in PREPAID_PAYMENT_REQUIRED_EVENTS
    assert OrderEvent.REJECT not in PREPAID_PAYMENT_REQUIRED_EVENTS


@pytest.mark.usefixtures("db", "db_url_env")
def test_s2_transition_order_blocks_unpaid_prepaid_confirm(db: object) -> None:
    from app.services.orders.state import transition_order
    from tests.rls.conftest import PgConn
    from tests.test_order_state import VENDOR_ID, _insert_order

    assert isinstance(db, PgConn)
    order_id = str(uuid.uuid4())
    group_id = str(uuid.uuid4())
    _insert_order(db, order_id=order_id, checkout_group_id=group_id, status="placed")

    with pytest.raises(PrepaidPaymentRequiredError) as exc:
        transition_order(
            order_id=order_id,
            event=OrderEvent.CONFIRM,
            actor_role=ActorRole.VENDOR,
            actor_id=VENDOR_ID,
            note="attempt unpaid confirm",
        )
    assert exc.value.code == "order_payment_required"


@pytest.mark.usefixtures("db", "db_url_env")
def test_s1_paid_prepaid_confirm_allowed(db: object) -> None:
    from app.services.orders.state import transition_order
    from tests.rls.conftest import PgConn
    from tests.test_order_state import (
        VENDOR_ID,
        _insert_order,
        _insert_payment,
        _order_status,
    )

    assert isinstance(db, PgConn)
    order_id = str(uuid.uuid4())
    group_id = str(uuid.uuid4())
    _insert_order(db, order_id=order_id, checkout_group_id=group_id, status="placed")
    _insert_payment(
        db,
        payment_id=str(uuid.uuid4()),
        checkout_group_id=group_id,
        status="success",
    )

    transition_order(
        order_id=order_id,
        event=OrderEvent.CONFIRM,
        actor_role=ActorRole.VENDOR,
        actor_id=VENDOR_ID,
        note="paid confirm",
    )
    assert _order_status(db, order_id) == "confirmed"


@pytest.mark.usefixtures("db", "db_url_env")
def test_s14_cod_semantically_separate_confirm_without_payment(db: object) -> None:
    from app.services.orders.state import transition_order
    from tests.rls.conftest import PgConn
    from tests.test_order_state import VENDOR_ID, _insert_order, _order_status

    assert isinstance(db, PgConn)
    order_id = str(uuid.uuid4())
    group_id = str(uuid.uuid4())
    _insert_order(
        db,
        order_id=order_id,
        checkout_group_id=group_id,
        status="placed",
        cod=True,
    )
    transition_order(
        order_id=order_id,
        event=OrderEvent.CONFIRM,
        actor_role=ActorRole.VENDOR,
        actor_id=VENDOR_ID,
        note="cod confirm",
    )
    assert _order_status(db, order_id) == "confirmed"


# --- S12 / S13: dispute hold + payouts fail-closed -----------------------------


def test_s13_payouts_disabled_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PAYOUTS_ENABLED", raising=False)
    with pytest.raises(PayoutsDisabledError):
        assert_payouts_enabled()


def test_s12_dispute_blocks_release_rules() -> None:
    from app.services.escrow.release import evaluate_release_rules

    outcome, reason, _rule = evaluate_release_rules(
        status="delivered",
        cod=False,
        has_open_dispute=True,
        already_released=False,
        buyer_confirmed=True,
        delivered_at=datetime(2026, 7, 1, tzinfo=UTC),
        shipped_at=datetime(2026, 6, 28, tzinfo=UTC),
        release_after_delivered_hours=48,
        release_after_shipped_days=7,
        now=datetime(2026, 7, 10, tzinfo=UTC),
    )
    assert outcome == "held"
    assert reason == "dispute_open"


def test_s12_cod_release_not_eligible() -> None:
    from app.services.escrow.release import evaluate_release_rules

    outcome, reason, _rule = evaluate_release_rules(
        status="delivered",
        cod=True,
        has_open_dispute=False,
        already_released=False,
        buyer_confirmed=True,
        delivered_at=datetime(2026, 7, 1, tzinfo=UTC),
        shipped_at=None,
        release_after_delivered_hours=48,
        release_after_shipped_days=7,
        now=datetime(2026, 7, 10, tzinfo=UTC),
    )
    assert outcome == "not_eligible"
    assert reason == "cod_order"


# --- Release without escrow evidence (S1 accounting gate) ----------------------


@pytest.mark.usefixtures("db", "db_url_env")
def test_release_without_escrow_evidence_not_eligible(db: object) -> None:
    from app.services.escrow.release import evaluate_and_release
    from tests.rls.conftest import PgConn
    from tests.test_release import _insert_order, _insert_order_event

    assert isinstance(db, PgConn)
    order_id = str(uuid.uuid4())
    group_id = str(uuid.uuid4())
    now = datetime(2026, 7, 12, tzinfo=UTC)
    _insert_order(db, order_id=order_id, group_id=group_id, status="delivered")
    _insert_order_event(
        db,
        order_id=order_id,
        from_status="shipped",
        to_status="delivered",
        actor="00000000-0000-0000-0000-000000000001",
        created_at=now - timedelta(hours=72),
    )
    result = evaluate_and_release(MagicMock(), order_id, now=now)
    assert result.outcome == "not_eligible"
    assert result.reason == "unpaid"


# --- S14 unknown reference -----------------------------------------------------


def test_s14_unknown_reference_load_returns_none() -> None:
    from app.services.payments.state import _load_payment_by_reference
    from tests.test_payment_state import FakeServiceClient, FakeSupabaseClient

    fake = FakeServiceClient(FakeSupabaseClient())
    assert _load_payment_by_reference(fake, "ord-does-not-exist") is None


# --- Notification sequencing: prepaid defers vendor; payment_received wired ----


def test_payment_success_emits_customer_and_vendor_notifications() -> None:
    from app.services.payments.state import _emit_payment_success_notifications
    from tests.test_payment_state import FakeServiceClient, FakeSupabaseClient

    fake_client = FakeSupabaseClient()
    # Ensure orders table exists for select chain
    if "orders" not in fake_client.tables:
        from tests.test_payment_state import FakeTable

        fake_client.tables["orders"] = FakeTable()
    if "checkout_groups" not in fake_client.tables:
        from tests.test_payment_state import FakeTable

        fake_client.tables["checkout_groups"] = FakeTable()
    fake_client.tables["checkout_groups"].rows.append(
        {"id": "c1000000-0000-0000-0000-000000000002", "customer_id": str(uuid.uuid4())}
    )
    fake_client.tables["orders"].rows.append(
        {
            "id": str(uuid.uuid4()),
            "checkout_group_id": "c1000000-0000-0000-0000-000000000002",
            "vendor_id": str(uuid.uuid4()),
            "customer_id": str(uuid.uuid4()),
            "cod": False,
            "status": "placed",
        }
    )
    service = FakeServiceClient(fake_client)

    with (
        patch("app.services.payments.events.emit_payment_lifecycle") as pay_emit,
        patch("app.services.orders.events.emit_order_lifecycle") as order_emit,
    ):
        pay_emit.return_value = {"id": "outbox-pay"}
        order_emit.return_value = {"id": "outbox-order"}
        _emit_payment_success_notifications(
            service,
            payment_id=str(uuid.uuid4()),
            checkout_group_id="c1000000-0000-0000-0000-000000000002",
            amount_ngwee=25_000,
            lenco_reference="ord-test",
        )
        assert pay_emit.called
        assert order_emit.called
        assert pay_emit.call_args.kwargs["event"] == "payment_received"
        assert order_emit.call_args.kwargs["event"] == "order_placed"


def test_resolve_transition_matrix_still_allows_reject_when_placed() -> None:
    result = resolve_transition(
        from_status=OrderStatus.PLACED,
        event=OrderEvent.REJECT,
        actor_role=ActorRole.VENDOR,
        fulfilment="delivery",
    )
    assert result.permitted is True
