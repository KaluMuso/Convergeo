"""Prepaid Lenco collection settlement — CHARGE_RECEIVED into platform cash/escrow.

Accounting policy (collection vs release):
- **At collection (this module):** post ``CHARGE_RECEIVED`` — debit ``platform_cash``,
  credit ``escrow`` for the gross payment amount, exactly once per ``payment_id``.
- **At escrow release (not implemented here):** ``capture_order_commission`` must post
  ``COMMISSION_CAPTURE`` before ``RELEASE_TO_VENDOR`` net payout. Prepaid release
  currently computes net in ``escrow/release.py`` but does not yet post commission
  ledger legs; that gap is tracked as a follow-up dependency on this slice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.services.ledger.engine import post_transaction
from app.services.ledger.templates import LedgerTemplate

PREPAID_COLLECTION_KEY_PREFIX = "prepaid-charge"


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


@dataclass(frozen=True, slots=True)
class PrepaidSettlementResult:
    payment_id: str
    transaction_id: str
    amount_ngwee: int
    created: bool


def prepaid_collection_idempotency_key(payment_id: str) -> str:
    """Stable ledger idempotency key — one CHARGE_RECEIVED per payment."""
    return f"{PREPAID_COLLECTION_KEY_PREFIX}-{payment_id}"


def settle_prepaid_collection(
    service_client: ServiceRoleClient,
    *,
    payment_id: str,
    checkout_group_id: str,
    amount_ngwee: int,
) -> PrepaidSettlementResult:
    """Post CHARGE_RECEIVED for a prepaid Lenco collection (idempotent per payment_id).

    Callers must invoke this **before** committing ``payments.status = success`` so a
    failed ledger write never leaves a successful payment without escrow backing.

    Raises ``LedgerError`` on posting failure; callers must not transition to SUCCESS.
    """
    _ = service_client
    posted = post_transaction(
        idempotency_key=prepaid_collection_idempotency_key(payment_id),
        template=LedgerTemplate.CHARGE_RECEIVED,
        checkout_group_id=checkout_group_id,
        payment_id=payment_id,
        gross_ngwee=amount_ngwee,
    )
    return PrepaidSettlementResult(
        payment_id=payment_id,
        transaction_id=posted.id,
        amount_ngwee=amount_ngwee,
        created=posted.created,
    )
