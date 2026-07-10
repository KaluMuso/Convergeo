from __future__ import annotations

import os
from typing import Annotated, Any

from app.deps import get_supabase_client
from app.errors import AppError
from app.services.notifications.adapter_registry import build_adapters
from app.services.notifications.dispatcher import run_dispatch_batch
from fastapi import APIRouter, Depends, Request

router = APIRouter(prefix="/internal/dispatch", tags=["internal-dispatch"])

_INTERNAL_TOKEN_ENV = "INTERNAL_DISPATCH_TOKEN"
_DEFAULT_INTERNAL_TOKEN = "dev-internal-dispatch"


def _expected_internal_token() -> str:
    return os.environ.get(_INTERNAL_TOKEN_ENV, _DEFAULT_INTERNAL_TOKEN)


async def require_internal_dispatch_token(request: Request) -> None:
    """Guard cron ticks — not publicly callable without the shared internal token."""
    expected = _expected_internal_token()
    provided = request.headers.get("X-Internal-Token")
    if not provided or provided != expected:
        raise AppError(
            code="unauthorized",
            message="Invalid or missing internal dispatch token",
            http_status=401,
        )


def _build_adapters() -> dict[str, Any]:
    return build_adapters()


@router.post(
    "/tick",
    dependencies=[Depends(require_internal_dispatch_token)],
)
async def dispatch_tick(
    supabase: Annotated[Any, Depends(get_supabase_client)],
) -> dict[str, int]:
    stats = await run_dispatch_batch(supabase, _build_adapters())
    return {
        "processed": stats.processed,
        "sent": stats.sent,
        "failed": stats.failed,
        "skipped": stats.skipped,
        "retried": stats.retried,
    }
