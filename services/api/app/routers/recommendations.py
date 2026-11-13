"""Public recommendation rails for PDP, service detail and event detail pages."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from app.core.ratelimit import bump_rate_counter, get_client_ip, raise_rate_limited
from app.core.ratelimit_policies import PUBLIC_DISCOVERY_READ
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.catalog import CatalogListingItem
from app.routers.events_public import (
    EventBrowseItem,
    EventOrganiserResponse,
    _fetch_event_by_slug,
)
from app.routers.events_public import build_browse_response as events_browse
from app.routers.services_listings import ServiceBrowseItem, resolve_service_id
from app.routers.services_listings import build_browse_response as services_browse
from app.services.discovery.recommendations import (
    recommend_events,
    recommend_for_product,
    recommend_services,
)
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

router = APIRouter(tags=["recommendations"])

MAX_LIMIT = 24


class ProductRecommendations(BaseModel):
    scope: Literal["store", "category"]
    items: list[CatalogListingItem]


class ServiceRecommendations(BaseModel):
    scope: Literal["provider", "category"]
    items: list[ServiceBrowseItem]


class EventRecommendations(BaseModel):
    scope: Literal["organiser", "category"]
    items: list[EventBrowseItem]


def _rate_limit(request: Request, client: Any) -> None:
    try:
        allowed, retry_after = bump_rate_counter(
            scope=PUBLIC_DISCOVERY_READ.scope,
            key=get_client_ip(request),
            window=PUBLIC_DISCOVERY_READ.window,
            limit=PUBLIC_DISCOVERY_READ.limit,
            client=client,
        )
    except Exception:  # noqa: BLE001 — read path fails open on limiter outage.
        return
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key="discovery.errors.rate_limited",
            message="Too many discovery requests",
        )


def _not_found(kind: str) -> AppError:
    return AppError(code="not_found", message=f"{kind} not found", http_status=404)


@router.get("/products/{slug}/recommendations", response_model=ProductRecommendations)
def product_recommendations(
    slug: str,
    request: Request,
    supabase: Annotated[Any, Depends(get_supabase_client)],
    scope: Annotated[Literal["store", "category"], Query()] = "category",
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 8,
) -> ProductRecommendations:
    """``store`` = more from the same vendor(s); ``category`` = similar from others."""
    _rate_limit(request, supabase.client)
    items = recommend_for_product(supabase.client, slug, scope=scope, limit=limit)
    if items is None:
        raise _not_found("Product")
    return ProductRecommendations(scope=scope, items=items)


@router.get("/services/{service_id}/recommendations", response_model=ServiceRecommendations)
def service_recommendations(
    service_id: str,
    request: Request,
    supabase: Annotated[Any, Depends(get_supabase_client)],
    scope: Annotated[Literal["provider", "category"], Query()] = "category",
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 8,
) -> ServiceRecommendations:
    _rate_limit(request, supabase.client)
    resolved = resolve_service_id(service_id)
    items = recommend_services(
        services_browse(supabase.client).items, resolved, scope=scope, limit=limit
    )
    if items is None:
        raise _not_found("Service")
    return ServiceRecommendations(scope=scope, items=items)


@router.get("/events/{slug}/recommendations", response_model=EventRecommendations)
def event_recommendations(
    slug: str,
    request: Request,
    supabase: Annotated[Any, Depends(get_supabase_client)],
    scope: Annotated[Literal["organiser", "category"], Query()] = "category",
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 8,
) -> EventRecommendations:
    _rate_limit(request, supabase.client)
    raw = _fetch_event_by_slug(supabase.client, slug)
    if raw is None or str(raw.get("visibility") or "public") == "private":
        raise _not_found("Event")
    vendor_raw = raw.get("vendors")
    vendor: dict[str, Any] = vendor_raw if isinstance(vendor_raw, dict) else {}
    current = EventBrowseItem(
        id=str(raw["id"]),
        slug=slug,
        title=str(raw.get("title") or ""),
        category=raw.get("category_slug"),
        organiser=EventOrganiserResponse(
            id=str(raw.get("organiser_vendor_id") or vendor.get("id") or ""),
            slug=str(vendor.get("slug") or ""),
            display_name=str(vendor.get("display_name") or ""),
        ),
    )
    items = recommend_events(
        events_browse(supabase.client).items, slug, scope=scope, limit=limit, current=current
    )
    return EventRecommendations(scope=scope, items=items or [])
