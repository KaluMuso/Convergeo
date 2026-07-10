"""Ngwee ↔ decimal-major-unit conversion for the Lenco API boundary."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.schemas.base import parse_ngwee

SUPPORTED_CURRENCY = "ZMW"
_TWO_DP = Decimal("0.01")
_NGEWEE_PER_MAJOR = Decimal(100)


def assert_zmw_currency(currency: str) -> None:
    """Reject any currency other than ZMW."""
    if currency != SUPPORTED_CURRENCY:
        msg = f"unsupported currency: {currency!r} (only {SUPPORTED_CURRENCY} is allowed)"
        raise ValueError(msg)


def ngwee_to_major_str(ngwee: int, *, currency: str = SUPPORTED_CURRENCY) -> str:
    """Convert integer ngwee to a 2dp decimal-major-unit string (e.g. 123456 → \"1234.56\")."""
    assert_zmw_currency(currency)
    validated = parse_ngwee(ngwee)
    major = (Decimal(validated) / _NGEWEE_PER_MAJOR).quantize(_TWO_DP)
    return format(major, "f")


def major_str_to_ngwee(amount: str, *, currency: str = SUPPORTED_CURRENCY) -> int:
    """Parse a 2dp decimal-major-unit string into integer ngwee."""
    assert_zmw_currency(currency)
    if isinstance(amount, float):  # noqa: SIM101 — explicit float guard
        msg = "amount must be a string, floats are forbidden"
        raise TypeError(msg)
    try:
        major = Decimal(amount)
    except (InvalidOperation, ValueError, TypeError) as exc:
        msg = f"invalid amount: {amount!r}"
        raise ValueError(msg) from exc
    if not major.is_finite():
        msg = "amount must be finite"
        raise ValueError(msg)
    if major < 0:
        msg = "amount must be non-negative"
        raise ValueError(msg)
    if major != major.quantize(_TWO_DP):
        msg = "amount must have at most 2 decimal places"
        raise ValueError(msg)
    ngwee_decimal = (major * _NGEWEE_PER_MAJOR).to_integral_value()
    return parse_ngwee(int(ngwee_decimal))
