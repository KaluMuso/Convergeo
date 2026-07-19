from __future__ import annotations

import re
import uuid
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
from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, Field, field_validator

router = APIRouter(prefix="/kyc", tags=["kyc"])

# Business archetypes persisted onto the vendor (must match vendors_archetype_check
# in migration 0037 and BUSINESS_CATEGORIES in the vendor onboarding UI).
VENDOR_ARCHETYPES = frozenset(
    {"electronics", "home", "fashion_beauty", "services", "groceries", "other"}
)

# Draft/onboarding sellers may edit business basics before admin approval.
# Note: KYC rejection keeps vendors.status as pending_kyc (no vendor status
# value of "rejected" — see kyc state machine).
_DRAFT_EDITABLE_STATUSES = frozenset({"draft", "pending_kyc"})
_DEFAULT_DRAFT_DISPLAY_NAME = "Seller application"


def _validate_optional_archetype(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if cleaned not in VENDOR_ARCHETYPES:
        raise ValueError("Unsupported vendor archetype")
    return cleaned


def _validate_optional_business_name(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) < 2:
        raise ValueError("Business name must be at least 2 characters")
    return cleaned[:200]


class KycSubmitRequest(BaseModel):
    tier: Literal[1, 2, 3]
    doc_storage_paths: list[str] = Field(min_length=1)
    momo_phone: str = Field(min_length=8, max_length=20)
    momo_operator: MomoOperator | None = None
    legal_name: str = Field(min_length=2, max_length=200)
    archetype: str | None = Field(default=None, max_length=40)
    business_name: str | None = Field(default=None, max_length=200)

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
        return _validate_optional_archetype(value)

    @field_validator("business_name")
    @classmethod
    def validate_business_name(cls, value: str | None) -> str | None:
        return _validate_optional_business_name(value)


class KycBootstrapRequest(BaseModel):
    """Optional business basics when creating/resuming a draft application."""

    business_name: str | None = Field(default=None, max_length=200)
    archetype: str | None = Field(default=None, max_length=40)

    @field_validator("archetype")
    @classmethod
    def validate_archetype(cls, value: str | None) -> str | None:
        return _validate_optional_archetype(value)

    @field_validator("business_name")
    @classmethod
    def validate_business_name(cls, value: str | None) -> str | None:
        return _validate_optional_business_name(value)


class KycDraftUpdateRequest(BaseModel):
    business_name: str | None = Field(default=None, max_length=200)
    archetype: str | None = Field(default=None, max_length=40)

    @field_validator("archetype")
    @classmethod
    def validate_archetype(cls, value: str | None) -> str | None:
        return _validate_optional_archetype(value)

    @field_validator("business_name")
    @classmethod
    def validate_business_name(cls, value: str | None) -> str | None:
        return _validate_optional_business_name(value)


class MomoNameMatchResponse(BaseModel):
    phone: str
    operator: str
    resolved_name: str | None
    legal_name: str
    match_score: float
    matched: bool


class KycCapabilitiesOut(BaseModel):
    wholesale: bool
    organise_events: bool
    directory_verified: bool


class KycStatusResponse(BaseModel):
    application_status: KycApplicationStatus
    vendor_status: str
    kyc_tier: int | None
    effective_tier: int | None = None
    kyc_record_id: str | None
    kyc_record_status: str | None
    tier: int | None
    doc_storage_paths: list[str]
    momo_name_match: MomoNameMatchResponse | None
    reviewer_notes: str | None
    archetype: str | None = None
    business_name: str | None = None
    is_auditable_approved: bool = False
    orphaned_tier: bool = False
    capabilities: KycCapabilitiesOut = Field(
        default_factory=lambda: KycCapabilitiesOut(
            wholesale=False,
            organise_events=False,
            directory_verified=False,
        )
    )


class KycBootstrapResponse(KycStatusResponse):
    """Same status payload plus whether a new draft row was created."""

    created: bool = False
    vendor_id: str


class KycSubmitResponse(BaseModel):
    application_status: KycApplicationStatus
    kyc_record_id: str
    momo_name_match: MomoNameMatchResponse


def _row_from_response(response: Any) -> dict[str, Any] | None:
    if response is None:
        return None
    data = response.data
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def _find_vendor_for_owner(
    service_client: ServiceRoleClient,
    owner_user_id: str,
) -> dict[str, Any] | None:
    response = (
        service_client.client.table("vendors")
        .select(
            "id, owner_user_id, status, kyc_tier, preferred_badge, archetype, display_name, slug"
        )
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
    return _row_from_response(response)


def _load_vendor_for_owner(
    service_client: ServiceRoleClient,
    owner_user_id: str,
) -> dict[str, Any]:
    row = _find_vendor_for_owner(service_client, owner_user_id)
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


def _draft_slug_for_owner(owner_user_id: str) -> str:
    compact = re.sub(r"[^a-zA-Z0-9]", "", owner_user_id).lower()[:12] or "seller"
    return f"draft-{compact}"


def _persist_vendor_basics(
    service_client: ServiceRoleClient,
    vendor_id: str,
    *,
    business_name: str | None = None,
    archetype: str | None = None,
) -> dict[str, Any] | None:
    """Persist onboarding business basics onto the owned vendor row."""
    patch: dict[str, Any] = {}
    if business_name:
        patch["display_name"] = business_name
    if archetype:
        patch["archetype"] = archetype
    if not patch:
        return None
    response = (
        service_client.client.table("vendors")
        .update(patch)
        .eq("id", vendor_id)
        .execute()
    )
    return _row_from_response(response)


def _assert_draft_editable(vendor: dict[str, Any]) -> None:
    status = str(vendor.get("status", ""))
    if status not in _DRAFT_EDITABLE_STATUSES:
        raise AppError(
            code="kyc_invalid_transition",
            message="Business basics can only be edited before approval",
            http_status=409,
            details={
                "vendor_status": status,
                "message_key": "vendor.onboarding.errors.draftLocked",
            },
        )


def _create_draft_vendor(
    service_client: ServiceRoleClient,
    *,
    owner_user_id: str,
    business_name: str | None,
    archetype: str | None,
) -> dict[str, Any]:
    """Insert one draft vendors row for the owner. Never assigns user_roles.vendor."""
    display_name = business_name or _DEFAULT_DRAFT_DISPLAY_NAME
    slug = _draft_slug_for_owner(owner_user_id)
    payload: dict[str, Any] = {
        "owner_user_id": owner_user_id,
        "slug": slug,
        "display_name": display_name,
        "status": "draft",
    }
    if archetype:
        payload["archetype"] = archetype

    try:
        response = service_client.client.table("vendors").insert(payload).execute()
    except Exception:
        # Likely slug uniqueness race — resume any row created for this owner.
        existing = _find_vendor_for_owner(service_client, owner_user_id)
        if existing is not None:
            return existing
        # Retry once with a unique suffix (no schema change required).
        payload["slug"] = f"{slug}-{uuid.uuid4().hex[:8]}"
        response = service_client.client.table("vendors").insert(payload).execute()

    created = _row_from_response(response)
    if created is None:
        # Concurrent bootstrap: another request may have inserted first.
        existing = _find_vendor_for_owner(service_client, owner_user_id)
        if existing is not None:
            return existing
        raise AppError(
            code="internal_error",
            message="Failed to create vendor application draft",
            http_status=500,
        )
    return created


def _status_for_vendor(
    service_client: ServiceRoleClient,
    vendor: dict[str, Any],
) -> KycStatusResponse:
    machine = KycStateMachine(service_client)
    application_status, kyc_record = machine.get_status(str(vendor["id"]))
    return _build_status_response(
        vendor,
        application_status,
        kyc_record,
        service_client=service_client,
    )


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
    *,
    service_client: ServiceRoleClient,
) -> KycStatusResponse:
    from app.services.kyc.eligibility import resolve_vendor_eligibility

    momo = _serialize_momo_match(kyc_record.momo_name_match if kyc_record else None)
    archetype = vendor.get("archetype")
    business_name = vendor.get("display_name")
    eligibility = resolve_vendor_eligibility(
        service_client,
        str(vendor["id"]),
        vendor_row=vendor,
    )
    # Never surface a bare stored tier as the capability tier when orphaned.
    public_tier = (
        eligibility.effective_tier
        if eligibility.is_auditable_approved
        else None
    )
    return KycStatusResponse(
        application_status=application_status,
        vendor_status=str(vendor.get("status", "draft")),
        kyc_tier=public_tier,
        effective_tier=eligibility.effective_tier,
        kyc_record_id=kyc_record.id if kyc_record else None,
        kyc_record_status=kyc_record.status if kyc_record else None,
        tier=kyc_record.tier if kyc_record else None,
        doc_storage_paths=kyc_record.doc_storage_paths if kyc_record else [],
        momo_name_match=momo,
        reviewer_notes=kyc_record.reviewer_notes if kyc_record else None,
        archetype=str(archetype) if isinstance(archetype, str) and archetype else None,
        business_name=(
            str(business_name)
            if isinstance(business_name, str)
            and business_name
            and business_name != _DEFAULT_DRAFT_DISPLAY_NAME
            else None
        ),
        is_auditable_approved=eligibility.is_auditable_approved,
        orphaned_tier=eligibility.orphaned_tier,
        capabilities=KycCapabilitiesOut(
            wholesale=eligibility.can_wholesale,
            organise_events=eligibility.can_organise_events,
            directory_verified=eligibility.is_directory_verified,
        ),
    )


@router.get("/status", response_model=KycStatusResponse)
async def get_kyc_status(
    vendor: Annotated[dict[str, Any], Depends(require_vendor_owner)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> KycStatusResponse:
    return _status_for_vendor(service_client, vendor)


@router.post("/bootstrap", response_model=KycBootstrapResponse)
async def bootstrap_kyc_application(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    body: Annotated[KycBootstrapRequest | None, Body()] = None,
) -> KycBootstrapResponse:
    """Idempotent invite/concierge onboarding bootstrap.

    Authenticated customers may create or resume one draft vendor application
    without holding the ``vendor`` role. Never assigns ``user_roles.vendor``.
    """
    payload = body if body is not None else KycBootstrapRequest()
    existing = _find_vendor_for_owner(service_client, current_user.id)
    created = False
    if existing is None:
        vendor = _create_draft_vendor(
            service_client,
            owner_user_id=current_user.id,
            business_name=payload.business_name,
            archetype=payload.archetype,
        )
        created = True
    else:
        vendor = existing
        if payload.business_name or payload.archetype:
            _assert_draft_editable(vendor)
            updated = _persist_vendor_basics(
                service_client,
                str(vendor["id"]),
                business_name=payload.business_name,
                archetype=payload.archetype,
            )
            if updated is not None:
                vendor = {**vendor, **updated}
            else:
                # Fake/empty update path — re-read for honest response fields.
                vendor = _load_vendor_for_owner(service_client, current_user.id)

    status = _status_for_vendor(service_client, vendor)
    return KycBootstrapResponse(
        **status.model_dump(),
        created=created,
        vendor_id=str(vendor["id"]),
    )


@router.patch("/draft", response_model=KycStatusResponse)
async def update_kyc_draft(
    body: KycDraftUpdateRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> KycStatusResponse:
    """Persist business basics for the caller's draft/pending application."""
    if body.business_name is None and body.archetype is None:
        raise AppError(
            code="validation_error",
            message="At least one of business_name or archetype is required",
            http_status=422,
        )
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    _assert_draft_editable(vendor)
    updated = _persist_vendor_basics(
        service_client,
        str(vendor["id"]),
        business_name=body.business_name,
        archetype=body.archetype,
    )
    if updated is not None:
        vendor = {**vendor, **updated}
    return _status_for_vendor(service_client, vendor)


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
    _persist_vendor_basics(
        service_client,
        str(vendor["id"]),
        business_name=body.business_name,
        archetype=body.archetype,
    )
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
    _persist_vendor_basics(
        service_client,
        str(vendor["id"]),
        business_name=body.business_name,
        archetype=body.archetype,
    )
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
