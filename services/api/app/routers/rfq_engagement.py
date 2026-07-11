"""RFQ engagement router — accept a quote → deposit checkout hand-off (M11-P04)."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated, Any, Protocol

from app.core.auth import CurrentUser, get_current_user
from app.core.ratelimit import bump_rate_counter, get_client_ip, raise_rate_limited
from app.deps import get_supabase_client
from app.schemas.base import StrictModel
from app.services.rfq.engagement import accept_quote
from fastapi import APIRouter, Depends, Request

router = APIRouter(tags=["rfq-engagement"])


class _ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class AcceptQuoteResponse(StrictModel):
    job_id: str
    quote_id: str
    checkout_group_id: str
    order_id: str
    vendor_id: str
    deposit_order_item_id: str
    total_job_ngwee: int
    deposit_ngwee: int
    balance_ngwee: int
    commission_ngwee: int
    replayed: bool


def _rate_limit_accept(
    request: Request, user_id: str, service_client: _ServiceRoleClient
) -> None:
    ip = get_client_ip(request)
    allowed_ip, retry_ip = bump_rate_counter(
        scope="rfq_accept_ip",
        key=ip,
        window=timedelta(minutes=1),
        limit=20,
        client=service_client.client,
    )
    if not allowed_ip:
        raise_rate_limited(
            retry_after=retry_ip,
            message_key="services.accept.errors.rateLimited",
            message="Too many accept requests",
        )
    allowed_user, retry_user = bump_rate_counter(
        scope="rfq_accept_user",
        key=user_id,
        window=timedelta(minutes=1),
        limit=10,
        client=service_client.client,
    )
    if not allowed_user:
        raise_rate_limited(
            retry_after=retry_user,
            message_key="services.accept.errors.rateLimited",
            message="Too many accept requests",
        )


@router.post("/jobs/{job_id}/quotes/{quote_id}/accept", response_model=AcceptQuoteResponse)
async def accept_job_quote(
    job_id: str,
    quote_id: str,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> AcceptQuoteResponse:
    """Owner-scoped accept: create the deposit money spine, hand off to deposit checkout."""
    _rate_limit_accept(request, current_user.id, service_client)
    result = accept_quote(
        service_client,
        job_id=job_id,
        quote_id=quote_id,
        customer_id=current_user.id,
    )
    return AcceptQuoteResponse(
        job_id=result.job_id,
        quote_id=result.quote_id,
        checkout_group_id=result.checkout_group_id,
        order_id=result.order_id,
        vendor_id=result.vendor_id,
        deposit_order_item_id=result.deposit_order_item_id,
        total_job_ngwee=result.total_job_ngwee,
        deposit_ngwee=result.deposit_ngwee,
        balance_ngwee=result.balance_ngwee,
        commission_ngwee=result.commission_ngwee,
        replayed=result.replayed,
    )
