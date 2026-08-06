"""Public, read-only category tree (cacheable)."""

from __future__ import annotations

from typing import Annotated, Any, Protocol

from app.deps import get_supabase_client
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
