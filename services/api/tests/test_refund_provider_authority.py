"""REFUND-PROVIDER-AUTHORITY — refund completes only after Lenco payout success."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from app.services.refunds.constants import AWAITING_PROVIDER_STATUSES
from app.services.refunds.execute import execute_refund
from app.services.refunds.state import (
    complete_refund_from_provider_payout,
    fail_refund_from_provider_payout,
    mark_refund_awaiting_payout,
)


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | None = None

    def select(self, _columns: str) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def order(self, column: str, *, desc: bool = False) -> FakeQuery:
        self._order = (column, desc)
        return self

    def limit(self, count: int) -> FakeQuery:
        self._limit = count
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self._pending_op = "update"
        self._payload = payload
        return self

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        self._pending_op = "insert"
        self._payload = payload
        return self

    def execute(self) -> Any:
        from unittest.mock import MagicMock

        if self._pending_op == "insert":
            assert self._payload is not None
            row = dict(self._payload)
            self._parent.rows.append(row)
            return MagicMock(data=[row])
        if self._pending_op == "update":
            assert self._payload is not None
            for row in self._parent.rows:
                if all(row.get(c) == v for op, c, v in self._filters if op == "eq"):
                    row.update(self._payload)
            return MagicMock(data=[])
        rows = list(self._parent.rows)
        for op, column, value in self._filters:
            if op == "eq":
                rows = [row for row in rows if row.get(column) == value]
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: row.get(column, ""), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=rows)


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str) -> FakeQuery:
        return FakeQuery(self, []).select(columns)

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).update(payload)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).insert(payload)


class FakeClient:
    def __init__(self) -> None:
        self.tables = {
            "refunds": FakeTable(),
            "audit_log": FakeTable(),
        }

    def table(self, name: str) -> FakeTable:
        return self.tables[name]


class FakeService:
    def __init__(self) -> None:
        self.client = FakeClient()


def test_mark_refund_awaiting_payout_is_idempotent() -> None:
    service = FakeService()
    refund_id = str(uuid.uuid4())
    payout_id = str(uuid.uuid4())
    service.client.tables["refunds"].rows.append(
        {
            "id": refund_id,
            "order_id": str(uuid.uuid4()),
            "status": "processing",
            "breakdown": {},
        }
    )

    mark_refund_awaiting_payout(
        service,
        refund_id=refund_id,
        payout_ref=payout_id,
        breakdown={"phase": "pre_release"},
    )
    mark_refund_awaiting_payout(
        service,
        refund_id=refund_id,
        payout_ref=payout_id,
        breakdown={"phase": "pre_release"},
    )

    row = service.client.tables["refunds"].rows[0]
    assert row["status"] == "awaiting_payout"
    assert row["payout_ref"] == payout_id
    assert len(service.client.tables["audit_log"].rows) == 1


def test_complete_refund_from_provider_payout_idempotent() -> None:
    service = FakeService()
    payout_id = str(uuid.uuid4())
    refund_id = str(uuid.uuid4())
    service.client.tables["refunds"].rows.append(
        {
            "id": refund_id,
            "order_id": str(uuid.uuid4()),
            "status": "awaiting_payout",
            "payout_ref": payout_id,
            "breakdown": {},
        }
    )

    assert complete_refund_from_provider_payout(service, payout_id=payout_id) is True
    assert complete_refund_from_provider_payout(service, payout_id=payout_id) is True
    assert service.client.tables["refunds"].rows[0]["status"] == "completed"


def test_fail_refund_from_provider_payout() -> None:
    service = FakeService()
    payout_id = str(uuid.uuid4())
    refund_id = str(uuid.uuid4())
    service.client.tables["refunds"].rows.append(
        {
            "id": refund_id,
            "order_id": str(uuid.uuid4()),
            "status": "awaiting_payout",
            "payout_ref": payout_id,
            "breakdown": {},
        }
    )

    assert fail_refund_from_provider_payout(
        service, payout_id=payout_id, reason="provider_failed"
    )
    assert service.client.tables["refunds"].rows[0]["status"] == "failed"


def test_active_statuses_include_awaiting_provider() -> None:
    assert "awaiting_payout" in AWAITING_PROVIDER_STATUSES


@pytest.mark.parametrize("status", sorted(AWAITING_PROVIDER_STATUSES))
def test_execute_returns_existing_awaiting_refund(status: str) -> None:
    from unittest.mock import MagicMock, patch

    from app.services.refunds.execute import RefundPhase

    service = MagicMock()
    existing = {
        "id": str(uuid.uuid4()),
        "order_id": str(uuid.uuid4()),
        "source_key": "refund-order-x",
        "lane": 1,
        "amount_ngwee": 1000,
        "status": status,
        "payout_ref": str(uuid.uuid4()),
        "breakdown": {"phase": RefundPhase.PRE_RELEASE.value},
    }
    with patch(
        "app.services.refunds.execute._find_existing_refund",
        return_value=existing,
    ):
        result = execute_refund(
            service_client=service,
            order_id=str(existing["order_id"]),
            lane=1,
            customer_momo="+260971234567",
        )
    assert result.created is False
    assert result.refund_id == existing["id"]
