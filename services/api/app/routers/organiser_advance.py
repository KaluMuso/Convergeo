"""Organiser pre-event advance: policy status + undertaking acceptance.

Tiered policy (services/events/advance_policy.py): unverified organisers are paid
after the event; verified organisers who accept the advance undertaking may get a
configured share before the event, repayable if the event is cancelled.
"""

from __future__ import annotations

from typing import Annotated, Literal

from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.organiser_events import _load_vendor_for_owner, _require_active_kyc_vendor
from app.schemas.base import StrictModel
from app.services.events.advance_policy import (
    ADVANCE_TERMS_VERSION,
    accept_advance_undertaking,
    has_current_undertaking,
    organiser_advance_decision,
    organiser_receivable_balance_ngwee,
)
from app.services.kyc.state_machine import ServiceRoleClient
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/organiser/advance", tags=["organiser-advance"])


class AdvancePolicyResponse(StrictModel):
    advance_bps: int
    reason: str
    terms_version: str
    undertaking_accepted: bool
    receivable_ngwee: int


class AcceptUndertakingRequest(StrictModel):
    terms_version: str
    accept: Literal[True]


def _policy_response(vendor_id: str) -> AdvancePolicyResponse:
    decision = organiser_advance_decision(vendor_id)
    return AdvancePolicyResponse(
        advance_bps=decision.bps,
        reason=decision.reason,
        terms_version=ADVANCE_TERMS_VERSION,
        undertaking_accepted=has_current_undertaking(vendor_id),
        receivable_ngwee=max(0, organiser_receivable_balance_ngwee(vendor_id)),
    )


@router.get("", response_model=AdvancePolicyResponse)
async def get_advance_policy(
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> AdvancePolicyResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    return _policy_response(str(vendor["id"]))


@router.post("/undertaking", response_model=AdvancePolicyResponse)
async def accept_undertaking(
    body: AcceptUndertakingRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> AdvancePolicyResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    _require_active_kyc_vendor(service_client, vendor)
    if body.terms_version != ADVANCE_TERMS_VERSION:
        raise AppError(
            code="advance_terms_outdated",
            message="Accept the current advance undertaking",
            http_status=409,
            details={"terms_version": ADVANCE_TERMS_VERSION},
        )
    vendor_id = str(vendor["id"])
    accept_advance_undertaking(vendor_id=vendor_id, actor_user_id=current_user.id)
    return _policy_response(vendor_id)
