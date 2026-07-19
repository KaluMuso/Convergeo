from __future__ import annotations

from app.core.internal_token import InternalTokenMisconfigured, resolve_internal_token
from app.errors import AppError
from app.services.reviews.aggregate import recompute_all
from fastapi import APIRouter, Depends, Request

router = APIRouter(prefix="/internal/review-aggregate", tags=["internal-review-aggregate"])

_INTERNAL_TOKEN_ENV = "INTERNAL_REVIEW_AGGREGATE_TOKEN"
_DEFAULT_INTERNAL_TOKEN = "dev-internal-review-aggregate"


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


async def require_internal_review_aggregate_token(request: Request) -> None:
    """Guard the nightly recompute tick — not publicly callable without the shared token."""
    expected = _expected_internal_token()
    provided = request.headers.get("X-Internal-Token")
    if not provided or provided != expected:
        raise AppError(
            code="unauthorized",
            message="Invalid or missing internal review-aggregate token",
            http_status=401,
        )


@router.post(
    "/tick",
    dependencies=[Depends(require_internal_review_aggregate_token)],
)
async def review_aggregate_tick() -> dict[str, int]:
    from app.deps import get_supabase_client

    service = next(get_supabase_client())
    entities = recompute_all(service)
    return {"entities": entities}
