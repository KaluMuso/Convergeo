from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.events.access import (
    hash_access_code,
    issue_event_access_proof,
    verify_access_code,
    verify_event_access_proof,
)
from app.services.events.recurrence import iter_occurrence_starts, parse_rrule


def test_access_code_uses_slow_versioned_digest_and_constant_time_verification() -> None:
    digest = hash_access_code("  invite-only  ")

    assert digest.startswith("v2$")
    assert verify_access_code("invite-only", digest) is True
    assert verify_access_code("wrong", digest) is False


def test_access_proof_is_event_version_bound_and_expires() -> None:
    now = datetime(2026, 8, 13, 12, tzinfo=UTC)
    proof = issue_event_access_proof(
        event_id="11111111-1111-1111-1111-111111111111",
        credential_version=3,
        now=now,
        secret="test-secret",
    )

    assert (
        verify_event_access_proof(
            proof,
            event_id="11111111-1111-1111-1111-111111111111",
            credential_version=3,
            now=now + timedelta(minutes=1),
            secret="test-secret",
        )
        is not None
    )
    assert (
        verify_event_access_proof(
            proof,
            event_id="22222222-2222-2222-2222-222222222222",
            credential_version=3,
            now=now,
            secret="test-secret",
        )
        is None
    )
    assert (
        verify_event_access_proof(
            proof,
            event_id="11111111-1111-1111-1111-111111111111",
            credential_version=3,
            now=now + timedelta(minutes=16),
            secret="test-secret",
        )
        is None
    )


def test_weekly_rrule_materialises_selected_weekdays_without_crossing_horizon() -> None:
    seed = datetime(2026, 8, 1, 18, tzinfo=UTC)  # Saturday in Africa/Lusaka
    rule = parse_rrule("FREQ=WEEKLY;BYDAY=WE,SA;COUNT=4", timezone="Africa/Lusaka")

    starts = list(
        iter_occurrence_starts(
            seed,
            rule=rule,
            timezone="Africa/Lusaka",
            horizon_days=30,
        )
    )

    assert starts == [
        datetime(2026, 8, 1, 18, tzinfo=UTC),
        datetime(2026, 8, 5, 18, tzinfo=UTC),
        datetime(2026, 8, 8, 18, tzinfo=UTC),
        datetime(2026, 8, 12, 18, tzinfo=UTC),
    ]
