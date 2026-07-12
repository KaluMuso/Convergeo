"""Generate and parse Lenco client references (ord-/pay-/rfd-)."""

from __future__ import annotations

import base64
from typing import Literal

from app.schemas.base import (
    REFERENCE_CHARSET_RE,
    OrderReference,
    PaymentReference,
    RefundReference,
)
from pydantic import TypeAdapter, ValidationError

ReferenceKind = Literal["order", "payment", "refund"]

_ORDER_PREFIX = "ord-"
_PAYMENT_PREFIX = "pay-"
_REFUND_PREFIX = "rfd-"

# Separator for the optional per-attempt salt. "." is inside the allowed charset
# [-._A-Za-z0-9] but is never emitted by urlsafe base64, so it splits the encoded
# id from the salt unambiguously and keeps the id fully round-trip-decodable.
_ATTEMPT_SEP = "."

_ORDER_ADAPTER: TypeAdapter[OrderReference] = TypeAdapter(OrderReference)
_PAYMENT_ADAPTER: TypeAdapter[PaymentReference] = TypeAdapter(PaymentReference)
_REFUND_ADAPTER: TypeAdapter[RefundReference] = TypeAdapter(RefundReference)


def _encode_id(raw_id: str) -> str:
    encoded = base64.urlsafe_b64encode(raw_id.encode("utf-8")).decode("ascii").rstrip("=")
    if not REFERENCE_CHARSET_RE.fullmatch(encoded):
        msg = "encoded id contains invalid characters (allowed: [-._A-Za-z0-9])"
        raise ValueError(msg)
    return encoded


def _decode_id(encoded: str) -> str:
    padding = "=" * (-len(encoded) % 4)
    try:
        return base64.urlsafe_b64decode(encoded + padding).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        msg = "reference suffix is not a valid encoded id"
        raise ValueError(msg) from exc


def make_order_reference(order_id: str, *, attempt: str | None = None) -> str:
    """Build an order collection reference: ``ord-<encoded-id>[.<encoded-attempt>]``.

    When ``attempt`` is provided (e.g. the per-attempt ``payment_id``), a distinct
    salt segment is appended so each retry produces a unique reference and does not
    collide on the UNIQUE ``payments.lenco_reference`` constraint. The salt is a
    separate segment, so ``parse_reference`` still round-trips the ``order_id``; the
    webhook/reconciler resolve the payment by the stored ``lenco_reference``, never
    by re-deriving it from ``order_id``, so the salt is transparent to them.
    """
    suffix = _encode_id(order_id)
    if attempt is not None:
        suffix = f"{suffix}{_ATTEMPT_SEP}{_encode_id(attempt)}"
    ref = f"{_ORDER_PREFIX}{suffix}"
    _ORDER_ADAPTER.validate_python(ref)
    return ref


def make_payment_reference(payment_id: str) -> str:
    """Build a payout transfer reference: pay-<encoded-id>."""
    ref = f"{_PAYMENT_PREFIX}{_encode_id(payment_id)}"
    _PAYMENT_ADAPTER.validate_python(ref)
    return ref


def make_refund_reference(refund_id: str) -> str:
    """Build a refund payout reference: rfd-<encoded-id>."""
    ref = f"{_REFUND_PREFIX}{_encode_id(refund_id)}"
    _REFUND_ADAPTER.validate_python(ref)
    return ref


def parse_reference(ref: str) -> tuple[ReferenceKind, str]:
    """Parse a reference into (kind, decoded_id), ignoring any per-attempt salt."""
    if ref.startswith(_ORDER_PREFIX):
        kind: ReferenceKind = "order"
        adapter = _ORDER_ADAPTER
        prefix = _ORDER_PREFIX
    elif ref.startswith(_PAYMENT_PREFIX):
        kind = "payment"
        adapter = _PAYMENT_ADAPTER
        prefix = _PAYMENT_PREFIX
    elif ref.startswith(_REFUND_PREFIX):
        kind = "refund"
        adapter = _REFUND_ADAPTER
        prefix = _REFUND_PREFIX
    else:
        msg = f"unknown reference prefix in {ref!r}"
        raise ValueError(msg)

    try:
        adapter.validate_python(ref)
    except ValidationError as exc:
        raise ValueError(str(exc.errors()[0]["msg"])) from exc

    # Drop the optional per-attempt salt segment before decoding the id.
    encoded = ref[len(prefix) :].split(_ATTEMPT_SEP, 1)[0]
    return kind, _decode_id(encoded)
