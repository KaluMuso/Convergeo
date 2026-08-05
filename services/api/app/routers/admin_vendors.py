from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.core.auth import CurrentUser, require_moderator
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.admin_base import router as admin_router
from app.routers.admin_kyc import (
    KycDecisionResponse,
    RejectReasonTemplate,
    _build_reviewer_notes,
    _handle_kyc_decision,
    _load_kyc_record_row,
    _load_vendor_row,
    _snapshot_before_decision,
    compute_sla_badge,
    sign_kyc_documents,
)
from app.services.kyc.state_machine import (
    ServiceRoleClient,
    transition_approve,
    transition_reject,
)
from app.services.webhooks.n8n_dispatch import schedule_n8n_webhook
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel, Field, model_validator

REVIEW_QUEUE_STATUSES = ("submitted", "under_review", "pending")
VENDOR_PENDING_STATUSES = frozenset({"pending_kyc", "pending"})

vendors_router = APIRouter(prefix="/vendors", tags=["admin-vendors"])


class VendorQueueItem(BaseModel):
    vendor_id: UUID
    kyc_record_id: UUID | None = None
    display_name: str
    slug: str
    vendor_status: str
    kyc_tier: int | None = None
    kyc_record_status: str | None = None
    tier: int | None = None
    updated_at: datetime
    sla_badge: Literal["on_track", "due_soon", "overdue"] | None = None
    age_hours: float | None = None


class VendorKycDetail(BaseModel):
    vendor_id: UUID
    kyc_record_id: UUID
    vendor_display_name: str
    vendor_slug: str
    vendor_status: str
    tier: int
    kyc_record_status: str
    documents: list[dict[str, Any]]
    docs_available: bool
    momo_name_match: dict[str, Any] | None = None
    updated_at: datetime


class VendorStatusPatch(BaseModel):
    action: Literal["approve", "reject"]
    reason: str | None = Field(default=None, max_length=2000)
    reason_template: RejectReasonTemplate | None = None
    reviewer_notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_reject_reason(self) -> VendorStatusPatch:
        if self.action == "reject":
            has_reason = bool(self.reason and self.reason.strip())
            has_template = self.reason_template is not None
            if not has_reason and not has_template:
                raise ValueError("reason or reason_template is required when action is reject")
        return self


def _table(client: ServiceRoleClient, name: str) -> Any:
    return client.client.table(name)


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    raise AppError(
        code="internal_error",
        message="Invalid timestamp",
        http_status=500,
    )


def _normalize_vendor_status_filter(status: str) -> str:
    normalized = status.strip().lower()
    if normalized in {"pending", "pending_kyc"}:
        return "pending_kyc"
    return normalized


def _find_reviewable_kyc_record(
    service_client: ServiceRoleClient,
    vendor_id: str,
) -> dict[str, Any] | None:
    response = (
        _table(service_client, "kyc_records")
        .select("id, vendor_id, tier, status, updated_at")
        .eq("vendor_id", vendor_id)
        .in_("status", list(REVIEW_QUEUE_STATUSES))
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = response.data if isinstance(response.data, list) else []
    if not rows:
        return None
    row = rows[0]
    return row if isinstance(row, dict) else None


@vendors_router.get("", response_model=list[VendorQueueItem])
async def list_vendors_for_moderation(
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    status: Annotated[str, Query(min_length=1, max_length=40)] = "pending",
) -> list[VendorQueueItem]:
    """List vendors awaiting KYC review (``status=pending`` → ``pending_kyc``)."""
    vendor_status = _normalize_vendor_status_filter(status)
    if vendor_status != "pending_kyc":
        raise AppError(
            code="validation_error",
            message="Only pending vendor status is supported for the KYC queue",
            http_status=422,
            details={"status": status},
        )

    response = (
        _table(service_client, "vendors")
        .select("id, slug, display_name, status, kyc_tier, updated_at")
        .eq("status", vendor_status)
        .order("updated_at", desc=False)
        .execute()
    )
    rows = response.data if isinstance(response.data, list) else []
    items: list[VendorQueueItem] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        vendor_id = str(row["id"])
        kyc_row = _find_reviewable_kyc_record(service_client, vendor_id)
        updated_at = _parse_timestamp(kyc_row["updated_at"] if kyc_row else row["updated_at"])
        sla_badge: Literal["on_track", "due_soon", "overdue"] | None = None
        age_hours: float | None = None
        if kyc_row is not None:
            sla_badge, age_hours = compute_sla_badge(updated_at)
            age_hours = round(age_hours, 2)
        items.append(
            VendorQueueItem(
                vendor_id=UUID(vendor_id),
                kyc_record_id=UUID(str(kyc_row["id"])) if kyc_row else None,
                display_name=str(row["display_name"]),
                slug=str(row["slug"]),
                vendor_status=str(row["status"]),
                kyc_tier=int(row["kyc_tier"]) if row.get("kyc_tier") is not None else None,
                kyc_record_status=str(kyc_row["status"]) if kyc_row else None,
                tier=int(kyc_row["tier"]) if kyc_row else None,
                updated_at=updated_at,
                sla_badge=sla_badge,
                age_hours=age_hours,
            )
        )
    return items


@vendors_router.get("/{vendor_id}/kyc", response_model=VendorKycDetail)
async def get_vendor_kyc_detail(
    vendor_id: UUID,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> VendorKycDetail:
    vendor = _load_vendor_row(service_client, str(vendor_id))
    kyc_row = _find_reviewable_kyc_record(service_client, str(vendor_id))
    if kyc_row is None:
        raise AppError(
            code="not_found",
            message="No pending KYC submission for this vendor",
            http_status=404,
        )
    record = _load_kyc_record_row(service_client, str(kyc_row["id"]))
    paths_raw = record.get("doc_storage_paths")
    paths = [str(path) for path in paths_raw] if isinstance(paths_raw, list) else []
    documents, docs_available = sign_kyc_documents(service_client, paths)
    momo_raw = record.get("momo_name_match")
    updated_at = _parse_timestamp(record["updated_at"])
    return VendorKycDetail(
        vendor_id=UUID(str(vendor["id"])),
        kyc_record_id=UUID(str(record["id"])),
        vendor_display_name=str(vendor["display_name"]),
        vendor_slug=str(vendor["slug"]),
        vendor_status=str(vendor["status"]),
        tier=int(record["tier"]),
        kyc_record_status=str(record["status"]),
        documents=[doc.model_dump(mode="json") for doc in documents],
        docs_available=docs_available,
        momo_name_match=momo_raw if isinstance(momo_raw, dict) else None,
        updated_at=updated_at,
    )


@vendors_router.patch("/{vendor_id}/status", response_model=KycDecisionResponse)
async def patch_vendor_kyc_status(
    vendor_id: UUID,
    body: VendorStatusPatch,
    background_tasks: BackgroundTasks,
    current_user: Annotated[CurrentUser, Depends(require_moderator())],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> KycDecisionResponse:
    """Approve or reject a vendor's pending KYC submission."""
    vendor_id_str = str(vendor_id)
    vendor = _load_vendor_row(service_client, vendor_id_str)
    kyc_row = _find_reviewable_kyc_record(service_client, vendor_id_str)
    if kyc_row is None:
        raise AppError(
            code="not_found",
            message="No pending KYC submission for this vendor",
            http_status=404,
        )

    record_id = str(kyc_row["id"])
    row = _load_kyc_record_row(service_client, record_id)
    tier = int(row["tier"])
    before = _snapshot_before_decision(service_client, vendor_id=vendor_id_str, kyc_row=row)

    if body.action == "approve":
        result = transition_approve(
            actor_id=current_user.id,
            vendor_id=vendor_id_str,
            kyc_record_id=record_id,
            tier=tier,
            reviewer_notes=body.reviewer_notes,
            service_client=service_client,
        )
        event_type = "kyc_approved"
        template = "kyc_approved"
        action = "admin.vendors.approve_kyc"
        notification_payload = {
            "vendor_id": vendor_id_str,
            "owner_user_id": str(vendor["owner_user_id"]),
            "kyc_record_id": record_id,
            "tier": tier,
        }
        n8n_status = "approved"
    else:
        if body.reason_template is not None:
            reviewer_notes = _build_reviewer_notes(
                reason_template=body.reason_template,
                free_text=body.reason,
            )
        else:
            reviewer_notes = (body.reason or "").strip()
        result = transition_reject(
            actor_id=current_user.id,
            vendor_id=vendor_id_str,
            kyc_record_id=record_id,
            reviewer_notes=reviewer_notes,
            service_client=service_client,
        )
        event_type = "kyc_rejected"
        template = "kyc_rejected"
        action = "admin.vendors.reject_kyc"
        notification_payload = {
            "vendor_id": vendor_id_str,
            "owner_user_id": str(vendor["owner_user_id"]),
            "kyc_record_id": record_id,
            "reason_template": body.reason_template,
            "reviewer_notes": reviewer_notes,
        }
        n8n_status = "rejected"

    response = _handle_kyc_decision(
        kyc_record_id=record_id,
        service_client=service_client,
        recorder=recorder,
        action=action,
        before=before,
        after=result,
        event_type=event_type,
        template=template,
        notification_payload=notification_payload,
    )

    schedule_n8n_webhook(
        background_tasks,
        event="vendor.kyc_updated",
        data={
            "vendor_id": vendor_id_str,
            "kyc_record_id": record_id,
            "status": n8n_status,
            "vendor_status": str(result["vendor"]["status"]),
            "kyc_tier": result["vendor"].get("kyc_tier"),
            "tier": tier,
            "actor_id": current_user.id,
        },
    )

    return response


admin_router.include_router(vendors_router)
