"""Date-window helpers for event discovery (strategy §4.1)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

LUSAKA_TZ = ZoneInfo("Africa/Lusaka")

DateWindow = Literal["tonight", "this_weekend", "next_week", "next_month"]


def tonight_window(ref: datetime | None = None) -> tuple[datetime, datetime]:
    local = (ref or datetime.now(LUSAKA_TZ)).astimezone(LUSAKA_TZ)
    end = datetime.combine(local.date(), time(23, 59, 59, 999999), tzinfo=LUSAKA_TZ)
    return local, end


def weekend_window(ref: datetime | None = None) -> tuple[datetime, datetime]:
    local = (ref or datetime.now(LUSAKA_TZ)).astimezone(LUSAKA_TZ)
    weekday = local.weekday()
    days_to_friday = 4 - weekday
    friday = local.date() + timedelta(days=days_to_friday)
    sunday = friday + timedelta(days=2)
    start = datetime.combine(friday, time.min, tzinfo=LUSAKA_TZ)
    end = datetime.combine(sunday, time(23, 59, 59, 999999), tzinfo=LUSAKA_TZ)
    return start, end


def next_week_window(ref: datetime | None = None) -> tuple[datetime, datetime]:
    """Next Monday 00:00 through the following Sunday 23:59:59, Africa/Lusaka."""
    local = (ref or datetime.now(LUSAKA_TZ)).astimezone(LUSAKA_TZ)
    days_to_next_monday = 7 - local.weekday()
    monday = local.date() + timedelta(days=days_to_next_monday)
    sunday = monday + timedelta(days=6)
    start = datetime.combine(monday, time.min, tzinfo=LUSAKA_TZ)
    end = datetime.combine(sunday, time(23, 59, 59, 999999), tzinfo=LUSAKA_TZ)
    return start, end


def next_month_window(ref: datetime | None = None) -> tuple[datetime, datetime]:
    local = (ref or datetime.now(LUSAKA_TZ)).astimezone(LUSAKA_TZ)
    if local.month == 12:
        year, month = local.year + 1, 1
    else:
        year, month = local.year, local.month + 1
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = date(year, month + 1, 1) - timedelta(days=1)
    start = datetime.combine(start_date, time.min, tzinfo=LUSAKA_TZ)
    end = datetime.combine(end_date, time(23, 59, 59, 999999), tzinfo=LUSAKA_TZ)
    return start, end


def on_date_window(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=LUSAKA_TZ)
    end = datetime.combine(day, time(23, 59, 59, 999999), tzinfo=LUSAKA_TZ)
    return start, end


def window_bounds(
    window: DateWindow | None,
    *,
    on_date: date | None,
    ref: datetime,
) -> tuple[datetime, datetime] | None:
    if on_date is not None:
        return on_date_window(on_date)
    if window is None:
        return None
    if window == "tonight":
        return tonight_window(ref)
    if window == "this_weekend":
        return weekend_window(ref)
    if window == "next_week":
        return next_week_window(ref)
    return next_month_window(ref)


def instance_in_bounds(starts_at: datetime, bounds: tuple[datetime, datetime]) -> bool:
    local_start = starts_at.astimezone(LUSAKA_TZ)
    win_start, win_end = bounds
    return win_start <= local_start <= win_end
