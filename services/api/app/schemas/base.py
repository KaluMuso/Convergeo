"""Strict Pydantic primitives shared across API request/response models."""

from __future__ import annotations

import re
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict

REFERENCE_CHARSET_RE = re.compile(r"^[-._A-Za-z0-9]+$")


def _reject_non_int_ngwee(value: object, *, allow_negative: bool = False) -> int:
    if isinstance(value, bool):
        msg = "ngwee must be an integer, not bool"
        raise ValueError(msg)
    if isinstance(value, float):
        msg = "ngwee must be an integer, floats are forbidden"
        raise ValueError(msg)
    if isinstance(value, str):
        msg = "ngwee must be an integer, strings are forbidden"
        raise ValueError(msg)
    if not isinstance(value, int):
        msg = f"ngwee must be int, got {type(value).__name__}"
        raise TypeError(msg)
    if not allow_negative and value < 0:
        msg = "ngwee must be non-negative"
        raise ValueError(msg)
    return value


def _validate_ngwee(value: object) -> int:
    return _reject_non_int_ngwee(value, allow_negative=False)


def _validate_signed_ngwee(value: object) -> int:
    return _reject_non_int_ngwee(value, allow_negative=True)


def _validate_reference(value: object, *, prefix: str) -> str:
    if not isinstance(value, str):
        msg = f"{prefix} reference must be a string"
        raise TypeError(msg)
    if not value.startswith(prefix):
        msg = f"reference must start with {prefix}"
        raise ValueError(msg)
    suffix = value[len(prefix) :]
    if not suffix:
        msg = "reference suffix must not be empty"
        raise ValueError(msg)
    if not REFERENCE_CHARSET_RE.fullmatch(suffix):
        msg = "reference contains invalid characters (allowed: [-._A-Za-z0-9])"
        raise ValueError(msg)
    return value


def _validate_order_reference(value: object) -> str:
    return _validate_reference(value, prefix="ord-")


def _validate_payment_reference(value: object) -> str:
    return _validate_reference(value, prefix="pay-")


def _validate_refund_reference(value: object) -> str:
    return _validate_reference(value, prefix="rfd-")


NgweeInt = Annotated[int, BeforeValidator(_validate_ngwee)]
SignedNgweeInt = Annotated[int, BeforeValidator(_validate_signed_ngwee)]
OrderReference = Annotated[str, BeforeValidator(_validate_order_reference)]
PaymentReference = Annotated[str, BeforeValidator(_validate_payment_reference)]
RefundReference = Annotated[str, BeforeValidator(_validate_refund_reference)]


class StrictModel(BaseModel):
    """Base for all API DTOs — strict parsing, no unknown fields."""

    model_config = ConfigDict(strict=True, extra="forbid")


def parse_ngwee(value: Any) -> int:
    """Parse a single ngwee value (for use outside model fields)."""
    return _validate_ngwee(value)
