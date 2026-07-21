"""M14-P05 — lifecycle event wiring: registry coverage, routing, dedupe, adapters."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from app.services.notifications.adapter_registry import build_adapters
from app.services.notifications.adapters.base import ChannelAdapter
from app.services.notifications.events import (
    EVENT_REGISTRY,
    Audience,
    documented_events,
    emit_event,
)
from app.services.notifications.templates.whatsapp import render_whatsapp_template
from app.services.orders.events import emit_order_lifecycle
from app.services.payments.events import emit_payment_lifecycle

# Explicit documented lifecycle surface — the coverage floor every emitter path
# and every OrderEvent-driven transition must be able to reference without
# tripping emit_event's "unmapped domain event" guard.
DOCUMENTED_EVENTS: frozenset[str] = frozenset(
    {
        # order lifecycle (drives / follows OrderEvent transitions)
        "order_placed",
        "order_confirmed",
        "order_processing",
        "order_ready_pickup",
        "order_shipped",
        "order_delivered",
        "order_completed",
        "order_cancelled",
        # payment lifecycle
        "payment_received",
        "payment_failed",
        "payout_sent",
        "payout_failed",
        # kyc
        "kyc_approved",
        "kyc_rejected",
        # disputes
        "dispute_opened",
        "dispute_resolved",
        # tickets
        "ticket_issued",
        "ticket_transferred",
        # quotes
        "quote_received",
        "quote_accepted",
    }
)

VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VENDOR_OWNER_ID = "11111111-1111-1111-1111-111111111111"
CUSTOMER_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
ORDER_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
CHECKOUT_GROUP_ID = "ffffffff-ffff-ffff-ffff-ffffffffffff"


class _FakeResult:
    def __init__(self, data: Any, count: int | None = None) -> None:
        self.data = data
        self.count = count


class _FakeQuery:
    def __init__(self, table: _FakeTable) -> None:
        self._table = table
        self._filters: list[tuple[str, Any]] = []
        self._maybe_single = False
        self._op: str | None = None
        self._payload: dict[str, Any] | None = None

    def select(self, *_args: Any, **_kwargs: Any) -> _FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> _FakeQuery:
        self._filters.append((column, value))
        return self

    def limit(self, _count: int) -> _FakeQuery:
        return self

    def maybe_single(self) -> _FakeQuery:
        self._maybe_single = True
        return self

    def insert(self, payload: dict[str, Any]) -> _FakeQuery:
        self._op = "insert"
        self._payload = payload
        return self

    def execute(self) -> _FakeResult:
        if self._op == "insert":
            assert self._payload is not None
            return self._table.insert_row(self._payload)
        rows = self._table.filtered(self._filters)
        if self._maybe_single:
            return _FakeResult(rows[0] if rows else None, len(rows))
        return _FakeResult(rows, len(rows))


class _FakeTable:
    def __init__(self, unique_key: str | None = None) -> None:
        self.rows: list[dict[str, Any]] = []
        self._unique_key = unique_key

    def select(self, *_args: Any, **_kwargs: Any) -> _FakeQuery:
        return _FakeQuery(self).select()

    def insert(self, payload: dict[str, Any]) -> _FakeQuery:
        return _FakeQuery(self).insert(payload)

    def filtered(self, filters: list[tuple[str, Any]]) -> list[dict[str, Any]]:
        rows = list(self.rows)
        for column, value in filters:
            rows = [row for row in rows if row.get(column) == value]
        return rows

    def insert_row(self, payload: dict[str, Any]) -> _FakeResult:
        row = dict(payload)
        if self._unique_key is not None and self._unique_key in row:
            for existing in self.rows:
                if existing.get(self._unique_key) == row[self._unique_key]:
                    # UNIQUE(dedupe_key) collision → nothing inserted.
                    return _FakeResult([], 0)
        row.setdefault("id", str(uuid4()))
        self.rows.append(row)
        return _FakeResult([row], 1)


class _FakeClient:
    def __init__(self) -> None:
        self.tables: dict[str, _FakeTable] = {
            "notification_outbox": _FakeTable(unique_key="dedupe_key"),
            "vendors": _FakeTable(),
            "checkout_groups": _FakeTable(),
        }

    def table(self, name: str) -> _FakeTable:
        return self.tables[name]


def _fresh_client() -> _FakeClient:
    client = _FakeClient()
    client.tables["vendors"].rows.append(
        {"id": VENDOR_ID, "owner_user_id": VENDOR_OWNER_ID}
    )
    client.tables["checkout_groups"].rows.append(
        {"id": CHECKOUT_GROUP_ID, "customer_id": CUSTOMER_ID}
    )
    return client


def _outbox(client: _FakeClient) -> list[dict[str, Any]]:
    return client.tables["notification_outbox"].rows


# --------------------------------------------------------------------------
# 1. coverage completeness
# --------------------------------------------------------------------------


def test_documented_events_are_all_registered() -> None:
    assert DOCUMENTED_EVENTS <= documented_events()


def test_emit_event_never_unmapped_for_documented_events() -> None:
    for event in DOCUMENTED_EVENTS:
        client = _FakeClient()
        # Must not raise "unmapped domain event" for any documented event.
        emit_event(
            client,
            event=event,
            entity_id=ORDER_ID,
            recipient_id=CUSTOMER_ID,
            payload={},
        )


def test_emit_event_raises_for_unknown_event() -> None:
    with pytest.raises(ValueError, match="unmapped domain event"):
        emit_event(
            _FakeClient(),
            event="not_a_real_event",
            entity_id=ORDER_ID,
            recipient_id=CUSTOMER_ID,
            payload={},
        )


def test_order_ready_pickup_payload_renders_via_whatsapp_template() -> None:
    """The pickup emit payload + dispatcher-injected contact must satisfy the
    real WhatsApp template (regression: `pickup_details` + `to`/`locale`)."""
    client = _fresh_client()
    order_row = {
        "id": ORDER_ID,
        "customer_id": CUSTOMER_ID,
        "vendor_id": VENDOR_ID,
        "fulfilment": "pickup",
        "reference": "ord-abc123",
    }
    emit_order_lifecycle(
        client,
        event="order_ready_pickup",
        order_row=order_row,
        extra={"pickup_details": "PIN 123456", "pickup_pin": "123456"},
    )
    rows = _outbox(client)
    assert len(rows) == 1
    payload = dict(rows[0]["payload"])
    assert payload["recipient_id"] == CUSTOMER_ID
    # The dispatcher injects the recipient's phone + locale before send.
    payload["to"] = "+260970000000"
    payload["locale"] = "en"
    rendered = render_whatsapp_template("order_ready_pickup", payload)  # must not raise
    assert "ord-abc123" in rendered.body_parameters
    assert "PIN 123456" in rendered.body_parameters


def test_event_cancelled_payload_renders_via_whatsapp_template() -> None:
    """EVENT_REGISTRY cancellation payload must satisfy the WhatsApp template."""
    client = _fresh_client()
    row = emit_event(
        client,
        event="event_cancelled",
        entity_id="evt-1:holder-1",
        recipient_id=CUSTOMER_ID,
        payload={
            "event_title": "Jazz Night",
            "event_date": "15 Aug 2026, 18:00 UTC",
            "refund_detail": "Your payment refund is being processed by Vergeo5.",
            "recipient_id": CUSTOMER_ID,
        },
    )
    assert row is not None
    payload = dict(row["payload"])
    payload["to"] = "+260970000000"
    payload["locale"] = "en"
    rendered = render_whatsapp_template("event_cancelled", payload)
    assert "Jazz Night" in rendered.body_parameters
    assert "15 Aug 2026" in rendered.body_parameters[1]
    assert "refund" in rendered.body_parameters[2].lower()


def test_event_schedule_changed_payload_renders_via_whatsapp_template() -> None:
    """EVENT_REGISTRY schedule-change payload must satisfy the WhatsApp template."""
    client = _fresh_client()
    row = emit_event(
        client,
        event="event_schedule_changed",
        entity_id="evt-1:holder-1",
        recipient_id=CUSTOMER_ID,
        payload={
            "event_title": "Jazz Night",
            "event_date": "20 Aug 2026, 18:00 UTC",
            "venue": "Lusaka Showgrounds",
            "recipient_id": CUSTOMER_ID,
        },
    )
    assert row is not None
    payload = dict(row["payload"])
    payload["to"] = "+260970000000"
    payload["locale"] = "en"
    rendered = render_whatsapp_template("event_schedule_changed", payload)
    assert rendered.body_parameters == (
        "Jazz Night",
        "20 Aug 2026, 18:00 UTC",
        "Lusaka Showgrounds",
    )


# --------------------------------------------------------------------------
# 2. audience routing
# --------------------------------------------------------------------------


def test_customer_audience_routes_to_customer_id() -> None:
    client = _fresh_client()
    order_row = {"id": ORDER_ID, "vendor_id": VENDOR_ID, "customer_id": CUSTOMER_ID}
    row = emit_order_lifecycle(client, event="order_confirmed", order_row=order_row)
    assert row is not None
    assert EVENT_REGISTRY["order_confirmed"].audience is Audience.CUSTOMER  # type: ignore[union-attr]
    assert row["payload"]["recipient_id"] == CUSTOMER_ID


def test_vendor_audience_routes_to_vendor_owner_profile() -> None:
    client = _fresh_client()
    order_row = {"id": ORDER_ID, "vendor_id": VENDOR_ID, "customer_id": CUSTOMER_ID}
    row = emit_order_lifecycle(client, event="order_placed", order_row=order_row)
    assert row is not None
    assert EVENT_REGISTRY["order_placed"].audience is Audience.VENDOR  # type: ignore[union-attr]
    assert row["payload"]["recipient_id"] == VENDOR_OWNER_ID


def test_payment_lifecycle_routes_to_checkout_group_customer() -> None:
    client = _fresh_client()
    payment_row = {
        "id": "pay-1",
        "checkout_group_id": CHECKOUT_GROUP_ID,
        "amount_ngwee": 12345,
    }
    row = emit_payment_lifecycle(client, event="payment_received", payment_row=payment_row)
    assert row is not None
    assert row["payload"]["recipient_id"] == CUSTOMER_ID
    assert row["payload"]["amount_ngwee"] == 12345


# --------------------------------------------------------------------------
# 3. dedupe / exactly-once
# --------------------------------------------------------------------------


def test_duplicate_emit_is_deduped_to_one_row() -> None:
    client = _fresh_client()
    order_row = {"id": ORDER_ID, "vendor_id": VENDOR_ID, "customer_id": CUSTOMER_ID}

    first = emit_order_lifecycle(client, event="order_confirmed", order_row=order_row)
    second = emit_order_lifecycle(client, event="order_confirmed", order_row=order_row)

    assert first is not None
    assert second is None  # collided on unique dedupe_key
    assert len(_outbox(client)) == 1
    assert _outbox(client)[0]["dedupe_key"] == f"order_confirmed:{ORDER_ID}:whatsapp"


# --------------------------------------------------------------------------
# 4. silent events
# --------------------------------------------------------------------------


def test_silent_event_emits_nothing() -> None:
    client = _fresh_client()
    order_row = {"id": ORDER_ID, "vendor_id": VENDOR_ID, "customer_id": CUSTOMER_ID}
    assert EVENT_REGISTRY["order_completed"] is None
    row = emit_order_lifecycle(client, event="order_completed", order_row=order_row)
    assert row is None
    assert _outbox(client) == []


def test_silent_event_via_emit_event_returns_none() -> None:
    client = _FakeClient()
    row = emit_event(
        client,
        event="order_completed",
        entity_id=ORDER_ID,
        recipient_id=CUSTOMER_ID,
        payload={},
    )
    assert row is None
    assert _outbox(client) == []


# --------------------------------------------------------------------------
# 5. adapter registry
# --------------------------------------------------------------------------


def test_build_adapters_returns_three_channels_without_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for env in (
        "AT_API_KEY",
        "AT_USERNAME",
        "AT_SENDER_ID",
        "RESEND_API_KEY",
        "RESEND_FROM_EMAIL",
    ):
        monkeypatch.delenv(env, raising=False)

    adapters = build_adapters()
    assert set(adapters) == {"whatsapp", "sms", "email"}
    for adapter in adapters.values():
        assert isinstance(adapter, ChannelAdapter)
