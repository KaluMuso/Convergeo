"""Public, read-only category tree (cacheable)."""

from __future__ import annotations

from typing import Annotated, Any, Protocol

from app.deps import get_supabase_client
from app.routers.organiser_events import EVENT_CATEGORIES
from app.schemas.base import StrictModel
from app.services.categories.public import PublicCategory, list_public_categories
from fastapi import APIRouter, Depends, Response

router = APIRouter(tags=["categories"])

PUBLIC_CATEGORIES_CACHE_CONTROL = "public, s-maxage=3600, stale-while-revalidate=300"


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


@router.get("/categories/events", response_model=list[EventCategoryOption])
async def get_event_categories(
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> list[EventCategoryOption]:
    response = (
        service_client.client.table("event_categories")
        .select("slug, parent_slug, label_key, sort")
        .order("sort")
        .execute()
    )
    rows = response.data if isinstance(response.data, list) else []
    return [
        EventCategoryOption.model_validate(
            {key: row.get(key) for key in ("slug", "parent_slug", "label_key")}
        )
        for row in rows
        if isinstance(row, dict) and row.get("slug") in EVENT_CATEGORIES
    ]
