"""Internal points tick (n8n): earn past the return window, reverse refunds, expire.

Internal-token guarded (same shared token as the founder digest).
"""

from __future__ import annotations

from typing import Any

from app.errors import AppError
from app.routers.internal_digest import require_internal_digest_token
from app.services.points.ledger import PointsError, run_points_sweep
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/internal/points", tags=["internal-points"])


@router.post("/sweep", dependencies=[Depends(require_internal_digest_token)])
async def points_sweep() -> dict[str, Any]:
    try:
        return run_points_sweep()
    except PointsError as exc:
        raise AppError(code="points_sweep_failed", message=str(exc), http_status=503) from exc
