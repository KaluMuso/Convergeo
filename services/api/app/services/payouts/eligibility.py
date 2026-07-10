"""Payout eligibility — released vendor_payable balance and velocity caps."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Protocol, cast

from app.errors import AppError
from app.services.kyc.caps import (
    VendorCapLimits,
    enforce_payout_velocity,
    load_vendor_quota,
)
from app.services.ledger.engine import account_balance_ngwee, resolve_account_id
from app.services.ledger.templates import AccountRef

PENDING_RESERVE_STATUSES = frozenset({"pending", "processing"})

_vendor_locks: dict[str, threading.Lock] = {}
_registry_lock = threading.Lock()


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


@dataclass(frozen=True, slots=True)
class EligibilitySnapshot:
    vendor_id: str
    ledger_balance_ngwee: int
    released_balance_ngwee: int
    reserved_ngwee: int
    available_ngwee: int


def _vendor_lock(vendor_id: str) -> threading.Lock:
    with _registry_lock:
        lock = _vendor_locks.get(vendor_id)
        if lock is None:
            lock = threading.Lock()
            _vendor_locks[vendor_id] = lock
        return lock


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


def vendor_payable_balance_ngwee(vendor_id: str) -> int:
    """Signed ledger balance for vendor_payable (negative = credit / owed to vendor)."""
    account_id = resolve_account_id(AccountRef("vendor_payable", vendor_id))
    return account_balance_ngwee(account_id)


def released_balance_ngwee(vendor_id: str) -> int:
    """Credit balance available for payout (ngwee owed to vendor)."""
    balance = vendor_payable_balance_ngwee(vendor_id)
    return max(0, -balance)


def _reserved_payout_ngwee(service_client: ServiceRoleClient, vendor_id: str) -> int:
    response = (
        service_client.client.table("payouts")
        .select("amount_ngwee")
        .eq("vendor_id", vendor_id)
        .in_("status", list(PENDING_RESERVE_STATUSES))
        .execute()
    )
    rows = _rows(response)
    return sum(int(row.get("amount_ngwee", 0)) for row in rows)


def compute_eligibility(
    service_client: ServiceRoleClient,
    vendor_id: str,
) -> EligibilitySnapshot:
    balance = vendor_payable_balance_ngwee(vendor_id)
    released = max(0, -balance)
    reserved = _reserved_payout_ngwee(service_client, vendor_id)
    available = max(0, released - reserved)
    return EligibilitySnapshot(
        vendor_id=vendor_id,
        ledger_balance_ngwee=balance,
        released_balance_ngwee=released,
        reserved_ngwee=reserved,
        available_ngwee=available,
    )


def load_vendor_cap_limits(
    service_client: ServiceRoleClient,
    vendor_id: str,
) -> VendorCapLimits:
    response = (
        service_client.client.table("vendors")
        .select("id, kyc_tier")
        .eq("id", vendor_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(
            code="vendor_not_found",
            message=f"Vendor {vendor_id} not found",
            http_status=404,
        )
    tier = int(row.get("kyc_tier") or 1)
    quota = load_vendor_quota(service_client, tier)
    return VendorCapLimits(
        vendor_id=vendor_id,
        kyc_tier=tier,
        quota=quota,
        cod_cap_ngwee=0,
        listing_count=0,
        order_count=0,
    )


def check_payout_eligible_unlocked(
    service_client: ServiceRoleClient,
    *,
    vendor_id: str,
    amount_ngwee: int,
) -> EligibilitySnapshot:
    """Balance + velocity check (caller must hold vendor lock for race safety)."""
    if amount_ngwee <= 0:
        raise AppError(
            code="invalid_amount",
            message="Payout amount must be positive",
            http_status=400,
        )

    snapshot = compute_eligibility(service_client, vendor_id)
    if amount_ngwee > snapshot.available_ngwee:
        raise AppError(
            code="insufficient_released_balance",
            message="Payout exceeds released vendor balance",
            http_status=409,
            details={
                "requested_ngwee": amount_ngwee,
                "available_ngwee": snapshot.available_ngwee,
                "released_balance_ngwee": snapshot.released_balance_ngwee,
                "reserved_ngwee": snapshot.reserved_ngwee,
            },
        )
    limits = load_vendor_cap_limits(service_client, vendor_id)
    enforce_payout_velocity(limits, amount_ngwee, service_client)
    return snapshot


def assert_payout_eligible(
    service_client: ServiceRoleClient,
    *,
    vendor_id: str,
    amount_ngwee: int,
) -> EligibilitySnapshot:
    """Race-safe balance + velocity check under a per-vendor lock."""
    with _vendor_lock(vendor_id):
        return check_payout_eligible_unlocked(
            service_client,
            vendor_id=vendor_id,
            amount_ngwee=amount_ngwee,
        )


def check_velocity_deferred(
    service_client: ServiceRoleClient,
    *,
    vendor_id: str,
    amount_ngwee: int,
) -> bool:
    """Return True when velocity caps would block this payout (defer, do not error)."""
    limits = load_vendor_cap_limits(service_client, vendor_id)
    try:
        enforce_payout_velocity(limits, amount_ngwee, service_client)
    except AppError as exc:
        if exc.code == "payout_velocity_exceeded":
            return True
        raise
    return False
