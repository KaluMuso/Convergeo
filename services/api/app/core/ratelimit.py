from __future__ import annotations

import logging
import math
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from fastapi import Request
from limits.storage.base import Storage
from slowapi import Limiter
from supabase import Client

from app.errors import AppError
from app.supabase_client import get_supabase_service_client

logger = logging.getLogger(__name__)

OTP_SCOPES = frozenset({"otp_number", "otp_ip"})
AUTH_SCOPES = frozenset({"auth_ip", "auth_number"})

DEFAULT_OTP_CAP_PER_NUMBER_HOUR = 5
DEFAULT_OTP_CAP_PER_IP_DAY = 20
DEFAULT_OTP_COOLDOWN_BASE_SECONDS = 30
DEFAULT_OTP_COOLDOWN_MAX_SECONDS = 900
DEFAULT_AUTH_ENDPOINT_CAP_PER_IP_MINUTE = 60

_CONFIG_CACHE_TTL_SECONDS = 60.0
_config_cache: dict[str, tuple[float, int]] = {}
_config_lock = threading.Lock()

BumpResult = tuple[bool, int]
ServiceClient = Client | Any


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return cast(dict[str, Any], data)
    return None


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [cast(dict[str, Any], row) for row in data if isinstance(row, dict)]
    return []


def _row_int(row: dict[str, Any] | None, key: str, default: int = 0) -> int:
    if row is None:
        return default
    value = row.get(key, default)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        return int(value)
    return default


class RateLimitConfig:
    def __init__(
        self,
        *,
        otp_cap_per_number_hour: int,
        otp_cap_per_ip_day: int,
        otp_resend_cooldown_base_seconds: int,
        otp_resend_cooldown_max_seconds: int,
        auth_endpoint_cap_per_ip_minute: int,
    ) -> None:
        self.otp_cap_per_number_hour = otp_cap_per_number_hour
        self.otp_cap_per_ip_day = otp_cap_per_ip_day
        self.otp_resend_cooldown_base_seconds = otp_resend_cooldown_base_seconds
        self.otp_resend_cooldown_max_seconds = otp_resend_cooldown_max_seconds
        self.auth_endpoint_cap_per_ip_minute = auth_endpoint_cap_per_ip_minute


def _parse_config_int(value: Any, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _read_platform_config_int(client: ServiceClient, key: str, default: int) -> int:
    now = datetime.now(UTC).timestamp()
    with _config_lock:
        cached = _config_cache.get(key)
        if cached is not None and cached[0] > now:
            return cached[1]

    try:
        response = (
            client.table("platform_config")
            .select("value")
            .eq("key", key)
            .maybe_single()
            .execute()
        )
        raw_value = _single_row(response)
        parsed = _parse_config_int(raw_value.get("value") if raw_value else None, default)
    except Exception:
        logger.warning("Failed to read platform_config key %s; using default", key, exc_info=True)
        parsed = default

    with _config_lock:
        _config_cache[key] = (now + _CONFIG_CACHE_TTL_SECONDS, parsed)
    return parsed


def load_rate_limit_config(client: ServiceClient | None = None) -> RateLimitConfig:
    service = client or get_supabase_service_client().client
    return RateLimitConfig(
        otp_cap_per_number_hour=_read_platform_config_int(
            service, "otp_cap_per_number_hour", DEFAULT_OTP_CAP_PER_NUMBER_HOUR
        ),
        otp_cap_per_ip_day=_read_platform_config_int(
            service, "otp_cap_per_ip_day", DEFAULT_OTP_CAP_PER_IP_DAY
        ),
        otp_resend_cooldown_base_seconds=_read_platform_config_int(
            service, "otp_resend_cooldown_base_seconds", DEFAULT_OTP_COOLDOWN_BASE_SECONDS
        ),
        otp_resend_cooldown_max_seconds=_read_platform_config_int(
            service, "otp_resend_cooldown_max_seconds", DEFAULT_OTP_COOLDOWN_MAX_SECONDS
        ),
        auth_endpoint_cap_per_ip_minute=_read_platform_config_int(
            service, "auth_endpoint_cap_per_ip_minute", DEFAULT_AUTH_ENDPOINT_CAP_PER_IP_MINUTE
        ),
    )


def clear_rate_limit_config_cache() -> None:
    with _config_lock:
        _config_cache.clear()


def compute_resend_cooldown_seconds(attempt: int, config: RateLimitConfig) -> int:
    exponent = max(attempt - 1, 0)
    cooldown = config.otp_resend_cooldown_base_seconds * (2**exponent)
    return int(min(cooldown, config.otp_resend_cooldown_max_seconds))


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client is not None and request.client.host:
        return request.client.host
    return "unknown"


def auth_ip_key_func(request: Request) -> str:
    return f"auth_ip:{get_client_ip(request)}"


def _parse_storage_key(key: str) -> tuple[str, str]:
    if ":" not in key:
        return "auth_ip", key
    scope, rate_key = key.split(":", 1)
    return scope, rate_key


def _window_start_for_expiry(expiry: int) -> datetime:
    window_seconds = float(expiry)
    epoch = datetime.now(UTC).timestamp()
    aligned = math.floor(epoch / window_seconds) * window_seconds
    return datetime.fromtimestamp(aligned, tz=UTC)


def _format_interval(seconds: int) -> str:
    return f"{seconds} seconds"


def bump_rate_counter(
    *,
    scope: str,
    key: str,
    window: timedelta,
    limit: int,
    client: ServiceClient | None = None,
) -> BumpResult:
    service = client or get_supabase_service_client().client
    window_seconds = max(int(window.total_seconds()), 1)
    response = service.rpc(
        "bump_rate_counter",
        {
            "p_scope": scope,
            "p_key": key,
            "p_window": _format_interval(window_seconds),
            "p_limit": limit,
        },
    ).execute()

    rows = _rows(response)
    if not rows:
        raise RuntimeError("bump_rate_counter returned no rows")

    row = rows[0]
    allowed = bool(row.get("allowed"))
    retry_after = _row_int(row, "retry_after_seconds", 0)
    return allowed, max(retry_after, 0)


def raise_rate_limited(
    *,
    retry_after: int,
    message_key: str,
    message: str = "Too many requests",
) -> None:
    raise AppError(
        code="rate_limited",
        message=message,
        http_status=429,
        details={
            "retry_after": max(retry_after, 1),
            "message_key": message_key,
        },
    )


def check_active_cooldown(
    *,
    phone: str,
    client: ServiceClient | None = None,
) -> BumpResult:
    service = client or get_supabase_service_client().client
    now_iso = datetime.now(UTC).isoformat()
    response = (
        service.table("rate_counters")
        .select("expires_at")
        .eq("scope", "otp_number")
        .eq("key", f"{phone}:cooldown")
        .gt("expires_at", now_iso)
        .order("expires_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = _rows(response)
    if not rows:
        return True, 0

    expires_at = datetime.fromisoformat(str(rows[0]["expires_at"]).replace("Z", "+00:00"))
    retry_after = max(1, math.ceil((expires_at - datetime.now(UTC)).total_seconds()))
    return False, retry_after


def record_resend_cooldown(
    *,
    phone: str,
    attempt: int,
    config: RateLimitConfig,
    client: ServiceClient | None = None,
) -> int:
    service = client or get_supabase_service_client().client
    cooldown_seconds = compute_resend_cooldown_seconds(attempt, config)
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=cooldown_seconds)
    service.table("rate_counters").insert(
        {
            "scope": "otp_number",
            "key": f"{phone}:cooldown",
            "window_start": now.isoformat(),
            "count": attempt,
            "expires_at": expires_at.isoformat(),
        }
    ).execute()
    return cooldown_seconds


def check_and_increment_otp_quota(
    *,
    phone: str,
    ip: str,
    client: ServiceClient | None = None,
    config: RateLimitConfig | None = None,
) -> None:
    service = client or get_supabase_service_client().client
    cfg = config or load_rate_limit_config(service)

    allowed, retry_after = check_active_cooldown(phone=phone, client=service)
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key="auth.errors.otp_resend_cooldown",
            message="Please wait before requesting another code",
        )

    number_allowed, number_retry = bump_rate_counter(
        scope="otp_number",
        key=phone,
        window=timedelta(hours=1),
        limit=cfg.otp_cap_per_number_hour,
        client=service,
    )
    if not number_allowed:
        raise_rate_limited(
            retry_after=number_retry,
            message_key="auth.errors.otp_number_limit",
            message="Too many OTP requests for this number",
        )

    ip_allowed, ip_retry = bump_rate_counter(
        scope="otp_ip",
        key=ip,
        window=timedelta(days=1),
        limit=cfg.otp_cap_per_ip_day,
        client=service,
    )
    if not ip_allowed:
        raise_rate_limited(
            retry_after=ip_retry,
            message_key="auth.errors.otp_ip_limit",
            message="Too many OTP requests from this network",
        )

    record_resend_cooldown(
        phone=phone,
        attempt=_current_scope_count(
            scope="otp_number",
            key=phone,
            window=timedelta(hours=1),
            client=service,
        ),
        config=cfg,
        client=service,
    )


def _current_scope_count(
    *,
    scope: str,
    key: str,
    window: timedelta,
    client: ServiceClient,
) -> int:
    window_start = _window_start_for_expiry(int(window.total_seconds()))
    response = (
        client.table("rate_counters")
        .select("count")
        .eq("scope", scope)
        .eq("key", key)
        .eq("window_start", window_start.isoformat())
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        return 1
    return max(_row_int(row, "count", 1), 1)


def check_auth_endpoint_limit(
    *,
    request: Request,
    client: ServiceClient | None = None,
    config: RateLimitConfig | None = None,
) -> None:
    service = client or get_supabase_service_client().client
    cfg = config or load_rate_limit_config(service)
    ip = get_client_ip(request)
    allowed, retry_after = bump_rate_counter(
        scope="auth_ip",
        key=ip,
        window=timedelta(minutes=1),
        limit=cfg.auth_endpoint_cap_per_ip_minute,
        client=service,
    )
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key="auth.errors.rate_limited",
            message="Too many authentication requests",
        )


class PostgresRateLimitStorage(Storage):
    """limits.storage backend backed by public.rate_counters via bump_rate_counter."""

    STORAGE_SCHEME = ["postgres"]

    def __init__(
        self,
        uri: str | None = None,
        wrap_exceptions: bool = False,
        client_factory: Callable[[], ServiceClient] | None = None,
        **_: str | float | bool,
    ) -> None:
        super().__init__(uri, wrap_exceptions=wrap_exceptions)
        self._client_factory = client_factory or (lambda: get_supabase_service_client().client)
        self._expiry_by_key: dict[str, int] = {}

    @property
    def base_exceptions(self) -> tuple[type[Exception], ...]:
        return (Exception,)

    def _client(self) -> ServiceClient:
        return self._client_factory()

    def incr(self, key: str, expiry: int, amount: int = 1) -> int:
        scope, rate_key = _parse_storage_key(key)
        window_seconds = max(int(expiry), 1)
        self._expiry_by_key[key] = window_seconds
        for _ in range(amount):
            bump_rate_counter(
                scope=scope,
                key=rate_key,
                window=timedelta(seconds=window_seconds),
                limit=999_999_999,
                client=self._client(),
            )
        return self.get(key)

    def get(self, key: str) -> int:
        scope, rate_key = _parse_storage_key(key)
        window_seconds = self._expiry_by_key.get(key, 60)
        window_start = _window_start_for_expiry(window_seconds)
        response = (
            self._client()
            .table("rate_counters")
            .select("count")
            .eq("scope", scope)
            .eq("key", rate_key)
            .eq("window_start", window_start.isoformat())
            .maybe_single()
            .execute()
        )
        row = _single_row(response)
        if row is None:
            return 0
        return _row_int(row, "count", 0)

    def get_expiry(self, key: str) -> int:
        return self._expiry_by_key.get(key, 60)

    def check(self) -> bool:
        try:
            self._client().table("rate_counters").select("id").limit(1).execute()
            return True
        except Exception:
            logger.warning("Postgres rate-limit storage health check failed", exc_info=True)
            return False

    def reset(self) -> int | None:
        return None

    def clear(self, key: str) -> None:
        scope, rate_key = _parse_storage_key(key)
        window_seconds = self._expiry_by_key.get(key, 60)
        window_start = _window_start_for_expiry(window_seconds)
        (
            self._client()
            .table("rate_counters")
            .delete()
            .eq("scope", scope)
            .eq("key", rate_key)
            .eq("window_start", window_start.isoformat())
            .execute()
        )


limiter = Limiter(
    key_func=auth_ip_key_func,
    storage_uri="postgres://",
    default_limits=[],
    enabled=True,
)
