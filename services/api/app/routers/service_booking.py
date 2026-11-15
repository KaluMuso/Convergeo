"""Direct service booking router — book a bookable service → deposit checkout hand-off.

Sits alongside RFQ. Reuses the accept-quote deposit money spine (see
``app.services.rfq.booking``); this router only validates input, rate-limits, and
returns the resulting checkout group so the customer can pay the deposit.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Any, Protocol

from app.core.auth import CurrentUser, get_current_user
from app.core.ratelimit import bump_rate_counter, get_client_ip, raise_rate_limited
from app.deps import get_supabase_client
from app.schemas.base import StrictModel
from app.services.rfq.booking import create_booking
from app.services.rfq.free_booking import (
    FreeBooking,
    FreeBookingStatus,
    list_vendor_free_bookings,
    request_free_booking,
    transition_free_booking,
)
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


# --------------------------------------------------------------------------- #
# Free services: request -> vendor accepts/declines. No quote, order or payment.
# --------------------------------------------------------------------------- #


class FreeBookingRequest(StrictModel):
    idempotency_key: str = Field(min_length=8, max_length=128)
    note: str | None = Field(default=None, max_length=2000)
    preferred_date: date | None = None


class FreeBookingResponse(StrictModel):
    id: str
    service_id: str
    vendor_id: str
    status: FreeBookingStatus
    note: str | None = None
    preferred_date: str | None = None
    created_at: str
    replayed: bool = False


class FreeBookingListResponse(StrictModel):
    items: list[FreeBookingResponse]


def _free_out(b: FreeBooking) -> FreeBookingResponse:
    return FreeBookingResponse(
        id=b.id,
        service_id=b.service_id,
        vendor_id=b.vendor_id,
        status=b.status,
        note=b.note,
        preferred_date=b.preferred_date,
        created_at=b.created_at,
        replayed=b.replayed,
    )


def _rate_limit_respond(user_id: str, service_client: _ServiceRoleClient) -> None:
    allowed, retry = bump_rate_counter(
        scope="service_free_booking_respond",
        key=user_id,
        window=timedelta(minutes=1),
        limit=30,
        client=service_client.client,
    )
    if not allowed:
        raise_rate_limited(
            retry_after=retry,
            message_key="services.booking.errors.rateLimited",
            message="Too many booking requests",
        )


@router.post("/services/{service_id}/request-free", response_model=FreeBookingResponse)
async def request_free_service(
    service_id: str,
    body: FreeBookingRequest,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> FreeBookingResponse:
    """Request a free service: straight to a booking request (no quote, no payment)."""
    _rate_limit_book(request, current_user.id, service_client)
    return _free_out(
        request_free_booking(
            service_id=service_id,
            customer_id=current_user.id,
            idempotency_key=body.idempotency_key,
            note=body.note,
            preferred_date=body.preferred_date,
        )
    )


@router.get("/vendor/free-bookings", response_model=FreeBookingListResponse)
async def vendor_free_bookings(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> FreeBookingListResponse:
    items = list_vendor_free_bookings(vendor_owner_id=current_user.id)
    return FreeBookingListResponse(items=[_free_out(b) for b in items])


async def _transition(
    booking_id: str,
    to: FreeBookingStatus,
    current_user: CurrentUser,
    service_client: _ServiceRoleClient,
) -> FreeBookingResponse:
    _rate_limit_respond(current_user.id, service_client)
    return _free_out(
        transition_free_booking(booking_id=booking_id, to=to, actor_id=current_user.id)
    )


@router.post("/vendor/free-bookings/{booking_id}/accept", response_model=FreeBookingResponse)
async def accept_free_booking(
    booking_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> FreeBookingResponse:
    return await _transition(booking_id, "accepted", current_user, service_client)


@router.post("/vendor/free-bookings/{booking_id}/decline", response_model=FreeBookingResponse)
async def decline_free_booking(
    booking_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> FreeBookingResponse:
    return await _transition(booking_id, "declined", current_user, service_client)


@router.post("/me/free-bookings/{booking_id}/cancel", response_model=FreeBookingResponse)
async def cancel_free_booking(
    booking_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> FreeBookingResponse:
    return await _transition(booking_id, "cancelled", current_user, service_client)
