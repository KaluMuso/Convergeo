from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
from typing import Any
from unittest.mock import patch

import pytest
from app.errors import AppError
from app.main import create_app
from app.routers.events_public import (
    LUSAKA_TZ,
    build_browse_response,
    build_detail_response,
    instance_in_window,
    order_instances,
    parse_starts_at,
    tonight_window,
    weekend_window,
)
from app.services.events.access import hash_access_code
from fastapi import FastAPI
from fastapi.testclient import TestClient

EVENT_A = "e1000000-0000-0000-0000-000000000001"
EVENT_B = "e1000000-0000-0000-0000-000000000002"
EVENT_PAST = "e1000000-0000-0000-0000-000000000003"
EVENT_FREE = "e1000000-0000-0000-0000-000000000004"
EVENT_SOLD = "e1000000-0000-0000-0000-000000000005"
VENDOR_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
INSTANCE_TONIGHT = "i1000000-0000-0000-0000-000000000001"
INSTANCE_WEEKEND = "i1000000-0000-0000-0000-000000000002"
INSTANCE_PAST = "i1000000-0000-0000-0000-000000000003"
INSTANCE_FREE = "i1000000-0000-0000-0000-000000000004"
INSTANCE_SOLD = "i1000000-0000-0000-0000-000000000005"
TICKET_GA = "t1000000-0000-0000-0000-000000000001"
TICKET_VIP = "t1000000-0000-0000-0000-000000000002"
TICKET_FREE = "t1000000-0000-0000-0000-000000000003"
TICKET_SOLD = "t1000000-0000-0000-0000-000000000004"


def _vendor_row(*, status: str = "active") -> dict[str, Any]:
    return {
        "id": VENDOR_A,
        "slug": "event-house",
        "display_name": "Event House Lusaka",
        "preferred_badge": True,
        "logo_url": "vendors/event-house-logo",
        "description": "Lusaka's premier events organiser.",
        "status": status,
        "vendor_locations": [{"landmark": "East Park Mall"}],
    }


def _event_row(
    *,
    event_id: str,
    slug: str,
    title: str,
    status: str = "published",
    visibility: str = "public",
    event_type: str = "standard",
    access_code_hash: str | None = None,
) -> dict[str, Any]:
    return {
        "id": event_id,
        "slug": slug,
        "title": title,
        "description": f"{title} description",
        "venue": "Lusaka Showgrounds",
        "lat": -15.4167,
        "lng": 28.2833,
        "images": ["events/sample"],
        "status": status,
        "visibility": visibility,
        "event_type": event_type,
        "access_code_hash": access_code_hash,
        "age_restriction": None,
        "organiser_vendor_id": VENDOR_A,
        "vendors": _vendor_row(),
    }


class FakeResponse:
    def __init__(self, data: Any) -> None:
        self.data = data


class FakeQuery:
    def __init__(self, store: FakeSupabaseStore, table: str) -> None:
        self.store = store
        self.table = table
        self._filters: list[tuple[str, str, Any]] = []
        self._order: tuple[str, bool] | None = None
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
        self._order = (column, desc)
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def execute(self) -> FakeResponse:
        rows = self.store.query(self.table, self._filters)
        if self._order:
            column, desc = self._order

            def sort_key(row: dict[str, Any]) -> str | int | float:
                value = row.get(column)
                if isinstance(value, (str, int, float)):
                    return value
                return ""

            rows = sorted(rows, key=sort_key, reverse=desc)
        if self._maybe_single:
            return FakeResponse(rows[0] if rows else None)
        return FakeResponse(rows)


class FakeSupabaseStore:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.event_instances: list[dict[str, Any]] = []
        self.ticket_types: list[dict[str, Any]] = []
        self.ticket_type_price_tiers: list[dict[str, Any]] = []
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


def _row_value(row: dict[str, Any], column: str) -> Any:
    """Resolve flat or dotted columns (e.g. vendors.status for !inner filters)."""
    if "." not in column:
        return row.get(column)
    current: Any = row
    for part in column.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def seed_store(store: FakeSupabaseStore) -> None:
    store.events = [
        _event_row(event_id=EVENT_A, slug="tonight-gig", title="Tonight Gig"),
        _event_row(event_id=EVENT_B, slug="weekend-market", title="Weekend Market"),
        _event_row(event_id=EVENT_PAST, slug="past-show", title="Past Show"),
        _event_row(event_id=EVENT_FREE, slug="free-meetup", title="Free Meetup"),
        _event_row(event_id=EVENT_SOLD, slug="sold-out-fest", title="Sold Out Fest"),
    ]
    store.event_instances = [
        {
            "id": INSTANCE_TONIGHT,
            "event_id": EVENT_A,
            "starts_at": "2026-07-09T20:00:00+02:00",
            "capacity": 100,
        },
        {
            "id": INSTANCE_WEEKEND,
            "event_id": EVENT_B,
            "starts_at": "2026-07-11T14:00:00+02:00",
            "capacity": 200,
        },
        {
            "id": INSTANCE_PAST,
            "event_id": EVENT_PAST,
            "starts_at": "2026-06-01T18:00:00+02:00",
            "capacity": 50,
        },
        {
            "id": INSTANCE_FREE,
            "event_id": EVENT_FREE,
            "starts_at": "2026-07-10T10:00:00+02:00",
            "capacity": 80,
        },
        {
            "id": INSTANCE_SOLD,
            "event_id": EVENT_SOLD,
            "starts_at": "2026-07-09T21:00:00+02:00",
            "capacity": 2,
        },
    ]
    store.ticket_types = [
        {
            "id": TICKET_GA,
            "event_id": EVENT_A,
            "kind": "fixed",
            "name": "General Admission",
            "price_ngwee": 50000,
            "qty_cap": 100,
        },
        {
            "id": TICKET_VIP,
            "event_id": EVENT_B,
            "kind": "tier",
            "name": "VIP",
            "price_ngwee": 150000,
            "qty_cap": 50,
        },
        {
            "id": TICKET_FREE,
            "event_id": EVENT_FREE,
            "kind": "free_rsvp",
            "name": "RSVP",
            "price_ngwee": 0,
            "qty_cap": 80,
        },
        {
            "id": TICKET_SOLD,
            "event_id": EVENT_SOLD,
            "kind": "fixed",
            "name": "Entry",
            "price_ngwee": 25000,
            "qty_cap": 2,
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


REF_THURSDAY = datetime(2026, 7, 9, 18, 0, tzinfo=LUSAKA_TZ)


@pytest.mark.parametrize(
    ("ref", "expected_start_day", "expected_end_day"),
    [
        (datetime(2026, 7, 9, 22, 30, tzinfo=LUSAKA_TZ), 9, 9),
        (datetime(2026, 7, 31, 23, 45, tzinfo=LUSAKA_TZ), 31, 31),
    ],
)
def test_tonight_window_respects_month_boundary(
    ref: datetime,
    expected_start_day: int,
    expected_end_day: int,
) -> None:
    start, end = tonight_window(ref)
    assert start.day == expected_start_day
    assert end.day == expected_end_day
    assert start.tzinfo == LUSAKA_TZ
    assert end.tzinfo == LUSAKA_TZ
    assert start <= end


def test_weekend_window_from_thursday_spans_into_next_month() -> None:
    ref = datetime(2026, 7, 30, 12, 0, tzinfo=LUSAKA_TZ)  # Thursday
    start, end = weekend_window(ref)
    assert start.date().isoformat() == "2026-07-31"
    assert end.date().isoformat() == "2026-08-02"


def test_weekend_window_on_saturday_uses_current_weekend() -> None:
    ref = datetime(2026, 8, 1, 9, 0, tzinfo=LUSAKA_TZ)  # Saturday
    start, end = weekend_window(ref)
    assert start.date().isoformat() == "2026-07-31"
    assert end.date().isoformat() == "2026-08-02"


def test_instance_in_window_tonight_across_boundary() -> None:
    ref = datetime(2026, 7, 31, 21, 0, tzinfo=LUSAKA_TZ)
    inside = parse_starts_at("2026-07-31T22:30:00+02:00")
    outside = parse_starts_at("2026-08-01T01:00:00+02:00")
    assert instance_in_window(inside, "tonight", ref) is True
    assert instance_in_window(outside, "tonight", ref) is False


def test_order_instances_sorts_ascending() -> None:
    rows = [
        {"id": "b", "starts_at": "2026-08-02T10:00:00+02:00"},
        {"id": "a", "starts_at": "2026-08-01T10:00:00+02:00"},
    ]
    ordered = order_instances(rows)
    assert [row["id"] for row in ordered] == ["a", "b"]


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


def test_browse_excludes_past_events(store: FakeSupabaseStore) -> None:
    response = build_browse_response(store, ref=REF_THURSDAY)
    slugs = {item.slug for item in response.items}
    assert "past-show" not in slugs


def test_browse_includes_in_progress_event(store: FakeSupabaseStore) -> None:
    # ends_at (0035) regression: an event that has STARTED but not yet ENDED must
    # stay discoverable. Before the fix the starts_at >= now filter dropped it.
    event_id = "0e000000-0000-0000-0000-0000000000aa"
    store.events.append(
        _event_row(event_id=event_id, slug="in-progress-gig", title="In Progress Gig")
    )
    store.event_instances.append(
        {
            "id": "0e000000-0000-0000-0000-0000000000ab",
            "event_id": event_id,
            "starts_at": "2026-07-09T17:00:00+02:00",  # 1h before REF_THURSDAY (18:00)
            "ends_at": "2026-07-09T21:00:00+02:00",  # still running at REF
            "capacity": 100,
        }
    )
    store.ticket_types.append(
        {
            "id": "0e000000-0000-0000-0000-0000000000ac",
            "event_id": event_id,
            "kind": "fixed",
            "name": "GA",
            "price_ngwee": 50000,
            "qty_cap": 100,
        }
    )
    response = build_browse_response(store, ref=REF_THURSDAY)
    assert "in-progress-gig" in {item.slug for item in response.items}
    # ends_at also flows through the detail projection.
    detail = build_detail_response(store, "in-progress-gig")
    assert detail.instances[0].ends_at == datetime.fromisoformat("2026-07-09T21:00:00+02:00")


def test_detail_surfaces_early_bird_and_group_tiers(store: FakeSupabaseStore) -> None:
    # A paid type carrying discount config exposes it on the detail projection so
    # the buyer can see why the resolved price is lower; a free type never does.
    event_id = "0e000000-0000-0000-0000-0000000000d0"
    type_id = "0e000000-0000-0000-0000-0000000000d1"
    store.events.append(_event_row(event_id=event_id, slug="discount-gig", title="Discount Gig"))
    store.event_instances.append(
        {
            "id": "0e000000-0000-0000-0000-0000000000d2",
            "event_id": event_id,
            "starts_at": "2026-07-09T20:00:00+02:00",
            "capacity": 100,
        }
    )
    store.ticket_types.append(
        {
            "id": type_id,
            "event_id": event_id,
            "kind": "fixed",
            "name": "General Admission",
            "price_ngwee": 50000,
            "qty_cap": 100,
            "early_bird_price_ngwee": 40000,
            "early_bird_until": "2026-07-01T00:00:00+00:00",
        }
    )
    store.ticket_type_price_tiers.extend(
        [
            {"ticket_type_id": type_id, "min_qty": 5, "price_ngwee": 42000},
            {"ticket_type_id": type_id, "min_qty": 2, "price_ngwee": 45000},
        ]
    )

    detail = build_detail_response(store, "discount-gig")
    ticket = detail.ticket_types[0]
    assert ticket.early_bird_price_ngwee == 40000
    assert ticket.early_bird_until == datetime.fromisoformat("2026-07-01T00:00:00+00:00")
    # Tiers surface ordered by min_qty ascending.
    assert [(tier.min_qty, tier.price_ngwee) for tier in ticket.tiers] == [(2, 45000), (5, 42000)]

    # A free RSVP type never carries discount config.
    free_detail = build_detail_response(store, "free-meetup")
    free_ticket = free_detail.ticket_types[0]
    assert free_ticket.early_bird_price_ngwee is None
    assert free_ticket.tiers == []


def test_detail_surfaces_attendee_named(store: FakeSupabaseStore) -> None:
    # The attendee_named flag reaches the buyer so the picker knows to collect a
    # name per ticket; it applies to paid and free types alike and defaults false.
    event_id = "0e000000-0000-0000-0000-0000000000e0"
    named_id = "0e000000-0000-0000-0000-0000000000e1"
    plain_id = "0e000000-0000-0000-0000-0000000000e2"
    store.events.append(_event_row(event_id=event_id, slug="named-gig", title="Named Gig"))
    store.event_instances.append(
        {
            "id": "0e000000-0000-0000-0000-0000000000e3",
            "event_id": event_id,
            "starts_at": "2026-07-09T20:00:00+02:00",
            "capacity": 100,
        }
    )
    store.ticket_types.extend(
        [
            {
                "id": named_id,
                "event_id": event_id,
                "kind": "free_rsvp",
                "name": "Workshop seat",
                "price_ngwee": 0,
                "attendee_named": True,
            },
            {
                "id": plain_id,
                "event_id": event_id,
                "kind": "fixed",
                "name": "General Admission",
                "price_ngwee": 50000,
            },
        ]
    )

    detail = build_detail_response(store, "named-gig")
    by_id = {ticket.id: ticket for ticket in detail.ticket_types}
    assert by_id[named_id].attendee_named is True
    assert by_id[plain_id].attendee_named is False


def test_browse_excludes_just_ended_event(store: FakeSupabaseStore) -> None:
    # Boundary: once ends_at passes, the event drops from discovery.
    event_id = "0e000000-0000-0000-0000-0000000000ba"
    store.events.append(
        _event_row(event_id=event_id, slug="just-ended-gig", title="Just Ended Gig")
    )
    store.event_instances.append(
        {
            "id": "0e000000-0000-0000-0000-0000000000bb",
            "event_id": event_id,
            "starts_at": "2026-07-09T14:00:00+02:00",
            "ends_at": "2026-07-09T17:30:00+02:00",  # ended 30m before REF (18:00)
            "capacity": 100,
        }
    )
    store.ticket_types.append(
        {
            "id": "0e000000-0000-0000-0000-0000000000bc",
            "event_id": event_id,
            "kind": "fixed",
            "name": "GA",
            "price_ngwee": 50000,
            "qty_cap": 100,
        }
    )
    response = build_browse_response(store, ref=REF_THURSDAY)
    assert "just-ended-gig" not in {item.slug for item in response.items}


def _append_categorised_event(
    store: FakeSupabaseStore,
    *,
    suffix: str,
    slug: str,
    title: str,
    category_slug: str,
    landmark: str | None = None,
) -> None:
    event_id = f"0e000000-0000-0000-0000-0000000000{suffix}"
    row = _event_row(event_id=event_id, slug=slug, title=title)
    row["category_slug"] = category_slug
    if landmark is not None:
        row["landmark"] = landmark
    store.events.append(row)
    store.event_instances.append(
        {
            "id": f"0e000000-0000-0000-0000-0000000001{suffix}",
            "event_id": event_id,
            "starts_at": "2026-07-11T14:00:00+02:00",
            "ends_at": "2026-07-11T17:00:00+02:00",
            "capacity": 20,
        }
    )
    store.ticket_types.append(
        {
            "id": f"0e000000-0000-0000-0000-0000000002{suffix}",
            "event_id": event_id,
            "kind": "fixed",
            "name": "GA",
            "price_ngwee": 30000,
            "qty_cap": 20,
        }
    )


def test_browse_filters_by_category_slug(store: FakeSupabaseStore) -> None:
    # D2 regression: category filtering reads events.category_slug. Before the fix
    # browse hardcoded category=None, so every non-free category filter returned
    # nothing.
    _append_categorised_event(
        store, suffix="ca", slug="pottery-workshop", title="Pottery", category_slug="workshops"
    )
    workshops = build_browse_response(store, category="workshops", ref=REF_THURSDAY)
    assert "pottery-workshop" in {i.slug for i in workshops.items}
    comedy = build_browse_response(store, category="comedy-theatre", ref=REF_THURSDAY)
    assert "pottery-workshop" not in {i.slug for i in comedy.items}


def test_detail_surfaces_category_and_event_landmark(store: FakeSupabaseStore) -> None:
    _append_categorised_event(
        store,
        suffix="da",
        slug="art-expo",
        title="Art Expo",
        category_slug="cultural-arts",
        landmark="Next to the National Museum",
    )
    detail = build_detail_response(store, "art-expo")
    assert detail.category == "cultural-arts"
    # Event-specific landmark wins over the organiser's vendor-location landmark.
    assert detail.landmark == "Next to the National Museum"


def test_browse_tonight_filter(store: FakeSupabaseStore) -> None:
    response = build_browse_response(store, date_window="tonight", ref=REF_THURSDAY)
    slugs = {item.slug for item in response.items}
    assert slugs == {"tonight-gig", "sold-out-fest"}


def test_browse_weekend_filter(store: FakeSupabaseStore) -> None:
    response = build_browse_response(store, date_window="this_weekend", ref=REF_THURSDAY)
    slugs = {item.slug for item in response.items}
    assert "weekend-market" in slugs
    assert "free-meetup" in slugs
    assert "tonight-gig" not in slugs


def test_browse_free_rsvp_category(store: FakeSupabaseStore) -> None:
    response = build_browse_response(store, category="free-rsvp", ref=REF_THURSDAY)
    assert len(response.items) == 1
    assert response.items[0].slug == "free-meetup"
    assert response.items[0].is_free is True


def test_browse_marks_sold_out(store: FakeSupabaseStore) -> None:
    response = build_browse_response(store, date_window="tonight", ref=REF_THURSDAY)
    sold = next(item for item in response.items if item.slug == "sold-out-fest")
    assert sold.is_sold_out is True


def test_detail_reachable_for_past_event(store: FakeSupabaseStore) -> None:
    detail = build_detail_response(store, "past-show")
    assert detail.slug == "past-show"
    assert len(detail.instances) == 1
    assert detail.instances[0].starts_at.isoformat().startswith("2026-06-01")


def test_detail_orders_instances_and_shows_free_rsvp(store: FakeSupabaseStore) -> None:
    store.event_instances.append(
        {
            "id": "i-later",
            "event_id": EVENT_FREE,
            "starts_at": "2026-07-12T10:00:00+02:00",
            "capacity": 80,
        }
    )
    detail = build_detail_response(store, "free-meetup")
    assert [instance.id for instance in detail.instances] == [INSTANCE_FREE, "i-later"]
    free_ticket = detail.ticket_types[0]
    assert free_ticket.kind == "free_rsvp"
    assert free_ticket.is_free is True
    assert free_ticket.price_ngwee == 0
    assert detail.is_free is True


class _FrozenDateTime(datetime):
    """Freezes `datetime.now()` to REF_THURSDAY so the route sees the same
    "now" as every other test in this file (which pass `ref=REF_THURSDAY`
    directly) — the live route has no `ref` override, so without this the
    fixture's fixed-calendar-date instances silently age into the past."""

    @classmethod
    def now(cls, tz: Any = None) -> _FrozenDateTime:
        frozen = REF_THURSDAY.astimezone(tz) if tz else REF_THURSDAY
        return cls.fromtimestamp(frozen.timestamp(), tz=frozen.tzinfo)


def test_list_events_endpoint(client: TestClient) -> None:
    with patch("app.routers.events_public.datetime", _FrozenDateTime):
        response = client.get("/events")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 1
    assert "categories" in payload


def test_get_event_endpoint(client: TestClient) -> None:
    response = client.get("/events/tonight-gig")
    assert response.status_code == 200
    payload = response.json()
    assert payload["slug"] == "tonight-gig"
    assert payload["organiser"]["display_name"] == "Event House Lusaka"
    assert payload["organiser"]["logo_url"] == "vendors/event-house-logo"
    assert payload["organiser"]["description"] == "Lusaka's premier events organiser."


def test_get_event_not_found(client: TestClient) -> None:
    response = client.get("/events/missing-event")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "event.not_found"


# --- Wave A / M10-P10: visibility gating + private-event access code ---------


def _add_event(
    store: FakeSupabaseStore,
    *,
    event_id: str,
    slug: str,
    visibility: str = "public",
    event_type: str = "standard",
    access_code_hash: str | None = None,
) -> None:
    store.events.append(
        _event_row(
            event_id=event_id,
            slug=slug,
            title=slug.replace("-", " ").title(),
            visibility=visibility,
            event_type=event_type,
            access_code_hash=access_code_hash,
        )
    )
    store.event_instances.append(
        {
            "id": f"i-{event_id}",
            "event_id": event_id,
            "starts_at": "2026-07-11T20:00:00+02:00",
            "capacity": 50,
        }
    )


def test_browse_excludes_unlisted_and_private(store: FakeSupabaseStore) -> None:
    _add_event(store, event_id="e-unlisted", slug="secret-unlisted", visibility="unlisted")
    _add_event(store, event_id="e-private", slug="secret-private", visibility="private")
    slugs = {item.slug for item in build_browse_response(store, ref=REF_THURSDAY).items}
    assert "secret-unlisted" not in slugs
    assert "secret-private" not in slugs


def test_detail_reachable_for_unlisted_by_slug(store: FakeSupabaseStore) -> None:
    _add_event(store, event_id="e-unlisted", slug="secret-unlisted", visibility="unlisted")
    detail = build_detail_response(store, "secret-unlisted")
    assert detail.slug == "secret-unlisted"


def test_detail_private_requires_matching_access_code(store: FakeSupabaseStore) -> None:
    _add_event(
        store,
        event_id="e-private",
        slug="secret-private",
        visibility="private",
        access_code_hash=hash_access_code("let-me-in"),
    )
    # No code → 404 (must not leak that the event exists).
    with pytest.raises(AppError) as no_code:
        build_detail_response(store, "secret-private")
    assert no_code.value.http_status == 404
    assert no_code.value.code == "event.not_found"
    # Wrong code → 404.
    with pytest.raises(AppError):
        build_detail_response(store, "secret-private", access_code="wrong")
    # Correct code → served.
    detail = build_detail_response(store, "secret-private", access_code="let-me-in")
    assert detail.slug == "secret-private"


def test_detail_private_without_code_set_is_unreachable(store: FakeSupabaseStore) -> None:
    _add_event(store, event_id="e-private2", slug="private-no-code", visibility="private")
    with pytest.raises(AppError):
        build_detail_response(store, "private-no-code", access_code="anything")


def test_detail_and_browse_surface_event_type(store: FakeSupabaseStore) -> None:
    _add_event(store, event_id="e-series", slug="weekly-series", event_type="recurring")
    detail = build_detail_response(store, "weekly-series")
    assert detail.event_type == "recurring"
    series = next(
        item for item in build_browse_response(store, ref=REF_THURSDAY).items
        if item.slug == "weekly-series"
    )
    assert series.event_type == "recurring"
