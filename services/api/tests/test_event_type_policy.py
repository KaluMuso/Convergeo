from __future__ import annotations

import pytest
from app.services.events.access import hash_access_code, verify_access_code
from app.services.events.type_policy import (
    EVENT_TYPES,
    normalize_event_type,
    policy_for,
)


def test_normalize_event_type_defaults_to_standard() -> None:
    assert normalize_event_type(None) == "standard"
    assert normalize_event_type("bogus") == "standard"
    for event_type in EVENT_TYPES:
        assert normalize_event_type(event_type) == event_type


def test_policy_for_unknown_falls_back_to_standard() -> None:
    policy = policy_for("nope")
    assert policy.event_type == "standard"
    assert policy.default_visibility == "public"
    assert policy.settlement_rule == "timing_default"


def test_private_defaults_to_private_visibility() -> None:
    assert policy_for("private").default_visibility == "private"


def test_non_private_types_default_public() -> None:
    for event_type in ("standard", "recurring", "free_rsvp"):
        assert policy_for(event_type).default_visibility == "public"


def test_only_recurring_overrides_settlement_rule() -> None:
    # P14: recurring settles full-only (single release at end+24h, no phased
    # advance); every other type keeps today's lead-time timing.
    assert policy_for("recurring").settlement_rule == "full_only"
    assert policy_for("recurring").is_series is True
    for event_type in ("standard", "free_rsvp", "private"):
        assert policy_for(event_type).settlement_rule == "timing_default"


def test_free_rsvp_flagged_free_only() -> None:
    assert policy_for("free_rsvp").is_free_only is True
    assert policy_for("standard").is_free_only is False


def test_access_code_round_trip() -> None:
    stored = hash_access_code("Backstage-2026")
    assert "$" in stored
    assert stored != "Backstage-2026"
    assert verify_access_code("Backstage-2026", stored) is True
    # Whitespace is trimmed symmetrically on hash + verify.
    assert verify_access_code("  Backstage-2026 ", stored) is True


def test_access_code_rejects_wrong_and_missing() -> None:
    stored = hash_access_code("correct-horse")
    assert verify_access_code("wrong", stored) is False
    assert verify_access_code(None, stored) is False
    assert verify_access_code("correct-horse", None) is False
    assert verify_access_code("correct-horse", "malformed-no-dollar") is False
    assert verify_access_code("", stored) is False


def test_access_code_salts_differ_per_call() -> None:
    # Same code, different stored hashes (random salt) — both still verify.
    a = hash_access_code("same-code")
    b = hash_access_code("same-code")
    assert a != b
    assert verify_access_code("same-code", a)
    assert verify_access_code("same-code", b)


def test_hash_access_code_rejects_empty() -> None:
    with pytest.raises(ValueError):
        hash_access_code("   ")
