from __future__ import annotations

from app.core.internal_token import InternalTokenMisconfigured, resolve_internal_token
from app.errors import AppError
from app.services.escrow.release import ReleaseSweepResult, sweep_escrow_releases
from fastapi import APIRouter, Depends, Request

router = APIRouter(prefix="/internal/release-job", tags=["internal-release-job"])

_INTERNAL_TOKEN_ENV = "INTERNAL_RELEASE_JOB_TOKEN"
_DEFAULT_INTERNAL_TOKEN = "dev-internal-release-job"


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


async def require_internal_release_job_token(request: Request) -> None:
    """Guard cron ticks — not publicly callable without the shared internal token."""
    expected = _expected_internal_token()
    provided = request.headers.get("X-Internal-Token")
    if not provided or provided != expected:
        raise AppError(
            code="unauthorized",
            message="Invalid or missing internal release job token",
            http_status=401,
        )


@router.post(
    "/tick",
    dependencies=[Depends(require_internal_release_job_token)],
)
async def release_job_tick() -> dict[str, int]:
    from app.deps import get_supabase_client

    service = next(get_supabase_client())
    stats: ReleaseSweepResult = sweep_escrow_releases(service)
    return {
        "scanned": stats.scanned,
        "released": stats.released,
        "held": stats.held,
        "already_released": stats.already_released,
        "not_eligible": stats.not_eligible,
    }
