"""Direct service booking router — book a bookable service → deposit checkout hand-off.

Sits alongside RFQ. Reuses the accept-quote deposit money spine (see
``app.services.rfq.booking``); this router only validates input, rate-limits, and
returns the resulting checkout group so the customer can pay the deposit.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated, Any, Protocol

from app.core.auth import CurrentUser, get_current_user
from app.core.ratelimit import bump_rate_counter, get_client_ip, raise_rate_limited
from app.deps import get_supabase_client
from app.schemas.base import StrictModel
from app.services.rfq.booking import create_booking
from fastapi import APIRouter, Depends, Request
from pydantic import Field

router = APIRouter(tags=["service-booking"])


class _ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class BookServiceRequest(StrictModel):
    idempotency_key: str = Field(min_length=8, max_length=128)
    note: str | None = Field(default=None, max_length=2000)


class BookingResponse(StrictModel):
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


def _rate_limit_book(
    request: Request, user_id: str, service_client: _ServiceRoleClient
) -> None:
    ip = get_client_ip(request)
    allowed_ip, retry_ip = bump_rate_counter(
        scope="service_book_ip",
        key=ip,
        window=timedelta(minutes=1),
        limit=20,
        client=service_client.client,
    )
    if not allowed_ip:
        raise_rate_limited(
            retry_after=retry_ip,
            message_key="services.booking.errors.rateLimited",
            message="Too many booking requests",
        )
    allowed_user, retry_user = bump_rate_counter(
        scope="service_book_user",
        key=user_id,
        window=timedelta(minutes=1),
        limit=10,
        client=service_client.client,
    )
    if not allowed_user:
        raise_rate_limited(
            retry_after=retry_user,
            message_key="services.booking.errors.rateLimited",
            message="Too many booking requests",
        )


@router.post("/services/{service_id}/book", response_model=BookingResponse)
async def book_service(
    service_id: str,
    body: BookServiceRequest,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> BookingResponse:
    """Book a bookable service at its fixed price → deposit money spine + checkout."""
    _rate_limit_book(request, current_user.id, service_client)
    result = create_booking(
        service_client,
        service_id=service_id,
        customer_id=current_user.id,
        idempotency_key=body.idempotency_key,
        note=body.note,
    )
    return BookingResponse(
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
