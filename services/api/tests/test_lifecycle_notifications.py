"""Never-silent events are emitted once, after commit, and never break the transition."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from app.services.notifications import lifecycle
from tests.test_event_wiring import (
    CHECKOUT_GROUP_ID,
    CUSTOMER_ID,
    ORDER_ID,
    VENDOR_ID,
    VENDOR_OWNER_ID,
    _FakeClient,
    _FakeTable,
    _outbox,
)

PAYMENT_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
PAYOUT_ID = "99999999-9999-9999-9999-999999999999"
DISPUTE_ID = "88888888-8888-8888-8888-888888888888"


def _client() -> _FakeClient:
    client = _FakeClient()
    client.tables["orders"] = _FakeTable()
    client.tables["payments"] = _FakeTable()
    client.tables["payouts"] = _FakeTable()
    client.tables["vendors"].rows.append(
        {
            "id": VENDOR_ID,
            "owner_user_id": VENDOR_OWNER_ID,
            "payout_msisdn": "+260971231234",
            "payout_rail": "mtn",
        }
    )
    client.tables["checkout_groups"].rows.append(
        {"id": CHECKOUT_GROUP_ID, "customer_id": CUSTOMER_ID}
    )
    client.tables["orders"].rows.append(
        {"id": ORDER_ID, "vendor_id": VENDOR_ID, "customer_id": CUSTOMER_ID, "total_ngwee": 5000}
    )
    client.tables["payments"].rows.append(
        {"id": PAYMENT_ID, "checkout_group_id": CHECKOUT_GROUP_ID, "amount_ngwee": 12345}
    )
    client.tables["payouts"].rows.append(
        {"id": PAYOUT_ID, "vendor_id": VENDOR_ID, "amount_ngwee": 290000, "resolve_snapshot": {}}
    )
    return client


def _templates(client: _FakeClient) -> list[str]:
    return [row["template"] for row in _outbox(client)]


CASES: list[tuple[str, Any, str, str]] = [
    (
        "order_cancelled",
        lambda c: lifecycle.notify_order_transition(ORDER_ID, "cancelled", client=c),
        "order_cancelled",
        CUSTOMER_ID,
    ),
    (
        "order_completed",
        lambda c: lifecycle.notify_order_transition(ORDER_ID, "completed", client=c),
        "order_completed",
        CUSTOMER_ID,
    ),
    (
        "payment_failed",
        lambda c: lifecycle.notify_payment_failed(PAYMENT_ID, client=c),
        "payment_failed",
        CUSTOMER_ID,
    ),
    (
        "payout_sent",
        lambda c: lifecycle.notify_vendor_payout(PAYOUT_ID, sent=True, client=c),
        "payout_sent",
        VENDOR_OWNER_ID,
    ),
    (
        "payout_failed",
        lambda c: lifecycle.notify_vendor_payout(PAYOUT_ID, sent=False, client=c),
        "payout_failed",
        VENDOR_OWNER_ID,
    ),
    (
        "dispute_opened",
        lambda c: lifecycle.notify_dispute_opened(DISPUTE_ID, ORDER_ID, client=c),
        "dispute_opened",
        VENDOR_OWNER_ID,
    ),
    (
        "dispute_resolved",
        lambda c: lifecycle.notify_dispute_resolved(
            DISPUTE_ID, ORDER_ID, "resolved_refund", client=c
        ),
        "dispute_resolved",
        CUSTOMER_ID,
    ),
    (
        "ticket_issued",
        lambda c: lifecycle.notify_tickets_issued(ORDER_ID, "Jazz Night", client=c),
        "ticket_issued",
        CUSTOMER_ID,
    ),
]


@pytest.mark.parametrize(
    ("name", "fire", "template", "recipient"), CASES, ids=[c[0] for c in CASES]
)
def test_event_is_enqueued_exactly_once_even_when_retried(
    name: str, fire: Any, template: str, recipient: str
) -> None:
    client = _client()
    fire(client)
    fire(client)  # retry of the same committed transition
    assert _templates(client) == [template]
    assert _outbox(client)[0]["payload"]["recipient_id"] == recipient


def test_payout_payload_is_integer_ngwee_with_destination() -> None:
    client = _client()
    lifecycle.notify_vendor_payout(PAYOUT_ID, sent=True, client=client)
    payload = _outbox(client)[0]["payload"]
    assert payload["amount_ngwee"] == 290000
    assert payload["destination_label"] == "MTN number ending 1234"


def test_customer_refund_payouts_never_notify_the_vendor() -> None:
    client = _client()
    client.tables["payouts"].rows[0]["resolve_snapshot"] = {"kind": "customer_refund"}
    lifecycle.notify_vendor_payout(PAYOUT_ID, sent=True, client=client)
    assert _outbox(client) == []


def test_helpers_swallow_a_broken_client() -> None:
    class Broken:
        def table(self, _name: str) -> Any:
            raise RuntimeError("db down")

    broken = Broken()
    lifecycle.notify_order_transition(ORDER_ID, "cancelled", client=broken)
    lifecycle.notify_payment_failed(PAYMENT_ID, client=broken)
    lifecycle.notify_vendor_payout(PAYOUT_ID, sent=True, client=broken)
    lifecycle.notify_dispute_opened(DISPUTE_ID, ORDER_ID, client=broken)
    lifecycle.notify_tickets_issued(ORDER_ID, "x", client=broken)


# --- hooks: notified after commit, and a notification failure never affects the transition


def _order_transition(monkeypatch: pytest.MonkeyPatch, notify: Any) -> Any:
    from app.services.notifications import lifecycle as lc
    from app.services.orders import state

    snapshot = state.OrderSnapshot(
        id=ORDER_ID,
        status=state.OrderStatus.PLACED,
        fulfilment="delivery",
        checkout_group_id=CHECKOUT_GROUP_ID,
        cod=True,
        paid=False,
    )
    monkeypatch.setattr(state, "_fetch_order_snapshot", lambda *_a, **_k: snapshot)
    monkeypatch.setattr(
        state, "_validate_snapshot_transition", lambda *_a, **_k: state.OrderStatus.CANCELLED
    )
    monkeypatch.setattr(
        state,
        "run_sql_script",
        lambda *_a, **_k: SimpleNamespace(ok=True, rows=["cancelled"], error=None),
    )
    monkeypatch.setattr(lc, "notify_order_transition", notify)
    return state.transition_order(
        order_id=ORDER_ID,
        event=state.OrderEvent.CANCEL,
        actor_role=state.ActorRole.ADMIN,
        actor_id=VENDOR_OWNER_ID,
        note="cancel",
    )


def test_order_transition_notifies_after_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []
    outcome = _order_transition(monkeypatch, lambda oid, st, **_k: calls.append((oid, st)))
    assert outcome.to_status.value == "cancelled"
    assert calls == [(ORDER_ID, "cancelled")]


def test_order_transition_survives_notification_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("outbox down")

    outcome = _order_transition(monkeypatch, boom)
    assert outcome.to_status.value == "cancelled"


@pytest.mark.parametrize("fails", [False, True])
def test_payment_failed_hook_never_changes_the_outcome(
    monkeypatch: pytest.MonkeyPatch, fails: bool
) -> None:
    from app.services.notifications import lifecycle as lc
    from app.services.payments import state

    sentinel = object()
    seen: list[str] = []

    def notify(payment_id: str, **_k: Any) -> None:
        seen.append(payment_id)
        if fails:
            raise RuntimeError("outbox down")

    monkeypatch.setattr(
        state,
        "_load_payment",
        lambda *_a, **_k: SimpleNamespace(
            status=state.PaymentStatus.USSD_PUSHED, raw={}, amount_ngwee=10000, rail="momo"
        ),
    )
    monkeypatch.setattr(state, "transition_payment", lambda *_a, **_k: sentinel)
    monkeypatch.setattr(lc, "notify_payment_failed", notify)
    client = SimpleNamespace(client=object())
    result = state.apply_payment_status(
        client,
        payment_id=PAYMENT_ID,
        incoming_status=state.PaymentStatus.FAILED,
        actor_id=VENDOR_OWNER_ID,
        note="failed",
    )
    assert result is sentinel
    assert seen == [PAYMENT_ID]
