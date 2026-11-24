"""Vendor geocoding search (Nominatim proxy for Zambia)."""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from datetime import timedelta
from typing import Annotated, Any

import httpx
from app.core.auth import CurrentUser, require_role
from app.core.inproc_ratelimit import InProcessRateLimiter
from app.core.ratelimit import bump_rate_counter, raise_rate_limited
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/geo", tags=["geo"])

NOMINATIM_SEARCH = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "Convergeo/1.0 (support@vergeo5.com)"
RATE_SCOPE = "geo_search_vendor"
RATE_LIMIT_PER_MINUTE = 10
_CACHE_TTL_SECONDS = 86_400
_CACHE_MAX_ENTRIES = 500

_nominatim_lock = threading.Lock()
_last_nominatim_at = 0.0
_cache: OrderedDict[str, tuple[float, list[dict[str, Any]]]] = OrderedDict()
_rate_limit_fallback = InProcessRateLimiter(
    global_rate_per_sec=1.0,
    global_burst=1,
    key_rate_per_sec=RATE_LIMIT_PER_MINUTE / 60.0,
    key_burst=RATE_LIMIT_PER_MINUTE,
    max_keys=2_000,
)


class GeoSearchResult(StrictModel):
    label: str
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class _ServiceRoleClient:
    @property
    def client(self) -> Any: ...


def _rate_limit_vendor(request: Request, user_id: str, service_client: _ServiceRoleClient) -> None:
    try:
        allowed, retry_after = bump_rate_counter(
            scope=RATE_SCOPE,
            key=user_id,
            window=timedelta(minutes=1),
            limit=RATE_LIMIT_PER_MINUTE,
            client=service_client.client,
        )
    except Exception:
        logger.warning("geo_search.rate_limit_unavailable", exc_info=True)
        _throttle_nominatim()
        if not _rate_limit_fallback.allow(user_id):
            raise_rate_limited(
                retry_after=60,
                message_key="vendor.profile.location.searchRateLimited",
                message="Too many place searches",
            )
        return
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key="vendor.profile.location.searchRateLimited",
            message="Too many place searches",
        )


def _purge_expired_cache() -> None:
    now = time.monotonic()
    expired = [
        key
        for key, (cached_at, _) in _cache.items()
        if now - cached_at > _CACHE_TTL_SECONDS
    ]
    for key in expired:
        _cache.pop(key, None)


def _cached_results(normalized_q: str) -> list[dict[str, Any]] | None:
    entry = _cache.get(normalized_q)
    if entry is None:
        return None
    cached_at, rows = entry
    if time.monotonic() - cached_at > _CACHE_TTL_SECONDS:
        _cache.pop(normalized_q, None)
        return None
    _cache.move_to_end(normalized_q)
    return rows


def _store_cache(normalized_q: str, rows: list[dict[str, Any]]) -> None:
    _purge_expired_cache()
    if normalized_q in _cache:
        _cache.move_to_end(normalized_q)
    _cache[normalized_q] = (time.monotonic(), rows)
    while len(_cache) > _CACHE_MAX_ENTRIES:
        _cache.popitem(last=False)


def _throttle_nominatim() -> None:
    global _last_nominatim_at
    with _nominatim_lock:
        now = time.monotonic()
        wait = 1.0 - (now - _last_nominatim_at)
        if wait > 0:
            time.sleep(wait)
        _last_nominatim_at = time.monotonic()


def _fetch_nominatim(q: str) -> list[dict[str, Any]]:
    _throttle_nominatim()
    params = {
        "format": "jsonv2",
        "countrycodes": "zm",
        "limit": "5",
        "q": q,
    }
    headers = {"User-Agent": USER_AGENT}
    try:
        with httpx.Client(timeout=httpx.Timeout(5.0), headers=headers) as client:
            response = client.get(NOMINATIM_SEARCH, params=params)
            response.raise_for_status()
            payload = response.json()
    except Exception:
        logger.warning("geo_search.nominatim_failed", exc_info=True)
        raise AppError(
            code="geo_unavailable",
            message="Place search is temporarily unavailable",
            http_status=503,
            details={"message_key": "vendor.profile.location.searchUnavailable"},
        ) from None

    if not isinstance(payload, list):
        return []

    results: list[dict[str, Any]] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        label = row.get("display_name")
        lat = row.get("lat")
        lng = row.get("lon")
        if not isinstance(label, str) or not label.strip():
            continue
        if not isinstance(lat, (str, int, float)) or not isinstance(lng, (str, int, float)):
            continue
        lat_f = float(lat)
        lng_f = float(lng)
        results.append({"label": label.strip(), "lat": lat_f, "lng": lng_f})
    return results


@router.get("/search", response_model=list[GeoSearchResult])
def geo_search(
    request: Request,
    q: Annotated[str, Query(min_length=3, max_length=80)],
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> list[GeoSearchResult]:
    """Search places in Zambia (vendor-only). Results are cached 24 h per query."""
    _rate_limit_vendor(request, current_user.id, service_client)

    normalized = q.strip().lower()
    if len(normalized) < 3:
        raise AppError(
            code="validation_error",
            message="query too short",
            http_status=422,
            details={"message_key": "vendor.profile.location.searchTooShort"},
        )

    cached = _cached_results(normalized)
    if cached is not None:
        return [GeoSearchResult.model_validate(row) for row in cached]

    rows = _fetch_nominatim(q.strip())
    _store_cache(normalized, rows)
    return [GeoSearchResult.model_validate(row) for row in rows]