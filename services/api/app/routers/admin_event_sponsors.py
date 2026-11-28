"""Admin review of event sponsor logos/links (founder decision, 27 Nov).

Organisers submit sponsors inside ``events.archetype_details``; each starts
``pending`` and is shown publicly only once an admin approves it. Mounted on the
shared ``/admin`` router, so ``require_admin_scope``, the registered rate-limit policy
(``ADMIN_WRITE``) and the audited route class apply: every decision writes exactly one
``audit_log`` row. RBAC: ``vendors.manage`` (see ``ROUTE_PERMISSIONS`` in
``core/auth.py``). Presentation only: no ticket, payment or escrow object is touched.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.admin_base import router
from app.schemas.base import StrictModel
from app.services.events.archetypes import has_pending_sponsor, sponsor_signature
from app.services.kyc.state_machine import ServiceRoleClient
from fastapi import Depends
from pydantic import BaseModel, Field

QUEUE_LIMIT = 100


class SponsorView(BaseModel):
    index: int
    name: str
    logo: str | None = None
    link_url: str | None = None
    tagline: str | None = None
    status: str


class SponsorQueueItem(BaseModel):
    event_id: UUID
    title: str
    slug: str
    event_status: str
    organiser_name: str | None = None
    sponsors: list[SponsorView]


class SponsorQueueResponse(BaseModel):
    items: list[SponsorQueueItem]


class SponsorReviewRequest(StrictModel):
    index: int = Field(ge=0, le=5)
    # Guards against reviewing a different sponsor after a concurrent organiser edit.
    name: str = Field(min_length=1, max_length=80)
    decision: Literal["approved", "rejected"]
    note: str | None = Field(default=None, max_length=500)


class SponsorReviewResponse(BaseModel):
    event_id: UUID
    index: int
    status: str
    pending_remaining: bool


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _views(details: object, *, only: str | None) -> list[SponsorView]:
    sponsors = details.get("sponsors") if isinstance(details, dict) else None
    if not isinstance(sponsors, list):
        return []
    views: list[SponsorView] = []
    for index, sponsor in enumerate(sponsors):
        if not isinstance(sponsor, dict):
            continue
        status = str(sponsor.get("status") or "pending")
        if only is not None and status != only:
            continue
        views.append(
            SponsorView(
                index=index,
                name=str(sponsor.get("name") or ""),
                logo=sponsor.get("logo") if isinstance(sponsor.get("logo"), str) else None,
                link_url=(
                    sponsor.get("link_url") if isinstance(sponsor.get("link_url"), str) else None
                ),
                tagline=sponsor.get("tagline") if isinstance(sponsor.get("tagline"), str) else None,
                status=status,
            )
        )
    return views


@router.get("/event-sponsors", response_model=SponsorQueueResponse)
def list_event_sponsor_queue(
    user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> SponsorQueueResponse:
    del user
    rows = _rows(
        service_client.client.table("events")
        .select("id, title, slug, status, archetype_details, vendors(display_name)")
        .eq("sponsor_review_pending", True)
        .limit(QUEUE_LIMIT)
        .execute()
    )
    items: list[SponsorQueueItem] = []
    for row in rows:
        pending = _views(row.get("archetype_details"), only="pending")
        if not pending or not row.get("id"):
            continue
        vendor = row.get("vendors")
        items.append(
            SponsorQueueItem(
                event_id=UUID(str(row["id"])),
                title=str(row.get("title") or ""),
                slug=str(row.get("slug") or ""),
                event_status=str(row.get("status") or ""),
                organiser_name=(
                    str(vendor.get("display_name"))
                    if isinstance(vendor, dict) and vendor.get("display_name")
                    else None
                ),
                sponsors=pending,
            )
        )
    return SponsorQueueResponse(items=items)


@router.post("/event-sponsors/{event_id}/review", response_model=SponsorReviewResponse)
def review_event_sponsor(
    event_id: UUID,
    body: SponsorReviewRequest,
    user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> SponsorReviewResponse:
    client = service_client.client
    rows = _rows(
        client.table("events").select("id, archetype_details").eq("id", str(event_id)).execute()
    )
    if not rows:
        raise AppError(code="not_found", message="Event not found", http_status=404)
    details = rows[0].get("archetype_details")
    sponsors = details.get("sponsors") if isinstance(details, dict) else None
    if not isinstance(sponsors, list) or body.index >= len(sponsors):
        raise AppError(code="not_found", message="Sponsor not found", http_status=404)
    target = sponsors[body.index]
    if not isinstance(target, dict) or str(target.get("name") or "") != body.name:
        raise AppError(
            code="conflict",
            message="Sponsor changed since it was listed; reload the queue",
            http_status=409,
        )
    before_status = str(target.get("status") or "pending")
    updated_sponsors = [
        {**sp, "status": body.decision} if i == body.index and isinstance(sp, dict) else sp
        for i, sp in enumerate(sponsors)
    ]
    new_details: dict[str, Any] = {
        **(details if isinstance(details, dict) else {}),
        "sponsors": updated_sponsors,
    }
    pending = has_pending_sponsor(new_details)
    client.table("events").update(
        {"archetype_details": new_details, "sponsor_review_pending": pending}
    ).eq("id", str(event_id)).execute()
    recorder.record(
        action=f"event_sponsors.{body.decision}",
        entity_type="event",
        entity_id=event_id,
        before={"sponsor_status": before_status, "sponsor": body.name},
        after={
            "sponsor_status": body.decision,
            "sponsor": body.name,
            "sponsor_signature": list(sponsor_signature(target)),
            "reviewer": user.id,
        },
        reason=body.note,
    )
    return SponsorReviewResponse(
        event_id=event_id, index=body.index, status=body.decision, pending_remaining=pending
    )
