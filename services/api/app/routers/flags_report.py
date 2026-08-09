"""Customer listing-report endpoint (AUTH_ANY) — rate-limited flags intake."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated, Any, Literal, Protocol
from uuid import UUID

from app.core.auth import CurrentUser, get_current_user
from app.core.ratelimit import bump_rate_counter, get_client_ip, raise_rate_limited
from app.deps import get_supabase_client
from app.schemas.base import StrictModel
from app.services.moderation.listing_reports import (
    LISTING_REPORT_REASONS,
    MAX_DETAIL_LEN,
    create_listing_report,
)
from fastapi import APIRouter, Depends, Request
from pydantic import Field, field_validator

router = APIRouter(prefix="/flags", tags=["flags"])

USER_REPORT_LIMIT = 10
IP_REPORT_LIMIT = 30
REPORT_WINDOW = timedelta(minutes=1)

ListingReportReasonLiteral = Literal[
    "counterfeit", "prohibited", "scam", "misleading", "other"
]


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class ListingReportRequest(StrictModel):
    # StrictModel forbids UUID string coercion — accept str and validate shape.
    listing_id: str = Field(min_length=36, max_length=36)
    reason: ListingReportReasonLiteral
    detail: str | None = Field(default=None, max_length=MAX_DETAIL_LEN)

    @field_validator("listing_id")
    @classmethod
    def _listing_id_uuid(cls, value: str) -> str:
        try:
            return str(UUID(value))
        except ValueError as exc:
            msg = "listing_id must be a UUID"
            raise ValueError(msg) from exc

    @field_validator("reason")
    @classmethod
    def _reason_allowed(cls, value: str) -> str:
        if value not in LISTING_REPORT_REASONS:
            msg = "unsupported report reason"
            raise ValueError(msg)
        return value


class ListingReportResponse(StrictModel):
    ok: bool = True
    flag_id: str
    created: bool
    deduped: bool


def _rate_limit_report(
    request: Request,
    *,
    user_id: str,
    service_client: ServiceRoleClient,
) -> None:
    ip = get_client_ip(request)
    allowed_ip, retry_ip = bump_rate_counter(
        scope="listing_report_ip",
        key=ip,
        window=REPORT_WINDOW,
        limit=IP_REPORT_LIMIT,
        client=service_client.client,
    )
    if not allowed_ip:
        raise_rate_limited(
            retry_after=retry_ip,
            message_key="catalog.pdp.reportListing.rateLimited",
            message="Too many listing reports",
        )

    allowed_user, retry_user = bump_rate_counter(
        scope="listing_report_user",
        key=user_id,
        window=REPORT_WINDOW,
        limit=USER_REPORT_LIMIT,
        client=service_client.client,
    )
    if not allowed_user:
        raise_rate_limited(
            retry_after=retry_user,
            message_key="catalog.pdp.reportListing.rateLimited",
            message="Too many listing reports",
        )


@router.post("/report", response_model=ListingReportResponse)
async def report_listing(
    body: ListingReportRequest,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ListingReportResponse:
    """Authenticated customer report → ``flags`` queue (deduped, rate-limited)."""
    _rate_limit_report(
        request,
        user_id=current_user.id,
        service_client=service_client,
    )
    flag_row, created = create_listing_report(
        service_client.client,
        listing_id=body.listing_id,
        reporter_user_id=current_user.id,
        reason=body.reason,
        detail=body.detail,
    )
    return ListingReportResponse(
        ok=True,
        flag_id=str(flag_row["id"]),
        created=created,
        deduped=not created,
    )
