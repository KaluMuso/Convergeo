"""Pre-payout /resolve name-match against KYC momo legal name."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, cast

from app.errors import AppError
from app.services.kyc.name_match import score_name_match
from app.services.notifications.dedupe import enqueue_outbox_row
from app.services.payments.base import ResolveAccountRequest, ResolveAccountResult
from app.services.payments.lenco.models import (
    LencoResolveBankAccountRequest,
    LencoResolveBankAccountResponse,
)


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class ResolveAccountFn(Protocol):
    async def __call__(self, request: ResolveAccountRequest) -> ResolveAccountResult: ...


class ResolveBankAccountFn(Protocol):
    async def __call__(
        self,
        request: LencoResolveBankAccountRequest,
    ) -> LencoResolveBankAccountResponse: ...


@dataclass(frozen=True, slots=True)
class VendorPayoutProfile:
    vendor_id: str
    owner_user_id: str
    phone: str
    operator: str
    legal_name: str
    rail: str
    account_number: str | None = None
    bank_id: str | None = None


@dataclass(frozen=True, slots=True)
class ResolveCheckResult:
    matched: bool
    resolved_name: str | None
    legal_name: str
    match_score: float
    snapshot: dict[str, Any]
    held: bool


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


def load_vendor_payout_profile(
    service_client: ServiceRoleClient,
    vendor_id: str,
) -> VendorPayoutProfile:
    vendor_resp = (
        service_client.client.table("vendors")
        .select("id, owner_user_id, kyc_tier")
        .eq("id", vendor_id)
        .maybe_single()
        .execute()
    )
    vendor = _single_row(vendor_resp)
    if vendor is None:
        raise AppError(
            code="vendor_not_found",
            message=f"Vendor {vendor_id} not found",
            http_status=404,
        )

    kyc_resp = (
        service_client.client.table("kyc_records")
        .select("momo_name_match, status")
        .eq("vendor_id", vendor_id)
        .eq("status", "approved")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    kyc_rows = _rows(kyc_resp)
    if not kyc_rows:
        raise AppError(
            code="kyc_not_approved",
            message="Vendor has no approved KYC record for payout",
            http_status=409,
        )

    momo = kyc_rows[0].get("momo_name_match")
    if not isinstance(momo, dict):
        raise AppError(
            code="kyc_incomplete",
            message="Approved KYC is missing momo_name_match",
            http_status=409,
        )

    phone = str(momo.get("phone", "")).strip()
    operator = str(momo.get("operator", "mtn")).strip().lower()
    legal_name = str(momo.get("legal_name", "")).strip()
    if not phone or not legal_name:
        raise AppError(
            code="kyc_incomplete",
            message="KYC momo_name_match missing phone or legal_name",
            http_status=409,
        )

    rail = operator if operator in {"mtn", "airtel", "zamtel"} else "mtn"
    return VendorPayoutProfile(
        vendor_id=vendor_id,
        owner_user_id=str(vendor["owner_user_id"]),
        phone=phone,
        operator=operator,
        legal_name=legal_name,
        rail=rail,
        account_number=(
            momo.get("account_number") if isinstance(momo.get("account_number"), str) else None
        ),
        bank_id=momo.get("bank_id") if isinstance(momo.get("bank_id"), str) else None,
    )


def _build_snapshot(
    *,
    profile: VendorPayoutProfile,
    resolved_name: str | None,
    match_score: float,
    matched: bool,
    held: bool,
    hold_reason: str | None = None,
    raw: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "phone": profile.phone,
        "operator": profile.operator,
        "rail": profile.rail,
        "legal_name": profile.legal_name,
        "resolved_name": resolved_name,
        "match_score": match_score,
        "matched": matched,
        "held": held,
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    if hold_reason:
        snapshot["hold_reason"] = hold_reason
    if raw:
        snapshot["raw"] = raw
    return snapshot


async def run_resolve_name_check(
    profile: VendorPayoutProfile,
    *,
    resolve_account: ResolveAccountFn,
    resolve_bank_account: ResolveBankAccountFn | None = None,
) -> ResolveCheckResult:
    """Compare Lenco /resolve account name to KYC legal name."""
    if profile.rail in {"mtn", "airtel", "zamtel"}:
        result = await resolve_account(
            ResolveAccountRequest(
                phone=profile.phone,
                operator=profile.operator,
                country="zm",
            )
        )
        resolved_name = result.account_name
        score, matched = score_name_match(resolved_name, profile.legal_name)
        held = not matched
        snapshot = _build_snapshot(
            profile=profile,
            resolved_name=resolved_name,
            match_score=score,
            matched=matched,
            held=held,
            hold_reason="name_mismatch" if held else None,
            raw=result.raw if isinstance(result.raw, dict) else None,
        )
        return ResolveCheckResult(
            matched=matched,
            resolved_name=resolved_name,
            legal_name=profile.legal_name,
            match_score=score,
            snapshot=snapshot,
            held=held,
        )

    if profile.account_number and profile.bank_id and resolve_bank_account is not None:
        bank_result = await resolve_bank_account(
            LencoResolveBankAccountRequest(
                account_number=profile.account_number,
                bank_id=profile.bank_id,
                country="zm",
            )
        )
        data = bank_result.data
        bank_resolved_name: str | None = data.account_name if data is not None else None
        score, matched = score_name_match(bank_resolved_name, profile.legal_name)
        held = not matched
        snapshot = _build_snapshot(
            profile=profile,
            resolved_name=bank_resolved_name,
            match_score=score,
            matched=matched,
            held=held,
            hold_reason="name_mismatch" if held else None,
            raw=bank_result.model_dump() if hasattr(bank_result, "model_dump") else None,
        )
        return ResolveCheckResult(
            matched=matched,
            resolved_name=bank_resolved_name,
            legal_name=profile.legal_name,
            match_score=score,
            snapshot=snapshot,
            held=held,
        )

    raise AppError(
        code="unsupported_rail",
        message=f"Payout rail {profile.rail!r} is not supported",
        http_status=400,
    )


def notify_payout_held(
    service_client: ServiceRoleClient,
    *,
    payout_id: str,
    vendor_id: str,
    owner_user_id: str,
    snapshot: dict[str, Any],
) -> None:
    """Enqueue vendor notification for a held payout (name mismatch)."""
    enqueue_outbox_row(
        service_client.client,
        event_type="payout_held",
        entity_id=payout_id,
        channel="email",
        template="payout_held",
        payload={
            "recipient_id": owner_user_id,
            "vendor_id": vendor_id,
            "payout_id": payout_id,
            "hold_reason": snapshot.get("hold_reason", "name_mismatch"),
            "resolved_name": snapshot.get("resolved_name"),
            "legal_name": snapshot.get("legal_name"),
        },
    )
