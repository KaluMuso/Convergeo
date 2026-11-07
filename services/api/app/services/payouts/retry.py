"""Payout retry with status re-query before re-send (never double-pay)."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from app.services.payments.base import ProviderOutcome, ProviderResult
from app.services.payouts.execution import (
    BankPayoutFn,
    MomoPayoutFn,
    _map_transfer_status,
    _post_payout_ledger,
    _rows,
    _send_lenco_payout,
    _settlement_expectation,
    _update_payout_row,
    lenco_account_id,
)
from app.services.payouts.obligation import (
    PayoutObservationMismatch,
    destination_for_profile,
    make_obligation,
    obligation_from_snapshot,
    validate_transfer_observation,
)
from app.services.payouts.resolve_check import VendorPayoutProfile, load_vendor_payout_profile
from app.services.refunds.state import complete_refund_from_provider_payout

logger = logging.getLogger(__name__)

RETRY_BACKOFF_BASE_SECONDS = 120


def _is_customer_refund(snapshot: dict[str, Any]) -> bool:
    """Refund payouts (M08-P10) are tagged so the sweeper sends to the customer,
    not the vendor, and skips the vendor `payout_executed` ledger post — the refund
    ledger legs were already posted by `execute_refund` at decision time."""
    return snapshot.get("kind") == "customer_refund"


def _dispatch_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    raw = snapshot.get("dispatch")
    return dict(raw) if isinstance(raw, dict) else {}


def _has_never_sent_provenance(snapshot: dict[str, Any]) -> bool:
    """Only the server-created, unconsumed marker permits a first dispatch.

    Historical pending rows can already have reached the provider. Never backfill
    this marker from a status, timestamp, missing response or not-found lookup.
    """
    attempts = snapshot.get("retry_attempts", 0)
    return (
        _dispatch_snapshot(snapshot) == {"state": "never_sent"}
        and isinstance(attempts, int)
        and not isinstance(attempts, bool)
        and attempts == 0
        and not any(snapshot.get(key) for key in (
            "provider_reference", "provider_status", "transfer_status",
            "last_error", "last_query_error", "verified_transfer",
        ))
    )


def _payout_destination_profile(
    service_client: ServiceRoleClient,
    *,
    payout_row: dict[str, Any],
    snapshot: dict[str, Any],
) -> VendorPayoutProfile:
    """Vendor payout → vendor KYC profile; customer refund → customer momo destination."""
    if _is_customer_refund(snapshot):
        rail = str(payout_row.get("rail", "mtn"))
        return VendorPayoutProfile(
            vendor_id=str(payout_row.get("vendor_id", "")),
            owner_user_id="",
            phone=str(snapshot.get("customer_momo", "")),
            operator=rail,
            legal_name="",
            rail=rail,
        )
    return load_vendor_payout_profile(service_client, str(payout_row["vendor_id"]))


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class TransferStatusQuerier(Protocol):
    async def query_transfer_status(self, reference: str) -> ProviderResult: ...


@dataclass(slots=True)
class RetryStats:
    scanned: int
    completed: int
    retried: int
    dead_lettered: int
    skipped: int
    manual: int = 0
    errors: int = 0


def compute_retry_backoff_seconds(
    attempt: int,
    *,
    base_seconds: int = RETRY_BACKOFF_BASE_SECONDS,
) -> int:
    """Exponential backoff: base, 2×base, 4×base, …"""
    if attempt < 1:
        return base_seconds
    return int(base_seconds * (2 ** (attempt - 1)))


def _next_retry_at(snapshot: dict[str, Any]) -> datetime | None:
    raw = snapshot.get("next_retry_at")
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None
    return None


def _notify_customer_refund_paid(
    service_client: ServiceRoleClient,
    *,
    payout_id: str,
    provider_status: str | None = None,
) -> None:
    complete_refund_from_provider_payout(
        service_client,
        payout_id=payout_id,
        provider_status=provider_status,
    )

    refund_resp = (
        service_client.client.table("refunds")
        .select("id")
        .eq("payout_ref", payout_id)
        .maybe_single()
        .execute()
    )
    refund_row = getattr(refund_resp, "data", None)
    if isinstance(refund_row, dict) and refund_row.get("id"):
        from app.services.events.refund_jobs import sync_event_refund_job_for_refund

        sync_event_refund_job_for_refund(service_client, refund_id=str(refund_row["id"]))


def _claim_first_dispatch(
    service_client: ServiceRoleClient,
    *,
    payout_row: dict[str, Any],
    snapshot: dict[str, Any],
    profile: VendorPayoutProfile,
    clock: datetime,
) -> dict[str, Any] | None:
    """Atomically turn never-sent into a durable claim before the provider POST."""
    if not _has_never_sent_provenance(snapshot):
        return None
    payout_id = str(payout_row["id"])
    obligation = snapshot.get("obligation")
    account_id = lenco_account_id()
    if not isinstance(obligation, dict):
        obligation = make_obligation(
            merchant_reference=str(payout_row["lenco_reference"]),
            amount_ngwee=int(payout_row["amount_ngwee"]),
            debit_account_id=account_id,
            destination=destination_for_profile(profile),
        )
    else:
        prior_account = obligation.get("debit_account_id")
        if prior_account not in {None, account_id}:
            raise PayoutObservationMismatch(payout_id, "debit_account_changed_before_dispatch")
        obligation = {**obligation, "debit_account_id": account_id}

    owner = str(uuid.uuid4())
    claimed = {
        **snapshot,
        "obligation": obligation,
        "dispatch": {
            "state": "claimed",
            "owner": owner,
            "claimed_at": clock.isoformat(),
        },
    }
    response = (
        service_client.client.table("payouts")
        .update({"status": "processing", "resolve_snapshot": claimed})
        .eq("id", payout_id)
        .eq("status", "pending")
        .eq("resolve_snapshot->dispatch->>state", "never_sent")
        .execute()
    )
    rows = _rows(response)
    if not rows:
        return None
    updated = rows[0].get("resolve_snapshot")
    return updated if isinstance(updated, dict) else claimed


def _manual_hold(
    service_client: ServiceRoleClient,
    *,
    payout_id: str,
    snapshot: dict[str, Any],
    reason: str,
    provider_status: str | None = None,
) -> None:
    dispatch = snapshot.get("dispatch")
    if not isinstance(dispatch, dict):
        dispatch = {}
    merged = {
        **snapshot,
        "held": True,
        "hold_reason": reason,
        "dispatch": {**dispatch, "state": "manual_review"},
    }
    if provider_status is not None:
        merged["provider_status"] = provider_status
    _update_payout_row(
        service_client,
        payout_id,
        {"status": "processing", "resolve_snapshot": merged},
    )


def _complete_verified_payout(
    service_client: ServiceRoleClient,
    *,
    payout_row: dict[str, Any],
    snapshot: dict[str, Any],
    observation: ProviderResult | Any,
    source: str,
) -> str:
    payout_id = str(payout_row["id"])
    obligation = obligation_from_snapshot(snapshot, payout_id=payout_id)
    expected_provider_reference = snapshot.get("provider_reference")
    if not isinstance(expected_provider_reference, str):
        expected_provider_reference = None
    evidence = validate_transfer_observation(
        payout_id=payout_id,
        obligation=obligation,
        observation=observation,
        expected_provider_reference=expected_provider_reference,
    )
    merged = {
        **snapshot,
        "provider_reference": evidence.provider_reference,
        "provider_status": "successful",
        "reconciled_via": source,
        "verified_transfer": evidence.as_snapshot(),
        "dispatch": {
            **_dispatch_snapshot(snapshot),
            "state": "successful",
        },
    }
    if not _is_customer_refund(snapshot):
        merged["ledger_transaction_id"] = _post_payout_ledger(
            payout_id=payout_id,
            vendor_id=str(payout_row["vendor_id"]),
            amount_ngwee=int(payout_row["amount_ngwee"]),
            lenco_reference=str(payout_row["lenco_reference"]),
        )
    _update_payout_row(
        service_client,
        payout_id,
        {"status": "paid", "resolve_snapshot": merged},
    )
    if _is_customer_refund(snapshot):
        _notify_customer_refund_paid(
            service_client,
            payout_id=payout_id,
            provider_status="successful",
        )
    return "completed"


async def retry_payout_row(
    service_client: ServiceRoleClient,
    payout_row: dict[str, Any],
    *,
    query_transfer_status: TransferStatusQuerier,
    initiate_momo_payout: MomoPayoutFn,
    initiate_bank_payout: BankPayoutFn,
    now: datetime | None = None,
) -> str:
    """Claim a first send once; after any attempt, only poll the stable reference."""
    clock = now or datetime.now(UTC)
    payout_id = str(payout_row["id"])
    lenco_reference = str(payout_row["lenco_reference"])
    amount_ngwee = int(payout_row["amount_ngwee"])
    status = str(payout_row.get("status", "pending"))
    snapshot = payout_row.get("resolve_snapshot")
    if not isinstance(snapshot, dict):
        snapshot = {}

    if status == "paid" or snapshot.get("held") is True:
        return "skipped"

    next_retry = _next_retry_at(snapshot)
    if next_retry is not None and clock < next_retry:
        return "skipped"

    if status == "pending" and _has_never_sent_provenance(snapshot):
        profile = _payout_destination_profile(
            service_client,
            payout_row=payout_row,
            snapshot=snapshot,
        )
        claimed = _claim_first_dispatch(
            service_client,
            payout_row=payout_row,
            snapshot=snapshot,
            profile=profile,
            clock=clock,
        )
        if claimed is None:
            return "skipped"
        snapshot = claimed
        obligation = obligation_from_snapshot(snapshot, payout_id=payout_id)
        account_id = obligation.get("debit_account_id")
        if not isinstance(account_id, str) or not account_id:
            _manual_hold(
                service_client,
                payout_id=payout_id,
                snapshot=snapshot,
                reason="debit_account_missing",
            )
            return "manual"

        try:
            transfer = await _send_lenco_payout(
                profile,
                lenco_reference=lenco_reference,
                amount_ngwee=amount_ngwee,
                initiate_momo_payout=initiate_momo_payout,
                initiate_bank_payout=initiate_bank_payout,
                account_id=account_id,
            )
        except Exception as exc:
            backoff = compute_retry_backoff_seconds(1)
            dispatch = snapshot.get("dispatch")
            merged = {
                **snapshot,
                "last_error": str(exc),
                "next_retry_at": (clock + timedelta(seconds=backoff)).isoformat(),
                "settlement": _settlement_expectation(profile.rail),
                "dispatch": {
                    **(dispatch if isinstance(dispatch, dict) else {}),
                    "state": "possibly_sent",
                    "failed_at": clock.isoformat(),
                },
            }
            _update_payout_row(
                service_client,
                payout_id,
                {"status": "processing", "resolve_snapshot": merged},
            )
            return "retried"

        merged = {
            **snapshot,
            "provider_reference": transfer.provider_reference,
            "transfer_status": transfer.status.value,
            "settlement": _settlement_expectation(profile.rail),
            "dispatch": {
                **_dispatch_snapshot(snapshot),
                "state": transfer.status.value,
                "observed_at": clock.isoformat(),
            },
        }
        terminal_status = _map_transfer_status(transfer)
        if terminal_status == "paid":
            try:
                return _complete_verified_payout(
                    service_client,
                    payout_row=payout_row,
                    snapshot=merged,
                    observation=transfer,
                    source="first_dispatch",
                )
            except PayoutObservationMismatch as exc:
                _manual_hold(
                    service_client,
                    payout_id=payout_id,
                    snapshot=merged,
                    reason=str(exc.details["reason"]),
                    provider_status=transfer.status.value,
                )
                raise

        if terminal_status == "failed":
            _manual_hold(
                service_client,
                payout_id=payout_id,
                snapshot=merged,
                reason="provider_failed_reference_reuse_unconfirmed",
                provider_status=transfer.status.value,
            )
            return "manual"

        backoff = compute_retry_backoff_seconds(1)
        merged["next_retry_at"] = (clock + timedelta(seconds=backoff)).isoformat()
        _update_payout_row(
            service_client,
            payout_id,
            {"status": "processing", "resolve_snapshot": merged},
        )
        return "retried"

    # Unmarked historical pending is possibly sent, not a new-send opportunity.
    # Query the original reference; missing immutable evidence will hold completion.
    if status not in {"pending", "processing"}:
        return "skipped"

    try:
        result = await query_transfer_status.query_transfer_status(lenco_reference)
    except Exception as exc:
        dispatch = snapshot.get("dispatch")
        _update_payout_row(
            service_client,
            payout_id,
            {
                "status": "processing",
                "resolve_snapshot": {
                    **snapshot,
                    "last_query_error": str(exc),
                    "next_retry_at": (
                        clock + timedelta(seconds=compute_retry_backoff_seconds(1))
                    ).isoformat(),
                    "dispatch": {
                        **(dispatch if isinstance(dispatch, dict) else {}),
                        "state": "possibly_sent",
                    },
                },
            },
        )
        raise

    if result.outcome == ProviderOutcome.SUCCESSFUL:
        try:
            return _complete_verified_payout(
                service_client,
                payout_row=payout_row,
                snapshot=snapshot,
                observation=result,
                source="status_requery",
            )
        except PayoutObservationMismatch as exc:
            _manual_hold(
                service_client,
                payout_id=payout_id,
                snapshot=snapshot,
                reason=str(exc.details["reason"]),
                provider_status=result.status,
            )
            raise

    if result.outcome == ProviderOutcome.PENDING:
        merged = {
            **snapshot,
            "provider_reference": result.provider_reference
            or snapshot.get("provider_reference"),
            "provider_status": result.status,
            "next_retry_at": (
                clock + timedelta(seconds=compute_retry_backoff_seconds(1))
            ).isoformat(),
            "dispatch": {
                **_dispatch_snapshot(snapshot),
                "state": "pending",
            },
        }
        _update_payout_row(
            service_client,
            payout_id,
            {"status": "processing", "resolve_snapshot": merged},
        )
        return "retried"

    reason = (
        "provider_failed_reference_reuse_unconfirmed"
        if result.outcome == ProviderOutcome.FAILED
        else "not_found_after_dispatch"
    )
    _manual_hold(
        service_client,
        payout_id=payout_id,
        snapshot=snapshot,
        reason=reason,
        provider_status=result.status,
    )
    return "manual"


async def retry_pending_payouts(
    service_client: ServiceRoleClient,
    *,
    query_transfer_status: TransferStatusQuerier,
    initiate_momo_payout: MomoPayoutFn,
    initiate_bank_payout: BankPayoutFn,
    limit: int = 50,
    now: datetime | None = None,
) -> RetryStats:
    from app.services.payouts.gate import assert_payouts_execution_allowed

    assert_payouts_execution_allowed()
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

        try:
            outcome = await retry_payout_row(
                service_client,
                row,
                query_transfer_status=query_transfer_status,
                initiate_momo_payout=initiate_momo_payout,
                initiate_bank_payout=initiate_bank_payout,
                now=now,
            )
        except Exception:
            logger.exception(
                "payout retry item failed; continuing batch",
                extra={"payout_id": str(row.get("id", ""))},
            )
            stats.errors += 1
            continue
        if outcome == "completed":
            stats.completed += 1
        elif outcome == "retried":
            stats.retried += 1
        elif outcome == "dead_lettered":
            stats.dead_lettered += 1
        elif outcome == "manual":
            stats.manual += 1
        else:
            stats.skipped += 1

    return stats
