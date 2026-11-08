"""Public admin-governed home feed + ad impression/click beacon.

``GET /home/feed`` is cache-friendly: anonymous responses are identical for all
guests (``Cache-Control: public, s-maxage``) and memoised for a short TTL; a
bearer token only personalises the ``for_you`` section and switches the response
to ``private, no-store``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Any

from app.core.auth import get_current_user
from app.core.ratelimit import bump_rate_counter, get_client_ip, raise_rate_limited
from app.core.ratelimit_policies import PUBLIC_DISCOVERY_READ, TELEMETRY_VIEWS
from app.core.ttl_cache import get_cached_json, set_cached_json
from app.deps import get_supabase_client
from app.errors import AppError
from app.services.home_feed.models import AdEventBatch, AdEventResult, HomeFeedPage
from app.services.home_feed.resolver import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, build_feed_page
from app.settings import get_settings
from fastapi import APIRouter, Depends, Query, Request, Response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/home", tags=["home-feed"])

FEED_CACHE_TTL_SECONDS = 30
FEED_CACHE_PREFIX = "home:feed:v1:"
SUPPORTED_LOCALES = frozenset({"en", "bem", "nya", "fr", "zh"})


async def _optional_user_id(request: Request) -> str | None:
    authorization = request.headers.get("Authorization")
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        user = await get_current_user(request, get_settings())
    except AppError:
        return None
    return user.id


def _rate_limit(request: Request, client: Any, *, scope: str, limit: int, window: Any) -> None:
    try:
        allowed, retry_after = bump_rate_counter(
            scope=scope,
            key=get_client_ip(request),
            window=window,
            limit=limit,
            client=client,
        )
    except Exception:  # noqa: BLE001 — read/telemetry paths fail open on limiter outage.
        logger.debug("home feed rate-limit check failed (allowing)", exc_info=True)
        return
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key="home.errors.rate_limited",
            message="Too many home feed requests",
        )


@router.get("/feed", response_model=HomeFeedPage)
async def home_feed(
    request: Request,
    response: Response,
    supabase: Annotated[Any, Depends(get_supabase_client)],
    cursor: Annotated[str | None, Query(max_length=16)] = None,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    locale: Annotated[str, Query(max_length=8)] = "en",
) -> HomeFeedPage:
    _rate_limit(
        request,
        supabase.client,
        scope=PUBLIC_DISCOVERY_READ.scope,
        limit=PUBLIC_DISCOVERY_READ.limit,
        window=PUBLIC_DISCOVERY_READ.window,
    )
    safe_locale = locale if locale in SUPPORTED_LOCALES else "en"
    user_id = await _optional_user_id(request)
    cache_key = f"{FEED_CACHE_PREFIX}{safe_locale}:{page_size}:{cursor or '0'}"

    if user_id is None:
        cached = get_cached_json(cache_key)
        if isinstance(cached, dict):
            try:
                page = HomeFeedPage.model_validate(cached)
                response.headers["Cache-Control"] = (
                    f"public, s-maxage={FEED_CACHE_TTL_SECONDS}, stale-while-revalidate=60"
                )
                return page
            except Exception:
                pass

    try:
        page = build_feed_page(
            supabase.client,
            cursor=cursor,
            page_size=page_size,
            locale=safe_locale,
            user_id=user_id,
            now=datetime.now(UTC),
        )
    except ValueError as exc:
        raise AppError(
            code="validation_error", message="Invalid feed cursor", http_status=422
        ) from exc

    if user_id is None:
        set_cached_json(cache_key, page.model_dump(mode="json"), ttl_seconds=FEED_CACHE_TTL_SECONDS)
        response.headers["Cache-Control"] = (
            f"public, s-maxage={FEED_CACHE_TTL_SECONDS}, stale-while-revalidate=60"
        )
    else:
        response.headers["Cache-Control"] = "private, no-store"
    return page


@router.post("/ads/events", response_model=AdEventResult)
async def record_ad_events(
    request: Request,
    body: AdEventBatch,
    supabase: Annotated[Any, Depends(get_supabase_client)],
) -> AdEventResult:
    """Aggregate impressions/clicks per placement per day (live placements only)."""
    _rate_limit(
        request,
        supabase.client,
        scope=TELEMETRY_VIEWS.scope,
        limit=TELEMETRY_VIEWS.limit,
        window=TELEMETRY_VIEWS.window,
    )
    counts: dict[str, list[int]] = {}
    for event in body.events:
        bucket = counts.setdefault(event.placement_id, [0, 0])
        if event.kind == "impression":
            bucket[0] = min(bucket[0] + 1, 50)
        else:
            bucket[1] = min(bucket[1] + 1, 20)

    day = datetime.now(UTC).date().isoformat()
    accepted = 0
    dropped = 0
    for placement_id, (impressions, clicks) in counts.items():
        try:
            result = supabase.client.rpc(
                "record_ad_placement_events",
                {
                    "p_placement_id": placement_id,
                    "p_day": day,
                    "p_impressions": impressions,
                    "p_clicks": clicks,
                },
            ).execute()
            if getattr(result, "data", 0) == 1:
                accepted += 1
            else:
                dropped += 1
        except Exception:  # noqa: BLE001 — telemetry is fire-and-forget.
            logger.debug("ad event record failed", exc_info=True)
            dropped += 1
    return AdEventResult(accepted=accepted, dropped=dropped)
