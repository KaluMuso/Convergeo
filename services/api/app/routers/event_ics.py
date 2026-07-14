"""Public add-to-calendar (.ics) endpoint for events (M10-P09).

Serves an RFC-5545 VCALENDAR (one VEVENT per event instance) so shoppers can
import an event into Google/Apple/Outlook calendars. Read-only, public, and
downloadable even when the event is sold out. Reuses the existing event-detail
builder from ``events_public`` — no event data/schema change.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Annotated, Any, Protocol

from app.deps import get_supabase_client
from app.routers.events_public import EventDetailResponse, build_detail_response
from fastapi import APIRouter, Depends, Response

router = APIRouter(prefix="/events", tags=["events"])

# DTEND now comes from each instance's effective end time (EventInstanceResponse
# already coalesces a null ends_at to starts_at + the shared default duration).
ICS_PRODID = "-//Vergeo5//Events//EN"
_MAX_ICS_LINE_OCTETS = 75


class _ServiceClient(Protocol):
    @property
    def client(self) -> Any: ...


def _site_base_url() -> str:
    return os.environ.get("PUBLIC_SITE_URL", "https://vergeo5.com").rstrip("/")


def escape_ics_text(value: str) -> str:
    """Escape a TEXT value per RFC 5545 §3.3.11 (order matters: backslash first)."""
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def format_ics_datetime(value: datetime) -> str:
    """UTC form ``YYYYMMDDTHHMMSSZ`` (RFC 5545 §3.3.5 date-time, UTC)."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def fold_ics_line(line: str) -> str:
    """Fold a content line longer than 75 octets (RFC 5545 §3.1) using CRLF + space."""
    encoded = line.encode("utf-8")
    if len(encoded) <= _MAX_ICS_LINE_OCTETS:
        return line

    chunks: list[bytes] = []
    remaining = encoded
    limit = _MAX_ICS_LINE_OCTETS
    while len(remaining) > limit:
        # Avoid splitting a multi-byte UTF-8 sequence across a fold boundary.
        split = limit
        while split > 0 and (remaining[split] & 0xC0) == 0x80:
            split -= 1
        chunks.append(remaining[:split])
        remaining = remaining[split:]
        limit = _MAX_ICS_LINE_OCTETS - 1  # continuation lines are prefixed by one space
    chunks.append(remaining)
    return "\r\n ".join(chunk.decode("utf-8") for chunk in chunks)


def _location_text(event: EventDetailResponse) -> str | None:
    parts = [part for part in (event.venue, event.landmark) if part and part.strip()]
    if not parts:
        return None
    return ", ".join(part.strip() for part in parts)


def build_event_ics(event: EventDetailResponse, *, now: datetime) -> str:
    """Render an event (all instances) as an RFC-5545 VCALENDAR string."""
    dtstamp = format_ics_datetime(now)
    event_url = f"{_site_base_url()}/en/e/{event.slug}"
    location = _location_text(event)

    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{ICS_PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    for instance in event.instances:
        start = instance.starts_at
        end = instance.ends_at
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{event.id}-{instance.id}@vergeo5.com",
                f"DTSTAMP:{dtstamp}",
                f"DTSTART:{format_ics_datetime(start)}",
                f"DTEND:{format_ics_datetime(end)}",
                f"SUMMARY:{escape_ics_text(event.title)}",
            ]
        )
        if location:
            lines.append(f"LOCATION:{escape_ics_text(location)}")
        if event.description:
            lines.append(f"DESCRIPTION:{escape_ics_text(event.description)}")
        lines.append(f"URL:{escape_ics_text(event_url)}")
        lines.append("STATUS:CONFIRMED")
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(fold_ics_line(line) for line in lines) + "\r\n"


@router.get("/{slug}/calendar.ics")
def event_calendar_ics(
    slug: str,
    supabase: Annotated[_ServiceClient, Depends(get_supabase_client)],
) -> Response:
    """Public: download an event as an ``.ics`` file (sold-out events included)."""
    event = build_detail_response(supabase.client, slug)
    body = build_event_ics(event, now=datetime.now(UTC))
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{event.slug}.ics"'},
    )
