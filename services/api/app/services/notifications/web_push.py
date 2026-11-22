"""Web Push sender for the in-app notification center (flag ``web_push``, default OFF).

Flow (docs/plan/notification-center.md, "Web Push"):

1. A trigger on ``in_app_notifications`` queues one ``web_push_deliveries`` row per
   matching subscription, in the same transaction, only while the flag is ON.
2. n8n calls ``POST /internal/dispatch/web-push-tick`` every minute; this module
   claims due rows (compare-and-set on ``attempts``), renders the payload in the
   recipient's locale and sends it with VAPID (RFC 8292) + aes128gcm (RFC 8291)
   via ``pywebpush``/``py_vapid`` for the crypto and ``httpx`` for transport.
3. 2xx => sent · 404/410 => the dead subscription is deleted (its queue rows
   cascade) · 429/5xx/network => retry with exponential backoff (honouring
   ``Retry-After``) up to ``MAX_ATTEMPTS`` · other 4xx => failed.

Fails closed: flag off, or any of the three VAPID env vars missing, means no
sends (a warning is logged). The payload carries only what the in-app row
already shows: localized title/body (short order ref), a locale-prefixed link
path and the unseen badge count — no PINs, QR tokens, phone numbers or amounts.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from datetime import time as dtime
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, Protocol
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx
from app.core.ratelimit import bump_rate_counter

logger = logging.getLogger(__name__)

DELIVERIES_TABLE: Final = "web_push_deliveries"
SUBSCRIPTIONS_TABLE: Final = "web_push_subscriptions"
NOTIFICATIONS_TABLE: Final = "in_app_notifications"
PROFILES_TABLE: Final = "profiles"
FLAG: Final = "web_push"

#: Env var NAMES only — values are set by the founder, never committed.
VAPID_PUBLIC_ENV: Final = "WEB_PUSH_VAPID_PUBLIC_KEY"
VAPID_PRIVATE_ENV: Final = "WEB_PUSH_VAPID_PRIVATE_KEY"
VAPID_SUBJECT_ENV: Final = "WEB_PUSH_VAPID_SUBJECT"
QUIET_HOURS_ENV: Final = "WEB_PUSH_QUIET_HOURS"
QUIET_TZ_ENV: Final = "WEB_PUSH_QUIET_TZ"

DEFAULT_QUIET_HOURS: Final = "22-6"
DEFAULT_QUIET_TZ: Final = "Africa/Lusaka"
DEFAULT_BATCH_SIZE: Final = 100
MAX_ATTEMPTS: Final = 5
BACKOFF_BASE_SECONDS: Final = 60
MAX_BACKOFF_SECONDS: Final = 6 * 3600
CLAIM_LEASE_SECONDS: Final = 300
#: A queued alert older than this is pointless on a lock screen — the in-app
#: center still has it.
MAX_AGE: Final = timedelta(hours=12)
#: Push service keeps an undelivered message this long (offline phone).
TTL_SECONDS: Final = 12 * 3600
#: Per-user send cap (bump_rate_counter scope seeded by the migration).
SEND_RATE_SCOPE: Final = "web_push_send"
SEND_RATE_LIMIT: Final = 20
SEND_RATE_WINDOW: Final = timedelta(hours=1)
#: Collapses still-undelivered alerts per subscription on the push service.
TOPIC: Final = "vergeo-notifications"
SEND_TIMEOUT_SECONDS: Final = 10.0

LOCALES: Final = ("en", "bem", "nya", "fr", "zh")
DEFAULT_LOCALE: Final = "en"
MAX_TEXT: Final = 240
MAX_PARAM_LEN: Final = 40
FALLBACK_PATH: Final = {"customer": "/account/notifications", "vendor": "/notifications"}

#: Push services we will POST to. Endpoints are browser-supplied URLs, so an
#: allow-list keeps the sender from being an SSRF primitive.
ALLOWED_PUSH_HOST_SUFFIXES: Final = (
    "fcm.googleapis.com",
    "android.googleapis.com",
    "push.services.mozilla.com",
    "push.apple.com",
    "notify.windows.com",
)

_KEY_RE: Final = re.compile(
    r"^notifications\.inApp\.(customer|vendor|admin)\.([a-z][a-z0-9_]{1,62})$"
)
_LINK_RE: Final = re.compile(r"^/[A-Za-z0-9/_-]{0,200}$")
_PLACEHOLDER_RE: Final = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_SAFE_PARAM_RE: Final = re.compile(r"[^A-Za-z0-9 #._-]")
_MESSAGES_PATH: Final = Path(__file__).resolve().parents[2] / "data" / "web_push_messages.json"


class SupabaseService(Protocol):
    @property
    def client(self) -> Any: ...


# --- Config --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class VapidConfig:
    public_key: str
    private_key: str
    subject: str

    @classmethod
    def from_env(cls) -> VapidConfig | None:
        """All three env vars or nothing (fail closed)."""
        public = os.environ.get(VAPID_PUBLIC_ENV, "").strip()
        private = os.environ.get(VAPID_PRIVATE_ENV, "").strip()
        subject = os.environ.get(VAPID_SUBJECT_ENV, "").strip()
        if not (public and private and subject):
            return None
        if not subject.startswith(("mailto:", "https://")):
            return None
        return cls(public_key=public, private_key=private, subject=subject)


@dataclass(frozen=True, slots=True)
class QuietHours:
    start_hour: int
    end_hour: int
    tz: str = DEFAULT_QUIET_TZ

    @classmethod
    def from_env(cls) -> QuietHours | None:
        """``WEB_PUSH_QUIET_HOURS`` = ``"22-6"`` (default) or ``"off"``."""
        raw = os.environ.get(QUIET_HOURS_ENV, DEFAULT_QUIET_HOURS).strip().lower()
        tz = os.environ.get(QUIET_TZ_ENV, DEFAULT_QUIET_TZ).strip() or DEFAULT_QUIET_TZ
        if raw in {"", "off", "none"}:
            return None
        match = re.fullmatch(r"(\d{1,2})-(\d{1,2})", raw)
        if not match:
            logger.warning("web_push: invalid %s, using %s", QUIET_HOURS_ENV, DEFAULT_QUIET_HOURS)
            return cls(22, 6, tz)
        start, end = int(match[1]), int(match[2])
        if not (0 <= start <= 23 and 0 <= end <= 23) or start == end:
            return None
        return cls(start, end, tz)

    def _local(self, now: datetime) -> datetime:
        try:
            return now.astimezone(ZoneInfo(self.tz))
        except Exception:
            return now.astimezone(ZoneInfo(DEFAULT_QUIET_TZ))

    def active(self, now: datetime) -> bool:
        hour = self._local(now).hour
        if self.start_hour > self.end_hour:
            return hour >= self.start_hour or hour < self.end_hour
        return self.start_hour <= hour < self.end_hour

    def ends_at(self, now: datetime) -> datetime:
        local = self._local(now)
        target = datetime.combine(local.date(), dtime(self.end_hour), tzinfo=local.tzinfo)
        if target <= local:
            target += timedelta(days=1)
        return target.astimezone(UTC)


# --- Payload ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def load_messages() -> dict[str, Any]:
    data = json.loads(_MESSAGES_PATH.read_text("utf-8"))
    return data if isinstance(data, dict) else {}


def normalize_locale(value: Any) -> str:
    if isinstance(value, str):
        base = value.strip().lower().replace("_", "-").split("-", 1)[0]
        if base in LOCALES:
            return base
    return DEFAULT_LOCALE


def _lookup(messages: dict[str, Any], locale: str, *path: str) -> str | None:
    node: Any = messages.get(locale)
    for part in path:
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node if isinstance(node, str) and node else None


def _safe_param(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, str | int):
        return None
    return _SAFE_PARAM_RE.sub("", str(value))[:MAX_PARAM_LEN]


def _interpolate(template: str, params: dict[str, Any]) -> str | None:
    """Replace simple ``{name}`` placeholders; None when one cannot be filled."""
    missing = False

    def repl(match: re.Match[str]) -> str:
        nonlocal missing
        value = _safe_param(params.get(match[1]))
        if value is None:
            missing = True
            return ""
        return value

    out = _PLACEHOLDER_RE.sub(repl, template)
    if missing or "{" in out or "}" in out:
        return None
    return out


def resolve_text(
    i18n_key: str, params: dict[str, Any], locale: str, messages: dict[str, Any] | None = None
) -> tuple[str, str]:
    """(title, body) for ``i18n_key`` in ``locale`` → English → generic fallback."""
    catalog = messages if messages is not None else load_messages()
    locale = normalize_locale(locale)
    chain = [locale] if locale == DEFAULT_LOCALE else [locale, DEFAULT_LOCALE]
    title = next((t for loc in chain if (t := _lookup(catalog, loc, "title"))), "")
    body: str | None = None
    match = _KEY_RE.match(i18n_key or "")
    if match:
        for loc in chain:
            template = _lookup(catalog, loc, "inApp", match[1], match[2])
            if template and (rendered := _interpolate(template, params)) is not None:
                body = rendered
                break
    if body is None:
        body = next((f for loc in chain if (f := _lookup(catalog, loc, "inApp", "fallback"))), "")
    return title[:MAX_TEXT], body[:MAX_TEXT]


def build_payload(
    notification: dict[str, Any], *, locale: str, badge: int | None
) -> dict[str, Any]:
    """Contract: apps/customer/lib/push-payload.ts (mirrored in vendor push-sw.js)."""
    locale = normalize_locale(locale)
    audience = str(notification.get("audience") or "customer")
    raw_params = notification.get("params")
    params = raw_params if isinstance(raw_params, dict) else {}
    title, body = resolve_text(str(notification.get("i18n_key") or ""), params, locale)
    link = notification.get("link_path")
    if not isinstance(link, str) or not _LINK_RE.match(link) or link.startswith("//"):
        link = FALLBACK_PATH.get(audience, "/notifications")
    payload: dict[str, Any] = {"title": title, "body": body, "url": f"/{locale}{link}"}
    payload["badge"] = max(int(badge), 0) if isinstance(badge, int) else None
    return payload


# --- Transport ---------------------------------------------------------------------------
def is_allowed_endpoint(endpoint: str) -> bool:
    try:
        parts = urlsplit(endpoint)
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host or parts.username or parts.password:
        return False
    if parts.port not in (None, 443):
        return False
    return any(host == s or host.endswith("." + s) for s in ALLOWED_PUSH_HOST_SUFFIXES)


@dataclass(frozen=True, slots=True)
class SendOutcome:
    status_code: int | None
    retry_after: int | None = None
    error: str | None = None


def _retry_after(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return max(int(value.strip()), 0)
    except ValueError:
        return None


class WebPushSender:
    """Encrypts (aes128gcm) and POSTs one message; never raises for HTTP errors."""

    def __init__(self, vapid: VapidConfig, *, client: httpx.AsyncClient | None = None) -> None:
        from py_vapid import Vapid02  # type: ignore[import-untyped]

        self._vapid = Vapid02.from_string(private_key=vapid.private_key)
        self._public_key = vapid.public_key
        self._subject = vapid.subject
        self._client = client

    def _headers(self, endpoint: str) -> dict[str, str]:
        parts = urlsplit(endpoint)
        claims = {
            "sub": self._subject,
            "aud": f"{parts.scheme}://{parts.hostname}",
            "exp": int(time.time()) + 12 * 3600,
        }
        headers: dict[str, str] = dict(self._vapid.sign(claims))
        headers.update(
            {
                "TTL": str(TTL_SECONDS),
                "Content-Encoding": "aes128gcm",
                "Content-Type": "application/octet-stream",
                "Urgency": "normal",
                "Topic": TOPIC,
            }
        )
        return headers

    @staticmethod
    def encrypt(payload: bytes, *, p256dh: str, auth: str) -> bytes:
        from pywebpush import WebPusher  # type: ignore[import-untyped]

        pusher = WebPusher(
            {"endpoint": "https://unused.invalid", "keys": {"p256dh": p256dh, "auth": auth}}
        )
        body = pusher.encode(payload, content_encoding="aes128gcm")["body"]
        return bytes(body)

    async def send(self, *, endpoint: str, p256dh: str, auth: str, payload: bytes) -> SendOutcome:
        if not is_allowed_endpoint(endpoint):
            return SendOutcome(status_code=None, error="endpoint_not_allowed")
        try:
            body = self.encrypt(payload, p256dh=p256dh, auth=auth)
            headers = self._headers(endpoint)
        except Exception:
            logger.warning("web_push: could not encrypt/sign for a subscription")
            return SendOutcome(status_code=None, error="encrypt_failed")
        try:
            if self._client is not None:
                response = await self._client.post(endpoint, content=body, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=SEND_TIMEOUT_SECONDS) as client:
                    response = await client.post(endpoint, content=body, headers=headers)
        except httpx.HTTPError:
            return SendOutcome(status_code=None, error="network_error")
        return SendOutcome(
            status_code=response.status_code,
            retry_after=_retry_after(response.headers.get("Retry-After")),
        )


SendFn = Callable[..., Awaitable[SendOutcome]]


# --- Batch -------------------------------------------------------------------------------
@dataclass(slots=True)
class WebPushStats:
    processed: int = 0
    sent: int = 0
    retried: int = 0
    failed: int = 0
    skipped: int = 0
    gone: int = 0
    deferred: int = 0
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "processed": self.processed,
            "sent": self.sent,
            "retried": self.retried,
            "failed": self.failed,
            "skipped": self.skipped,
            "gone": self.gone,
            "deferred": self.deferred,
            "reason": self.reason,
        }


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def flag_enabled(client: Any) -> bool:
    try:
        rows = _rows(
            client.table("feature_flags").select("enabled").eq("flag", FLAG).limit(1).execute()
        )
    except Exception:
        return False
    return bool(rows and rows[0].get("enabled") is True)


def backoff_seconds(attempts: int, retry_after: int | None = None) -> int:
    delay: int = BACKOFF_BASE_SECONDS * int(2 ** max(attempts - 1, 0))
    if retry_after is not None:
        delay = max(delay, retry_after)
    return min(delay, MAX_BACKOFF_SECONDS)


class WebPushDispatcher:
    def __init__(
        self,
        service: SupabaseService,
        send: SendFn,
        *,
        quiet_hours: QuietHours | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        rate_limiter: Callable[[str], bool] | None = None,
    ) -> None:
        self._service = service
        self._send = send
        self._quiet = quiet_hours
        self._batch_size = batch_size
        self._rate_limiter = rate_limiter or self._default_rate_limiter
        self._badges: dict[tuple[str, str], int | None] = {}

    @property
    def client(self) -> Any:
        return self._service.client

    def _default_rate_limiter(self, user_id: str) -> bool:
        allowed, _retry = bump_rate_counter(
            scope=SEND_RATE_SCOPE,
            key=user_id,
            window=SEND_RATE_WINDOW,
            limit=SEND_RATE_LIMIT,
            client=self.client,
        )
        return allowed

    # -- queries
    def _due(self, now: datetime) -> list[dict[str, Any]]:
        return _rows(
            self.client.table(DELIVERIES_TABLE)
            .select("id, notification_id, subscription_id, recipient_user_id, status, attempts")
            .in_("status", ["pending", "sending"])
            .lte("next_attempt_at", now.isoformat())
            .order("next_attempt_at")
            .limit(self._batch_size)
            .execute()
        )

    def _by_id(self, table: str, columns: str, ids: list[str]) -> dict[str, dict[str, Any]]:
        if not ids:
            return {}
        rows = _rows(self.client.table(table).select(columns).in_("id", ids).execute())
        return {str(r["id"]): r for r in rows if r.get("id") is not None}

    def _locales(self, user_ids: list[str]) -> dict[str, str]:
        if not user_ids:
            return {}
        try:
            rows = _rows(
                self.client.table(PROFILES_TABLE).select("id, locale").in_("id", user_ids).execute()
            )
        except Exception:
            return {}
        return {str(r.get("id")): normalize_locale(r.get("locale")) for r in rows}

    def _badge(self, user_id: str, audience: str) -> int | None:
        key = (user_id, audience)
        if key not in self._badges:
            try:
                response = (
                    self.client.table(NOTIFICATIONS_TABLE)
                    .select("id", count="exact", head=True)
                    .eq("recipient_user_id", user_id)
                    .eq("audience", audience)
                    .is_("seen_at", "null")
                    .execute()
                )
                count = getattr(response, "count", None)
                self._badges[key] = count if isinstance(count, int) else None
            except Exception:
                self._badges[key] = None
        return self._badges[key]

    # -- writes
    def _update(self, row_id: str, values: dict[str, Any]) -> None:
        self.client.table(DELIVERIES_TABLE).update(values).eq("id", row_id).execute()

    def _claim(self, row: dict[str, Any], now: datetime) -> int | None:
        """Compare-and-set on ``attempts`` so two ticks never send the same row."""
        attempts = int(row.get("attempts") or 0)
        claimed = _rows(
            self.client.table(DELIVERIES_TABLE)
            .update(
                {
                    "status": "sending",
                    "attempts": attempts + 1,
                    "next_attempt_at": (now + timedelta(seconds=CLAIM_LEASE_SECONDS)).isoformat(),
                }
            )
            .eq("id", row["id"])
            .eq("attempts", attempts)
            .in_("status", ["pending", "sending"])
            .execute()
        )
        return attempts + 1 if claimed else None

    def _finish(
        self,
        row_id: str,
        status: str,
        *,
        code: int | None = None,
        error: str | None = None,
        now: datetime | None = None,
    ) -> None:
        values: dict[str, Any] = {"status": status, "last_status_code": code, "last_error": error}
        if status == "sent" and now is not None:
            values["sent_at"] = now.isoformat()
        self._update(row_id, values)

    def _delete_subscription(self, subscription: dict[str, Any]) -> None:
        # Scoped to this exact row (id + owner + endpoint): a re-subscribed or
        # transferred endpoint is never deleted on behalf of someone else.
        (
            self.client.table(SUBSCRIPTIONS_TABLE)
            .delete()
            .eq("id", subscription["id"])
            .eq("user_id", subscription["user_id"])
            .eq("endpoint", subscription["endpoint"])
            .execute()
        )

    # -- main
    async def run(self, *, now: datetime | None = None) -> WebPushStats:
        current = now or datetime.now(UTC)
        stats = WebPushStats()
        due = self._due(current)
        if not due:
            return stats
        if self._quiet is not None and self._quiet.active(current):
            resume = self._quiet.ends_at(current).isoformat()
            for row in due:
                if row.get("status") == "pending":
                    self._update(str(row["id"]), {"next_attempt_at": resume})
                    stats.deferred += 1
            stats.reason = "quiet_hours"
            return stats

        notifications = self._by_id(
            NOTIFICATIONS_TABLE,
            "id, recipient_user_id, audience, i18n_key, params, link_path,"
            " created_at, seen_at, read_at",
            sorted({str(r["notification_id"]) for r in due}),
        )
        subscriptions = self._by_id(
            SUBSCRIPTIONS_TABLE,
            "id, user_id, audience, endpoint, p256dh, auth_secret",
            sorted({str(r["subscription_id"]) for r in due}),
        )
        locales = self._locales(sorted({str(r["recipient_user_id"]) for r in due}))

        for row in due:
            stats.processed += 1
            await self._process(row, notifications, subscriptions, locales, current, stats)
        return stats

    async def _process(
        self,
        row: dict[str, Any],
        notifications: dict[str, dict[str, Any]],
        subscriptions: dict[str, dict[str, Any]],
        locales: dict[str, str],
        now: datetime,
        stats: WebPushStats,
    ) -> None:
        row_id = str(row["id"])
        recipient = str(row["recipient_user_id"])
        notification = notifications.get(str(row["notification_id"]))
        subscription = subscriptions.get(str(row["subscription_id"]))

        skip: str | None = None
        if notification is None or subscription is None:
            skip = "gone"
        elif (
            str(subscription.get("user_id")) != recipient
            or str(notification.get("recipient_user_id")) != recipient
            or subscription.get("audience") != notification.get("audience")
        ):
            # Endpoint changed hands after queueing: never show A's alert on B's phone.
            skip = "owner_changed"
        elif notification.get("seen_at") or notification.get("read_at"):
            skip = "already_seen"
        else:
            created = _parse_ts(notification.get("created_at"))
            if created is not None and now - created > MAX_AGE:
                skip = "stale"
        if skip is not None:
            self._finish(row_id, "skipped", error=skip)
            stats.skipped += 1
            return
        assert notification is not None and subscription is not None

        attempts = self._claim(row, now)
        if attempts is None:
            return  # another tick owns it

        try:
            allowed = self._rate_limiter(recipient)
        except Exception:
            allowed = None  # limiter unavailable: hold, do not spend an attempt
        if allowed is None:
            self._update(
                row_id,
                {
                    "status": "pending",
                    "attempts": attempts - 1,
                    "next_attempt_at": (now + timedelta(seconds=BACKOFF_BASE_SECONDS)).isoformat(),
                },
            )
            stats.deferred += 1
            return
        if not allowed:
            self._finish(row_id, "skipped", error="rate_limited")
            stats.skipped += 1
            return

        audience = str(notification.get("audience"))
        payload = build_payload(
            notification,
            locale=locales.get(recipient, DEFAULT_LOCALE),
            badge=self._badge(recipient, audience),
        )
        outcome = await self._send(
            endpoint=str(subscription["endpoint"]),
            p256dh=str(subscription["p256dh"]),
            auth=str(subscription["auth_secret"]),
            payload=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(),
        )
        code = outcome.status_code
        if code is not None and 200 <= code < 300:
            self._finish(row_id, "sent", code=code, now=now)
            stats.sent += 1
        elif code in (404, 410):
            self._delete_subscription(subscription)
            stats.gone += 1
        elif code is None and outcome.error in {"endpoint_not_allowed", "encrypt_failed"}:
            self._finish(row_id, "failed", error=outcome.error)
            stats.failed += 1
        elif code is None or code == 429 or code >= 500:
            if attempts >= MAX_ATTEMPTS:
                self._finish(
                    row_id, "failed", code=code, error=outcome.error or "retries_exhausted"
                )
                stats.failed += 1
            else:
                delay = backoff_seconds(attempts, outcome.retry_after)
                self._update(
                    row_id,
                    {
                        "status": "pending",
                        "last_status_code": code,
                        "last_error": outcome.error or "retryable",
                        "next_attempt_at": (now + timedelta(seconds=delay)).isoformat(),
                    },
                )
                stats.retried += 1
        else:
            if code in (401, 403):
                logger.warning("web_push: push service rejected VAPID auth (HTTP %s)", code)
            self._finish(row_id, "failed", code=code, error="rejected")
            stats.failed += 1


async def run_web_push_batch(
    service: SupabaseService,
    *,
    sender_factory: Callable[[VapidConfig], SendFn] | None = None,
    now: datetime | None = None,
) -> WebPushStats:
    """One sweeper tick. Fails closed on flag OFF or missing VAPID env."""
    if not flag_enabled(service.client):
        return WebPushStats(reason="flag_off")
    vapid = VapidConfig.from_env()
    if vapid is None:
        logger.warning(
            "web_push: flag is ON but %s/%s/%s are not all set; no alerts sent",
            VAPID_PUBLIC_ENV,
            VAPID_PRIVATE_ENV,
            VAPID_SUBJECT_ENV,
        )
        return WebPushStats(reason="vapid_missing")
    if sender_factory is None:
        try:
            send: SendFn = WebPushSender(vapid).send
        except Exception:
            logger.warning("web_push: %s is not a usable VAPID private key", VAPID_PRIVATE_ENV)
            return WebPushStats(reason="vapid_invalid")
    else:
        send = sender_factory(vapid)
    dispatcher = WebPushDispatcher(service, send, quiet_hours=QuietHours.from_env())
    return await dispatcher.run(now=now)


def urlsafe_b64(data: bytes) -> str:
    """Helper for tests/tools: unpadded base64url."""
    return base64.urlsafe_b64encode(data).decode().rstrip("=")
