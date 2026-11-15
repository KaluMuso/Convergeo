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
  ``Decimal`` at the boundary);
* never charge a plan fee while the business's free trial runs: call
  :func:`plan_fee_due_ngwee` (or SQL ``vendor_plan_fee_accrues``) first.
  :class:`TrialAwareGateway` enforces this around any real gateway.

Until then :func:`get_subscription_gateway` returns a gateway that refuses, so
nothing can charge a vendor by accident.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

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


DEFAULT_ANNUAL_DISCOUNT_PCT = 15
TRIAL_MONTHS = 1


def annual_price_ngwee(monthly_ngwee: int, discount_pct: int) -> int:
    """12 x monthly x (1 - pct/100), integer ngwee, rounded down. Integer math only."""
    if monthly_ngwee < 0:
        raise ValueError("monthly price must be >= 0")
    if not 0 <= discount_pct <= 90:
        raise ValueError("discount must be between 0 and 90 percent")
    return (monthly_ngwee * 12 * (100 - discount_pct)) // 100


def parse_ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def add_months(at: datetime, months: int) -> datetime:
    """Calendar months (Postgres ``interval 'n months'`` semantics: clamp the day)."""
    month_index = at.month - 1 + months
    year = at.year + month_index // 12
    month = month_index % 12 + 1
    days_in_month = [
        31,
        29 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 28,
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ][month - 1]
    return at.replace(year=year, month=month, day=min(at.day, days_in_month))


def trial_end_for_signup(signed_up_at: datetime) -> datetime:
    return add_months(signed_up_at, TRIAL_MONTHS)


def in_trial(trial_ends_at: datetime | None, *, at: datetime | None = None) -> bool:
    if trial_ends_at is None:
        return False
    return (at or datetime.now(UTC)) < trial_ends_at


def plan_fee_due_ngwee(
    monthly_ngwee: int, trial_ends_at: datetime | None, *, at: datetime | None = None
) -> int:
    """The plan fee that accrues at ``at``: zero during the free trial."""
    if in_trial(trial_ends_at, at=at):
        return 0
    return monthly_ngwee


class TrialAwareGateway:
    """Wraps a real gateway: refuses any plan charge while the trial runs."""

    def __init__(self, inner: SubscriptionChargeGateway, trial_ends_at: datetime | None) -> None:
        self._inner = inner
        self._trial_ends_at = trial_ends_at

    def request_charge(self, charge: SubscriptionCharge) -> str:
        if in_trial(self._trial_ends_at):
            raise AppError(
                code="plan_in_trial",
                message="No plan fee accrues during the free trial",
                http_status=409,
                details={"message_key": "vendor.plans.trialNoCharge"},
            )
        return self._inner.request_charge(charge)


def get_subscription_gateway(trial_ends_at: datetime | None = None) -> SubscriptionChargeGateway:
    return TrialAwareGateway(BillingNotConfigured(), trial_ends_at)
