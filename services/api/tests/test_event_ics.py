from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import pytest
from app.main import create_app
from app.routers.event_ics import (
    build_event_ics,
    escape_ics_text,
    fold_ics_line,
    format_ics_datetime,
)
from app.routers.events_public import build_detail_response
from app.services.events.timing import DEFAULT_EVENT_DURATION
from fastapi import FastAPI
from fastapi.testclient import TestClient

EVENT_PAID = "e2000000-0000-0000-0000-000000000001"
EVENT_SOLD = "e2000000-0000-0000-0000-000000000002"
EVENT_MULTIDAY = "e2000000-0000-0000-0000-000000000003"
VENDOR = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
INSTANCE_PAID = "i2000000-0000-0000-0000-000000000001"
INSTANCE_SOLD = "i2000000-0000-0000-0000-000000000002"
INSTANCE_MULTIDAY = "i2000000-0000-0000-0000-000000000003"
TICKET_PAID = "t2000000-0000-0000-0000-000000000001"
TICKET_SOLD = "t2000000-0000-0000-0000-000000000002"
TICKET_MULTIDAY = "t2000000-0000-0000-0000-000000000003"


class FakeResponse:
    def __init__(self, data: Any) -> None:
        self.data = data


class FakeQuery:
    def __init__(self, store: FakeSupabaseStore, table: str) -> None:
        self.store = store
        self.table = table
        self._filters: list[tuple[str, str, Any]] = []
        self._maybe_single = False

    def select(self, columns: str, count: str | None = None) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._filters.append(("in", column, values))
        return self

    def order(self, column: str, desc: bool = False) -> FakeQuery:
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def execute(self) -> FakeResponse:
        rows = self.store.query(self.table, self._filters)
        if self._maybe_single:
            return FakeResponse(rows[0] if rows else None)
        return FakeResponse(rows)


def _row_value(row: dict[str, Any], column: str) -> Any:
    """Resolve dotted PostgREST filter paths (e.g. vendors.status) on nested embeds."""
    if "." not in column:
        return row.get(column)
    current: Any = row
    for part in column.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


class FakeSupabaseStore:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.event_instances: list[dict[str, Any]] = []
        self.ticket_types: list[dict[str, Any]] = []
        self.tickets: list[dict[str, Any]] = []

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self, name)

    def query(self, table: str, filters: list[tuple[str, str, Any]]) -> list[dict[str, Any]]:
        rows = getattr(self, table, []).copy()
        for op, column, value in filters:
            if op == "eq":
                rows = [row for row in rows if _row_value(row, column) == value]
            elif op == "in":
                rows = [row for row in rows if _row_value(row, column) in value]
        return rows


def _vendor_row() -> dict[str, Any]:
    return {
        "id": VENDOR,
        "slug": "event-house",
        "display_name": "Event House Lusaka",
        "preferred_badge": True,
        # D9 / 0058: public event detail requires organiser vendors.status=active.
        "status": "active",
        "vendor_locations": [{"landmark": "Opposite East Park Mall"}],
    }


def seed_store(store: FakeSupabaseStore) -> None:
    store.events = [
        {
            "id": EVENT_PAID,
            "slug": "jazz-night",
            "title": "Jazz, Wine & Cheese; Night",
            "description": "An evening of live jazz.\nDoors open at 18:00.",
            "venue": "Lusaka Playhouse",
            "lat": -15.4167,
            "lng": 28.2833,
            "images": ["events/jazz"],
            "status": "published",
            "visibility": "public",
            "organiser_vendor_id": VENDOR,
            "vendors": _vendor_row(),
        },
        {
            "id": EVENT_SOLD,
            "slug": "sold-out-fest",
            "title": "Sold Out Fest",
            "description": None,
            "venue": "Showgrounds",
            "lat": None,
            "lng": None,
            "images": [],
            "status": "published",
            "visibility": "public",
            "organiser_vendor_id": VENDOR,
            "vendors": _vendor_row(),
        },
        {
            "id": EVENT_MULTIDAY,
            "slug": "harvest-festival",
            "title": "Harvest Festival",
            "description": None,
            "venue": "Botanical Gardens",
            "lat": None,
            "lng": None,
            "images": [],
            "status": "published",
            "visibility": "public",
            "organiser_vendor_id": VENDOR,
            "vendors": _vendor_row(),
        },
    ]
    store.event_instances = [
        {
            "id": INSTANCE_PAID,
            "event_id": EVENT_PAID,
            "starts_at": "2026-09-12T20:00:00+02:00",
            "capacity": 100,
        },
        {
            "id": INSTANCE_SOLD,
            "event_id": EVENT_SOLD,
            "starts_at": "2026-09-13T21:00:00+02:00",
            "capacity": 2,
        },
        {
            # Multi-day event with an explicit end 2 days after the start.
            "id": INSTANCE_MULTIDAY,
            "event_id": EVENT_MULTIDAY,
            "starts_at": "2026-10-01T10:00:00+02:00",
            "ends_at": "2026-10-03T18:00:00+02:00",
            "capacity": 500,
        },
    ]
    store.ticket_types = [
        {
            "id": TICKET_PAID,
            "event_id": EVENT_PAID,
            "kind": "fixed",
            "name": "General Admission",
            "price_ngwee": 50000,
            "qty_cap": 100,
        },
        {
            "id": TICKET_SOLD,
            "event_id": EVENT_SOLD,
            "kind": "fixed",
            "name": "Entry",
            "price_ngwee": 25000,
            "qty_cap": 2,
        },
        {
            "id": TICKET_MULTIDAY,
            "event_id": EVENT_MULTIDAY,
            "kind": "fixed",
            "name": "Festival Pass",
            "price_ngwee": 150000,
            "qty_cap": 500,
        },
    ]
    store.tickets = [
        {
            "id": "tk-1",
            "instance_id": INSTANCE_SOLD,
            "ticket_type_id": TICKET_SOLD,
            "status": "issued",
        },
        {
            "id": "tk-2",
            "instance_id": INSTANCE_SOLD,
            "ticket_type_id": TICKET_SOLD,
            "status": "checked_in",
        },
    ]


@pytest.fixture
def store() -> FakeSupabaseStore:
    seeded = FakeSupabaseStore()
    seed_store(seeded)
    return seeded


@pytest.fixture
def client(store: FakeSupabaseStore) -> Generator[TestClient, None, None]:
    app: FastAPI = create_app()

    class FakeServiceClient:
        def __init__(self) -> None:
            self.client = store

    with patch("app.deps.get_supabase_service_client", return_value=FakeServiceClient()):
        with TestClient(app, raise_server_exceptions=False) as test_client:
            yield test_client


def unfold(ics: str) -> str:
    """Reverse RFC 5545 line folding so logical property lines can be asserted."""
    return ics.replace("\r\n ", "")


# ---- pure-function unit tests -------------------------------------------------


def test_escape_ics_text_escapes_special_chars() -> None:
    escaped = escape_ics_text("Jazz, Wine & Cheese; Night\nline two")
    assert escaped == "Jazz\\, Wine & Cheese\\; Night\\nline two"


def test_escape_ics_text_backslash_first() -> None:
    assert escape_ics_text("a\\b") == "a\\\\b"


def test_format_ics_datetime_is_utc_zulu() -> None:
    dt = datetime.fromisoformat("2026-09-12T20:00:00+02:00")
    assert format_ics_datetime(dt) == "20260912T180000Z"


def test_fold_ics_line_wraps_long_lines() -> None:
    line = "DESCRIPTION:" + "x" * 200
    folded = fold_ics_line(line)
    physical = folded.split("\r\n")
    assert len(physical) > 1
    assert all(len(part.encode("utf-8")) <= 75 for part in physical)
    # Continuation lines must start with a single space.
    assert all(part.startswith(" ") for part in physical[1:])


def test_build_event_ics_paid_event_structure(store: FakeSupabaseStore) -> None:
    event = build_detail_response(store, "jazz-night")
    now = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    ics = build_event_ics(event, now=now)
    logical = unfold(ics)

    assert ics.startswith("BEGIN:VCALENDAR\r\n")
    assert ics.endswith("END:VCALENDAR\r\n")
    assert "VERSION:2.0" in logical
    assert "PRODID:-//Vergeo5//Events//EN" in logical
    assert "BEGIN:VEVENT" in logical and "END:VEVENT" in logical
    assert f"UID:{EVENT_PAID}-{INSTANCE_PAID}@vergeo5.com" in logical
    assert "DTSTART:20260912T180000Z" in logical
    # 20:00 +02:00 start (= 18:00 UTC) + 2h default duration -> 20:00 UTC
    assert "DTEND:20260912T200000Z" in logical
    assert "DTSTAMP:20260801T120000Z" in logical
    assert "SUMMARY:Jazz\\, Wine & Cheese\\; Night" in logical
    assert "LOCATION:Lusaka Playhouse\\, Opposite East Park Mall" in logical
    assert "DESCRIPTION:An evening of live jazz.\\nDoors open at 18:00." in logical


def test_build_event_ics_dtend_uses_default_duration(store: FakeSupabaseStore) -> None:
    # Instance has no explicit ends_at -> DTEND falls back to start + 2h default.
    event = build_detail_response(store, "jazz-night")
    ics = build_event_ics(event, now=datetime(2026, 8, 1, tzinfo=UTC))
    start = event.instances[0].starts_at
    expected_end = format_ics_datetime(start + DEFAULT_EVENT_DURATION)
    assert f"DTEND:{expected_end}" in ics


def test_build_event_ics_dtend_honours_explicit_ends_at(store: FakeSupabaseStore) -> None:
    # Multi-day event with a real ends_at -> DTEND is the actual end, not start+2h.
    event = build_detail_response(store, "harvest-festival")
    ics = build_event_ics(event, now=datetime(2026, 8, 1, tzinfo=UTC))
    logical = unfold(ics)
    assert "DTSTART:20261001T080000Z" in logical  # 10:00 +02:00 -> 08:00 UTC
    # 18:00 +02:00 end on day 3 -> 16:00 UTC (spans 2 days, not a 2h default).
    assert "DTEND:20261003T160000Z" in logical


# ---- endpoint tests -----------------------------------------------------------


def test_calendar_ics_endpoint_returns_calendar(client: TestClient) -> None:
    response = client.get("/events/jazz-night/calendar.ics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/calendar")
    assert 'filename="jazz-night.ics"' in response.headers["content-disposition"]
    assert response.text.startswith("BEGIN:VCALENDAR")
    assert "BEGIN:VEVENT" in response.text


def test_calendar_ics_sold_out_event_still_downloadable(client: TestClient) -> None:
    response = client.get("/events/sold-out-fest/calendar.ics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/calendar")
    assert "BEGIN:VEVENT" in response.text
    assert f"UID:{EVENT_SOLD}-{INSTANCE_SOLD}@vergeo5.com" in unfold(response.text)


def test_calendar_ics_missing_event_returns_envelope(client: TestClient) -> None:
    response = client.get("/events/does-not-exist/calendar.ics")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "event.not_found"
