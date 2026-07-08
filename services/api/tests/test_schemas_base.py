"""Tests for strict Pydantic money and reference codecs."""

from __future__ import annotations

import pytest
from app.schemas.base import (
    NgweeInt,
    OrderReference,
    PaymentReference,
    RefundReference,
    SignedNgweeInt,
    StrictModel,
)
from pydantic import ValidationError


class MoneyPayload(StrictModel):
    amount_ngwee: NgweeInt


class SignedMoneyPayload(StrictModel):
    amount_ngwee: SignedNgweeInt


class OrderPayload(StrictModel):
    reference: OrderReference


class PaymentPayload(StrictModel):
    reference: PaymentReference


class RefundPayload(StrictModel):
    reference: RefundReference


def test_ngwee_accepts_valid_integer() -> None:
    payload = MoneyPayload(amount_ngwee=12_500)
    assert payload.amount_ngwee == 12_500


def test_ngwee_rejects_float() -> None:
    with pytest.raises(ValidationError) as exc_info:
        MoneyPayload(amount_ngwee=10.5)  # type: ignore[arg-type]
    assert "floats are forbidden" in str(exc_info.value)


def test_ngwee_rejects_string() -> None:
    with pytest.raises(ValidationError) as exc_info:
        MoneyPayload(amount_ngwee="10500")  # type: ignore[arg-type]
    assert "strings are forbidden" in str(exc_info.value)


def test_ngwee_rejects_negative() -> None:
    with pytest.raises(ValidationError) as exc_info:
        MoneyPayload(amount_ngwee=-1)
    assert "non-negative" in str(exc_info.value)


def test_signed_ngwee_allows_negative() -> None:
    payload = SignedMoneyPayload(amount_ngwee=-500)
    assert payload.amount_ngwee == -500


def test_order_reference_accepts_valid() -> None:
    payload = OrderPayload(reference="ord-abc123._-XYZ")
    assert payload.reference == "ord-abc123._-XYZ"


def test_order_reference_rejects_bad_prefix() -> None:
    with pytest.raises(ValidationError) as exc_info:
        OrderPayload(reference="pay-wrong-prefix")
    assert "must start with ord-" in str(exc_info.value)


def test_order_reference_rejects_bad_charset() -> None:
    with pytest.raises(ValidationError) as exc_info:
        OrderPayload(reference="ord-has space")
    assert "invalid characters" in str(exc_info.value)


def test_payment_reference_accepts_valid() -> None:
    payload = PaymentPayload(reference="pay-lenco_2026.01")
    assert payload.reference == "pay-lenco_2026.01"


def test_payment_reference_rejects_bad_prefix() -> None:
    with pytest.raises(ValidationError) as exc_info:
        PaymentPayload(reference="ord-not-payment")
    assert "must start with pay-" in str(exc_info.value)


def test_refund_reference_accepts_valid() -> None:
    payload = RefundPayload(reference="rfd-9aZ._-0")
    assert payload.reference == "rfd-9aZ._-0"


def test_refund_reference_rejects_bad_charset() -> None:
    with pytest.raises(ValidationError) as exc_info:
        RefundPayload(reference="rfd-bad+plus")
    assert "invalid characters" in str(exc_info.value)
