from __future__ import annotations

import os

from app.errors import AppError
from app.services.analytics.retention import RetentionSweepResult, sweep_analytics_retention
from fastapi import APIRouter, Depends, Request

router = APIRouter(prefix="/internal/analytics", tags=["internal-analytics"])

_INTERNAL_TOKEN_ENV = "INTERNAL_ANALYTICS_TOKEN"
_DEFAULT_INTERNAL_TOKEN = "dev-internal-analytics"


def _expected_internal_token() -> str:
    return os.environ.get(_INTERNAL_TOKEN_ENV, _DEFAULT_INTERNAL_TOKEN)


async def require_internal_analytics_token(request: Request) -> None:
    """Guard the retention tick — machine-to-machine, shared internal token only."""
    expected = _expected_internal_token()
    provided = request.headers.get("X-Internal-Token")
    if not provided or provided != expected:
        raise AppError(
            code="unauthorized",
            message="Invalid or missing internal analytics token",
            http_status=401,
        )


@router.post(
    "/retention-tick",
    dependencies=[Depends(require_internal_analytics_token)],
)
async def analytics_retention_tick() -> dict[str, int]:
    """Clear person-links on analytics rows past the retention window (daily n8n tick)."""
    result: RetentionSweepResult = sweep_analytics_retention()
    return {
        "search_query_log": result.search_query_log,
        "funnel_events": result.funnel_events,
        "analytics_events": result.analytics_events,
    }
