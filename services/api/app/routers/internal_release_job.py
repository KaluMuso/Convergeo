from __future__ import annotations

import os

from app.errors import AppError
from app.services.escrow.release import ReleaseSweepResult, sweep_escrow_releases
from fastapi import APIRouter, Depends, Request

router = APIRouter(prefix="/internal/release-job", tags=["internal-release-job"])

_INTERNAL_TOKEN_ENV = "INTERNAL_RELEASE_JOB_TOKEN"
_DEFAULT_INTERNAL_TOKEN = "dev-internal-release-job"


def _expected_internal_token() -> str:
    return os.environ.get(_INTERNAL_TOKEN_ENV, _DEFAULT_INTERNAL_TOKEN)


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
