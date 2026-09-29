"""Immutable payout obligations and provider evidence validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.errors import AppError
from app.services.payments.money import major_str_to_ngwee
from app.services.payouts.resolve_check import VendorPayoutProfile


class TransferObservation(Protocol):
    @property
    def reference(self) -> str | None: ...

    @property
    def provider_reference(self) -> str | None: ...

    @property
    def amount_major(self) -> str | None: ...

    @property
    def currency(self) -> str | None: ...

    @property
    def debit_account_id(self) -> str | None: ...

    @property
    def destination(self) -> dict[str, Any] | None: ...


class PayoutObservationMismatch(AppError):
    """A provider transfer does not satisfy the reserved payout obligation."""

    def __init__(self, payout_id: str, reason: str) -> None:
        super().__init__(
            code="payout_provider_observation_mismatch",
            message="Provider transfer does not match the payout obligation",
            http_status=409,
            details={"payout_id": payout_id, "reason": reason},
        )


@dataclass(frozen=True, slots=True)
class ValidatedTransferEvidence:
    merchant_reference: str
    provider_reference: str
    amount_ngwee: int
    currency: str
    debit_account_id: str
    destination: dict[str, str]

    def as_snapshot(self) -> dict[str, Any]:
        return {
            "merchant_reference": self.merchant_reference,
            "provider_reference": self.provider_reference,
            "amount_ngwee": self.amount_ngwee,
            "currency": self.currency,
            "debit_account_id": self.debit_account_id,
            "destination": self.destination,
        }


def destination_for_profile(profile: VendorPayoutProfile) -> dict[str, str]:
    if profile.rail in {"mtn", "airtel", "zamtel"}:
        return {
            "type": "mobile-money",
            "phone": profile.phone,
            "operator": profile.operator,
        }
    if profile.account_number and profile.bank_id:
        return {
            "type": "bank-account",
            "account_number": profile.account_number,
            "bank_id": profile.bank_id,
        }
    raise ValueError("payout destination is incomplete")


def make_obligation(
    *,
    merchant_reference: str,
    amount_ngwee: int,
    debit_account_id: str | None,
    destination: dict[str, str],
    currency: str = "ZMW",
) -> dict[str, Any]:
    return {
        "merchant_reference": merchant_reference,
        "amount_ngwee": amount_ngwee,
        "currency": currency,
        "debit_account_id": debit_account_id,
        "destination": dict(destination),
    }


def obligation_from_snapshot(
    snapshot: dict[str, Any],
    *,
    payout_id: str,
) -> dict[str, Any]:
    obligation = snapshot.get("obligation")
    if not isinstance(obligation, dict):
        raise PayoutObservationMismatch(payout_id, "obligation_missing")
    return obligation


def _observed_destination(value: dict[str, Any] | None) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    kind = value.get("type")
    if kind == "mobile-money":
        phone = value.get("phone")
        operator = value.get("operator")
        if isinstance(phone, str) and isinstance(operator, str):
            return {"type": kind, "phone": phone, "operator": operator}
        return None
    if kind == "bank-account":
        account_number = value.get("account_number", value.get("accountNumber"))
        bank_id: object = value.get("bank_id", value.get("bankId"))
        bank = value.get("bank")
        if bank_id is None and isinstance(bank, dict):
            bank_id = bank.get("id")
        if isinstance(account_number, str) and isinstance(bank_id, str):
            return {
                "type": kind,
                "account_number": account_number,
                "bank_id": bank_id,
            }
    return None


def validate_transfer_observation(
    *,
    payout_id: str,
    obligation: dict[str, Any],
    observation: TransferObservation,
    expected_provider_reference: str | None = None,
) -> ValidatedTransferEvidence:
    merchant_reference = obligation.get("merchant_reference")
    if not isinstance(merchant_reference, str) or not merchant_reference:
        raise PayoutObservationMismatch(payout_id, "merchant_reference_missing")
    if observation.reference != merchant_reference:
        raise PayoutObservationMismatch(payout_id, "merchant_reference")

    amount_ngwee = obligation.get("amount_ngwee")
    if not isinstance(amount_ngwee, int) or isinstance(amount_ngwee, bool):
        raise PayoutObservationMismatch(payout_id, "intended_amount_missing")
    if not isinstance(observation.amount_major, str):
        raise PayoutObservationMismatch(payout_id, "amount_missing")
    try:
        observed_amount = major_str_to_ngwee(
            observation.amount_major,
            currency=str(obligation.get("currency", "")),
        )
    except (TypeError, ValueError) as exc:
        raise PayoutObservationMismatch(payout_id, "amount_invalid") from exc
    if observed_amount != amount_ngwee:
        raise PayoutObservationMismatch(payout_id, "amount")

    currency = obligation.get("currency")
    if not isinstance(currency, str) or observation.currency != currency:
        raise PayoutObservationMismatch(payout_id, "currency")

    debit_account_id = obligation.get("debit_account_id")
    if not isinstance(debit_account_id, str) or not debit_account_id:
        raise PayoutObservationMismatch(payout_id, "intended_debit_account_missing")
    if observation.debit_account_id != debit_account_id:
        reason = (
            "debit_account_missing"
            if observation.debit_account_id is None
            else "debit_account"
        )
        raise PayoutObservationMismatch(payout_id, reason)

    destination = obligation.get("destination")
    observed_destination = _observed_destination(observation.destination)
    if not isinstance(destination, dict):
        raise PayoutObservationMismatch(payout_id, "intended_destination_missing")
    if observed_destination is None:
        raise PayoutObservationMismatch(payout_id, "destination_missing")
    if observed_destination != destination:
        raise PayoutObservationMismatch(payout_id, "destination")

    provider_reference = observation.provider_reference
    if not isinstance(provider_reference, str) or not provider_reference:
        raise PayoutObservationMismatch(payout_id, "provider_reference_missing")
    if expected_provider_reference and provider_reference != expected_provider_reference:
        raise PayoutObservationMismatch(payout_id, "provider_reference")

    return ValidatedTransferEvidence(
        merchant_reference=merchant_reference,
        provider_reference=provider_reference,
        amount_ngwee=observed_amount,
        currency=currency,
        debit_account_id=debit_account_id,
        destination=observed_destination,
    )
