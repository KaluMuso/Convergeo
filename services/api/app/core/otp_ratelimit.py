"""Upstash Redis REST client for OTP rate limiting."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from app.settings import Settings, get_settings

logger = logging.getLogger(__name__)

OTP_CAP_PER_NUMBER = 3
OTP_WINDOW_SECONDS = 900  # 15 minutes


class OtpRedisStore(Protocol):
    def increment_with_ttl(self, key: str, *, ttl_seconds: int) -> tuple[int, int]: ...


class InMemoryOtpRedisStore:
    """Test/dev fallback when Upstash is not configured."""

    def __init__(self) -> None:
        self._counts: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def increment_with_ttl(self, key: str, *, ttl_seconds: int) -> tuple[int, int]:
        now = time.monotonic()
        with self._lock:
            count, expires_at = self._counts.get(key, (0, 0.0))
            if expires_at <= now:
                count = 0
                expires_at = now + ttl_seconds
            count += 1
            if count == 1:
                expires_at = now + ttl_seconds
            self._counts[key] = (count, expires_at)
            retry_after = max(1, int(expires_at - now))
            return count, retry_after


class UpstashRedisStore:
    """Minimal Upstash Redis REST wrapper (INCR + EXPIRE + TTL)."""

    def __init__(self, *, rest_url: str, rest_token: str, timeout_seconds: float = 5.0) -> None:
        self._rest_url = rest_url.rstrip("/")
        self._rest_token = rest_token
        self._timeout = timeout_seconds

    def _command(self, command: str, key: str, *args: str) -> Any:
        encoded_key = quote(key, safe="")
        parts = [command, encoded_key, *args]
        path = "/".join(parts)
        url = f"{self._rest_url}/{path}"
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {self._rest_token}"},
            timeout=self._timeout,
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict) or "result" not in body:
            msg = "unexpected Upstash response shape"
            raise RuntimeError(msg)
        return body["result"]

    def increment_with_ttl(self, key: str, *, ttl_seconds: int) -> tuple[int, int]:
        count_raw = self._command("incr", key)
        count = int(count_raw)
        if count == 1:
            self._command("expire", key, str(ttl_seconds))
        ttl_raw = self._command("ttl", key)
        ttl = int(ttl_raw)
        retry_after = ttl if ttl > 0 else ttl_seconds
        return count, retry_after


_store: InMemoryOtpRedisStore | None = None
_store_lock = threading.Lock()


def _resolve_store(settings: Settings | None = None) -> tuple[OtpRedisStore, bool]:
    cfg = settings or get_settings()
    if cfg.upstash_redis_rest_url and cfg.upstash_redis_rest_token:
        return (
            UpstashRedisStore(
                rest_url=cfg.upstash_redis_rest_url,
                rest_token=cfg.upstash_redis_rest_token,
            ),
            True,
        )
    global _store
    with _store_lock:
        if _store is None:
            _store = InMemoryOtpRedisStore()
        return _store, False


def clear_otp_redis_store_cache() -> None:
    global _store
    with _store_lock:
        _store = None


def otp_number_key(phone: str) -> str:
    return f"otp:number:{phone}"


def check_otp_number_rate_limit(
    *,
    phone: str,
    settings: Settings | None = None,
    store: OtpRedisStore | None = None,
) -> tuple[bool, int, int]:
    """Return (allowed, retry_after_seconds, attempt_count).

    When Upstash is configured, Redis errors fail closed (deny) to block SMS pumping.
    When only the in-memory fallback is active (dev/CI), errors fail open.
    """
    if store is not None:
        backend: OtpRedisStore = store
        upstash = False
    else:
        backend, upstash = _resolve_store(settings)
    key = otp_number_key(phone)
    try:
        count, retry_after = backend.increment_with_ttl(
            key,
            ttl_seconds=OTP_WINDOW_SECONDS,
        )
    except Exception:
        logger.warning("OTP Redis rate-limit check failed", exc_info=True)
        if upstash:
            return False, OTP_WINDOW_SECONDS, 0
        return True, 0, 1
    if count > OTP_CAP_PER_NUMBER:
        return False, retry_after, count
    return True, 0, count
