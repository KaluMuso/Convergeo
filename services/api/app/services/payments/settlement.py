"""Prepaid Lenco collection settlement — CHARGE_RECEIVED into platform cash/escrow.

Accounting policy (collection vs release):
- **At collection (this module):** post ``CHARGE_RECEIVED`` — debit ``platform_cash``,
  credit ``escrow`` for the gross payment amount, exactly once per ``checkout_group_id``.
- **At escrow release (product / service / event / COD paths):** capture commission
  from the purchase-time ``commission_snapshot`` via ``COMMISSION_CAPTURE`` *before*
  ``RELEASE_TO_VENDOR`` (net). See ``escrow/release.py``, ``escrow/event_release.py``,
  ``routers/job_completion.py``, and ``payments/cod.py``.

Retries create a new ``payments`` row for the same checkout. Settlement is therefore
keyed by checkout (not payment_id) so a late SUCCESS on a prior FAILED/EXPIRED
attempt cannot post a second ``CHARGE_RECEIVED`` after the retry already settled.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

from app.services.ledger.engine import LedgerError, post_transaction
from app.services.ledger.templates import LedgerTemplate
from app.services.orders.audit import run_sql_script

PREPAID_COLLECTION_KEY_PREFIX = "prepaid-charge"
_CHARGE_KIND = LedgerTemplate.CHARGE_RECEIVED.value

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
    # True when another payment already posted CHARGE_RECEIVED for this checkout.
    # Callers must not treat this payment as the settling attempt (no SUCCESS
    # transition that would imply a second collection on the books).
    skipped_sibling: bool = False


def prepaid_collection_idempotency_key(checkout_group_id: str) -> str:
    """Stable ledger idempotency key — one CHARGE_RECEIVED per checkout group."""
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
    script = f"""
BEGIN;
SELECT pg_advisory_xact_lock(hashtext('checkout_prepaid:' || {cg_sql}::text));
SELECT coalesce(
  (
    SELECT coalesce(payment_id::text, '') || '|' || id::text
    FROM public.ledger_transactions
    WHERE checkout_group_id = {cg_sql}
      AND kind = '{_CHARGE_KIND}'
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
    """Post CHARGE_RECEIVED for a prepaid Lenco collection (idempotent per checkout).

    Callers must invoke this **before** committing ``payments.status = success`` so a
    failed ledger write never leaves a successful payment without escrow backing.

    When a sibling payment already settled the same checkout, returns
    ``skipped_sibling=True`` and does not post a second charge. Callers should
    audit and leave the late payment non-SUCCESS (ops refunds the duplicate MoMo).

    Raises ``LedgerError`` on posting failure; callers must not transition to SUCCESS.
    """
    _ = service_client

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

    posted = post_transaction(
        idempotency_key=prepaid_collection_idempotency_key(checkout_group_id),
        template=LedgerTemplate.CHARGE_RECEIVED,
        checkout_group_id=checkout_group_id,
        payment_id=payment_id,
        gross_ngwee=amount_ngwee,
    )

    if not posted.created:
        owner = _fetch_charge_payment_id(posted.id)
        skipped = owner is not None and owner != payment_id
        return PrepaidSettlementResult(
            payment_id=payment_id,
            transaction_id=posted.id,
            amount_ngwee=amount_ngwee,
            created=False,
            skipped_sibling=skipped,
        )

    return PrepaidSettlementResult(
        payment_id=payment_id,
        transaction_id=posted.id,
        amount_ngwee=amount_ngwee,
        created=True,
        skipped_sibling=False,
    )
