"""Regression tests for the notification outbox dedupe contract.

Two bugs are locked down here:

* ``enqueue_outbox_row`` must treat a UNIQUE(dedupe_key) collision as the idempotent
  no-op it documents ("Returns inserted row or None on collision") rather than letting
  the ``23505`` bubble up and 500 the surrounding request (e.g. an order status change).
* The order status-changed dedupe key must be qualified by the destination status so
  every transition of an order is its own outbox row, not just the first.
"""

from __future__ import annotations

from typing import Any

import pytest
from app.services.notifications.dedupe import build_dedupe_key, enqueue_outbox_row
from postgrest.exceptions import APIError


class _FakeInsert:
    def __init__(self, table: _FakeTable, row: dict[str, Any]) -> None:
        self._table = table
        self._row = row

    def execute(self) -> Any:
        for existing in self._table.rows:
            if existing["dedupe_key"] == self._row["dedupe_key"]:
                raise APIError(
                    {
                        "code": "23505",
                        "message": "duplicate key value violates unique constraint "
                        '"notification_outbox_dedupe_key_key"',
                    }
                )
        self._table.rows.append(self._row)
        return type("Resp", (), {"data": [self._row]})()


class _FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def insert(self, row: dict[str, Any]) -> _FakeInsert:
        return _FakeInsert(self, row)


class _FakeClient:
    def __init__(self) -> None:
        self._table = _FakeTable()

    def table(self, name: str) -> _FakeTable:
        assert name == "notification_outbox"
        return self._table


def _enqueue(client: _FakeClient, *, entity_id: str) -> Any:
    return enqueue_outbox_row(
        client,
        event_type="order-status-changed",
        entity_id=entity_id,
        channel="whatsapp",
        template="order_status_changed",
        payload={"order_id": entity_id},
    )


def test_first_enqueue_inserts_row() -> None:
    client = _FakeClient()
    row = _enqueue(client, entity_id="order-1:confirmed")
    assert row is not None
    assert row["dedupe_key"] == "order-status-changed:order-1:confirmed:whatsapp"


def test_collision_returns_none_and_does_not_raise() -> None:
    client = _FakeClient()
    _enqueue(client, entity_id="order-1:confirmed")
    # Re-enqueuing the identical (event, entity, channel) must NOT raise — the
    # duplicate is the documented idempotent no-op.
    duplicate = _enqueue(client, entity_id="order-1:confirmed")
    assert duplicate is None
    assert len(client._table.rows) == 1


def test_distinct_statuses_are_distinct_rows() -> None:
    client = _FakeClient()
    # Two different transitions of the same order must each enqueue their own row.
    _enqueue(client, entity_id="order-1:confirmed")
    _enqueue(client, entity_id="order-1:shipped")
    _enqueue(client, entity_id="order-1:delivered")
    assert len(client._table.rows) == 3
    keys = {r["dedupe_key"] for r in client._table.rows}
    assert keys == {
        "order-status-changed:order-1:confirmed:whatsapp",
        "order-status-changed:order-1:shipped:whatsapp",
        "order-status-changed:order-1:delivered:whatsapp",
    }


def test_non_unique_api_error_propagates() -> None:
    class _BoomTable(_FakeTable):
        def insert(self, row: dict[str, Any]) -> Any:
            class _Boom:
                def execute(self_inner) -> Any:
                    raise APIError({"code": "42501", "message": "permission denied"})

            return _Boom()

    class _BoomClient(_FakeClient):
        def __init__(self) -> None:
            self._table = _BoomTable()

    with pytest.raises(APIError):
        _enqueue(_BoomClient(), entity_id="order-1:confirmed")


def test_build_dedupe_key_shape() -> None:
    assert (
        build_dedupe_key("order-status-changed", "order-1:confirmed", "whatsapp")
        == "order-status-changed:order-1:confirmed:whatsapp"
    )
