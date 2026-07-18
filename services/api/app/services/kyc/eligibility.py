"""Backend-derived vendor KYC eligibility (MR-D02 / VEND-01).

A bare ``vendors.kyc_tier`` must never unlock verified, wholesale, or other
privileged capabilities. Callers must use :func:`resolve_vendor_eligibility`
(or the batch helper) so capability checks require an approved ``kyc_records``
trail.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from app.errors import AppError
from app.services.kyc.state_machine import ServiceRoleClient

APPROVED_STATUS = "approved"
PRIVILEGED_VENDOR_STATUSES = frozenset({"active", "pending_kyc"})


@dataclass(frozen=True, slots=True)
class VendorKycEligibility:
    vendor_id: str
    vendor_status: str
    stored_kyc_tier: int | None
    effective_tier: int | None
    kyc_record_id: str | None
    kyc_record_status: str | None
    is_auditable_approved: bool
    orphaned_tier: bool
    can_wholesale: bool
    can_organise_events: bool
    is_directory_verified: bool
    preferred_badge: bool

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "effective_tier": self.effective_tier,
            "is_auditable_approved": self.is_auditable_approved,
            "orphaned_tier": self.orphaned_tier,
            "capabilities": {
                "wholesale": self.can_wholesale,
                "organise_events": self.can_organise_events,
                "directory_verified": self.is_directory_verified,
            },
        }


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


def _parse_tier(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value in (1, 2, 3) else None
    if isinstance(value, float):
        as_int = int(value)
        return as_int if as_int in (1, 2, 3) else None
    if isinstance(value, str) and value.strip():
        try:
            as_int = int(value.strip())
        except ValueError:
            return None
        return as_int if as_int in (1, 2, 3) else None
    return None


def _load_vendor_row(
    service_client: ServiceRoleClient,
    vendor_id: str,
) -> dict[str, Any]:
    response = (
        service_client.client.table("vendors")
        .select("id, status, kyc_tier, preferred_badge")
        .eq("id", vendor_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(code="not_found", message="Vendor not found", http_status=404)
    return row


def _load_best_approved_record(
    service_client: ServiceRoleClient,
    vendor_id: str,
) -> dict[str, Any] | None:
    """Highest-tier approved KYC record for the vendor, if any."""
    response = (
        service_client.client.table("kyc_records")
        .select("id, vendor_id, tier, status, reviewed_by, reviewed_at, decision_reason")
        .eq("vendor_id", vendor_id)
        .eq("status", APPROVED_STATUS)
        .order("tier", desc=True)
        .limit(1)
        .execute()
    )
    rows = _rows(response)
    return rows[0] if rows else None


@dataclass(slots=True)
class _ClientAdapter:
    """Adapt a raw Supabase client to the ServiceRoleClient protocol."""

    client: Any


def load_approved_tiers_by_vendor(
    service_client: ServiceRoleClient,
    vendor_ids: list[str],
) -> dict[str, int]:
    """Batch map vendor_id → highest approved KYC tier (auditable only)."""
    if not vendor_ids:
        return {}
    unique_ids = list(dict.fromkeys(vendor_ids))
    response = (
        service_client.client.table("kyc_records")
        .select("vendor_id, tier, status")
        .in_("vendor_id", unique_ids)
        .eq("status", APPROVED_STATUS)
        .execute()
    )
    best: dict[str, int] = {}
    for row in _rows(response):
        vendor_id = str(row["vendor_id"])
        tier = _parse_tier(row.get("tier"))
        if tier is None:
            continue
        current = best.get(vendor_id)
        if current is None or tier > current:
            best[vendor_id] = tier
    return best


def load_approved_tiers_for_client(client: Any, vendor_ids: list[str]) -> dict[str, int]:
    """Batch helper for routers that hold a raw Supabase client."""
    return load_approved_tiers_by_vendor(_ClientAdapter(client), vendor_ids)


def build_eligibility_from_rows(
    *,
    vendor: dict[str, Any],
    approved_record: dict[str, Any] | None,
) -> VendorKycEligibility:
    vendor_id = str(vendor["id"])
    vendor_status = str(vendor.get("status") or "")
    stored_tier = _parse_tier(vendor.get("kyc_tier"))
    preferred_badge = bool(vendor.get("preferred_badge"))

    approved_tier: int | None = None
    record_id: str | None = None
    record_status: str | None = None
    if approved_record is not None:
        approved_tier = _parse_tier(approved_record.get("tier"))
        record_id = str(approved_record["id"])
        record_status = str(approved_record.get("status") or "")

    is_auditable_approved = (
        approved_record is not None
        and record_status == APPROVED_STATUS
        and approved_tier is not None
    )
    orphaned_tier = stored_tier is not None and not is_auditable_approved
    effective_tier = approved_tier if is_auditable_approved else None

    status_ok_for_privileged = vendor_status in PRIVILEGED_VENDOR_STATUSES
    can_wholesale = (
        is_auditable_approved
        and status_ok_for_privileged
        and effective_tier is not None
        and effective_tier >= 2
    )
    can_organise_events = (
        is_auditable_approved
        and vendor_status == "active"
        and effective_tier is not None
        and effective_tier >= 1
    )
    is_directory_verified = preferred_badge or (
        is_auditable_approved and effective_tier is not None and effective_tier >= 2
    )

    return VendorKycEligibility(
        vendor_id=vendor_id,
        vendor_status=vendor_status,
        stored_kyc_tier=stored_tier,
        effective_tier=effective_tier,
        kyc_record_id=record_id,
        kyc_record_status=record_status,
        is_auditable_approved=is_auditable_approved,
        orphaned_tier=orphaned_tier,
        can_wholesale=can_wholesale,
        can_organise_events=can_organise_events,
        is_directory_verified=is_directory_verified,
        preferred_badge=preferred_badge,
    )


def resolve_vendor_eligibility(
    service_client: ServiceRoleClient,
    vendor_id: str,
    *,
    vendor_row: dict[str, Any] | None = None,
) -> VendorKycEligibility:
    vendor = vendor_row if vendor_row is not None else _load_vendor_row(service_client, vendor_id)
    if str(vendor.get("id")) != vendor_id and "id" in vendor:
        # Allow callers that already loaded the row keyed by id.
        pass
    approved = _load_best_approved_record(service_client, vendor_id)
    return build_eligibility_from_rows(vendor=vendor, approved_record=approved)


def require_wholesale_eligible(eligibility: VendorKycEligibility) -> None:
    if not eligibility.can_wholesale:
        raise AppError(
            code="wholesale_requires_t2",
            message="Wholesale listings require T2 verification or higher",
            http_status=403,
            details={
                "message_key": "vendor.listings.errors.wholesale_requires_t2",
                "orphaned_tier": eligibility.orphaned_tier,
                "effective_tier": eligibility.effective_tier,
                "stored_kyc_tier": eligibility.stored_kyc_tier,
            },
        )


def require_events_eligible(eligibility: VendorKycEligibility) -> None:
    if not eligibility.can_organise_events:
        raise AppError(
            code="kyc_required",
            message="Active KYC verification is required to manage events",
            http_status=403,
            details={
                "message_key": "vendor.events.errors.kyc_required",
                "orphaned_tier": eligibility.orphaned_tier,
                "effective_tier": eligibility.effective_tier,
            },
        )


def cap_tier_for_quotas(eligibility: VendorKycEligibility) -> int:
    """Quota tier derived from auditable approval only (orphans → T1 baseline)."""
    if eligibility.effective_tier is not None:
        return eligibility.effective_tier
    return 1
