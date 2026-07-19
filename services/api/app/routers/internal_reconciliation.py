from __future__ import annotations

from app.core.internal_token import InternalTokenMisconfigured, resolve_internal_token
from app.errors import AppError
from app.services.payments.reconcile import (
    DailyReportResult,
    DrainResult,
    PollResult,
    drain_pending_webhook_events,
    poll_non_terminal_payments,
    run_daily_reconciliation_report,
)
from app.services.payments.registry import get
from fastapi import APIRouter, Depends, Request

router = APIRouter(prefix="/internal/reconciliation", tags=["internal-reconciliation"])

_INTERNAL_TOKEN_ENV = "INTERNAL_RECONCILIATION_TOKEN"
_DEFAULT_INTERNAL_TOKEN = "dev-internal-reconciliation"


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
    "/webhook-drain-tick",
    dependencies=[Depends(require_internal_reconciliation_token)],
)
async def reconciliation_webhook_drain_tick() -> dict[str, int]:
    """Frequent tick: apply stored Lenco webhooks to the payment state machine.

    Fast path for the MoMo/USSD push confirmation — processes the webhook_events
    the ``/webhooks/lenco`` endpoint persisted, without a Lenco re-query.
    """
    from app.deps import get_supabase_client

    service = next(get_supabase_client())
    stats: DrainResult = drain_pending_webhook_events(service)
    return {
        "scanned": stats.scanned,
        "applied": stats.applied,
        "skipped": stats.skipped,
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
