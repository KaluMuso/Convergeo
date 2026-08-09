"""Prohibited listing-attempt flag recording — dedupe + non-blocking failure."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

from app.services.moderation.prohibited_flags import (
    PROHIBITED_ATTEMPT_REASON,
    record_prohibited_listing_attempt,
)

VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
OWNER_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


class FakeQuery:
    def __init__(self, parent: FakeTable) -> None:
        self._parent = parent
        self._filters: list[tuple[str, str, Any]] = []
        self._limit: int | None = None
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | None = None
        self._raise_on_execute = parent.raise_on_execute

    def select(self, columns: str) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def limit(self, count: int) -> FakeQuery:
        self._limit = count
        return self

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        self._pending_op = "insert"
        self._payload = payload
        return self

    def execute(self) -> MagicMock:
        if self._raise_on_execute:
            raise RuntimeError("flags unavailable")
        if self._pending_op == "insert":
            assert isinstance(self._payload, dict)
            row = dict(self._payload)
            row.setdefault("id", str(uuid4()))
            self._parent.rows.append(row)
            return MagicMock(data=[row])
        rows = self._parent.rows
        for _, column, value in self._filters:
            rows = [row for row in rows if row.get(column) == value]
        if self._limit is not None:
            rows = rows[: self._limit]
        return MagicMock(data=rows)


class FakeTable:
    def __init__(self, *, raise_on_execute: bool = False) -> None:
        self.rows: list[dict[str, Any]] = []
        self.raise_on_execute = raise_on_execute

    def select(self, columns: str) -> FakeQuery:
        return FakeQuery(self).select(columns)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).insert(payload)


class FakeClient:
    def __init__(self, *, flags_down: bool = False) -> None:
        self.tables = {
            "flags": FakeTable(raise_on_execute=flags_down),
            "audit_log": FakeTable(),
        }

    def table(self, name: str) -> FakeTable:
        return self.tables[name]


def test_records_prohibited_attempt_with_context() -> None:
    client = FakeClient()
    wrote = record_prohibited_listing_attempt(
        client,
        vendor_id=VENDOR_ID,
        title="Selling weapons cheap",
        reason="keyword",
        matched="weapon",
        reporter_user_id=OWNER_ID,
    )
    assert wrote is True
    flag = client.tables["flags"].rows[0]
    assert flag["entity_type"] == "prohibited"
    assert flag["entity_id"] == VENDOR_ID
    assert flag["reporter_user_id"] == OWNER_ID
    assert flag["reason"].startswith(PROHIBITED_ATTEMPT_REASON)
    assert "weapon" in flag["reason"]
    audit = client.tables["audit_log"].rows[0]
    assert audit["action"] == "vendor.prohibited_listing_attempt"
    assert audit["after"]["matched"] == "weapon"
    assert audit["after"]["title"] == "Selling weapons cheap"


def test_dedupes_same_vendor_matched_term_within_window() -> None:
    client = FakeClient()
    first = record_prohibited_listing_attempt(
        client,
        vendor_id=VENDOR_ID,
        title="weapon kit",
        reason="keyword",
        matched="weapon",
        reporter_user_id=OWNER_ID,
    )
    second = record_prohibited_listing_attempt(
        client,
        vendor_id=VENDOR_ID,
        title="weapon kit again",
        reason="keyword",
        matched="weapon",
        reporter_user_id=OWNER_ID,
    )
    assert first is True
    assert second is False
    assert len(client.tables["flags"].rows) == 1


def test_different_matched_term_creates_separate_flag() -> None:
    client = FakeClient()
    record_prohibited_listing_attempt(
        client,
        vendor_id=VENDOR_ID,
        title="weapon",
        reason="keyword",
        matched="weapon",
        reporter_user_id=OWNER_ID,
    )
    wrote = record_prohibited_listing_attempt(
        client,
        vendor_id=VENDOR_ID,
        title="beer keg",
        reason="keyword",
        matched="beer",
        reporter_user_id=OWNER_ID,
    )
    assert wrote is True
    assert len(client.tables["flags"].rows) == 2


def test_skips_without_reporter() -> None:
    client = FakeClient()
    wrote = record_prohibited_listing_attempt(
        client,
        vendor_id=VENDOR_ID,
        title="weapon",
        reason="keyword",
        matched="weapon",
        reporter_user_id=None,
    )
    assert wrote is False
    assert client.tables["flags"].rows == []


def test_insert_failure_is_non_blocking() -> None:
    client = FakeClient(flags_down=True)
    wrote = record_prohibited_listing_attempt(
        client,
        vendor_id=VENDOR_ID,
        title="weapon",
        reason="keyword",
        matched="weapon",
        reporter_user_id=OWNER_ID,
    )
    assert wrote is False


def test_stale_open_flag_outside_window_allows_new() -> None:
    client = FakeClient()
    stale = (datetime.now(UTC) - timedelta(hours=48)).isoformat()
    client.tables["flags"].rows.append(
        {
            "id": str(uuid4()),
            "entity_type": "prohibited",
            "entity_id": VENDOR_ID,
            "reason": f"{PROHIBITED_ATTEMPT_REASON}:keyword:weapon",
            "reporter_user_id": OWNER_ID,
            "status": "open",
            "created_at": stale,
        }
    )
    wrote = record_prohibited_listing_attempt(
        client,
        vendor_id=VENDOR_ID,
        title="weapon",
        reason="keyword",
        matched="weapon",
        reporter_user_id=OWNER_ID,
    )
    assert wrote is True
    assert len(client.tables["flags"].rows) == 2
