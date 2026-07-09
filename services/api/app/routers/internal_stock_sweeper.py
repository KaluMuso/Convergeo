from __future__ import annotations

import os

from app.errors import AppError
from app.services.stock.sweep import SweepResult, sweep_expired_reservations
from fastapi import APIRouter, Depends, Request

router = APIRouter(prefix="/internal/stock-sweeper", tags=["internal-stock-sweeper"])

_INTERNAL_TOKEN_ENV = "INTERNAL_STOCK_SWEEPER_TOKEN"
_DEFAULT_INTERNAL_TOKEN = "dev-internal-stock-sweeper"


def _expected_internal_token() -> str:
    return os.environ.get(_INTERNAL_TOKEN_ENV, _DEFAULT_INTERNAL_TOKEN)


async def require_internal_stock_sweeper_token(request: Request) -> None:
    """Guard cron ticks — not publicly callable without the shared internal token."""
    expected = _expected_internal_token()
    provided = request.headers.get("X-Internal-Token")
    if not provided or provided != expected:
        raise AppError(
            code="unauthorized",
            message="Invalid or missing internal stock sweeper token",
            http_status=401,
        )


@router.post(
    "/tick",
    dependencies=[Depends(require_internal_stock_sweeper_token)],
)
async def stock_sweeper_tick() -> dict[str, int]:
    stats: SweepResult = sweep_expired_reservations()
    return {
        "scanned": stats.scanned,
        "released": stats.released,
        "restocked_qty": stats.restocked_qty,
    }
