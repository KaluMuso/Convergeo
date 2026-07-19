from __future__ import annotations

from typing import Annotated, Any

from app.core.internal_token import InternalTokenMisconfigured, resolve_internal_token
from app.deps import get_supabase_client
from app.errors import AppError
from app.services.payments.lenco.client import LencoStrategy
from app.services.payments.registry import get as get_payment_strategy
from app.services.payouts.batching import run_payout_batch
from app.services.payouts.execution import execute_vendor_payout
from app.services.payouts.retry import retry_pending_payouts
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/internal/payouts", tags=["internal-payouts"])

_INTERNAL_TOKEN_ENV = "INTERNAL_PAYOUTS_TOKEN"
_DEFAULT_INTERNAL_TOKEN = "dev-internal-payouts"


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


async def require_internal_payouts_token(request: Request) -> None:
    """Guard cron ticks — not publicly callable without the shared internal token."""
    expected = _expected_internal_token()
    provided = request.headers.get("X-Internal-Token")
    if not provided or provided != expected:
        raise AppError(
            code="unauthorized",
            message="Invalid or missing internal payouts token",
            http_status=401,
        )


class ExecutePayoutBody(BaseModel):
    vendor_id: str
    amount_ngwee: int | None = Field(default=None, gt=0)


def _lenco_adapters() -> tuple[LencoStrategy, Any]:
    strategy = get_payment_strategy("lenco")
    if not isinstance(strategy, LencoStrategy):
        msg = "Lenco strategy is required for payouts"
        raise AppError(code="configuration_error", message=msg, http_status=503)
    return strategy, strategy._client


@router.post(
    "/tick",
    dependencies=[Depends(require_internal_payouts_token)],
)
async def payouts_batch_tick(
    supabase: Annotated[Any, Depends(get_supabase_client)],
) -> dict[str, int]:
    """Process eligible vendor payouts in batch (n8n cron)."""
    strategy, client = _lenco_adapters()
    stats, _ = await run_payout_batch(
        supabase,
        resolve_account=strategy.resolve_account,
        resolve_bank_account=client.resolve_bank_account,
        initiate_momo_payout=strategy.initiate_momo_payout,
        initiate_bank_payout=strategy.initiate_bank_payout,
    )
    return {
        "vendors_scanned": stats.vendors_scanned,
        "payouts_attempted": stats.payouts_attempted,
        "paid": stats.paid,
        "processing": stats.processing,
        "held": stats.held,
        "deferred": stats.deferred,
        "failed": stats.failed,
        "skipped": stats.skipped,
    }


@router.post(
    "/retry",
    dependencies=[Depends(require_internal_payouts_token)],
)
async def payouts_retry_tick(
    supabase: Annotated[Any, Depends(get_supabase_client)],
) -> dict[str, int]:
    """Re-query and retry in-flight payouts (status before re-send)."""
    strategy, client = _lenco_adapters()
    stats = await retry_pending_payouts(
        supabase,
        query_transfer_status=client,
        initiate_momo_payout=strategy.initiate_momo_payout,
        initiate_bank_payout=strategy.initiate_bank_payout,
    )
    return {
        "scanned": stats.scanned,
        "completed": stats.completed,
        "retried": stats.retried,
        "dead_lettered": stats.dead_lettered,
        "skipped": stats.skipped,
    }


@router.post(
    "/execute",
    dependencies=[Depends(require_internal_payouts_token)],
)
async def execute_single_payout(
    body: ExecutePayoutBody,
    supabase: Annotated[Any, Depends(get_supabase_client)],
) -> dict[str, Any]:
    """Execute one vendor payout (manual / targeted)."""
    strategy, lenco_client = _lenco_adapters()
    result = await execute_vendor_payout(
        supabase,
        vendor_id=body.vendor_id,
        amount_ngwee=body.amount_ngwee,
        resolve_account=strategy.resolve_account,
        resolve_bank_account=lenco_client.resolve_bank_account,
        initiate_momo_payout=strategy.initiate_momo_payout,
        initiate_bank_payout=strategy.initiate_bank_payout,
    )
    return {
        "payout_id": result.payout_id,
        "lenco_reference": result.lenco_reference,
        "status": result.status,
        "outcome": result.outcome.value,
        "amount_ngwee": result.amount_ngwee,
        "ledger_transaction_id": result.ledger_transaction_id,
    }
