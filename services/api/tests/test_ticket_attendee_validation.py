"""DB-free unit tests for the M10-P11 attendee-name validation + SQL helpers."""

from __future__ import annotations

import pytest
from app.errors import AppError
from app.services.tickets.purchase import (
    _sql_json_names,
    _sql_text_array,
    _validate_attendee_names,
)


def test_names_optional_when_type_not_named() -> None:
    assert _validate_attendee_names(None, qty=2, attendee_named=False) is None


def test_names_required_when_type_named() -> None:
    with pytest.raises(AppError) as exc:
        _validate_attendee_names(None, qty=1, attendee_named=True)
    assert exc.value.http_status == 422
    assert exc.value.code == "tickets.attendee_names_required"


def test_names_must_match_qty() -> None:
    with pytest.raises(AppError) as exc:
        _validate_attendee_names(["Alice"], qty=2, attendee_named=True)
    assert exc.value.code == "tickets.attendee_names_mismatch"


def test_names_reject_blank_entries() -> None:
    with pytest.raises(AppError):
        _validate_attendee_names(["Alice", "   "], qty=2, attendee_named=True)


def test_names_stripped_and_returned() -> None:
    assert _validate_attendee_names(["  Alice ", "Bob"], qty=2, attendee_named=True) == [
        "Alice",
        "Bob",
    ]


def test_names_validated_even_for_unnamed_type_when_supplied() -> None:
    # Sending names for a non-named type is allowed, but they must still match qty.
    with pytest.raises(AppError):
        _validate_attendee_names(["Alice"], qty=2, attendee_named=False)
    assert _validate_attendee_names(["Alice", "Bob"], qty=2, attendee_named=False) == [
        "Alice",
        "Bob",
    ]


def test_sql_json_names_null_for_empty() -> None:
    assert _sql_json_names(None) == "NULL"
    assert _sql_json_names([]) == "NULL"


def test_sql_json_names_builds_jsonb_and_escapes_quotes() -> None:
    out = _sql_json_names(["Alice", "O'Brien"])
    assert out.endswith("::jsonb")
    assert "Alice" in out
    # Single quotes are doubled so the jsonb literal can't break out of the string.
    assert "O''Brien" in out


def test_sql_text_array_builds_array_and_escapes_quotes() -> None:
    out = _sql_text_array(["O'Brien", "Bob"])
    assert out.startswith("ARRAY[")
    assert out.endswith("::text[]")
    assert "O''Brien" in out
    assert "'Bob'" in out
