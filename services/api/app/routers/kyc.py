from __future__ import annotations

from typing import Annotated, Any, Literal

from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.errors import AppError
from app.services.kyc.name_match import MomoOperator, resolve_and_score_momo_name
from app.services.kyc.state_machine import (
    KycApplicationStatus,
    KycRecordSnapshot,
    KycStateMachine,
    ServiceRoleClient,
    transition_resubmit,
    transition_submit,
)
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

router = APIRouter(prefix="/kyc", tags=["kyc"])

# Business archetypes persisted onto the vendor (must match vendors_archetype_check
# in migration 0035 and BUSINESS_CATEGORIES in the vendor onboarding UI).
VENDOR_ARCHETYPES = frozenset(
    {"electronics", "home", "fashion_beauty", "services", "groceries", "other"}
)


class KycSubmitRequest(BaseModel):
    tier: Literal[1, 2, 3]
    doc_storage_paths: list[str] = Field(min_length=1)
    momo_phone: str = Field(min_length=8, max_length=20)
    momo_operator: MomoOperator | None = None
    legal_name: str = Field(min_length=2, max_length=200)
    archetype: str | None = Field(default=None, max_length=40)

    @field_validator("doc_storage_paths")
    @classmethod
    def validate_paths(cls, paths: list[str]) -> list[str]:
        cleaned = [path.strip() for path in paths if path.strip()]
        if not cleaned:
            raise ValueError("At least one document path is required")
        return cleaned

    @field_validator("archetype")
    @classmethod
    def validate_archetype(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        if cleaned not in VENDOR_ARCHETYPES:
            raise ValueError("Unsupported vendor archetype")
        return cleaned


class MomoNameMatchResponse(BaseModel):
    phone: str
    operator: str
    resolved_name: str | None
    legal_name: str
    match_score: float
    matched: bool


class KycStatusResponse(BaseModel):
    application_status: KycApplicationStatus
    vendor_status: str
    kyc_tier: int | None
    kyc_record_id: str | None
    kyc_record_status: str | None
    tier: int | None
    doc_storage_paths: list[str]
    momo_name_match: MomoNameMatchResponse | None
    reviewer_notes: str | None
    archetype: str | None = None
    business_name: str | None = None


class KycSubmitResponse(BaseModel):
    application_status: KycApplicationStatus
    kyc_record_id: str
    momo_name_match: MomoNameMatchResponse


def _load_vendor_for_owner(
    service_client: ServiceRoleClient,
    owner_user_id: str,
) -> dict[str, Any]:
    response = (
        service_client.client.table("vendors")
        .select("id, owner_user_id, status, kyc_tier, archetype, display_name")
        .eq("owner_user_id", owner_user_id)
        .maybe_single()
        .execute()
    )
    if response is None:
        raise AppError(
            code="internal_error",
            message="Vendor lookup failed",
            http_status=500,
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
        raise AppError(
            code="forbidden",
            message="Authenticated user does not own a vendor profile",
            http_status=403,
            details={"message_key": "vendor.errors.not_found"},
        )
    return row


async def require_vendor_owner(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> dict[str, Any]:
    return _load_vendor_for_owner(service_client, current_user.id)


def _persist_vendor_archetype(
    service_client: ServiceRoleClient,
    vendor_id: str,
    archetype: str | None,
) -> None:
    """Persist the onboarding-selected business archetype onto the vendor row.

    Fixes the audit gap where the archetype lived only in browser localStorage.
    """
    if not archetype:
        return
    service_client.client.table("vendors").update({"archetype": archetype}).eq(
        "id", vendor_id
    ).execute()


def _serialize_momo_match(payload: dict[str, Any] | None) -> MomoNameMatchResponse | None:
    if payload is None:
        return None
    return MomoNameMatchResponse(
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


def _build_status_response(
    vendor: dict[str, Any],
    application_status: KycApplicationStatus,
    kyc_record: KycRecordSnapshot | None,
) -> KycStatusResponse:
    momo = _serialize_momo_match(kyc_record.momo_name_match if kyc_record else None)
    archetype = vendor.get("archetype")
    business_name = vendor.get("display_name")
    return KycStatusResponse(
        application_status=application_status,
        vendor_status=str(vendor.get("status", "draft")),
        kyc_tier=vendor.get("kyc_tier"),
        kyc_record_id=kyc_record.id if kyc_record else None,
        kyc_record_status=kyc_record.status if kyc_record else None,
        tier=kyc_record.tier if kyc_record else None,
        doc_storage_paths=kyc_record.doc_storage_paths if kyc_record else [],
        momo_name_match=momo,
        reviewer_notes=kyc_record.reviewer_notes if kyc_record else None,
        archetype=str(archetype) if isinstance(archetype, str) and archetype else None,
        business_name=(
            str(business_name) if isinstance(business_name, str) and business_name else None
        ),
    )


@router.get("/status", response_model=KycStatusResponse)
async def get_kyc_status(
    vendor: Annotated[dict[str, Any], Depends(require_vendor_owner)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> KycStatusResponse:
    machine = KycStateMachine(service_client)
    application_status, kyc_record = machine.get_status(str(vendor["id"]))
    return _build_status_response(vendor, application_status, kyc_record)


@router.post("/submit", response_model=KycSubmitResponse)
async def submit_kyc(
    body: KycSubmitRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    vendor: Annotated[dict[str, Any], Depends(require_vendor_owner)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> KycSubmitResponse:
    momo_result = await resolve_and_score_momo_name(
        phone=body.momo_phone,
        legal_name=body.legal_name,
        operator=body.momo_operator,
    )
    result = transition_submit(
        actor_id=current_user.id,
        vendor_id=str(vendor["id"]),
        tier=body.tier,
        doc_storage_paths=body.doc_storage_paths,
        momo_name_match=momo_result.to_json(),
        service_client=service_client,
    )
    _persist_vendor_archetype(service_client, str(vendor["id"]), body.archetype)
    kyc_record_id = str(result["kyc_record"]["id"])
    return KycSubmitResponse(
        application_status=KycApplicationStatus.SUBMITTED,
        kyc_record_id=kyc_record_id,
        momo_name_match=_serialize_momo_match(momo_result.to_json()) or MomoNameMatchResponse(
            phone=body.momo_phone,
            operator=momo_result.operator,
            resolved_name=momo_result.resolved_name,
            legal_name=body.legal_name,
            match_score=momo_result.match_score,
            matched=momo_result.matched,
        ),
    )


@router.post("/resubmit", response_model=KycSubmitResponse)
async def resubmit_kyc(
    body: KycSubmitRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    vendor: Annotated[dict[str, Any], Depends(require_vendor_owner)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> KycSubmitResponse:
    machine = KycStateMachine(service_client)
    application_status, _ = machine.get_status(str(vendor["id"]))
    if application_status != KycApplicationStatus.REJECTED:
        raise AppError(
            code="kyc_invalid_transition",
            message="Resubmit is only allowed after rejection",
            http_status=409,
            details={
                "application_status": application_status.value,
                "message_key": "vendor.kyc.resubmit_not_allowed",
            },
        )

    momo_result = await resolve_and_score_momo_name(
        phone=body.momo_phone,
        legal_name=body.legal_name,
        operator=body.momo_operator,
    )
    result = transition_resubmit(
        actor_id=current_user.id,
        vendor_id=str(vendor["id"]),
        tier=body.tier,
        doc_storage_paths=body.doc_storage_paths,
        momo_name_match=momo_result.to_json(),
        service_client=service_client,
    )
    _persist_vendor_archetype(service_client, str(vendor["id"]), body.archetype)
    return KycSubmitResponse(
        application_status=KycApplicationStatus.SUBMITTED,
        kyc_record_id=str(result["kyc_record"]["id"]),
        momo_name_match=_serialize_momo_match(momo_result.to_json()) or MomoNameMatchResponse(
            phone=body.momo_phone,
            operator=momo_result.operator,
            resolved_name=momo_result.resolved_name,
            legal_name=body.legal_name,
            match_score=momo_result.match_score,
            matched=momo_result.matched,
        ),
    )
