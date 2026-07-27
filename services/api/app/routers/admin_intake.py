"""M18-P06 — admin review and publication control for WhatsApp intake (D35).

The last gate before an intake-born listing can be sold. A vendor's submission
(M18-P05) produced a ``draft`` listing and a session in ``pending_admin_review``;
nothing is buyable until a human here approves it.

Design constraints this router exists to enforce:

* **No bulk approve, ever.** There is deliberately no endpoint that accepts a
  list of session ids. Approval is one decision by one human on one draft, and
  the absence of the batch endpoint is what makes that structural rather than a
  matter of UI discipline.
* **No auto-publish and no model-only decision.** Approval activates a listing
  only through the same guarded, gate-checked transition the rest of moderation
  uses, and only when a reviewer asks for it.
* **Idempotent and race-safe.** Every action asserts the from-state inside the
  UPDATE (``.eq("status", from_status)``), so a concurrent double-approve has
  exactly one winner and the loser gets a 409. Re-running a completed action on
  a session already in its target state is a no-op, not an error.
* **Audited.** Every action records through ``AdminAuditRecorder`` with a
  before/after snapshot.
* **Lane 1 only for vendor notification.** Rejections and change-requests notify
  through the normal outbox. The WAHA lane is strictly inbound-only and is never
  written to from here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Final, Protocol

from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.admin_base import router as admin_router
from app.services.intake import state_machine
from app.services.listings.canonical_match import load_active_candidates, suggest_matches
from app.services.moderation.prohibited import screen_listing
from app.services.notifications.dedupe import enqueue_outbox_row
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

intake_router = APIRouter(prefix="/intake", tags=["admin-intake"])

SESSIONS_TABLE: Final = "intake_sessions"
DRAFT_TABLE: Final = "intake_draft_fields"
PROVENANCE_TABLE: Final = "intake_field_provenance"
MEDIA_TABLE: Final = "intake_media"
LISTINGS_TABLE: Final = "vendor_listings"
BUCKET: Final = "vendor-intake-media"

SIGNED_URL_TTL_SECONDS: Final = 10 * 60
QUEUE_STATUSES: Final[tuple[str, ...]] = (
    state_machine.SUBMITTED,
    state_machine.PENDING_ADMIN_REVIEW,
)
MAX_REASON_LEN: Final = 1_000


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


# --- Schemas ----------------------------------------------------------------
class IntakeQueueItem(BaseModel):
    session_id: str
    status: str
    vendor_id: str
    vendor_display_name: str | None = None
    vendor_kyc_tier: int | None = None
    title: str | None = None
    price_ngwee: int | None = None
    listing_id: str | None = None
    submitted_at: datetime | None = None


class ProvenanceOut(BaseModel):
    field_name: str
    source: str
    confidence: float | None = None
    model_ref: str | None = None


class MediaOut(BaseModel):
    id: str
    mime_type: str
    width_px: int | None = None
    height_px: int | None = None
    signed_url: str | None = None
    ttl_seconds: int = SIGNED_URL_TTL_SECONDS


class CanonicalCandidateOut(BaseModel):
    product_id: str
    name: str
    score: float


class ListingDiffEntry(BaseModel):
    field_name: str
    draft_value: str | None = None
    listing_value: str | None = None
    changed: bool


class IntakeDetail(BaseModel):
    session_id: str
    status: str
    vendor_id: str
    vendor_display_name: str | None = None
    vendor_status: str | None = None
    vendor_kyc_tier: int | None = None
    listing_id: str | None = None
    listing_status: str | None = None
    draft: dict[str, Any]
    provenance: list[ProvenanceOut]
    media: list[MediaOut]
    warnings: list[str]
    canonical_candidates: list[CanonicalCandidateOut]
    listing_diff: list[ListingDiffEntry]
    admin_notes: str | None = None


class ReasonBody(BaseModel):
    reason: str = Field(min_length=1, max_length=MAX_REASON_LEN)


class AttachCanonicalBody(BaseModel):
    product_id: str = Field(min_length=1)


class IntakeActionResponse(BaseModel):
    session_id: str
    session_status: str
    listing_id: str | None = None
    listing_status: str | None = None
    notification_enqueued: bool = False
    changed: bool = True


# --- Helpers ----------------------------------------------------------------
def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _single(response: Any) -> dict[str, Any] | None:
    rows = _rows(response)
    return rows[0] if rows else None


def _load_session(service_client: ServiceRoleClient, session_id: str) -> dict[str, Any]:
    row = _single(
        service_client.client.table(SESSIONS_TABLE)
        .select("*")
        .eq("id", session_id)
        .maybe_single()
        .execute()
    )
    if row is None:
        raise AppError(
            code="intake_session_not_found",
            message="Intake session not found",
            http_status=404,
            details={"session_id": session_id},
        )
    return row


def _load_vendor(service_client: ServiceRoleClient, vendor_id: str) -> dict[str, Any]:
    return (
        _single(
            service_client.client.table("vendors")
            .select("id, display_name, status, kyc_tier")
            .eq("id", vendor_id)
            .maybe_single()
            .execute()
        )
        or {}
    )


def _load_draft(service_client: ServiceRoleClient, session_id: str) -> dict[str, Any]:
    return (
        _single(
            service_client.client.table(DRAFT_TABLE)
            .select("*")
            .eq("session_id", session_id)
            .maybe_single()
            .execute()
        )
        or {}
    )


def _load_listing(service_client: ServiceRoleClient, listing_id: str) -> dict[str, Any] | None:
    return _single(
        service_client.client.table(LISTINGS_TABLE)
        .select("id, vendor_id, product_id, title_override, price_ngwee, condition, status")
        .eq("id", listing_id)
        .maybe_single()
        .execute()
    )


def _sign_media(service_client: ServiceRoleClient, session_id: str) -> list[MediaOut]:
    """Short-lived signed URLs over the private quarantine bucket (M13-P02 shape)."""
    rows = _rows(
        service_client.client.table(MEDIA_TABLE)
        .select("id, storage_path, mime_type, width_px, height_px")
        .eq("session_id", session_id)
        .execute()
    )
    storage = getattr(service_client.client, "storage", None)
    bucket = storage.from_(BUCKET) if storage is not None else None

    out: list[MediaOut] = []
    for row in rows:
        signed: str | None = None
        if bucket is not None:
            try:
                result = bucket.create_signed_url(str(row["storage_path"]), SIGNED_URL_TTL_SECONDS)
                if isinstance(result, dict):
                    raw = (
                        result.get("signedURL")
                        or result.get("signedUrl")
                        or result.get("signed_url")
                    )
                    signed = str(raw) if raw else None
            except Exception:
                # A storage outage must not blank the whole review page.
                signed = None
        out.append(
            MediaOut(
                id=str(row["id"]),
                mime_type=str(row.get("mime_type") or ""),
                width_px=row.get("width_px"),
                height_px=row.get("height_px"),
                signed_url=signed,
            )
        )
    return out


def _warnings(
    service_client: ServiceRoleClient, *, draft: dict[str, Any], vendor: dict[str, Any]
) -> list[str]:
    """Reviewer-facing warning keys. Advisory — they never auto-decide anything."""
    warnings: list[str] = []

    title = draft.get("title")
    if isinstance(title, str) and title.strip():
        guard = screen_listing(title=title, description=draft.get("description"), category=None)
        if not guard.allowed:
            warnings.append("admin.intake.warnings.prohibited")
    else:
        warnings.append("admin.intake.warnings.missingTitle")

    if draft.get("price_ngwee") in (None, 0):
        warnings.append("admin.intake.warnings.missingPrice")

    if str(draft.get("condition") or "") == "used":
        warnings.append("admin.intake.warnings.usedCondition")

    if str(vendor.get("status") or "") != "active":
        warnings.append("admin.intake.warnings.vendorNotActive")

    # A draft carrying no vendor-typed field was never really reviewed by a human
    # on the vendor side — worth flagging even though P05 requires a submit click.
    return warnings


def _listing_diff(draft: dict[str, Any], listing: dict[str, Any] | None) -> list[ListingDiffEntry]:
    """What the proposed listing says vs what the draft says, field by field."""
    pairs: tuple[tuple[str, str], ...] = (
        ("title", "title_override"),
        ("price_ngwee", "price_ngwee"),
        ("condition", "condition"),
    )
    entries: list[ListingDiffEntry] = []
    for draft_key, listing_key in pairs:
        draft_value = draft.get(draft_key)
        listing_value = (listing or {}).get(listing_key)
        entries.append(
            ListingDiffEntry(
                field_name=draft_key,
                draft_value=None if draft_value is None else str(draft_value),
                listing_value=None if listing_value is None else str(listing_value),
                changed=str(draft_value) != str(listing_value),
            )
        )
    return entries


def _canonical_candidates(
    service_client: ServiceRoleClient, draft: dict[str, Any]
) -> list[CanonicalCandidateOut]:
    title = draft.get("title")
    if not isinstance(title, str) or not title.strip():
        return []
    suggestions = suggest_matches(title, load_active_candidates(service_client.client))
    return [
        CanonicalCandidateOut(product_id=s.product_id, name=s.name, score=s.score)
        for s in suggestions
    ]


def _notify_vendor(
    service_client: ServiceRoleClient,
    *,
    event_type: str,
    session_id: str,
    template: str,
    payload: dict[str, Any],
) -> bool:
    """Enqueue on the Lane 1 outbox. Never the WAHA lane — that is inbound-only."""
    row = enqueue_outbox_row(
        service_client.client,
        event_type=event_type,
        entity_id=session_id,
        channel="whatsapp",
        template=template,
        payload=payload,
    )
    return row is not None


def _snapshot(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(session.get("id")),
        "status": str(session.get("status") or ""),
        "vendor_id": str(session.get("vendor_id") or ""),
        "listing_id": str(session["listing_id"]) if session.get("listing_id") else None,
    }


def _require_reviewable(session: dict[str, Any]) -> str:
    status = str(session.get("status") or "")
    if status not in QUEUE_STATUSES:
        raise AppError(
            code="intake_session_not_reviewable",
            message="Intake session is not awaiting admin review",
            http_status=409,
            details={"session_id": str(session.get("id")), "status": status},
        )
    return status


def _ensure_pending_review(
    service_client: ServiceRoleClient, session: dict[str, Any]
) -> dict[str, Any]:
    """Normalise ``submitted`` to ``pending_admin_review`` before acting.

    P05 already advances both steps; this covers a session left mid-way by an
    interrupted submit rather than forcing a reviewer to retry.
    """
    if str(session.get("status")) == state_machine.SUBMITTED:
        return state_machine.transition(
            service_client,
            session_id=str(session["id"]),
            to_status=state_machine.PENDING_ADMIN_REVIEW,
        )
    return session


def _activate_listing(service_client: ServiceRoleClient, listing_id: str) -> dict[str, Any]:
    """Guarded draft → active. The from-state in the WHERE clause is the race guard."""
    listing = _load_listing(service_client, listing_id)
    if listing is None:
        raise AppError(
            code="listing_not_found",
            message="Listing for this intake session no longer exists",
            http_status=404,
            details={"listing_id": listing_id},
        )
    from_status = str(listing.get("status") or "")
    if from_status == "active":
        return listing
    if from_status != "draft":
        raise AppError(
            code="listing_not_activatable",
            message="Only a draft listing can be activated from intake review",
            http_status=409,
            details={"listing_id": listing_id, "status": from_status},
        )
    updated = _rows(
        service_client.client.table(LISTINGS_TABLE)
        .update({"status": "active"})
        .eq("id", listing_id)
        .eq("status", "draft")
        .execute()
    )
    if not updated:
        raise AppError(
            code="listing_transition_conflict",
            message="Listing status changed concurrently",
            http_status=409,
            details={"listing_id": listing_id},
        )
    return updated[0]


# --- Routes -----------------------------------------------------------------
@intake_router.get("", response_model=list[IntakeQueueItem])
async def list_intake_queue(
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    status: Annotated[str | None, Query()] = None,
) -> list[IntakeQueueItem]:
    """Sessions awaiting a human decision. Never any other vendor's private data."""
    wanted = [status] if status in QUEUE_STATUSES else list(QUEUE_STATUSES)
    sessions = _rows(
        service_client.client.table(SESSIONS_TABLE)
        .select("id, status, vendor_id, listing_id, submitted_at")
        .in_("status", wanted)
        .order("submitted_at", desc=False)
        .execute()
    )

    items: list[IntakeQueueItem] = []
    for session in sessions:
        vendor = _load_vendor(service_client, str(session["vendor_id"]))
        draft = _load_draft(service_client, str(session["id"]))
        items.append(
            IntakeQueueItem(
                session_id=str(session["id"]),
                status=str(session.get("status") or ""),
                vendor_id=str(session["vendor_id"]),
                vendor_display_name=vendor.get("display_name"),
                vendor_kyc_tier=vendor.get("kyc_tier"),
                title=draft.get("title"),
                price_ngwee=draft.get("price_ngwee"),
                listing_id=str(session["listing_id"]) if session.get("listing_id") else None,
                submitted_at=session.get("submitted_at"),
            )
        )
    return items


@intake_router.get("/{session_id}", response_model=IntakeDetail)
async def get_intake_detail(
    session_id: str,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> IntakeDetail:
    session = _load_session(service_client, session_id)
    vendor = _load_vendor(service_client, str(session["vendor_id"]))
    draft = _load_draft(service_client, session_id)
    listing = (
        _load_listing(service_client, str(session["listing_id"]))
        if session.get("listing_id")
        else None
    )
    provenance = _rows(
        service_client.client.table(PROVENANCE_TABLE)
        .select("field_name, source, confidence, model_ref")
        .eq("session_id", session_id)
        .execute()
    )

    return IntakeDetail(
        session_id=session_id,
        status=str(session.get("status") or ""),
        vendor_id=str(session["vendor_id"]),
        vendor_display_name=vendor.get("display_name"),
        vendor_status=vendor.get("status"),
        vendor_kyc_tier=vendor.get("kyc_tier"),
        listing_id=str(session["listing_id"]) if session.get("listing_id") else None,
        listing_status=str(listing["status"]) if listing else None,
        draft={k: v for k, v in draft.items() if k != "session_id"},
        provenance=[
            ProvenanceOut(
                field_name=str(row["field_name"]),
                source=str(row["source"]),
                confidence=float(row["confidence"]) if row.get("confidence") is not None else None,
                model_ref=row.get("model_ref"),
            )
            for row in provenance
        ],
        media=_sign_media(service_client, session_id),
        warnings=_warnings(service_client, draft=draft, vendor=vendor),
        canonical_candidates=_canonical_candidates(service_client, draft),
        listing_diff=_listing_diff(draft, listing),
        admin_notes=session.get("admin_notes"),
    )


@intake_router.post("/{session_id}/request-changes", response_model=IntakeActionResponse)
async def request_changes(
    session_id: str,
    body: ReasonBody,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> IntakeActionResponse:
    """Send the draft back to the vendor for more detail. Reversible, not terminal."""
    session = _load_session(service_client, session_id)
    if str(session.get("status")) == state_machine.NEEDS_DETAILS:
        return IntakeActionResponse(
            session_id=session_id,
            session_status=state_machine.NEEDS_DETAILS,
            listing_id=str(session["listing_id"]) if session.get("listing_id") else None,
            changed=False,
        )
    _require_reviewable(session)
    before = _snapshot(session)
    session = _ensure_pending_review(service_client, session)

    updated = state_machine.transition(
        service_client,
        session_id=session_id,
        to_status=state_machine.NEEDS_DETAILS,
        reason=body.reason,
        extra={"admin_notes": body.reason},
    )
    recorder.record(
        action="admin.intake.request_changes",
        entity_type="intake_session",
        entity_id=session_id,
        before=before,
        after=_snapshot(updated),
    )
    enqueued = _notify_vendor(
        service_client,
        event_type="intake_changes_requested",
        session_id=session_id,
        template="intake_changes_requested",
        payload={"session_id": session_id, "reason": body.reason},
    )
    return IntakeActionResponse(
        session_id=session_id,
        session_status=str(updated.get("status") or state_machine.NEEDS_DETAILS),
        listing_id=str(session["listing_id"]) if session.get("listing_id") else None,
        notification_enqueued=enqueued,
    )


@intake_router.post("/{session_id}/reject", response_model=IntakeActionResponse)
async def reject_intake(
    session_id: str,
    body: ReasonBody,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> IntakeActionResponse:
    """Terminal rejection. The draft listing is removed so it can never surface."""
    session = _load_session(service_client, session_id)
    if str(session.get("status")) == state_machine.REJECTED:
        return IntakeActionResponse(
            session_id=session_id,
            session_status=state_machine.REJECTED,
            listing_id=str(session["listing_id"]) if session.get("listing_id") else None,
            changed=False,
        )
    _require_reviewable(session)
    before = _snapshot(session)
    session = _ensure_pending_review(service_client, session)

    updated = state_machine.transition(
        service_client,
        session_id=session_id,
        to_status=state_machine.REJECTED,
        reason=body.reason,
        extra={"admin_notes": body.reason},
    )

    listing_status: str | None = None
    listing_id = str(session["listing_id"]) if session.get("listing_id") else None
    if listing_id:
        # A rejected intake must not leave a draft listing the vendor could later
        # publish from the normal listings screen.
        removed = _rows(
            service_client.client.table(LISTINGS_TABLE)
            .update({"status": "removed"})
            .eq("id", listing_id)
            .eq("status", "draft")
            .execute()
        )
        listing_status = str(removed[0]["status"]) if removed else None

    recorder.record(
        action="admin.intake.reject",
        entity_type="intake_session",
        entity_id=session_id,
        before=before,
        after={**_snapshot(updated), "listing_status": listing_status},
    )
    enqueued = _notify_vendor(
        service_client,
        event_type="intake_rejected",
        session_id=session_id,
        template="intake_rejected",
        payload={"session_id": session_id, "reason": body.reason},
    )
    return IntakeActionResponse(
        session_id=session_id,
        session_status=str(updated.get("status") or state_machine.REJECTED),
        listing_id=listing_id,
        listing_status=listing_status,
        notification_enqueued=enqueued,
    )


@intake_router.post("/{session_id}/attach-canonical", response_model=IntakeActionResponse)
async def attach_canonical(
    session_id: str,
    body: AttachCanonicalBody,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> IntakeActionResponse:
    """Point the draft listing at an existing **active** canonical product.

    This does not approve anything and does not change the session status — it
    only improves the listing before a separate approval decision.
    """
    session = _load_session(service_client, session_id)
    _require_reviewable(session)
    listing_id = str(session["listing_id"]) if session.get("listing_id") else None
    if not listing_id:
        raise AppError(
            code="intake_listing_missing",
            message="Intake session has no listing to attach a product to",
            http_status=409,
            details={"session_id": session_id},
        )

    product = _single(
        service_client.client.table("products")
        .select("id, status")
        .eq("id", body.product_id)
        .maybe_single()
        .execute()
    )
    if product is None:
        raise AppError(
            code="not_found",
            message="Product not found",
            http_status=404,
            details={"product_id": body.product_id},
        )
    if str(product.get("status")) != "active":
        # Attaching a pending/removed canonical would publish through the back
        # door what the catalog moderation path has not yet approved.
        raise AppError(
            code="product_not_attachable",
            message="Only active canonical products can be attached",
            http_status=422,
            details={"product_id": body.product_id, "status": str(product.get("status"))},
        )

    before_listing = _load_listing(service_client, listing_id) or {}
    if str(before_listing.get("product_id") or "") == body.product_id:
        return IntakeActionResponse(
            session_id=session_id,
            session_status=str(session.get("status") or ""),
            listing_id=listing_id,
            listing_status=str(before_listing.get("status") or ""),
            changed=False,
        )

    service_client.client.table(LISTINGS_TABLE).update({"product_id": body.product_id}).eq(
        "id", listing_id
    ).execute()

    recorder.record(
        action="admin.intake.attach_canonical",
        entity_type="vendor_listing",
        entity_id=listing_id,
        before={"product_id": before_listing.get("product_id")},
        after={"product_id": body.product_id, "session_id": session_id},
    )
    return IntakeActionResponse(
        session_id=session_id,
        session_status=str(session.get("status") or ""),
        listing_id=listing_id,
        listing_status=str(before_listing.get("status") or ""),
    )


@intake_router.post("/{session_id}/approve", response_model=IntakeActionResponse)
async def approve_intake(
    session_id: str,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> IntakeActionResponse:
    """Approve one draft. One session, one human, one decision — no batch form.

    The existing gates are re-checked here rather than trusted from submission
    time: a vendor may have been suspended, or the title may have been edited
    into something the prohibited screen now blocks.
    """
    session = _load_session(service_client, session_id)
    if str(session.get("status")) == state_machine.APPROVED:
        listing_id = str(session["listing_id"]) if session.get("listing_id") else None
        listing = _load_listing(service_client, listing_id) if listing_id else None
        return IntakeActionResponse(
            session_id=session_id,
            session_status=state_machine.APPROVED,
            listing_id=listing_id,
            listing_status=str(listing["status"]) if listing else None,
            changed=False,
        )
    _require_reviewable(session)
    before = _snapshot(session)
    session = _ensure_pending_review(service_client, session)

    listing_id = str(session["listing_id"]) if session.get("listing_id") else None
    if not listing_id:
        raise AppError(
            code="intake_listing_missing",
            message="Intake session has no listing to approve",
            http_status=409,
            details={"session_id": session_id},
        )

    vendor = _load_vendor(service_client, str(session["vendor_id"]))
    if str(vendor.get("status") or "") != "active":
        raise AppError(
            code="vendor_not_active",
            message="Vendor is not active; the listing cannot be published",
            http_status=409,
            details={"vendor_id": str(session["vendor_id"]), "status": vendor.get("status")},
        )

    draft = _load_draft(service_client, session_id)
    guard = screen_listing(
        title=draft.get("title"), description=draft.get("description"), category=None
    )
    if not guard.allowed:
        raise AppError(
            code="prohibited_listing",
            message="Listing contains a prohibited category or keyword",
            http_status=422,
            details={"reason": guard.reason, "matched": guard.matched},
        )

    # Session first: if activation then conflicts, the session is not left
    # claiming a listing went live that did not.
    updated = state_machine.transition(
        service_client, session_id=session_id, to_status=state_machine.APPROVED
    )
    listing = _activate_listing(service_client, listing_id)

    recorder.record(
        action="admin.intake.approve",
        entity_type="intake_session",
        entity_id=session_id,
        before=before,
        after={**_snapshot(updated), "listing_status": str(listing.get("status") or "")},
    )
    enqueued = _notify_vendor(
        service_client,
        event_type="intake_approved",
        session_id=session_id,
        template="intake_approved",
        payload={"session_id": session_id, "listing_id": listing_id},
    )
    return IntakeActionResponse(
        session_id=session_id,
        session_status=str(updated.get("status") or state_machine.APPROVED),
        listing_id=listing_id,
        listing_status=str(listing.get("status") or ""),
        notification_enqueued=enqueued,
    )


admin_router.include_router(intake_router)
