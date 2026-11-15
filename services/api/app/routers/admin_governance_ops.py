"""Scoped operator tools behind the 2026-11 governance permissions.

* services.manage — pause/restore a service listing, list service providers, moderate
  RFQ jobs (close an abusive or stale request).
* events.manage — list events and organisers, unpublish (tickets already sold stay
  valid) and cancel (queues refunds for paid tickets and notifies holders).
* support.manage / finance.* — internal notes on a dispute (append-only; stored in
  audit_log, so they cannot be edited or deleted).

Every route sits on the shared admin router: `require_admin_scope` gates it against the
route map in `app.core.auth`, and `AdminAuditedRoute` refuses a mutation that does not
write its audit row.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated, Any, Literal, Protocol
from uuid import UUID

from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.admin_base import router
from app.services.events.cancellation import process_event_cancellation
from fastapi import Depends, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_LIST_LIMIT = 100


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def _one(response: Any) -> dict[str, Any] | None:
    rows = _rows(response)
    return rows[0] if rows else None


class ReasonBody(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


# ---------------------------------------------------------------------------
# services.manage
# ---------------------------------------------------------------------------


class ServiceStatusBody(ReasonBody):
    # Moderation pauses a listing or restores it; drafts stay with the provider.
    status: Literal["active", "paused"]


@router.patch("/services/{service_id}/status")
def set_service_status(
    service_id: UUID,
    body: ServiceStatusBody,
    _actor: Annotated[CurrentUser, Depends(require_role("admin", "superadmin"))],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> dict[str, Any]:
    key = str(service_id)
    before = _one(service.client.table("services").select("id,status").eq("id", key).execute())
    if before is None:
        raise AppError(code="not_found", message="Service not found", http_status=404)
    allowed_from = {"paused"} if body.status == "active" else {"active"}
    if before.get("status") not in allowed_from:
        raise AppError(
            code="invalid_transition",
            message=f"Cannot move a {before.get('status')} service to {body.status}",
            http_status=409,
        )
    # Compare-and-set on the status we read, so a concurrent provider edit is not lost.
    updated = _one(
        service.client.table("services")
        .update({"status": body.status})
        .eq("id", key)
        .eq("status", str(before["status"]))
        .execute()
    )
    if updated is None:
        raise AppError(code="conflict", message="Service changed; reload", http_status=409)
    recorder.record(
        action="admin.services.status",
        entity_type="service",
        entity_id=key,
        before={"status": before.get("status")},
        after={"status": body.status},
        reason=body.reason,
    )
    return {"id": key, "status": body.status}


@router.get("/service-providers")
def list_service_providers(
    _actor: Annotated[CurrentUser, Depends(require_role("admin", "superadmin"))],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> dict[str, Any]:
    services = _rows(
        service.client.table("services").select("vendor_id,status").limit(2000).execute()
    )
    counts: dict[str, dict[str, int]] = {}
    for row in services:
        vendor_id = row.get("vendor_id")
        if not isinstance(vendor_id, str):
            continue
        bucket = counts.setdefault(vendor_id, {"active": 0, "paused": 0, "draft": 0})
        status = str(row.get("status") or "")
        if status in bucket:
            bucket[status] += 1
    if not counts:
        return {"items": []}
    vendors = _rows(
        service.client.table("vendors")
        .select("id,display_name,slug,status,kyc_tier")
        .in_("id", sorted(counts)[:_LIST_LIMIT])
        .execute()
    )
    return {
        "items": [
            {**vendor, "services": counts.get(str(vendor.get("id")), {})} for vendor in vendors
        ]
    }


@router.get("/rfq/jobs")
def list_rfq_jobs(
    _actor: Annotated[CurrentUser, Depends(require_role("admin", "superadmin"))],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    status: Annotated[
        Literal["open", "quoted", "accepted", "completed", "cancelled"] | None, Query()
    ] = None,
) -> dict[str, Any]:
    query = (
        service.client.table("jobs")
        .select("id,category,description,status,preferred_date,created_at")
        .order("created_at", desc=True)
        .limit(_LIST_LIMIT)
    )
    if status is not None:
        query = query.eq("status", status)
    # The customer's identity is deliberately not selected: moderation needs the request
    # text, not who sent it.
    return {"items": _rows(query.execute())}


@router.post("/rfq/jobs/{job_id}/close")
def close_rfq_job(
    job_id: UUID,
    body: ReasonBody,
    _actor: Annotated[CurrentUser, Depends(require_role("admin", "superadmin"))],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> dict[str, Any]:
    key = str(job_id)
    before = _one(service.client.table("jobs").select("id,status").eq("id", key).execute())
    if before is None:
        raise AppError(code="not_found", message="Request not found", http_status=404)
    # Only requests nobody has committed to: an accepted job carries a quote and money.
    if before.get("status") not in {"open", "quoted"}:
        raise AppError(
            code="invalid_transition",
            message="Only open or quoted requests can be closed by moderation",
            http_status=409,
        )
    updated = _one(
        service.client.table("jobs")
        .update({"status": "cancelled"})
        .eq("id", key)
        .eq("status", str(before["status"]))
        .execute()
    )
    if updated is None:
        raise AppError(code="conflict", message="Request changed; reload", http_status=409)
    recorder.record(
        action="admin.rfq.close",
        entity_type="job",
        entity_id=key,
        before={"status": before.get("status")},
        after={"status": "cancelled"},
        reason=body.reason,
    )
    return {"id": key, "status": "cancelled"}


# ---------------------------------------------------------------------------
# events.manage
# ---------------------------------------------------------------------------


@router.get("/events")
def list_events(
    _actor: Annotated[CurrentUser, Depends(require_role("admin", "superadmin"))],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    status: Annotated[Literal["draft", "published", "cancelled", "completed"] | None, Query()] = (
        None
    ),
) -> dict[str, Any]:
    query = (
        service.client.table("events")
        .select("id,title,status,organiser_vendor_id,created_at")
        .order("created_at", desc=True)
        .limit(_LIST_LIMIT)
    )
    if status is not None:
        query = query.eq("status", status)
    return {"items": _rows(query.execute())}


@router.get("/events/organisers")
def list_event_organisers(
    _actor: Annotated[CurrentUser, Depends(require_role("admin", "superadmin"))],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> dict[str, Any]:
    events = _rows(
        service.client.table("events").select("organiser_vendor_id,status").limit(2000).execute()
    )
    counts: dict[str, dict[str, int]] = {}
    for row in events:
        vendor_id = row.get("organiser_vendor_id")
        if isinstance(vendor_id, str):
            bucket = counts.setdefault(vendor_id, {})
            status = str(row.get("status") or "unknown")
            bucket[status] = bucket.get(status, 0) + 1
    if not counts:
        return {"items": []}
    vendors = _rows(
        service.client.table("vendors")
        .select("id,display_name,slug,status,kyc_tier")
        .in_("id", sorted(counts)[:_LIST_LIMIT])
        .execute()
    )
    return {
        "items": [{**vendor, "events": counts.get(str(vendor.get("id")), {})} for vendor in vendors]
    }


def _load_event(service: ServiceRoleClient, event_id: str) -> dict[str, Any]:
    row = _one(
        service.client.table("events").select("id,title,status").eq("id", event_id).execute()
    )
    if row is None:
        raise AppError(code="not_found", message="Event not found", http_status=404)
    return row


def _transition_event(
    service: ServiceRoleClient, event: dict[str, Any], *, allowed: set[str], to_status: str
) -> None:
    if event.get("status") not in allowed:
        raise AppError(
            code="invalid_transition",
            message=f"Cannot move a {event.get('status')} event to {to_status}",
            http_status=409,
        )
    updated = _one(
        service.client.table("events")
        .update({"status": to_status})
        .eq("id", str(event["id"]))
        .eq("status", str(event["status"]))
        .execute()
    )
    if updated is None:
        raise AppError(code="conflict", message="Event changed; reload", http_status=409)


@router.post("/events/{event_id}/unpublish")
def unpublish_event(
    event_id: UUID,
    body: ReasonBody,
    _actor: Annotated[CurrentUser, Depends(require_role("admin", "superadmin"))],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> dict[str, Any]:
    """Hide an event from discovery. Tickets already sold stay valid (founder, 2026-11-13)."""
    event = _load_event(service, str(event_id))
    _transition_event(service, event, allowed={"published"}, to_status="draft")
    recorder.record(
        action="admin.events.unpublish",
        entity_type="event",
        entity_id=str(event_id),
        before={"status": event.get("status")},
        after={"status": "draft"},
        reason=body.reason,
    )
    return {"id": str(event_id), "status": "draft"}


class CancelEventBody(ReasonBody):
    confirmation: Literal["CANCEL EVENT"]


@router.post("/events/{event_id}/cancel")
def cancel_event(
    event_id: UUID,
    body: CancelEventBody,
    _actor: Annotated[CurrentUser, Depends(require_role("admin", "superadmin"))],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> dict[str, Any]:
    """Cancel an event that must not take place: paid tickets are queued for refund.

    Refunds run through the existing event refund jobs (ledger-orchestrated payouts);
    nothing here moves money directly.
    """
    event = _load_event(service, str(event_id))
    _transition_event(service, event, allowed={"draft", "published"}, to_status="cancelled")
    result: dict[str, int] = {}
    try:
        outcome = process_event_cancellation(
            service, event_id=str(event_id), event_title=str(event.get("title") or "")
        )
        result = {
            "orders_flagged": outcome.orders_flagged,
            "jobs_enqueued": outcome.jobs_enqueued,
            "recipients_notified": outcome.recipients_notified,
        }
    except Exception:
        # The escrow sweep re-flags refunds on its next run, as for organiser cancels.
        logger.exception("admin event cancellation side-effects failed")
    recorder.record(
        action="admin.events.cancel",
        entity_type="event",
        entity_id=str(event_id),
        before={"status": event.get("status")},
        after={"status": "cancelled", **result},
        reason=body.reason,
    )
    return {"id": str(event_id), "status": "cancelled", **result}


# ---------------------------------------------------------------------------
# Dispute notes (support.manage, finance.*)
# ---------------------------------------------------------------------------


class DisputeNoteBody(BaseModel):
    note: str = Field(min_length=3, max_length=1000)


class DisputeNoteOut(BaseModel):
    id: str
    actor: str | None
    note: str
    at: datetime


@router.get("/disputes/{dispute_id}/notes")
def list_dispute_notes(
    dispute_id: UUID,
    _actor: Annotated[CurrentUser, Depends(require_role("admin", "superadmin"))],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> dict[str, Any]:
    rows = _rows(
        service.client.table("audit_log")
        .select("id,actor,after,at")
        .eq("entity_type", "dispute")
        .eq("entity_id", str(dispute_id))
        .eq("action", "admin.disputes.note")
        .order("at", desc=False)
        .limit(200)
        .execute()
    )
    notes = [
        DisputeNoteOut(
            id=str(row.get("id")),
            actor=str(row["actor"]) if row.get("actor") else None,
            note=str((row.get("after") or {}).get("note") or ""),
            at=row["at"],
        )
        for row in rows
        if row.get("at")
    ]
    return {"items": [note.model_dump(mode="json") for note in notes]}


@router.post("/disputes/{dispute_id}/notes", status_code=201)
def add_dispute_note(
    dispute_id: UUID,
    body: DisputeNoteBody,
    _actor: Annotated[CurrentUser, Depends(require_role("admin", "superadmin"))],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> dict[str, Any]:
    exists = _one(service.client.table("disputes").select("id").eq("id", str(dispute_id)).execute())
    if exists is None:
        raise AppError(code="not_found", message="Dispute not found", http_status=404)
    row = recorder.record(
        action="admin.disputes.note",
        entity_type="dispute",
        entity_id=str(dispute_id),
        before=None,
        after={"note": body.note.strip()},
    )
    return {"id": str(row.get("id")), "dispute_id": str(dispute_id)}
