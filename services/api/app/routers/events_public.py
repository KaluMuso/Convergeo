from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Annotated, Any, Literal, Protocol
from zoneinfo import ZoneInfo

from app.deps import get_supabase_client
from app.errors import AppError
from app.services.events.access import verify_access_code
from app.services.events.timing import instance_display_end
from app.services.events.type_policy import normalize_event_type
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/events", tags=["events"])

LUSAKA_TZ = ZoneInfo("Africa/Lusaka")

EVENT_CATEGORIES = (
    "workshops",
    "comedy-theatre",
    "pop-up-dinners",
    "cultural-arts",
    "lifestyle-community",
    "free-rsvp",
)

DateWindow = Literal["tonight", "this_weekend"]
EventCategory = Literal[
    "workshops",
    "comedy-theatre",
    "pop-up-dinners",
    "cultural-arts",
    "lifestyle-community",
    "free-rsvp",
]

SOLD_TICKET_STATUSES = frozenset({"issued", "checked_in"})


class _ServiceClient(Protocol):
    @property
    def client(self) -> Any: ...


class EventOrganiserResponse(BaseModel):
    id: str
    slug: str
    display_name: str
    preferred_badge: bool = False
    landmark: str | None = None
    logo_url: str | None = None
    description: str | None = None


class EventInstanceResponse(BaseModel):
    id: str
    starts_at: datetime
    # Effective end time: the instance's ends_at, or starts_at + default duration
    # when unset (always populated so clients need no fallback of their own).
    ends_at: datetime
    capacity: int
    spots_sold: int
    spots_remaining: int
    is_sold_out: bool


class PriceTierResponse(BaseModel):
    min_qty: int
    price_ngwee: int


class TicketTypeResponse(BaseModel):
    id: str
    kind: Literal["fixed", "tier", "free_rsvp"]
    name: str
    price_ngwee: int
    qty_cap: int | None = None
    tickets_sold: int = 0
    is_sold_out: bool = False
    is_free: bool = False
    # When true the buyer must name each attendee at purchase (M10-P11). Applies to
    # paid and free types alike; enforced server-side in the purchase path.
    attendee_named: bool = False
    # Optional discount config (M10-P12) so the buyer sees *why* the resolved price
    # is lower. The authoritative price is still resolved server-side at checkout.
    early_bird_price_ngwee: int | None = None
    early_bird_until: datetime | None = None
    tiers: list[PriceTierResponse] = Field(default_factory=list)


class EventBrowseItem(BaseModel):
    id: str
    slug: str
    title: str
    venue: str | None = None
    images: list[str] = Field(default_factory=list)
    category: str | None = None
    event_type: str = "standard"
    next_starts_at: datetime | None = None
    min_price_ngwee: int | None = None
    is_free: bool = False
    spots_sold: int = 0
    spots_total: int = 0
    is_sold_out: bool = False
    organiser: EventOrganiserResponse


class EventBrowseResponse(BaseModel):
    items: list[EventBrowseItem]
    total: int
    categories: list[str] = Field(default_factory=lambda: list(EVENT_CATEGORIES))
    calendar_dates: list[str] = Field(default_factory=list)


class EventDetailResponse(BaseModel):
    id: str
    slug: str
    title: str
    description: str | None = None
    venue: str | None = None
    lat: float | None = None
    lng: float | None = None
    landmark: str | None = None
    images: list[str] = Field(default_factory=list)
    category: str | None = None
    event_type: str = "standard"
    age_restriction: int | None = None
    instances: list[EventInstanceResponse] = Field(default_factory=list)
    ticket_types: list[TicketTypeResponse] = Field(default_factory=list)
    min_price_ngwee: int | None = None
    is_free: bool = False
    is_sold_out: bool = False
    organiser: EventOrganiserResponse


def parse_starts_at(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=ZoneInfo("UTC"))
        return value
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=ZoneInfo("UTC"))
        return parsed
    raise ValueError(f"Unsupported datetime value: {value!r}")


def _parse_ends_at(row: dict[str, Any]) -> datetime | None:
    """Parse an instance row's optional ends_at (NULL for pre-0035 rows)."""
    raw = row.get("ends_at")
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    return parse_starts_at(raw)


def tonight_window(ref: datetime | None = None) -> tuple[datetime, datetime]:
    """Return [start, end] for tonight in Africa/Lusaka (from ref through end of local day)."""
    local = (ref or datetime.now(LUSAKA_TZ)).astimezone(LUSAKA_TZ)
    start = local
    end = datetime.combine(local.date(), time(23, 59, 59, 999999), tzinfo=LUSAKA_TZ)
    return start, end


def weekend_window(ref: datetime | None = None) -> tuple[datetime, datetime]:
    """Return [start, end] for the current or upcoming Fri–Sun window in Africa/Lusaka."""
    local = (ref or datetime.now(LUSAKA_TZ)).astimezone(LUSAKA_TZ)
    weekday = local.weekday()  # Monday=0 … Sunday=6
    if weekday <= 3:
        days_to_friday = 4 - weekday
    else:
        days_to_friday = 4 - weekday
    friday = local.date() + timedelta(days=days_to_friday)
    sunday = friday + timedelta(days=2)
    start = datetime.combine(friday, time.min, tzinfo=LUSAKA_TZ)
    end = datetime.combine(sunday, time(23, 59, 59, 999999), tzinfo=LUSAKA_TZ)
    return start, end


def instance_in_window(starts_at: datetime, window: DateWindow, ref: datetime) -> bool:
    local_start = starts_at.astimezone(LUSAKA_TZ)
    if window == "tonight":
        win_start, win_end = tonight_window(ref)
    else:
        win_start, win_end = weekend_window(ref)
    return win_start <= local_start <= win_end


def order_instances(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: parse_starts_at(row["starts_at"]))


def _parse_images(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]


def _parse_organiser(vendor_row: dict[str, Any] | None) -> EventOrganiserResponse:
    if vendor_row is None:
        return EventOrganiserResponse(id="", slug="", display_name="")
    locations = vendor_row.get("vendor_locations")
    landmark: str | None = None
    if isinstance(locations, list) and locations:
        first = locations[0]
        if isinstance(first, dict):
            raw = first.get("landmark")
            if isinstance(raw, str) and raw.strip():
                landmark = raw.strip()
    return EventOrganiserResponse(
        id=str(vendor_row.get("id") or ""),
        slug=str(vendor_row.get("slug") or ""),
        display_name=str(vendor_row.get("display_name") or ""),
        preferred_badge=bool(vendor_row.get("preferred_badge")),
        landmark=landmark,
        logo_url=(str(vendor_row.get("logo_url")) if vendor_row.get("logo_url") else None),
        description=(
            str(vendor_row.get("description")) if vendor_row.get("description") else None
        ),
    )


def _ticket_counts_by_instance(ticket_rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in ticket_rows:
        status = str(row.get("status") or "")
        if status not in SOLD_TICKET_STATUSES:
            continue
        instance_id = row.get("instance_id")
        if instance_id is None:
            continue
        key = str(instance_id)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _ticket_counts_by_type(ticket_rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in ticket_rows:
        status = str(row.get("status") or "")
        if status not in SOLD_TICKET_STATUSES:
            continue
        ticket_type_id = row.get("ticket_type_id")
        if ticket_type_id is None:
            continue
        key = str(ticket_type_id)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _build_instance_response(
    row: dict[str, Any],
    *,
    spots_sold: int,
) -> EventInstanceResponse:
    capacity = int(row.get("capacity") or 0)
    remaining = max(capacity - spots_sold, 0)
    starts_at = parse_starts_at(row["starts_at"])
    return EventInstanceResponse(
        id=str(row["id"]),
        starts_at=starts_at,
        ends_at=instance_display_end(starts_at, _parse_ends_at(row)),
        capacity=capacity,
        spots_sold=spots_sold,
        spots_remaining=remaining,
        is_sold_out=capacity > 0 and spots_sold >= capacity,
    )


def _build_ticket_type_response(
    row: dict[str, Any],
    *,
    tickets_sold: int,
    tiers: list[dict[str, Any]] | None = None,
) -> TicketTypeResponse:
    tiers = tiers or []
    kind = str(row.get("kind") or "fixed")
    if kind not in {"fixed", "tier", "free_rsvp"}:
        kind = "fixed"
    price_ngwee = int(row.get("price_ngwee") or 0)
    qty_cap = row.get("qty_cap")
    qty_cap_int = int(qty_cap) if qty_cap is not None else None
    is_free = kind == "free_rsvp" or price_ngwee == 0
    is_sold_out = qty_cap_int is not None and tickets_sold >= qty_cap_int
    # Discounts are meaningless on a free type (and the write API forbids setting
    # them there), so only surface them for paid types.
    early_bird_price = row.get("early_bird_price_ngwee")
    early_bird_until = row.get("early_bird_until")
    return TicketTypeResponse(
        id=str(row["id"]),
        kind=kind,  # type: ignore[arg-type]
        name=str(row.get("name") or ""),
        price_ngwee=price_ngwee,
        qty_cap=qty_cap_int,
        tickets_sold=tickets_sold,
        is_sold_out=is_sold_out,
        is_free=is_free,
        attendee_named=bool(row.get("attendee_named", False)),
        early_bird_price_ngwee=(
            int(early_bird_price) if not is_free and early_bird_price is not None else None
        ),
        early_bird_until=early_bird_until if not is_free and early_bird_until else None,
        tiers=(
            []
            if is_free
            else [
                PriceTierResponse(
                    min_qty=int(tier["min_qty"]),
                    price_ngwee=int(tier["price_ngwee"]),
                )
                for tier in tiers
            ]
        ),
    )


def _event_is_free(ticket_type_rows: list[dict[str, Any]]) -> bool:
    if not ticket_type_rows:
        return False
    return all(
        str(row.get("kind") or "") == "free_rsvp" or int(row.get("price_ngwee") or 0) == 0
        for row in ticket_type_rows
    )


def _min_price_ngwee(ticket_type_rows: list[dict[str, Any]]) -> int | None:
    prices = [
        int(row["price_ngwee"])
        for row in ticket_type_rows
        if row.get("price_ngwee") is not None and int(row["price_ngwee"]) > 0
    ]
    if not prices:
        return None
    return min(prices)


def _matches_category(
    category: EventCategory | None,
    *,
    ticket_type_rows: list[dict[str, Any]],
    event_category: str | None,
) -> bool:
    if category is None:
        return True
    if category == "free-rsvp":
        return _event_is_free(ticket_type_rows)
    return event_category == category


def _upcoming_instances(
    instance_rows: list[dict[str, Any]],
    *,
    now: datetime,
) -> list[dict[str, Any]]:
    upcoming: list[dict[str, Any]] = []
    for row in instance_rows:
        starts_at = parse_starts_at(row["starts_at"])
        # Keep an instance until it ENDS, not when it starts — an in-progress
        # event should stay discoverable. ends_at falls back to starts_at + 2h.
        end = instance_display_end(starts_at, _parse_ends_at(row))
        if end >= now:
            upcoming.append(row)
    return order_instances(upcoming)


def _instance_is_sold_out(row: dict[str, Any], *, tickets_by_instance: dict[str, int]) -> bool:
    capacity = int(row.get("capacity") or 0)
    if capacity <= 0:
        return False
    sold = tickets_by_instance.get(str(row["id"]), 0)
    return sold >= capacity


def _ticket_types_sold_out(
    ticket_type_rows: list[dict[str, Any]],
    *,
    tickets_by_type: dict[str, int],
) -> bool:
    capped = [row for row in ticket_type_rows if row.get("qty_cap") is not None]
    if not capped:
        return False
    return all(
        tickets_by_type.get(str(row["id"]), 0) >= int(row["qty_cap"])
        for row in capped
    )


def _event_sold_out(
    instance_rows: list[dict[str, Any]],
    ticket_type_rows: list[dict[str, Any]],
    *,
    tickets_by_instance: dict[str, int],
    tickets_by_type: dict[str, int],
    only_upcoming: bool,
    now: datetime,
) -> bool:
    scoped_instances = (
        _upcoming_instances(instance_rows, now=now)
        if only_upcoming
        else order_instances(instance_rows)
    )
    if not scoped_instances:
        return False
    if all(
        _instance_is_sold_out(row, tickets_by_instance=tickets_by_instance)
        for row in scoped_instances
    ):
        return True
    return _ticket_types_sold_out(ticket_type_rows, tickets_by_type=tickets_by_type)


def _browse_item_sold_out(
    next_instance: dict[str, Any],
    ticket_type_rows: list[dict[str, Any]],
    *,
    tickets_by_instance: dict[str, int],
    tickets_by_type: dict[str, int],
) -> bool:
    if _instance_is_sold_out(next_instance, tickets_by_instance=tickets_by_instance):
        return True
    return _ticket_types_sold_out(ticket_type_rows, tickets_by_type=tickets_by_type)


def _fetch_published_events(client: Any) -> list[dict[str, Any]]:
    response = (
        client.table("events")
        .select(
            "id, slug, title, description, venue, lat, lng, images, status, "
            "category_slug, landmark, event_type, "
            "organiser_vendor_id, vendors!events_organiser_vendor_id_fkey("
            "id, slug, display_name, preferred_badge, logo_url, description, "
            "vendor_locations(landmark)"
            ")"
        )
        .eq("status", "published")
        # Browse shows only public events; unlisted/private are excluded here and
        # reachable only by direct slug (detail endpoint, access-gated).
        .eq("visibility", "public")
        .execute()
    )
    rows = response.data or []
    return [row for row in rows if isinstance(row, dict)]


def _fetch_event_by_slug(client: Any, slug: str) -> dict[str, Any] | None:
    response = (
        client.table("events")
        .select(
            "id, slug, title, description, venue, lat, lng, images, status, "
            "category_slug, landmark, event_type, visibility, access_code_hash, "
            "age_restriction, "
            "organiser_vendor_id, vendors!events_organiser_vendor_id_fkey("
            "id, slug, display_name, preferred_badge, logo_url, description, "
            "vendor_locations(landmark)"
            ")"
        )
        .eq("slug", slug)
        .eq("status", "published")
        # No visibility filter: unlisted (direct-link) and private (access-gated)
        # events are found here; access enforcement happens in build_detail_response.
        .maybe_single()
        .execute()
    )
    row = response.data
    return row if isinstance(row, dict) else None


def _fetch_instances(client: Any, event_ids: list[str]) -> list[dict[str, Any]]:
    if not event_ids:
        return []
    response = (
        client.table("event_instances")
        .select("id, event_id, starts_at, ends_at, capacity")
        .in_("event_id", event_ids)
        .order("starts_at")
        .execute()
    )
    return [row for row in (response.data or []) if isinstance(row, dict)]


def _fetch_ticket_types(client: Any, event_ids: list[str]) -> list[dict[str, Any]]:
    if not event_ids:
        return []
    response = (
        client.table("ticket_types")
        .select(
            "id, event_id, kind, name, price_ngwee, qty_cap, attendee_named, "
            "early_bird_price_ngwee, early_bird_until"
        )
        .in_("event_id", event_ids)
        .execute()
    )
    return [row for row in (response.data or []) if isinstance(row, dict)]


def _fetch_price_tiers(
    client: Any, ticket_type_ids: list[str]
) -> dict[str, list[dict[str, Any]]]:
    if not ticket_type_ids:
        return {}
    response = (
        client.table("ticket_type_price_tiers")
        .select("ticket_type_id, min_qty, price_ngwee")
        .in_("ticket_type_id", ticket_type_ids)
        .order("min_qty")
        .execute()
    )
    by_type: dict[str, list[dict[str, Any]]] = {}
    for row in response.data or []:
        if isinstance(row, dict) and row.get("ticket_type_id") is not None:
            by_type.setdefault(str(row["ticket_type_id"]), []).append(row)
    return by_type


def _fetch_tickets(client: Any, instance_ids: list[str]) -> list[dict[str, Any]]:
    if not instance_ids:
        return []
    response = (
        client.table("tickets")
        .select("id, instance_id, ticket_type_id, status")
        .in_("instance_id", instance_ids)
        .execute()
    )
    return [row for row in (response.data or []) if isinstance(row, dict)]


def build_browse_response(
    client: Any,
    *,
    date_window: DateWindow | None = None,
    category: EventCategory | None = None,
    ref: datetime | None = None,
) -> EventBrowseResponse:
    now = (ref or datetime.now(LUSAKA_TZ)).astimezone(ZoneInfo("UTC"))
    ref_lusaka = (ref or datetime.now(LUSAKA_TZ)).astimezone(LUSAKA_TZ)

    events = _fetch_published_events(client)
    event_ids = [str(row["id"]) for row in events if row.get("id")]
    instances = _fetch_instances(client, event_ids)
    ticket_types = _fetch_ticket_types(client, event_ids)
    instance_ids = [str(row["id"]) for row in instances if row.get("id")]
    tickets = _fetch_tickets(client, instance_ids)

    instances_by_event: dict[str, list[dict[str, Any]]] = {}
    for row in instances:
        event_id = str(row.get("event_id") or "")
        instances_by_event.setdefault(event_id, []).append(row)

    ticket_types_by_event: dict[str, list[dict[str, Any]]] = {}
    for row in ticket_types:
        event_id = str(row.get("event_id") or "")
        ticket_types_by_event.setdefault(event_id, []).append(row)

    tickets_by_instance = _ticket_counts_by_instance(tickets)
    tickets_by_type = _ticket_counts_by_type(tickets)

    items: list[EventBrowseItem] = []
    calendar_date_set: set[date] = set()

    for event in events:
        event_id = str(event["id"])
        event_instances = order_instances(instances_by_event.get(event_id, []))
        event_ticket_types = ticket_types_by_event.get(event_id, [])
        raw_category = event.get("category_slug")
        event_category: str | None = raw_category if isinstance(raw_category, str) else None

        if not _matches_category(
            category,
            ticket_type_rows=event_ticket_types,
            event_category=event_category,
        ):
            continue

        upcoming = _upcoming_instances(event_instances, now=now)
        if not upcoming:
            continue

        matching_instances = upcoming
        if date_window is not None:
            matching_instances = [
                row
                for row in upcoming
                if instance_in_window(parse_starts_at(row["starts_at"]), date_window, ref_lusaka)
            ]
            if not matching_instances:
                continue

        next_instance = matching_instances[0]
        next_starts_at = parse_starts_at(next_instance["starts_at"])
        calendar_date_set.add(next_starts_at.astimezone(LUSAKA_TZ).date())

        spots_sold = tickets_by_instance.get(str(next_instance["id"]), 0)
        spots_total = int(next_instance.get("capacity") or 0)
        vendor_raw = event.get("vendors")
        vendor_row = vendor_raw if isinstance(vendor_raw, dict) else None

        items.append(
            EventBrowseItem(
                id=event_id,
                slug=str(event.get("slug") or ""),
                title=str(event.get("title") or ""),
                venue=event.get("venue") if isinstance(event.get("venue"), str) else None,
                images=_parse_images(event.get("images")),
                category=event_category,
                event_type=normalize_event_type(event.get("event_type")),
                next_starts_at=next_starts_at,
                min_price_ngwee=_min_price_ngwee(event_ticket_types),
                is_free=_event_is_free(event_ticket_types),
                spots_sold=spots_sold,
                spots_total=spots_total,
                is_sold_out=_browse_item_sold_out(
                    next_instance,
                    event_ticket_types,
                    tickets_by_instance=tickets_by_instance,
                    tickets_by_type=tickets_by_type,
                ),
                organiser=_parse_organiser(vendor_row),
            )
        )

        for row in matching_instances:
            calendar_date_set.add(parse_starts_at(row["starts_at"]).astimezone(LUSAKA_TZ).date())

    items.sort(key=lambda item: item.next_starts_at or datetime.max.replace(tzinfo=ZoneInfo("UTC")))
    calendar_dates = sorted(day.isoformat() for day in calendar_date_set)

    return EventBrowseResponse(items=items, total=len(items), calendar_dates=calendar_dates)


def build_detail_response(
    client: Any, slug: str, *, access_code: str | None = None
) -> EventDetailResponse:
    event = _fetch_event_by_slug(client, slug)
    if event is None:
        raise AppError("event.not_found", "Event not found", 404)

    # Private events require a matching access code; without it we 404 rather
    # than reveal the event exists (a private event with no code set is likewise
    # unreachable, since verify_access_code returns False for a NULL hash).
    if str(event.get("visibility") or "public") == "private":
        stored_hash = event.get("access_code_hash")
        if not verify_access_code(
            access_code, stored_hash if isinstance(stored_hash, str) else None
        ):
            raise AppError("event.not_found", "Event not found", 404)

    event_id = str(event["id"])
    instances = order_instances(_fetch_instances(client, [event_id]))
    ticket_types = _fetch_ticket_types(client, [event_id])
    tiers_by_type = _fetch_price_tiers(
        client, [str(row["id"]) for row in ticket_types if row.get("id")]
    )
    tickets = _fetch_tickets(client, [str(row["id"]) for row in instances if row.get("id")])

    tickets_by_instance = _ticket_counts_by_instance(tickets)
    tickets_by_type = _ticket_counts_by_type(tickets)

    vendor_raw = event.get("vendors")
    vendor_row = vendor_raw if isinstance(vendor_raw, dict) else None
    organiser = _parse_organiser(vendor_row)
    # Prefer the event's own landmark (0036 column); fall back to the organiser's
    # vendor-location landmark.
    event_landmark = event.get("landmark")
    landmark = (
        event_landmark.strip()
        if isinstance(event_landmark, str) and event_landmark.strip()
        else organiser.landmark
    )
    raw_category = event.get("category_slug")
    category = raw_category if isinstance(raw_category, str) else None

    instance_responses = [
        _build_instance_response(row, spots_sold=tickets_by_instance.get(str(row["id"]), 0))
        for row in instances
    ]
    ticket_type_responses = [
        _build_ticket_type_response(
            row,
            tickets_sold=tickets_by_type.get(str(row["id"]), 0),
            tiers=tiers_by_type.get(str(row["id"]), []),
        )
        for row in ticket_types
    ]

    now = datetime.now(ZoneInfo("UTC"))
    age_restriction = event.get("age_restriction")
    return EventDetailResponse(
        id=event_id,
        slug=str(event.get("slug") or ""),
        title=str(event.get("title") or ""),
        description=event.get("description") if isinstance(event.get("description"), str) else None,
        venue=event.get("venue") if isinstance(event.get("venue"), str) else None,
        lat=float(event["lat"]) if event.get("lat") is not None else None,
        lng=float(event["lng"]) if event.get("lng") is not None else None,
        landmark=landmark,
        images=_parse_images(event.get("images")),
        category=category,
        event_type=normalize_event_type(event.get("event_type")),
        age_restriction=int(age_restriction) if age_restriction is not None else None,
        instances=instance_responses,
        ticket_types=ticket_type_responses,
        min_price_ngwee=_min_price_ngwee(ticket_types),
        is_free=_event_is_free(ticket_types),
        is_sold_out=_event_sold_out(
            instances,
            ticket_types,
            tickets_by_instance=tickets_by_instance,
            tickets_by_type=tickets_by_type,
            only_upcoming=True,
            now=now,
        ),
        organiser=organiser,
    )


@router.get("", response_model=EventBrowseResponse)
def list_events(
    supabase: Annotated[_ServiceClient, Depends(get_supabase_client)],
    date_window: Annotated[DateWindow | None, Query(alias="date_window")] = None,
    category: Annotated[EventCategory | None, Query()] = None,
) -> EventBrowseResponse:
    return build_browse_response(
        supabase.client,
        date_window=date_window,
        category=category,
    )


@router.get("/{slug}", response_model=EventDetailResponse)
def get_event(
    slug: str,
    supabase: Annotated[_ServiceClient, Depends(get_supabase_client)],
    access_code: Annotated[str | None, Query()] = None,
) -> EventDetailResponse:
    return build_detail_response(supabase.client, slug, access_code=access_code)
