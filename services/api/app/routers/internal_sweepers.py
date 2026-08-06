"""Internal cron endpoints for consolidated background sweepers."""

from __future__ import annotations

from typing import Any

from app.core.internal_token import InternalTokenMisconfigured, resolve_internal_token
from app.deps import get_supabase_client
from app.errors import AppError
from app.services.payments.lenco.client import LencoStrategy
from app.services.payments.registry import get as get_payment_strategy
from app.services.payouts.batching import run_payout_batch
from app.tasks.sweepers import (
    CartReservationSweepResult,
    DailySummaryResult,
    EscrowSweepResult,
    ExpiredLicenceSweepResult,
    dispatch_daily_summary,
    sweep_expired_cart_reservations,
    sweep_expired_escrows,
    sweep_expired_licenses,
)
from fastapi import APIRouter, Depends, Request

router = APIRouter(prefix="/internal/sweepers", tags=["internal-sweepers"])

_INTERNAL_TOKEN_ENV = "INTERNAL_SWEEPERS_TOKEN"
_DEFAULT_INTERNAL_TOKEN = "dev-internal-sweepers"


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


async def require_internal_sweepers_token(request: Request) -> None:
    """Guard cron ticks — not publicly callable without the shared internal token."""
    expected = _expected_internal_token()
    provided = request.headers.get("X-Internal-Token")
    if not provided or provided != expected:
        raise AppError(
            code="unauthorized",
            message="Invalid or missing internal sweepers token",
            http_status=401,
        )


def _lenco_adapters() -> tuple[LencoStrategy, Any]:
    strategy = get_payment_strategy("lenco")
    if not isinstance(strategy, LencoStrategy):
        msg = "Lenco strategy is required for payout sweeps"
        raise AppError(code="configuration_error", message=msg, http_status=503)
    return strategy, strategy._client


@router.post(
    "/escrow",
    dependencies=[Depends(require_internal_sweepers_token)],
)
async def escrow_sweeper_tick() -> dict[str, int]:
    """Release escrow holds older than 48h and queue vendor payouts."""
    service = next(get_supabase_client())
    stats: EscrowSweepResult = sweep_expired_escrows(service)

    payouts_attempted = 0
    if stats.released > 0:
        strategy, client = _lenco_adapters()
        batch_stats, _ = await run_payout_batch(
            service,
            resolve_account=strategy.resolve_account,
            resolve_bank_account=client.resolve_bank_account,
            initiate_momo_payout=strategy.initiate_momo_payout,
            initiate_bank_payout=strategy.initiate_bank_payout,
        )
        payouts_attempted = batch_stats.payouts_attempted

    return {
        "scanned": stats.scanned,
        "released": stats.released,
        "held": stats.held,
        "already_released": stats.already_released,
        "not_eligible": stats.not_eligible,
        "payout_vendors_queued": stats.payout_vendors_queued,
        "payouts_attempted": payouts_attempted,
    }


@router.post(
    "/cart-reservations",
    dependencies=[Depends(require_internal_sweepers_token)],
)
async def cart_reservation_sweeper_tick() -> dict[str, int]:
    """Expire abandoned cart reservations and restock inventory."""
    stats: CartReservationSweepResult = sweep_expired_cart_reservations()
    return {
        "scanned": stats.scanned,
        "released": stats.released,
        "restocked_qty": stats.restocked_qty,
    }


@router.post(
    "/daily-summary",
    dependencies=[Depends(require_internal_sweepers_token)],
)
async def daily_summary_tick() -> dict[str, int | str | bool]:
    """Compute daily marketplace metrics and POST to the n8n webhook."""
    service = next(get_supabase_client())
    result: DailySummaryResult = dispatch_daily_summary(service)
    return {
        "report_date": result.report_date.isoformat(),
        "gmv_ngwee": result.gmv_ngwee,
        "total_orders": result.total_orders,
        "new_users": result.new_users,
        "dispatched": result.dispatched,
    }


@router.post(
    "/expired-licences",
    dependencies=[Depends(require_internal_sweepers_token)],
)
async def expired_licences_sweeper_tick() -> dict[str, int]:
    """Suspend vendors with expired regulator licences and hide their listings."""
    service = next(get_supabase_client())
    stats: ExpiredLicenceSweepResult = sweep_expired_licenses(service)
    return {
        "scanned": stats.scanned,
        "vendors_suspended": stats.vendors_suspended,
        "listings_removed": stats.listings_removed,
        "audit_rows": stats.audit_rows,
    }
