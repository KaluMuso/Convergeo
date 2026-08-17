"""Listing impression and PDP view recording.

Writes are deduped per (session_id, listing_id, UTC day, view_kind, surface) via
the ``listing_view_dedup`` table (or optional Upstash Redis SET NX when configured).
Aggregates land in the partitioned ``listing_analytics`` table. An optional
viewer user id is used only to suppress a vendor's own listings and is never stored.
"""

from __future__ import annotations

import logging
import re
import threading
from datetime import UTC, date, datetime
from typing import Literal
from urllib.parse import quote
from uuid import UUID

import httpx
from app.services.orders.audit import run_sql_script, sql_literal
from app.settings import Settings, get_settings

logger = logging.getLogger(__name__)

ViewKind = Literal["impression", "pdp_view"]
ListingViewSurface = Literal["home", "plp", "storefront", "pdp", "unknown"]
LISTING_VIEW_SURFACES: frozenset[str] = frozenset(
    ("home", "plp", "storefront", "pdp", "unknown")
)

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

_DEDUP_TTL_SECONDS = 86_400 * 2  # 48h — covers UTC day boundary + slack


class _DedupStore:
    def try_claim(self, key: str) -> bool:
        raise NotImplementedError


class _InMemoryDedupStore(_DedupStore):
    def __init__(self) -> None:
        self._keys: set[str] = set()
        self._lock = threading.Lock()

    def try_claim(self, key: str) -> bool:
        with self._lock:
            if key in self._keys:
                return False
            self._keys.add(key)
            return True


class _UpstashDedupStore(_DedupStore):
    def __init__(self, *, rest_url: str, rest_token: str, timeout_seconds: float = 5.0) -> None:
        self._rest_url = rest_url.rstrip("/")
        self._rest_token = rest_token
        self._timeout = timeout_seconds

    def _command(self, command: str, key: str, *args: str) -> object:
        encoded_key = quote(key, safe="")
        path = "/".join([command, encoded_key, *args])
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

    def try_claim(self, key: str) -> bool:
        # SET key 1 NX EX ttl — returns OK when claimed, null when already set.
        result = self._command("set", key, "1", "NX", "EX", str(_DEDUP_TTL_SECONDS))
        return result == "OK"


_dedup_store: _DedupStore | None = None
_dedup_lock = threading.Lock()


def _resolve_dedup_store(settings: Settings | None = None) -> _DedupStore | None:
    """Return a Redis-backed dedup store when configured; else None (Postgres only)."""
    cfg = settings or get_settings()
    if not (cfg.upstash_redis_rest_url and cfg.upstash_redis_rest_token):
        return None
    global _dedup_store
    with _dedup_lock:
        if _dedup_store is None or not isinstance(_dedup_store, _UpstashDedupStore):
            _dedup_store = _UpstashDedupStore(
                rest_url=cfg.upstash_redis_rest_url,
                rest_token=cfg.upstash_redis_rest_token,
            )
        return _dedup_store


def _valid_uuid(value: str, *, field: str) -> str:
    if not _UUID_RE.match(value):
        raise ValueError(f"Invalid UUID for {field}")
    UUID(value)
    return value


def _utc_today() -> date:
    return datetime.now(tz=UTC).date()


def _dedup_key(
    *,
    session_id: str,
    listing_id: str,
    day: date,
    view_kind: ViewKind,
    surface: ListingViewSurface,
) -> str:
    return f"lv:{day.isoformat()}:{view_kind}:{surface}:{session_id}:{listing_id}"


def _record_one(
    *,
    session_id: str,
    listing_id: str,
    day: date,
    view_kind: ViewKind,
    surface: ListingViewSurface,
    viewer_user_id: str | None,
    redis_store: _DedupStore | None,
) -> bool:
    """Record a single view. Returns True when counted (not deduped)."""
    if redis_store is not None:
        key = _dedup_key(
            session_id=session_id,
            listing_id=listing_id,
            day=day,
            view_kind=view_kind,
            surface=surface,
        )
        if not redis_store.try_claim(key):
            return False

    viewer_sql = (
        "NULL::uuid" if viewer_user_id is None else f"{sql_literal(viewer_user_id)}::uuid"
    )
    script = f"""
SELECT public.record_listing_view(
  {sql_literal(session_id)}::uuid,
  {sql_literal(listing_id)}::uuid,
  {sql_literal(day.isoformat())}::date,
  {sql_literal(view_kind)},
  {sql_literal(surface)},
  {viewer_sql}
)::text;
"""
    result = run_sql_script(script)
    if not result.ok:
        logger.debug("record_listing_view failed: %s", result.error)
        return False
    if not result.rows:
        return False
    return result.rows[0].strip() == "1"


def record_listing_views(
    *,
    session_id: str | None,
    listing_ids: list[str],
    view_kind: ViewKind,
    surface: ListingViewSurface = "unknown",
    viewer_user_id: str | None = None,
) -> int:
    """Record one or more listing views. Returns the number newly counted."""
    if not listing_ids:
        return 0
    if session_id is None:
        return 0

    session = _valid_uuid(session_id, field="session_id")
    resolved_surface: ListingViewSurface = (
        surface if surface in LISTING_VIEW_SURFACES else "unknown"
    )
    viewer: str | None = None
    if viewer_user_id is not None:
        try:
            viewer = _valid_uuid(viewer_user_id, field="viewer_user_id")
        except ValueError:
            viewer = None
    day = _utc_today()
    redis_store = _resolve_dedup_store()

    counted = 0
    seen: set[str] = set()
    for raw_id in listing_ids:
        if raw_id in seen:
            continue
        seen.add(raw_id)
        try:
            listing_id = _valid_uuid(raw_id, field="listing_id")
        except ValueError:
            continue
        if _record_one(
            session_id=session,
            listing_id=listing_id,
            day=day,
            view_kind=view_kind,
            surface=resolved_surface,
            viewer_user_id=viewer,
            redis_store=redis_store,
        ):
            counted += 1
    return counted


def clear_dedup_store_cache() -> None:
    """Test helper — reset the module-level Redis dedup store."""
    global _dedup_store
    with _dedup_lock:
        _dedup_store = None
