"""Billing seam for vendor plans — deliberately NOT implemented.

Scope (founder, 2026-11-13): record plan assignment only; no money moves.
A future pebble adds a Lenco mobile-money subscription charge behind
``feature_flags.paid_tiers``. It should:

* implement :class:`SubscriptionChargeGateway` in the payments adapter (Lenco
  ``reference`` = ``sub-{assignment_id}-{yyyymm}``, charset ``[-._A-Za-z0-9]``);
* write ``vendor_plan_assignments.billing_status / paid_through /
  billing_reference`` only through a guarded, audited transition function
  (CLAUDE.md convention 4), idempotent under Lenco webhook retries;
* keep amounts as integer ngwee end to end (the Lenco adapter converts with
  ``Decimal`` at the boundary).

Until then :func:`get_subscription_gateway` returns a gateway that refuses, so
nothing can charge a vendor by accident.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.errors import AppError


@dataclass(frozen=True, slots=True)
class SubscriptionCharge:
    vendor_id: str
    plan_key: str
    amount_ngwee: int
    reference: str


class SubscriptionChargeGateway(Protocol):
    def request_charge(self, charge: SubscriptionCharge) -> str:
        """Start a charge; return the provider reference. Must be idempotent."""
        ...


class BillingNotConfigured:
    def request_charge(self, charge: SubscriptionCharge) -> str:
        raise AppError(
            code="billing_not_available",
            message="Plan billing is not available yet",
            http_status=409,
            details={"message_key": "vendor.plans.billingUnavailable"},
        )


def get_subscription_gateway() -> SubscriptionChargeGateway:
    return BillingNotConfigured()
