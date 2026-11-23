"""Who bears the Lenco collection fee — one config value for MoMo and card.

Business decision (owner): the customer pays Lenco's collection fee on top of the
order total; Vergeo5's margin lives in the service fee / commission. The Lenco
dashboard is set to "Either", so each API request (MoMo ``bearer``) and the card
widget config (``LencoPay.getPaid({bearer})``) decide who bears it.

* ``customer`` (default): Lenco charges the payer ``amount + fee`` and settles the
  full ``amount`` to us. Our ledger records exactly ``amount`` collected and books
  no fee expense.
* ``merchant`` (rollback): the payer pays ``amount``; Lenco nets the fee from our
  settlement and ``fees.book_collection_fee`` books it (debit ``fees``).

Env ``LENCO_COLLECTION_FEE_BEARER``. Any other value is rejected (fail closed: no
collection is initiated with an ambiguous fee owner).

Money: amounts/fees arrive as decimal-major strings and are parsed with
``Decimal`` only (``major_str_to_ngwee``); results are integer ngwee.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any, Literal, cast

from app.services.payments.money import major_str_to_ngwee

CollectionFeeBearer = Literal["customer", "merchant"]

LENCO_COLLECTION_FEE_BEARER_ENV = "LENCO_COLLECTION_FEE_BEARER"
CUSTOMER_BEARER: CollectionFeeBearer = "customer"
MERCHANT_BEARER: CollectionFeeBearer = "merchant"
DEFAULT_COLLECTION_FEE_BEARER: CollectionFeeBearer = CUSTOMER_BEARER
VALID_BEARERS: frozenset[str] = frozenset({CUSTOMER_BEARER, MERCHANT_BEARER})

# Key under ``payments.raw`` recording the bearer we requested for that attempt.
RAW_BEARER_KEY = "collection_bearer"


class InvalidBearerConfigError(ValueError):
    """``LENCO_COLLECTION_FEE_BEARER`` holds something other than customer/merchant."""


def get_collection_fee_bearer() -> CollectionFeeBearer:
    """Configured collection-fee bearer (default ``customer``); invalid → raise."""
    raw = os.environ.get(LENCO_COLLECTION_FEE_BEARER_ENV)
    if raw is None or raw.strip() == "":
        return DEFAULT_COLLECTION_FEE_BEARER
    value = raw.strip().lower()
    if value not in VALID_BEARERS:
        msg = f"{LENCO_COLLECTION_FEE_BEARER_ENV} must be 'customer' or 'merchant', got {raw!r}"
        raise InvalidBearerConfigError(msg)
    return cast(CollectionFeeBearer, value)


def normalize_bearer(value: object) -> CollectionFeeBearer | None:
    """Provider/raw bearer → ``customer``/``merchant``; anything else → ``None``."""
    if not isinstance(value, str):
        return None
    lowered = value.strip().lower()
    if lowered in VALID_BEARERS:
        return cast(CollectionFeeBearer, lowered)
    return None


def resolve_collection_bearer(
    provider_bearer: object, payment_raw: Mapping[str, Any] | None
) -> CollectionFeeBearer | None:
    """What Lenco reports wins; else the bearer we requested for this attempt.

    ``None`` means unknown (legacy rows from before this setting existed), which
    downstream treats as merchant — the historical behaviour.
    """
    reported = normalize_bearer(provider_bearer)
    if reported is not None:
        return reported
    if isinstance(payment_raw, Mapping):
        return normalize_bearer(payment_raw.get(RAW_BEARER_KEY))
    return None


def _fee_ngwee_or_none(fee: object) -> int | None:
    if fee is None or isinstance(fee, bool) or not isinstance(fee, str | int):
        return None
    try:
        return major_str_to_ngwee(str(fee).strip())
    except (TypeError, ValueError):
        return None


def net_collected_ngwee(
    observed_ngwee: int,
    *,
    expected_ngwee: int,
    fee: object,
    bearer: object,
) -> int:
    """Strip a customer-borne fee if Lenco folded it into the reported amount.

    Lenco documents that with ``bearer=customer`` it charges ``amount + fee`` and
    settles ``amount``. If a payload instead reports the gross charged to the
    payer, the observation equals ``expected + fee`` exactly; only then (and only
    for a customer bearer) is it treated as ``expected``. Any other value is
    returned unchanged so the existing exact-match checks still fail closed.
    """
    if observed_ngwee == expected_ngwee:
        return observed_ngwee
    if normalize_bearer(bearer) != CUSTOMER_BEARER:
        return observed_ngwee
    fee_ngwee = _fee_ngwee_or_none(fee)
    if fee_ngwee is None or fee_ngwee <= 0:
        return observed_ngwee
    if observed_ngwee == expected_ngwee + fee_ngwee:
        return expected_ngwee
    return observed_ngwee


def normalize_observation_amount(
    observation: dict[str, Any] | None,
    *,
    expected_ngwee: int,
    fee: object,
    bearer: object,
) -> dict[str, Any] | None:
    """Copy of ``observation`` with a customer-borne fee removed from ``amount_ngwee``.

    The atomic settlement RPC requires ``amount_ngwee == payment.amount_ngwee``
    (Σ order gross); the gross the payer was charged is kept for audit only.
    """
    if observation is None:
        return None
    observed = observation.get("amount_ngwee")
    if not isinstance(observed, int) or isinstance(observed, bool):
        return observation
    net = net_collected_ngwee(observed, expected_ngwee=expected_ngwee, fee=fee, bearer=bearer)
    if net == observed:
        return observation
    return {
        **observation,
        "amount_ngwee": net,
        "provider_gross_ngwee": observed,
        "customer_fee_ngwee": observed - net,
    }
