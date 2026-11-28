"""Public, read-only category tree (cacheable)."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Protocol

from app.deps import get_supabase_client
from app.schemas.base import StrictModel
from app.services.categories.public import PublicCategory, list_public_categories
from app.services.categories.taxonomy import TaxonomyNode
from app.services.categories.taxonomy_public import list_public
from fastapi import APIRouter, Depends, Query, Response

router = APIRouter(tags=["categories"])

# Tagged "categories" on the customer side (next.revalidate); 5 minutes so admin publish/block
# reaches menus quickly.
PUBLIC_CATEGORIES_CACHE_CONTROL = "public, s-maxage=300, stale-while-revalidate=60"


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


@router.get("/categories", response_model=list[PublicCategory])
async def get_categories(
    response: Response,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> list[PublicCategory]:
    categories = list_public_categories(service_client.client)
    response.headers["Cache-Control"] = PUBLIC_CATEGORIES_CACHE_CONTROL
    return categories


class EventCategoryOption(StrictModel):
    slug: str
    parent_slug: str | None = None
    label_key: str
    name: str | None = None
    sort: int = 0
    image_url: str | None = None
    image_alt: str | None = None
    icon: str | None = None


class ServiceCategoryOption(StrictModel):
    slug: str
    parent_slug: str | None = None
    name: str
    sort: int = 0
    image_url: str | None = None
    image_alt: str | None = None
    icon: str | None = None


def _parent_slug(node: TaxonomyNode) -> str | None:
    return node.parent_id  # slug-keyed tables use the parent slug as parent_id


@router.get("/categories/events", response_model=list[EventCategoryOption])
async def get_event_categories(
    response: Response,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    audience: Annotated[Literal["customer", "vendor"], Query()] = "customer",
) -> list[EventCategoryOption]:
    nodes = list_public(service_client.client, "event", audience)
    response.headers["Cache-Control"] = PUBLIC_CATEGORIES_CACHE_CONTROL
    return [
        EventCategoryOption(
            slug=node.slug,
            parent_slug=_parent_slug(node),
            label_key=node.label_key or "events.categories.custom",
            name=node.name,
            sort=node.sort_order,
            image_url=node.image_url,
            image_alt=node.image_alt,
            icon=node.icon,
        )
        for node in nodes
    ]


@router.get("/categories/services", response_model=list[ServiceCategoryOption])
async def get_service_categories(
    response: Response,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    audience: Annotated[Literal["customer", "vendor"], Query()] = "customer",
) -> list[ServiceCategoryOption]:
    nodes = list_public(service_client.client, "service", audience)
    response.headers["Cache-Control"] = PUBLIC_CATEGORIES_CACHE_CONTROL
    return [
        ServiceCategoryOption(
            slug=node.slug,
            parent_slug=_parent_slug(node),
            name=node.name,
            sort=node.sort_order,
            image_url=node.image_url,
            image_alt=node.image_alt,
            icon=node.icon,
        )
        for node in nodes
    ]
