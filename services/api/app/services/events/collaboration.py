"""Event collaboration: checklist model, readiness, state machine wrapper.

A vendor without organiser KYC proposes an event to run under a verified,
opted-in organiser. Statuses move ONLY through the database function
``public.event_collab_transition`` (guarded, audited); this module mirrors the
transition table so illegal moves are refused before a round-trip and so the
rules are unit-testable.

Money: ``revenue_share_bps`` is the co-host share of ticket revenue in integer
basis points (1% = 100); ticket prices are integer ngwee. Never floats.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Annotated, Any, Final, Literal, Protocol, cast

from app.errors import AppError
from app.schemas.base import NgweeInt, StrictModel
from postgrest.exceptions import APIError
from pydantic import Field, field_validator

STATUSES: Final = (
    "draft",
    "submitted",
    "changes_requested",
    "approved",
    "declined",
    "published",
)
Status = Literal["draft", "submitted", "changes_requested", "approved", "declined", "published"]
Action = Literal["submit", "approve", "decline", "request_changes", "publish"]

#: action -> (role allowed, statuses it may start from, resulting status)
TRANSITIONS: Final[dict[str, tuple[str, frozenset[str], str]]] = {
    "submit": ("proposer", frozenset({"draft", "changes_requested"}), "submitted"),
    "approve": ("organiser", frozenset({"submitted"}), "approved"),
    "decline": ("organiser", frozenset({"submitted"}), "declined"),
    "request_changes": ("organiser", frozenset({"submitted"}), "changes_requested"),
    "publish": ("organiser", frozenset({"approved"}), "published"),
}
EDITABLE_STATUSES: Final = frozenset({"draft", "changes_requested"})
MAX_BPS: Final = 10_000
EQUIPMENT_ITEMS: Final = ("sound", "stage", "power", "seating", "security")
READINESS_TOTAL: Final = 11  # venue, schedule, capacity, 5 equipment, permits, tiers, share

EquipmentState = Literal["ready", "needed", "not_needed"]
PermitState = Literal["obtained", "pending", "not_required"]


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class Venue(StrictModel):
    name: str | None = Field(default=None, max_length=200)
    landmark: str | None = Field(default=None, max_length=200)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)


def parse_instant(value: str) -> datetime:
    """Parse an ISO-8601 instant (naive values are treated as UTC)."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


class Schedule(StrictModel):
    # ISO-8601 strings: strict mode does not coerce str -> datetime from JSON bodies.
    starts_at: str | None = Field(default=None, max_length=40)
    ends_at: str | None = Field(default=None, max_length=40)

    @field_validator("starts_at", "ends_at")
    @classmethod
    def _iso(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                parse_instant(value)
            except ValueError as exc:
                msg = "must be an ISO-8601 date-time"
                raise ValueError(msg) from exc
        return value


class Capacity(StrictModel):
    capacity: int | None = Field(default=None, ge=1, le=1_000_000)


class Equipment(StrictModel):
    sound: EquipmentState | None = None
    stage: EquipmentState | None = None
    power: EquipmentState | None = None
    seating: EquipmentState | None = None
    security: EquipmentState | None = None


class Permits(StrictModel):
    status: PermitState | None = None
    note: str | None = Field(default=None, max_length=500)


class TicketTier(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    price_ngwee: NgweeInt
    qty_cap: int | None = Field(default=None, ge=1, le=1_000_000)


class Checklist(StrictModel):
    venue: Venue = Field(default_factory=Venue)
    schedule: Schedule = Field(default_factory=Schedule)
    capacity: Capacity = Field(default_factory=Capacity)
    equipment: Equipment = Field(default_factory=Equipment)
    permits: Permits = Field(default_factory=Permits)
    tiers: Annotated[list[TicketTier], Field(max_length=10)] = Field(default_factory=list)


class EventDraft(StrictModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    category: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=4000)
    city: str | None = Field(default=None, max_length=80)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def readiness_items(checklist: Checklist, revenue_share_bps: int | None) -> dict[str, bool]:
    """Which of the 11 readiness items are complete (single source for % and errors)."""
    v, s = checklist.venue, checklist.schedule
    items: dict[str, bool] = {
        "venue": bool(
            v.name
            and v.name.strip()
            and v.landmark
            and v.landmark.strip()
            and v.lat is not None
            and v.lng is not None
        ),
        "schedule": bool(
            s.starts_at is not None
            and s.ends_at is not None
            and parse_instant(s.ends_at) > parse_instant(s.starts_at)
        ),
        "capacity": checklist.capacity.capacity is not None,
    }
    for name in EQUIPMENT_ITEMS:
        items[f"equipment_{name}"] = getattr(checklist.equipment, name) in ("ready", "not_needed")
    items["permits"] = checklist.permits.status in ("obtained", "not_required")
    items["tiers"] = len(checklist.tiers) > 0
    items["revenue_share"] = revenue_share_bps is not None
    return items


def readiness_pct(checklist: Checklist, revenue_share_bps: int | None) -> int:
    items = readiness_items(checklist, revenue_share_bps)
    return round(100 * sum(items.values()) / READINESS_TOTAL)


def submit_field_errors(
    draft: EventDraft,
    checklist: Checklist,
    revenue_share_bps: int | None,
    *,
    now: datetime | None = None,
) -> list[dict[str, str]]:
    """Field-level problems that block SUBMIT.

    Equipment and permits must be ANSWERED (ready / needed / not needed;
    obtained / pending / not required) but need not be ready: the organiser
    sees the readiness percentage and decides.
    """
    errors: list[dict[str, str]] = []

    def add(field: str, code: str) -> None:
        errors.append({"field": field, "code": code})

    if not draft.title:
        add("event_draft.title", "required")
    if not draft.category:
        add("event_draft.category", "required")
    v = checklist.venue
    if not (v.name and v.name.strip()):
        add("checklist.venue.name", "required")
    if not (v.landmark and v.landmark.strip()):
        add("checklist.venue.landmark", "required")
    if v.lat is None or v.lng is None:
        add("checklist.venue.gps", "required")
    s = checklist.schedule
    if s.starts_at is None:
        add("checklist.schedule.starts_at", "required")
    elif parse_instant(s.starts_at) <= _aware(now or datetime.now(UTC)):
        add("checklist.schedule.starts_at", "must_be_future")
    if s.ends_at is None:
        add("checklist.schedule.ends_at", "required")
    elif s.starts_at is not None and parse_instant(s.ends_at) <= parse_instant(s.starts_at):
        add("checklist.schedule.ends_at", "must_be_after_start")
    if checklist.capacity.capacity is None:
        add("checklist.capacity.capacity", "required")
    for name in EQUIPMENT_ITEMS:
        if getattr(checklist.equipment, name) is None:
            add(f"checklist.equipment.{name}", "required")
    if checklist.permits.status is None:
        add("checklist.permits.status", "required")
    if not checklist.tiers:
        add("checklist.tiers", "required")
    else:
        cap = checklist.capacity.capacity
        for index, tier in enumerate(checklist.tiers):
            if cap is not None and tier.qty_cap is not None and tier.qty_cap > cap:
                add(f"checklist.tiers.{index}.qty_cap", "exceeds_capacity")
    if revenue_share_bps is None:
        add("revenue_share_bps", "required")
    return errors


def assert_submittable(
    draft: EventDraft,
    checklist: Checklist,
    revenue_share_bps: int | None,
    *,
    now: datetime | None = None,
) -> None:
    errors = submit_field_errors(draft, checklist, revenue_share_bps, now=now)
    if errors:
        raise AppError(
            code="checklist_incomplete",
            message="The readiness checklist is incomplete",
            http_status=422,
            details={
                "message_key": "vendor.events.collab.errors.checklistIncomplete",
                "fields": errors,
            },
        )


def assert_transition_allowed(action: str, *, role: str, status: str) -> str:
    """Python mirror of the SQL guard; returns the resulting status."""
    rule = TRANSITIONS.get(action)
    if rule is None:
        raise AppError(code="validation_error", message="Unknown action", http_status=422)
    need_role, from_statuses, to_status = rule
    if role != need_role:
        raise AppError(
            code="forbidden",
            message=f"Only the {need_role} can {action} this request",
            http_status=403,
            details={"message_key": "vendor.events.collab.errors.forbidden"},
        )
    if status not in from_statuses:
        raise AppError(
            code="invalid_transition",
            message=f"Cannot {action} a request that is {status}",
            http_status=409,
            details={
                "message_key": "vendor.events.collab.errors.invalidTransition",
                "from_status": status,
                "action": action,
            },
        )
    return to_status


_SQLSTATE_TO_ERROR: Final[dict[str, tuple[str, int, str]]] = {
    "42501": ("forbidden", 403, "vendor.events.collab.errors.forbidden"),
    "55000": ("invalid_transition", 409, "vendor.events.collab.errors.invalidTransition"),
    "22023": ("validation_error", 422, "vendor.events.collab.errors.invalidInput"),
    "P0002": ("not_found", 404, "vendor.events.collab.errors.notFound"),
    "23505": ("conflict", 409, "vendor.events.collab.errors.conflict"),
}


def map_rpc_error(exc: APIError) -> AppError:
    code = str(getattr(exc, "code", "") or "")
    mapped = _SQLSTATE_TO_ERROR.get(code)
    if mapped is None:
        return AppError(
            code="internal_error", message="Collaboration update failed", http_status=500
        )
    name, status, key = mapped
    return AppError(
        code=name,
        message=str(getattr(exc, "message", "") or name),
        http_status=status,
        details={"message_key": key},
    )


def call_transition(
    service_client: ServiceRoleClient,
    *,
    request_id: str,
    actor_user_id: str,
    action: str,
    reason: str | None = None,
    event_slug: str | None = None,
) -> dict[str, Any]:
    """Run the guarded transition RPC and return the updated request row."""
    params: dict[str, Any] = {
        "p_request_id": request_id,
        "p_actor_user_id": actor_user_id,
        "p_action": action,
        "p_reason": reason,
        "p_event_slug": event_slug,
    }
    try:
        response = service_client.client.rpc("event_collab_transition", params).execute()
    except APIError as exc:
        raise map_rpc_error(exc) from exc
    data = getattr(response, "data", None)
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return cast(dict[str, Any], data[0])
    if isinstance(data, dict):
        return cast(dict[str, Any], data)
    raise AppError(code="internal_error", message="Transition returned no row", http_status=500)


_SLUG_OK = re.compile(r"^[a-z0-9][a-z0-9-]{0,99}$")


def valid_event_slug(slug: str) -> bool:
    return bool(_SLUG_OK.fullmatch(slug))
