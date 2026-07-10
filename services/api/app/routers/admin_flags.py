from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Protocol
from uuid import UUID

from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.admin_base import router as admin_router
from app.services.notifications.dedupe import enqueue_outbox_row
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

FLAG_STATUSES = frozenset({"open", "actioned", "dismissed"})
ENTITY_TYPES = frozenset({"listing", "review", "prohibited"})
LISTING_ENTITY_TYPES = frozenset({"listing", "prohibited"})

FlagStatus = Literal["open", "actioned", "dismissed"]
EntityType = Literal["listing", "review", "prohibited"]

flags_router = APIRouter(prefix="/flags", tags=["admin-flags"])


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class FlagQueueItem(BaseModel):
    id: UUID
    entity_type: EntityType
    entity_id: UUID
    reason: str
    reporter_user_id: UUID
    status: FlagStatus
    created_at: datetime
    updated_at: datetime
    vendor_id: UUID | None = None
    vendor_display_name: str | None = None
    vendor_slug: str | None = None
    repeat_offender_count: int = 0
    entity_label: str | None = None
    entity_status: str | None = None


class FlagActionResponse(BaseModel):
    flag_id: UUID
    flag_status: FlagStatus
    entity_type: EntityType
    entity_id: UUID
    vendor_id: UUID | None = None
    vendor_status: str | None = None
    entity_status: str | None = None
    notification_enqueued: bool
    repeat_offender_count: int


class FlagActionNote(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


def _table(client: ServiceRoleClient, name: str) -> Any:
    return client.client.table(name)


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        if not data:
            return None
        first = data[0]
        return first if isinstance(first, dict) else None
    return None


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    raise AppError(
        code="internal_error",
        message="Invalid timestamp in flag record",
        http_status=500,
    )


def _load_flag_row(service_client: ServiceRoleClient, flag_id: str) -> dict[str, Any]:
    row = _single_row(
        _table(service_client, "flags")
        .select(
            "id, entity_type, entity_id, reason, reporter_user_id, status, "
            "created_at, updated_at"
        )
        .eq("id", flag_id)
        .maybe_single()
        .execute()
    )
    if row is None:
        raise AppError(code="not_found", message="Flag not found", http_status=404)
    return row


def _load_vendor_row(service_client: ServiceRoleClient, vendor_id: str) -> dict[str, Any]:
    row = _single_row(
        _table(service_client, "vendors")
        .select("id, owner_user_id, slug, display_name, status")
        .eq("id", vendor_id)
        .maybe_single()
        .execute()
    )
    if row is None:
        raise AppError(code="not_found", message="Vendor not found", http_status=404)
    return row


def _load_listing_row(service_client: ServiceRoleClient, listing_id: str) -> dict[str, Any]:
    row = _single_row(
        _table(service_client, "vendor_listings")
        .select("id, vendor_id, title_override, status, products(name)")
        .eq("id", listing_id)
        .maybe_single()
        .execute()
    )
    if row is None:
        raise AppError(code="not_found", message="Listing not found", http_status=404)
    return row


def _load_review_row(service_client: ServiceRoleClient, review_id: str) -> dict[str, Any]:
    row = _single_row(
        _table(service_client, "reviews")
        .select("id, order_item_id, rating, body, status")
        .eq("id", review_id)
        .maybe_single()
        .execute()
    )
    if row is None:
        raise AppError(code="not_found", message="Review not found", http_status=404)
    return row


def _listing_title(listing: dict[str, Any]) -> str:
    override = listing.get("title_override")
    if isinstance(override, str) and override.strip():
        return override.strip()
    products = listing.get("products")
    if isinstance(products, dict):
        name = products.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return "Listing"


def _resolve_vendor_for_flag(
    service_client: ServiceRoleClient,
    *,
    entity_type: str,
    entity_id: str,
) -> tuple[str | None, str | None, str | None]:
    if entity_type in LISTING_ENTITY_TYPES:
        listing = _load_listing_row(service_client, entity_id)
        vendor_id = str(listing["vendor_id"])
        vendor = _load_vendor_row(service_client, vendor_id)
        return vendor_id, str(vendor["display_name"]), str(vendor["slug"])

    if entity_type == "review":
        review = _load_review_row(service_client, entity_id)
        order_item_id = str(review["order_item_id"])
        order_item = _single_row(
            _table(service_client, "order_items")
            .select("order_id")
            .eq("id", order_item_id)
            .maybe_single()
            .execute()
        )
        if order_item is None:
            return None, None, None
        order = _single_row(
            _table(service_client, "orders")
            .select("vendor_id")
            .eq("id", str(order_item["order_id"]))
            .maybe_single()
            .execute()
        )
        if order is None:
            return None, None, None
        vendor_id = str(order["vendor_id"])
        vendor = _load_vendor_row(service_client, vendor_id)
        return vendor_id, str(vendor["display_name"]), str(vendor["slug"])

    return None, None, None


def _compute_repeat_offender_counts(
    service_client: ServiceRoleClient,
) -> dict[str, int]:
    actioned_rows = _rows(
        _table(service_client, "flags")
        .select("id, entity_type, entity_id")
        .eq("status", "actioned")
        .execute()
    )
    counts: dict[str, int] = {}
    for row in actioned_rows:
        vendor_id, _, _ = _resolve_vendor_for_flag(
            service_client,
            entity_type=str(row["entity_type"]),
            entity_id=str(row["entity_id"]),
        )
        if vendor_id is None:
            continue
        counts[vendor_id] = counts.get(vendor_id, 0) + 1
    return counts


def _assert_flag_open(flag: dict[str, Any]) -> None:
    status = str(flag.get("status", ""))
    if status != "open":
        raise AppError(
            code="flag_not_open",
            message="Flag is not open for moderation action",
            http_status=409,
            details={"flag_id": flag.get("id"), "status": status},
        )


def transition_flag_status(
    service_client: ServiceRoleClient,
    *,
    flag_id: str,
    to_status: FlagStatus,
) -> dict[str, Any]:
    current = _load_flag_row(service_client, flag_id)
    from_status = str(current["status"])
    if from_status not in FLAG_STATUSES:
        raise AppError(
            code="invalid_flag_status",
            message="Flag has an invalid status",
            http_status=500,
            details={"flag_id": flag_id, "status": from_status},
        )
    if to_status not in FLAG_STATUSES:
        raise AppError(
            code="invalid_flag_status",
            message="Invalid target flag status",
            http_status=500,
            details={"to_status": to_status},
        )
    if from_status == to_status:
        return current
    allowed: dict[str, frozenset[str]] = {
        "open": frozenset({"actioned", "dismissed"}),
        "actioned": frozenset(),
        "dismissed": frozenset(),
    }
    if to_status not in allowed.get(from_status, frozenset()):
        raise AppError(
            code="invalid_flag_transition",
            message="Flag status transition is not allowed",
            http_status=409,
            details={"from_status": from_status, "to_status": to_status},
        )

    response = (
        _table(service_client, "flags")
        .update({"status": to_status})
        .eq("id", flag_id)
        .eq("status", from_status)
        .execute()
    )
    updated = _rows(response)
    if not updated:
        raise AppError(
            code="flag_transition_conflict",
            message="Flag status changed concurrently",
            http_status=409,
            details={"flag_id": flag_id},
        )
    return updated[0]


def transition_listing_unpublish(
    service_client: ServiceRoleClient,
    *,
    listing_id: str,
) -> dict[str, Any]:
    listing = _load_listing_row(service_client, listing_id)
    from_status = str(listing["status"])
    if from_status != "active":
        raise AppError(
            code="listing_not_active",
            message="Only active listings can be unpublished",
            http_status=409,
            details={"listing_id": listing_id, "status": from_status},
        )
    response = (
        _table(service_client, "vendor_listings")
        .update({"status": "paused"})
        .eq("id", listing_id)
        .eq("status", "active")
        .execute()
    )
    updated = _rows(response)
    if not updated:
        raise AppError(
            code="listing_transition_conflict",
            message="Listing status changed concurrently",
            http_status=409,
            details={"listing_id": listing_id},
        )
    return updated[0]


def transition_listing_remove(
    service_client: ServiceRoleClient,
    *,
    listing_id: str,
) -> dict[str, Any]:
    listing = _load_listing_row(service_client, listing_id)
    from_status = str(listing["status"])
    if from_status == "removed":
        return listing
    if from_status not in {"draft", "active", "paused"}:
        raise AppError(
            code="listing_not_removable",
            message="Listing cannot be removed from its current status",
            http_status=409,
            details={"listing_id": listing_id, "status": from_status},
        )
    response = (
        _table(service_client, "vendor_listings")
        .update({"status": "removed"})
        .eq("id", listing_id)
        .eq("status", from_status)
        .execute()
    )
    updated = _rows(response)
    if not updated:
        raise AppError(
            code="listing_transition_conflict",
            message="Listing status changed concurrently",
            http_status=409,
            details={"listing_id": listing_id},
        )
    return updated[0]


def transition_review_remove(
    service_client: ServiceRoleClient,
    *,
    review_id: str,
) -> dict[str, Any]:
    review = _load_review_row(service_client, review_id)
    from_status = str(review["status"])
    if from_status == "removed":
        return review
    if from_status not in {"published", "flagged"}:
        raise AppError(
            code="review_not_removable",
            message="Review cannot be removed from its current status",
            http_status=409,
            details={"review_id": review_id, "status": from_status},
        )
    response = (
        _table(service_client, "reviews")
        .update({"status": "removed"})
        .eq("id", review_id)
        .eq("status", from_status)
        .execute()
    )
    updated = _rows(response)
    if not updated:
        raise AppError(
            code="review_transition_conflict",
            message="Review status changed concurrently",
            http_status=409,
            details={"review_id": review_id},
        )
    return updated[0]


def transition_vendor_suspend(
    service_client: ServiceRoleClient,
    *,
    vendor_id: str,
) -> dict[str, Any]:
    vendor = _load_vendor_row(service_client, vendor_id)
    from_status = str(vendor["status"])
    if from_status == "suspended":
        return vendor
    if from_status != "active":
        raise AppError(
            code="vendor_not_suspendable",
            message="Only active vendors can be suspended",
            http_status=409,
            details={"vendor_id": vendor_id, "status": from_status},
        )
    response = (
        _table(service_client, "vendors")
        .update({"status": "suspended"})
        .eq("id", vendor_id)
        .eq("status", "active")
        .execute()
    )
    updated = _rows(response)
    if not updated:
        raise AppError(
            code="vendor_transition_conflict",
            message="Vendor status changed concurrently",
            http_status=409,
            details={"vendor_id": vendor_id},
        )
    return updated[0]


def _enqueue_notification(
    service_client: ServiceRoleClient,
    *,
    event_type: str,
    entity_id: str,
    template: str,
    payload: dict[str, Any],
) -> bool:
    row = enqueue_outbox_row(
        service_client.client,
        event_type=event_type,
        entity_id=entity_id,
        channel="whatsapp",
        template=template,
        payload=payload,
    )
    return row is not None


def _repeat_count_for_vendor(
    service_client: ServiceRoleClient,
    vendor_id: str | None,
) -> int:
    if vendor_id is None:
        return 0
    counts = _compute_repeat_offender_counts(service_client)
    return counts.get(vendor_id, 0)


def _snapshot_flag(flag: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": flag["id"],
        "entity_type": flag["entity_type"],
        "entity_id": flag["entity_id"],
        "status": flag["status"],
        "reason": flag["reason"],
    }


def _handle_flag_action(
    *,
    flag_id: str,
    service_client: ServiceRoleClient,
    recorder: AdminAuditRecorder,
    action: str,
    before: dict[str, Any],
    after: dict[str, Any],
    event_type: str,
    template: str,
    notification_payload: dict[str, Any],
    vendor_id: str | None,
) -> FlagActionResponse:
    recorder.record(
        action=action,
        entity_type="flag",
        entity_id=flag_id,
        before=before,
        after=after,
    )
    enqueued = _enqueue_notification(
        service_client,
        event_type=event_type,
        entity_id=flag_id,
        template=template,
        payload=notification_payload,
    )
    flag_after = after["flag"]
    return FlagActionResponse(
        flag_id=UUID(flag_id),
        flag_status=str(flag_after["status"]),  # type: ignore[arg-type]
        entity_type=str(flag_after["entity_type"]),  # type: ignore[arg-type]
        entity_id=UUID(str(flag_after["entity_id"])),
        vendor_id=UUID(vendor_id) if vendor_id else None,
        vendor_status=(
            str(after["vendor"]["status"]) if isinstance(after.get("vendor"), dict) else None
        ),
        entity_status=(
            str(after["entity"]["status"]) if isinstance(after.get("entity"), dict) else None
        ),
        notification_enqueued=enqueued,
        repeat_offender_count=_repeat_count_for_vendor(service_client, vendor_id),
    )


@flags_router.get("", response_model=list[FlagQueueItem])
async def list_flags(
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    status: Annotated[FlagStatus | None, Query()] = "open",
    entity_type: Annotated[EntityType | None, Query()] = None,
) -> list[FlagQueueItem]:
    query = _table(service_client, "flags").select(
        "id, entity_type, entity_id, reason, reporter_user_id, status, created_at, updated_at"
    )
    if status is not None:
        query = query.eq("status", status)
    if entity_type is not None:
        query = query.eq("entity_type", entity_type)
    response = query.order("created_at", desc=False).execute()
    rows = _rows(response)
    offender_counts = _compute_repeat_offender_counts(service_client)

    items: list[FlagQueueItem] = []
    for row in rows:
        entity_type_value = str(row["entity_type"])
        entity_id_value = str(row["entity_id"])
        vendor_id, vendor_name, vendor_slug = _resolve_vendor_for_flag(
            service_client,
            entity_type=entity_type_value,
            entity_id=entity_id_value,
        )
        entity_label: str | None = None
        entity_status: str | None = None
        try:
            if entity_type_value in LISTING_ENTITY_TYPES:
                listing = _load_listing_row(service_client, entity_id_value)
                entity_label = _listing_title(listing)
                entity_status = str(listing["status"])
            elif entity_type_value == "review":
                review = _load_review_row(service_client, entity_id_value)
                body = review.get("body")
                entity_label = (
                    str(body)[:120]
                    if isinstance(body, str) and body.strip()
                    else f"Rating {review.get('rating')}/5"
                )
                entity_status = str(review["status"])
        except AppError:
            entity_label = None
            entity_status = None

        items.append(
            FlagQueueItem(
                id=UUID(str(row["id"])),
                entity_type=entity_type_value,  # type: ignore[arg-type]
                entity_id=UUID(entity_id_value),
                reason=str(row["reason"]),
                reporter_user_id=UUID(str(row["reporter_user_id"])),
                status=str(row["status"]),  # type: ignore[arg-type]
                created_at=_parse_timestamp(row["created_at"]),
                updated_at=_parse_timestamp(row["updated_at"]),
                vendor_id=UUID(vendor_id) if vendor_id else None,
                vendor_display_name=vendor_name,
                vendor_slug=vendor_slug,
                repeat_offender_count=offender_counts.get(vendor_id or "", 0),
                entity_label=entity_label,
                entity_status=entity_status,
            )
        )
    return items


@flags_router.post("/{flag_id}/dismiss", response_model=FlagActionResponse)
async def dismiss_flag(
    flag_id: UUID,
    body: FlagActionNote,
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> FlagActionResponse:
    _ = current_user
    flag_key = str(flag_id)
    flag = _load_flag_row(service_client, flag_key)
    _assert_flag_open(flag)
    before = {"flag": _snapshot_flag(flag)}
    updated_flag = transition_flag_status(service_client, flag_id=flag_key, to_status="dismissed")
    vendor_id, _, _ = _resolve_vendor_for_flag(
        service_client,
        entity_type=str(flag["entity_type"]),
        entity_id=str(flag["entity_id"]),
    )
    after = {"flag": _snapshot_flag(updated_flag), "note": body.note}
    return _handle_flag_action(
        flag_id=flag_key,
        service_client=service_client,
        recorder=recorder,
        action="admin.flags.dismiss",
        before=before,
        after=after,
        event_type="flag_dismissed",
        template="flag_dismissed",
        notification_payload={
            "flag_id": flag_key,
            "reporter_user_id": str(flag["reporter_user_id"]),
            "note": body.note,
        },
        vendor_id=vendor_id,
    )


@flags_router.post("/{flag_id}/unpublish", response_model=FlagActionResponse)
async def unpublish_flagged_listing(
    flag_id: UUID,
    body: FlagActionNote,
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> FlagActionResponse:
    _ = current_user
    flag_key = str(flag_id)
    flag = _load_flag_row(service_client, flag_key)
    _assert_flag_open(flag)
    entity_type = str(flag["entity_type"])
    entity_id = str(flag["entity_id"])
    if entity_type not in LISTING_ENTITY_TYPES:
        raise AppError(
            code="invalid_entity_type",
            message="Unpublish applies to listing flags only",
            http_status=409,
            details={"entity_type": entity_type},
        )

    listing_before = _load_listing_row(service_client, entity_id)
    vendor_id = str(listing_before["vendor_id"])
    vendor_before = _load_vendor_row(service_client, vendor_id)
    before = {
        "flag": _snapshot_flag(flag),
        "entity": {"id": entity_id, "status": listing_before["status"]},
        "vendor": {"id": vendor_id, "status": vendor_before["status"]},
    }

    updated_listing = transition_listing_unpublish(service_client, listing_id=entity_id)
    updated_flag = transition_flag_status(service_client, flag_id=flag_key, to_status="actioned")
    after = {
        "flag": _snapshot_flag(updated_flag),
        "entity": {"id": entity_id, "status": updated_listing["status"]},
        "vendor": {"id": vendor_id, "status": vendor_before["status"]},
        "note": body.note,
    }
    return _handle_flag_action(
        flag_id=flag_key,
        service_client=service_client,
        recorder=recorder,
        action="admin.flags.unpublish",
        before=before,
        after=after,
        event_type="listing_unpublished",
        template="listing_unpublished",
        notification_payload={
            "flag_id": flag_key,
            "listing_id": entity_id,
            "vendor_id": vendor_id,
            "owner_user_id": str(vendor_before["owner_user_id"]),
            "note": body.note,
        },
        vendor_id=vendor_id,
    )


@flags_router.post("/{flag_id}/remove", response_model=FlagActionResponse)
async def remove_flagged_entity(
    flag_id: UUID,
    body: FlagActionNote,
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> FlagActionResponse:
    _ = current_user
    flag_key = str(flag_id)
    flag = _load_flag_row(service_client, flag_key)
    _assert_flag_open(flag)
    entity_type = str(flag["entity_type"])
    entity_id = str(flag["entity_id"])

    vendor_id: str | None = None
    vendor_before: dict[str, Any] | None = None
    entity_before_status: str

    if entity_type in LISTING_ENTITY_TYPES:
        entity_row = _load_listing_row(service_client, entity_id)
        vendor_id = str(entity_row["vendor_id"])
        vendor_before = _load_vendor_row(service_client, vendor_id)
        entity_before_status = str(entity_row["status"])
    elif entity_type == "review":
        entity_row = _load_review_row(service_client, entity_id)
        entity_before_status = str(entity_row["status"])
        vendor_id, _, _ = _resolve_vendor_for_flag(
            service_client, entity_type=entity_type, entity_id=entity_id
        )
        if vendor_id is not None:
            vendor_before = _load_vendor_row(service_client, vendor_id)
    else:
        raise AppError(
            code="invalid_entity_type",
            message="Remove is not supported for this entity type",
            http_status=409,
            details={"entity_type": entity_type},
        )

    before = {
        "flag": _snapshot_flag(flag),
        "entity": {"id": entity_id, "status": entity_before_status},
    }
    if vendor_before is not None and vendor_id is not None:
        before["vendor"] = {"id": vendor_id, "status": vendor_before["status"]}

    if entity_type in LISTING_ENTITY_TYPES:
        updated_entity = transition_listing_remove(service_client, listing_id=entity_id)
        template = "listing_removed"
        event_type = "listing_removed"
    else:
        updated_entity = transition_review_remove(service_client, review_id=entity_id)
        template = "review_removed"
        event_type = "review_removed"

    updated_flag = transition_flag_status(service_client, flag_id=flag_key, to_status="actioned")
    after: dict[str, Any] = {
        "flag": _snapshot_flag(updated_flag),
        "entity": {"id": entity_id, "status": updated_entity["status"]},
        "note": body.note,
    }
    if vendor_before is not None and vendor_id is not None:
        after["vendor"] = {"id": vendor_id, "status": vendor_before["status"]}

    payload: dict[str, Any] = {
        "flag_id": flag_key,
        "entity_id": entity_id,
        "entity_type": entity_type,
        "note": body.note,
    }
    if vendor_before is not None and vendor_id is not None:
        payload["vendor_id"] = vendor_id
        payload["owner_user_id"] = str(vendor_before["owner_user_id"])

    return _handle_flag_action(
        flag_id=flag_key,
        service_client=service_client,
        recorder=recorder,
        action="admin.flags.remove",
        before=before,
        after=after,
        event_type=event_type,
        template=template,
        notification_payload=payload,
        vendor_id=vendor_id,
    )


@flags_router.post("/{flag_id}/warn-vendor", response_model=FlagActionResponse)
async def warn_vendor_for_flag(
    flag_id: UUID,
    body: FlagActionNote,
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> FlagActionResponse:
    _ = current_user
    flag_key = str(flag_id)
    flag = _load_flag_row(service_client, flag_key)
    _assert_flag_open(flag)
    vendor_id, _, _ = _resolve_vendor_for_flag(
        service_client,
        entity_type=str(flag["entity_type"]),
        entity_id=str(flag["entity_id"]),
    )
    if vendor_id is None:
        raise AppError(
            code="vendor_not_resolved",
            message="Could not resolve vendor for this flag",
            http_status=409,
        )
    vendor_before = _load_vendor_row(service_client, vendor_id)
    before = {
        "flag": _snapshot_flag(flag),
        "vendor": {"id": vendor_id, "status": vendor_before["status"]},
    }
    updated_flag = transition_flag_status(service_client, flag_id=flag_key, to_status="actioned")
    after = {
        "flag": _snapshot_flag(updated_flag),
        "vendor": {"id": vendor_id, "status": vendor_before["status"]},
        "note": body.note,
    }
    return _handle_flag_action(
        flag_id=flag_key,
        service_client=service_client,
        recorder=recorder,
        action="admin.flags.warn_vendor",
        before=before,
        after=after,
        event_type="vendor_warned",
        template="vendor_warned",
        notification_payload={
            "flag_id": flag_key,
            "vendor_id": vendor_id,
            "owner_user_id": str(vendor_before["owner_user_id"]),
            "reason": str(flag["reason"]),
            "note": body.note,
        },
        vendor_id=vendor_id,
    )


@flags_router.post("/{flag_id}/escalate-suspend", response_model=FlagActionResponse)
async def escalate_suspend_vendor(
    flag_id: UUID,
    body: FlagActionNote,
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> FlagActionResponse:
    _ = current_user
    flag_key = str(flag_id)
    flag = _load_flag_row(service_client, flag_key)
    _assert_flag_open(flag)
    vendor_id, _, _ = _resolve_vendor_for_flag(
        service_client,
        entity_type=str(flag["entity_type"]),
        entity_id=str(flag["entity_id"]),
    )
    if vendor_id is None:
        raise AppError(
            code="vendor_not_resolved",
            message="Could not resolve vendor for this flag",
            http_status=409,
        )
    vendor_before = _load_vendor_row(service_client, vendor_id)
    listing_rows = _rows(
        _table(service_client, "vendor_listings")
        .select("id, status")
        .eq("vendor_id", vendor_id)
        .execute()
    )
    order_rows = _rows(
        _table(service_client, "orders")
        .select("id, status")
        .eq("vendor_id", vendor_id)
        .execute()
    )
    payout_rows = _rows(
        _table(service_client, "payouts").select("id, status").eq("vendor_id", vendor_id).execute()
    )

    before = {
        "flag": _snapshot_flag(flag),
        "vendor": {"id": vendor_id, "status": vendor_before["status"]},
        "listings": [{"id": row["id"], "status": row["status"]} for row in listing_rows],
        "orders": [{"id": row["id"], "status": row["status"]} for row in order_rows],
        "payouts": [{"id": row["id"], "status": row["status"]} for row in payout_rows],
    }

    updated_vendor = transition_vendor_suspend(service_client, vendor_id=vendor_id)
    updated_flag = transition_flag_status(service_client, flag_id=flag_key, to_status="actioned")

    listings_after = _rows(
        _table(service_client, "vendor_listings")
        .select("id, status")
        .eq("vendor_id", vendor_id)
        .execute()
    )
    orders_after = _rows(
        _table(service_client, "orders")
        .select("id, status")
        .eq("vendor_id", vendor_id)
        .execute()
    )
    payouts_after = _rows(
        _table(service_client, "payouts").select("id, status").eq("vendor_id", vendor_id).execute()
    )

    after = {
        "flag": _snapshot_flag(updated_flag),
        "vendor": {"id": vendor_id, "status": updated_vendor["status"]},
        "listings": [{"id": row["id"], "status": row["status"]} for row in listings_after],
        "orders": [{"id": row["id"], "status": row["status"]} for row in orders_after],
        "payouts": [{"id": row["id"], "status": row["status"]} for row in payouts_after],
        "note": body.note,
    }

    return _handle_flag_action(
        flag_id=flag_key,
        service_client=service_client,
        recorder=recorder,
        action="admin.flags.escalate_suspend",
        before=before,
        after=after,
        event_type="vendor_suspended",
        template="vendor_suspended",
        notification_payload={
            "flag_id": flag_key,
            "vendor_id": vendor_id,
            "owner_user_id": str(vendor_before["owner_user_id"]),
            "reason": str(flag["reason"]),
            "note": body.note,
        },
        vendor_id=vendor_id,
    )


admin_router.include_router(flags_router)
