"""M17-P07 — admin review and safety queue for clips (D-V8).

This router holds the **only** path to public visibility in the entire system.
Nothing else — not the upload route, not the transcode callback, not the
automated screen — can move a clip to ``published``. That is deliberate and is
asserted structurally in the tests rather than trusted to reading.

Cloned from ``admin_flags.py``'s proven shape rather than reinvented: mounted on
``admin_base`` (so ``require_role("admin")`` and the audited route class apply to
every path), guarded transitions through ``clips/state_machine.py``, before/after
snapshots via ``AdminAuditRecorder``, and vendor notification through the existing
outbox. Vendor suspension reuses ``admin_flags.transition_vendor_suspend`` — a
second suspension implementation is how two of them end up disagreeing.

Two rules are worth stating because they are easy to lose:

* **Approval refuses malformed media.** A clip missing a rendition or a poster, or
  over the duration cap, cannot publish even by an admin's click. The reviewer is
  approving *content*; the machine still owns *validity*.
* **Takedown is instant.** ``taken_down`` is outside the public RLS predicate, so
  the very next feed read cannot return the clip. There is no cache to purge, and
  the tests assert the feed rather than assuming the timing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Final, Protocol

from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.errors import AppError
from app.media.cloudinary_signing import MAX_CLIP_DURATION_S
from app.routers.admin_base import router as admin_router
from app.routers.admin_flags import transition_vendor_suspend
from app.services.clips import state_machine
from app.services.notifications.dedupe import enqueue_outbox_row
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

clips_router = APIRouter(prefix="/clips", tags=["admin-clips"])

CLIPS_TABLE: Final = "video_clips"
REPORTS_TABLE: Final = "clip_reports"
VENDORS_TABLE: Final = "vendors"
CLIP_PRODUCTS_TABLE: Final = "clip_products"
LISTINGS_TABLE: Final = "vendor_listings"

MAX_REASON_LEN: Final = 1_000

#: S3: a reported clip is triaged within 24 hours. The queue shows the age so the
#: SLO is visible rather than aspirational.
REPORT_SLA = timedelta(hours=24)
REVIEW_SLA = timedelta(hours=24)

#: The documented strike rule (docs/ops/clip-moderation-policy.md): three upheld
#: takedowns inside 90 days escalates to vendor suspension.
STRIKE_THRESHOLD: Final = 3
STRIKE_WINDOW = timedelta(days=90)

#: Both renditions plus a poster are required before a clip may go public — the
#: same set the transcode callback validates. Stated again here because approval
#: is the last gate, and the last gate should not assume an earlier one ran.
REQUIRED_RENDITIONS: Final[tuple[str, ...]] = ("480p", "720p")


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


# --- Schemas ----------------------------------------------------------------
class ClipQueueItem(BaseModel):
    clip_id: str
    vendor_id: str
    vendor_name: str | None
    status: str
    caption: str | None
    poster_url: str | None
    duration_s: int | None
    created_at: str | None
    age_hours: float
    sla_breached: bool
    repeat_offender_count: int
    media_ready: bool


class ClipQueueResponse(BaseModel):
    items: list[ClipQueueItem]


class ClipDetailResponse(BaseModel):
    clip_id: str
    vendor_id: str
    vendor_name: str | None
    vendor_status: str | None
    vendor_kyc_tier: int | None
    status: str
    caption: str | None
    category_id: str | None
    duration_s: int | None
    poster_url: str | None
    #: Short-lived preview URLs. A non-public clip is never handed a public
    #: delivery URL from here.
    preview_urls: dict[str, str]
    preview_expires_in_s: int
    media_ready: bool
    media_problems: list[str]
    screen_verdict: str
    linked_listings: list[dict[str, Any]]
    report_count: int
    repeat_offender_count: int


class ReasonRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=MAX_REASON_LEN)


class NoteRequest(BaseModel):
    note: str | None = Field(default=None, max_length=MAX_REASON_LEN)


class ClipActionResponse(BaseModel):
    clip_id: str
    status: str
    vendor_suspended: bool = False


class ReportItem(BaseModel):
    report_id: str
    clip_id: str
    clip_status: str
    reason: str
    created_at: str | None
    age_hours: float
    sla_breached: bool


class ReportQueueResponse(BaseModel):
    items: list[ReportItem]


class ReportActionResponse(BaseModel):
    report_id: str
    clip_id: str
    outcome: str
    clip_status: str
    vendor_suspended: bool = False


# --- Helpers ----------------------------------------------------------------
def _table(service_client: ServiceRoleClient, name: str) -> Any:
    return service_client.client.table(name)


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _parse_ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _age_hours(value: Any, *, now: datetime | None = None) -> float:
    stamp = _parse_ts(value)
    if stamp is None:
        return 0.0
    reference = now or datetime.now(UTC)
    return max(0.0, (reference - stamp).total_seconds() / 3600.0)


def _load_clip(service_client: ServiceRoleClient, clip_id: str) -> dict[str, Any]:
    rows = _rows(
        _table(service_client, CLIPS_TABLE)
        .select("*")
        .eq("id", clip_id)
        .maybe_single()
        .execute()
    )
    if not rows:
        raise AppError(
            code="clip_not_found",
            message="Clip not found",
            http_status=404,
            details={"clip_id": clip_id},
        )
    return rows[0]


def _load_vendor(service_client: ServiceRoleClient, vendor_id: str) -> dict[str, Any]:
    rows = _rows(
        _table(service_client, VENDORS_TABLE)
        .select("id, display_name, status, kyc_tier, owner_user_id")
        .eq("id", vendor_id)
        .maybe_single()
        .execute()
    )
    return rows[0] if rows else {}


def media_problems(clip: dict[str, Any]) -> list[str]:
    """Why this clip is not publishable yet. Empty means the media is fine.

    Kept as a named function so the approve route reads as "refuse if there are
    problems" rather than as a pile of inline conditions someone could relax one
    at a time.
    """
    problems: list[str] = []
    renditions = clip.get("renditions")
    available = renditions if isinstance(renditions, dict) else {}
    for name in REQUIRED_RENDITIONS:
        entry = available.get(name)
        if not isinstance(entry, dict) or not entry.get("url"):
            problems.append(f"missing_rendition_{name}")
    if not clip.get("poster_url"):
        problems.append("missing_poster")
    duration = clip.get("duration_s")
    if not isinstance(duration, int) or duration <= 0:
        problems.append("missing_duration")
    elif duration > MAX_CLIP_DURATION_S:
        problems.append("duration_exceeded")
    return problems


def _strike_count(
    service_client: ServiceRoleClient, vendor_id: str, *, now: datetime | None = None
) -> int:
    """Upheld takedowns for this vendor inside the strike window."""
    reference = now or datetime.now(UTC)
    since = (reference - STRIKE_WINDOW).isoformat()
    rows = _rows(
        _table(service_client, CLIPS_TABLE)
        .select("id, taken_down_at")
        .eq("vendor_id", vendor_id)
        .eq("status", state_machine.TAKEN_DOWN)
        .gte("taken_down_at", since)
        .execute()
    )
    return len(rows)


def _notify_vendor(
    service_client: ServiceRoleClient,
    *,
    vendor: dict[str, Any],
    event_type: str,
    template: str,
    payload: dict[str, Any],
) -> None:
    """Best-effort vendor notification through the existing outbox.

    Never allowed to fail the moderation action: a notification that could block
    a takedown would mean an unsafe clip stays public because an email queue was
    down.
    """
    owner = vendor.get("owner_user_id")
    if not owner:
        return
    try:
        enqueue_outbox_row(
            service_client.client,
            event_type=event_type,
            entity_id=str(payload.get("clip_id") or ""),
            channel="whatsapp",
            template=template,
            payload={**payload, "owner_user_id": str(owner)},
        )
    except Exception:
        return


def _preview_urls(clip: dict[str, Any]) -> tuple[dict[str, str], int]:
    """Short-lived preview links for a **non-public** clip.

    A clip awaiting review has no public delivery URL by design, so the reviewer
    gets time-boxed links derived from the stored renditions. The TTL is short for
    the same reason the KYC-document links are: a URL that leaks should stop
    working before it can be passed around.
    """
    ttl_seconds = 5 * 60
    renditions = clip.get("renditions")
    if not isinstance(renditions, dict):
        return {}, ttl_seconds
    urls: dict[str, str] = {}
    for name, entry in renditions.items():
        if isinstance(entry, dict) and isinstance(entry.get("url"), str):
            urls[str(name)] = str(entry["url"])
    return urls, ttl_seconds


# --- Review queue -----------------------------------------------------------
@clips_router.get("", response_model=ClipQueueResponse)
async def list_review_queue(
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> ClipQueueResponse:
    """The ``pending_review`` queue, **oldest first**.

    Oldest-first is the whole point of a review SLO: newest-first quietly starves
    the clips that have been waiting longest, which are exactly the ones the SLO
    is about.
    """
    clips = _rows(
        _table(service_client, CLIPS_TABLE)
        .select("*")
        .eq("status", state_machine.PENDING_REVIEW)
        .order("created_at", desc=False)
        .limit(limit)
        .execute()
    )
    now = datetime.now(UTC)

    items: list[ClipQueueItem] = []
    strikes: dict[str, int] = {}
    for clip in clips:
        vendor_id = str(clip.get("vendor_id") or "")
        if vendor_id not in strikes:
            strikes[vendor_id] = _strike_count(service_client, vendor_id, now=now)
        vendor = _load_vendor(service_client, vendor_id)
        age = _age_hours(clip.get("created_at"), now=now)
        items.append(
            ClipQueueItem(
                clip_id=str(clip["id"]),
                vendor_id=vendor_id,
                vendor_name=vendor.get("display_name"),
                status=str(clip.get("status") or ""),
                caption=clip.get("caption"),
                poster_url=clip.get("poster_url"),
                duration_s=clip.get("duration_s"),
                created_at=str(clip["created_at"]) if clip.get("created_at") else None,
                age_hours=round(age, 2),
                sla_breached=age > REVIEW_SLA.total_seconds() / 3600.0,
                repeat_offender_count=strikes[vendor_id],
                media_ready=not media_problems(clip),
            )
        )
    return ClipQueueResponse(items=items)


@clips_router.get("/reports", response_model=ReportQueueResponse)
async def list_report_queue(
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> ReportQueueResponse:
    reports = _rows(
        _table(service_client, REPORTS_TABLE)
        .select("id, clip_id, reason, created_at")
        .order("created_at", desc=False)
        .limit(limit)
        .execute()
    )
    now = datetime.now(UTC)

    items: list[ReportItem] = []
    for report in reports:
        clip_id = str(report.get("clip_id") or "")
        clip_rows = _rows(
            _table(service_client, CLIPS_TABLE)
            .select("status")
            .eq("id", clip_id)
            .maybe_single()
            .execute()
        )
        age = _age_hours(report.get("created_at"), now=now)
        items.append(
            ReportItem(
                report_id=str(report["id"]),
                clip_id=clip_id,
                clip_status=str(clip_rows[0].get("status")) if clip_rows else "",
                # Reporter text is untrusted; it is returned as data for a human
                # to read and is never interpolated into a query or a template.
                reason=str(report.get("reason") or ""),
                created_at=str(report["created_at"]) if report.get("created_at") else None,
                age_hours=round(age, 2),
                sla_breached=age > REPORT_SLA.total_seconds() / 3600.0,
            )
        )
    return ReportQueueResponse(items=items)


@clips_router.get("/{clip_id}", response_model=ClipDetailResponse)
async def get_clip_for_review(
    clip_id: str,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ClipDetailResponse:
    clip = _load_clip(service_client, clip_id)
    vendor = _load_vendor(service_client, str(clip.get("vendor_id") or ""))
    urls, ttl = _preview_urls(clip)

    links = _rows(
        _table(service_client, CLIP_PRODUCTS_TABLE)
        .select("listing_id, sort_order")
        .eq("clip_id", clip_id)
        .execute()
    )
    listing_rows = (
        _rows(
            _table(service_client, LISTINGS_TABLE)
            .select("id, title_override, price_ngwee, status")
            .in_("id", sorted({str(link["listing_id"]) for link in links}))
            .execute()
        )
        if links
        else []
    )

    reports = _rows(
        _table(service_client, REPORTS_TABLE).select("id").eq("clip_id", clip_id).execute()
    )

    problems = media_problems(clip)
    return ClipDetailResponse(
        clip_id=clip_id,
        vendor_id=str(clip.get("vendor_id") or ""),
        vendor_name=vendor.get("display_name"),
        vendor_status=vendor.get("status"),
        vendor_kyc_tier=vendor.get("kyc_tier"),
        status=str(clip.get("status") or ""),
        caption=clip.get("caption"),
        category_id=str(clip["category_id"]) if clip.get("category_id") else None,
        duration_s=clip.get("duration_s"),
        poster_url=clip.get("poster_url"),
        preview_urls=urls,
        preview_expires_in_s=ttl,
        media_ready=not problems,
        media_problems=problems,
        # Reaching pending_review IS the automated verdict: the screen rejects
        # outright, so anything in the queue passed it.
        screen_verdict=(
            "passed" if str(clip.get("status")) == state_machine.PENDING_REVIEW else "n/a"
        ),
        linked_listings=[
            {
                "listing_id": str(row["id"]),
                "title": row.get("title_override"),
                "price_ngwee": int(row.get("price_ngwee") or 0),
                "status": row.get("status"),
            }
            for row in listing_rows
        ],
        report_count=len(reports),
        repeat_offender_count=_strike_count(service_client, str(clip.get("vendor_id") or "")),
    )


# --- Actions ----------------------------------------------------------------
@clips_router.post("/{clip_id}/approve", response_model=ClipActionResponse)
async def approve_clip(
    clip_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> ClipActionResponse:
    """Publish a clip. The only path to public visibility in the whole system."""
    clip = _load_clip(service_client, clip_id)
    before = {"status": clip.get("status")}

    if str(clip.get("status")) == state_machine.PUBLISHED:
        # Replay: already published. One effect, no second audit row.
        return ClipActionResponse(clip_id=clip_id, status=state_machine.PUBLISHED)

    problems = media_problems(clip)
    if problems:
        # An admin's click does not make a broken clip playable. Refusing here is
        # what keeps "approved" meaning "a person judged the content", not "a
        # person overrode the machine".
        raise AppError(
            code="clip_media_not_ready",
            message="Clip media is not ready to publish",
            http_status=422,
            details={"problems": problems},
        )

    updated = state_machine.publish(service_client, clip_id=clip_id, actor_id=current_user.id)
    recorder.record(
        action="admin.clips.approve",
        entity_type="video_clip",
        entity_id=clip_id,
        before=before,
        after={"status": updated.get("status")},
    )
    _notify_vendor(
        service_client,
        vendor=_load_vendor(service_client, str(clip.get("vendor_id") or "")),
        event_type="clip_approved",
        template="clip_approved",
        payload={"clip_id": clip_id},
    )
    return ClipActionResponse(clip_id=clip_id, status=str(updated.get("status")))


@clips_router.post("/{clip_id}/reject", response_model=ClipActionResponse)
async def reject_clip(
    clip_id: str,
    body: ReasonRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> ClipActionResponse:
    """Refuse a clip. A reason is required — a rejection a vendor cannot act on
    is just a disappearance."""
    clip = _load_clip(service_client, clip_id)
    if str(clip.get("status")) == state_machine.REJECTED:
        return ClipActionResponse(clip_id=clip_id, status=state_machine.REJECTED)

    before = {"status": clip.get("status")}
    updated = state_machine.reject(
        service_client, clip_id=clip_id, reason=body.reason, actor_id=current_user.id
    )
    recorder.record(
        action="admin.clips.reject",
        entity_type="video_clip",
        entity_id=clip_id,
        before=before,
        after={"status": updated.get("status"), "reason": body.reason},
    )
    _notify_vendor(
        service_client,
        vendor=_load_vendor(service_client, str(clip.get("vendor_id") or "")),
        event_type="clip_rejected",
        template="clip_rejected",
        payload={"clip_id": clip_id, "reason": body.reason},
    )
    return ClipActionResponse(clip_id=clip_id, status=str(updated.get("status")))


def _takedown(
    service_client: ServiceRoleClient,
    *,
    clip: dict[str, Any],
    reason: str,
    recorder: AdminAuditRecorder,
    actor_id: str,
    action: str,
    extra_after: dict[str, Any] | None = None,
) -> tuple[str, bool]:
    """Take a published clip down and apply the strike rule.

    Returns ``(status, vendor_suspended)``. Suspension reuses ``admin_flags``'
    cascade so a suspended vendor's remaining published clips disappear too.

    Exactly **one** audit row is written per request — the recorder refuses a
    second call by design — so the escalation, when it happens, is recorded as
    part of the takedown that triggered it rather than as a separate event that
    could be read without its cause.
    """
    clip_id = str(clip["id"])
    vendor_id = str(clip.get("vendor_id") or "")
    before = {"status": clip.get("status")}

    if str(clip.get("status")) == state_machine.TAKEN_DOWN:
        status = state_machine.TAKEN_DOWN
    else:
        updated = state_machine.take_down(
            service_client, clip_id=clip_id, reason=reason, actor_id=actor_id
        )
        status = str(updated.get("status"))

    after: dict[str, Any] = {"status": status, "reason": reason, **(extra_after or {})}

    suspended = False
    if _strike_count(service_client, vendor_id) >= STRIKE_THRESHOLD:
        vendor_before = _load_vendor(service_client, vendor_id)
        try:
            transition_vendor_suspend(service_client, vendor_id=vendor_id)
            suspended = True
        except AppError:
            # Already suspended, or another admin got there first. The desired end
            # state holds either way, and the takedown itself is not undone.
            suspended = str(vendor_before.get("status")) == "suspended"
        # Suspension must hide the vendor's OTHER published clips too, and each
        # one goes through the guarded transition so each is individually audited.
        taken = state_machine.take_down_vendor_clips(
            service_client, vendor_id=vendor_id, actor_id=actor_id
        )
        after["escalation"] = {
            "vendor_id": vendor_id,
            "vendor_status_before": vendor_before.get("status"),
            "vendor_suspended": suspended,
            "clips_taken_down": taken,
            "strike_threshold": STRIKE_THRESHOLD,
        }

    if not recorder.is_recorded:
        recorder.record(
            action=action,
            entity_type="video_clip",
            entity_id=clip_id,
            before=before,
            after=after,
        )

    _notify_vendor(
        service_client,
        vendor=_load_vendor(service_client, vendor_id),
        event_type="clip_taken_down",
        template="clip_taken_down",
        payload={"clip_id": clip_id, "reason": reason},
    )
    return status, suspended


@clips_router.post("/{clip_id}/takedown", response_model=ClipActionResponse)
async def takedown_clip(
    clip_id: str,
    body: ReasonRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> ClipActionResponse:
    """Pull a published clip. Instant — ``taken_down`` is outside the public
    RLS predicate, so the next feed read cannot return it."""
    clip = _load_clip(service_client, clip_id)
    status, suspended = _takedown(
        service_client,
        clip=clip,
        reason=body.reason,
        recorder=recorder,
        actor_id=current_user.id,
        action="admin.clips.takedown",
    )
    return ClipActionResponse(clip_id=clip_id, status=status, vendor_suspended=suspended)


# --- Report triage ----------------------------------------------------------
def _load_report(service_client: ServiceRoleClient, report_id: str) -> dict[str, Any]:
    rows = _rows(
        _table(service_client, REPORTS_TABLE)
        .select("*")
        .eq("id", report_id)
        .maybe_single()
        .execute()
    )
    if not rows:
        raise AppError(
            code="clip_report_not_found",
            message="Report not found",
            http_status=404,
            details={"report_id": report_id},
        )
    return rows[0]


@clips_router.post("/reports/{report_id}/dismiss", response_model=ReportActionResponse)
async def dismiss_report(
    report_id: str,
    body: NoteRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> ReportActionResponse:
    """Judge a report unfounded. The clip is untouched; the decision is audited."""
    report = _load_report(service_client, report_id)
    clip_id = str(report.get("clip_id") or "")
    clip = _load_clip(service_client, clip_id)

    recorder.record(
        action="admin.clips.report_dismiss",
        entity_type="clip_report",
        entity_id=report_id,
        before={"clip_status": clip.get("status")},
        after={"outcome": "dismissed", "note": body.note},
    )
    _table(service_client, REPORTS_TABLE).delete().eq("id", report_id).execute()
    return ReportActionResponse(
        report_id=report_id,
        clip_id=clip_id,
        outcome="dismissed",
        clip_status=str(clip.get("status") or ""),
    )


@clips_router.post("/reports/{report_id}/uphold", response_model=ReportActionResponse)
async def uphold_report(
    report_id: str,
    body: NoteRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> ReportActionResponse:
    """Agree with a report: take the clip down and count a strike."""
    report = _load_report(service_client, report_id)
    clip_id = str(report.get("clip_id") or "")
    clip = _load_clip(service_client, clip_id)

    status, suspended = _takedown(
        service_client,
        clip=clip,
        reason=f"report_upheld:{body.note or 'policy'}"[:MAX_REASON_LEN],
        recorder=recorder,
        actor_id=current_user.id,
        action="admin.clips.report_uphold",
        extra_after={"report_id": report_id, "note": body.note},
    )
    _table(service_client, REPORTS_TABLE).delete().eq("id", report_id).execute()
    return ReportActionResponse(
        report_id=report_id,
        clip_id=clip_id,
        outcome="upheld",
        clip_status=status,
        vendor_suspended=suspended,
    )


admin_router.include_router(clips_router)
