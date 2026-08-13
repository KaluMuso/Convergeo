from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.events.access import hash_access_code
from app.services.events.cancellation import process_event_cancellation
from app.services.events.recurrence import RecurrenceError, materialize_recurrence_instances
from app.services.events.type_policy import (
    VISIBILITIES,
    EventType,
    Visibility,
    normalize_event_type,
    policy_for,
)
from app.services.kyc.state_machine import ServiceRoleClient
from app.services.notifications.events import emit_event
from fastapi import APIRouter, Depends
from pydantic import Field, field_validator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/organiser/events", tags=["organiser-events"])

EVENT_CATEGORIES = (
    "workshops",
    "comedy-theatre",
    "pop-up-dinners",
    "cultural-arts",
    "lifestyle-community",
    "free-rsvp",
)

EventCategory = Literal[
    "workshops",
    "comedy-theatre",
    "pop-up-dinners",
    "cultural-arts",
    "lifestyle-community",
    "free-rsvp",
]

EventStatus = Literal["draft", "published", "cancelled", "completed"]
PlatformFeePayer = Literal["organiser", "buyer"]
EDITABLE_STATUSES = frozenset({"draft", "published"})
SOLD_TICKET_STATUSES = frozenset({"issued", "checked_in"})
MAX_EVENT_IMAGES = 8
_SCHEDULE_CHANGE_EVENT = "event_schedule_changed"


class EventInstanceInput(StrictModel):
    id: str | None = None
    starts_at: str
    ends_at: str | None = None
    capacity: int = Field(ge=0)

    @field_validator("starts_at")
    @classmethod
    def validate_starts_at(cls, value: str) -> str:
        _parse_starts_at(value)
        return value

    @field_validator("ends_at")
    @classmethod
    def validate_ends_at(cls, value: str | None) -> str | None:
        if value is not None:
            _parse_starts_at(value)
        return value


class EventInstanceResponse(StrictModel):
    id: str
    starts_at: datetime
    ends_at: datetime | None = None
    capacity: int
    tickets_sold: int = 0


class EventCreateRequest(StrictModel):
    title: str = Field(min_length=2, max_length=200)
    category: EventCategory
    description: str | None = None
    venue: str | None = None
    lat: float | None = None
    lng: float | None = None
    landmark: str | None = None
    # Wave A (D29): classification, visibility & policy. All optional/defaulted
    # so existing clients keep working unchanged.
    event_type: EventType = "standard"
    visibility: Visibility | None = None
    access_code: str | None = Field(default=None, max_length=64)
    recurrence_rule: str | None = Field(default=None, max_length=1024)
    recurrence_timezone: str | None = Field(default=None, max_length=64)
    recurrence_until: str | None = Field(default=None, max_length=64)
    recurrence_horizon_days: int | None = Field(default=None, ge=14, le=366)
    platform_fee_payer: PlatformFeePayer = "organiser"
    refund_policy_key: str | None = Field(default=None, max_length=64)
    age_restriction: int | None = Field(default=None, ge=0, le=120)
    terms: str | None = Field(default=None, max_length=4000)
    images: list[str] = Field(default_factory=list, max_length=MAX_EVENT_IMAGES)
    instances: list[EventInstanceInput] = Field(min_length=1)

    @field_validator("images")
    @classmethod
    def validate_images(cls, images: list[str]) -> list[str]:
        cleaned = [item.strip() for item in images if item.strip()]
        if len(cleaned) > MAX_EVENT_IMAGES:
            msg = f"At most {MAX_EVENT_IMAGES} images are allowed"
            raise ValueError(msg)
        return cleaned


class EventUpdateRequest(StrictModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    category: EventCategory | None = None
    description: str | None = None
    venue: str | None = None
    lat: float | None = None
    lng: float | None = None
    landmark: str | None = None
    event_type: EventType | None = None
    visibility: Visibility | None = None
    access_code: str | None = Field(default=None, max_length=64)
    recurrence_rule: str | None = Field(default=None, max_length=1024)
    recurrence_timezone: str | None = Field(default=None, max_length=64)
    recurrence_until: str | None = Field(default=None, max_length=64)
    recurrence_horizon_days: int | None = Field(default=None, ge=14, le=366)
    platform_fee_payer: PlatformFeePayer | None = None
    refund_policy_key: str | None = Field(default=None, max_length=64)
    age_restriction: int | None = Field(default=None, ge=0, le=120)
    terms: str | None = Field(default=None, max_length=4000)
    images: list[str] | None = Field(default=None, max_length=MAX_EVENT_IMAGES)
    instances: list[EventInstanceInput] | None = None

    @field_validator("images")
    @classmethod
    def validate_images(cls, images: list[str] | None) -> list[str] | None:
        if images is None:
            return None
        cleaned = [item.strip() for item in images if item.strip()]
        if len(cleaned) > MAX_EVENT_IMAGES:
            msg = f"At most {MAX_EVENT_IMAGES} images are allowed"
            raise ValueError(msg)
        return cleaned


class EventSummary(StrictModel):
    id: str
    title: str
    slug: str
    status: EventStatus
    category: EventCategory | None = None
    event_type: EventType = "standard"
    visibility: Visibility = "public"
    recurrence_rule: str | None = None
    recurrence_timezone: str | None = None
    recurrence_until: datetime | None = None
    platform_fee_payer: PlatformFeePayer = "organiser"
    venue: str | None = None
    landmark: str | None = None
    images: list[str] = Field(default_factory=list)
    next_starts_at: datetime | None = None
    instance_count: int = 0
    tickets_sold: int = 0


class EventDetailResponse(StrictModel):
    id: str
    title: str
    slug: str
    status: EventStatus
    category: EventCategory | None = None
    event_type: EventType = "standard"
    visibility: Visibility = "public"
    has_access_code: bool = False
    recurrence_rule: str | None = None
    recurrence_timezone: str | None = None
    recurrence_until: datetime | None = None
    recurrence_horizon_days: int = 90
    platform_fee_payer: PlatformFeePayer = "organiser"
    refund_policy_key: str | None = None
    age_restriction: int | None = None
    terms: str | None = None
    description: str | None = None
    venue: str | None = None
    lat: float | None = None
    lng: float | None = None
    landmark: str | None = None
    images: list[str] = Field(default_factory=list)
    instances: list[EventInstanceResponse] = Field(default_factory=list)
    tickets_sold: int = 0


class EventListResponse(StrictModel):
    items: list[EventSummary]


class EventMutationResponse(StrictModel):
    event: EventDetailResponse


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def _parse_starts_at(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed
    raise ValueError(f"Unsupported datetime value: {value!r}")


def _instance_ends_at(row: dict[str, Any]) -> datetime | None:
    """Parse an instance row's optional ends_at (NULL for pre-0035 rows)."""
    raw = row.get("ends_at")
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    return _parse_starts_at(raw)


def _instance_write_payload(
    event_id: str,
    instance: EventInstanceInput,
    *,
    recurrence_key: str | None = None,
) -> dict[str, Any]:
    """DB payload for an instance insert/update.

    ends_at is included only when supplied. On update this preserves any existing
    end time when a (still-optional) client omits the field, rather than wiping it.
    """
    payload: dict[str, Any] = {
        "event_id": event_id,
        "starts_at": _parse_starts_at(instance.starts_at).astimezone(UTC).isoformat(),
        "capacity": instance.capacity,
    }
    if instance.ends_at is not None:
        payload["ends_at"] = _parse_starts_at(instance.ends_at).astimezone(UTC).isoformat()
    if recurrence_key is not None:
        payload["recurrence_key"] = recurrence_key
    return payload


def _slugify(title: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", title.lower())
    slug = re.sub(r"[-\s]+", "-", slug).strip("-")
    return slug[:80] or "event"


def _unique_event_slug(service_client: ServiceRoleClient, base_title: str) -> str:
    base = _slugify(base_title)
    client = service_client.client
    for suffix in range(0, 100):
        candidate = base if suffix == 0 else f"{base}-{suffix}"
        existing = (
            client.table("events")
            .select("id")
            .eq("slug", candidate)
            .maybe_single()
            .execute()
        )
        if _single_row(existing) is None:
            return candidate
    return f"{base}-{uuid.uuid4().hex[:8]}"


def _category_from_row(row: dict[str, Any]) -> EventCategory | None:
    """Read events.category_slug (0036), guarding against unknown values."""
    raw = row.get("category_slug")
    if isinstance(raw, str) and raw in EVENT_CATEGORIES:
        return raw  # type: ignore[return-value]
    return None


def _landmark_from_row(row: dict[str, Any]) -> str | None:
    raw = row.get("landmark")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _visibility_from_row(row: dict[str, Any]) -> Visibility:
    raw = row.get("visibility")
    for candidate in VISIBILITIES:
        if raw == candidate:
            return candidate
    return "public"


def _optional_text(row: dict[str, Any], key: str) -> str | None:
    raw = row.get(key)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _recurrence_until_from_row(row: dict[str, Any]) -> datetime | None:
    raw = row.get("recurrence_until")
    if raw is None:
        return None
    try:
        return _parse_starts_at(raw)
    except (TypeError, ValueError):
        return None


def _platform_fee_payer_from_row(row: dict[str, Any]) -> PlatformFeePayer:
    return "buyer" if row.get("platform_fee_payer") == "buyer" else "organiser"


def _validate_recurrence_payload(
    *,
    event_type: EventType,
    recurrence_rule: str | None,
    recurrence_timezone: str | None,
    recurrence_until: str | None,
) -> None:
    """Make recurrence explicit before the database invariant is reached.

    The recurrence engine parses RFC5545 in a dedicated service. Here we keep
    malformed/partial series drafts from producing a database constraint error.
    """
    if event_type != "recurring":
        if any(value is not None for value in (recurrence_rule, recurrence_timezone, recurrence_until)):
            raise AppError(
                code="recurrence_only_for_recurring_event",
                message="Recurrence fields can only be used on recurring events",
                http_status=422,
            )
        return
    if not recurrence_rule or not recurrence_timezone:
        raise AppError(
            code="recurrence_required",
            message="Recurring events require an RRULE and timezone",
            http_status=422,
            details={"fields": ["recurrence_rule", "recurrence_timezone"]},
        )
    if not recurrence_rule.strip().upper().startswith("FREQ="):
        raise AppError(
            code="invalid_recurrence_rule",
            message="recurrence_rule must be an RFC5545 RRULE beginning with FREQ=",
            http_status=422,
        )
    try:
        ZoneInfo(recurrence_timezone)
        if recurrence_until is not None:
            _parse_starts_at(recurrence_until)
    except (TypeError, ValueError, ZoneInfoNotFoundError):
        raise AppError(
            code="invalid_recurrence_timezone",
            message="recurrence_timezone must be an IANA timezone",
            http_status=422,
        ) from None


def _has_access_credential(client: Any, event_id: str) -> bool:
    response = (
        client.table("event_access_credentials")
        .select("event_id")
        .eq("event_id", event_id)
        .maybe_single()
        .execute()
    )
    return _single_row(response) is not None


def _write_access_credential(
    client: Any,
    *,
    event_id: str,
    visibility: str,
    access_code: str | None,
    rotate: bool,
) -> bool:
    """Create, rotate, or clear the private credential without exposing its digest."""
    code = (access_code or "").strip()
    if visibility != "private" or (rotate and not code):
        client.table("event_access_credentials").delete().eq("event_id", event_id).execute()
        return False
    if not rotate:
        return _has_access_credential(client, event_id)
    existing = (
        client.table("event_access_credentials")
        .select("version")
        .eq("event_id", event_id)
        .maybe_single()
        .execute()
    )
    previous = _single_row(existing)
    version = int(previous.get("version") or 0) + 1 if previous else 1
    client.table("event_access_credentials").upsert(
        {
            "event_id": event_id,
            "code_hash": hash_access_code(code),
            "version": version,
            "rotated_at": datetime.now(UTC).isoformat(),
        },
        on_conflict="event_id",
    ).execute()
    return True


def _parse_images(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]


def _load_vendor_for_owner(
    service_client: ServiceRoleClient,
    owner_user_id: str,
) -> dict[str, Any]:
    response = (
        service_client.client.table("vendors")
        .select("id, owner_user_id, status, kyc_tier")
        .eq("owner_user_id", owner_user_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(
            code="forbidden",
            message="Authenticated user does not own a vendor profile",
            http_status=403,
            details={"message_key": "vendor.errors.not_found"},
        )
    return row


def _require_active_kyc_vendor(
    service_client: ServiceRoleClient,
    vendor: dict[str, Any],
) -> None:
    from app.services.kyc.eligibility import (
        require_events_eligible,
        resolve_vendor_eligibility,
    )

    eligibility = resolve_vendor_eligibility(
        service_client,
        str(vendor["id"]),
        vendor_row=vendor,
    )
    require_events_eligible(eligibility)


def _load_event_for_vendor(
    service_client: ServiceRoleClient,
    *,
    event_id: str,
    vendor_id: str,
) -> dict[str, Any]:
    response = (
        service_client.client.table("events")
        .select(
            "id, organiser_vendor_id, title, slug, description, venue, lat, lng, images, "
            "status, category_slug, landmark, event_type, visibility, recurrence_rule, "
            "recurrence_timezone, recurrence_until, recurrence_horizon_days, platform_fee_payer, "
            "refund_policy_key, age_restriction, terms"
        )
        .eq("id", event_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None or str(row.get("organiser_vendor_id")) != vendor_id:
        raise AppError(
            code="not_found",
            message="Event not found",
            http_status=404,
            details={"message_key": "vendor.events.errors.not_found"},
        )
    row["_has_access_code"] = _has_access_credential(service_client.client, event_id)
    return row


def _fetch_instances(client: Any, event_id: str) -> list[dict[str, Any]]:
    response = (
        client.table("event_instances")
        .select("id, event_id, starts_at, ends_at, capacity")
        .eq("event_id", event_id)
        .order("starts_at")
        .execute()
    )
    return _rows(response)


def _count_sold_tickets(client: Any, instance_ids: list[str]) -> dict[str, int]:
    if not instance_ids:
        return {}
    response = (
        client.table("tickets")
        .select("id, instance_id, status")
        .in_("instance_id", instance_ids)
        .execute()
    )
    counts: dict[str, int] = {}
    for row in _rows(response):
        if str(row.get("status") or "") not in SOLD_TICKET_STATUSES:
            continue
        instance_id = str(row.get("instance_id") or "")
        counts[instance_id] = counts.get(instance_id, 0) + 1
    return counts


def _serialize_event_detail(
    event_row: dict[str, Any],
    instance_rows: list[dict[str, Any]],
    *,
    sold_by_instance: dict[str, int],
) -> EventDetailResponse:
    description = (
        event_row.get("description") if isinstance(event_row.get("description"), str) else None
    )
    instances = [
        EventInstanceResponse(
            id=str(row["id"]),
            starts_at=_parse_starts_at(row["starts_at"]),
            ends_at=_instance_ends_at(row),
            capacity=int(row.get("capacity") or 0),
            tickets_sold=sold_by_instance.get(str(row["id"]), 0),
        )
        for row in instance_rows
    ]
    tickets_sold = sum(sold_by_instance.values())
    status = str(event_row.get("status") or "draft")
    if status not in {"draft", "published", "cancelled", "completed"}:
        status = "draft"
    age_restriction = event_row.get("age_restriction")
    return EventDetailResponse(
        id=str(event_row["id"]),
        title=str(event_row.get("title") or ""),
        slug=str(event_row.get("slug") or ""),
        status=status,  # type: ignore[arg-type]
        category=_category_from_row(event_row),
        event_type=normalize_event_type(event_row.get("event_type")),
        visibility=_visibility_from_row(event_row),
        has_access_code=bool(event_row.get("_has_access_code")),
        recurrence_rule=_optional_text(event_row, "recurrence_rule"),
        recurrence_timezone=_optional_text(event_row, "recurrence_timezone"),
        recurrence_until=_recurrence_until_from_row(event_row),
        recurrence_horizon_days=int(event_row.get("recurrence_horizon_days") or 90),
        platform_fee_payer=_platform_fee_payer_from_row(event_row),
        refund_policy_key=_optional_text(event_row, "refund_policy_key"),
        age_restriction=int(age_restriction) if age_restriction is not None else None,
        terms=_optional_text(event_row, "terms"),
        description=description or None,
        venue=event_row.get("venue") if isinstance(event_row.get("venue"), str) else None,
        lat=float(event_row["lat"]) if event_row.get("lat") is not None else None,
        lng=float(event_row["lng"]) if event_row.get("lng") is not None else None,
        landmark=_landmark_from_row(event_row),
        images=_parse_images(event_row.get("images")),
        instances=instances,
        tickets_sold=tickets_sold,
    )


def _serialize_event_summary(
    event_row: dict[str, Any],
    instance_rows: list[dict[str, Any]],
    *,
    sold_by_instance: dict[str, int],
) -> EventSummary:
    next_starts_at: datetime | None = None
    if instance_rows:
        next_starts_at = _parse_starts_at(instance_rows[0]["starts_at"])
    status = str(event_row.get("status") or "draft")
    if status not in {"draft", "published", "cancelled", "completed"}:
        status = "draft"
    return EventSummary(
        id=str(event_row["id"]),
        title=str(event_row.get("title") or ""),
        slug=str(event_row.get("slug") or ""),
        status=status,  # type: ignore[arg-type]
        category=_category_from_row(event_row),
        event_type=normalize_event_type(event_row.get("event_type")),
        visibility=_visibility_from_row(event_row),
        recurrence_rule=_optional_text(event_row, "recurrence_rule"),
        recurrence_timezone=_optional_text(event_row, "recurrence_timezone"),
        recurrence_until=_recurrence_until_from_row(event_row),
        platform_fee_payer=_platform_fee_payer_from_row(event_row),
        venue=event_row.get("venue") if isinstance(event_row.get("venue"), str) else None,
        landmark=_landmark_from_row(event_row),
        images=_parse_images(event_row.get("images")),
        next_starts_at=next_starts_at,
        instance_count=len(instance_rows),
        tickets_sold=sum(sold_by_instance.values()),
    )


def _validate_instance_time_order(instances: list[EventInstanceInput]) -> None:
    """Reject any instance whose ends_at is not strictly after its starts_at.

    Mirrors the DB CHECK (event_instances_ends_after_starts_chk) so the client
    gets a clean 422 with an i18n key instead of a database error.
    """
    for instance in instances:
        if instance.ends_at is None:
            continue
        if _parse_starts_at(instance.ends_at) <= _parse_starts_at(instance.starts_at):
            raise AppError(
                code="ends_before_starts",
                message="Instance end time must be after its start time",
                http_status=422,
                details={
                    "message_key": "vendor.events.errors.ends_before_starts",
                    "instance_id": instance.id,
                },
            )


def _validate_instances_capacity(
    instances: list[EventInstanceInput],
    *,
    sold_by_instance: dict[str, int],
) -> None:
    for instance in instances:
        if instance.id is None:
            continue
        sold = sold_by_instance.get(instance.id, 0)
        if instance.capacity < sold:
            raise AppError(
                code="capacity_below_sold",
                message="Instance capacity cannot be below tickets already sold",
                http_status=422,
                details={
                    "message_key": "vendor.events.errors.capacity_below_sold",
                    "instance_id": instance.id,
                    "tickets_sold": sold,
                    "requested_capacity": instance.capacity,
                },
            )


def _instances_changed(
    existing: list[dict[str, Any]],
    incoming: list[EventInstanceInput],
) -> bool:
    if len(existing) != len(incoming):
        return True
    existing_by_id = {str(row["id"]): row for row in existing if row.get("id")}
    for item in incoming:
        if item.id is None:
            return True
        prior = existing_by_id.get(item.id)
        if prior is None:
            return True
        if _parse_starts_at(prior["starts_at"]) != _parse_starts_at(item.starts_at):
            return True
        # Only treat ends_at as changed when the client actually supplies one
        # (still-optional field); an omitted end preserves the stored value.
        if item.ends_at is not None:
            prior_ends = _instance_ends_at(prior)
            if prior_ends is None or prior_ends != _parse_starts_at(item.ends_at):
                return True
        if int(prior.get("capacity") or 0) != item.capacity:
            return True
    return False


def _schedule_event_date_label(client: Any, event_id: str) -> str:
    instances = _fetch_instances(client, event_id)
    if not instances:
        return ""
    starts_at_values = [
        _parse_starts_at(row["starts_at"])
        for row in instances
        if row.get("starts_at") is not None
    ]
    if not starts_at_values:
        return ""
    earliest = min(starts_at_values)
    return earliest.astimezone(UTC).strftime("%d %b %Y, %H:%M UTC")


def _notify_schedule_change(
    client: Any,
    *,
    event_id: str,
    event_title: str,
    venue: str,
    holder_user_ids: set[str],
) -> None:
    event_date = _schedule_event_date_label(client, event_id)
    for holder_id in holder_user_ids:
        payload = {
            "event_id": event_id,
            "event_title": event_title,
            "event_date": event_date,
            "venue": venue,
            "recipient_id": holder_id,
        }
        emit_event(
            client,
            event=_SCHEDULE_CHANGE_EVENT,
            entity_id=f"{event_id}:{holder_id}",
            recipient_id=holder_id,
            payload=payload,
        )


def _load_ticket_holders(client: Any, event_id: str) -> set[str]:
    instances = _fetch_instances(client, event_id)
    instance_ids = [str(row["id"]) for row in instances if row.get("id")]
    if not instance_ids:
        return set()
    response = (
        client.table("tickets")
        .select("holder_user_id, status")
        .in_("instance_id", instance_ids)
        .execute()
    )
    holders: set[str] = set()
    for row in _rows(response):
        if str(row.get("status") or "") not in SOLD_TICKET_STATUSES:
            continue
        holder = row.get("holder_user_id")
        if isinstance(holder, str) and holder:
            holders.add(holder)
    return holders


def _sync_instances(
    client: Any,
    *,
    event_id: str,
    instances: list[EventInstanceInput],
    sold_by_instance: dict[str, int],
) -> list[dict[str, Any]]:
    existing = _fetch_instances(client, event_id)
    existing_ids = {str(row["id"]) for row in existing if row.get("id")}
    incoming_ids = {instance.id for instance in instances if instance.id}

    for row in existing:
        row_id = str(row["id"])
        if row_id not in incoming_ids:
            sold = sold_by_instance.get(row_id, 0)
            if sold > 0:
                raise AppError(
                    code="instance_has_sales",
                    message="Cannot remove an instance that has sold tickets",
                    http_status=422,
                    details={
                        "message_key": "vendor.events.errors.instance_has_sales",
                        "instance_id": row_id,
                    },
                )
            client.table("event_instances").delete().eq("id", row_id).execute()

    for instance in instances:
        payload = _instance_write_payload(event_id, instance)
        if instance.id and instance.id in existing_ids:
            client.table("event_instances").update(payload).eq("id", instance.id).execute()
        else:
            client.table("event_instances").insert(payload).execute()

    return _fetch_instances(client, event_id)


def _assert_publishable_instances(instances: list[dict[str, Any]], *, now: datetime) -> None:
    if not instances:
        raise AppError(
            code="validation_error",
            message="At least one instance is required to publish",
            http_status=422,
            details={"message_key": "vendor.events.errors.no_instances"},
        )
    for row in instances:
        starts_at = _parse_starts_at(row["starts_at"])
        if starts_at < now:
            raise AppError(
                code="past_instance",
                message="Cannot publish an event with past-date instances",
                http_status=422,
                details={
                    "message_key": "vendor.events.errors.past_instance",
                    "instance_id": str(row.get("id") or ""),
                },
            )


def _transition_status(
    service_client: ServiceRoleClient,
    *,
    event_row: dict[str, Any],
    vendor_id: str,
    from_statuses: frozenset[str],
    to_status: str,
) -> dict[str, Any]:
    current = str(event_row.get("status") or "")
    if current not in from_statuses:
        raise AppError(
            code="invalid_transition",
            message=f"Cannot transition event from {current} to {to_status}",
            http_status=422,
            details={
                "message_key": "vendor.events.errors.invalid_transition",
                "from_status": current,
                "to_status": to_status,
            },
        )
    response = (
        service_client.client.table("events")
        .update({"status": to_status})
        .eq("id", event_row["id"])
        .eq("organiser_vendor_id", vendor_id)
        .execute()
    )
    updated = _single_row(response)
    if updated is None:
        raise AppError(
            code="not_found",
            message="Event not found",
            http_status=404,
            details={"message_key": "vendor.events.errors.not_found"},
        )
    return updated


@router.get("", response_model=EventListResponse)
async def list_organiser_events(
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> EventListResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    _require_active_kyc_vendor(service_client, vendor)
    vendor_id = str(vendor["id"])
    client = service_client.client

    response = (
        client.table("events")
        .select(
            "id, title, slug, description, venue, images, status, category_slug, landmark, "
            "event_type, visibility, recurrence_rule, recurrence_timezone, recurrence_until, "
            "recurrence_horizon_days, platform_fee_payer"
        )
        .eq("organiser_vendor_id", vendor_id)
        .order("updated_at", desc=True)
        .execute()
    )
    events = _rows(response)
    items: list[EventSummary] = []
    for event in events:
        event_id = str(event["id"])
        instances = _fetch_instances(client, event_id)
        sold = _count_sold_tickets(client, [str(row["id"]) for row in instances if row.get("id")])
        items.append(_serialize_event_summary(event, instances, sold_by_instance=sold))
    return EventListResponse(items=items)


@router.post("", response_model=EventMutationResponse)
async def create_organiser_event(
    body: EventCreateRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> EventMutationResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    _require_active_kyc_vendor(service_client, vendor)
    _validate_instance_time_order(body.instances)
    _validate_recurrence_payload(
        event_type=body.event_type,
        recurrence_rule=body.recurrence_rule,
        recurrence_timezone=body.recurrence_timezone,
        recurrence_until=body.recurrence_until,
    )
    if body.event_type == "recurring" and (len(body.instances) != 1 or body.instances[0].ends_at is None):
        raise AppError(
            code="recurring_event_seed_required",
            message="A recurring event needs exactly one seed instance with an end time",
            http_status=422,
        )
    vendor_id = str(vendor["id"])
    client = service_client.client

    slug = _unique_event_slug(service_client, body.title)
    # event_type drives the default visibility (D29): private events default to
    # visibility='private' unless the organiser overrides it explicitly.
    resolved_visibility = body.visibility or policy_for(body.event_type).default_visibility
    insert_payload = {
        "organiser_vendor_id": vendor_id,
        "title": body.title.strip(),
        "slug": slug,
        "description": (body.description or "").strip() or None,
        "category_slug": body.category,
        "landmark": body.landmark.strip() if body.landmark else None,
        "venue": body.venue.strip() if body.venue else None,
        "lat": body.lat,
        "lng": body.lng,
        "event_type": body.event_type,
        "visibility": resolved_visibility,
        "recurrence_rule": (body.recurrence_rule or "").strip() or None,
        "recurrence_timezone": (body.recurrence_timezone or "").strip() or None,
        "recurrence_until": (
            _parse_starts_at(body.recurrence_until).astimezone(UTC).isoformat()
            if body.recurrence_until
            else None
        ),
        "recurrence_horizon_days": body.recurrence_horizon_days or 90,
        "platform_fee_payer": body.platform_fee_payer,
        "refund_policy_key": (body.refund_policy_key or "").strip() or None,
        "age_restriction": body.age_restriction,
        "terms": (body.terms or "").strip() or None,
        "images": body.images,
        "status": "draft",
    }
    response = client.table("events").insert(insert_payload).execute()
    event_row = _single_row(response)
    if event_row is None:
        raise AppError(
            code="internal_error",
            message="Failed to create event",
            http_status=500,
        )

    event_id = str(event_row["id"])
    event_row["_has_access_code"] = _write_access_credential(
        client,
        event_id=event_id,
        visibility=resolved_visibility,
        access_code=body.access_code,
        rotate=body.access_code is not None,
    )
    if body.event_type == "recurring":
        seed = body.instances[0]
        try:
            materialize_recurrence_instances(
                client,
                event_id=event_id,
                seed_starts_at=_parse_starts_at(seed.starts_at),
                seed_ends_at=_parse_starts_at(seed.ends_at or seed.starts_at),
                capacity=seed.capacity,
                rule=body.recurrence_rule or "",
                timezone=body.recurrence_timezone or "",
                horizon_days=body.recurrence_horizon_days or 90,
                until=_parse_starts_at(body.recurrence_until) if body.recurrence_until else None,
            )
        except RecurrenceError as exc:
            # The event remains a draft, but no partially materialised series is
            # exposed. Organisers can correct it with PATCH and retry.
            raise AppError(
                code="invalid_recurrence_rule",
                message=str(exc),
                http_status=422,
            ) from exc
    else:
        for instance in body.instances:
            client.table("event_instances").insert(
                _instance_write_payload(event_id, instance)
            ).execute()

    instances = _fetch_instances(client, event_id)
    sold = _count_sold_tickets(client, [str(row["id"]) for row in instances if row.get("id")])
    return EventMutationResponse(
        event=_serialize_event_detail(event_row, instances, sold_by_instance=sold)
    )


@router.get("/{event_id}", response_model=EventMutationResponse)
async def get_organiser_event(
    event_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> EventMutationResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    _require_active_kyc_vendor(service_client, vendor)
    vendor_id = str(vendor["id"])
    client = service_client.client

    event_row = _load_event_for_vendor(service_client, event_id=event_id, vendor_id=vendor_id)
    instances = _fetch_instances(client, event_id)
    sold = _count_sold_tickets(client, [str(row["id"]) for row in instances if row.get("id")])
    return EventMutationResponse(
        event=_serialize_event_detail(event_row, instances, sold_by_instance=sold)
    )


@router.patch("/{event_id}", response_model=EventMutationResponse)
async def update_organiser_event(
    event_id: str,
    body: EventUpdateRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> EventMutationResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    _require_active_kyc_vendor(service_client, vendor)
    vendor_id = str(vendor["id"])
    client = service_client.client

    event_row = _load_event_for_vendor(service_client, event_id=event_id, vendor_id=vendor_id)
    status = str(event_row.get("status") or "")
    if status not in EDITABLE_STATUSES:
        raise AppError(
            code="event_not_editable",
            message="Only draft or published events can be edited",
            http_status=422,
            details={"message_key": "vendor.events.errors.not_editable", "status": status},
        )

    existing_instances = _fetch_instances(client, event_id)
    sold_by_instance = _count_sold_tickets(
        client,
        [str(row["id"]) for row in existing_instances if row.get("id")],
    )
    has_sales = sum(sold_by_instance.values()) > 0

    if body.instances is not None:
        _validate_instances_capacity(body.instances, sold_by_instance=sold_by_instance)
        _validate_instance_time_order(body.instances)

    recurrence_fields = {
        "recurrence_rule",
        "recurrence_timezone",
        "recurrence_until",
        "recurrence_horizon_days",
    }
    current_event_type = normalize_event_type(event_row.get("event_type"))
    effective_event_type = body.event_type or current_event_type
    effective_recurrence_rule = (
        body.recurrence_rule
        if "recurrence_rule" in body.model_fields_set
        else _optional_text(event_row, "recurrence_rule")
    )
    effective_recurrence_timezone = (
        body.recurrence_timezone
        if "recurrence_timezone" in body.model_fields_set
        else _optional_text(event_row, "recurrence_timezone")
    )
    effective_recurrence_until = (
        body.recurrence_until
        if "recurrence_until" in body.model_fields_set
        else (
            _recurrence_until_from_row(event_row).isoformat()
            if _recurrence_until_from_row(event_row) is not None
            else None
        )
    )
    _validate_recurrence_payload(
        event_type=effective_event_type,
        recurrence_rule=effective_recurrence_rule,
        recurrence_timezone=effective_recurrence_timezone,
        recurrence_until=effective_recurrence_until,
    )
    if (
        (current_event_type == "recurring" or effective_event_type == "recurring")
        and (body.instances is not None or recurrence_fields & body.model_fields_set)
        and status == "published"
    ):
        raise AppError(
            code="published_recurrence_locked",
            message="Change a published recurring series by creating a new series revision",
            http_status=422,
        )
    if current_event_type != "recurring" and effective_event_type == "recurring":
        raise AppError(
            code="recurrence_create_only",
            message="Create a new recurring series instead of converting an existing event",
            http_status=422,
        )

    venue_before = event_row.get("venue")
    instances_before = [dict(row) for row in existing_instances]

    updates: dict[str, Any] = {}
    if body.title is not None:
        updates["title"] = body.title.strip()
    if body.description is not None:
        updates["description"] = body.description.strip() or None
    if body.category is not None:
        updates["category_slug"] = body.category
    if body.landmark is not None:
        updates["landmark"] = body.landmark.strip() or None
    if body.venue is not None:
        updates["venue"] = body.venue.strip() or None
    if body.lat is not None:
        updates["lat"] = body.lat
    if body.lng is not None:
        updates["lng"] = body.lng
    if body.event_type is not None:
        updates["event_type"] = body.event_type
        if body.event_type != "recurring":
            updates.update(
                {
                    "recurrence_rule": None,
                    "recurrence_timezone": None,
                    "recurrence_until": None,
                }
            )
    if body.visibility is not None:
        updates["visibility"] = body.visibility
    if "recurrence_rule" in body.model_fields_set:
        updates["recurrence_rule"] = (body.recurrence_rule or "").strip() or None
    if "recurrence_timezone" in body.model_fields_set:
        updates["recurrence_timezone"] = (body.recurrence_timezone or "").strip() or None
    if "recurrence_until" in body.model_fields_set:
        updates["recurrence_until"] = (
            _parse_starts_at(body.recurrence_until).astimezone(UTC).isoformat()
            if body.recurrence_until
            else None
        )
    if body.recurrence_horizon_days is not None:
        updates["recurrence_horizon_days"] = body.recurrence_horizon_days
    if body.platform_fee_payer is not None:
        updates["platform_fee_payer"] = body.platform_fee_payer
    if body.refund_policy_key is not None:
        updates["refund_policy_key"] = body.refund_policy_key.strip() or None
    if body.age_restriction is not None:
        updates["age_restriction"] = body.age_restriction
    if body.terms is not None:
        updates["terms"] = body.terms.strip() or None
    if body.images is not None:
        updates["images"] = body.images

    if updates:
        response = (
            client.table("events")
            .update(updates)
            .eq("id", event_id)
            .eq("organiser_vendor_id", vendor_id)
            .execute()
        )
        updated = _single_row(response)
        if updated is not None:
            event_row.update(updated)

    effective_visibility = str(event_row.get("visibility") or "public")
    if body.visibility is not None or body.access_code is not None:
        event_row["_has_access_code"] = _write_access_credential(
            client,
            event_id=event_id,
            visibility=effective_visibility,
            access_code=body.access_code,
            rotate=body.access_code is not None,
        )

    if body.instances is not None:
        existing_instances = _sync_instances(
            client,
            event_id=event_id,
            instances=body.instances,
            sold_by_instance=sold_by_instance,
        )

    if has_sales:
        venue_changed = body.venue is not None and body.venue != venue_before
        dates_changed = body.instances is not None and _instances_changed(
            instances_before,
            body.instances,
        )
        if venue_changed or dates_changed:
            holders = _load_ticket_holders(client, event_id)
            _notify_schedule_change(
                client,
                event_id=event_id,
                event_title=str(event_row.get("title") or ""),
                venue=str(event_row.get("venue") or ""),
                holder_user_ids=holders,
            )

    sold = _count_sold_tickets(
        client,
        [str(row["id"]) for row in existing_instances if row.get("id")],
    )
    return EventMutationResponse(
        event=_serialize_event_detail(event_row, existing_instances, sold_by_instance=sold)
    )


@router.post("/{event_id}/publish", response_model=EventMutationResponse)
async def publish_organiser_event(
    event_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> EventMutationResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    _require_active_kyc_vendor(service_client, vendor)
    vendor_id = str(vendor["id"])
    client = service_client.client

    event_row = _load_event_for_vendor(service_client, event_id=event_id, vendor_id=vendor_id)
    instances = _fetch_instances(client, event_id)
    _assert_publishable_instances(instances, now=datetime.now(UTC))
    if str(event_row.get("visibility") or "public") == "private" and not _has_access_credential(
        client, event_id
    ):
        raise AppError(
            code="private_event_access_code_required",
            message="A private event needs an access code before it can be published",
            http_status=422,
            details={"field": "access_code"},
        )

    event_row = _transition_status(
        service_client,
        event_row=event_row,
        vendor_id=vendor_id,
        from_statuses=frozenset({"draft"}),
        to_status="published",
    )
    sold = _count_sold_tickets(client, [str(row["id"]) for row in instances if row.get("id")])
    return EventMutationResponse(
        event=_serialize_event_detail(event_row, instances, sold_by_instance=sold)
    )


@router.post("/{event_id}/cancel", response_model=EventMutationResponse)
async def cancel_organiser_event(
    event_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> EventMutationResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    _require_active_kyc_vendor(service_client, vendor)
    vendor_id = str(vendor["id"])
    client = service_client.client

    event_row = _load_event_for_vendor(service_client, event_id=event_id, vendor_id=vendor_id)
    instances = _fetch_instances(client, event_id)
    event_row = _transition_status(
        service_client,
        event_row=event_row,
        vendor_id=vendor_id,
        from_statuses=frozenset({"draft", "published"}),
        to_status="cancelled",
    )
    # Post-commit side-effects (D3, approach b): queue admin refunds + notify
    # buyers/holders. Best-effort — the event is already cancelled and the escrow
    # sweep re-flags refunds on its next run, so a transient failure here must not
    # fail the cancellation or leave the organiser unable to retry.
    try:
        process_event_cancellation(
            service_client, event_id=event_id, event_title=str(event_row.get("title") or "")
        )
    except Exception:
        logger.exception("event cancellation side-effects failed", extra={"event_id": event_id})

    sold = _count_sold_tickets(client, [str(row["id"]) for row in instances if row.get("id")])
    return EventMutationResponse(
        event=_serialize_event_detail(event_row, instances, sold_by_instance=sold)
    )


@router.post("/{event_id}/end", response_model=EventMutationResponse)
async def end_organiser_event(
    event_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> EventMutationResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    _require_active_kyc_vendor(service_client, vendor)
    vendor_id = str(vendor["id"])
    client = service_client.client

    event_row = _load_event_for_vendor(service_client, event_id=event_id, vendor_id=vendor_id)
    instances = _fetch_instances(client, event_id)
    event_row = _transition_status(
        service_client,
        event_row=event_row,
        vendor_id=vendor_id,
        from_statuses=frozenset({"published"}),
        to_status="completed",
    )
    sold = _count_sold_tickets(client, [str(row["id"]) for row in instances if row.get("id")])
    return EventMutationResponse(
        event=_serialize_event_detail(event_row, instances, sold_by_instance=sold)
    )
