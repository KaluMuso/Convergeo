from __future__ import annotations

from datetime import timedelta
from typing import Annotated, Any

from app.core.ratelimit import bump_rate_counter, get_client_ip, raise_rate_limited
from app.deps import get_supabase_client
from app.services.business.access import BusinessAccess, get_business_access
from app.services.search import SearchResponse, SuggestResponse, run_search, run_suggest
from app.services.search.nearby import (
    DEFAULT_RADIUS_KM,
    MAX_RADIUS_KM,
    NearbyResponse,
    run_nearby,
)
from app.services.search.query_builder import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    SearchKind,
)
from fastapi import APIRouter, Depends, Query, Request

router = APIRouter(prefix="/search", tags=["search"])

# Geo endpoints are cheap per call but enumerable — cap aggressively per IP.
_GEO_RATE_LIMIT_PER_MINUTE = 20


def _rate_limit_geo_read(request: Request, supabase: Any) -> None:
    ip = get_client_ip(request)
    allowed, retry_after = bump_rate_counter(
        scope="search_geo_ip",
        key=ip,
        window=timedelta(minutes=1),
        limit=_GEO_RATE_LIMIT_PER_MINUTE,
        client=supabase.client,
    )
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key="search.errors.rate_limited",
            message="Too many location-based search requests",
        )


@router.get("", response_model=SearchResponse)
async def search(
    request: Request,
    supabase: Annotated[Any, Depends(get_supabase_client)],
    access: Annotated[BusinessAccess, Depends(get_business_access)],
    q: Annotated[str, Query(min_length=1, max_length=200)],
    kind: Annotated[SearchKind | None, Query()] = None,
    category_path: Annotated[str | None, Query(max_length=200)] = None,
    price_min_ngwee: Annotated[int | None, Query(ge=0)] = None,
    price_max_ngwee: Annotated[int | None, Query(ge=0)] = None,
    page: Annotated[int, Query(ge=1)] = DEFAULT_PAGE,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    lng: Annotated[float | None, Query(ge=-180, le=180)] = None,
    include_kind_totals: Annotated[bool, Query()] = False,
) -> SearchResponse:
    if lat is not None and lng is not None:
        _rate_limit_geo_read(request, supabase)
    return await run_search(
        supabase.client,
        query=q,
        kind=kind,
        category_path=category_path,
        price_min_ngwee=price_min_ngwee,
        price_max_ngwee=price_max_ngwee,
        page=page,
        page_size=page_size,
        include_wholesale=access.eligible,
        user_id=access.user_id,
        # Only a complete lat/lng pair drives proximity ranking; a lone coord is ignored.
        user_lat=lat if lng is not None else None,
        user_lng=lng if lat is not None else None,
        include_kind_totals=include_kind_totals,
    )


@router.get("/nearby", response_model=NearbyResponse)
async def nearby(
    request: Request,
    supabase: Annotated[Any, Depends(get_supabase_client)],
    lat: Annotated[float, Query(ge=-90, le=90)],
    lng: Annotated[float, Query(ge=-180, le=180)],
    radius_km: Annotated[float, Query(gt=0, le=MAX_RADIUS_KM)] = DEFAULT_RADIUS_KM,
    open_now: Annotated[bool, Query()] = False,
    page: Annotated[int, Query(ge=1)] = DEFAULT_PAGE,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> NearbyResponse:
    _rate_limit_geo_read(request, supabase)
    return run_nearby(
        supabase.client,
        lat=lat,
        lng=lng,
        radius_km=radius_km,
        open_now=open_now,
        page=page,
        page_size=page_size,
    )


@router.get("/suggest", response_model=SuggestResponse)
async def suggest(
    supabase: Annotated[Any, Depends(get_supabase_client)],
    access: Annotated[BusinessAccess, Depends(get_business_access)],
    q: Annotated[str, Query(min_length=1, max_length=80)],
    kind: Annotated[SearchKind | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=20)] = 8,
) -> SuggestResponse:
    return run_suggest(
        supabase.client,
        query=q,
        kind=kind,
        limit=limit,
        include_wholesale=access.eligible,
    )
