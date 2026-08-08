"""Public discovery endpoints — home BFF, popular searches, deterministic trending."""

from __future__ import annotations

from typing import Annotated, Any

from app.core.ratelimit import bump_rate_counter, get_client_ip, raise_rate_limited
from app.core.ratelimit_policies import PUBLIC_DISCOVERY_READ
from app.deps import get_supabase_client
from app.schemas.base import StrictModel
from app.services.discovery.home import HomeFeedPayload, build_home_feed
from app.services.discovery.popular_searches import (
    DEFAULT_LIMIT as DEFAULT_POPULAR_LIMIT,
    DEFAULT_WINDOW_DAYS,
    MAX_LIMIT as MAX_POPULAR_LIMIT,
    MAX_WINDOW_DAYS,
    PopularSearchItem,
    fetch_popular_searches,
)
from app.services.discovery.trending import (
    DEFAULT_LIMIT as DEFAULT_TRENDING_LIMIT,
    MAX_LIMIT as MAX_TRENDING_LIMIT,
    TrendingListing,
    fetch_trending_listings,
)
from fastapi import APIRouter, Depends, Query, Request

router = APIRouter(prefix="/discovery", tags=["discovery"])


def _rate_limit_discovery_read(request: Request, supabase: Any) -> None:
    ip = get_client_ip(request)
    allowed, retry_after = bump_rate_counter(
        scope=PUBLIC_DISCOVERY_READ.scope,
        key=ip,
        window=PUBLIC_DISCOVERY_READ.window,
        limit=PUBLIC_DISCOVERY_READ.limit,
        client=supabase.client,
    )
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key="discovery.errors.rate_limited",
            message="Too many discovery requests",
        )


class PopularSearchesResponse(StrictModel):
    items: list[PopularSearchItem]


class TrendingResponse(StrictModel):
    items: list[TrendingListing]


class HomeFeedResponse(HomeFeedPayload):
    """Wire alias — same shape as the service payload."""


@router.get("/popular-searches", response_model=PopularSearchesResponse)
async def popular_searches(
    request: Request,
    supabase: Annotated[Any, Depends(get_supabase_client)],
    limit: Annotated[int, Query(ge=1, le=MAX_POPULAR_LIMIT)] = DEFAULT_POPULAR_LIMIT,
    days: Annotated[int, Query(ge=1, le=MAX_WINDOW_DAYS)] = DEFAULT_WINDOW_DAYS,
) -> PopularSearchesResponse:
    """Anonymized, thresholded top search terms (no rare / PII / prohibited leaks)."""
    _rate_limit_discovery_read(request, supabase)
    items = fetch_popular_searches(limit=limit, days=days)
    return PopularSearchesResponse(items=items)


@router.get("/trending", response_model=TrendingResponse)
async def trending_listings(
    request: Request,
    supabase: Annotated[Any, Depends(get_supabase_client)],
    limit: Annotated[int, Query(ge=1, le=MAX_TRENDING_LIMIT)] = DEFAULT_TRENDING_LIMIT,
) -> TrendingResponse:
    _rate_limit_discovery_read(request, supabase)
    items = fetch_trending_listings(supabase.client, limit=limit)
    return TrendingResponse(items=items)


@router.get("/home", response_model=HomeFeedResponse)
async def home_feed(
    request: Request,
    supabase: Annotated[Any, Depends(get_supabase_client)],
    department_paths: Annotated[
        str | None,
        Query(
            max_length=500,
            description="Comma-separated category paths for department rails (max 3).",
        ),
    ] = None,
    newest_limit: Annotated[int, Query(ge=1, le=24)] = 8,
    department_limit: Annotated[int, Query(ge=1, le=12)] = 4,
    services_limit: Annotated[int, Query(ge=1, le=12)] = 6,
    vendors_limit: Annotated[int, Query(ge=1, le=12)] = 6,
    trending_limit: Annotated[int, Query(ge=0, le=12)] = 8,
) -> HomeFeedResponse:
    """Homepage discovery BFF — concurrent fan-in, partial failure OK."""
    _rate_limit_discovery_read(request, supabase)
    paths = [part.strip() for part in (department_paths or "").split(",") if part.strip()]
    payload = await build_home_feed(
        supabase.client,
        department_paths=paths,
        newest_limit=newest_limit,
        department_limit=department_limit,
        services_limit=services_limit,
        vendors_limit=vendors_limit,
        trending_limit=trending_limit,
    )
    return HomeFeedResponse.model_validate(payload.model_dump())
