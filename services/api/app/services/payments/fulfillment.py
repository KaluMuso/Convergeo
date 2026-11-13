"""Prepaid payment fulfillment — per-order escrow holds after collection.

When a checkout group contains orders, collection is recorded as one
``escrow_hold`` ledger posting per order (integer ngwee, idempotent per
``order_id``). Orders that carry a buyer-paid platform fee
(``orders.platform_fee_ngwee`` — event tickets with fee payer = buyer) get a
SEPARATE fee hold (``escrow-hold-fee-{order_id}``) so payment amount =
items + delivery + platform fee reconciles, the fee stays refundable with the
ticket, and event release captures it to ``commission_revenue`` (never to the
organiser). Checkout groups with no orders yet fall back to a single
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
    platform_fee_ngwee: int = 0

    @property
    def collected_ngwee(self) -> int:
        return self.gross_ngwee + self.platform_fee_ngwee


@dataclass(frozen=True, slots=True)
class EscrowFulfillmentResult:
    checkout_group_id: str
    payment_id: str
    transaction_ids: tuple[str, ...]
    total_ngwee: int
    created_count: int


def escrow_hold_idempotency_key(order_id: str) -> str:
    return f"escrow-hold-{order_id}"


def platform_fee_hold_idempotency_key(order_id: str) -> str:
    return f"escrow-hold-fee-{order_id}"


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
  -- to_jsonb read tolerates databases that predate the platform_fee_ngwee
  -- column (20260816220000): the fee reads as 0 there instead of erroring.
  || '|' || coalesce((to_jsonb(o) ->> 'platform_fee_ngwee')::bigint, 0)::text
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
        parts = marker.split("|")
        order_id = parts[0]
        try:
            gross = int(parts[1])
            fee = int(parts[2]) if len(parts) > 2 and parts[2] else 0
        except (IndexError, ValueError):
            continue
        if fee < 0:
            raise LedgerError(f"negative platform fee on order {order_id}")
        if gross + fee <= 0:
            continue
        rows.append(CheckoutOrderRow(order_id=order_id, gross_ngwee=gross, platform_fee_ngwee=fee))
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

    # Payment amount = Σ(items + delivery + buyer-paid platform fee) per order.
    order_total = sum(row.collected_ngwee for row in orders)
    if order_total != amount_ngwee:
        raise LedgerError(
            "checkout order gross does not match payment amount "
            f"({order_total} ngwee vs {amount_ngwee} ngwee)"
        )

    txn_ids: list[str] = []
    created = 0
    for row in orders:
        UUID(row.order_id)  # validate
        if row.gross_ngwee > 0:
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
        if row.platform_fee_ngwee > 0:
            # Separate fee leg: held in escrow on the order (refundable with the
            # ticket), captured to commission_revenue at event release.
            fee_posted = post_transaction(
                idempotency_key=platform_fee_hold_idempotency_key(row.order_id),
                template=LedgerTemplate.ESCROW_HOLD,
                checkout_group_id=checkout_group_id,
                order_id=row.order_id,
                payment_id=payment_id,
                order_amount_ngwee=row.platform_fee_ngwee,
            )
            txn_ids.append(fee_posted.id)
            if fee_posted.created:
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


def held_platform_fee_ngwee(order_id: str) -> int:
    """Platform fee actually held in escrow for ``order_id`` (0 when none).

    Read from the ledger (the fee-hold posting), not from ``orders``, so release
    captures exactly what collection put into escrow.
    """
    UUID(order_id)
    key_sql = "'" + platform_fee_hold_idempotency_key(order_id) + "'"
    script = f"""
SELECT coalesce(sum(abs(lp.amount_ngwee)), 0)::text
FROM public.ledger_transactions lt
JOIN public.ledger_postings lp ON lp.transaction_id = lt.id
JOIN public.ledger_accounts la ON la.id = lp.account_id
WHERE lt.idempotency_key = {key_sql}
  AND la.kind = 'escrow';
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        raise LedgerError(f"platform fee hold lookup failed: {result.error or 'empty result'}")
    return int(result.rows[0])
