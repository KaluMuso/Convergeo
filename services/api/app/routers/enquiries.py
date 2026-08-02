"""Listing-anchored customer→business enquiry threads (R02-P13b, D37).

The API half of migration ``0082_enquiry_threads.sql``. The structural fence
lives in the schema (distinct NOT NULL party columns, ``vendor_id <>
customer_id`` CHECK, subject-ownership trigger); this router adds the
behavioural half:

* the vendor party is derived SERVER-SIDE from the subject row
  (``vendor_listings.vendor_id`` / ``events.organiser_vendor_id`` /
  ``services.vendor_id``) — never from client input, so a customer↔customer
  thread cannot be requested, let alone stored;
* outsiders get a 404 byte-identical to a thread that never existed — the
  same no-existence-oracle posture as D36's wholesale omission;
* message bodies are untrusted data: screened by the existing prohibited
  screen (reject-on-match, same helper as listing creation) and contact-
  masked by the existing pre-escrow strip (M11-P06) — no new moderation
  mechanism is invented here;
* notifications ride the existing ``notification_outbox`` (WhatsApp Cloud
  API path; WAHA is forbidden — D15/D35/D37) and NEVER carry the message
  body off-platform, only the fact that a message exists.
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
from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import Field, field_validator

router = APIRouter(prefix="/enquiries", tags=["enquiries"])

SubjectKind = Literal["listing", "event", "service"]
Party = Literal["customer", "vendor"]

THREAD_SELECT = (
    "id, subject_kind, subject_id, vendor_id, customer_id, status, last_message_at, created_at"
)
MESSAGE_SELECT = "id, thread_id, sender_role, body, created_at"

#: subject_kind → (table, owner column, statuses an enquiry may target).
#: NB: ``events`` names its owner ``organiser_vendor_id`` (0004), not
#: ``vendor_id`` — the 0082 guard trigger makes the same distinction.
SUBJECT_TABLES: dict[str, tuple[str, str, frozenset[str]]] = {
    "listing": ("vendor_listings", "vendor_id", frozenset({"active"})),
    "event": ("events", "organiser_vendor_id", frozenset({"published"})),
    "service": ("services", "vendor_id", frozenset({"active"})),
}

MAX_PAGE_SIZE = 50
MAX_BODY_CHARS = 2000  # mirrors the enquiry_messages CHECK (1..2000 after btrim)

# Per-user ceilings (hourly — an enquiry is a conversation, not a firehose).
# The per-minute envelope for these routes is declared in
# app/core/ratelimit_policies.py; these are the tighter product limits.
NEW_THREADS_PER_HOUR = 10
MESSAGES_PER_HOUR = 60
IP_WRITES_PER_MINUTE = 30

OPENED_TEMPLATE = "enquiry_opened"
REPLY_TEMPLATE = "enquiry_reply"


class _ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


class _BodyMixin(StrictModel):
    body: str = Field(min_length=1, max_length=MAX_BODY_CHARS)

    @field_validator("body", mode="before")
    @classmethod
    def _strip_body(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class CreateEnquiryRequest(_BodyMixin):
    subject_kind: SubjectKind
    subject_id: str


class PostMessageRequest(_BodyMixin):
    pass


class EnquiryMessageResponse(StrictModel):
    id: str
    thread_id: str
    sender_role: str
    body: str
    created_at: str


class EnquiryThreadResponse(StrictModel):
    id: str
    subject_kind: str
    subject_id: str
    vendor_id: str
    customer_id: str
    status: str
    last_message_at: str | None
    created_at: str


class CreateEnquiryResponse(StrictModel):
    thread: EnquiryThreadResponse
    message: EnquiryMessageResponse
    #: True when the open thread for (subject, customer) already existed and
    #: the message was appended to it instead of a duplicate being created.
    reused_existing_thread: bool


class EnquiryMessagePostedResponse(StrictModel):
    thread: EnquiryThreadResponse
    message: EnquiryMessageResponse


class EnquiryThreadListResponse(StrictModel):
    items: list[EnquiryThreadResponse]
    limit: int
    offset: int


class EnquiryMessagesResponse(StrictModel):
    thread_id: str
    items: list[EnquiryMessageResponse]
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Row helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Errors — single constructors so equal cases stay byte-identical
# ---------------------------------------------------------------------------


def _thread_not_found() -> AppError:
    """The ONE thread 404.

    Raised identically for a thread id that does not exist and for a thread
    the caller is not a party to. Byte-identical code/message/details means
    the response is no existence oracle: an outsider cannot distinguish
    "there is a private conversation here" from "there is nothing here".
    """
    return AppError(
        code="enquiry.not_found",
        message="Enquiry thread not found",
        http_status=404,
        details={},
    )


def _subject_not_found() -> AppError:
    """The ONE subject 404 — absent, inactive/unpublished and (for listings)
    wholesale-hidden-under-D36 must all answer identically."""
    return AppError(
        code="enquiry.subject_not_found",
        message="Subject not found",
        http_status=404,
        details={},
    )


# ---------------------------------------------------------------------------
# Rate limiting — existing primitive (bump_rate_counter / rate_counters)
# ---------------------------------------------------------------------------


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
        scope=f"enquiries_ip_{scope_suffix}",
        key=ip,
        window=timedelta(minutes=1),
        limit=IP_WRITES_PER_MINUTE,
        client=service_client.client,
    )
    if not allowed_ip:
        raise_rate_limited(
            retry_after=ip_retry,
            message_key="enquiries.errors.rateLimited",
            message="Too many enquiry requests",
        )
    allowed_user, user_retry = bump_rate_counter(
        scope=f"enquiries_user_{scope_suffix}",
        key=user_id,
        window=timedelta(hours=1),
        limit=user_limit_per_hour,
        client=service_client.client,
    )
    if not allowed_user:
        raise_rate_limited(
            retry_after=user_retry,
            message_key="enquiries.errors.rateLimited",
            message="Too many enquiry requests",
        )


# ---------------------------------------------------------------------------
# Untrusted-body handling — reuse, do not fork (no new moderation mechanism)
# ---------------------------------------------------------------------------


def _screen_body(body: str) -> None:
    """Reject-on-match prohibited screen — the SAME helper listing creation
    uses (app.services.moderation.prohibited). Bodies are data, never
    instructions; on a match the message is refused, not rewritten."""
    result = screen_listing(description=body)
    if not result.allowed:
        raise AppError(
            code="enquiry.prohibited_content",
            message="Message contains prohibited content",
            http_status=422,
            details={"reason": result.reason or "keyword"},
        )


def _mask_contacts(body: str) -> str:
    """Pre-escrow disintermediation guard — the SAME strip used on
    pre-acceptance RFQ quotes (M11-P06). Each contact span is replaced with a
    visible notice token, never silently deleted. Truncated defensively so a
    token-inflated body can never violate the DB's 2000-char CHECK."""
    masked = strip_contacts(body).clean_text.strip()
    return masked[:MAX_BODY_CHARS]


# ---------------------------------------------------------------------------
# Subject / party resolution — the D37 fence's behavioural half
# ---------------------------------------------------------------------------


def _resolve_subject_vendor(
    service_client: _ServiceRoleClient,
    *,
    subject_kind: str,
    subject_id: str,
    caller_user_id: str,
) -> str:
    """Return the vendor that owns the subject, or raise the subject 404.

    The vendor is derived from the subject row alone — client input never
    names a counterparty, which is what keeps a customer↔customer thread
    unrepresentable at the API as well as in the schema (D37).
    """
    table, owner_column, live_statuses = SUBJECT_TABLES[subject_kind]
    columns = f"id, {owner_column}, status"
    if subject_kind == "listing":
        columns += ", wholesale"
    response = (
        service_client.client.table(table)
        .select(columns)
        .eq("id", subject_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise _subject_not_found()
    if str(row.get("status") or "") not in live_statuses:
        raise _subject_not_found()
    if subject_kind == "listing" and bool(row.get("wholesale")):
        # D36: a wholesale-only listing is invisible to non-verified callers.
        # An enquiry must not become the existence oracle the catalog closed,
        # so the answer here is the same 404 as a listing that never existed.
        buyer = fetch_business_buyer(service_client.client, caller_user_id)
        if not (buyer and buyer.get("status") == "verified"):
            raise _subject_not_found()
    owner_vendor = row.get(owner_column)
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


def _vendor_id_owned_by(service_client: _ServiceRoleClient, user_id: str) -> str | None:
    response = (
        service_client.client.table("vendors")
        .select("id, owner_user_id")
        .eq("owner_user_id", user_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        return None
    vendor_id = row.get("id")
    return str(vendor_id) if vendor_id else None


def _load_thread_for_party(
    service_client: _ServiceRoleClient,
    thread_id: str,
    user_id: str,
) -> tuple[dict[str, Any], Party]:
    """Load a thread the caller is a party to, or raise the identical 404."""
    if not _valid_uuid(thread_id):
        raise _thread_not_found()
    response = (
        service_client.client.table("enquiry_threads")
        .select(THREAD_SELECT)
        .eq("id", thread_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise _thread_not_found()
    if str(row.get("customer_id")) == user_id:
        return row, "customer"
    owner = _vendor_owner_user_id(service_client, str(row.get("vendor_id")))
    if owner is not None and owner == user_id:
        return row, "vendor"
    raise _thread_not_found()


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def _fetch_open_thread(
    service_client: _ServiceRoleClient,
    *,
    customer_id: str,
    subject_kind: str,
    subject_id: str,
) -> dict[str, Any] | None:
    response = (
        service_client.client.table("enquiry_threads")
        .select(THREAD_SELECT)
        .eq("customer_id", customer_id)
        .eq("subject_kind", subject_kind)
        .eq("subject_id", subject_id)
        .neq("status", "closed")
        .limit(1)
        .execute()
    )
    rows = _rows(response)
    return rows[0] if rows else None


def _insert_thread(
    service_client: _ServiceRoleClient,
    *,
    subject_kind: str,
    subject_id: str,
    vendor_id: str,
    customer_id: str,
    now: str,
) -> dict[str, Any]:
    thread_id = str(uuid.uuid4())
    payload = {
        "id": thread_id,
        "subject_kind": subject_kind,
        "subject_id": subject_id,
        "vendor_id": vendor_id,
        "customer_id": customer_id,
        "status": "open",
        "last_message_at": now,
        "created_at": now,
    }
    response = service_client.client.table("enquiry_threads").insert(payload).execute()
    return _single_row(response) or payload


def _insert_message(
    service_client: _ServiceRoleClient,
    *,
    thread_id: str,
    sender_role: Party,
    sender_id: str,
    body: str,
    now: str,
) -> dict[str, Any]:
    message_id = str(uuid.uuid4())
    payload = {
        "id": message_id,
        "thread_id": thread_id,
        "sender_role": sender_role,
        "sender_id": sender_id,
        "body": body,
        "created_at": now,
    }
    response = service_client.client.table("enquiry_messages").insert(payload).execute()
    return _single_row(response) or payload


def _touch_thread(
    service_client: _ServiceRoleClient,
    *,
    thread_id: str,
    status: str,
    now: str,
) -> None:
    (
        service_client.client.table("enquiry_threads")
        .update({"status": status, "last_message_at": now})
        .eq("id", thread_id)
        .execute()
    )


# ---------------------------------------------------------------------------
# Notifications — existing outbox only; the body NEVER leaves the platform
# ---------------------------------------------------------------------------


def _notification_payload(thread: dict[str, Any]) -> dict[str, Any]:
    """Outbox payload for enquiry events.

    Deliberately contains NO message body: the WhatsApp/SMS/email notification
    says a message exists and links back into the app. Message content is
    private correspondence and never rides an off-platform channel (D37).
    """
    return {
        "thread_id": str(thread.get("id")),
        "vendor_id": str(thread.get("vendor_id")),
        "customer_id": str(thread.get("customer_id")),
        "subject_kind": str(thread.get("subject_kind")),
        "subject_id": str(thread.get("subject_id")),
    }


def _notify_vendor_enquiry_opened(
    service_client: _ServiceRoleClient,
    *,
    thread: dict[str, Any],
    message_id: str,
) -> None:
    enqueue_outbox_row(
        service_client.client,
        event_type="enquiry-opened",
        entity_id=f"{thread.get('id')}:{message_id}",
        channel="whatsapp",
        template=OPENED_TEMPLATE,
        payload=_notification_payload(thread),
    )


def _notify_customer_vendor_replied(
    service_client: _ServiceRoleClient,
    *,
    thread: dict[str, Any],
    message_id: str,
) -> None:
    enqueue_outbox_row(
        service_client.client,
        event_type="enquiry-replied",
        entity_id=f"{thread.get('id')}:{message_id}",
        channel="whatsapp",
        template=REPLY_TEMPLATE,
        payload=_notification_payload(thread),
    )


# ---------------------------------------------------------------------------
# Response mapping
# ---------------------------------------------------------------------------


def _thread_response(row: dict[str, Any]) -> EnquiryThreadResponse:
    last_message_at = row.get("last_message_at")
    return EnquiryThreadResponse(
        id=str(row["id"]),
        subject_kind=str(row["subject_kind"]),
        subject_id=str(row["subject_id"]),
        vendor_id=str(row["vendor_id"]),
        customer_id=str(row["customer_id"]),
        status=str(row["status"]),
        last_message_at=str(last_message_at) if last_message_at else None,
        created_at=str(row["created_at"]),
    )


def _message_response(row: dict[str, Any]) -> EnquiryMessageResponse:
    return EnquiryMessageResponse(
        id=str(row["id"]),
        thread_id=str(row["thread_id"]),
        sender_role=str(row["sender_role"]),
        body=str(row["body"]),
        created_at=str(row["created_at"]),
    )


def _thread_sort_key(row: dict[str, Any]) -> str:
    value = row.get("last_message_at") or row.get("created_at") or ""
    return str(value)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=CreateEnquiryResponse, status_code=201)
async def create_enquiry(
    body: CreateEnquiryRequest,
    request: Request,
    response: Response,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> CreateEnquiryResponse:
    _rate_limit(
        request,
        current_user.id,
        service_client,
        scope_suffix="create",
        user_limit_per_hour=NEW_THREADS_PER_HOUR,
    )
    _screen_body(body.body)

    if not _valid_uuid(body.subject_id):
        raise _subject_not_found()
    vendor_id = _resolve_subject_vendor(
        service_client,
        subject_kind=body.subject_kind,
        subject_id=body.subject_id,
        caller_user_id=current_user.id,
    )

    owner_user_id = _vendor_owner_user_id(service_client, vendor_id)
    if owner_user_id is not None and owner_user_id == current_user.id:
        raise AppError(
            code="enquiry.own_subject",
            message="You cannot open an enquiry about your own listing",
            http_status=400,
            details={},
        )

    stored_body = _mask_contacts(body.body)
    now = _now_iso()

    existing = _fetch_open_thread(
        service_client,
        customer_id=current_user.id,
        subject_kind=body.subject_kind,
        subject_id=body.subject_id,
    )
    created = False
    if existing is None:
        try:
            thread = _insert_thread(
                service_client,
                subject_kind=body.subject_kind,
                subject_id=body.subject_id,
                vendor_id=vendor_id,
                customer_id=current_user.id,
                now=now,
            )
            created = True
        except Exception as exc:
            if not _is_unique_violation(exc):
                raise
            # Concurrent create hit enquiry_threads_one_open_per_subject —
            # the reopen semantics apply: append to the winner, never 500.
            racer = _fetch_open_thread(
                service_client,
                customer_id=current_user.id,
                subject_kind=body.subject_kind,
                subject_id=body.subject_id,
            )
            if racer is None:
                raise
            thread = racer
    else:
        thread = existing

    thread_id = str(thread["id"])
    message = _insert_message(
        service_client,
        thread_id=thread_id,
        sender_role="customer",
        sender_id=current_user.id,
        body=stored_body,
        now=now,
    )
    # A customer message (re)opens the conversation for the vendor.
    _touch_thread(service_client, thread_id=thread_id, status="open", now=now)
    thread = {**thread, "status": "open", "last_message_at": now}

    if created:
        _notify_vendor_enquiry_opened(service_client, thread=thread, message_id=str(message["id"]))
    else:
        response.status_code = 200

    return CreateEnquiryResponse(
        thread=_thread_response(thread),
        message=_message_response(message),
        reused_existing_thread=not created,
    )


@router.get("", response_model=EnquiryThreadListResponse)
async def list_enquiries(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EnquiryThreadListResponse:
    """My threads: as customer always; as vendor when I own a vendor."""
    fetch_cap = offset + limit
    customer_rows = _rows(
        service_client.client.table("enquiry_threads")
        .select(THREAD_SELECT)
        .eq("customer_id", current_user.id)
        .order("last_message_at", desc=True)
        .limit(fetch_cap)
        .execute()
    )
    vendor_rows: list[dict[str, Any]] = []
    owned_vendor_id = _vendor_id_owned_by(service_client, current_user.id)
    if owned_vendor_id is not None:
        vendor_rows = _rows(
            service_client.client.table("enquiry_threads")
            .select(THREAD_SELECT)
            .eq("vendor_id", owned_vendor_id)
            .order("last_message_at", desc=True)
            .limit(fetch_cap)
            .execute()
        )

    merged: dict[str, dict[str, Any]] = {}
    for row in customer_rows + vendor_rows:
        merged[str(row["id"])] = row
    ordered = sorted(merged.values(), key=_thread_sort_key, reverse=True)
    page = ordered[offset : offset + limit]
    return EnquiryThreadListResponse(
        items=[_thread_response(row) for row in page],
        limit=limit,
        offset=offset,
    )


@router.get("/{thread_id}/messages", response_model=EnquiryMessagesResponse)
async def list_enquiry_messages(
    thread_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EnquiryMessagesResponse:
    _load_thread_for_party(service_client, thread_id, current_user.id)
    rows = _rows(
        service_client.client.table("enquiry_messages")
        .select(MESSAGE_SELECT)
        .eq("thread_id", thread_id)
        .order("created_at", desc=False)
        .limit(offset + limit)
        .execute()
    )
    page = rows[offset : offset + limit]
    return EnquiryMessagesResponse(
        thread_id=thread_id,
        items=[_message_response(row) for row in page],
        limit=limit,
        offset=offset,
    )


@router.post("/{thread_id}/messages", response_model=EnquiryMessagePostedResponse, status_code=201)
async def post_enquiry_message(
    thread_id: str,
    body: PostMessageRequest,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> EnquiryMessagePostedResponse:
    _rate_limit(
        request,
        current_user.id,
        service_client,
        scope_suffix="message",
        user_limit_per_hour=MESSAGES_PER_HOUR,
    )
    _screen_body(body.body)

    thread, party = _load_thread_for_party(service_client, thread_id, current_user.id)
    if str(thread.get("status")) == "closed":
        raise AppError(
            code="enquiry.closed",
            message="This enquiry is closed",
            http_status=409,
            details={},
        )

    stored_body = _mask_contacts(body.body)
    now = _now_iso()
    message = _insert_message(
        service_client,
        thread_id=str(thread["id"]),
        sender_role=party,
        sender_id=current_user.id,
        body=stored_body,
        now=now,
    )
    new_status = "answered" if party == "vendor" else "open"
    _touch_thread(service_client, thread_id=str(thread["id"]), status=new_status, now=now)
    thread = {**thread, "status": new_status, "last_message_at": now}

    if party == "vendor":
        _notify_customer_vendor_replied(
            service_client, thread=thread, message_id=str(message["id"])
        )

    return EnquiryMessagePostedResponse(
        thread=_thread_response(thread),
        message=_message_response(message),
    )


@router.post("/{thread_id}/close", response_model=EnquiryThreadResponse)
async def close_enquiry(
    thread_id: str,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> EnquiryThreadResponse:
    """Either party may close; closing an already-closed thread is a no-op."""
    _rate_limit(
        request,
        current_user.id,
        service_client,
        scope_suffix="close",
        user_limit_per_hour=MESSAGES_PER_HOUR,
    )
    thread, _party = _load_thread_for_party(service_client, thread_id, current_user.id)
    if str(thread.get("status")) != "closed":
        (
            service_client.client.table("enquiry_threads")
            .update({"status": "closed"})
            .eq("id", str(thread["id"]))
            .execute()
        )
        thread = {**thread, "status": "closed"}
    return _thread_response(thread)
