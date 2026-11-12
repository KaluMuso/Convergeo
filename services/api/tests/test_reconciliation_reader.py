"""Protected PostgREST reader controls for F3 reconciliation."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest
from app.services.payments.reconciliation_matcher import MovementKind
from app.services.payments.reconciliation_reader import PostgrestReconciliationReader


class _Query:
    def __init__(
        self,
        rows: list[dict[str, Any]],
        *,
        ignore_range: bool = False,
    ) -> None:
        self._rows = rows
        self._filters: list[tuple[str, str, object]] = []
        self._order = "id"
        self._range = (0, len(rows))
        self._ignore_range = ignore_range

    def select(self, _columns: str) -> _Query:
        return self

    def eq(self, column: str, value: object) -> _Query:
        self._filters.append(("eq", column, value))
        return self

    def is_(self, column: str, value: object) -> _Query:
        self._filters.append(("is", column, value))
        return self

    def in_(self, column: str, value: object) -> _Query:
        self._filters.append(("in", column, value))
        return self

    def gte(self, column: str, value: object) -> _Query:
        self._filters.append(("gte", column, value))
        return self

    def lt(self, column: str, value: object) -> _Query:
        self._filters.append(("lt", column, value))
        return self

    def order(self, column: str) -> _Query:
        self._order = column
        return self

    def range(self, start: int, end: int) -> _Query:
        self._range = (start, end)
        return self

    def execute(self) -> SimpleNamespace:
        rows = list(self._rows)
        for operation, column, value in self._filters:
            if operation == "eq":
                rows = [row for row in rows if row.get(column) == value]
            elif operation == "is":
                rows = [row for row in rows if row.get(column) is None]
            elif operation == "in":
                assert isinstance(value, list)
                rows = [row for row in rows if row.get(column) in value]
            elif operation == "gte":
                rows = [row for row in rows if str(row.get(column)) >= str(value)]
            elif operation == "lt":
                rows = [row for row in rows if str(row.get(column)) < str(value)]
        rows.sort(key=lambda row: str(row.get(self._order, "")))
        if self._ignore_range:
            rows = rows[:1]
        else:
            start, end = self._range
            rows = rows[start : end + 1]
        return SimpleNamespace(data=rows)


class _Client:
    def __init__(
        self,
        tables: dict[str, list[dict[str, Any]]],
        *,
        repeat_table: str | None = None,
    ) -> None:
        self.tables = tables
        self.repeat_table = repeat_table

    def table(self, name: str) -> _Query:
        return _Query(
            self.tables.get(name, []),
            ignore_range=name == self.repeat_table,
        )


def _service(*, card: bool = False, repeat_table: str | None = None) -> SimpleNamespace:
    created_at = "2026-09-29T12:00:00+00:00"
    tables: dict[str, list[dict[str, Any]]] = {
        "ledger_accounts": [
            {"id": "cash", "kind": "platform_cash", "vendor_id": None}
        ],
        "ledger_transactions": [
            {
                "id": "ledger-1",
                "kind": "escrow_hold",
                "checkout_group_id": "checkout-1",
                "order_id": "order-1",
                "payment_id": "payment-1",
                "payout_id": None,
                "refund_id": None,
                "created_at": created_at,
            }
        ],
        "ledger_postings": [
            {
                "id": "posting-1",
                "transaction_id": "ledger-1",
                "account_id": "cash",
                "amount_ngwee": 30000,
                "created_at": created_at,
            }
        ],
        "payments": [
            {
                "id": "payment-1",
                "lenco_reference": "ord-1",
                "rail": "card" if card else "mtn",
                "raw": {},
                "status": "success",
            }
        ],
        "payment_collection_receipts": [
            {
                "payment_id": "payment-1",
                "receipt_identity": {
                    "merchant_reference": "ord-1",
                    "provider_reference": "lenco-1",
                    "obligation_id": "obligation-1",
                    "order_id": "order-1",
                    "leg": "balance",
                },
                "provider_reference": "lenco-1",
                "canonical_status_verified_at": None,
                "accepted_at": created_at,
            }
        ],
        "payment_collection_exceptions": [],
        "payouts": [
            {
                "id": "payout-pending",
                "amount_ngwee": 10000,
                "rail": "mtn",
                "lenco_reference": "pay-pending",
                "status": "processing",
                "resolve_snapshot": {"dispatch": {"state": "possibly_sent"}},
                "payout_kind": "vendor",
                "created_at": created_at,
            }
        ],
        "refunds": [],
    }
    return SimpleNamespace(client=_Client(tables, repeat_table=repeat_table))


def test_reader_uses_receipt_and_ledger_linkage_and_keeps_pending_separate() -> None:
    reader = PostgrestReconciliationReader(
        _service(),
        runtime_role="service_role",
        page_size=1,
    )

    evidence = reader.collect(report_date=date(2026, 9, 29))

    assert len(evidence.movements) == 1
    movement = evidence.movements[0]
    assert movement.kind == MovementKind.SERVICE_BALANCE
    assert movement.amount_ngwee == 30000
    assert movement.merchant_reference == "ord-1"
    assert movement.provider_reference == "lenco-1"
    assert movement.ledger_transaction_id == "ledger-1"
    assert movement.ledger_linkage_id == "payment-1"
    assert movement.obligation_id == "obligation-1"
    assert evidence.pending_transfers == (
        {
            "payout_id": "payout-pending",
            "payout_kind": "vendor",
            "status": "processing",
            "merchant_reference": "pay-pending",
            "provider_reference": None,
            "provider_status": None,
        },
    )
    assert evidence.terminal_transfers == ()
    assert evidence.unresolved == ()
    assert len(evidence.source_sha256) == 64


def test_card_without_canonical_verification_is_unresolved() -> None:
    reader = PostgrestReconciliationReader(
        _service(card=True),
        runtime_role="service_role",
    )

    evidence = reader.collect(report_date=date(2026, 9, 29))

    assert any("canonical verification" in issue for issue in evidence.unresolved)


def test_reader_rejects_non_service_role_and_repeated_postgrest_page() -> None:
    with pytest.raises(ValueError, match="service_role"):
        PostgrestReconciliationReader(_service(), runtime_role="authenticated")

    reader = PostgrestReconciliationReader(
        _service(repeat_table="ledger_transactions"),
        runtime_role="service_role",
        page_size=1,
    )
    with pytest.raises(RuntimeError, match="pagination repeated"):
        reader.collect(report_date=date(2026, 9, 29))
