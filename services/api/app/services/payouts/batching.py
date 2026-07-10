"""Batch payout processing for vendors with released balance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, cast

from app.services.payouts.eligibility import compute_eligibility, released_balance_ngwee
from app.services.payouts.execution import (
    BankPayoutFn,
    MomoPayoutFn,
    PayoutExecutionResult,
    PayoutOutcome,
    execute_vendor_payout,
)
from app.services.payouts.resolve_check import ResolveAccountFn, ResolveBankAccountFn


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


@dataclass(slots=True)
class BatchStats:
    vendors_scanned: int
    payouts_attempted: int
    paid: int
    processing: int
    held: int
    deferred: int
    failed: int
    skipped: int


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [cast(dict[str, Any], row) for row in data if isinstance(row, dict)]
    return []


def list_vendors_with_released_balance(
    service_client: ServiceRoleClient,
    *,
    min_ngwee: int = 1,
    limit: int = 100,
) -> list[str]:
    """Return vendor IDs with positive released balance (ledger-derived)."""
    response = (
        service_client.client.table("vendors")
        .select("id, status")
        .eq("status", "active")
        .limit(limit)
        .execute()
    )
    vendor_ids: list[str] = []
    for row in _rows(response):
        vendor_id = str(row["id"])
        if released_balance_ngwee(vendor_id) >= min_ngwee:
            eligibility = compute_eligibility(service_client, vendor_id)
            if eligibility.available_ngwee >= min_ngwee:
                vendor_ids.append(vendor_id)
    return vendor_ids


async def run_payout_batch(
    service_client: ServiceRoleClient,
    *,
    vendor_ids: list[str] | None = None,
    resolve_account: ResolveAccountFn,
    resolve_bank_account: ResolveBankAccountFn | None = None,
    initiate_momo_payout: MomoPayoutFn,
    initiate_bank_payout: BankPayoutFn,
    min_ngwee: int = 1,
    limit: int = 50,
) -> tuple[BatchStats, list[PayoutExecutionResult]]:
    targets = vendor_ids or list_vendors_with_released_balance(
        service_client,
        min_ngwee=min_ngwee,
        limit=limit,
    )

    stats = BatchStats(
        vendors_scanned=len(targets),
        payouts_attempted=0,
        paid=0,
        processing=0,
        held=0,
        deferred=0,
        failed=0,
        skipped=0,
    )
    results: list[PayoutExecutionResult] = []

    for vendor_id in targets[:limit]:
        eligibility = compute_eligibility(service_client, vendor_id)
        if eligibility.available_ngwee < min_ngwee:
            stats.skipped += 1
            continue

        stats.payouts_attempted += 1
        try:
            result = await execute_vendor_payout(
                service_client,
                vendor_id=vendor_id,
                amount_ngwee=None,
                resolve_account=resolve_account,
                resolve_bank_account=resolve_bank_account,
                initiate_momo_payout=initiate_momo_payout,
                initiate_bank_payout=initiate_bank_payout,
            )
        except Exception:
            stats.failed += 1
            continue

        results.append(result)
        if result.outcome == PayoutOutcome.PAID:
            stats.paid += 1
        elif result.outcome == PayoutOutcome.PROCESSING:
            stats.processing += 1
        elif result.outcome == PayoutOutcome.HELD:
            stats.held += 1
        elif result.outcome == PayoutOutcome.DEFERRED:
            stats.deferred += 1
        else:
            stats.failed += 1

    return stats, results
