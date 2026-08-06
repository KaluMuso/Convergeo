"""Small TTL cache with Upstash Redis REST + in-memory fallback."""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from app.settings import Settings, get_settings

logger = logging.getLogger(__name__)


class TtlCacheStore(Protocol):
    def get_json(self, key: str) -> Any | None: ...

    def set_json(self, key: str, value: Any, *, ttl_seconds: int) -> None: ...


class InMemoryTtlCacheStore:
    def __init__(self) -> None:
        self._entries: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get_json(self, key: str) -> Any | None:
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at <= now:
                del self._entries[key]
                return None
            return value

    def set_json(self, key: str, value: Any, *, ttl_seconds: int) -> None:
        expires_at = time.monotonic() + ttl_seconds
        with self._lock:
            self._entries[key] = (expires_at, value)


class UpstashTtlCacheStore:
    """Minimal Upstash Redis REST wrapper for JSON GET/SETEX."""

    def __init__(self, *, rest_url: str, rest_token: str, timeout_seconds: float = 5.0) -> None:
        self._rest_url = rest_url.rstrip("/")
        self._rest_token = rest_token
        self._timeout = timeout_seconds

    def _command(self, *parts: str) -> Any:
        path = "/".join(quote(part, safe="") for part in parts)
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

    def get_json(self, key: str) -> Any | None:
        raw = self._command("get", key)
        if raw is None:
            return None
        if not isinstance(raw, str):
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("ttl_cache_invalid_json", extra={"key": key})
            return None

    def set_json(self, key: str, value: Any, *, ttl_seconds: int) -> None:
        payload = json.dumps(value, separators=(",", ":"), default=str)
        self._command("set", key, payload, "ex", str(ttl_seconds))


_store: InMemoryTtlCacheStore | None = None
_store_lock = threading.Lock()


def _resolve_store(settings: Settings | None = None) -> TtlCacheStore:
    cfg = settings or get_settings()
    if cfg.upstash_redis_rest_url and cfg.upstash_redis_rest_token:
        return UpstashTtlCacheStore(
            rest_url=cfg.upstash_redis_rest_url,
            rest_token=cfg.upstash_redis_rest_token,
        )
    global _store
    with _store_lock:
        if _store is None:
            _store = InMemoryTtlCacheStore()
        return _store


def clear_ttl_cache_store() -> None:
    global _store
    with _store_lock:
        _store = None


def get_cached_json(
    key: str,
    *,
    settings: Settings | None = None,
    store: TtlCacheStore | None = None,
) -> Any | None:
    backend = store if store is not None else _resolve_store(settings)
    try:
        return backend.get_json(key)
    except Exception:
        logger.warning("ttl_cache_get_failed", exc_info=True, extra={"key": key})
        return None


def set_cached_json(
    key: str,
    value: Any,
    *,
    ttl_seconds: int,
    settings: Settings | None = None,
    store: TtlCacheStore | None = None,
) -> None:
    backend = store if store is not None else _resolve_store(settings)
    try:
        backend.set_json(key, value, ttl_seconds=ttl_seconds)
    except Exception:
        logger.warning("ttl_cache_set_failed", exc_info=True, extra={"key": key})
