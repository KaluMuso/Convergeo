"""Automated refund of late Mobile Money collections (cancelled order / cancelled payment).

When a payment succeeds at Lenco AFTER its order was cancelled (or after the attempt
itself was cancelled), ``apply_prepaid_collection_success`` refuses to allocate the
money and records a ``payment_collection_exceptions`` row (reason ``order_cancelled``
or ``payment_cancelled``). The cash is real but unbooked: no ledger leg exists for it.

Lenco has no refunds API, so the refund is a ledger-orchestrated payout, exactly like
every other refund:

1. Book the collection that really happened to ``door_payment_suspense`` (never escrow,
   so it can never reach a vendor) under key ``late-collection-charge-<payment id>``.
2. ``execute_refund(from_suspense=True)`` pays it back out of suspense and queues a
   ``customer_refund`` payout to the ORIGINAL PAYER's MSISDN, under the deterministic
   source key ``late-collection-<payment id>``. Same key => same ledger rows, same
   ``refunds`` row, same ``rfd-*`` payout reference, so running this twice (or two
   workers at once) can never refund the payment twice.

Safe by default: the whole path is off unless ``LATE_COLLECTION_AUTO_REFUND_ENABLED`` is
truthy, and it is additionally behind the payout kill switch (``PAYOUTS_ENABLED``) that
guards every customer refund. Anything the automation cannot prove safe (card rail, no
payer phone, order already released to the vendor, service obligations, a previously
failed refund for the same payment) is left for a human and counted as ``manual_review``.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from app.errors import AppError
from app.services.db import run_sql_script
from app.services.ledger.engine import post_transaction
from app.services.ledger.templates import LedgerTemplate
from app.services.orders.audit import sql_literal
from app.services.orders.state import SYSTEM_ACTOR_ID
from app.services.payouts.gate import payouts_enabled
from app.services.refunds.constants import LATE_COLLECTION_SOURCE_PREFIX
from app.services.refunds.execute import (
    RefundExecutionResult,
    ServiceRoleClient,
    ensure_refund_allowed,
    execute_refund,
)
from app.services.refunds.payout_port import CustomerRail

logger = logging.getLogger(__name__)

LATE_COLLECTION_AUTO_REFUND_ENV = "LATE_COLLECTION_AUTO_REFUND_ENABLED"
REFUNDABLE_REASONS = ("order_cancelled", "payment_cancelled")
AUDIT_ACTION = "payment.late_collection_refund"
_TRUTHY = frozenset({"1", "true", "yes", "on"})
_MOMO_RAILS = frozenset({"mtn", "airtel", "zamtel"})
_ACTIVE_OR_DONE = frozenset(
    {"pending", "processing", "awaiting_payout", "needs_destination", "manual_review", "completed"}
)


def late_collection_auto_refund_enabled() -> bool:
    """True only when the founder explicitly enables the automation (default: off)."""
    return os.environ.get(LATE_COLLECTION_AUTO_REFUND_ENV, "").strip().lower() in _TRUTHY


def late_collection_source_key(payment_id: str) -> str:
    """Deterministic refund identity: one refund per late-collected payment, ever."""
    return f"{LATE_COLLECTION_SOURCE_PREFIX}{payment_id}"


def late_collection_charge_key(payment_id: str) -> str:
    return f"late-collection-charge-{payment_id}"


@dataclass(frozen=True, slots=True)
class LateCollectionSweepResult:
    enabled: bool
    payouts_enabled: bool
    scanned: int = 0
    refunded: int = 0
    already_refunded: int = 0
    manual_review: int = 0
    failed: int = 0


def _list_candidates(limit: int) -> list[dict[str, Any]]:
    """Unresolved late collections with everything needed to refund them.

    Excludes service obligations (their ``order_cancelled`` reason means "order moved
    on", not "cancelled") and requires an actually-cancelled order for that reason.
    """
    reasons = ", ".join(sql_literal(r) for r in REFUNDABLE_REASONS)
    script = f"""
SELECT json_build_object(
  'payment_id', e.payment_id::text,
  'reason', e.reason,
  'amount_ngwee', p.amount_ngwee,
  'rail', p.rail,
  'payer_phone', p.raw->>'payer_phone',
  'order_id', ord.id::text,
  'checkout_group_id', p.checkout_group_id::text,
  'order_ids', (SELECT coalesce(json_agg(o3.id::text ORDER BY o3.id), '[]'::json)
                FROM public.orders o3 WHERE o3.checkout_group_id = p.checkout_group_id),
  'order_released', coalesce(ord.released, false)
)::text
FROM public.payment_collection_exceptions e
JOIN public.payments p ON p.id = e.payment_id
LEFT JOIN LATERAL (
  SELECT o.id,
         EXISTS (SELECT 1 FROM public.ledger_transactions lt
                 WHERE lt.order_id = o.id AND lt.kind = 'release_to_vendor') AS released
  FROM public.orders o
  WHERE o.checkout_group_id = p.checkout_group_id
  ORDER BY (o.status = 'cancelled') DESC, o.id
  LIMIT 1
) ord ON true
WHERE e.resolved_at IS NULL
  AND e.reason IN ({reasons})
  AND NOT EXISTS (SELECT 1 FROM public.service_payment_obligations spo
                  WHERE spo.checkout_group_id = p.checkout_group_id)
  AND (e.reason <> 'order_cancelled' OR EXISTS (
         SELECT 1 FROM public.orders o2
         WHERE o2.checkout_group_id = p.checkout_group_id AND o2.status = 'cancelled'))
ORDER BY e.created_at, e.id
LIMIT {int(limit)};
"""
    result = run_sql_script(script)
    if not result.ok:
        raise AppError(
            code="database_unavailable",
            message="Late-collection candidate query failed",
            http_status=503,
        )
    rows: list[dict[str, Any]] = []
    for raw in result.rows:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            rows.append(cast(dict[str, Any], parsed))
    return rows


def _refund_rows_for_key(
    service_client: ServiceRoleClient, source_key: str
) -> list[dict[str, Any]]:
    response = (
        service_client.client.table("refunds")
        .select("id, status")
        .eq("source_key", source_key)
        .execute()
    )
    data = getattr(response, "data", None)
    return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []


def _resolve_exception(
    service_client: ServiceRoleClient,
    *,
    payment_id: str,
    refund: RefundExecutionResult,
    candidate: dict[str, Any],
) -> None:
    service_client.client.table("payment_collection_exceptions").update(
        {"resolved_at": datetime.now(UTC).isoformat()}
    ).eq("payment_id", payment_id).execute()
    service_client.client.table("audit_log").insert(
        {
            "actor": SYSTEM_ACTOR_ID,
            "action": AUDIT_ACTION,
            "entity_type": "payment",
            "entity_id": payment_id,
            "before": {},
            "after": {
                "refund_id": refund.refund_id,
                "order_id": refund.order_id,
                "amount_ngwee": refund.amount_ngwee,
                "source_key": late_collection_source_key(payment_id),
                # The payment covered the WHOLE checkout group, not just this order.
                "checkout_group_id": candidate.get("checkout_group_id"),
                "checkout_group_order_ids": candidate.get("order_ids") or [],
            },
        }
    ).execute()


def refund_late_collection(
    service_client: ServiceRoleClient, candidate: dict[str, Any]
) -> RefundExecutionResult | str:
    """Refund one late collection. Returns the refund, or a skip reason string.

    Idempotent: every key below derives from the payment id.
    """
    payment_id = str(candidate["payment_id"])
    source_key = late_collection_source_key(payment_id)
    order_id = candidate.get("order_id")
    rail = candidate.get("rail")
    phone = candidate.get("payer_phone")
    amount = candidate.get("amount_ngwee")

    existing = _refund_rows_for_key(service_client, source_key)
    if existing and not any(str(r.get("status")) in _ACTIVE_OR_DONE for r in existing):
        # Only failed/cancelled rows: a human must decide (ledger legs may be reversed),
        # so never mint a second refund automatically for the same payment.
        return "manual_review_previous_refund_failed"

    if not isinstance(order_id, str) or not order_id:
        return "manual_review_no_order"
    if candidate.get("order_released"):
        return "manual_review_order_released"
    if rail not in _MOMO_RAILS:
        return "manual_review_not_mobile_money"
    if not isinstance(phone, str) or not phone.strip():
        return "manual_review_no_payer_phone"
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        return "manual_review_bad_amount"

    # Payout kill switch / replay rule BEFORE any ledger write (ensure_refund_allowed
    # is a no-op when payouts are enabled).
    ensure_refund_allowed(
        service_client,
        order_id=order_id,
        idempotency_key=source_key,
        surface="late_collection_refund",
    )
    # Book the cash that really arrived into door_payment_suspense (platform_cash in,
    # suspense out) - NEVER escrow. If the refund step below fails, this money still
    # cannot be released to the vendor of a live order (release reads escrow only).
    post_transaction(
        idempotency_key=late_collection_charge_key(payment_id),
        template=LedgerTemplate.DOOR_PAYMENT_EXCEPTION,
        order_id=order_id,
        payment_id=payment_id,
        received_ngwee=amount,
    )
    refund = execute_refund(
        service_client=service_client,
        order_id=order_id,
        lane=1,
        customer_rail=cast(CustomerRail, rail),
        customer_momo=phone.strip(),
        idempotency_key=source_key,
        item_ngwee_override=amount,
        delivery_fee_ngwee_override=0,
        ignore_coupon_share=True,
        from_suspense=True,
    )
    _resolve_exception(service_client, payment_id=payment_id, refund=refund, candidate=candidate)
    return refund


def sweep_late_collection_refunds(
    service_client: ServiceRoleClient, *, limit: int = 50
) -> LateCollectionSweepResult:
    """Refund every unresolved late collection (flag + payout gate permitting)."""
    if not late_collection_auto_refund_enabled():
        return LateCollectionSweepResult(enabled=False, payouts_enabled=payouts_enabled())
    if not payouts_enabled():
        return LateCollectionSweepResult(enabled=True, payouts_enabled=False)

    refunded = already = manual = failed = 0
    candidates = _list_candidates(limit)
    for candidate in candidates:
        try:
            outcome = refund_late_collection(service_client, candidate)
        except AppError as exc:
            failed += 1
            logger.error(
                "late collection refund failed; will retry next run",
                extra={
                    "alert": "late_collection_refund_failed",
                    "payment_id": candidate.get("payment_id"),
                    "error_code": exc.code,
                },
            )
            continue
        if isinstance(outcome, str):
            manual += 1
            logger.error(
                "late collection needs manual refund",
                extra={
                    "alert": "late_collection_manual_review",
                    "payment_id": candidate.get("payment_id"),
                    "reason": outcome,
                },
            )
        elif outcome.created:
            refunded += 1
        else:
            already += 1
    return LateCollectionSweepResult(
        enabled=True,
        payouts_enabled=True,
        scanned=len(candidates),
        refunded=refunded,
        already_refunded=already,
        manual_review=manual,
        failed=failed,
    )
