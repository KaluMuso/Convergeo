from __future__ import annotations

from app.core.internal_token import InternalTokenMisconfigured, resolve_internal_token
from app.errors import AppError
from app.services.embeddings.batch import EMBEDDING_BATCH_LIMIT, process_embedding_tick
from fastapi import APIRouter, Depends, Request

router = APIRouter(prefix="/internal/embeddings", tags=["internal-embeddings"])

_INTERNAL_TOKEN_ENV = "INTERNAL_EMBEDDINGS_TOKEN"
_DEFAULT_INTERNAL_TOKEN = "dev-internal-embeddings"


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


async def require_internal_embeddings_token(request: Request) -> None:
    """Guard cron ticks — not publicly callable without the shared internal token."""
    expected = _expected_internal_token()
    provided = request.headers.get("X-Internal-Token")
    if not provided or provided != expected:
        raise AppError(
            code="unauthorized",
            message="Invalid or missing internal embeddings token",
            http_status=401,
        )


@router.post(
    "/tick",
    dependencies=[Depends(require_internal_embeddings_token)],
)
async def embeddings_tick() -> dict[str, float | int]:
    from app.deps import get_supabase_client

    service = next(get_supabase_client())
    result = await process_embedding_tick(service, limit=EMBEDDING_BATCH_LIMIT)
    return {
        "processed": result.processed,
        "dead": result.dead,
        "cost_usd": result.cost_usd,
    }
