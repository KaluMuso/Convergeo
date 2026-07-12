"""OpenAPI/schema-driven input fuzz — deterministic and bounded.

Goals (M15-P04):
- Prove strict Pydantic DTO validation rejects hostile input: type confusion,
  oversized payloads, unicode abuse, and — critically — **negative / overflow
  ngwee on money fields** (money must never be persisted out of range).
- Stay DETERMINISTIC: a single fixed seed (overridable via the ``FUZZ_SEED``
  env var, but constant in CI) drives a bounded number of examples. No wall
  clock, no unbounded generation, no network, no DB — so CI never flakes.

The money contract under test:
- ``NgweeInt`` (the shared validator) rejects floats, strings, bools, and
  negatives, and raises ``TypeError`` for wholly wrong types (dict/list/None/…).
- ``NgweeInt`` intentionally defers the UPPER bound to the DB ``bigint`` column.
  A persistable money field therefore composes ``NgweeInt`` with the bigint
  ceiling; the fuzz asserts anything above it is rejected before persistence.
"""

from __future__ import annotations

import os
import random
from typing import Annotated

import pytest
from app.schemas.base import NgweeInt, SignedNgweeInt, StrictModel, parse_ngwee
from pydantic import Field, ValidationError

# --- Determinism knobs ------------------------------------------------------
# Fixed seed keeps every run identical; capped example counts keep CI bounded.
FUZZ_SEED = int(os.environ.get("FUZZ_SEED", "20260711"))
MONEY_EXAMPLES = 250
TEXT_EXAMPLES = 200

# Postgres signed bigint range — the persistable ngwee ceiling for money.
PG_BIGINT_MAX = 9_223_372_036_854_775_807

# Max length of the representative free-text field under test.
TEXT_MAX_LEN = 500

# Rejection may surface as a Pydantic ValidationError (ValueError-class guards)
# or a bare TypeError (wholly-wrong input types). Both mean "not persisted".
REJECTIONS = (ValidationError, TypeError)


# --- Representative strict DTOs mirroring real request models ---------------
class MoneyModel(StrictModel):
    """Unsigned ngwee money field (e.g. price_ngwee, amount_ngwee)."""

    amount_ngwee: NgweeInt


class SignedMoneyModel(StrictModel):
    """Signed ngwee money field (e.g. ledger deltas)."""

    amount_ngwee: SignedNgweeInt


class PersistableMoneyModel(StrictModel):
    """Money bounded to the DB bigint range — what actually reaches Postgres."""

    amount_ngwee: Annotated[NgweeInt, Field(le=PG_BIGINT_MAX)]


class TextModel(StrictModel):
    """Bounded free-text field (e.g. review body, dispute reason)."""

    note: str = Field(max_length=TEXT_MAX_LEN)


# --- Deterministic generators ----------------------------------------------
def _rng() -> random.Random:
    return random.Random(FUZZ_SEED)


def _type_confusion_values(rng: random.Random) -> list[object]:
    """Non-integer values that must never validate as money."""
    return [
        rng.uniform(-1e9, 1e9),  # arbitrary float
        float("nan"),
        float("inf"),
        float("-inf"),
        str(rng.randint(0, 10**6)),  # numeric string
        f"{rng.randint(0, 999)}.{rng.randint(0, 99)}",  # decimal string
        True,  # bool masquerading as int
        False,
        None,
        b"1234",  # bytes
        [rng.randint(0, 9)],  # list
        {"amount": rng.randint(0, 9)},  # dict
        complex(rng.randint(0, 9), 1),  # complex
    ]


def test_generator_is_deterministic() -> None:
    """Same seed → identical value stream (no flaky CI)."""
    a = _type_confusion_values(_rng())
    b = _type_confusion_values(_rng())
    # NaN != NaN, so compare via repr for a stable equality check.
    assert [repr(x) for x in a] == [repr(x) for x in b]


def test_money_rejects_type_confusion() -> None:
    rng = _rng()
    for _ in range(MONEY_EXAMPLES):
        value = rng.choice(_type_confusion_values(rng))
        with pytest.raises(REJECTIONS):
            MoneyModel(amount_ngwee=value)  # type: ignore[arg-type]


def test_money_rejects_negative_ngwee() -> None:
    rng = _rng()
    for _ in range(MONEY_EXAMPLES):
        negative = -rng.randint(1, PG_BIGINT_MAX)
        with pytest.raises(ValidationError) as exc:
            MoneyModel(amount_ngwee=negative)
        assert "non-negative" in str(exc.value)


def test_money_rejects_overflow_ngwee() -> None:
    """Values above the DB bigint ceiling must be rejected, never persisted."""
    rng = _rng()
    for _ in range(MONEY_EXAMPLES):
        # Anything strictly greater than the signed bigint max, incl. wildly
        # oversized ints Python would otherwise carry silently.
        overflow = PG_BIGINT_MAX + rng.randint(1, 10**24)
        with pytest.raises(ValidationError):
            PersistableMoneyModel(amount_ngwee=overflow)


def test_money_accepts_in_range_ngwee() -> None:
    """Valid in-range values round-trip exactly (int, no float coercion)."""
    rng = _rng()
    for _ in range(MONEY_EXAMPLES):
        valid = rng.randint(0, PG_BIGINT_MAX)
        model = PersistableMoneyModel(amount_ngwee=valid)
        assert model.amount_ngwee == valid
        assert type(model.amount_ngwee) is int


def test_signed_money_allows_negative_rejects_float() -> None:
    rng = _rng()
    for _ in range(MONEY_EXAMPLES):
        negative = -rng.randint(1, PG_BIGINT_MAX)
        assert SignedMoneyModel(amount_ngwee=negative).amount_ngwee == negative
        # A float is never acceptable money even where negatives are allowed.
        with pytest.raises(REJECTIONS):
            SignedMoneyModel(amount_ngwee=float(negative))  # type: ignore[arg-type]


def test_parse_ngwee_helper_rejects_hostile_scalars() -> None:
    """The shared scalar money parser must reject the same hostile inputs."""
    rng = _rng()
    for value in _type_confusion_values(rng):
        with pytest.raises((ValueError, TypeError)):
            parse_ngwee(value)


def test_text_rejects_oversized_payloads() -> None:
    rng = _rng()
    for _ in range(TEXT_EXAMPLES):
        length = rng.randint(TEXT_MAX_LEN + 1, TEXT_MAX_LEN + 20_000)
        oversized = "a" * length
        with pytest.raises(ValidationError):
            TextModel(note=oversized)


def test_text_accepts_bounded_unicode() -> None:
    """Arbitrary unicode within the length bound is accepted verbatim."""
    rng = _rng()
    # Mix emoji, RTL, combining marks, zero-width, CJK — all valid within bound.
    alphabet = "aZ9 \t\n​́é😀क漢‮ש"
    for _ in range(TEXT_EXAMPLES):
        length = rng.randint(1, TEXT_MAX_LEN)
        text = "".join(rng.choice(alphabet) for _ in range(length))
        model = TextModel(note=text)
        assert model.note == text


def test_text_rejects_non_string_types() -> None:
    rng = _rng()
    for value in (rng.randint(0, 9), 1.5, True, None, [rng.randint(0, 9)], {"a": 1}):
        with pytest.raises(ValidationError):
            TextModel(note=value)  # type: ignore[arg-type]


def test_openapi_money_fields_are_integer_typed() -> None:
    """OpenAPI-driven guard: schema must expose ngwee fields as integers.

    Confirms the strict money DTOs surface as ``integer`` (never ``number``/
    ``string``) in the generated OpenAPI, so clients cannot send float money.
    """
    from app.main import create_app

    schema = create_app().openapi()
    schemas = schema.get("components", {}).get("schemas", {})
    checked = 0
    for definition in schemas.values():
        for field_name, spec in definition.get("properties", {}).items():
            if field_name.endswith("_ngwee") and "type" in spec:
                assert spec["type"] == "integer", (field_name, spec)
                checked += 1
    assert checked > 0, "expected at least one *_ngwee integer field in OpenAPI"
