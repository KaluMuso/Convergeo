from __future__ import annotations

from typing import Annotated

from app.core.internal_token import InternalTokenMisconfigured, resolve_internal_token
from app.deps import get_supabase_client
from app.errors import AppError
from app.services.privacy.export_purge import (
    ExportPurgeResult,
    ServiceRoleClient,
    run_export_purge,
)
from fastapi import APIRouter, Depends, Request

router = APIRouter(prefix="/internal/privacy", tags=["internal-privacy"])

_INTERNAL_TOKEN_ENV = "INTERNAL_PRIVACY_TOKEN"
_DEFAULT_INTERNAL_TOKEN = "dev-internal-privacy"


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


async def require_internal_privacy_token(request: Request) -> None:
    """Guard the export-purge tick — machine-to-machine, shared internal token only."""
    expected = _expected_internal_token()
    provided = request.headers.get("X-Internal-Token")
    if not provided or provided != expected:
        raise AppError(
            code="unauthorized",
            message="Invalid or missing internal privacy token",
            http_status=401,
        )


@router.post(
    "/export-purge-tick",
    dependencies=[Depends(require_internal_privacy_token)],
)
async def export_purge_tick(
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> dict[str, int]:
    """Delete account-data-export bundles older than the retention TTL (daily n8n tick)."""
    result: ExportPurgeResult = run_export_purge(service)
    return {"scanned": result.scanned, "deleted": result.deleted}
