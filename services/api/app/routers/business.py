from __future__ import annotations

from datetime import timedelta
from typing import Annotated, Any

from app.core.auth import CurrentUser, get_current_user
from app.core.ratelimit import bump_rate_counter, get_client_ip, raise_rate_limited
from app.deps import get_supabase_client
from app.services.business.access import (
    BusinessAccess,
    ServiceRoleClient,
    resolve_business_eligibility,
)
from app.services.business.store import upsert_application
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/business", tags=["business"])


class BusinessApplyRequest(BaseModel):
    legal_name: str = Field(min_length=2, max_length=200)
    registration_no: str = Field(min_length=2, max_length=60)
    tpin: str | None = Field(default=None, max_length=20)


class BusinessStatusResponse(BaseModel):
    has_application: bool
    status: str | None = None
    eligible: bool = False
    legal_name: str | None = None
    registration_no: str | None = None
    tpin: str | None = None
    reviewer_notes: str | None = None


def _rate_limit_apply(request: Request, service: ServiceRoleClient, user_id: str) -> None:
    allowed, retry_after = bump_rate_counter(
        scope="write_sensitive",
        key=f"{get_client_ip(request)}:business_apply:{user_id}",
        window=timedelta(minutes=1),
        limit=10,
        client=service.client,
    )
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key="account.business.errors.rateLimited",
            message="Too many requests",
        )


def _status_response(access: BusinessAccess, row: dict[str, Any] | None) -> BusinessStatusResponse:
    if row is None:
        return BusinessStatusResponse(has_application=False, status=None, eligible=False)
    return BusinessStatusResponse(
        has_application=True,
        status=str(row.get("status")) if row.get("status") else None,
        eligible=access.eligible,
        legal_name=str(row["legal_name"]) if row.get("legal_name") else None,
        registration_no=str(row["registration_no"]) if row.get("registration_no") else None,
        tpin=str(row["tpin"]) if row.get("tpin") else None,
        reviewer_notes=str(row["reviewer_notes"]) if row.get("reviewer_notes") else None,
    )


@router.get("/status", response_model=BusinessStatusResponse)
async def get_business_status(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> BusinessStatusResponse:
    from app.services.business.access import fetch_business_buyer

    row = fetch_business_buyer(service.client, current_user.id)
    access = resolve_business_eligibility(current_user.id, service)
    return _status_response(access, row)


@router.post("/apply", response_model=BusinessStatusResponse)
async def apply_for_business(
    body: BusinessApplyRequest,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> BusinessStatusResponse:
    _rate_limit_apply(request, service, current_user.id)

    tpin = body.tpin.strip() if body.tpin and body.tpin.strip() else None
    row = upsert_application(
        service,
        user_id=current_user.id,
        legal_name=body.legal_name.strip(),
        registration_no=body.registration_no.strip(),
        tpin=tpin,
    )
    access = resolve_business_eligibility(current_user.id, service)
    return _status_response(access, row)
