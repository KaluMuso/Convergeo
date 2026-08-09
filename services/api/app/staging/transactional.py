"""Staging transactional fixture driver — post-seed order/payment states.

Static catalogue rows are seeded by ``scripts/seed_staging.py``. This module
drives supported checkout/order/payment states through application service
boundaries after an exact-SHA staging deployment.

States that require a live Lenco sandbox collection or external webhook replay
are classified ``external`` and are never fabricated via inconsistent direct
ledger inserts.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, Literal

from app.core.env_guards import StagingIsolationError, assert_staging_project_target
from app.staging.synthetic_contract import (
    SEED_PREFIX,
    guard_seed_targets,
    persona_by_key,
    product_fixture,
)

TransactionalMode = Literal["plan", "apply"]


class TransactionalState(StrEnum):
    PREPAID_AWAITING_PAYMENT = "prepaid_awaiting_payment"
    PAYMENT_FAILED = "payment_failed"
    PAYMENT_EXPIRED = "payment_expired"
    COD_PLACED = "cod_placed"
    PROCESSING = "processing"
    DELIVERED = "delivered"
    RETURN_ELIGIBLE = "return_eligible"
    DISPUTE_HELD = "dispute_held"


@dataclass(frozen=True, slots=True)
class StateSpec:
    state: TransactionalState
    delivery: Literal["service", "external"]
    summary: str
    requires_payment_success: bool = False


STATE_SPECS: dict[TransactionalState, StateSpec] = {
    TransactionalState.PREPAID_AWAITING_PAYMENT: StateSpec(
        state=TransactionalState.PREPAID_AWAITING_PAYMENT,
        delivery="service",
        summary=(
            "Checkout group + placed prepaid order + payment row in pending "
            "via checkout/payment services (no ledger post)."
        ),
    ),
    TransactionalState.PAYMENT_FAILED: StateSpec(
        state=TransactionalState.PAYMENT_FAILED,
        delivery="service",
        summary="Apply payment FAILED transition through apply_payment_status.",
    ),
    TransactionalState.PAYMENT_EXPIRED: StateSpec(
        state=TransactionalState.PAYMENT_EXPIRED,
        delivery="service",
        summary="Apply payment EXPIRED transition through apply_payment_status.",
    ),
    TransactionalState.COD_PLACED: StateSpec(
        state=TransactionalState.COD_PLACED,
        delivery="service",
        summary="COD checkout group + placed order via checkout service boundary.",
    ),
    TransactionalState.PROCESSING: StateSpec(
        state=TransactionalState.PROCESSING,
        delivery="external",
        summary=(
            "Requires prepaid payment success (Lenco sandbox or payment mock "
            "harness) before vendor CONFIRM transition."
        ),
        requires_payment_success=True,
    ),
    TransactionalState.DELIVERED: StateSpec(
        state=TransactionalState.DELIVERED,
        delivery="external",
        summary=(
            "Requires payment success + guarded order transitions through "
            "fulfilment chain (vendor actions or test harness)."
        ),
        requires_payment_success=True,
    ),
    TransactionalState.RETURN_ELIGIBLE: StateSpec(
        state=TransactionalState.RETURN_ELIGIBLE,
        delivery="external",
        summary=(
            "Requires delivered prepaid order within return window — drive via "
            "post-delivery harness after payment success."
        ),
        requires_payment_success=True,
    ),
    TransactionalState.DISPUTE_HELD: StateSpec(
        state=TransactionalState.DISPUTE_HELD,
        delivery="external",
        summary=(
            "Requires escrow-funded order + dispute open — use dispute service "
            "harness; never insert ledger rows directly."
        ),
        requires_payment_success=True,
    ),
}

CHECKOUT_IDEMPOTENCY_PREFIX: Final = f"{SEED_PREFIX}-txn-"


def assert_transactional_safe(
    *,
    project_ref: str | None,
    api_host: str = "",
    require_exact_project: bool = False,
) -> None:
    guard_seed_targets(
        supabase_url="",
        db_url="",
        api_host=api_host,
        staging_project_id=project_ref or "",
        require_exact_project=require_exact_project,
    )
    if require_exact_project:
        assert_staging_project_target(project_ref, require_exact=True)


def plan_state(state: TransactionalState) -> dict[str, Any]:
    spec = STATE_SPECS[state]
    customer = persona_by_key("CUSTOMER_A")
    listing = product_fixture("PRODUCT_B").listings[0]
    vendor = persona_by_key(listing.vendor_key)
    return {
        "state": state.value,
        "delivery": spec.delivery,
        "summary": spec.summary,
        "requires_payment_success": spec.requires_payment_success,
        "customer_user_id": customer.user_id,
        "vendor_id": vendor.vendor_id,
        "listing_id": listing.listing_id,
        "idempotency_prefix": CHECKOUT_IDEMPOTENCY_PREFIX,
        "notes": (
            "Apply mode invokes checkout/payment services when delivery=service. "
            "delivery=external states must be produced by the Lenco sandbox or an "
            "explicit payment-mock harness after exact-SHA staging deployment."
        ),
    }


def classify_state(state: str) -> StateSpec:
    try:
        return STATE_SPECS[TransactionalState(state)]
    except ValueError as exc:
        raise StagingIsolationError(f"unknown transactional state: {state}") from exc


def is_service_drivable(state: TransactionalState) -> bool:
    return STATE_SPECS[state].delivery == "service"


__all__ = [
    "CHECKOUT_IDEMPOTENCY_PREFIX",
    "STATE_SPECS",
    "TransactionalMode",
    "TransactionalState",
    "assert_transactional_safe",
    "classify_state",
    "is_service_drivable",
    "plan_state",
]
