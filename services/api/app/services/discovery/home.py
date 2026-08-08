"""Homepage discovery BFF — concurrent fan-in with bounded timeouts.

Each rail is independent: a timeout or DB failure yields an empty section rather
than failing the whole homepage. Sync PostgREST helpers run in a threadpool via
``asyncio.to_thread`` so the event loop stays responsive.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any

from app.core.ttl_cache import get_cached_json, set_cached_json
from app.routers.catalog import CatalogListResponse, FacetCounts, PlpFilterState, list_catalog
from app.routers.directory import DirectoryFacets, DirectoryListResponse, list_directory_vendors
from app.routers.services_listings import ServiceBrowseItem, build_browse_response
from app.schemas.base import StrictModel
from app.services.discovery.trending import TrendingListing, fetch_trending_listings

logger = logging.getLogger(__name__)

# Per-section wall clock — homepage must degrade, not hang on a slow rail.
SECTION_TIMEOUT_SECONDS = 2.5
# Short server cache; customer fetch also revalidates ~60s.
HOME_CACHE_TTL_SECONDS = 30
HOME_CACHE_KEY_PREFIX = "discovery:home:v1:"

MAX_DEPARTMENT_PATHS = 3


class HomeDepartmentRail(StrictModel):
    category_path: str
    listings: CatalogListResponse


class HomeFeedPayload(StrictModel):
    newest: CatalogListResponse
    services: list[ServiceBrowseItem]
    vendors: DirectoryListResponse
    department_rails: list[HomeDepartmentRail]
    trending: list[TrendingListing]


def _empty_catalog() -> CatalogListResponse:
    return CatalogListResponse(items=[], facets=FacetCounts(), total=0, next_cursor=None)


def _empty_directory(*, page_size: int) -> DirectoryListResponse:
    return DirectoryListResponse(
        items=[],
        facets=DirectoryFacets(),
        total=0,
        page=1,
        page_size=page_size,
    )


async def _run_section[T](
    label: str,
    fn: Any,
    *,
    fallback: T,
    timeout: float = SECTION_TIMEOUT_SECONDS,
) -> T:
    """Run a sync section in a worker thread with timeout + soft failure."""
    try:
        return await asyncio.wait_for(asyncio.to_thread(fn), timeout=timeout)
    except TimeoutError:
        logger.warning("discovery_home_section_timeout", extra={"section": label})
        return fallback
    except Exception:
        logger.warning("discovery_home_section_failed", exc_info=True, extra={"section": label})
        return fallback


def _cache_key(
    *,
    paths: list[str],
    newest_limit: int,
    department_limit: int,
    services_limit: int,
    vendors_limit: int,
    trending_limit: int,
) -> str:
    raw = (
        f"{','.join(paths)}|{newest_limit}|{department_limit}|"
        f"{services_limit}|{vendors_limit}|{trending_limit}"
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"{HOME_CACHE_KEY_PREFIX}{digest}"


async def build_home_feed(
    client: Any,
    *,
    department_paths: list[str] | None = None,
    newest_limit: int = 8,
    department_limit: int = 4,
    services_limit: int = 6,
    vendors_limit: int = 6,
    trending_limit: int = 8,
    use_cache: bool = True,
) -> HomeFeedPayload:
    """Concurrent homepage aggregation.

    Query model (typical):
    - 1× newest catalog
    - 1× services browse
    - 1× directory vendors
    - N≤3 department catalog rails
    - 0–1× trending (skipped when trending_limit=0)
    All kicked off together via ``asyncio.gather`` (threadpool for sync DB).
    """
    paths = [part.strip() for part in (department_paths or []) if part.strip()][:MAX_DEPARTMENT_PATHS]
    cache_key = _cache_key(
        paths=paths,
        newest_limit=newest_limit,
        department_limit=department_limit,
        services_limit=services_limit,
        vendors_limit=vendors_limit,
        trending_limit=trending_limit,
    )
    if use_cache:
        cached = get_cached_json(cache_key)
        if isinstance(cached, dict):
            try:
                return HomeFeedPayload.model_validate(cached)
            except Exception:
                pass

    empty_catalog = _empty_catalog()
    empty_directory = _empty_directory(page_size=vendors_limit)

    newest_task = _run_section(
        "newest",
        lambda: list_catalog(
            client,
            PlpFilterState(sort="newest", limit=newest_limit),
            include_wholesale=False,
        ),
        fallback=empty_catalog,
    )
    services_task = _run_section(
        "services",
        lambda: build_browse_response(client).items[:services_limit],
        fallback=[],
    )
    vendors_task = _run_section(
        "vendors",
        lambda: list_directory_vendors(client, page_size=vendors_limit),
        fallback=empty_directory,
    )

    department_tasks = [
        _run_section(
            f"department:{path}",
            lambda path=path: list_catalog(
                client,
                PlpFilterState(category_path=path, sort="newest", limit=department_limit),
                include_wholesale=False,
            ),
            fallback=empty_catalog,
        )
        for path in paths
    ]

    if trending_limit > 0:
        trending_task = _run_section(
            "trending",
            lambda: fetch_trending_listings(client, limit=trending_limit),
            fallback=[],
        )
    else:

        async def _empty_trending() -> list[TrendingListing]:
            return []

        trending_task = _empty_trending()

    gathered = await asyncio.gather(
        newest_task,
        services_task,
        vendors_task,
        trending_task,
        *department_tasks,
    )
    newest = gathered[0]
    services = gathered[1]
    vendors = gathered[2]
    trending = gathered[3]
    department_results = list(gathered[4:])

    department_rails: list[HomeDepartmentRail] = []
    for path, rail in zip(paths, department_results, strict=False):
        if isinstance(rail, CatalogListResponse) and rail.items:
            department_rails.append(HomeDepartmentRail(category_path=path, listings=rail))

    payload = HomeFeedPayload(
        newest=newest if isinstance(newest, CatalogListResponse) else empty_catalog,
        services=list(services) if isinstance(services, list) else [],
        vendors=vendors if isinstance(vendors, DirectoryListResponse) else empty_directory,
        department_rails=department_rails,
        trending=list(trending) if isinstance(trending, list) else [],
    )

    if use_cache:
        set_cached_json(
            cache_key,
            payload.model_dump(mode="json"),
            ttl_seconds=HOME_CACHE_TTL_SECONDS,
        )
    return payload
