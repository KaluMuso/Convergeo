"""Prepaid Lenco collection settlement — escrow_hold / CHARGE_RECEIVED into escrow.

Accounting policy (collection vs release):
- **At collection (this module):** post per-order ``escrow_hold`` (or checkout
  ``CHARGE_RECEIVED`` when no orders exist) — debit ``platform_cash``, credit
  ``escrow`` for the gross payment amount, exactly once per ``checkout_group_id``.
- **At escrow release (product / service / event / COD paths):** capture commission
  from the purchase-time ``commission_snapshot`` via ``COMMISSION_CAPTURE`` *before*
  ``RELEASE_TO_VENDOR`` (net). See ``escrow/release.py``, ``escrow/event_release.py``,
  ``routers/job_completion.py``, and ``payments/cod.py``.

Retries create a new ``payments`` row for the same checkout. Settlement is therefore
keyed by checkout (not payment_id) so a late SUCCESS on a prior FAILED/EXPIRED
attempt cannot post a second collection after the retry already settled.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

from app.services.ledger.engine import LedgerError
from app.services.ledger.templates import LedgerTemplate
from app.services.orders.audit import run_sql_script
from app.services.payments.fulfillment import fulfill_prepaid_checkout_escrow

PREPAID_COLLECTION_KEY_PREFIX = "prepaid-charge"
_SETTLEMENT_KINDS = (
    LedgerTemplate.CHARGE_RECEIVED.value,
    LedgerTemplate.ESCROW_HOLD.value,
)

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


@dataclass(frozen=True, slots=True)
class PrepaidSettlementResult:
    payment_id: str
    transaction_id: str
    amount_ngwee: int
    created: bool
    # True when another payment already posted collection for this checkout.
    # Callers must not treat this payment as the settling attempt (no SUCCESS
    # transition that would imply a second collection on the books).
    skipped_sibling: bool = False


def prepaid_collection_idempotency_key(checkout_group_id: str) -> str:
    """Stable ledger idempotency key — one collection per checkout group."""
    return f"{PREPAID_COLLECTION_KEY_PREFIX}-checkout-{checkout_group_id}"


def _sql_uuid(value: str, field: str) -> str:
    if not _UUID_RE.match(value):
        msg = f"{field} must be a valid UUID"
        raise ValueError(msg)
    return f"'{value}'::uuid"


def _lookup_existing_charge(
    *,
    checkout_group_id: str,
) -> tuple[str, str] | None:
    """Return ``(payment_id, transaction_id)`` for an existing checkout charge, if any.

    Runs under a checkout-scoped advisory xact lock so concurrent SUCCESS paths
    serialise before deciding whether to post.
    """
    cg_sql = _sql_uuid(checkout_group_id, "checkout_group_id")
    kinds_sql = ", ".join(f"'{kind}'" for kind in _SETTLEMENT_KINDS)
    script = f"""
BEGIN;
SELECT pg_advisory_xact_lock(hashtext('checkout_prepaid:' || {cg_sql}::text));
SELECT coalesce(
  (
    SELECT coalesce(payment_id::text, '') || '|' || id::text
    FROM public.ledger_transactions
    WHERE checkout_group_id = {cg_sql}
      AND kind IN ({kinds_sql})
    ORDER BY created_at ASC
    LIMIT 1
  ),
  'none'
);
COMMIT;
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        raise LedgerError(
            f"checkout prepaid charge lookup failed: {result.error or 'empty result'}"
        )
    marker = result.rows[-1]
    if marker == "none":
        return None
    if "|" not in marker:
        raise LedgerError("checkout prepaid charge lookup returned malformed row")
    payment_id, txn_id = marker.split("|", 1)
    if not txn_id:
        raise LedgerError("checkout prepaid charge lookup missing transaction id")
    return payment_id, txn_id


def _fetch_charge_payment_id(transaction_id: str) -> str | None:
    txn_sql = _sql_uuid(transaction_id, "transaction_id")
    result = run_sql_script(
        f"SELECT coalesce(payment_id::text, '') FROM public.ledger_transactions "
        f"WHERE id = {txn_sql};"
    )
    if not result.ok or not result.rows:
        return None
    value = result.rows[-1]
    return value or None


def settle_prepaid_collection(
    service_client: ServiceRoleClient,
    *,
    payment_id: str,
    checkout_group_id: str,
    amount_ngwee: int,
) -> PrepaidSettlementResult:
    """Post collection into escrow for a prepaid Lenco payment (idempotent per checkout).

    Callers must invoke this **before** committing ``payments.status = success`` so a
    failed ledger write never leaves a successful payment without escrow backing.

    When a sibling payment already settled the same checkout, returns
    ``skipped_sibling=True`` and does not post a second charge. Callers should
    audit and leave the late payment non-SUCCESS (ops refunds the duplicate MoMo).

    Raises ``LedgerError`` on posting failure; callers must not transition to SUCCESS.
    """
    existing = _lookup_existing_charge(checkout_group_id=checkout_group_id)
    if existing is not None:
        owner_payment_id, txn_id = existing
        skipped = owner_payment_id != payment_id
        return PrepaidSettlementResult(
            payment_id=payment_id,
            transaction_id=txn_id,
            amount_ngwee=amount_ngwee,
            created=False,
            skipped_sibling=skipped,
        )

    fulfilled = fulfill_prepaid_checkout_escrow(
        service_client,
        payment_id=payment_id,
        checkout_group_id=checkout_group_id,
        amount_ngwee=amount_ngwee,
    )
    txn_id = fulfilled.transaction_ids[0] if fulfilled.transaction_ids else ""
    if not txn_id:
        raise LedgerError("prepaid fulfillment produced no ledger transaction")

    owner = _fetch_charge_payment_id(txn_id)
    skipped = owner is not None and owner != payment_id
    return PrepaidSettlementResult(
        payment_id=payment_id,
        transaction_id=txn_id,
        amount_ngwee=amount_ngwee,
        created=fulfilled.created_count > 0,
        skipped_sibling=skipped,
    )
