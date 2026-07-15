"""D3: organiser event cancellation -> admin refund flags + buyer/holder notices.

Money is never moved here; the test asserts the queue + notifications only.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from app.services.escrow.event_release import MASS_REFUND_FLAG_ACTION
from app.services.events.cancellation import EVENT_CANCELLED_EVENT, process_event_cancellation

EVENT_ID = "e9000000-0000-0000-0000-000000000001"
INSTANCE_ID = "e9000000-0000-0000-0000-0000000000a1"
ORDER_ID = "e9000000-0000-0000-0000-0000000000b1"
ORDER_ITEM_ID = "e9000000-0000-0000-0000-0000000000c1"
GROUP_ID = "e9000000-0000-0000-0000-0000000000d1"
BUYER_ID = "e9000000-0000-0000-0000-0000000000e1"
HOLDER_ID = "e9000000-0000-0000-0000-0000000000f1"


class _Query:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self._filters: list[tuple[str, str, Any]] = []
        self._op: str | None = None
        self._payload: dict[str, Any] | None = None

    def select(self, *_a: Any, **_k: Any) -> _Query:
        return self

    def eq(self, column: str, value: Any) -> _Query:
        self._filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> _Query:
        self._filters.append(("in", column, list(values)))
        return self

    def order(self, *_a: Any, **_k: Any) -> _Query:
        return self

    def insert(self, payload: dict[str, Any]) -> _Query:
        self._op = "insert"
        self._payload = payload
        return self

    def _match(self, row: dict[str, Any]) -> bool:
        for op, column, value in self._filters:
            if op == "eq" and row.get(column) != value:
                return False
            if op == "in" and row.get(column) not in set(value):
                return False
        return True

    def execute(self) -> MagicMock:
        if self._op == "insert":
            assert self._payload is not None
            row = dict(self._payload)
            self._rows.append(row)
            return MagicMock(data=[row])
        return MagicMock(data=[r for r in self._rows if self._match(r)])


class _Table:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def select(self, *a: Any, **k: Any) -> _Query:
        return _Query(self.rows).select(*a, **k)

    def insert(self, payload: dict[str, Any]) -> _Query:
        return _Query(self.rows).insert(payload)


class _Client:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self.tables = {name: _Table(rows) for name, rows in tables.items()}

    def table(self, name: str) -> _Table:
        return self.tables.setdefault(name, _Table([]))


class _Service:
    def __init__(self, client: _Client) -> None:
        self.client = client


def _seeded(*, paid: bool = True, holder: bool = True) -> _Client:
    return _Client(
        {
            "event_instances": [{"id": INSTANCE_ID, "event_id": EVENT_ID}],
            "order_item_tickets": [{"order_item_id": ORDER_ITEM_ID, "instance_id": INSTANCE_ID}],
            "order_items": [{"id": ORDER_ITEM_ID, "order_id": ORDER_ID}],
            "orders": [
                {"id": ORDER_ID, "customer_id": BUYER_ID, "checkout_group_id": GROUP_ID}
            ],
            "payments": [
                {"checkout_group_id": GROUP_ID, "status": "success" if paid else "failed"}
            ],
            "tickets": (
                [{"holder_user_id": HOLDER_ID, "status": "issued", "instance_id": INSTANCE_ID}]
                if holder
                else []
            ),
            "audit_log": [],
            "notification_outbox": [],
        }
    )


def _rows(client: _Client, name: str) -> list[dict[str, Any]]:
    return client.tables[name].rows


def test_cancellation_flags_paid_order_and_notifies_buyer_and_holder() -> None:
    client = _seeded()
    result = process_event_cancellation(_Service(client), event_id=EVENT_ID, event_title="Jazz")

    flags = _rows(client, "audit_log")
    assert len(flags) == 1
    assert flags[0]["action"] == MASS_REFUND_FLAG_ACTION
    assert flags[0]["entity_id"] == ORDER_ID

    outbox = _rows(client, "notification_outbox")
    recipients = {row["payload"]["recipient_id"] for row in outbox}
    assert recipients == {BUYER_ID, HOLDER_ID}
    assert all(EVENT_CANCELLED_EVENT in row["dedupe_key"] for row in outbox)

    assert result.orders_flagged == 1
    assert result.recipients_notified == 2


def test_cancellation_is_idempotent_for_refund_flags() -> None:
    client = _seeded()
    process_event_cancellation(_Service(client), event_id=EVENT_ID, event_title="Jazz")
    second = process_event_cancellation(_Service(client), event_id=EVENT_ID, event_title="Jazz")
    # No duplicate admin refund flag on re-run.
    assert len(_rows(client, "audit_log")) == 1
    assert second.orders_flagged == 0


def test_cancellation_skips_unpaid_orders_but_still_notifies_holder() -> None:
    client = _seeded(paid=False)
    result = process_event_cancellation(_Service(client), event_id=EVENT_ID, event_title="Jazz")
    assert _rows(client, "audit_log") == []  # unpaid -> no refund to queue
    assert result.orders_flagged == 0
    # The attendee is still told the event is off.
    recipients = {row["payload"]["recipient_id"] for row in _rows(client, "notification_outbox")}
    assert recipients == {HOLDER_ID}
