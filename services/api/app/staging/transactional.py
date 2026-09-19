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
from uuid import uuid4

from app.core.env_guards import StagingIsolationError, assert_staging_project_target
from app.staging.synthetic_contract import (
    SEED_PREFIX,
    VENDOR_LOCATIONS,
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
    "COD_ADDRESS_ID",
    "COD_CHECKOUT_GROUP_ID",
    "COD_IDEMPOTENCY_KEY",
    "COD_ORDER_QTY",
    "STATE_SPECS",
    "CodPlacedFixture",
    "TransactionalMode",
    "TransactionalState",
    "apply_cod_placed",
    "assert_transactional_safe",
    "classify_state",
    "cod_placed_fixture",
    "is_service_drivable",
    "plan_state",
]


# ── COD placed order — the one service-drivable transactional fixture ──────────
#
# `cod_placed` is the only state a synthetic run can reach without a payment
# provider: COD is exempt from the prepaid-payment-success gate
# (`_available_vendor_actions` -> `prepaid_unpaid = (not cod) and (not paid)`),
# so the order is immediately fulfilment-valid and the vendor can walk it
# placed -> confirmed -> processing -> shipped through the real guarded
# transitions. Every other transactional state stays `external`.
#
# Identity is deterministic and lives inside the reserved synthetic namespace,
# so `build_cleanup_sql()`'s existing `{SEED_PREFIX}-txn-%` branch already
# removes it between runs — this module supplies the producer that namespace was
# always written for.
#
# PRODUCT_B is chosen deliberately: it is the only catalogue fixture with a
# SINGLE listing, owned by APPROVED_VENDOR_A — the same persona the vendor
# portal specs authenticate as. A multi-listing product would make the receiving
# vendor depend on buy-box selection, which is not deterministic.

COD_CHECKOUT_GROUP_ID: Final = "c0d00000-0000-4000-8000-000000000001"
COD_ADDRESS_ID: Final = "ad000000-0000-4000-8000-000000000001"
COD_IDEMPOTENCY_KEY: Final = f"{CHECKOUT_IDEMPOTENCY_PREFIX}cod-placed"
COD_ORDER_QTY: Final = 1


@dataclass(frozen=True, slots=True)
class CodPlacedFixture:
    """Deterministic identity of the seeded COD order."""

    customer_user_id: str
    vendor_id: str
    listing_id: str
    product_slug: str
    product_name: str
    qty: int
    unit_price_ngwee: int
    subtotal_ngwee: int
    checkout_group_id: str
    address_id: str
    idempotency_key: str


def cod_placed_fixture() -> CodPlacedFixture:
    """Resolve the COD fixture from the canonical contract (no DB access)."""
    customer = persona_by_key("CUSTOMER_A")
    product = product_fixture("PRODUCT_B")
    if len(product.listings) != 1:
        raise StagingIsolationError(
            "PRODUCT_B must keep exactly one listing so the receiving vendor is deterministic"
        )
    listing = product.listings[0]
    if listing.vendor_key != "APPROVED_VENDOR_A":
        raise StagingIsolationError(
            "the COD fixture listing must belong to APPROVED_VENDOR_A — the persona the "
            "vendor portal specs authenticate as"
        )
    vendor = persona_by_key(listing.vendor_key)
    if vendor.vendor_id is None:
        raise StagingIsolationError("APPROVED_VENDOR_A has no vendor_id in the contract")
    return CodPlacedFixture(
        customer_user_id=customer.user_id,
        vendor_id=vendor.vendor_id,
        listing_id=listing.listing_id,
        product_slug=product.product_slug,
        product_name=product.product_name,
        qty=COD_ORDER_QTY,
        unit_price_ngwee=listing.price_ngwee,
        subtotal_ngwee=listing.price_ngwee * COD_ORDER_QTY,
        checkout_group_id=COD_CHECKOUT_GROUP_ID,
        address_id=COD_ADDRESS_ID,
        idempotency_key=COD_IDEMPOTENCY_KEY,
    )


def apply_cod_placed(
    client: Any, *, landmark: str | None = None, phone: str | None = None
) -> dict[str, Any]:
    """Create the COD `placed` order through the real order-creation service.

    Nothing here writes an order, an order item or a status by hand: the two
    direct inserts are a delivery address and a pending checkout session — the
    inputs a real buyer's checkout would have produced — and the order itself is
    created by `create_orders_atomic`, the same guarded, transactional service
    the `POST /orders` route calls. The order therefore starts in `placed` with a
    real commission snapshot and a real audit trail, and every later transition
    must go through `transition_order`.

    Idempotent: a completed checkout group carrying the same idempotency key is
    replayed rather than duplicated.
    """
    # Imported lazily: this module is also imported by the plan-only CLI and by
    # the E2E fixture generator, which must stay importable without dragging in
    # the order-service dependency graph.
    from app.services.orders.create import (
        CartLineInput,
        VendorFulfilmentInput,
        create_orders_atomic,
    )
    from app.services.stock.claim import claim_reservation, load_reservation_ttl_minutes

    fixture = cod_placed_fixture()
    # Landmark + phone default to the same canonical values the generated E2E
    # contract publishes as SEED.address, so the fixture address matches what a
    # spec would have typed at checkout (Zambia landmark addressing).
    location = next(loc for loc in VENDOR_LOCATIONS if loc.vendor_key == "APPROVED_VENDOR_A")
    resolved_landmark = landmark or location.landmark
    resolved_phone = phone or persona_by_key("CUSTOMER_A").phone

    client.table("addresses").upsert(
        {
            "id": fixture.address_id,
            "user_id": fixture.customer_user_id,
            "label": f"{SEED_PREFIX} synthetic delivery address",
            "landmark": resolved_landmark,
            "phone": resolved_phone,
        }
    ).execute()

    existing = (
        client.table("checkout_groups")
        .select("id, status")
        .eq("id", fixture.checkout_group_id)
        .maybe_single()
        .execute()
    )
    existing_group = getattr(existing, "data", None)
    if not isinstance(existing_group, dict):
        client.table("checkout_groups").insert(
            {
                "id": fixture.checkout_group_id,
                "customer_id": fixture.customer_user_id,
                "idempotency_key": fixture.idempotency_key,
                "subtotal_ngwee": fixture.subtotal_ngwee,
                "delivery_fee_ngwee": 0,
                "total_ngwee": fixture.subtotal_ngwee,
                "status": "pending",
            }
        ).execute()

    if not isinstance(existing_group, dict) or existing_group.get("status") != "completed":
        reservation_response = (
            client.table("stock_reservations")
            .select("qty, location_id")
            .eq("listing_id", fixture.listing_id)
            .eq("checkout_group_id", fixture.checkout_group_id)
            .maybe_single()
            .execute()
        )
        reservation = getattr(reservation_response, "data", None)
        if isinstance(reservation, dict):
            # Claiming again would decrement stock twice. Leave expiry validation
            # and consumption of the existing hold to create_orders_atomic.
            if (
                reservation.get("qty") != fixture.qty
                or reservation.get("location_id") != location.location_id
            ):
                raise StagingIsolationError(
                    "COD fixture reservation does not match its stock binding"
                )
        else:
            claimed = claim_reservation(
                listing_id=fixture.listing_id,
                checkout_group_id=fixture.checkout_group_id,
                qty=fixture.qty,
                location_id=location.location_id,
                ttl_minutes=load_reservation_ttl_minutes(),
            )
            if not claimed.claimed or claimed.skipped:
                raise StagingIsolationError(
                    "COD fixture tracked-stock reservation was not acquired"
                )

    result = create_orders_atomic(
        client=client,
        customer_id=fixture.customer_user_id,
        session_id=fixture.checkout_group_id,
        idempotency_key=fixture.idempotency_key,
        payment_method="cod",
        cart_lines=[
            CartLineInput(
                cart_item_id=str(uuid4()),
                listing_id=fixture.listing_id,
                vendor_id=fixture.vendor_id,
                qty=fixture.qty,
                unit_price_ngwee=fixture.unit_price_ngwee,
                title_snapshot=fixture.product_name,
            )
        ],
        vendor_groups=[
            VendorFulfilmentInput(
                vendor_id=fixture.vendor_id,
                # `ship` is only reachable from processing + delivery
                # (services/api/app/services/orders/state.py TRANSITION_TABLE),
                # so the fixture must be a DELIVERY order, not pickup.
                fulfilment="delivery",
                delivery_zone=None,
                delivery_fee_ngwee=0,
                subtotal_ngwee=fixture.subtotal_ngwee,
            )
        ],
        address_id=fixture.address_id,
    )

    return {
        "state": TransactionalState.COD_PLACED.value,
        "checkout_group_id": result.checkout_group_id,
        "idempotency_key": result.idempotency_key,
        "replayed": result.replayed,
        "listing_id": fixture.listing_id,
        "product_slug": fixture.product_slug,
        "subtotal_ngwee": result.subtotal_ngwee,
        "total_ngwee": result.total_ngwee,
        "orders": [
            {"order_id": order.order_id, "vendor_id": order.vendor_id, "cod": order.cod}
            for order in result.orders
        ],
    }
