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


def make_order_reference(order_id: str) -> str:
    """Build an order collection reference: ord-<encoded-id>."""
    ref = f"{_ORDER_PREFIX}{_encode_id(order_id)}"
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
    """Parse a reference into (kind, decoded_id)."""
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

    return kind, _decode_id(ref[len(prefix) :])
