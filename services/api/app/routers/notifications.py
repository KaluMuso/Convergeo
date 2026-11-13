"""In-app notification center API (docs/plan/notification-center.md).

Every endpoint is scoped to the caller's OWN identity: queries always filter on
``recipient_user_id = current_user.id`` (the service client is used for the
round-trip, and the table's FORCE RLS additionally limits any direct client read
to own rows). ``audience=vendor|admin`` further requires that role, so a
customer token can never page through the vendor or admin feed even of its own
user id.

Rows are written only by the database (outbox + domain triggers in migration
20261113130000) — there is deliberately no create endpoint.

Web Push subscription endpoints are gated by ``feature_flags.web_push``
(default OFF, read fresh each call, fails closed).
"""

from __future__ import annotations

import base64
import binascii
import os
import re
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Final, Literal, Protocol

from app.core.auth import CurrentUser, get_current_user
from app.core.ratelimit import bump_rate_counter, raise_rate_limited
from app.core.ratelimit_policies import POLICIES, RateLimitPolicy, route_id
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from fastapi import APIRouter, Depends, Query, Response
from pydantic import Field

router = APIRouter(tags=["notifications"])

TABLE: Final = "in_app_notifications"
PUSH_TABLE: Final = "web_push_subscriptions"
WEB_PUSH_FLAG: Final = "web_push"
#: Env var NAME only — the value is set by the founder (see the design doc).
VAPID_PUBLIC_ENV: Final = "WEB_PUSH_VAPID_PUBLIC_KEY"

DEFAULT_PAGE_SIZE: Final = 20
MAX_PAGE_SIZE: Final = 50
MAX_MARK_IDS: Final = 100

Audience = Literal["customer", "vendor", "admin"]
PushAudience = Literal["customer", "vendor"]

_COLUMNS: Final = "id, type, i18n_key, params, link_path, created_at, seen_at, read_at"
_UUID_RE: Final = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)
_TS_RE: Final = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|[+-]\d{2}:?\d{2})?$"
)

# --- Rate limits ------------------------------------------------------------------
#: Badge polling runs every 60 s while a tab is visible (≈60/h per open app);
#: 600/h leaves room for several open apps + page navigation.
READ_POLICY: Final = RateLimitPolicy(
    scope="notifications_read", limit=600, window=timedelta(hours=1)
)
WRITE_POLICY: Final = RateLimitPolicy(
    scope="notifications_write", limit=300, window=timedelta(hours=1)
)
PUSH_POLICY: Final = RateLimitPolicy(
    scope="web_push_subscribe", limit=20, window=timedelta(hours=1)
)
for _method, _path, _policy in (
    ("POST", "/me/notifications/seen", WRITE_POLICY),
    ("POST", "/me/notifications/read-all", WRITE_POLICY),
    ("POST", "/me/notifications/{notification_id}/read", WRITE_POLICY),
    ("PUT", "/me/push-subscriptions", PUSH_POLICY),
    ("POST", "/me/push-subscriptions/remove", PUSH_POLICY),
):
    POLICIES.setdefault(route_id(_method, _path), _policy)


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


# --- Schemas ------------------------------------------------------------------------
class NotificationItem(StrictModel):
    id: str
    type: str
    i18n_key: str
    params: dict[str, str | int]
    link_path: str | None
    created_at: str
    seen: bool
    read: bool


class NotificationPage(StrictModel):
    items: list[NotificationItem]
    next_cursor: str | None


class UnseenCount(StrictModel):
    unseen: int


class MarkSeenRequest(StrictModel):
    #: Empty / omitted = mark every unseen notification of this audience seen.
    ids: list[str] = Field(default_factory=list, max_length=MAX_MARK_IDS)


class MarkResult(StrictModel):
    updated: int


class PushKeys(StrictModel):
    p256dh: str = Field(min_length=16, max_length=256)
    auth: str = Field(min_length=8, max_length=64)


class PushSubscriptionRequest(StrictModel):
    audience: PushAudience
    endpoint: str = Field(min_length=12, max_length=1024, pattern=r"^https://")
    keys: PushKeys


class PushUnsubscribeRequest(StrictModel):
    endpoint: str = Field(min_length=12, max_length=1024, pattern=r"^https://")


class WebPushConfig(StrictModel):
    enabled: bool
    vapid_public_key: str | None


# --- Helpers ------------------------------------------------------------------------
def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


ADMIN_PANEL_ROLES = frozenset({"admin", "superadmin", "moderator"})


def _is_admin_panel_user(current_user: CurrentUser) -> bool:
    """Any admin-panel role: admin, superadmin, moderator or a restricted rbac_* role."""
    return bool(current_user.roles & ADMIN_PANEL_ROLES) or any(
        role.startswith("rbac_") for role in current_user.roles
    )


def _require_audience(current_user: CurrentUser, audience: str) -> None:
    """Vendor/admin feeds need the matching role; the customer feed is anyone's own."""
    if audience == "admin":
        allowed = _is_admin_panel_user(current_user)
    else:
        allowed = audience != "vendor" or audience in current_user.roles
    if not allowed:
        raise AppError(
            code="forbidden",
            message="Not allowed for this audience",
            http_status=403,
            details={"message_key": "notifications.center.errors.forbidden"},
        )


def _limit(service_client: ServiceRoleClient, user_id: str, policy: RateLimitPolicy) -> None:
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
            message_key="notifications.center.errors.rateLimited",
            message="Too many notification requests",
        )


def encode_cursor(created_at: str, row_id: str) -> str:
    raw = f"{created_at}|{row_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[str, str]:
    """Strictly parse an opaque cursor — its parts are spliced into a filter."""
    invalid = AppError(
        code="validation_error",
        message="Invalid cursor",
        http_status=422,
        details={"message_key": "notifications.center.errors.invalidCursor"},
    )
    if len(cursor) > 200:
        raise invalid
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        created_at, row_id = base64.urlsafe_b64decode(padded).decode().split("|", 1)
    except (ValueError, binascii.Error, UnicodeDecodeError):
        raise invalid from None
    if not _TS_RE.match(created_at) or not _UUID_RE.match(row_id):
        raise invalid
    return created_at, row_id


def _clean_params(value: Any) -> dict[str, str | int]:
    if not isinstance(value, dict):
        return {}
    cleaned: dict[str, str | int] = {}
    for key, item in value.items():
        if isinstance(key, str) and isinstance(item, (str, int)) and not isinstance(item, bool):
            cleaned[key] = item
    return cleaned


def _to_item(row: dict[str, Any]) -> NotificationItem:
    link = row.get("link_path")
    return NotificationItem(
        id=str(row["id"]),
        type=str(row["type"]),
        i18n_key=str(row["i18n_key"]),
        params=_clean_params(row.get("params")),
        link_path=str(link) if isinstance(link, str) else None,
        created_at=str(row["created_at"]),
        seen=row.get("seen_at") is not None,
        read=row.get("read_at") is not None,
    )


def _own(service_client: ServiceRoleClient, user_id: str, audience: str) -> Any:
    return (
        service_client.client.table(TABLE)
        .select(_COLUMNS)
        .eq("recipient_user_id", user_id)
        .eq("audience", audience)
    )


# --- Endpoints ----------------------------------------------------------------------
@router.get("/me/notifications", response_model=NotificationPage)
async def list_notifications(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    audience: Audience = "customer",
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> NotificationPage:
    """Newest first, keyset-paginated on ``(created_at, id)``."""
    _require_audience(current_user, audience)
    _limit(service_client, current_user.id, READ_POLICY)
    query = _own(service_client, current_user.id, audience)
    if cursor:
        created_at, row_id = decode_cursor(cursor)
        query = query.or_(
            f'created_at.lt."{created_at}",and(created_at.eq."{created_at}",id.lt.{row_id})'
        )
    rows = _rows(
        query.order("created_at", desc=True).order("id", desc=True).limit(limit + 1).execute()
    )
    page = rows[:limit]
    next_cursor = None
    if len(rows) > limit and page:
        last = page[-1]
        next_cursor = encode_cursor(str(last["created_at"]), str(last["id"]))
    return NotificationPage(items=[_to_item(row) for row in page], next_cursor=next_cursor)


@router.get("/me/notifications/unseen-count", response_model=UnseenCount)
async def unseen_count(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    audience: Audience = "customer",
) -> UnseenCount:
    _require_audience(current_user, audience)
    _limit(service_client, current_user.id, READ_POLICY)
    response = (
        service_client.client.table(TABLE)
        .select("id", count="exact", head=True)
        .eq("recipient_user_id", current_user.id)
        .eq("audience", audience)
        .is_("seen_at", "null")
        .execute()
    )
    count = getattr(response, "count", None)
    return UnseenCount(unseen=count if isinstance(count, int) and count > 0 else 0)


@router.post("/me/notifications/seen", response_model=MarkResult)
async def mark_seen(
    body: MarkSeenRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    audience: Audience = "customer",
) -> MarkResult:
    """Clear the badge (opening the bell). Does not mark anything read."""
    _require_audience(current_user, audience)
    _limit(service_client, current_user.id, WRITE_POLICY)
    for row_id in body.ids:
        if not _UUID_RE.match(row_id):
            raise AppError(code="validation_error", message="Invalid id", http_status=422)
    query = (
        service_client.client.table(TABLE)
        .update({"seen_at": _now_iso()})
        .eq("recipient_user_id", current_user.id)
        .eq("audience", audience)
        .is_("seen_at", "null")
    )
    if body.ids:
        query = query.in_("id", body.ids)
    return MarkResult(updated=len(_rows(query.execute())))


@router.post("/me/notifications/read-all", response_model=MarkResult)
async def mark_all_read(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    audience: Audience = "customer",
) -> MarkResult:
    _require_audience(current_user, audience)
    _limit(service_client, current_user.id, WRITE_POLICY)
    now = _now_iso()
    # Two statements so already-seen rows keep their original seen_at (the DB
    # guard would keep it anyway — this keeps the fake-free intent explicit).
    service_client.client.table(TABLE).update({"seen_at": now}).eq(
        "recipient_user_id", current_user.id
    ).eq("audience", audience).is_("seen_at", "null").execute()
    rows = _rows(
        service_client.client.table(TABLE)
        .update({"read_at": now})
        .eq("recipient_user_id", current_user.id)
        .eq("audience", audience)
        .is_("read_at", "null")
        .execute()
    )
    return MarkResult(updated=len(rows))


@router.post("/me/notifications/{notification_id}/read", response_model=MarkResult)
async def mark_read(
    notification_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> MarkResult:
    """Mark one of the caller's own notifications read (tap-through).

    Another user's id answers exactly like an unknown id (404) — no oracle.
    """
    _limit(service_client, current_user.id, WRITE_POLICY)
    not_found = AppError(code="not_found", message="Notification not found", http_status=404)
    if not _UUID_RE.match(notification_id):
        raise not_found
    owned = _rows(
        service_client.client.table(TABLE)
        .select("id, audience, read_at")
        .eq("id", notification_id)
        .eq("recipient_user_id", current_user.id)
        .limit(1)
        .execute()
    )
    if not owned:
        raise not_found
    _require_audience(current_user, str(owned[0].get("audience")))
    if owned[0].get("read_at") is not None:
        return MarkResult(updated=0)
    now = _now_iso()
    rows = _rows(
        service_client.client.table(TABLE)
        .update({"read_at": now, "seen_at": now})
        .eq("id", notification_id)
        .eq("recipient_user_id", current_user.id)
        .is_("read_at", "null")
        .execute()
    )
    return MarkResult(updated=len(rows))


# --- Web Push (flag-gated) --------------------------------------------------------------
def web_push_enabled(service_client: ServiceRoleClient) -> bool:
    """Flag read fresh every call; any failure or missing row means OFF."""
    try:
        rows = _rows(
            service_client.client.table("feature_flags")
            .select("enabled")
            .eq("flag", WEB_PUSH_FLAG)
            .limit(1)
            .execute()
        )
    except Exception:
        return False
    return bool(rows and rows[0].get("enabled") is True)


def _vapid_public_key() -> str | None:
    value = os.environ.get(VAPID_PUBLIC_ENV, "").strip()
    return value or None


def _require_web_push(service_client: ServiceRoleClient) -> None:
    if not web_push_enabled(service_client) or _vapid_public_key() is None:
        raise AppError(
            code="web_push_disabled",
            message="Web push is not enabled",
            http_status=409,
            details={"message_key": "notifications.center.push.unavailable"},
        )


@router.get("/me/web-push", response_model=WebPushConfig)
async def web_push_config(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> WebPushConfig:
    enabled = web_push_enabled(service_client) and _vapid_public_key() is not None
    return WebPushConfig(enabled=enabled, vapid_public_key=_vapid_public_key() if enabled else None)


@router.put("/me/push-subscriptions", status_code=204)
async def subscribe_push(
    body: PushSubscriptionRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> Response:
    """Store the caller's subscription. Re-subscribing a device moves it to the caller."""
    _require_web_push(service_client)
    _require_audience(current_user, body.audience)
    _limit(service_client, current_user.id, PUSH_POLICY)
    table = service_client.client.table(PUSH_TABLE)
    table.delete().eq("endpoint", body.endpoint).execute()
    row: dict[str, str] = {
        "user_id": current_user.id,
        "audience": body.audience,
        "endpoint": body.endpoint,
        "p256dh": body.keys.p256dh,
    }
    row["auth_secret"] = body.keys.auth
    service_client.client.table(PUSH_TABLE).insert(row).execute()
    return Response(status_code=204)


@router.post("/me/push-subscriptions/remove", status_code=204)
async def unsubscribe_push(
    body: PushUnsubscribeRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> Response:
    """Remove one of the caller's own subscriptions (works even with the flag off)."""
    _limit(service_client, current_user.id, PUSH_POLICY)
    service_client.client.table(PUSH_TABLE).delete().eq("user_id", current_user.id).eq(
        "endpoint", body.endpoint
    ).execute()
    return Response(status_code=204)
