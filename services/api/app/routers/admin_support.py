from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal, Protocol, cast
from uuid import UUID

from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.core.auth import CurrentUser, require_role
from app.core.ratelimit import bump_rate_counter, get_client_ip, raise_rate_limited
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.admin_base import router as admin_router
from app.services.notifications.dedupe import enqueue_outbox_row
from app.services.notifications.dispatcher import resolve_channel
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, model_validator

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_MAX_QUERY_LEN = 120
_MAX_FREE_TEXT_LEN = 2000
_SUPPORT_EVENT_TYPE = "admin-support-reply"
_SUPPORT_OUTBOX_TEMPLATE = "admin-support-reply"

CANNED_TEMPLATE_KEYS = frozenset(
    {
        "order_status_update",
        "delivery_eta",
        "payment_reminder",
        "apology_delay",
        "pickup_ready",
    }
)

# English fallback bodies — mirrored by `admin.support.templates.*.body` in i18n.
CANNED_TEMPLATE_BODIES: dict[str, str] = {
    "order_status_update": (
        "Hi from Vergeo5 support — we're checking on your order "
        "and will update you shortly."
    ),
    "delivery_eta": (
        "Hi from Vergeo5 — your delivery is on the way. "
        "We'll share an ETA as soon as the courier confirms."
    ),
    "payment_reminder": (
        "Hi from Vergeo5 — your order is awaiting payment. "
        "Open the app to complete checkout when ready."
    ),
    "apology_delay": (
        "Hi from Vergeo5 — we're sorry for the delay on your order. "
        "Our team is prioritising it now."
    ),
    "pickup_ready": (
        "Hi from Vergeo5 — your order is ready for pickup. "
        "Bring your order reference when you arrive."
    ),
}

support_router = APIRouter(prefix="/support", tags=["admin-support"])


class ServiceRoleClient(Protocol):
    client: Any


class CustomerOut(BaseModel):
    id: UUID
    phone: str | None
    display_name: str | None
    locale: str


class OrderSummaryOut(BaseModel):
    id: UUID
    status: str
    vendor_display_name: str
    vendor_slug: str
    created_at: datetime


class ContextCardOut(BaseModel):
    customer: CustomerOut
    orders: list[OrderSummaryOut]
    open_orders_count: int
    latest_order_status: str | None


class LookupResponse(BaseModel):
    matches: list[ContextCardOut]


class SendRequest(BaseModel):
    customer_id: UUID
    order_id: UUID | None = None
    template_key: str | None = Field(default=None, max_length=64)
    free_text: str | None = Field(default=None, max_length=_MAX_FREE_TEXT_LEN)

    @model_validator(mode="after")
    def require_exactly_one_message(self) -> SendRequest:
        has_template = bool(self.template_key and self.template_key.strip())
        has_free_text = bool(self.free_text and self.free_text.strip())
        if has_template == has_free_text:
            raise ValueError("Provide exactly one of template_key or free_text")
        if has_template and self.template_key not in CANNED_TEMPLATE_KEYS:
            raise ValueError("Unknown template_key")
        return self


class SendResponse(BaseModel):
    customer_id: UUID
    channel: str
    template_key: str | None
    outbox_id: str | None
    deduped: bool


InteractionKind = Literal["canned", "free_text"]


class InteractionLogEntry(BaseModel):
    id: str
    kind: InteractionKind
    channel: str | None
    template_key: str | None
    message_preview: str | None
    actor: str | None
    order_id: str | None
    created_at: datetime
    source: Literal["outbox", "audit_log"]


def _table(client: ServiceRoleClient, name: str) -> Any:
    return client.client.table(name)


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    raise AppError(
        code="internal_error",
        message=f"Invalid timestamp in {value!r}",
        http_status=500,
    )


def _sanitize_query(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise AppError(
            code="validation_error",
            message="q cannot be empty",
            http_status=422,
        )
    if len(cleaned) > _MAX_QUERY_LEN:
        raise AppError(
            code="validation_error",
            message="q is too long",
            http_status=422,
            details={"max_length": _MAX_QUERY_LEN},
        )
    if any(char in cleaned for char in ("%", "_", "\\", ";", "--")):
        raise AppError(
            code="validation_error",
            message="Invalid characters in q",
            http_status=422,
        )
    return cleaned


def _load_vendor_map(client: ServiceRoleClient, vendor_ids: set[str]) -> dict[str, dict[str, Any]]:
    if not vendor_ids:
        return {}
    response = (
        _table(client, "vendors")
        .select("id, display_name, slug")
        .in_("id", sorted(vendor_ids))
        .execute()
    )
    rows = response.data or []
    return {str(row["id"]): row for row in rows}


def _profile_to_customer(row: dict[str, Any]) -> CustomerOut:
    locale_raw = row.get("locale")
    locale = locale_raw.strip() if isinstance(locale_raw, str) and locale_raw.strip() else "en"
    return CustomerOut(
        id=row["id"],
        phone=row.get("phone"),
        display_name=row.get("display_name"),
        locale=locale,
    )


def _find_profiles_by_query(client: ServiceRoleClient, query: str) -> list[dict[str, Any]]:
    if _UUID_RE.match(query):
        response = (
            _table(client, "profiles")
            .select("id, phone, display_name, locale, notif_prefs")
            .eq("id", query)
            .limit(1)
            .execute()
        )
        return list(response.data or [])

    phone_digits = re.sub(r"[\s\-()]", "", query)
    if phone_digits:
        response = (
            _table(client, "profiles")
            .select("id, phone, display_name, locale, notif_prefs")
            .ilike("phone", f"%{phone_digits}%")
            .limit(20)
            .execute()
        )
        profiles = list(response.data or [])
        if profiles:
            return profiles

    return []


def _find_customer_via_order(client: ServiceRoleClient, order_id: str) -> dict[str, Any] | None:
    order_response = (
        _table(client, "orders").select("customer_id").eq("id", order_id).maybe_single().execute()
    )
    order_row = order_response.data
    if not order_row:
        return None
    customer_id = str(order_row["customer_id"])
    profile_response = (
        _table(client, "profiles")
        .select("id, phone, display_name, locale, notif_prefs")
        .eq("id", customer_id)
        .maybe_single()
        .execute()
    )
    profile = profile_response.data
    if isinstance(profile, dict):
        return profile
    return None


def _load_orders_for_customer(
    client: ServiceRoleClient, customer_id: str
) -> list[dict[str, Any]]:
    response = (
        _table(client, "orders")
        .select("id, status, vendor_id, created_at")
        .eq("customer_id", customer_id)
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )
    return list(response.data or [])


def _build_context_card(
    client: ServiceRoleClient,
    profile: dict[str, Any],
) -> ContextCardOut:
    customer_id = str(profile["id"])
    order_rows = _load_orders_for_customer(client, customer_id)
    vendor_ids = {str(row["vendor_id"]) for row in order_rows}
    vendors = _load_vendor_map(client, vendor_ids)

    orders = [
        OrderSummaryOut(
            id=row["id"],
            status=row["status"],
            vendor_display_name=vendors.get(str(row["vendor_id"]), {}).get("display_name") or "—",
            vendor_slug=vendors.get(str(row["vendor_id"]), {}).get("slug") or "—",
            created_at=_parse_timestamp(row["created_at"]),
        )
        for row in order_rows
    ]

    open_statuses = {"placed", "confirmed", "processing", "ready", "shipped", "delivered"}
    open_orders = [row for row in order_rows if row["status"] in open_statuses]

    return ContextCardOut(
        customer=_profile_to_customer(profile),
        orders=orders,
        open_orders_count=len(open_orders),
        latest_order_status=orders[0].status if orders else None,
    )


def _lookup_support(client: ServiceRoleClient, query: str) -> list[ContextCardOut]:
    cleaned = _sanitize_query(query)
    profiles: list[dict[str, Any]] = []

    if _UUID_RE.match(cleaned):
        via_order = _find_customer_via_order(client, cleaned)
        if via_order is not None:
            profiles = [via_order]
        else:
            profile_response = (
                _table(client, "profiles")
                .select("id, phone, display_name, locale, notif_prefs")
                .eq("id", cleaned)
                .limit(1)
                .execute()
            )
            profiles = list(profile_response.data or [])
    else:
        profiles = _find_profiles_by_query(client, cleaned)

    seen: set[str] = set()
    matches: list[ContextCardOut] = []
    for profile in profiles:
        customer_id = str(profile["id"])
        if customer_id in seen:
            continue
        seen.add(customer_id)
        matches.append(_build_context_card(client, profile))
    return matches


def _load_customer_profile(client: ServiceRoleClient, customer_id: str) -> dict[str, Any]:
    response = (
        _table(client, "profiles")
        .select("id, phone, display_name, locale, notif_prefs")
        .eq("id", customer_id)
        .maybe_single()
        .execute()
    )
    row = response.data
    if not row:
        raise AppError(code="not_found", message="Customer not found", http_status=404)
    return cast(dict[str, Any], row)


def _rate_limit_support_send(
    request: Request,
    actor_id: str,
    service_client: ServiceRoleClient,
) -> None:
    ip = get_client_ip(request)
    allowed_ip, retry_ip = bump_rate_counter(
        scope="admin_support_ip",
        key=ip,
        window=timedelta(minutes=1),
        limit=60,
        client=service_client.client,
    )
    if not allowed_ip:
        raise_rate_limited(
            retry_after=retry_ip,
            message_key="admin.support.errors.rateLimited",
            message="Too many support messages",
        )

    allowed_actor, retry_actor = bump_rate_counter(
        scope="admin_support_actor",
        key=actor_id,
        window=timedelta(minutes=1),
        limit=30,
        client=service_client.client,
    )
    if not allowed_actor:
        raise_rate_limited(
            retry_after=retry_actor,
            message_key="admin.support.errors.rateLimited",
            message="Too many support messages",
        )


def _message_preview(body: str, *, max_len: int = 120) -> str:
    trimmed = body.strip()
    if len(trimmed) <= max_len:
        return trimmed
    return f"{trimmed[: max_len - 1]}…"


def _resolve_customer_channel(profile: dict[str, Any]) -> str:
    prefs_raw = profile.get("notif_prefs")
    prefs = prefs_raw if isinstance(prefs_raw, dict) else {}
    return resolve_channel("whatsapp", prefs)


@support_router.get("/lookup", response_model=LookupResponse)
async def support_lookup(
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    q: Annotated[str, Query(min_length=1, max_length=_MAX_QUERY_LEN)],
) -> LookupResponse:
    matches = _lookup_support(service_client, q)
    return LookupResponse(matches=matches)


@support_router.post("/send", response_model=SendResponse)
async def support_send(
    body: SendRequest,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> SendResponse:
    _rate_limit_support_send(request, current_user.id, service_client)

    customer_key = str(body.customer_id)
    profile = _load_customer_profile(service_client, customer_key)
    phone = profile.get("phone")
    if not isinstance(phone, str) or not phone.strip():
        raise AppError(
            code="validation_error",
            message="Customer has no phone number on file",
            http_status=422,
        )

    channel = _resolve_customer_channel(profile)
    template_key = body.template_key.strip() if body.template_key else None
    free_text = body.free_text.strip() if body.free_text else None

    if template_key:
        message_body = CANNED_TEMPLATE_BODIES[template_key]
        kind: InteractionKind = "canned"
    else:
        assert free_text is not None
        message_body = free_text
        kind = "free_text"

    payload: dict[str, Any] = {
        "customer_id": customer_key,
        "phone": phone.strip(),
        "locale": _profile_to_customer(profile).locale,
        "body": message_body,
        "template_key": template_key,
        "order_id": str(body.order_id) if body.order_id else None,
        "actor_id": current_user.id,
        "kind": kind,
    }

    row = enqueue_outbox_row(
        service_client.client,
        event_type=_SUPPORT_EVENT_TYPE,
        entity_id=customer_key,
        channel=channel,
        template=_SUPPORT_OUTBOX_TEMPLATE,
        payload=payload,
    )

    after: dict[str, Any] = {
        "channel": channel,
        "template_key": template_key,
        "order_id": payload["order_id"],
        "kind": kind,
    }
    if kind == "free_text":
        after["body"] = message_body

    audit_action = (
        "admin.support.send_free_text" if kind == "free_text" else "admin.support.send_canned"
    )
    recorder.record(
        action=audit_action,
        entity_type="customer",
        entity_id=customer_key,
        before=None,
        after=after,
    )

    return SendResponse(
        customer_id=body.customer_id,
        channel=channel,
        template_key=template_key,
        outbox_id=str(row["id"]) if row else None,
        deduped=row is None,
    )


def _audit_log_entries(
    client: ServiceRoleClient,
    customer_id: str,
) -> list[InteractionLogEntry]:
    response = (
        _table(client, "audit_log")
        .select("id, actor, action, after, at")
        .eq("entity_type", "customer")
        .eq("entity_id", customer_id)
        .order("at", desc=True)
        .limit(50)
        .execute()
    )
    entries: list[InteractionLogEntry] = []
    for row in response.data or []:
        action = str(row.get("action", ""))
        if not action.startswith("admin.support."):
            continue
        after_raw = row.get("after")
        after = after_raw if isinstance(after_raw, dict) else {}
        kind: InteractionKind = (
            "free_text" if action.endswith("send_free_text") else "canned"
        )
        body = after.get("body")
        preview = _message_preview(str(body)) if isinstance(body, str) else None
        entries.append(
            InteractionLogEntry(
                id=str(row["id"]),
                kind=kind,
                channel=str(after.get("channel")) if after.get("channel") else None,
                template_key=(
                    str(after.get("template_key")) if after.get("template_key") else None
                ),
                message_preview=preview,
                actor=str(row.get("actor")) if row.get("actor") else None,
                order_id=str(after.get("order_id")) if after.get("order_id") else None,
                created_at=_parse_timestamp(row.get("at", datetime.now(UTC))),
                source="audit_log",
            )
        )
    return entries


def _outbox_log_entries(
    client: ServiceRoleClient,
    customer_id: str,
) -> list[InteractionLogEntry]:
    response = (
        _table(client, "notification_outbox")
        .select("id, channel, template, payload, created_at, dedupe_key")
        .like("dedupe_key", f"{_SUPPORT_EVENT_TYPE}:{customer_id}:%")
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    entries: list[InteractionLogEntry] = []
    for row in response.data or []:
        payload_raw = row.get("payload")
        payload = payload_raw if isinstance(payload_raw, dict) else {}
        kind_raw = payload.get("kind")
        kind: InteractionKind = "free_text" if kind_raw == "free_text" else "canned"
        body = payload.get("body")
        preview = _message_preview(str(body)) if isinstance(body, str) else None
        entries.append(
            InteractionLogEntry(
                id=str(row["id"]),
                kind=kind,
                channel=str(row.get("channel")) if row.get("channel") else None,
                template_key=(
                    str(payload.get("template_key")) if payload.get("template_key") else None
                ),
                message_preview=preview,
                actor=str(payload.get("actor_id")) if payload.get("actor_id") else None,
                order_id=str(payload.get("order_id")) if payload.get("order_id") else None,
                created_at=_parse_timestamp(row.get("created_at", datetime.now(UTC))),
                source="outbox",
            )
        )
    return entries


@support_router.get("/log", response_model=list[InteractionLogEntry])
async def support_log(
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    customer_id: Annotated[UUID, Query()],
) -> list[InteractionLogEntry]:
    customer_key = str(customer_id)
    merged = _audit_log_entries(service_client, customer_key) + _outbox_log_entries(
        service_client, customer_key
    )
    merged.sort(key=lambda entry: entry.created_at, reverse=True)
    seen: set[str] = set()
    deduped: list[InteractionLogEntry] = []
    for entry in merged:
        dedupe_key = f"{entry.source}:{entry.id}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        deduped.append(entry)
    return deduped[:50]


admin_router.include_router(support_router)
