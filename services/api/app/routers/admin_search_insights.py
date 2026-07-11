"""M06-P06: admin-only search/ask insight reads for the merchandising dashboard.

Mounted under the audited, admin-guarded `/admin` router (see admin_base), so
every route here inherits `require_role("admin")` — non-admins get 403.
"""

from __future__ import annotations

from app.routers.admin_base import router as admin_router
from app.services.analytics.search_log import (
    DEFAULT_INSIGHT_WINDOW_DAYS,
    DEFAULT_TOP_TERMS_LIMIT,
    ask_cost_by_day,
    top_terms,
    zero_result_terms,
)
from fastapi import APIRouter, Query
from pydantic import BaseModel

search_insights_router = APIRouter(
    prefix="/search-insights",
    tags=["admin-search-insights"],
)

WindowDays = Query(default=DEFAULT_INSIGHT_WINDOW_DAYS, ge=1, le=365)
TermsLimit = Query(default=DEFAULT_TOP_TERMS_LIMIT, ge=1, le=200)


class TermCountOut(BaseModel):
    normalized_term: str
    sample_term: str
    count: int


class DailyAskCostOut(BaseModel):
    day: str
    usd_micros: int
    query_count: int


@search_insights_router.get("/top-terms", response_model=list[TermCountOut])
async def get_top_terms(
    days: int = WindowDays,
    limit: int = TermsLimit,
) -> list[TermCountOut]:
    return [
        TermCountOut(
            normalized_term=row.normalized_term,
            sample_term=row.sample_term,
            count=row.count,
        )
        for row in top_terms(days=days, limit=limit)
    ]


@search_insights_router.get("/zero-results", response_model=list[TermCountOut])
async def get_zero_result_terms(
    days: int = WindowDays,
    limit: int = TermsLimit,
) -> list[TermCountOut]:
    return [
        TermCountOut(
            normalized_term=row.normalized_term,
            sample_term=row.sample_term,
            count=row.count,
        )
        for row in zero_result_terms(days=days, limit=limit)
    ]


@search_insights_router.get("/ask-cost", response_model=list[DailyAskCostOut])
async def get_ask_cost(days: int = WindowDays) -> list[DailyAskCostOut]:
    return [
        DailyAskCostOut(
            day=row.day,
            usd_micros=row.usd_micros,
            query_count=row.query_count,
        )
        for row in ask_cost_by_day(days=days)
    ]


admin_router.include_router(search_insights_router)
