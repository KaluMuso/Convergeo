"""Payout retry with status re-query before re-send (never double-pay)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from app.services.payments.lenco.models import LencoTransferStatusResponse
from app.services.payments.state import SYSTEM_ACTOR_ID
from app.services.payouts.execution import (
    BankPayoutFn,
    MomoPayoutFn,
    _map_transfer_status,
    _post_payout_ledger,
    _rows,
    _send_lenco_payout,
    _settlement_expectation,
    _update_payout_row,
)
from app.services.payouts.resolve_check import load_vendor_payout_profile

logger = logging.getLogger(__name__)

MAX_PAYOUT_ATTEMPTS = 5
RETRY_BACKOFF_BASE_SECONDS = 120


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class TransferStatusQuerier(Protocol):
    async def query_transfer_status(self, reference: str) -> LencoTransferStatusResponse: ...


@dataclass(slots=True)
class RetryStats:
    scanned: int
    completed: int
    retried: int
    dead_lettered: int
    skipped: int


def compute_retry_backoff_seconds(
    attempt: int,
    *,
    base_seconds: int = RETRY_BACKOFF_BASE_SECONDS,
) -> int:
    """Exponential backoff: base, 2×base, 4×base, …"""
    if attempt < 1:
        return base_seconds
    return int(base_seconds * (2 ** (attempt - 1)))


def _attempt_count(snapshot: dict[str, Any]) -> int:
    raw = snapshot.get("retry_attempts")
    if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 0:
        return raw
    return 0


def _next_retry_at(snapshot: dict[str, Any]) -> datetime | None:
    raw = snapshot.get("next_retry_at")
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None
    return None


def _provider_status_to_db(status: str) -> str:
    normalized = status.strip().lower()
    if normalized == "successful":
        return "paid"
    if normalized == "failed":
        return "failed"
    return "processing"


def dead_letter_payout(
    service_client: ServiceRoleClient,
    *,
    payout_id: str,
    vendor_id: str,
    lenco_reference: str,
    reason: str,
    snapshot: dict[str, Any],
) -> None:
    """Route exhausted payout failures to the admin audit queue."""
    structured = {
        "payout_id": payout_id,
        "vendor_id": vendor_id,
        "lenco_reference": lenco_reference,
        "reason": reason,
        "snapshot": snapshot,
        "dead_lettered_at": datetime.now(UTC).isoformat(),
    }
    service_client.client.table("audit_log").insert(
        {
            "actor": SYSTEM_ACTOR_ID,
            "action": "payout.dead_letter",
            "entity_type": "payout",
            "entity_id": payout_id,
            "before": None,
            "after": structured,
        }
    ).execute()
    logger.error(
        "Payout dead-lettered",
        extra={"payout_id": payout_id, "vendor_id": vendor_id, "reason": reason},
    )


async def retry_payout_row(
    service_client: ServiceRoleClient,
    payout_row: dict[str, Any],
    *,
    query_transfer_status: TransferStatusQuerier,
    initiate_momo_payout: MomoPayoutFn,
    initiate_bank_payout: BankPayoutFn,
    now: datetime | None = None,
) -> str:
    """Re-query Lenco status before any re-send. Returns outcome label."""
    clock = now or datetime.now(UTC)
    payout_id = str(payout_row["id"])
    vendor_id = str(payout_row["vendor_id"])
    lenco_reference = str(payout_row["lenco_reference"])
    amount_ngwee = int(payout_row["amount_ngwee"])
    status = str(payout_row.get("status", "pending"))
    snapshot = payout_row.get("resolve_snapshot")
    if not isinstance(snapshot, dict):
        snapshot = {}

    if status == "paid":
        return "skipped"

    attempts = _attempt_count(snapshot)
    next_retry = _next_retry_at(snapshot)
    if next_retry is not None and clock < next_retry:
        return "skipped"

    # Status re-query BEFORE re-send — timed-out transfer may have succeeded.
    query_response = await query_transfer_status.query_transfer_status(lenco_reference)
    if query_response.data is not None:
        provider_status = _provider_status_to_db(query_response.data.status)
        if provider_status == "paid":
            ledger_id = _post_payout_ledger(
                payout_id=payout_id,
                vendor_id=vendor_id,
                amount_ngwee=amount_ngwee,
                lenco_reference=lenco_reference,
            )
            merged = {
                **snapshot,
                "reconciled_via": "status_requery",
                "provider_status": query_response.data.status,
                "ledger_transaction_id": ledger_id,
            }
            _update_payout_row(
                service_client,
                payout_id,
                {"status": "paid", "resolve_snapshot": merged},
            )
            return "completed"

        if provider_status == "failed" and status != "processing":
            merged = {**snapshot, "provider_status": query_response.data.status}
            _update_payout_row(
                service_client,
                payout_id,
                {"status": "failed", "resolve_snapshot": merged},
            )
            return "failed"

    if status not in {"processing", "pending"}:
        return "skipped"

    if attempts >= MAX_PAYOUT_ATTEMPTS:
        dead_letter_payout(
            service_client,
            payout_id=payout_id,
            vendor_id=vendor_id,
            lenco_reference=lenco_reference,
            reason="max_retry_attempts_exceeded",
            snapshot=snapshot,
        )
        _update_payout_row(
            service_client,
            payout_id,
            {
                "status": "failed",
                "resolve_snapshot": {
                    **snapshot,
                    "dead_lettered": True,
                    "retry_attempts": attempts,
                },
            },
        )
        return "dead_lettered"

    profile = load_vendor_payout_profile(service_client, vendor_id)
    try:
        transfer = await _send_lenco_payout(
            profile,
            lenco_reference=lenco_reference,
            amount_ngwee=amount_ngwee,
            initiate_momo_payout=initiate_momo_payout,
            initiate_bank_payout=initiate_bank_payout,
        )
    except Exception as exc:
        new_attempts = attempts + 1
        backoff = compute_retry_backoff_seconds(new_attempts)
        merged = {
            **snapshot,
            "retry_attempts": new_attempts,
            "last_error": str(exc),
            "next_retry_at": (clock + timedelta(seconds=backoff)).isoformat(),
            "settlement": _settlement_expectation(profile.rail),
        }
        _update_payout_row(
            service_client,
            payout_id,
            {"status": "processing", "resolve_snapshot": merged},
        )
        if new_attempts >= MAX_PAYOUT_ATTEMPTS:
            dead_letter_payout(
                service_client,
                payout_id=payout_id,
                vendor_id=vendor_id,
                lenco_reference=lenco_reference,
                reason=str(exc),
                snapshot=merged,
            )
            _update_payout_row(
                service_client,
                payout_id,
                {"status": "failed", "resolve_snapshot": {**merged, "dead_lettered": True}},
            )
            return "dead_lettered"
        return "retried"

    terminal_status = _map_transfer_status(transfer)
    merged = {
        **snapshot,
        "retry_attempts": attempts + 1,
        "provider_reference": transfer.provider_reference,
        "transfer_status": transfer.status.value,
        "settlement": _settlement_expectation(profile.rail),
    }

    if terminal_status == "paid":
        ledger_id = _post_payout_ledger(
            payout_id=payout_id,
            vendor_id=vendor_id,
            amount_ngwee=amount_ngwee,
            lenco_reference=lenco_reference,
        )
        merged["ledger_transaction_id"] = ledger_id
        _update_payout_row(
            service_client,
            payout_id,
            {"status": "paid", "resolve_snapshot": merged},
        )
        return "completed"

    if terminal_status == "failed":
        new_attempts = attempts + 1
        if new_attempts >= MAX_PAYOUT_ATTEMPTS:
            dead_letter_payout(
                service_client,
                payout_id=payout_id,
                vendor_id=vendor_id,
                lenco_reference=lenco_reference,
                reason="provider_failed",
                snapshot=merged,
            )
            _update_payout_row(
                service_client,
                payout_id,
                {"status": "failed", "resolve_snapshot": {**merged, "dead_lettered": True}},
            )
            return "dead_lettered"
        backoff = compute_retry_backoff_seconds(new_attempts)
        merged["next_retry_at"] = (clock + timedelta(seconds=backoff)).isoformat()
        _update_payout_row(
            service_client,
            payout_id,
            {"status": "processing", "resolve_snapshot": merged},
        )
        return "retried"

    backoff = compute_retry_backoff_seconds(attempts + 1)
    merged["next_retry_at"] = (clock + timedelta(seconds=backoff)).isoformat()
    _update_payout_row(
        service_client,
        payout_id,
        {"status": "processing", "resolve_snapshot": merged},
    )
    return "retried"


async def retry_pending_payouts(
    service_client: ServiceRoleClient,
    *,
    query_transfer_status: TransferStatusQuerier,
    initiate_momo_payout: MomoPayoutFn,
    initiate_bank_payout: BankPayoutFn,
    limit: int = 50,
    now: datetime | None = None,
) -> RetryStats:
    response = (
        service_client.client.table("payouts")
        .select("id, vendor_id, amount_ngwee, rail, lenco_reference, status, resolve_snapshot")
        .in_("status", ["pending", "processing"])
        .order("created_at")
        .limit(limit)
        .execute()
    )
    rows = _rows(response)
    stats = RetryStats(scanned=len(rows), completed=0, retried=0, dead_lettered=0, skipped=0)

    for row in rows:
        snapshot = row.get("resolve_snapshot")
        if isinstance(snapshot, dict) and snapshot.get("held") is True:
            stats.skipped += 1
            continue
        if isinstance(snapshot, dict) and snapshot.get("deferred") is True:
            stats.skipped += 1
            continue

        outcome = await retry_payout_row(
            service_client,
            row,
            query_transfer_status=query_transfer_status,
            initiate_momo_payout=initiate_momo_payout,
            initiate_bank_payout=initiate_bank_payout,
            now=now,
        )
        if outcome == "completed":
            stats.completed += 1
        elif outcome == "retried":
            stats.retried += 1
        elif outcome == "dead_lettered":
            stats.dead_lettered += 1
        else:
            stats.skipped += 1

    return stats
