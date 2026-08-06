"""Listing/service-anchored RFQ threads with formal quote payload.

Distinct from enquiry_threads (no money) and jobs/job_quotes (broadcast).
Vendors issue quotes in integer ngwee; customers accept listing RFQs into cart
via POST /cart/rfq/{rfq_id}/accept.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal, Protocol

from app.core.auth import CurrentUser, get_current_user
from app.core.ratelimit import bump_rate_counter, get_client_ip, raise_rate_limited
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.business.access import fetch_business_buyer
from app.services.moderation.contact_strip import strip_contacts
from app.services.moderation.prohibited import screen_listing
from app.services.notifications.dedupe import enqueue_outbox_row
from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field, field_validator

router = APIRouter(prefix="/rfq", tags=["rfq"])

Party = Literal["customer", "vendor"]

THREAD_SELECT = (
    "id, customer_id, vendor_id, listing_id, service_id, requested_details, "
    "status, quote_price_ngwee, quote_valid_until, quoted_at, last_message_at, created_at"
)
MESSAGE_SELECT = "id, thread_id, sender_role, body, created_at"

MAX_PAGE_SIZE = 50
MAX_DETAILS_CHARS = 4000
MAX_BODY_CHARS = 2000
MAX_QUOTE_VALIDITY_DAYS = 30
DEFAULT_QUOTE_VALIDITY_DAYS = 7

NEW_THREADS_PER_HOUR = 10
MESSAGES_PER_HOUR = 60
IP_WRITES_PER_MINUTE = 30

RFQ_OPENED_TEMPLATE = "rfq_opened"
RFQ_REPLY_TEMPLATE = "rfq_reply"
RFQ_QUOTED_TEMPLATE = "rfq_quoted"


class _ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class _BodyMixin(StrictModel):
    body: str = Field(min_length=1, max_length=MAX_BODY_CHARS)

    @field_validator("body", mode="before")
    @classmethod
    def _strip_body(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class CreateRfqRequest(StrictModel):
    listing_id: str | None = None
    service_id: str | None = None
    requested_details: str = Field(min_length=1, max_length=MAX_DETAILS_CHARS)

    @field_validator("requested_details", mode="before")
    @classmethod
    def _strip_details(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class PostRfqMessageRequest(_BodyMixin):
    pass


class IssueQuoteRequest(StrictModel):
    price_ngwee: int = Field(gt=0)
    valid_until: datetime | None = None
    validity_days: int | None = Field(default=None, ge=1, le=MAX_QUOTE_VALIDITY_DAYS)
    message: str | None = Field(default=None, max_length=MAX_BODY_CHARS)


class RfqMessageResponse(StrictModel):
    id: str
    thread_id: str
    sender_role: str
    body: str
    created_at: str


class RfqThreadResponse(StrictModel):
    id: str
    customer_id: str
    vendor_id: str
    listing_id: str | None
    service_id: str | None
    requested_details: str
    status: str
    quote_price_ngwee: int | None
    quote_valid_until: str | None
    quoted_at: str | None
    last_message_at: str | None
    created_at: str


class CreateRfqResponse(StrictModel):
    thread: RfqThreadResponse
    message: RfqMessageResponse
    reused_existing_thread: bool


class RfqThreadListResponse(StrictModel):
    items: list[RfqThreadResponse]
    limit: int
    offset: int


class RfqMessagesResponse(StrictModel):
    thread_id: str
    items: list[RfqMessageResponse]
    limit: int
    offset: int


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


def _is_unique_violation(exc: Exception) -> bool:
    text = str(exc).lower()
    return "duplicate key" in text or "unique" in text or "23505" in str(exc)


def _thread_not_found() -> AppError:
    return AppError(
        code="rfq.not_found",
        message="RFQ thread not found",
        http_status=404,
        details={},
    )


def _subject_not_found() -> AppError:
    return AppError(
        code="rfq.subject_not_found",
        message="Subject not found",
        http_status=404,
        details={},
    )


def _thread_to_response(row: dict[str, Any]) -> RfqThreadResponse:
    quote_price = row.get("quote_price_ngwee")
    return RfqThreadResponse(
        id=str(row["id"]),
        customer_id=str(row["customer_id"]),
        vendor_id=str(row["vendor_id"]),
        listing_id=str(row["listing_id"]) if row.get("listing_id") else None,
        service_id=str(row["service_id"]) if row.get("service_id") else None,
        requested_details=str(row["requested_details"]),
        status=str(row["status"]),
        quote_price_ngwee=int(quote_price) if quote_price is not None else None,
        quote_valid_until=str(row["quote_valid_until"]) if row.get("quote_valid_until") else None,
        quoted_at=str(row["quoted_at"]) if row.get("quoted_at") else None,
        last_message_at=str(row["last_message_at"]) if row.get("last_message_at") else None,
        created_at=str(row["created_at"]),
    )


def _message_to_response(row: dict[str, Any]) -> RfqMessageResponse:
    return RfqMessageResponse(
        id=str(row["id"]),
        thread_id=str(row["thread_id"]),
        sender_role=str(row["sender_role"]),
        body=str(row["body"]),
        created_at=str(row["created_at"]),
    )


def _rate_limit(
    request: Request,
    user_id: str,
    service_client: _ServiceRoleClient,
    *,
    scope_suffix: str,
    user_limit_per_hour: int,
) -> None:
    ip = get_client_ip(request)
    allowed_ip, ip_retry = bump_rate_counter(
        scope=f"rfq_ip_{scope_suffix}",
        key=ip,
        window=timedelta(minutes=1),
        limit=IP_WRITES_PER_MINUTE,
        client=service_client.client,
    )
    if not allowed_ip:
        raise_rate_limited(
            retry_after=ip_retry,
            message_key="rfq.errors.rateLimited",
            message="Too many RFQ requests",
        )
    allowed_user, user_retry = bump_rate_counter(
        scope=f"rfq_user_{scope_suffix}",
        key=user_id,
        window=timedelta(hours=1),
        limit=user_limit_per_hour,
        client=service_client.client,
    )
    if not allowed_user:
        raise_rate_limited(
            retry_after=user_retry,
            message_key="rfq.errors.rateLimited",
            message="Too many RFQ requests",
        )


def _screen_body(body: str) -> None:
    result = screen_listing(description=body)
    if not result.allowed:
        raise AppError(
            code="rfq.prohibited_content",
            message="Message contains prohibited content",
            http_status=422,
            details={"reason": result.reason or "keyword"},
        )


def _mask_contacts(body: str) -> str:
    masked = strip_contacts(body).clean_text.strip()
    return masked[:MAX_BODY_CHARS]


def _resolve_listing_vendor(
    service_client: _ServiceRoleClient,
    listing_id: str,
    caller_user_id: str,
) -> str:
    response = (
        service_client.client.table("vendor_listings")
        .select("id, vendor_id, status, wholesale, product_class")
        .eq("id", listing_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None or str(row.get("status") or "") != "active":
        raise _subject_not_found()
    if str(row.get("product_class") or "") != "E":
        raise _subject_not_found()
    if bool(row.get("wholesale")):
        buyer = fetch_business_buyer(service_client.client, caller_user_id)
        if not (buyer and buyer.get("status") == "verified"):
            raise _subject_not_found()
    owner_vendor = row.get("vendor_id")
    if not owner_vendor:
        raise _subject_not_found()
    return str(owner_vendor)


def _resolve_service_vendor(
    service_client: _ServiceRoleClient,
    service_id: str,
) -> str:
    response = (
        service_client.client.table("services")
        .select("id, vendor_id, status, from_price_ngwee")
        .eq("id", service_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None or str(row.get("status") or "") != "active":
        raise _subject_not_found()
    if row.get("from_price_ngwee") is not None:
        raise _subject_not_found()
    owner_vendor = row.get("vendor_id")
    if not owner_vendor:
        raise _subject_not_found()
    return str(owner_vendor)


def _vendor_owner_user_id(service_client: _ServiceRoleClient, vendor_id: str) -> str | None:
    response = (
        service_client.client.table("vendors")
        .select("id, owner_user_id")
        .eq("id", vendor_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        return None
    owner = row.get("owner_user_id")
    return str(owner) if owner else None


def _resolve_party(
    service_client: _ServiceRoleClient,
    thread: dict[str, Any],
    user_id: str,
) -> Party:
    if str(thread.get("customer_id")) == user_id:
        return "customer"
    vendor_id = str(thread.get("vendor_id") or "")
    owner = _vendor_owner_user_id(service_client, vendor_id)
    if owner == user_id:
        return "vendor"
    raise _thread_not_found()


def _load_thread_for_party(
    service_client: _ServiceRoleClient,
    thread_id: str,
    user_id: str,
) -> tuple[dict[str, Any], Party]:
    if not _valid_uuid(thread_id):
        raise _thread_not_found()
    response = (
        service_client.client.table("rfq_threads")
        .select(THREAD_SELECT)
        .eq("id", thread_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise _thread_not_found()
    party = _resolve_party(service_client, row, user_id)
    return row, party


def _find_open_thread(
    service_client: _ServiceRoleClient,
    *,
    customer_id: str,
    listing_id: str | None,
    service_id: str | None,
) -> dict[str, Any] | None:
    query = (
        service_client.client.table("rfq_threads")
        .select(THREAD_SELECT)
        .eq("customer_id", customer_id)
        .neq("status", "rejected")
        .neq("status", "accepted")
    )
    if listing_id:
        query = query.eq("listing_id", listing_id)
    else:
        query = query.eq("service_id", service_id)
    response = query.limit(1).maybe_single().execute()
    return _single_row(response)


def _insert_message(
    service_client: _ServiceRoleClient,
    *,
    thread_id: str,
    sender_role: str,
    sender_id: str,
    body: str,
) -> dict[str, Any]:
    now = _now_iso()
    message_id = str(uuid.uuid4())
    payload = {
        "id": message_id,
        "thread_id": thread_id,
        "sender_role": sender_role,
        "sender_id": sender_id,
        "body": body,
        "created_at": now,
    }
    service_client.client.table("rfq_messages").insert(payload).execute()
    service_client.client.table("rfq_threads").update(
        {"last_message_at": now}
    ).eq("id", thread_id).execute()
    return payload


def _notification_payload(thread: dict[str, Any]) -> dict[str, Any]:
    """Outbox payload for RFQ events — no message body off-platform."""
    return {
        "thread_id": str(thread.get("id")),
        "vendor_id": str(thread.get("vendor_id")),
        "customer_id": str(thread.get("customer_id")),
        "listing_id": thread.get("listing_id"),
        "service_id": thread.get("service_id"),
    }


def _notify_counterparty(
    service_client: _ServiceRoleClient,
    *,
    thread: dict[str, Any],
    party: Party,
    template: str,
    message_id: str | None = None,
) -> None:
    entity_suffix = message_id or str(thread.get("id"))
    if template == RFQ_OPENED_TEMPLATE:
        event_type = "rfq-opened"
    elif template == RFQ_QUOTED_TEMPLATE:
        event_type = "rfq-quoted"
    else:
        event_type = "rfq-replied"
    enqueue_outbox_row(
        service_client.client,
        event_type=event_type,
        entity_id=f"{thread.get('id')}:{entity_suffix}",
        channel="whatsapp",
        template=template,
        payload=_notification_payload(thread),
    )


@router.post("", response_model=CreateRfqResponse)
async def create_rfq(
    body: CreateRfqRequest,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> CreateRfqResponse:
    if bool(body.listing_id) == bool(body.service_id):
        raise AppError(
            code="rfq.invalid_subject",
            message="Provide exactly one of listing_id or service_id",
            http_status=422,
            details={},
        )

    _rate_limit(
        request,
        current_user.id,
        service_client,
        scope_suffix="create",
        user_limit_per_hour=NEW_THREADS_PER_HOUR,
    )
    _screen_body(body.requested_details)
    details = _mask_contacts(body.requested_details)

    if body.listing_id:
        if not _valid_uuid(body.listing_id):
            raise _subject_not_found()
        vendor_id = _resolve_listing_vendor(service_client, body.listing_id, current_user.id)
        subject_filter = {"listing_id": body.listing_id, "service_id": None}
    else:
        assert body.service_id is not None
        if not _valid_uuid(body.service_id):
            raise _subject_not_found()
        vendor_id = _resolve_service_vendor(service_client, body.service_id)
        subject_filter = {"listing_id": None, "service_id": body.service_id}

    vendor_owner = _vendor_owner_user_id(service_client, vendor_id)
    if vendor_owner == current_user.id:
        raise AppError(
            code="rfq.own_listing",
            message="You cannot request a quote on your own listing",
            http_status=403,
            details={},
        )

    existing = _find_open_thread(
        service_client,
        customer_id=current_user.id,
        listing_id=body.listing_id,
        service_id=body.service_id,
    )
    reused = existing is not None
    now = _now_iso()

    if existing is not None:
        thread_id = str(existing["id"])
        thread_row = existing
    else:
        thread_id = str(uuid.uuid4())
        thread_row = {
            "id": thread_id,
            "customer_id": current_user.id,
            "vendor_id": vendor_id,
            **subject_filter,
            "requested_details": details,
            "status": "pending",
            "quote_price_ngwee": None,
            "quote_valid_until": None,
            "quoted_at": None,
            "last_message_at": now,
            "created_at": now,
        }
        try:
            service_client.client.table("rfq_threads").insert(thread_row).execute()
        except Exception as exc:
            if _is_unique_violation(exc):
                raced = _find_open_thread(
                    service_client,
                    customer_id=current_user.id,
                    listing_id=body.listing_id,
                    service_id=body.service_id,
                )
                if raced is None:
                    raise
                thread_id = str(raced["id"])
                thread_row = raced
                reused = True
            else:
                raise

    message_row = _insert_message(
        service_client,
        thread_id=thread_id,
        sender_role="customer",
        sender_id=current_user.id,
        body=details,
    )

    if not reused:
        _notify_counterparty(
            service_client,
            thread=thread_row,
            party="customer",
            template=RFQ_OPENED_TEMPLATE,
            message_id=message_row["id"],
        )

    refreshed = (
        service_client.client.table("rfq_threads")
        .select(THREAD_SELECT)
        .eq("id", thread_id)
        .maybe_single()
        .execute()
    )
    final_thread = _single_row(refreshed) or thread_row

    return CreateRfqResponse(
        thread=_thread_to_response(final_thread),
        message=_message_to_response(message_row),
        reused_existing_thread=reused,
    )


@router.get("", response_model=RfqThreadListResponse)
async def list_rfq_threads(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
    party: Annotated[Party, Query()] = "customer",
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RfqThreadListResponse:
    query = service_client.client.table("rfq_threads").select(THREAD_SELECT)
    if party == "customer":
        query = query.eq("customer_id", current_user.id)
    else:
        vendor_resp = (
            service_client.client.table("vendors")
            .select("id")
            .eq("owner_user_id", current_user.id)
            .limit(1)
            .execute()
        )
        vendor_rows = _rows(vendor_resp)
        if not vendor_rows:
            return RfqThreadListResponse(items=[], limit=limit, offset=offset)
        query = query.eq("vendor_id", str(vendor_rows[0]["id"]))

    response = (
        query.order("last_message_at", desc=True)
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    items = [_thread_to_response(row) for row in _rows(response)]
    return RfqThreadListResponse(items=items, limit=limit, offset=offset)


@router.get("/{thread_id}", response_model=RfqThreadResponse)
async def get_rfq_thread(
    thread_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> RfqThreadResponse:
    thread, _party = _load_thread_for_party(service_client, thread_id, current_user.id)
    return _thread_to_response(thread)


@router.get("/{thread_id}/messages", response_model=RfqMessagesResponse)
async def list_rfq_messages(
    thread_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RfqMessagesResponse:
    _load_thread_for_party(service_client, thread_id, current_user.id)
    response = (
        service_client.client.table("rfq_messages")
        .select(MESSAGE_SELECT)
        .eq("thread_id", thread_id)
        .order("created_at", desc=False)
        .range(offset, offset + limit - 1)
        .execute()
    )
    items = [_message_to_response(row) for row in _rows(response)]
    return RfqMessagesResponse(thread_id=thread_id, items=items, limit=limit, offset=offset)


@router.post("/{thread_id}/messages", response_model=RfqMessageResponse)
async def post_rfq_message(
    thread_id: str,
    body: PostRfqMessageRequest,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> RfqMessageResponse:
    thread, party = _load_thread_for_party(service_client, thread_id, current_user.id)
    if str(thread.get("status")) in {"accepted", "rejected"}:
        raise AppError(
            code="rfq.thread_closed",
            message="This RFQ is closed",
            http_status=409,
            details={"status": thread.get("status")},
        )

    _rate_limit(
        request,
        current_user.id,
        service_client,
        scope_suffix="message",
        user_limit_per_hour=MESSAGES_PER_HOUR,
    )
    _screen_body(body.body)
    masked = _mask_contacts(body.body)

    message_row = _insert_message(
        service_client,
        thread_id=thread_id,
        sender_role=party,
        sender_id=current_user.id,
        body=masked,
    )
    _notify_counterparty(
        service_client,
        thread=thread,
        party=party,
        template=RFQ_REPLY_TEMPLATE,
        message_id=message_row["id"],
    )
    return _message_to_response(message_row)


@router.post("/{thread_id}/quote", response_model=RfqThreadResponse)
async def issue_quote(
    thread_id: str,
    body: IssueQuoteRequest,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> RfqThreadResponse:
    thread, party = _load_thread_for_party(service_client, thread_id, current_user.id)
    if party != "vendor":
        raise AppError(
            code="rfq.forbidden",
            message="Only the vendor may issue a quote",
            http_status=403,
            details={},
        )
    if str(thread.get("status")) not in {"pending", "quoted"}:
        raise AppError(
            code="rfq.invalid_status",
            message="Quote cannot be issued for this RFQ",
            http_status=409,
            details={"status": thread.get("status")},
        )

    _rate_limit(
        request,
        current_user.id,
        service_client,
        scope_suffix="quote",
        user_limit_per_hour=MESSAGES_PER_HOUR,
    )

    if body.valid_until is not None:
        valid_until = body.valid_until.astimezone(UTC)
    else:
        days = body.validity_days or DEFAULT_QUOTE_VALIDITY_DAYS
        valid_until = datetime.now(UTC) + timedelta(days=days)

    if valid_until <= datetime.now(UTC):
        raise AppError(
            code="rfq.invalid_validity",
            message="Quote validity must be in the future",
            http_status=422,
            details={},
        )

    now = _now_iso()
    update_payload = {
        "status": "quoted",
        "quote_price_ngwee": body.price_ngwee,
        "quote_valid_until": valid_until.isoformat(),
        "quoted_at": now,
        "last_message_at": now,
    }
    service_client.client.table("rfq_threads").update(update_payload).eq(
        "id", thread_id
    ).execute()

    if body.message:
        _screen_body(body.message)
        _insert_message(
            service_client,
            thread_id=thread_id,
            sender_role="vendor",
            sender_id=current_user.id,
            body=_mask_contacts(body.message),
        )

    _notify_counterparty(
        service_client,
        thread={**thread, **update_payload},
        party="vendor",
        template=RFQ_QUOTED_TEMPLATE,
    )

    refreshed = (
        service_client.client.table("rfq_threads")
        .select(THREAD_SELECT)
        .eq("id", thread_id)
        .maybe_single()
        .execute()
    )
    final = _single_row(refreshed)
    if final is None:
        raise _thread_not_found()
    return _thread_to_response(final)


@router.post("/{thread_id}/reject", response_model=RfqThreadResponse)
async def reject_rfq(
    thread_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> RfqThreadResponse:
    thread, party = _load_thread_for_party(service_client, thread_id, current_user.id)
    if str(thread.get("status")) in {"accepted", "rejected"}:
        raise AppError(
            code="rfq.invalid_status",
            message="RFQ is already closed",
            http_status=409,
            details={"status": thread.get("status")},
        )

    service_client.client.table("rfq_threads").update({"status": "rejected"}).eq(
        "id", thread_id
    ).execute()

    refreshed = (
        service_client.client.table("rfq_threads")
        .select(THREAD_SELECT)
        .eq("id", thread_id)
        .maybe_single()
        .execute()
    )
    final = _single_row(refreshed)
    if final is None:
        raise _thread_not_found()
    return _thread_to_response(final)


def load_rfq_for_cart_accept(
    service_client: Any,
    *,
    rfq_id: str,
    customer_id: str,
) -> dict[str, Any]:
    """Load a quoted listing RFQ for cart accept. Used by cart router."""
    if not _valid_uuid(rfq_id):
        raise _thread_not_found()
    response = (
        service_client.table("rfq_threads")
        .select(THREAD_SELECT)
        .eq("id", rfq_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None or str(row.get("customer_id")) != customer_id:
        raise _thread_not_found()
    if row.get("listing_id") is None:
        raise AppError(
            code="rfq.no_listing",
            message="This RFQ is not linked to a product listing",
            http_status=422,
            details={},
        )
    if str(row.get("status")) != "quoted":
        raise AppError(
            code="rfq.not_quoted",
            message="RFQ must be in quoted status to accept",
            http_status=409,
            details={"status": row.get("status")},
        )
    valid_until_raw = row.get("quote_valid_until")
    if valid_until_raw:
        valid_until = datetime.fromisoformat(str(valid_until_raw).replace("Z", "+00:00"))
        if valid_until.tzinfo is None:
            valid_until = valid_until.replace(tzinfo=UTC)
        if valid_until <= datetime.now(UTC):
            raise AppError(
                code="rfq.quote_expired",
                message="Quote has expired",
                http_status=409,
                details={},
            )
    quote_price = row.get("quote_price_ngwee")
    if quote_price is None or int(quote_price) <= 0:
        raise AppError(
            code="rfq.no_quote_price",
            message="RFQ has no valid quote price",
            http_status=409,
            details={},
        )
    return row
