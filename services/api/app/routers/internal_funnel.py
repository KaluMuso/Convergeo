from __future__ import annotations

from app.core.internal_token import InternalTokenMisconfigured, resolve_internal_token
from app.errors import AppError
from app.services.analytics.funnel import AbandonSweepResult, sweep_abandoned
from fastapi import APIRouter, Depends, Request

router = APIRouter(prefix="/internal/funnel", tags=["internal-funnel"])

_INTERNAL_TOKEN_ENV = "INTERNAL_FUNNEL_TOKEN"
_DEFAULT_INTERNAL_TOKEN = "dev-internal-funnel"


def _expected_internal_token() -> str:
    try:
        return resolve_internal_token(
            _INTERNAL_TOKEN_ENV,
            dev_default=_DEFAULT_INTERNAL_TOKEN,
        )
    except InternalTokenMisconfigured as exc:
        raise AppError(
            code="configuration_error",
            message=str(exc),
            http_status=503,
        ) from exc


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
