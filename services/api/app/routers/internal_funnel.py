from __future__ import annotations

import os

from app.errors import AppError
from app.services.analytics.funnel import AbandonSweepResult, sweep_abandoned
from fastapi import APIRouter, Depends, Request

router = APIRouter(prefix="/internal/funnel", tags=["internal-funnel"])

_INTERNAL_TOKEN_ENV = "INTERNAL_FUNNEL_TOKEN"
_DEFAULT_INTERNAL_TOKEN = "dev-internal-funnel"


def _expected_internal_token() -> str:
    return os.environ.get(_INTERNAL_TOKEN_ENV, _DEFAULT_INTERNAL_TOKEN)


async def require_internal_funnel_token(request: Request) -> None:
    """Guard cron ticks — not publicly callable without the shared internal token."""
    expected = _expected_internal_token()
    provided = request.headers.get("X-Internal-Token")
    if not provided or provided != expected:
        raise AppError(
            code="unauthorized",
            message="Invalid or missing internal funnel token",
            http_status=401,
        )


@router.post(
    "/abandon-tick",
    dependencies=[Depends(require_internal_funnel_token)],
)
async def funnel_abandon_tick() -> dict[str, int]:
    stats: AbandonSweepResult = sweep_abandoned()
    return {
        "scanned": stats.scanned,
        "abandoned": stats.abandoned,
        "notifications_enqueued": stats.notifications_enqueued,
    }
