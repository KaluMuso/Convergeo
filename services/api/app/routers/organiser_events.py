from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.kyc.state_machine import ServiceRoleClient
from app.services.notifications.dedupe import enqueue_outbox_row
from app.services.notifications.events import emit_event
from fastapi import APIRouter, Depends
from pydantic import Field, field_validator

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
EDITABLE_STATUSES = frozenset({"draft", "published"})
SOLD_TICKET_STATUSES = frozenset({"issued", "checked_in"})
MAX_EVENT_IMAGES = 8
_EVENT_META_RE = re.compile(r"\n?<!--vergeo5:event-meta:(\{.*?\})-->\s*$", re.DOTALL)
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
    """Parse an instance row's optional ends_at (NULL for pre-0034 rows)."""
    raw = row.get("ends_at")
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    return _parse_starts_at(raw)


def _instance_write_payload(event_id: str, instance: EventInstanceInput) -> dict[str, Any]:
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


def _split_event_description(raw: str | None) -> tuple[str, dict[str, Any]]:
    if not raw:
        return "", {}
    match = _EVENT_META_RE.search(raw)
    if not match:
        return raw.strip(), {}
    try:
        meta = json.loads(match.group(1))
    except json.JSONDecodeError:
        return raw.strip(), {}
    if not isinstance(meta, dict):
        meta = {}
    visible = raw[: match.start()].strip()
    return visible, meta


def _merge_event_description(
    visible: str | None,
    *,
    category: str | None,
    landmark: str | None,
) -> str | None:
    body = (visible or "").strip()
    meta: dict[str, str] = {}
    if category:
        meta["category"] = category
    if landmark:
        meta["landmark"] = landmark.strip()
    if not meta:
        return body or None
    meta_json = json.dumps(meta, separators=(",", ":"))
    if body:
        return f"{body}\n<!--vergeo5:event-meta:{meta_json}-->"
    return f"<!--vergeo5:event-meta:{meta_json}-->"


def _parse_category(meta: dict[str, Any]) -> EventCategory | None:
    raw = meta.get("category")
    if isinstance(raw, str) and raw in EVENT_CATEGORIES:
        return raw  # type: ignore[return-value]
    return None


def _parse_landmark(meta: dict[str, Any]) -> str | None:
    raw = meta.get("landmark")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


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


def _require_active_kyc_vendor(vendor: dict[str, Any]) -> None:
    status = str(vendor.get("status") or "")
    tier = vendor.get("kyc_tier")
    if status != "active" or tier is None or int(tier) < 1:
        raise AppError(
            code="kyc_required",
            message="Active KYC verification is required to manage events",
            http_status=403,
            details={"message_key": "vendor.events.errors.kyc_required"},
        )


def _load_event_for_vendor(
    service_client: ServiceRoleClient,
    *,
    event_id: str,
    vendor_id: str,
) -> dict[str, Any]:
    response = (
        service_client.client.table("events")
        .select(
            "id, organiser_vendor_id, title, slug, description, venue, lat, lng, images, status"
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
    description, meta = _split_event_description(
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
    return EventDetailResponse(
        id=str(event_row["id"]),
        title=str(event_row.get("title") or ""),
        slug=str(event_row.get("slug") or ""),
        status=status,  # type: ignore[arg-type]
        category=_parse_category(meta),
        description=description or None,
        venue=event_row.get("venue") if isinstance(event_row.get("venue"), str) else None,
        lat=float(event_row["lat"]) if event_row.get("lat") is not None else None,
        lng=float(event_row["lng"]) if event_row.get("lng") is not None else None,
        landmark=_parse_landmark(meta),
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
    _, meta = _split_event_description(
        event_row.get("description") if isinstance(event_row.get("description"), str) else None
    )
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
        category=_parse_category(meta),
        venue=event_row.get("venue") if isinstance(event_row.get("venue"), str) else None,
        landmark=_parse_landmark(meta),
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


def _notify_schedule_change(
    client: Any,
    *,
    event_id: str,
    event_title: str,
    holder_user_ids: set[str],
) -> None:
    for holder_id in holder_user_ids:
        payload = {
            "event_id": event_id,
            "event_title": event_title,
            "recipient_id": holder_id,
        }
        try:
            emit_event(
                client,
                event=_SCHEDULE_CHANGE_EVENT,
                entity_id=f"{event_id}:{holder_id}",
                recipient_id=holder_id,
                payload=payload,
            )
        except ValueError:
            enqueue_outbox_row(
                client,
                event_type=_SCHEDULE_CHANGE_EVENT,
                entity_id=f"{event_id}:{holder_id}",
                channel="whatsapp",
                template=None,
                payload={
                    **payload,
                    "todo": "TODO(M14): map event_schedule_changed to WhatsApp template",
                },
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
    _require_active_kyc_vendor(vendor)
    vendor_id = str(vendor["id"])
    client = service_client.client

    response = (
        client.table("events")
        .select("id, title, slug, description, venue, images, status")
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
    _require_active_kyc_vendor(vendor)
    _validate_instance_time_order(body.instances)
    vendor_id = str(vendor["id"])
    client = service_client.client

    slug = _unique_event_slug(service_client, body.title)
    description = _merge_event_description(
        body.description,
        category=body.category,
        landmark=body.landmark,
    )
    insert_payload = {
        "organiser_vendor_id": vendor_id,
        "title": body.title.strip(),
        "slug": slug,
        "description": description,
        "venue": body.venue.strip() if body.venue else None,
        "lat": body.lat,
        "lng": body.lng,
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
    _require_active_kyc_vendor(vendor)
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
    _require_active_kyc_vendor(vendor)
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

    visible_description, meta = _split_event_description(
        event_row.get("description") if isinstance(event_row.get("description"), str) else None
    )
    next_category = body.category if body.category is not None else _parse_category(meta)
    next_landmark = (
        body.landmark.strip()
        if body.landmark is not None
        else _parse_landmark(meta)
    )
    next_visible = body.description if body.description is not None else visible_description

    venue_before = event_row.get("venue")
    instances_before = [dict(row) for row in existing_instances]

    updates: dict[str, Any] = {}
    if body.title is not None:
        updates["title"] = body.title.strip()
    if (
        body.description is not None
        or body.category is not None
        or body.landmark is not None
    ):
        updates["description"] = _merge_event_description(
            next_visible,
            category=next_category,
            landmark=next_landmark,
        )
    if body.venue is not None:
        updates["venue"] = body.venue.strip() or None
    if body.lat is not None:
        updates["lat"] = body.lat
    if body.lng is not None:
        updates["lng"] = body.lng
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
    _require_active_kyc_vendor(vendor)
    vendor_id = str(vendor["id"])
    client = service_client.client

    event_row = _load_event_for_vendor(service_client, event_id=event_id, vendor_id=vendor_id)
    instances = _fetch_instances(client, event_id)
    _assert_publishable_instances(instances, now=datetime.now(UTC))

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
    _require_active_kyc_vendor(vendor)
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
    _require_active_kyc_vendor(vendor)
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
