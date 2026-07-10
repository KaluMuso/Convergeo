from __future__ import annotations

import os

from app.errors import AppError
from app.services.payments.reconcile import (
    DailyReportResult,
    PollResult,
    poll_non_terminal_payments,
    run_daily_reconciliation_report,
)
from app.services.payments.registry import get
from fastapi import APIRouter, Depends, Request

router = APIRouter(prefix="/internal/reconciliation", tags=["internal-reconciliation"])

_INTERNAL_TOKEN_ENV = "INTERNAL_RECONCILIATION_TOKEN"
_DEFAULT_INTERNAL_TOKEN = "dev-internal-reconciliation"


def _expected_internal_token() -> str:
    return os.environ.get(_INTERNAL_TOKEN_ENV, _DEFAULT_INTERNAL_TOKEN)


async def require_internal_reconciliation_token(request: Request) -> None:
    """Guard cron ticks — not publicly callable without the shared internal token."""
    expected = _expected_internal_token()
    provided = request.headers.get("X-Internal-Token")
    if not provided or provided != expected:
        raise AppError(
            code="unauthorized",
            message="Invalid or missing internal reconciliation token",
            http_status=401,
        )


@router.post(
    "/poll-tick",
    dependencies=[Depends(require_internal_reconciliation_token)],
)
async def reconciliation_poll_tick() -> dict[str, int]:
    """30-min poller: re-query non-terminal payments and close webhook gaps."""
    from app.deps import get_supabase_client

    service = next(get_supabase_client())
    strategy = get("lenco")
    stats: PollResult = await poll_non_terminal_payments(
        service,
        query_status=strategy.query_status,
    )
    return {
        "scanned": stats.scanned,
        "updated": stats.updated,
        "unchanged": stats.unchanged,
        "errors": stats.errors,
    }


@router.post(
    "/daily-report",
    dependencies=[Depends(require_internal_reconciliation_token)],
)
async def reconciliation_daily_report() -> dict[str, object]:
    """Daily reconciliation: Lenco balance/transactions vs ledger (ngwee-exact)."""
    from app.deps import get_supabase_client

    service = next(get_supabase_client())
    result: DailyReportResult = await run_daily_reconciliation_report(service)
    return {
        "report_id": result.report_id,
        "report_date": result.report_date.isoformat(),
        "created": result.created,
        "clean": result.clean,
        "summary": result.summary,
        "discrepancies": result.discrepancies,
    }
