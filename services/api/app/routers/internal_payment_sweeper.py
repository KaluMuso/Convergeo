from __future__ import annotations

from app.core.internal_token import InternalTokenMisconfigured, resolve_internal_token
from app.errors import AppError
from app.services.payments.registry import get
from app.services.payments.state import SweepResult, sweep_stale_payments
from fastapi import APIRouter, Depends, Request

router = APIRouter(prefix="/internal/payment-sweeper", tags=["internal-payment-sweeper"])

_INTERNAL_TOKEN_ENV = "INTERNAL_PAYMENT_SWEEPER_TOKEN"
_DEFAULT_INTERNAL_TOKEN = "dev-internal-payment-sweeper"


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


async def require_internal_payment_sweeper_token(request: Request) -> None:
    """Guard cron ticks — not publicly callable without the shared internal token."""
    expected = _expected_internal_token()
    provided = request.headers.get("X-Internal-Token")
    if not provided or provided != expected:
        raise AppError(
            code="unauthorized",
            message="Invalid or missing internal payment sweeper token",
            http_status=401,
        )


@router.post(
    "/tick",
    dependencies=[Depends(require_internal_payment_sweeper_token)],
)
async def payment_sweeper_tick() -> dict[str, int]:
    from app.deps import get_supabase_client

    service = next(get_supabase_client())
    strategy = get("lenco")
    stats: SweepResult = await sweep_stale_payments(
        service,
        query_status=strategy.query_status,
    )
    return {
        "scanned": stats.scanned,
        "expired": stats.expired,
        "reconciled_success": stats.reconciled_success,
        "released": stats.released,
    }
