"""Public discovery endpoints — home BFF, popular searches, deterministic trending."""

from __future__ import annotations

from typing import Annotated, Any

from app.deps import get_supabase_client
from app.routers.catalog import CatalogListResponse, PlpFilterState, list_catalog
from app.routers.directory import DirectoryListResponse, list_directory_vendors
from app.routers.services_listings import ServiceBrowseItem, build_browse_response
from app.schemas.base import StrictModel
from app.services.analytics.search_log import top_terms
from app.services.discovery.trending import TrendingListing, fetch_trending_listings
from fastapi import APIRouter, Depends, Query

router = APIRouter(prefix="/discovery", tags=["discovery"])

DEFAULT_POPULAR_LIMIT = 8
MAX_POPULAR_LIMIT = 20
DEFAULT_TRENDING_LIMIT = 8
MAX_TRENDING_LIMIT = 24


class PopularSearchItem(StrictModel):
    term: str
    count: int


class PopularSearchesResponse(StrictModel):
    items: list[PopularSearchItem]


class HomeDepartmentRail(StrictModel):
    category_path: str
    listings: CatalogListResponse


class HomeFeedResponse(StrictModel):
    newest: CatalogListResponse
    services: list[ServiceBrowseItem]
    vendors: DirectoryListResponse
    department_rails: list[HomeDepartmentRail]
    trending: list[TrendingListing]


class TrendingResponse(StrictModel):
    items: list[TrendingListing]


@router.get("/popular-searches", response_model=PopularSearchesResponse)
async def popular_searches(
    limit: Annotated[int, Query(ge=1, le=MAX_POPULAR_LIMIT)] = DEFAULT_POPULAR_LIMIT,
    days: Annotated[int, Query(ge=1, le=90)] = 30,
) -> PopularSearchesResponse:
    """Anonymized top search terms for customer recovery surfaces (no PII)."""
    rows = top_terms(days=days, limit=limit * 2)
    items = [
        PopularSearchItem(term=row.sample_term or row.normalized_term, count=row.count)
        for row in rows
        if row.sample_term or row.normalized_term
    ][:limit]
    return PopularSearchesResponse(items=items)


@router.get("/trending", response_model=TrendingResponse)
async def trending_listings(
    supabase: Annotated[Any, Depends(get_supabase_client)],
    limit: Annotated[int, Query(ge=1, le=MAX_TRENDING_LIMIT)] = DEFAULT_TRENDING_LIMIT,
) -> TrendingResponse:
    items = fetch_trending_listings(supabase.client, limit=limit)
    return TrendingResponse(items=items)


@router.get("/home", response_model=HomeFeedResponse)
async def home_feed(
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
    """Homepage discovery BFF — one round-trip for catalogue rails."""
    client = supabase.client
    paths = [part.strip() for part in (department_paths or "").split(",") if part.strip()][:3]

    newest = list_catalog(
        client,
        PlpFilterState(sort="newest", limit=newest_limit),
        include_wholesale=False,
    )
    services_response = build_browse_response(client)
    services = services_response.items[:services_limit]
    vendors = list_directory_vendors(client, page_size=vendors_limit)

    department_rails: list[HomeDepartmentRail] = []
    for path in paths:
        rail = list_catalog(
            client,
            PlpFilterState(category_path=path, sort="newest", limit=department_limit),
            include_wholesale=False,
        )
        if rail.items:
            department_rails.append(HomeDepartmentRail(category_path=path, listings=rail))

    trending = fetch_trending_listings(client, limit=trending_limit) if trending_limit > 0 else []

    return HomeFeedResponse(
        newest=newest,
        services=services,
        vendors=vendors,
        department_rails=department_rails,
        trending=trending,
    )
