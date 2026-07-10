from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from app.deps import get_supabase_client
from app.main import create_app
from app.routers.vendor_order_queue import (
    OrderQueueItem,
    compute_takings_ngwee,
    compute_urgency,
    lusaka_day_bounds,
    sort_needs_action,
)
from fastapi.testclient import TestClient

USER_A_ID = "11111111-1111-1111-1111-111111111111"
VENDOR_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
ORDER_PLACED_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
ORDER_CONFIRMED_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
ORDER_LATE_ID = "ffffffff-ffff-ffff-ffff-ffffffffffff"
TOKEN_A = "vendor-a-token"


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | list[dict[str, Any]] | None = None
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._in_filter: tuple[str, list[Any]] | None = None

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        _ = count
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._in_filter = (column, list(values))
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

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        self._pending_op = "insert"
        self._payload = payload
        return self

    def execute(self) -> Any:
        if self._pending_op == "insert":
            assert isinstance(self._payload, dict)
            row = dict(self._payload)
            if "id" not in row:
                row["id"] = str(uuid4())
            self._parent.rows.append(row)
            return _magic(data=[row], count=None)

        rows = self._filtered_rows()
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: row.get(column, ""), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return _magic(data=rows[0] if rows else None, count=len(rows))
        return _magic(data=rows, count=len(rows))

    def _filtered_rows(self) -> list[dict[str, Any]]:
        rows = list(self._parent.rows)
        for op, column, value in self._filters:
            if op == "eq":
                rows = [row for row in rows if row.get(column) == value]
        if self._in_filter is not None:
            column, values = self._in_filter
            allowed = {str(value) for value in values}
            rows = [row for row in rows if str(row.get(column)) in allowed]
        return rows


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self, []).select(columns, count=count)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).insert(payload)


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "vendors": FakeTable(),
            "orders": FakeTable(),
            "order_items": FakeTable(),
            "order_events": FakeTable(),
        }

    def table(self, name: str) -> FakeTable:
        return self.tables[name]


def _magic(**kwargs: Any) -> Any:
    from unittest.mock import MagicMock

    return MagicMock(**kwargs)


def _seed_vendor(fake: FakeSupabaseClient) -> None:
    fake.tables["vendors"].rows.append(
        {
            "id": VENDOR_A_ID,
            "owner_user_id": USER_A_ID,
            "status": "active",
        }
    )


def _seed_orders(fake: FakeSupabaseClient) -> None:
    fake.tables["orders"].rows.extend(
        [
            {
                "id": ORDER_PLACED_ID,
                "vendor_id": VENDOR_A_ID,
                "status": "placed",
                "fulfilment": "delivery",
                "delivery_fee_ngwee": 1_000,
                "created_at": "2026-07-10T10:00:00+00:00",
            },
            {
                "id": ORDER_CONFIRMED_ID,
                "vendor_id": VENDOR_A_ID,
                "status": "confirmed",
                "fulfilment": "pickup",
                "delivery_fee_ngwee": 0,
                "created_at": "2026-07-10T08:00:00+00:00",
            },
            {
                "id": ORDER_LATE_ID,
                "vendor_id": VENDOR_A_ID,
                "status": "placed",
                "fulfilment": "delivery",
                "delivery_fee_ngwee": 500,
                "created_at": "2026-07-09T20:00:00+00:00",
            },
        ]
    )
    fake.tables["order_items"].rows.extend(
        [
            {
                "order_id": ORDER_PLACED_ID,
                "qty": 2,
                "unit_price_ngwee": 5_000,
                "title_snapshot": "Phone case",
            },
            {
                "order_id": ORDER_CONFIRMED_ID,
                "qty": 1,
                "unit_price_ngwee": 12_000,
                "title_snapshot": "Earbuds",
            },
            {
                "order_id": ORDER_LATE_ID,
                "qty": 1,
                "unit_price_ngwee": 8_000,
                "title_snapshot": "Charger",
            },
        ]
    )
    fake.tables["order_events"].rows.append(
        {
            "order_id": ORDER_CONFIRMED_ID,
            "to_status": "confirmed",
            "created_at": "2026-07-10T21:30:00+00:00",
        }
    )


@pytest.fixture
def queue_client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    fake = FakeSupabaseClient()
    _seed_vendor(fake)
    _seed_orders(fake)

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": USER_A_ID, "exp": 9_999_999_999},
    )
    monkeypatch.setattr(
        "app.core.auth._load_user_roles",
        lambda uid, service_client: frozenset({"vendor"}),
    )

    service_wrapper = MagicMock()
    service_wrapper.client = fake

    app = create_app()
    app.dependency_overrides[get_supabase_client] = lambda: service_wrapper
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN_A}"}


def test_lusaka_day_bounds_counts_late_evening_as_today() -> None:
    lusaka = ZoneInfo("Africa/Lusaka")
    # 2026-07-10 23:30 Lusaka = 2026-07-10 21:30 UTC
    now = datetime(2026, 7, 10, 21, 30, tzinfo=UTC)
    start, end = lusaka_day_bounds(now=now)
    event_at = datetime(2026, 7, 10, 21, 30, tzinfo=UTC)
    assert start <= event_at < end
    assert start.astimezone(lusaka).date().isoformat() == "2026-07-10"


def test_compute_takings_only_counts_confirmed_in_lusaka_day() -> None:
    day_start, day_end = lusaka_day_bounds(
        now=datetime(2026, 7, 10, 12, 0, tzinfo=UTC),
    )
    total = compute_takings_ngwee(
        confirmed_events=[
            {
                "order_id": ORDER_CONFIRMED_ID,
                "created_at": "2026-07-10T21:30:00+00:00",
            },
            {
                "order_id": ORDER_PLACED_ID,
                "created_at": "2026-07-10T22:00:00+00:00",
            },
        ],
        order_totals={
            ORDER_CONFIRMED_ID: 12_000,
            ORDER_PLACED_ID: 11_000,
        },
        day_start_utc=day_start,
        day_end_utc=day_end,
    )
    assert total == 12_000


def test_needs_action_sort_placed_before_confirmed_and_sla_first() -> None:
    now = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
    placed_recent = OrderQueueItem(
        id="recent-placed",
        status="placed",
        fulfilment="delivery",
        total_ngwee=1_000,
        item_count=1,
        preview_title="A",
        created_at="2026-07-10T11:30:00+00:00",
        available_actions=["confirm", "reject"],
        urgency=compute_urgency(
            status="placed",
            created_at=datetime(2026, 7, 10, 11, 30, tzinfo=UTC),
            now=now,
        ),
    )
    placed_overdue = OrderQueueItem(
        id="overdue-placed",
        status="placed",
        fulfilment="delivery",
        total_ngwee=2_000,
        item_count=1,
        preview_title="B",
        created_at="2026-07-10T06:00:00+00:00",
        available_actions=["confirm", "reject"],
        urgency=compute_urgency(
            status="placed",
            created_at=datetime(2026, 7, 10, 6, 0, tzinfo=UTC),
            now=now,
        ),
    )
    confirmed = OrderQueueItem(
        id="confirmed",
        status="confirmed",
        fulfilment="pickup",
        total_ngwee=3_000,
        item_count=1,
        preview_title="C",
        created_at="2026-07-10T05:00:00+00:00",
        available_actions=["pack"],
        urgency=compute_urgency(
            status="confirmed",
            created_at=datetime(2026, 7, 10, 5, 0, tzinfo=UTC),
            now=now,
        ),
    )

    ordered = sort_needs_action([confirmed, placed_recent, placed_overdue])
    assert [item.id for item in ordered] == [
        "overdue-placed",
        "recent-placed",
        "confirmed",
    ]


def test_dashboard_takings_and_needs_action(queue_client: TestClient) -> None:
    response = queue_client.get("/vendor/orders/dashboard", headers=_auth_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["takings_ngwee"] == 12_000
    assert body["needs_action"][0]["status"] == "placed"
    assert body["needs_action"][0]["id"] == ORDER_LATE_ID


def test_queue_filter_status(queue_client: TestClient) -> None:
    response = queue_client.get(
        "/vendor/orders/queue",
        params={"status": "confirmed"},
        headers=_auth_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == ORDER_CONFIRMED_ID
    assert body[0]["available_actions"] == ["reject", "pack"]
