"""Small, bounded RFC5545 recurrence materialiser for event instances.

The database stores concrete instances because availability, tickets and scanner
workflows must never depend on a client interpreting an RRULE. This parser
supports the launch rule set (DAILY, WEEKLY and MONTHLY with INTERVAL, COUNT,
UNTIL and BYDAY); unsupported clauses fail closed instead of silently creating
the wrong dates.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Iterator
from zoneinfo import ZoneInfo


_WEEKDAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
_ALLOWED_PARTS = frozenset({"FREQ", "INTERVAL", "COUNT", "UNTIL", "BYDAY"})
_MAX_OCCURRENCES = 366


class RecurrenceError(ValueError):
    """A supplied rule cannot be materialised safely."""


@dataclass(frozen=True, slots=True)
class ParsedRule:
    frequency: str
    interval: int
    count: int | None
    until: datetime | None
    byday: tuple[int, ...]


def parse_rrule(rule: str, *, timezone: str) -> ParsedRule:
    """Parse the supported deterministic RFC5545 subset."""
    raw_parts = [part.strip() for part in rule.strip().upper().split(";") if part.strip()]
    pairs: dict[str, str] = {}
    for part in raw_parts:
        if "=" not in part:
            raise RecurrenceError("each RRULE part must contain =")
        key, value = part.split("=", 1)
        if key not in _ALLOWED_PARTS or not value or key in pairs:
            raise RecurrenceError("unsupported or repeated RRULE part")
        pairs[key] = value
    frequency = pairs.get("FREQ", "")
    if frequency not in {"DAILY", "WEEKLY", "MONTHLY"}:
        raise RecurrenceError("FREQ must be DAILY, WEEKLY or MONTHLY")
    try:
        interval = int(pairs.get("INTERVAL", "1"))
        count = int(pairs["COUNT"]) if "COUNT" in pairs else None
    except ValueError as exc:
        raise RecurrenceError("INTERVAL and COUNT must be integers") from exc
    if interval < 1 or interval > 52 or (count is not None and not 1 <= count <= _MAX_OCCURRENCES):
        raise RecurrenceError("RRULE interval or count is outside the supported range")
    if count is not None and "UNTIL" in pairs:
        raise RecurrenceError("use COUNT or UNTIL, not both")

    try:
        tz = ZoneInfo(timezone)
    except Exception as exc:  # ZoneInfoNotFoundError is platform dependent.
        raise RecurrenceError("invalid recurrence timezone") from exc

    until: datetime | None = None
    if "UNTIL" in pairs:
        raw_until = pairs["UNTIL"]
        try:
            if len(raw_until) == 8:
                until = datetime.strptime(raw_until, "%Y%m%d").replace(
                    hour=23, minute=59, second=59, tzinfo=tz
                )
            elif raw_until.endswith("Z"):
                until = datetime.strptime(raw_until, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
            else:
                until = datetime.strptime(raw_until, "%Y%m%dT%H%M%S").replace(tzinfo=tz)
        except ValueError as exc:
            raise RecurrenceError("UNTIL must be RFC5545 basic date/time") from exc
    byday: tuple[int, ...] = ()
    if "BYDAY" in pairs:
        tokens = tuple(token.strip() for token in pairs["BYDAY"].split(",") if token.strip())
        if not tokens or any(token not in _WEEKDAYS for token in tokens):
            raise RecurrenceError("BYDAY must contain weekday codes such as MO,WE")
        byday = tuple(sorted({_WEEKDAYS[token] for token in tokens}))
    if byday and frequency != "WEEKLY":
        raise RecurrenceError("BYDAY is supported for WEEKLY rules only")
    return ParsedRule(frequency, interval, count, until, byday)


def recurrence_key(starts_at: datetime, timezone: str) -> str:
    local = starts_at.astimezone(ZoneInfo(timezone))
    return local.strftime("%Y%m%dT%H%M%S")


def _month_add(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def iter_occurrence_starts(
    seed: datetime,
    *,
    rule: ParsedRule,
    timezone: str,
    horizon_days: int,
) -> Iterator[datetime]:
    """Yield bounded UTC starts, including the explicit seed occurrence."""
    tz = ZoneInfo(timezone)
    local_seed = seed.astimezone(tz)
    limit = local_seed + timedelta(days=horizon_days)
    emitted = 0

    def include(candidate: datetime) -> bool:
        nonlocal emitted
        if candidate > limit:
            return False
        candidate_utc = candidate.astimezone(UTC)
        if rule.until is not None and candidate_utc > rule.until.astimezone(UTC):
            return False
        emitted += 1
        return rule.count is None or emitted <= rule.count

    if rule.frequency == "DAILY":
        step = 0
        while emitted < _MAX_OCCURRENCES:
            candidate = local_seed + timedelta(days=step * rule.interval)
            if not include(candidate):
                break
            yield candidate.astimezone(UTC)
            step += 1
        return

    if rule.frequency == "MONTHLY":
        step = 0
        while emitted < _MAX_OCCURRENCES:
            candidate = _month_add(local_seed, step * rule.interval)
            if not include(candidate):
                break
            yield candidate.astimezone(UTC)
            step += 1
        return

    # Weekly: scan local dates so BYDAY and daylight-saving transitions retain
    # the intended wall-clock time. Without BYDAY, the seed weekday repeats.
    days = rule.byday or (local_seed.weekday(),)
    candidate_date = local_seed.date()
    max_date = limit.date()
    while candidate_date <= max_date and emitted < _MAX_OCCURRENCES:
        weeks_since = (candidate_date - local_seed.date()).days // 7
        candidate = datetime(
            candidate_date.year,
            candidate_date.month,
            candidate_date.day,
            local_seed.hour,
            local_seed.minute,
            local_seed.second,
            local_seed.microsecond,
            tzinfo=tz,
        )
        if (
            candidate_date >= local_seed.date()
            and weeks_since >= 0
            and weeks_since % rule.interval == 0
            and candidate.weekday() in days
            and candidate >= local_seed
        ):
            if not include(candidate):
                break
            yield candidate.astimezone(UTC)
        candidate_date += timedelta(days=1)


def materialize_recurrence_instances(
    client: Any,
    *,
    event_id: str,
    seed_starts_at: datetime,
    seed_ends_at: datetime,
    capacity: int,
    rule: str,
    timezone: str,
    horizon_days: int,
    until: datetime | None = None,
) -> int:
    """Insert missing concrete occurrences, idempotently by recurrence_key."""
    parsed = parse_rrule(rule, timezone=timezone)
    if seed_ends_at <= seed_starts_at:
        raise RecurrenceError("seed end must be after seed start")
    duration = seed_ends_at - seed_starts_at
    existing_response = (
        client.table("event_instances")
        .select("recurrence_key")
        .eq("event_id", event_id)
        .execute()
    )
    existing = {
        str(row.get("recurrence_key"))
        for row in (getattr(existing_response, "data", None) or [])
        if isinstance(row, dict) and isinstance(row.get("recurrence_key"), str)
    }
    rows: list[dict[str, Any]] = []
    for start in iter_occurrence_starts(
        seed_starts_at,
        rule=parsed,
        timezone=timezone,
        horizon_days=horizon_days,
    ):
        if until is not None and start > until.astimezone(UTC):
            break
        key = recurrence_key(start, timezone)
        if key in existing:
            continue
        rows.append(
            {
                "event_id": event_id,
                "starts_at": start.isoformat(),
                "ends_at": (start + duration).isoformat(),
                "capacity": capacity,
                "recurrence_key": key,
                "status": "scheduled",
            }
        )
    if rows:
        client.table("event_instances").insert(rows).execute()
    return len(rows)
