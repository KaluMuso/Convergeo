from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from app.core.admin_audit import (
    AdminAuditedRoute,
    AdminAuditRecorder,
    get_admin_audit_recorder,
)
from app.core.auth import require_role
from app.deps import get_supabase_client
from app.services.business.access import ServiceRoleClient
from app.services.business.store import load_by_id, set_decision
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

# Self-contained admin router (own admin guard + audit route class) mounted at
# /admin/business, discovered directly by app.main — no shared-router mutation.
router = APIRouter(
    prefix="/admin/business",
    tags=["admin-business"],
    route_class=AdminAuditedRoute,
    dependencies=[Depends(require_role("admin"))],
)


class BusinessBuyerOut(BaseModel):
    id: str
    user_id: str
    legal_name: str
    registration_no: str
    tpin: str | None = None
    status: str
    reviewer_notes: str | None = None
    verified_at: str | None = None
    created_at: str | None = None


class VerifyBusinessRequest(BaseModel):
    reviewer_notes: str | None = Field(default=None, max_length=1000)


class RejectBusinessRequest(BaseModel):
    reviewer_notes: str = Field(min_length=3, max_length=1000)


def _serialize(row: dict[str, Any]) -> BusinessBuyerOut:
    return BusinessBuyerOut(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        legal_name=str(row.get("legal_name") or ""),
        registration_no=str(row.get("registration_no") or ""),
        tpin=str(row["tpin"]) if row.get("tpin") else None,
        status=str(row.get("status") or ""),
        reviewer_notes=str(row["reviewer_notes"]) if row.get("reviewer_notes") else None,
        verified_at=str(row["verified_at"]) if row.get("verified_at") else None,
        created_at=str(row["created_at"]) if row.get("created_at") else None,
    )


@router.get("", response_model=list[BusinessBuyerOut])
async def list_business_buyers(
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    status: Annotated[
        Literal["pending", "verified", "rejected", "suspended"] | None, Query()
    ] = None,
) -> list[BusinessBuyerOut]:
    query = (
        service.client.table("business_buyers")
        .select(
            "id, user_id, legal_name, registration_no, tpin, status, "
            "reviewer_notes, verified_at, created_at"
        )
        .order("created_at", desc=True)
        .limit(100)
    )
    if status is not None:
        query = query.eq("status", status)
    response = query.execute()
    rows = response.data if isinstance(response.data, list) else []
    return [_serialize(row) for row in rows if isinstance(row, dict)]


@router.post("/{buyer_id}/verify", response_model=BusinessBuyerOut)
async def verify_business_buyer(
    buyer_id: str,
    body: VerifyBusinessRequest,
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> BusinessBuyerOut:
    before = load_by_id(service, buyer_id)
    after = set_decision(
        service,
        buyer_id=buyer_id,
        status="verified",
        verified_at=datetime.now(UTC).isoformat(),
        reviewer_notes=body.reviewer_notes,
    )
    recorder.record(
        action="business.verify",
        entity_type="business_buyer",
        entity_id=buyer_id,
        before={"status": before.get("status")},
        after={"status": "verified"},
    )
    return _serialize(after)


@router.post("/{buyer_id}/reject", response_model=BusinessBuyerOut)
async def reject_business_buyer(
    buyer_id: str,
    body: RejectBusinessRequest,
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> BusinessBuyerOut:
    before = load_by_id(service, buyer_id)
    after = set_decision(
        service,
        buyer_id=buyer_id,
        status="rejected",
        verified_at=None,
        reviewer_notes=body.reviewer_notes,
    )
    recorder.record(
        action="business.reject",
        entity_type="business_buyer",
        entity_id=buyer_id,
        before={"status": before.get("status")},
        after={"status": "rejected", "reviewer_notes": body.reviewer_notes},
    )
    return _serialize(after)
