from __future__ import annotations

from typing import Annotated, Any

from app.deps import get_supabase_client
from app.services.search import SearchResponse, SuggestResponse, run_search, run_suggest
from app.services.search.query_builder import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    SearchKind,
)
from fastapi import APIRouter, Depends, Query

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResponse)
async def search(
    supabase: Annotated[Any, Depends(get_supabase_client)],
    q: Annotated[str, Query(min_length=1, max_length=200)],
    kind: Annotated[SearchKind | None, Query()] = None,
    category_path: Annotated[str | None, Query(max_length=200)] = None,
    price_min_ngwee: Annotated[int | None, Query(ge=0)] = None,
    price_max_ngwee: Annotated[int | None, Query(ge=0)] = None,
    page: Annotated[int, Query(ge=1)] = DEFAULT_PAGE,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> SearchResponse:
    return await run_search(
        supabase.client,
        query=q,
        kind=kind,
        category_path=category_path,
        price_min_ngwee=price_min_ngwee,
        price_max_ngwee=price_max_ngwee,
        page=page,
        page_size=page_size,
    )


@router.get("/suggest", response_model=SuggestResponse)
async def suggest(
    supabase: Annotated[Any, Depends(get_supabase_client)],
    q: Annotated[str, Query(min_length=1, max_length=80)],
    kind: Annotated[SearchKind | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=20)] = 8,
) -> SuggestResponse:
    return run_suggest(
        supabase.client,
        query=q,
        kind=kind,
        limit=limit,
    )
