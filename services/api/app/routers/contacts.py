"""T28 — social contacts: handles, requests, discovery, chat (flag ``social_contacts``)."""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Annotated, Any, Final, Literal, Protocol
from uuid import UUID

from app.core.auth import CurrentUser, get_current_user
from app.core.ratelimit import bump_rate_counter, raise_rate_limited
from app.core.ratelimit_policies import POLICIES, RateLimitPolicy, route_id
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.social.errors import map_social_rpc_error, rpc_rows
from app.services.social.flag import require_social_contacts_enabled
from app.services.social.phone import (
    client_hash_to_storage_hash,
    e164_sha256_hex,
    require_phone_pepper,
    zm_e164_from_profile_phone,
)
from app.settings import Settings, get_settings
from fastapi import APIRouter, Depends, Query
from postgrest.exceptions import APIError
from pydantic import Field, field_validator

router = APIRouter(tags=["contacts"])

_HANDLE_RE: Final = re.compile(r"^[a-z0-9_.]{3,24}$")
_UUID_RE: Final = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_MAX_CLIENT_HASHES: Final = 500
_DB_HASH_CHUNK: Final = 200
_QR_PREFIX: Final = "vgo:add:"

DISCOVER_POLICY: Final = RateLimitPolicy(
    scope="social_discover_phones", limit=5, window=timedelta(days=1)
)
WRITE_POLICY: Final = RateLimitPolicy(scope="social_write", limit=60, window=timedelta(minutes=1))
READ_POLICY: Final = RateLimitPolicy(scope="social_read", limit=120, window=timedelta(minutes=1))

for _method, _path in (
    ("PUT", "/me/handle"),
    ("POST", "/contacts/requests"),
    ("POST", "/contacts/requests/{request_id}/accept"),
    ("POST", "/contacts/requests/{request_id}/ignore"),
    ("DELETE", "/contacts/{user_id}"),
    ("POST", "/contacts/{user_id}/block"),
    ("POST", "/contacts/{user_id}/report"),
    ("POST", "/contacts/discover-phones"),
    ("PUT", "/me/phone-discovery"),
    ("POST", "/chats/{thread_id}/messages"),
):
    POLICIES.setdefault(route_id(_method, _path), WRITE_POLICY)


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _require_flag(service_client: ServiceRoleClient) -> None:
    require_social_contacts_enabled(service_client)


def _rate_limit(user_id: str, policy: RateLimitPolicy, service_client: ServiceRoleClient) -> None:
    allowed, retry_after = bump_rate_counter(
        scope=policy.scope,
        key=user_id,
        window=policy.window,
        limit=policy.limit,
        client=service_client.client,
    )
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key="social.errors.rateLimited",
            message="Too many social requests",
        )


def _rpc(
    service_client: ServiceRoleClient,
    name: str,
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    try:
        return rpc_rows(service_client.client.rpc(name, params).execute())
    except APIError as exc:
        raise map_social_rpc_error(exc) from exc


def _actor(user_id: str) -> dict[str, str]:
    return {"p_actor": user_id}


# --- Schemas ------------------------------------------------------------------


class HandleBody(StrictModel):
    handle: str = Field(min_length=3, max_length=26)

    @field_validator("handle")
    @classmethod
    def strip_at(cls, value: str) -> str:
        return value.lstrip("@").strip().lower()


class HandleView(StrictModel):
    handle: str


class QrView(StrictModel):
    handle: str
    payload: str
    share_path: str


class PeopleCard(StrictModel):
    user_id: str
    handle: str
    display_name: str | None = None
    is_contact: bool = False


class ContactRequestCreate(StrictModel):
    to_handle: str = Field(min_length=3, max_length=26)
    note: str | None = Field(default=None, max_length=80)


class ContactRequestView(StrictModel):
    id: str
    from_user: str
    to_user: str
    note: str | None = None
    status: str
    created_at: str
    outgoing: bool


class ContactRequestList(StrictModel):
    items: list[ContactRequestView]


class ContactRequestSent(StrictModel):
    request_id: str
    status: str
    thread_id: str | None = None


class ContactView(StrictModel):
    user_id: str
    handle: str | None = None
    display_name: str | None = None
    thread_id: str | None = None


class ContactList(StrictModel):
    items: list[ContactView]


class DiscoverPhonesBody(StrictModel):
    hashes: list[str] = Field(min_length=1, max_length=_MAX_CLIENT_HASHES)


class DiscoverMatch(StrictModel):
    user_id: str
    handle: str | None = None
    display_name: str | None = None


class DiscoverMatches(StrictModel):
    items: list[DiscoverMatch]


class PhoneDiscoveryBody(StrictModel):
    enabled: bool


class PhoneDiscoveryView(StrictModel):
    enabled: bool
    pepper_configured: bool


class ChatThreadView(StrictModel):
    id: str
    other_user_id: str
    other_handle: str | None = None
    other_display_name: str | None = None
    last_message_at: str | None = None


class ChatThreadList(StrictModel):
    items: list[ChatThreadView]


class ChatMessageView(StrictModel):
    id: str
    thread_id: str
    sender: str
    kind: str
    body: str | None = None
    card: dict[str, Any] | None = None
    created_at: str


class ChatMessageList(StrictModel):
    items: list[ChatMessageView]


class ChatMessageCreate(StrictModel):
    kind: Literal["text", "share_card"]
    body: str | None = Field(default=None, max_length=2000)
    card: dict[str, Any] | None = None


class ChatMessageSent(StrictModel):
    message_id: str
    created_at: str


class ReportBody(StrictModel):
    reason: Literal["spam", "harassment", "scam", "other"] = "other"
    detail: str | None = Field(default=None, max_length=500)


class ReportResponse(StrictModel):
    ok: bool = True
    flag_id: str


class OkResponse(StrictModel):
    ok: bool = True


# --- Handle + QR --------------------------------------------------------------


@router.get("/me/handle", response_model=HandleView)
async def get_my_handle(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> HandleView:
    _require_flag(service_client)
    _rate_limit(current_user.id, READ_POLICY, service_client)
    row = _rows(
        service_client.client.table("user_handles")
        .select("handle")
        .eq("user_id", current_user.id)
        .maybe_single()
        .execute()
    )
    if not row:
        raise AppError(
            code="not_found",
            message="Handle not set",
            http_status=404,
            details={"message_key": "social.errors.handleNotSet"},
        )
    return HandleView(handle=str(row[0]["handle"]))


@router.put("/me/handle", response_model=HandleView)
async def put_my_handle(
    body: HandleBody,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> HandleView:
    _require_flag(service_client)
    _rate_limit(current_user.id, WRITE_POLICY, service_client)
    if not _HANDLE_RE.fullmatch(body.handle):
        raise AppError(
            code="validation_error",
            message="Invalid handle",
            http_status=422,
            details={"message_key": "social.errors.handleInvalid"},
        )
    try:
        data = service_client.client.rpc(
            "set_my_handle",
            {"p_handle": body.handle, "p_actor": current_user.id},
        ).execute()
    except APIError as exc:
        raise map_social_rpc_error(exc) from exc
    raw = getattr(data, "data", None)
    handle = body.handle
    if isinstance(raw, str):
        handle = raw
    return HandleView(handle=handle)


@router.get("/me/qr", response_model=QrView)
async def get_my_qr(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> QrView:
    _require_flag(service_client)
    view = await get_my_handle(current_user, service_client)
    payload = f"{_QR_PREFIX}{view.handle}"
    return QrView(
        handle=view.handle,
        payload=payload,
        share_path=f"/u/{view.handle}",
    )


@router.get("/people/{handle}", response_model=PeopleCard)
async def get_people_card(
    handle: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> PeopleCard:
    _require_flag(service_client)
    _rate_limit(current_user.id, READ_POLICY, service_client)
    cleaned = handle.lstrip("@").strip().lower()
    rows = _rpc(
        service_client,
        "lookup_handle_card",
        {"p_handle": cleaned, "p_actor": current_user.id},
    )
    if not rows:
        raise AppError(
            code="not_found",
            message="Person not found",
            http_status=404,
            details={"message_key": "social.errors.unavailable"},
        )
    row = rows[0]
    return PeopleCard(
        user_id=str(row["user_id"]),
        handle=str(row["handle"]),
        display_name=row.get("display_name"),
        is_contact=bool(row.get("is_contact")),
    )


# --- Requests -----------------------------------------------------------------


@router.post("/contacts/requests", response_model=ContactRequestSent)
async def create_contact_request(
    body: ContactRequestCreate,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ContactRequestSent:
    _require_flag(service_client)
    _rate_limit(current_user.id, WRITE_POLICY, service_client)
    rows = _rpc(
        service_client,
        "send_contact_request",
        {
            "p_to_handle": body.to_handle.lstrip("@"),
            "p_note": body.note,
            "p_actor": current_user.id,
        },
    )
    if not rows:
        raise AppError(code="internal_error", message="No response", http_status=500)
    row = rows[0]
    thread_id: str | None = None
    if str(row.get("status")) == "accepted":
        to_handle = body.to_handle.lstrip("@").lower()
        card_rows = _rpc(
            service_client,
            "lookup_handle_card",
            {"p_handle": to_handle, "p_actor": current_user.id},
        )
        if card_rows:
            thread_id = _find_thread_for_users(
                service_client, current_user.id, str(card_rows[0]["user_id"])
            )
    return ContactRequestSent(
        request_id=str(row["request_id"]),
        status=str(row["status"]),
        thread_id=thread_id,
    )


def _find_thread_for_users(
    service_client: ServiceRoleClient,
    me: str,
    other: str,
) -> str | None:
    user_a, user_b = _ordered_pair(me, other)
    rows = _rows(
        service_client.client.table("chat_threads")
        .select("id")
        .eq("user_a", user_a)
        .eq("user_b", user_b)
        .limit(1)
        .execute()
    )
    return str(rows[0]["id"]) if rows else None


@router.get("/contacts/requests", response_model=ContactRequestList)
async def list_contact_requests(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    box: Annotated[Literal["in", "out", "all"], Query()] = "all",
) -> ContactRequestList:
    _require_flag(service_client)
    _rate_limit(current_user.id, READ_POLICY, service_client)
    rows = _rpc(service_client, "my_contact_requests", {"p_actor": current_user.id})
    items: list[ContactRequestView] = []
    for row in rows:
        outgoing = bool(row.get("outgoing"))
        if box == "in" and outgoing:
            continue
        if box == "out" and not outgoing:
            continue
        items.append(
            ContactRequestView(
                id=str(row["id"]),
                from_user=str(row["from_user"]),
                to_user=str(row["to_user"]),
                note=row.get("note"),
                status=str(row["status"]),
                created_at=str(row["created_at"]),
                outgoing=outgoing,
            )
        )
    return ContactRequestList(items=items)


def _load_request_for_party(
    service_client: ServiceRoleClient,
    request_id: str,
    user_id: str,
) -> dict[str, Any]:
    if not _UUID_RE.fullmatch(request_id):
        raise AppError(
            code="not_found",
            message="Request not found",
            http_status=404,
            details={"message_key": "social.errors.notFound"},
        )
    rows = _rpc(service_client, "my_contact_requests", {"p_actor": user_id})
    for row in rows:
        if str(row["id"]) == request_id:
            return row
    raise AppError(
        code="not_found",
        message="Request not found",
        http_status=404,
        details={"message_key": "social.errors.notFound"},
    )


@router.post("/contacts/requests/{request_id}/accept", response_model=ContactRequestSent)
async def accept_contact_request(
    request_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ContactRequestSent:
    _require_flag(service_client)
    _rate_limit(current_user.id, WRITE_POLICY, service_client)
    _load_request_for_party(service_client, request_id, current_user.id)
    rows = _rpc(
        service_client,
        "respond_contact_request",
        {"p_request_id": request_id, "p_action": "accept", "p_actor": current_user.id},
    )
    if not rows:
        raise AppError(code="internal_error", message="No response", http_status=500)
    row = rows[0]
    thread_id = row.get("thread_id")
    return ContactRequestSent(
        request_id=str(row["request_id"]),
        status=str(row["status"]),
        thread_id=str(thread_id) if thread_id else None,
    )


@router.post("/contacts/requests/{request_id}/ignore", response_model=ContactRequestSent)
async def ignore_contact_request(
    request_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ContactRequestSent:
    _require_flag(service_client)
    _rate_limit(current_user.id, WRITE_POLICY, service_client)
    _load_request_for_party(service_client, request_id, current_user.id)
    rows = _rpc(
        service_client,
        "respond_contact_request",
        {"p_request_id": request_id, "p_action": "ignore", "p_actor": current_user.id},
    )
    if not rows:
        raise AppError(code="internal_error", message="No response", http_status=500)
    row = rows[0]
    return ContactRequestSent(
        request_id=str(row["request_id"]),
        status=str(row["status"]),
        thread_id=None,
    )


# --- Contacts -----------------------------------------------------------------


@router.get("/contacts", response_model=ContactList)
async def list_contacts(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ContactList:
    _require_flag(service_client)
    _rate_limit(current_user.id, READ_POLICY, service_client)
    rows = _rows(
        service_client.client.table("contacts")
        .select("user_a, user_b, created_at")
        .or_(f"user_a.eq.{current_user.id},user_b.eq.{current_user.id}")
        .order("created_at", desc=True)
        .limit(200)
        .execute()
    )
    other_ids = [
        str(r["user_b"] if str(r["user_a"]) == current_user.id else r["user_a"]) for r in rows
    ]
    profiles = _profile_map(service_client, other_ids)
    handles = _handle_map(service_client, other_ids)
    threads = _thread_map(service_client, current_user.id, other_ids)
    items = [
        ContactView(
            user_id=oid,
            handle=handles.get(oid),
            display_name=profiles.get(oid),
            thread_id=threads.get(oid),
        )
        for oid in other_ids
    ]
    return ContactList(items=items)


def _profile_map(service_client: ServiceRoleClient, user_ids: list[str]) -> dict[str, str | None]:
    if not user_ids:
        return {}
    rows = _rows(
        service_client.client.table("profiles")
        .select("id, display_name")
        .in_("id", user_ids)
        .execute()
    )
    return {str(r["id"]): r.get("display_name") for r in rows}


def _handle_map(service_client: ServiceRoleClient, user_ids: list[str]) -> dict[str, str | None]:
    if not user_ids:
        return {}
    rows = _rows(
        service_client.client.table("user_handles")
        .select("user_id, handle")
        .in_("user_id", user_ids)
        .execute()
    )
    return {str(r["user_id"]): str(r["handle"]) for r in rows}


def _ordered_pair(a: str, b: str) -> tuple[str, str]:
    ua, ub = UUID(a), UUID(b)
    return (str(min(ua, ub)), str(max(ua, ub)))


def _thread_map(
    service_client: ServiceRoleClient,
    me: str,
    others: list[str],
) -> dict[str, str]:
    out: dict[str, str] = {}
    for other in others:
        user_a, user_b = _ordered_pair(me, other)
        rows = _rows(
            service_client.client.table("chat_threads")
            .select("id")
            .eq("user_a", user_a)
            .eq("user_b", user_b)
            .limit(1)
            .execute()
        )
        if rows:
            out[other] = str(rows[0]["id"])
    return out


@router.delete("/contacts/{user_id}", status_code=204, response_model=None)
async def remove_contact(
    user_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> None:
    _require_flag(service_client)
    _rate_limit(current_user.id, WRITE_POLICY, service_client)
    if not _UUID_RE.fullmatch(user_id):
        raise AppError(
            code="not_found",
            message="Contact not found",
            http_status=404,
            details={"message_key": "social.errors.notFound"},
        )
    _rpc(
        service_client,
        "remove_contact",
        {"p_other": user_id, "p_actor": current_user.id},
    )


@router.post("/contacts/{user_id}/block", response_model=OkResponse)
async def block_contact(
    user_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> OkResponse:
    _rate_limit(current_user.id, WRITE_POLICY, service_client)
    if not _UUID_RE.fullmatch(user_id):
        raise AppError(
            code="not_found",
            message="User not found",
            http_status=404,
            details={"message_key": "social.errors.notFound"},
        )
    _require_flag(service_client)
    _rpc(
        service_client,
        "block_user",
        {"p_other": user_id, "p_actor": current_user.id},
    )
    return OkResponse()


@router.post("/contacts/{user_id}/report", response_model=ReportResponse)
async def report_contact(
    user_id: str,
    body: ReportBody,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ReportResponse:
    _require_flag(service_client)
    _rate_limit(current_user.id, WRITE_POLICY, service_client)
    if not _UUID_RE.fullmatch(user_id):
        raise AppError(
            code="not_found",
            message="User not found",
            http_status=404,
            details={"message_key": "social.errors.notFound"},
        )
    reason = body.reason if body.detail is None else f"{body.reason}: {body.detail[:500]}"
    inserted = _rows(
        service_client.client.table("flags")
        .insert(
            {
                "entity_type": "user",
                "entity_id": user_id,
                "reason": reason[:500],
                "reporter_user_id": current_user.id,
                "status": "open",
            }
        )
        .execute()
    )
    if not inserted:
        raise AppError(code="internal_error", message="Could not report", http_status=500)
    return ReportResponse(flag_id=str(inserted[0]["id"]))


# --- Phone discovery ----------------------------------------------------------


@router.get("/me/phone-discovery", response_model=PhoneDiscoveryView)
async def get_phone_discovery(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PhoneDiscoveryView:
    _require_flag(service_client)
    pepper_ok = True
    try:
        require_phone_pepper(settings)
    except AppError:
        pepper_ok = False
    row = _rows(
        service_client.client.table("phone_discovery")
        .select("enabled")
        .eq("user_id", current_user.id)
        .maybe_single()
        .execute()
    )
    enabled = bool(row and row[0].get("enabled"))
    return PhoneDiscoveryView(enabled=enabled, pepper_configured=pepper_ok)


@router.put("/me/phone-discovery", response_model=PhoneDiscoveryView)
async def put_phone_discovery(
    body: PhoneDiscoveryBody,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PhoneDiscoveryView:
    _require_flag(service_client)
    _rate_limit(current_user.id, WRITE_POLICY, service_client)
    pepper = require_phone_pepper(settings)
    existing = _rows(
        service_client.client.table("phone_discovery")
        .select("phone_hash")
        .eq("user_id", current_user.id)
        .maybe_single()
        .execute()
    )
    existing_hash = (
        str(existing[0]["phone_hash"])
        if existing and existing[0].get("phone_hash")
        else None
    )
    profile = _rows(
        service_client.client.table("profiles")
        .select("phone")
        .eq("id", current_user.id)
        .maybe_single()
        .execute()
    )
    phone = profile[0].get("phone") if profile else None
    e164 = zm_e164_from_profile_phone(str(phone) if phone else None)
    if body.enabled and not e164:
        raise AppError(
            code="validation_error",
            message="Verified phone required",
            http_status=422,
            details={"message_key": "social.errors.phoneRequired"},
        )
    storage_hash = existing_hash
    if body.enabled:
        client_hash = e164_sha256_hex(e164)  # type: ignore[arg-type]
        storage_hash = client_hash_to_storage_hash(client_hash, settings=settings)
    if not storage_hash:
        storage_hash = "0" * 64
    _ = pepper  # used inside client_hash_to_storage_hash
    try:
        service_client.client.rpc(
            "set_phone_discovery",
            {
                "p_user": current_user.id,
                "p_phone_hash": storage_hash,
                "p_enabled": body.enabled,
            },
        ).execute()
    except APIError as exc:
        raise map_social_rpc_error(exc) from exc
    return PhoneDiscoveryView(enabled=body.enabled, pepper_configured=True)


@router.post("/contacts/discover-phones", response_model=DiscoverMatches)
async def discover_phones(
    body: DiscoverPhonesBody,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DiscoverMatches:
    _require_flag(service_client)
    _rate_limit(current_user.id, DISCOVER_POLICY, service_client)
    require_phone_pepper(settings)
    storage_hashes = [client_hash_to_storage_hash(h, settings=settings) for h in body.hashes]
    merged: list[DiscoverMatch] = []
    seen_users: set[str] = set()
    for offset in range(0, len(storage_hashes), _DB_HASH_CHUNK):
        chunk = storage_hashes[offset : offset + _DB_HASH_CHUNK]
        rows = _rpc(
            service_client,
            "discover_by_phone_hashes",
            {"p_hashes": chunk, "p_actor": current_user.id},
        )
        for row in rows:
            uid = str(row["user_id"])
            if uid in seen_users:
                continue
            seen_users.add(uid)
            merged.append(
                DiscoverMatch(
                    user_id=uid,
                    handle=row.get("handle"),
                    display_name=row.get("display_name"),
                )
            )
    return DiscoverMatches(items=merged)


# --- Chats --------------------------------------------------------------------


def _require_thread_party(
    service_client: ServiceRoleClient,
    thread_id: str,
    user_id: str,
) -> dict[str, Any]:
    if not _UUID_RE.fullmatch(thread_id):
        raise AppError(
            code="not_found",
            message="Chat not found",
            http_status=404,
            details={"message_key": "social.errors.notFound"},
        )
    rows = _rows(
        service_client.client.table("chat_threads")
        .select("id, user_a, user_b, last_message_at")
        .eq("id", thread_id)
        .limit(1)
        .execute()
    )
    if not rows:
        raise AppError(
            code="not_found",
            message="Chat not found",
            http_status=404,
            details={"message_key": "social.errors.notFound"},
        )
    row = rows[0]
    if user_id not in {str(row["user_a"]), str(row["user_b"])}:
        raise AppError(
            code="not_found",
            message="Chat not found",
            http_status=404,
            details={"message_key": "social.errors.notFound"},
        )
    return row


@router.get("/chats", response_model=ChatThreadList)
async def list_chats(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ChatThreadList:
    _require_flag(service_client)
    _rate_limit(current_user.id, READ_POLICY, service_client)
    rows = _rows(
        service_client.client.table("chat_threads")
        .select("id, user_a, user_b, last_message_at")
        .or_(f"user_a.eq.{current_user.id},user_b.eq.{current_user.id}")
        .order("last_message_at", desc=True)
        .limit(100)
        .execute()
    )
    others = [
        str(r["user_b"] if str(r["user_a"]) == current_user.id else r["user_a"]) for r in rows
    ]
    profiles = _profile_map(service_client, others)
    handles = _handle_map(service_client, others)
    items = [
        ChatThreadView(
            id=str(r["id"]),
            other_user_id=str(r["user_b"] if str(r["user_a"]) == current_user.id else r["user_a"]),
            other_handle=handles.get(
                str(r["user_b"] if str(r["user_a"]) == current_user.id else r["user_a"])
            ),
            other_display_name=profiles.get(
                str(r["user_b"] if str(r["user_a"]) == current_user.id else r["user_a"])
            ),
            last_message_at=r.get("last_message_at"),
        )
        for r in rows
    ]
    return ChatThreadList(items=items)


@router.get("/chats/{thread_id}/messages", response_model=ChatMessageList)
async def list_chat_messages(
    thread_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    before: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 30,
) -> ChatMessageList:
    _require_flag(service_client)
    _rate_limit(current_user.id, READ_POLICY, service_client)
    _require_thread_party(service_client, thread_id, current_user.id)
    query = (
        service_client.client.table("chat_messages")
        .select("id, thread_id, sender, kind, body, card, created_at")
        .eq("thread_id", thread_id)
        .order("created_at", desc=True)
        .limit(limit)
    )
    if before:
        query = query.lt("created_at", before)
    rows = _rows(query.execute())
    items = [
        ChatMessageView(
            id=str(r["id"]),
            thread_id=str(r["thread_id"]),
            sender=str(r["sender"]),
            kind=str(r["kind"]),
            body=r.get("body"),
            card=r.get("card"),
            created_at=str(r["created_at"]),
        )
        for r in rows
    ]
    return ChatMessageList(items=items)


@router.post("/chats/{thread_id}/messages", response_model=ChatMessageSent)
async def send_chat_message(
    thread_id: str,
    body: ChatMessageCreate,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ChatMessageSent:
    _require_flag(service_client)
    _rate_limit(current_user.id, WRITE_POLICY, service_client)
    _require_thread_party(service_client, thread_id, current_user.id)
    rows = _rpc(
        service_client,
        "send_chat_message",
        {
            "p_thread_id": thread_id,
            "p_kind": body.kind,
            "p_body": body.body,
            "p_card": body.card,
            "p_actor": current_user.id,
        },
    )
    if not rows:
        raise AppError(code="internal_error", message="No response", http_status=500)
    row = rows[0]
    return ChatMessageSent(
        message_id=str(row["message_id"]),
        created_at=str(row["created_at"]),
    )