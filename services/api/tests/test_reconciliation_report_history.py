"""Complete immutable stream reads under server caps and concurrent appends."""

from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest
from app.services.payments.reconciliation_reports import ReconciliationReportStore

DAY = date(2026, 9, 30)


class CappedQuery:
    def __init__(self, client: Any) -> None:
        self.client = client
        self.filters: list[tuple[str, str, Any]] = []
        self.desc = False
        self.maximum = 1000

    def select(self, _: str) -> "CappedQuery":
        return self

    def eq(self, field: str, value: Any) -> "CappedQuery":
        self.filters.append(("eq", field, value))
        return self

    def gt(self, field: str, value: Any) -> "CappedQuery":
        self.filters.append(("gt", field, value))
        return self

    def lte(self, field: str, value: Any) -> "CappedQuery":
        self.filters.append(("lte", field, value))
        return self

    def order(self, _: str, *, desc: bool = False) -> "CappedQuery":
        self.desc = desc
        return self

    def limit(self, value: int) -> "CappedQuery":
        self.maximum = value
        return self

    def execute(self) -> Any:
        rows = self.client.rows[:]
        for op, field, value in self.filters:
            rows = [
                row
                for row in rows
                if (
                    row[field] == value
                    if op == "eq"
                    else row[field] > value
                    if op == "gt"
                    else row[field] <= value
                )
            ]
        rows.sort(key=lambda row: row["version_number"], reverse=self.desc)
        result = rows[: min(self.maximum, self.client.cap)]
        if self.desc and self.client.append_after_snapshot:
            self.client.rows.append(row_for(self.client.count + 1))
            self.client.append_after_snapshot = False
        return SimpleNamespace(data=result)


def row_for(number: int, **changes: Any) -> dict[str, Any]:
    return {
        "id": str(number),
        "version_number": number,
        "provider_account_id": "account",
        "currency": "ZMW",
        "report_date": DAY.isoformat(),
        **changes,
    }


def store_for(count: int, cap: int, *, append: bool = False) -> tuple[Any, Any]:
    client = SimpleNamespace(
        rows=[row_for(i) for i in range(1, count + 1)],
        count=count,
        cap=cap,
        append_after_snapshot=append,
    )
    client.table = lambda _: CappedQuery(client)
    return ReconciliationReportStore(SimpleNamespace(client=client), runtime_role="admin"), client


@pytest.mark.parametrize("count,cap", [(0, 3), (3, 3), (6, 3), (7, 3), (1001, 1000)])
def test_history_reads_all_pages_including_newest(count: int, cap: int) -> None:
    store, client = store_for(count, cap)
    client.rows.extend(
        [row_for(9999, provider_account_id="foreign"), row_for(9999, currency="USD")]
    )
    result = store.versions(account_id="account", currency="ZMW", report_date=DAY)
    assert [row["version_number"] for row in result] == list(range(1, count + 1))


def test_concurrent_append_does_not_change_snapshot_history() -> None:
    store, client = store_for(6, 2, append=True)
    result = store.versions(account_id="account", currency="ZMW", report_date=DAY)
    assert [row["version_number"] for row in result] == list(range(1, 7))
    assert client.rows[-1]["version_number"] == 7


def test_missing_middle_version_is_rejected_instead_of_truncated() -> None:
    store, client = store_for(6, 2)
    client.rows = [row for row in client.rows if row["version_number"] != 3]
    with pytest.raises(RuntimeError, match="incomplete version history"):
        store.versions(account_id="account", currency="ZMW", report_date=DAY)
