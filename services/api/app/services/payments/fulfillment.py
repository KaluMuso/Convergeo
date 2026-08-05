"""Prepaid payment fulfillment — per-order escrow holds after collection.

When a checkout group contains orders, collection is recorded as one
``escrow_hold`` ledger posting per order (integer ngwee, idempotent per
``order_id``). Checkout groups with no orders yet fall back to a single
checkout-scoped ``CHARGE_RECEIVED`` posting (legacy / test fixtures).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from app.services.ledger.engine import LedgerError, post_transaction
from app.services.ledger.templates import LedgerTemplate
from app.services.orders.audit import run_sql_script

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

_ESCROW_HOLD_KIND = LedgerTemplate.ESCROW_HOLD.value
_CHARGE_KIND = LedgerTemplate.CHARGE_RECEIVED.value


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


@dataclass(frozen=True, slots=True)
class CheckoutOrderRow:
    order_id: str
    gross_ngwee: int


@dataclass(frozen=True, slots=True)
class EscrowFulfillmentResult:
    checkout_group_id: str
    payment_id: str
    transaction_ids: tuple[str, ...]
    total_ngwee: int
    created_count: int


def escrow_hold_idempotency_key(order_id: str) -> str:
    return f"escrow-hold-{order_id}"


def _sql_uuid(value: str, field: str) -> str:
    if not _UUID_RE.match(value):
        msg = f"{field} must be a valid UUID"
        raise ValueError(msg)
    return f"'{value}'::uuid"


def _fetch_checkout_orders(checkout_group_id: str) -> list[CheckoutOrderRow]:
    cg_sql = _sql_uuid(checkout_group_id, "checkout_group_id")
    script = f"""
SELECT
  o.id::text || '|' || (
    coalesce((
      SELECT sum(oi.qty * oi.unit_price_ngwee)
      FROM public.order_items oi
      WHERE oi.order_id = o.id
    ), 0) + o.delivery_fee_ngwee
  )::text
FROM public.orders o
WHERE o.checkout_group_id = {cg_sql}
  AND o.status <> 'cancelled'
ORDER BY o.id ASC;
"""
    result = run_sql_script(script)
    if not result.ok:
        raise LedgerError(f"checkout order lookup failed: {result.error or 'empty result'}")
    rows: list[CheckoutOrderRow] = []
    for marker in result.rows:
        if "|" not in marker:
            continue
        order_id, gross_raw = marker.split("|", 1)
        try:
            gross = int(gross_raw)
        except ValueError:
            continue
        if gross <= 0:
            continue
        rows.append(CheckoutOrderRow(order_id=order_id, gross_ngwee=gross))
    return rows


def fulfill_prepaid_checkout_escrow(
    service_client: ServiceRoleClient,
    *,
    payment_id: str,
    checkout_group_id: str,
    amount_ngwee: int,
) -> EscrowFulfillmentResult:
    """Post per-order ``escrow_hold`` rows for a successful prepaid collection.

  Idempotent per ``order_id``. When the checkout has no orders, posts a single
  checkout-scoped ``CHARGE_RECEIVED`` instead (test fixtures / edge cases).
    """
    _ = service_client
    orders = _fetch_checkout_orders(checkout_group_id)
    if not orders:
        posted = post_transaction(
            idempotency_key=f"prepaid-charge-checkout-{checkout_group_id}",
            template=LedgerTemplate.CHARGE_RECEIVED,
            checkout_group_id=checkout_group_id,
            payment_id=payment_id,
            gross_ngwee=amount_ngwee,
        )
        return EscrowFulfillmentResult(
            checkout_group_id=checkout_group_id,
            payment_id=payment_id,
            transaction_ids=(posted.id,),
            total_ngwee=amount_ngwee,
            created_count=1 if posted.created else 0,
        )

    order_total = sum(row.gross_ngwee for row in orders)
    if order_total != amount_ngwee:
        raise LedgerError(
            "checkout order gross does not match payment amount "
            f"({order_total} ngwee vs {amount_ngwee} ngwee)"
        )

    txn_ids: list[str] = []
    created = 0
    for row in orders:
        UUID(row.order_id)  # validate
        posted = post_transaction(
            idempotency_key=escrow_hold_idempotency_key(row.order_id),
            template=LedgerTemplate.ESCROW_HOLD,
            checkout_group_id=checkout_group_id,
            order_id=row.order_id,
            payment_id=payment_id,
            order_amount_ngwee=row.gross_ngwee,
        )
        txn_ids.append(posted.id)
        if posted.created:
            created += 1

    return EscrowFulfillmentResult(
        checkout_group_id=checkout_group_id,
        payment_id=payment_id,
        transaction_ids=tuple(txn_ids),
        total_ngwee=order_total,
        created_count=created,
    )


def checkout_escrow_already_settled(*, checkout_group_id: str) -> bool:
    """True when this checkout already has collection / escrow-hold postings."""
    cg_sql = _sql_uuid(checkout_group_id, "checkout_group_id")
    kinds_sql = ", ".join(f"'{kind}'" for kind in (_CHARGE_KIND, _ESCROW_HOLD_KIND))
    script = f"""
SELECT count(*)::text
FROM public.ledger_transactions
WHERE checkout_group_id = {cg_sql}
  AND kind IN ({kinds_sql});
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        return False
    return int(result.rows[0]) > 0
