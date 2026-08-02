"""Evaluate a vendor location's opening hours (R02-P10).

``vendor_locations.hours`` has been stored since migration ``0002`` and returned
by the directory and catalog read paths ever since — but nothing has ever
*evaluated* it, so the product could show a customer a shop's hours without ever
being able to answer "is it open now?".

Shape, as established by the existing fixtures and seeds::

    {"mon": "09:00-17:00", "sat": "09:00-13:00"}

A day whose key is absent is **closed**. The column is nullable, and real rows
carry ``None``.

Two rules govern everything here:

* **Fail closed.** Anything unparseable — a missing day, a malformed span, a
  reversed range, junk in the JSON — resolves to *closed*, never to open. A
  customer sent to a shut shop across Lusaka on 3G data has been actively
  misled; a customer told "we don't know" has merely been under-served.
* **The server owns the clock.** The reference zone is Africa/Lusaka (UTC+2, no
  DST) and it comes from here, never from the caller's device. A phone with a
  wrong clock must not be able to change what the platform says is open.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any, Final
from zoneinfo import ZoneInfo

LUSAKA_TZ: Final = ZoneInfo("Africa/Lusaka")

#: Index 0 == Monday, matching ``datetime.weekday()``.
DAY_KEYS: Final[tuple[str, ...]] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _parse_hhmm(value: str) -> time | None:
    parts = value.strip().split(":")
    if len(parts) != 2:
        return None
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    # 24:00 is a legitimate way to write "closes at midnight".
    if hour == 24 and minute == 0:
        return time(23, 59, 59)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return time(hour, minute)


def parse_span(raw: Any) -> tuple[time, time] | None:
    """Parse ``"09:00-17:00"`` into a (open, close) pair, or None if unusable."""
    if not isinstance(raw, str):
        return None
    parts = raw.split("-")
    if len(parts) != 2:
        return None
    opens, closes = _parse_hhmm(parts[0]), _parse_hhmm(parts[1])
    if opens is None or closes is None:
        return None
    return opens, closes


def _span_for(hours: Any, day_index: int) -> tuple[time, time] | None:
    if not isinstance(hours, dict):
        return None
    return parse_span(hours.get(DAY_KEYS[day_index]))


def is_open_at(hours: Any, at: datetime, *, tz: ZoneInfo = LUSAKA_TZ) -> bool:
    """Is the location open at ``at``?

    ``at`` is converted into ``tz`` before comparison, so a UTC "now" and a
    local "now" give the same answer.

    A span whose close is at or before its open is read as running **overnight**
    into the following day (``"18:00-02:00"``), because that is what a Zambian
    bar or filling station actually means by it. The alternative reading — a
    zero-length or invalid window — would silently mark those vendors as never
    open.
    """
    local = at.astimezone(tz)
    today = local.weekday()
    now = local.time()

    span = _span_for(hours, today)
    if span is not None:
        opens, closes = span
        if opens < closes:
            if opens <= now < closes:
                return True
        elif opens > closes:
            # Overnight: open from `opens` until midnight today.
            if now >= opens:
                return True
        # opens == closes is a zero-length window: closed, not "all day".

    # Still open from yesterday's overnight span?
    yesterday = (today - 1) % 7
    span = _span_for(hours, yesterday)
    if span is not None:
        opens, closes = span
        if opens > closes and now < closes:
            return True

    return False


def next_open_at(
    hours: Any,
    at: datetime,
    *,
    tz: ZoneInfo = LUSAKA_TZ,
    horizon_days: int = 7,
) -> datetime | None:
    """When does this location next open, at or after ``at``?

    Returns ``None`` when it never opens within ``horizon_days`` — which is the
    honest answer for a vendor with no usable hours, and lets the UI say
    "hours not published" instead of inventing one.
    """
    local = at.astimezone(tz)

    for offset in range(horizon_days + 1):
        day = local.date() + timedelta(days=offset)
        span = _span_for(hours, day.weekday())
        if span is None:
            continue
        opens, _closes = span
        candidate = datetime.combine(day, opens, tzinfo=tz)
        if candidate >= local:
            return candidate
    return None
