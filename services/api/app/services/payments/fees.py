"""Lenco provider-fee booking (C6) — keeps ``platform_cash`` equal to the Lenco balance.

Lenco deducts its fee from our merchant account:

* collections with ``bearer=merchant`` (the default): the customer pays ``amount``
  and our balance rises by ``amount − fee``;
* transfers (vendor payouts and customer refund payouts): our balance falls by
  ``amount + fee``.

Without booking the fee, ``platform_cash`` drifts from the Lenco available balance
by every fee and the daily reconciliation report is never clean. Each fee is booked
once via the ``lenco_fee`` template (debit ``fees``, credit ``platform_cash``),
idempotent per payment / payout.

Money: the fee arrives as a decimal-major string and is parsed with ``Decimal``
only (``major_str_to_ngwee``); anything else is never treated as money.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from app.services.ledger.engine import PostedTransaction, post_transaction
from app.services.ledger.templates import LedgerTemplate
from app.services.payments.money import major_str_to_ngwee

logger = logging.getLogger(__name__)

CUSTOMER_BEARER = "customer"


def collection_fee_idempotency_key(payment_id: str) -> str:
    return f"lenco-fee-collection-{payment_id}"


def transfer_fee_idempotency_key(payout_id: str) -> str:
    return f"lenco-fee-transfer-{payout_id}"


def parse_fee_ngwee(fee: object) -> int:
    """Lenco ``fee`` ("0.25" / None) → integer ngwee. Missing → 0.

    Raises ``ValueError`` for anything that is present but not a valid
    non-negative 2dp decimal string (floats are rejected, never coerced).
    """
    if fee is None or fee == "":
        return 0
    if isinstance(fee, bool) or not isinstance(fee, str | int):
        msg = f"unparseable Lenco fee: {fee!r}"
        raise ValueError(msg)
    return major_str_to_ngwee(str(fee).strip())


def fee_fields_from_provider_raw(raw: Mapping[str, Any] | None) -> tuple[object, object]:
    """Pull ``(fee, bearer)`` from a provider payload or its ``data`` envelope."""
    if not isinstance(raw, Mapping):
        return None, None
    data = raw.get("data")
    source: Mapping[str, Any] = data if isinstance(data, Mapping) else raw
    return source.get("fee"), source.get("bearer")


def _book(
    *,
    idempotency_key: str,
    fee: object,
    payment_id: str | None = None,
    payout_id: str | None = None,
) -> PostedTransaction | None:
    try:
        fee_ngwee = parse_fee_ngwee(fee)
    except (TypeError, ValueError):
        # A malformed fee must not block a real payment/payout. Reconciliation
        # surfaces the resulting balance difference for ops.
        logger.error(
            "Lenco fee not booked: unparseable fee",
            extra={
                "alert": "lenco_fee_unparseable",
                "payment_id": payment_id,
                "payout_id": payout_id,
                "fee": repr(fee),
            },
        )
        return None
    if fee_ngwee <= 0:
        return None
    return post_transaction(
        idempotency_key=idempotency_key,
        template=LedgerTemplate.LENCO_FEE,
        payment_id=payment_id,
        payout_id=payout_id,
        fee_ngwee=fee_ngwee,
    )


def book_collection_fee(
    *, payment_id: str, fee: object, bearer: object
) -> PostedTransaction | None:
    """Book a collection fee we bear (``bearer`` merchant or unspecified)."""
    if isinstance(bearer, str) and bearer.strip().lower() == CUSTOMER_BEARER:
        # Customer paid the fee on top; our balance receives the full amount.
        return None
    return _book(
        idempotency_key=collection_fee_idempotency_key(payment_id),
        fee=fee,
        payment_id=payment_id,
    )


def book_transfer_fee(*, payout_id: str, fee: object) -> PostedTransaction | None:
    """Book the fee Lenco charged on a paid transfer (payout or refund payout)."""
    return _book(
        idempotency_key=transfer_fee_idempotency_key(payout_id),
        fee=fee,
        payout_id=payout_id,
    )
