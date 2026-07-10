"""Tests for payment money primitives, reference codec, and provider registry."""

from __future__ import annotations

import ast
import inspect
from decimal import Decimal
from pathlib import Path

import pytest
from app.services.payments.money import (
    assert_zmw_currency,
    major_str_to_ngwee,
    ngwee_to_major_str,
)
from app.services.payments.references import (
    make_order_reference,
    make_payment_reference,
    make_refund_reference,
    parse_reference,
)
from app.services.payments.registry import UnknownProviderError, get

MAX_BIGINT = 9_223_372_036_854_775_807


@pytest.mark.parametrize(
    ("ngwee", "expected"),
    [
        (0, "0.00"),
        (1, "0.01"),
        (123, "1.23"),
        (123_456, "1234.56"),
        (MAX_BIGINT, "92233720368547758.07"),
    ],
)
def test_ngwee_to_major_str_goldens(ngwee: int, expected: str) -> None:
    assert ngwee_to_major_str(ngwee) == expected


@pytest.mark.parametrize(
    ("major", "expected_ngwee"),
    [
        ("0.00", 0),
        ("0.01", 1),
        ("1.23", 123),
        ("1234.56", 123_456),
        ("92233720368547758.07", MAX_BIGINT),
    ],
)
def test_major_str_to_ngwee_goldens(major: str, expected_ngwee: int) -> None:
    assert major_str_to_ngwee(major) == expected_ngwee


def test_money_round_trip_goldens() -> None:
    for ngwee in (0, 1, 123, 123_456, MAX_BIGINT):
        assert major_str_to_ngwee(ngwee_to_major_str(ngwee)) == ngwee


@pytest.mark.parametrize("amount", ["1.234", "0.001", "10.999"])
def test_major_str_rejects_more_than_two_decimal_places(amount: str) -> None:
    with pytest.raises(ValueError, match="at most 2 decimal places"):
        major_str_to_ngwee(amount)


@pytest.mark.parametrize("amount", ["NaN", "nan", "Infinity", "-Infinity", "inf"])
def test_major_str_rejects_non_finite(amount: str) -> None:
    with pytest.raises(ValueError, match="finite|non-negative|invalid"):
        major_str_to_ngwee(amount)


def test_major_str_rejects_negative() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        major_str_to_ngwee("-1.00")


def test_assert_zmw_currency_rejects_non_zmw() -> None:
    with pytest.raises(ValueError, match="unsupported currency"):
        assert_zmw_currency("USD")


def test_ngwee_to_major_str_rejects_non_zmw_currency() -> None:
    with pytest.raises(ValueError, match="unsupported currency"):
        ngwee_to_major_str(100, currency="EUR")


def test_major_str_to_ngwee_rejects_non_zmw_currency() -> None:
    with pytest.raises(ValueError, match="unsupported currency"):
        major_str_to_ngwee("1.00", currency="GBP")


@pytest.mark.parametrize(
    ("maker", "kind", "raw_id"),
    [
        (make_order_reference, "order", "550e8400-e29b-41d4-a716-446655440000"),
        (make_payment_reference, "payment", "pay-row-42"),
        (make_refund_reference, "refund", "rfd-row-9"),
    ],
)
def test_reference_generate_parse_round_trip(
    maker: object,
    kind: str,
    raw_id: str,
) -> None:
    ref = maker(raw_id)  # type: ignore[operator]
    parsed_kind, parsed_id = parse_reference(ref)
    assert parsed_kind == kind
    assert parsed_id == raw_id


@pytest.mark.parametrize(
    "ref",
    [
        "ord-has space",
        "pay-bad+plus",
        "rfd-",
        "ord-",
        "pay-",
        "rfd-",
    ],
)
def test_parse_reference_rejects_invalid(ref: str) -> None:
    with pytest.raises(ValueError):
        parse_reference(ref)


def test_parse_reference_rejects_unknown_prefix() -> None:
    with pytest.raises(ValueError, match="unknown reference prefix"):
        parse_reference("xyz-not-a-reference")


def test_registry_unknown_provider_raises_clean_error() -> None:
    with pytest.raises(UnknownProviderError) as exc_info:
        get("flutterwave")
    err = exc_info.value
    assert err.code == "unknown_provider"
    assert err.provider == "flutterwave"
    assert "unknown provider" in err.message


def test_registry_lenco_is_registered() -> None:
    assert get("lenco") is not None


def test_money_helpers_never_emit_float() -> None:
    result = ngwee_to_major_str(123_456)
    assert isinstance(result, str)
    assert not isinstance(result, float)


def test_major_str_to_ngwee_rejects_float_input() -> None:
    with pytest.raises(TypeError, match="floats are forbidden"):
        major_str_to_ngwee(12.34)  # type: ignore[arg-type]


def test_money_module_has_no_float_literals_in_computation() -> None:
    """AST guard: money.py must not use float() or float literals on money paths."""
    money_path = Path(inspect.getfile(ngwee_to_major_str))
    tree = ast.parse(money_path.read_text(encoding="utf-8"))
    offenders: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "float":
                offenders.append(f"float() call at line {node.lineno}")
        if isinstance(node, ast.Constant) and isinstance(node.value, float):
            offenders.append(f"float literal {node.value!r} at line {node.lineno}")

    assert offenders == [], f"money.py must not use float: {offenders}"


def test_ngwee_conversion_uses_decimal_not_float() -> None:
    """Golden path uses Decimal arithmetic exclusively."""
    ngwee = 123_456
    major = Decimal(ngwee) / Decimal(100)
    assert ngwee_to_major_str(ngwee) == format(major.quantize(Decimal("0.01")), "f")
