from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.admin_base import router as admin_router
from app.services.kyc.state_machine import (
    ServiceRoleClient,
    transition_approve,
    transition_reject,
)
from app.services.notifications.dedupe import enqueue_outbox_row
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator

# Private bucket for KYC documents (declared in M12-P02b / vendor onboarding types).
KYC_DOCS_BUCKET = "kyc-docs"
SIGNED_URL_TTL_SECONDS = 300

SLA_ON_TRACK_HOURS = 24
SLA_DUE_SOON_HOURS = 72

SlaBadge = Literal["on_track", "due_soon", "overdue"]
RejectReasonTemplate = Literal[
    "blurry_document",
    "name_mismatch",
    "expired_id",
    "incomplete_submission",
    "other",
]

kyc_router = APIRouter(prefix="/kyc", tags=["admin-kyc"])


class KycQueueItem(BaseModel):
    id: UUID
    vendor_id: UUID
    vendor_display_name: str
    vendor_slug: str
    tier: int
    status: str
    updated_at: datetime
    sla_badge: SlaBadge
    age_hours: float


class SignedDocUrl(BaseModel):
    path: str
    doc_type: Literal["nrc", "selfie", "other"]
    signed_url: str | None
    expires_at: datetime | None
    ttl_seconds: int


class MomoNameMatchOut(BaseModel):
    phone: str
    operator: str
    resolved_name: str | None
    legal_name: str
    match_score: float
    matched: bool


class KycDetailOut(BaseModel):
    id: UUID
    vendor_id: UUID
    vendor_display_name: str
    vendor_slug: str
    vendor_status: str
    vendor_owner_user_id: UUID
    tier: int
    status: str
    reviewer_notes: str | None
    momo_name_match: MomoNameMatchOut | None
    documents: list[SignedDocUrl]
    updated_at: datetime
    sla_badge: SlaBadge
    age_hours: float
    docs_available: bool


class ApproveKycRequest(BaseModel):
    reviewer_notes: str | None = Field(default=None, max_length=2000)


class RejectKycRequest(BaseModel):
    reason_template: RejectReasonTemplate
    free_text: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_free_text_for_other(self) -> RejectKycRequest:
        if self.reason_template == "other" and not (self.free_text and self.free_text.strip()):
            raise ValueError("free_text is required when reason_template is other")
        return self


def _default_docs_requested() -> list[Literal["nrc", "selfie"]]:
    return ["nrc", "selfie"]


class RequestResubmitRequest(BaseModel):
    reason_template: RejectReasonTemplate
    free_text: str | None = Field(default=None, max_length=2000)
    docs_requested: list[Literal["nrc", "selfie"]] = Field(default_factory=_default_docs_requested)

    @model_validator(mode="after")
    def require_free_text_for_other(self) -> RequestResubmitRequest:
        if self.reason_template == "other" and not (self.free_text and self.free_text.strip()):
            raise ValueError("free_text is required when reason_template is other")
        return self


class KycDecisionResponse(BaseModel):
    kyc_record_id: UUID
    vendor_id: UUID
    vendor_status: str
    kyc_record_status: str
    notification_enqueued: bool


def _table(client: ServiceRoleClient, name: str) -> Any:
    return client.client.table(name)


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    raise AppError(
        code="internal_error",
        message="Invalid timestamp in KYC record",
        http_status=500,
    )


def compute_sla_badge(
    updated_at: datetime, *, now: datetime | None = None
) -> tuple[SlaBadge, float]:
    reference = now or datetime.now(UTC)
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=UTC)
    age = reference - updated_at
    age_hours = age.total_seconds() / 3600.0
    if age_hours < SLA_ON_TRACK_HOURS:
        return "on_track", age_hours
    if age_hours < SLA_DUE_SOON_HOURS:
        return "due_soon", age_hours
    return "overdue", age_hours


def classify_doc_type(path: str) -> Literal["nrc", "selfie", "other"]:
    lowered = path.lower()
    if "nrc" in lowered:
        return "nrc"
    if "selfie" in lowered:
        return "selfie"
    return "other"


def _build_reviewer_notes(
    *,
    reason_template: str,
    free_text: str | None,
    prefix: str | None = None,
) -> str:
    parts: list[str] = []
    if prefix:
        parts.append(prefix)
    parts.append(f"template:{reason_template}")
    if free_text and free_text.strip():
        parts.append(free_text.strip())
    return " | ".join(parts)


def sign_kyc_documents(
    service_client: ServiceRoleClient,
    paths: list[str],
    *,
    now: datetime | None = None,
) -> tuple[list[SignedDocUrl], bool]:
    reference = now or datetime.now(UTC)
    documents: list[SignedDocUrl] = []
    docs_available = True

    storage = getattr(service_client.client, "storage", None)
    if storage is None:
        docs_available = False
        for path in paths:
            documents.append(
                SignedDocUrl(
                    path=path,
                    doc_type=classify_doc_type(path),
                    signed_url=None,
                    expires_at=None,
                    ttl_seconds=SIGNED_URL_TTL_SECONDS,
                )
            )
        return documents, docs_available

    bucket = storage.from_(KYC_DOCS_BUCKET)
    for path in paths:
        signed_url: str | None = None
        expires_at: datetime | None = None
        try:
            result = bucket.create_signed_url(path, SIGNED_URL_TTL_SECONDS)
            if isinstance(result, dict):
                signed_url = (
                    result.get("signedURL")
                    or result.get("signedUrl")
                    or result.get("signed_url")
                )
                expires_in = result.get("expires_in") or result.get("expiresIn")
                if isinstance(expires_in, int | float):
                    expires_at = reference + timedelta(seconds=int(expires_in))
                else:
                    expires_at = reference + timedelta(seconds=SIGNED_URL_TTL_SECONDS)
        except Exception:
            docs_available = False
            signed_url = None
            expires_at = None

        documents.append(
            SignedDocUrl(
                path=path,
                doc_type=classify_doc_type(path),
                signed_url=str(signed_url) if signed_url else None,
                expires_at=expires_at,
                ttl_seconds=SIGNED_URL_TTL_SECONDS,
            )
        )

    return documents, docs_available


def _serialize_momo_match(payload: dict[str, Any] | None) -> MomoNameMatchOut | None:
    if payload is None:
        return None
    return MomoNameMatchOut(
        phone=str(payload.get("phone", "")),
        operator=str(payload.get("operator", "")),
        resolved_name=(
            str(payload["resolved_name"])
            if isinstance(payload.get("resolved_name"), str)
            else None
        ),
        legal_name=str(payload.get("legal_name", "")),
        match_score=float(payload.get("match_score", 0.0)),
        matched=bool(payload.get("matched")),
    )


def _enqueue_vendor_notification(
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


def _load_kyc_record_row(
    service_client: ServiceRoleClient,
    kyc_record_id: str,
) -> dict[str, Any]:
    response = (
        _table(service_client, "kyc_records")
        .select(
            "id, vendor_id, tier, status, doc_storage_paths, momo_name_match, "
            "reviewer_notes, updated_at"
        )
        .eq("id", kyc_record_id)
        .maybe_single()
        .execute()
    )
    data = response.data
    row: dict[str, Any] | None
    if isinstance(data, dict):
        row = data
    elif isinstance(data, list) and data and isinstance(data[0], dict):
        row = data[0]
    else:
        row = None
    if row is None:
        raise AppError(code="not_found", message="KYC record not found", http_status=404)
    return row


def _load_vendor_row(service_client: ServiceRoleClient, vendor_id: str) -> dict[str, Any]:
    response = (
        _table(service_client, "vendors")
        .select("id, owner_user_id, slug, display_name, status, kyc_tier")
        .eq("id", vendor_id)
        .maybe_single()
        .execute()
    )
    data = response.data
    row: dict[str, Any] | None
    if isinstance(data, dict):
        row = data
    elif isinstance(data, list) and data and isinstance(data[0], dict):
        row = data[0]
    else:
        row = None
    if row is None:
        raise AppError(code="not_found", message="Vendor not found", http_status=404)
    return row


def _audit_decision(
    recorder: AdminAuditRecorder,
    *,
    action: str,
    kyc_record_id: str,
    before: dict[str, Any],
    after: dict[str, Any],
) -> None:
    recorder.record(
        action=action,
        entity_type="kyc_record",
        entity_id=kyc_record_id,
        before=before,
        after=after,
    )


def _handle_kyc_decision(
    *,
    kyc_record_id: str,
    service_client: ServiceRoleClient,
    recorder: AdminAuditRecorder,
    action: str,
    before: dict[str, Any],
    after: dict[str, Any],
    event_type: str,
    template: str,
    notification_payload: dict[str, Any],
) -> KycDecisionResponse:
    _audit_decision(
        recorder,
        action=action,
        kyc_record_id=kyc_record_id,
        before=before,
        after=after,
    )
    enqueued = _enqueue_vendor_notification(
        service_client,
        event_type=event_type,
        entity_id=kyc_record_id,
        template=template,
        payload=notification_payload,
    )
    return KycDecisionResponse(
        kyc_record_id=UUID(kyc_record_id),
        vendor_id=UUID(str(after["vendor"]["id"])),
        vendor_status=str(after["vendor"]["status"]),
        kyc_record_status=str(after["kyc_record"]["status"]),
        notification_enqueued=enqueued,
    )


def _snapshot_before_decision(
    service_client: ServiceRoleClient,
    *,
    vendor_id: str,
    kyc_row: dict[str, Any],
) -> dict[str, Any]:
    vendor = _load_vendor_row(service_client, vendor_id)
    return {
        "vendor": {
            "id": vendor["id"],
            "status": vendor["status"],
            "kyc_tier": vendor.get("kyc_tier"),
        },
        "kyc_record": {
            "id": kyc_row["id"],
            "status": kyc_row["status"],
            "tier": kyc_row["tier"],
            "reviewer_notes": kyc_row.get("reviewer_notes"),
        },
    }


@kyc_router.get("", response_model=list[KycQueueItem])
async def list_kyc_queue(
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> list[KycQueueItem]:
    response = (
        _table(service_client, "kyc_records")
        .select("id, vendor_id, tier, status, updated_at")
        .eq("status", "pending")
        .order("updated_at", desc=False)
        .execute()
    )
    rows = response.data if isinstance(response.data, list) else []
    items: list[KycQueueItem] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        vendor = _load_vendor_row(service_client, str(row["vendor_id"]))
        updated_at = _parse_timestamp(row["updated_at"])
        sla_badge, age_hours = compute_sla_badge(updated_at)
        items.append(
            KycQueueItem(
                id=UUID(str(row["id"])),
                vendor_id=UUID(str(row["vendor_id"])),
                vendor_display_name=str(vendor["display_name"]),
                vendor_slug=str(vendor["slug"]),
                tier=int(row["tier"]),
                status=str(row["status"]),
                updated_at=updated_at,
                sla_badge=sla_badge,
                age_hours=round(age_hours, 2),
            )
        )
    return items


@kyc_router.get("/{kyc_record_id}", response_model=KycDetailOut)
async def get_kyc_detail(
    kyc_record_id: UUID,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> KycDetailOut:
    row = _load_kyc_record_row(service_client, str(kyc_record_id))
    vendor = _load_vendor_row(service_client, str(row["vendor_id"]))
    paths_raw = row.get("doc_storage_paths")
    paths = [str(path) for path in paths_raw] if isinstance(paths_raw, list) else []
    documents, docs_available = sign_kyc_documents(service_client, paths)
    momo_raw = row.get("momo_name_match")
    momo = momo_raw if isinstance(momo_raw, dict) else None
    updated_at = _parse_timestamp(row["updated_at"])
    sla_badge, age_hours = compute_sla_badge(updated_at)
    reviewer_notes = row.get("reviewer_notes")
    return KycDetailOut(
        id=UUID(str(row["id"])),
        vendor_id=UUID(str(row["vendor_id"])),
        vendor_display_name=str(vendor["display_name"]),
        vendor_slug=str(vendor["slug"]),
        vendor_status=str(vendor["status"]),
        vendor_owner_user_id=UUID(str(vendor["owner_user_id"])),
        tier=int(row["tier"]),
        status=str(row["status"]),
        reviewer_notes=str(reviewer_notes) if isinstance(reviewer_notes, str) else None,
        momo_name_match=_serialize_momo_match(momo),
        documents=documents,
        updated_at=updated_at,
        sla_badge=sla_badge,
        age_hours=round(age_hours, 2),
        docs_available=docs_available,
    )


@kyc_router.post("/{kyc_record_id}/approve", response_model=KycDecisionResponse)
async def approve_kyc(
    kyc_record_id: UUID,
    body: ApproveKycRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> KycDecisionResponse:
    record_id = str(kyc_record_id)
    row = _load_kyc_record_row(service_client, record_id)
    vendor_id = str(row["vendor_id"])
    tier = int(row["tier"])
    before = _snapshot_before_decision(service_client, vendor_id=vendor_id, kyc_row=row)
    result = transition_approve(
        actor_id=current_user.id,
        vendor_id=vendor_id,
        kyc_record_id=record_id,
        tier=tier,
        reviewer_notes=body.reviewer_notes,
        service_client=service_client,
    )
    vendor = _load_vendor_row(service_client, vendor_id)
    return _handle_kyc_decision(
        kyc_record_id=record_id,
        service_client=service_client,
        recorder=recorder,
        action="admin.kyc.approve",
        before=before,
        after=result,
        event_type="kyc_approved",
        template="kyc_approved",
        notification_payload={
            "vendor_id": vendor_id,
            "owner_user_id": str(vendor["owner_user_id"]),
            "kyc_record_id": record_id,
            "tier": tier,
        },
    )


@kyc_router.post("/{kyc_record_id}/reject", response_model=KycDecisionResponse)
async def reject_kyc(
    kyc_record_id: UUID,
    body: RejectKycRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> KycDecisionResponse:
    record_id = str(kyc_record_id)
    row = _load_kyc_record_row(service_client, record_id)
    vendor_id = str(row["vendor_id"])
    before = _snapshot_before_decision(service_client, vendor_id=vendor_id, kyc_row=row)
    reviewer_notes = _build_reviewer_notes(
        reason_template=body.reason_template,
        free_text=body.free_text,
    )
    result = transition_reject(
        actor_id=current_user.id,
        vendor_id=vendor_id,
        kyc_record_id=record_id,
        reviewer_notes=reviewer_notes,
        service_client=service_client,
    )
    vendor = _load_vendor_row(service_client, vendor_id)
    return _handle_kyc_decision(
        kyc_record_id=record_id,
        service_client=service_client,
        recorder=recorder,
        action="admin.kyc.reject",
        before=before,
        after=result,
        event_type="kyc_rejected",
        template="kyc_rejected",
        notification_payload={
            "vendor_id": vendor_id,
            "owner_user_id": str(vendor["owner_user_id"]),
            "kyc_record_id": record_id,
            "reason_template": body.reason_template,
            "reviewer_notes": reviewer_notes,
        },
    )


@kyc_router.post("/{kyc_record_id}/request-resubmit", response_model=KycDecisionResponse)
async def request_kyc_resubmit(
    kyc_record_id: UUID,
    body: RequestResubmitRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> KycDecisionResponse:
    record_id = str(kyc_record_id)
    row = _load_kyc_record_row(service_client, record_id)
    vendor_id = str(row["vendor_id"])
    before = _snapshot_before_decision(service_client, vendor_id=vendor_id, kyc_row=row)
    reviewer_notes = _build_reviewer_notes(
        reason_template=body.reason_template,
        free_text=body.free_text,
        prefix=f"resubmit_request:docs={','.join(body.docs_requested)}",
    )
    result = transition_reject(
        actor_id=current_user.id,
        vendor_id=vendor_id,
        kyc_record_id=record_id,
        reviewer_notes=reviewer_notes,
        service_client=service_client,
    )
    vendor = _load_vendor_row(service_client, vendor_id)
    return _handle_kyc_decision(
        kyc_record_id=record_id,
        service_client=service_client,
        recorder=recorder,
        action="admin.kyc.request_resubmit",
        before=before,
        after=result,
        event_type="kyc_resubmit_requested",
        template="kyc_resubmit_requested",
        notification_payload={
            "vendor_id": vendor_id,
            "owner_user_id": str(vendor["owner_user_id"]),
            "kyc_record_id": record_id,
            "reason_template": body.reason_template,
            "docs_requested": body.docs_requested,
            "reviewer_notes": reviewer_notes,
        },
    )


admin_router.include_router(kyc_router)
