"""REFUND-PROVIDER-AUTHORITY — refund completes only after Lenco payout success."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from app.services.db import SqlResult
from app.services.ledger.engine import LedgerError, PostedTransaction
from app.services.ledger.templates import AccountRef, LedgerTemplate, PostingLeg
from app.services.refunds import state as refund_state
from app.services.refunds.constants import AWAITING_PROVIDER_STATUSES
from app.services.refunds.execute import execute_refund
from app.services.refunds.state import (
    complete_refund_from_provider_payout,
    fail_refund_from_provider_payout,
    mark_refund_awaiting_payout,
    refund_reversal_idempotency_key,
    reverse_refund_ledger,
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


def test_fail_refund_from_provider_payout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(refund_state, "reverse_refund_ledger", lambda **_k: ["rev-1"])
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


# ---------------------------------------------------------------------------
# C5: definitive payout failure reverses the refund ledger posting
# ---------------------------------------------------------------------------


def _awaiting_refund(service: FakeService, *, status: str = "awaiting_payout") -> tuple[str, str]:
    payout_id = str(uuid.uuid4())
    refund_id = str(uuid.uuid4())
    service.client.tables["refunds"].rows.append(
        {
            "id": refund_id,
            "order_id": str(uuid.uuid4()),
            "status": status,
            "payout_ref": payout_id,
            "breakdown": {},
        }
    )
    return payout_id, refund_id


def test_definitive_failure_reverses_ledger_and_audits(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def _reverse(**kwargs: Any) -> list[str]:
        calls.append(kwargs)
        return ["rev-txn-1"]

    monkeypatch.setattr(refund_state, "reverse_refund_ledger", _reverse)
    service = FakeService()
    payout_id, refund_id = _awaiting_refund(service)

    assert fail_refund_from_provider_payout(
        service, payout_id=payout_id, reason="provider_failed", provider_status="failed"
    )

    assert len(calls) == 1 and calls[0]["refund_id"] == refund_id
    row = service.client.tables["refunds"].rows[0]
    assert row["status"] == "failed"
    assert row["breakdown"]["ledger_reversal_transaction_ids"] == ["rev-txn-1"]
    audit = service.client.tables["audit_log"].rows[-1]
    assert audit["after"]["ledger_reversal_transaction_ids"] == ["rev-txn-1"]


@pytest.mark.parametrize("reason", ["max_retry_attempts_exceeded", "ConnectTimeout()"])
def test_ambiguous_failure_does_not_reverse(
    monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    """Exhausted retries after send errors may have paid out — never auto-reverse."""

    def _boom(**_kwargs: Any) -> list[str]:
        raise AssertionError("ambiguous failure must not reverse the ledger")

    monkeypatch.setattr(refund_state, "reverse_refund_ledger", _boom)
    service = FakeService()
    payout_id, _refund_id = _awaiting_refund(service)

    assert fail_refund_from_provider_payout(
        service, payout_id=payout_id, reason=reason, dead_lettered=True
    )
    row = service.client.tables["refunds"].rows[0]
    assert row["status"] == "failed"
    assert row["breakdown"]["ledger_reversal"] == "manual_review_ambiguous_failure"


def test_reversal_failure_leaves_refund_awaiting(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(**_kwargs: Any) -> list[str]:
        raise LedgerError("ledger post failed")

    monkeypatch.setattr(refund_state, "reverse_refund_ledger", _boom)
    service = FakeService()
    payout_id, _refund_id = _awaiting_refund(service)

    with pytest.raises(LedgerError):
        fail_refund_from_provider_payout(service, payout_id=payout_id, reason="provider_failed")
    # Not FAILED-with-escrow-drained: still awaiting, so the next notice retries.
    assert service.client.tables["refunds"].rows[0]["status"] == "awaiting_payout"
    assert service.client.tables["audit_log"].rows == []


def test_repeat_failure_notice_reensures_reversal(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def _reverse(**kwargs: Any) -> list[str]:
        calls.append(kwargs["refund_id"])
        return ["rev"]

    monkeypatch.setattr(refund_state, "reverse_refund_ledger", _reverse)
    service = FakeService()
    payout_id, refund_id = _awaiting_refund(service, status="failed")

    assert fail_refund_from_provider_payout(service, payout_id=payout_id, reason="provider_failed")
    assert calls == [refund_id]
    assert service.client.tables["audit_log"].rows == []


def test_reverse_refund_ledger_negates_each_original_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vendor = str(uuid.uuid4())
    lane1_txn = str(uuid.uuid4())
    claw_txn = str(uuid.uuid4())
    rows = [
        f"{lane1_txn}|escrow||10000",
        f"{lane1_txn}|platform_cash||-10000",
        f"{claw_txn}|vendor_payable|{vendor}|2500",
        f"{claw_txn}|platform_cash||-2500",
    ]
    monkeypatch.setattr(refund_state, "run_sql_script", lambda _s: SqlResult(ok=True, rows=rows))
    posted: list[dict[str, Any]] = []

    def _post(**kwargs: Any) -> PostedTransaction:
        posted.append(kwargs)
        return PostedTransaction(
            id=f"rev-{len(posted)}", kind="refund_reversal",
            idempotency_key=kwargs["idempotency_key"], created=True,
        )

    monkeypatch.setattr(refund_state, "post_transaction", _post)
    refund_id = str(uuid.uuid4())
    ids = reverse_refund_ledger(refund_id=refund_id, order_id=None)

    assert ids == ["rev-1", "rev-2"]
    assert [p["idempotency_key"] for p in posted] == [
        refund_reversal_idempotency_key(lane1_txn),
        refund_reversal_idempotency_key(claw_txn),
    ]
    assert all(p["template"] == LedgerTemplate.REFUND_REVERSAL for p in posted)
    assert posted[0]["original_legs"] == (
        PostingLeg(AccountRef("escrow"), 10_000),
        PostingLeg(AccountRef("platform_cash"), -10_000),
    )
    assert posted[1]["original_legs"][0] == PostingLeg(AccountRef("vendor_payable", vendor), 2_500)


def test_reverse_refund_ledger_fails_closed_on_lookup_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        refund_state, "run_sql_script", lambda _s: SqlResult(ok=False, rows=[], error="down")
    )
    with pytest.raises(LedgerError):
        reverse_refund_ledger(refund_id=str(uuid.uuid4()), order_id=None)
