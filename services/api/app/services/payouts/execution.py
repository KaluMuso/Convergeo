"""Payout execution — row creation, Lenco transfer, ledger posting."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol, cast

from app.errors import AppError
from app.services.ledger.engine import post_transaction
from app.services.ledger.templates import LedgerTemplate
from app.services.payments.base import InitiatePayoutResult, TransferStatus
from app.services.payments.lenco.models import (
    LencoBankPayoutRequest,
    LencoMomoPayoutRequest,
    PayoutOperator,
)
from app.services.payments.references import make_payment_reference
from app.services.payouts.eligibility import load_vendor_cap_limits
from app.services.payouts.reservation import reserve_payout_row
from app.services.payouts.resolve_check import (
    ResolveBankAccountFn,
    VendorPayoutProfile,
    load_vendor_payout_profile,
    notify_payout_held,
    run_resolve_name_check,
)

MOMO_RAILS = frozenset({"mtn", "airtel", "zamtel"})
BANK_SETTLEMENT_HOURS = (24, 36)


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class ResolveAccountFn(Protocol):
    async def __call__(self, request: Any) -> Any: ...


class MomoPayoutFn(Protocol):
    async def __call__(self, request: LencoMomoPayoutRequest) -> InitiatePayoutResult: ...


class BankPayoutFn(Protocol):
    async def __call__(self, request: LencoBankPayoutRequest) -> InitiatePayoutResult: ...


class PayoutOutcome(StrEnum):
    PAID = "paid"
    PROCESSING = "processing"
    HELD = "held"
    DEFERRED = "deferred"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PayoutExecutionResult:
    payout_id: str
    lenco_reference: str
    status: str
    outcome: PayoutOutcome
    amount_ngwee: int
    ledger_transaction_id: str | None = None


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [cast(dict[str, Any], row) for row in data if isinstance(row, dict)]
    return []


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return cast(dict[str, Any], data)
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            return cast(dict[str, Any], first)
    return None


def lenco_account_id() -> str:
    account_id = os.environ.get("LENCO_ACCOUNT_ID", "").strip()
    if not account_id:
        raise AppError(
            code="configuration_error",
            message="LENCO_ACCOUNT_ID is not configured",
            http_status=503,
        )
    return account_id


def _vendor_payout_method_fields(
    service_client: ServiceRoleClient,
    vendor_id: str,
) -> dict[str, Any]:
    response = (
        service_client.client.table("vendors")
        .select("payout_msisdn, payout_rail, payout_hold_until")
        .eq("id", vendor_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    return row if row is not None else {}


def _parse_hold_until(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        normalized = str(value).replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def assert_payout_method_not_held(
    service_client: ServiceRoleClient,
    vendor_id: str,
) -> None:
    """Block payout initiation while payout_hold_until is active (M12-P08)."""
    fields = _vendor_payout_method_fields(service_client, vendor_id)
    hold_until = _parse_hold_until(fields.get("payout_hold_until"))
    if hold_until is not None and hold_until > datetime.now(UTC):
        raise AppError(
            code="payout_method_held",
            message="Payouts are paused after a payout method change",
            http_status=409,
            details={
                "message_key": "vendor.payouts.errors.payoutsPaused",
                "payout_hold_until": hold_until.isoformat(),
            },
        )


def _apply_vendor_payout_destination(
    profile: VendorPayoutProfile,
    fields: dict[str, Any],
) -> VendorPayoutProfile:
    """Prefer vendors.payout_msisdn/payout_rail when set (0021), else KYC profile."""
    msisdn = fields.get("payout_msisdn")
    rail = fields.get("payout_rail")
    if not isinstance(msisdn, str) or not msisdn.strip():
        return profile
    operator = (
        str(rail).strip().lower()
        if isinstance(rail, str) and rail.strip()
        else profile.operator
    )
    if operator not in MOMO_RAILS:
        operator = profile.operator
    return VendorPayoutProfile(
        vendor_id=profile.vendor_id,
        owner_user_id=profile.owner_user_id,
        phone=msisdn.strip(),
        operator=operator,
        legal_name=profile.legal_name,
        rail=operator,
        account_number=profile.account_number,
        bank_id=profile.bank_id,
    )


def _insert_payout_row(
    service_client: ServiceRoleClient,
    *,
    payout_id: str,
    vendor_id: str,
    amount_ngwee: int,
    rail: str,
    lenco_reference: str,
    resolve_snapshot: dict[str, Any],
    status: str = "pending",
) -> dict[str, Any]:
    row = {
        "id": payout_id,
        "vendor_id": vendor_id,
        "amount_ngwee": amount_ngwee,
        "rail": rail,
        "lenco_reference": lenco_reference,
        "status": status,
        "resolve_snapshot": resolve_snapshot,
    }
    response = service_client.client.table("payouts").insert(row).execute()
    inserted = _single_row(response)
    if inserted is None and _rows(response):
        inserted = _rows(response)[0]
    if inserted is None:
        raise AppError(
            code="payout_insert_failed",
            message="Failed to create payout row",
            http_status=500,
        )
    return inserted


def _update_payout_row(
    service_client: ServiceRoleClient,
    payout_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    response = (
        service_client.client.table("payouts")
        .update(payload)
        .eq("id", payout_id)
        .execute()
    )
    updated = _single_row(response)
    if updated is None and _rows(response):
        updated = _rows(response)[0]
    if updated is None:
        raise AppError(
            code="payout_update_failed",
            message=f"Failed to update payout {payout_id}",
            http_status=500,
        )
    return updated


def _map_transfer_status(result: InitiatePayoutResult) -> str:
    if result.status == TransferStatus.SUCCESSFUL:
        return "paid"
    if result.status == TransferStatus.FAILED:
        return "failed"
    return "processing"


def _settlement_expectation(rail: str) -> dict[str, Any]:
    if rail in MOMO_RAILS:
        return {"kind": "instant", "note": "MoMo payout expected near-instant"}
    return {
        "kind": "bank",
        "expected_hours_min": BANK_SETTLEMENT_HOURS[0],
        "expected_hours_max": BANK_SETTLEMENT_HOURS[1],
        "note": "Bank payout expected within 24–36h",
    }


async def _send_lenco_payout(
    profile: VendorPayoutProfile,
    *,
    lenco_reference: str,
    amount_ngwee: int,
    initiate_momo_payout: MomoPayoutFn,
    initiate_bank_payout: BankPayoutFn,
) -> InitiatePayoutResult:
    account_id = lenco_account_id()
    if profile.rail in MOMO_RAILS:
        return await initiate_momo_payout(
            LencoMomoPayoutRequest(
                reference=lenco_reference,
                amount_ngwee=amount_ngwee,
                account_id=account_id,
                phone=profile.phone,
                operator=cast(PayoutOperator, profile.operator),
                country="zm",
                narration=f"Vergeo5 vendor payout {lenco_reference}",
            )
        )

    if profile.account_number and profile.bank_id:
        return await initiate_bank_payout(
            LencoBankPayoutRequest(
                reference=lenco_reference,
                amount_ngwee=amount_ngwee,
                account_id=account_id,
                account_number=profile.account_number,
                bank_id=profile.bank_id,
                country="zm",
                narration=f"Vergeo5 vendor payout {lenco_reference}",
            )
        )

    raise AppError(
        code="unsupported_rail",
        message="Bank payout requires account_number and bank_id on KYC profile",
        http_status=400,
    )


def _post_payout_ledger(
    *,
    payout_id: str,
    vendor_id: str,
    amount_ngwee: int,
    lenco_reference: str,
) -> str:
    posted = post_transaction(
        idempotency_key=f"payout-executed-{payout_id}",
        template=LedgerTemplate.PAYOUT_EXECUTED,
        payout_id=payout_id,
        amount_ngwee=amount_ngwee,
        vendor_id=vendor_id,
    )
    return posted.id


async def execute_vendor_payout(
    service_client: ServiceRoleClient,
    *,
    vendor_id: str,
    amount_ngwee: int | None = None,
    resolve_account: ResolveAccountFn,
    resolve_bank_account: ResolveBankAccountFn | None = None,
    initiate_momo_payout: MomoPayoutFn,
    initiate_bank_payout: BankPayoutFn,
    skip_velocity: bool = False,
) -> PayoutExecutionResult:
    """Full payout pipeline: eligibility → resolve → send → ledger."""
    from app.core.env_guards import payouts_suppressed

    if payouts_suppressed():
        raise AppError(
            code="payouts_suppressed_on_staging",
            message=(
                "Payouts are suppressed on staging. "
                "Set STAGING_ALLOW_PAYOUTS=true only for sandbox drills."
            ),
            http_status=503,
        )
    assert_payout_method_not_held(service_client, vendor_id)
    method_fields = _vendor_payout_method_fields(service_client, vendor_id)
    profile = _apply_vendor_payout_destination(
        load_vendor_payout_profile(service_client, vendor_id),
        method_fields,
    )
    snapshot_pre = compute_amount_and_eligibility(
        service_client,
        vendor_id=vendor_id,
        amount_ngwee=amount_ngwee,
        skip_velocity=skip_velocity,
    )
    if snapshot_pre.deferred:
        # Do NOT insert a pending payouts row. Retry permanently skips
        # resolve_snapshot.deferred=true, so a reserving row would freeze the
        # vendor's available balance forever after one velocity hit. Deferral is
        # a soft signal: the next batch tick retries once the day window resets.
        assert_payout_method_not_held(service_client, vendor_id)
        return PayoutExecutionResult(
            payout_id="",
            lenco_reference="",
            status="deferred",
            outcome=PayoutOutcome.DEFERRED,
            amount_ngwee=snapshot_pre.amount_ngwee,
        )

    payout_amount = snapshot_pre.amount_ngwee

    resolve_result = await run_resolve_name_check(
        profile,
        resolve_account=resolve_account,
        resolve_bank_account=resolve_bank_account,
    )

    payout_id = str(uuid.uuid4())
    lenco_reference = make_payment_reference(payout_id)

    if resolve_result.held:
        assert_payout_method_not_held(service_client, vendor_id)
        reserve_payout_row(
            payout_id=payout_id,
            vendor_id=vendor_id,
            amount_ngwee=payout_amount,
            rail=profile.rail,
            lenco_reference=lenco_reference,
            resolve_snapshot=resolve_result.snapshot,
            status="pending",
        )
        notify_payout_held(
            service_client,
            payout_id=payout_id,
            vendor_id=vendor_id,
            owner_user_id=profile.owner_user_id,
            snapshot=resolve_result.snapshot,
        )
        return PayoutExecutionResult(
            payout_id=payout_id,
            lenco_reference=lenco_reference,
            status="pending",
            outcome=PayoutOutcome.HELD,
            amount_ngwee=payout_amount,
        )

    assert_payout_method_not_held(service_client, vendor_id)
    if not skip_velocity:
        from app.services.kyc.caps import enforce_payout_velocity

        limits = load_vendor_cap_limits(service_client, vendor_id)
        enforce_payout_velocity(limits, payout_amount, service_client)
    reserve_payout_row(
        payout_id=payout_id,
        vendor_id=vendor_id,
        amount_ngwee=payout_amount,
        rail=profile.rail,
        lenco_reference=lenco_reference,
        resolve_snapshot=resolve_result.snapshot,
        status="processing",
    )

    try:
        transfer = await _send_lenco_payout(
            profile,
            lenco_reference=lenco_reference,
            amount_ngwee=payout_amount,
            initiate_momo_payout=initiate_momo_payout,
            initiate_bank_payout=initiate_bank_payout,
        )
    except Exception as exc:
        failure_snapshot = {
            **resolve_result.snapshot,
            "send_error": str(exc),
            "settlement": _settlement_expectation(profile.rail),
        }
        _update_payout_row(
            service_client,
            payout_id,
            {"status": "processing", "resolve_snapshot": failure_snapshot},
        )
        raise

    terminal_status = _map_transfer_status(transfer)
    settlement = _settlement_expectation(profile.rail)
    merged_snapshot = {
        **resolve_result.snapshot,
        "provider_reference": transfer.provider_reference,
        "transfer_status": transfer.status.value,
        "settlement": settlement,
    }

    ledger_id: str | None = None
    if terminal_status == "paid":
        ledger_id = _post_payout_ledger(
            payout_id=payout_id,
            vendor_id=vendor_id,
            amount_ngwee=payout_amount,
            lenco_reference=lenco_reference,
        )

    _update_payout_row(
        service_client,
        payout_id,
        {"status": terminal_status, "resolve_snapshot": merged_snapshot},
    )

    outcome = PayoutOutcome.PAID if terminal_status == "paid" else PayoutOutcome.PROCESSING
    if terminal_status == "failed":
        outcome = PayoutOutcome.FAILED

    return PayoutExecutionResult(
        payout_id=payout_id,
        lenco_reference=lenco_reference,
        status=terminal_status,
        outcome=outcome,
        amount_ngwee=payout_amount,
        ledger_transaction_id=ledger_id,
    )


@dataclass(frozen=True, slots=True)
class _AmountPlan:
    amount_ngwee: int
    deferred: bool


def compute_amount_and_eligibility(
    service_client: ServiceRoleClient,
    *,
    vendor_id: str,
    amount_ngwee: int | None,
    skip_velocity: bool,
) -> _AmountPlan:
    from app.services.payouts.eligibility import check_velocity_deferred, compute_eligibility

    eligibility = compute_eligibility(service_client, vendor_id)
    payout_amount = amount_ngwee if amount_ngwee is not None else eligibility.available_ngwee
    if payout_amount <= 0:
        raise AppError(
            code="nothing_to_payout",
            message="No released balance available for payout",
            http_status=409,
        )
    if not skip_velocity and check_velocity_deferred(
        service_client,
        vendor_id=vendor_id,
        amount_ngwee=payout_amount,
    ):
        return _AmountPlan(amount_ngwee=payout_amount, deferred=True)
    return _AmountPlan(amount_ngwee=payout_amount, deferred=False)
