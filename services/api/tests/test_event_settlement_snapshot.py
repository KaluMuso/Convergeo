"""Unit tests for settlement snapshot schedule building (no Postgres required)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.events.settlement_snapshot import (
    SettlementSchedule,
    build_settlement_schedule,
    compute_settlement_branch,
)


def test_build_schedule_records_branch_and_settlement_end() -> None:
    starts_at = datetime(2026, 9, 1, 18, 0, tzinfo=UTC)
    ends_at = starts_at + timedelta(hours=3)
    purchased_at = starts_at - timedelta(days=20)

    schedule = build_settlement_schedule(
        starts_at=starts_at,
        ends_at=ends_at,
        event_type="standard",
        purchased_at=purchased_at,
    )

    assert schedule.branch == "phased"
    assert schedule.settlement_end == ends_at
    assert schedule.event_type == "standard"
    assert schedule.settlement_rule == "timing_default"


def test_recurring_forces_full_branch_in_schedule() -> None:
    starts_at = datetime(2026, 10, 1, 18, 0, tzinfo=UTC)
    purchased_at = starts_at - timedelta(days=30)

    schedule = build_settlement_schedule(
        starts_at=starts_at,
        ends_at=None,
        event_type="recurring",
        purchased_at=purchased_at,
    )

    assert schedule.branch == "full"
    assert schedule.settlement_rule == "full_only"
    assert compute_settlement_branch(
        purchased_at=purchased_at, starts_at=starts_at, event_type="recurring"
    ) == "full"


def test_schedule_json_roundtrip() -> None:
    starts_at = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    purchased_at = starts_at - timedelta(days=3)
    original = build_settlement_schedule(
        starts_at=starts_at,
        ends_at=None,
        event_type="standard",
        purchased_at=purchased_at,
    )
    restored = SettlementSchedule.from_json(original.to_json())
    assert restored == original
