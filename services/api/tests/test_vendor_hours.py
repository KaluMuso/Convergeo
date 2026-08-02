"""R02-P10: opening-hours evaluation.

The data has been stored since migration 0002 and returned by the read paths
ever since; nothing evaluated it. These tests pin the edges that decide whether
a customer is sent across Lusaka to a shut shop.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from app.services.vendors.hours import (
    LUSAKA_TZ,
    is_open_at,
    next_open_at,
    parse_span,
)

# Monday 2026-08-03, in Africa/Lusaka.
MON = datetime(2026, 8, 3, 12, 0, tzinfo=LUSAKA_TZ)


def _at(day: int, hour: int, minute: int = 0) -> datetime:
    """A datetime in Lusaka on 2026-08-{day}."""
    return datetime(2026, 8, day, hour, minute, tzinfo=LUSAKA_TZ)


class TestParseSpan:
    def test_parses_a_normal_span(self) -> None:
        assert parse_span("09:00-17:00") == (
            datetime(2026, 1, 1, 9, 0).time(),
            datetime(2026, 1, 1, 17, 0).time(),
        )

    @pytest.mark.parametrize(
        "raw",
        [
            None,
            "",
            "09:00",
            "09:00-",
            "09:00-17:00-19:00",
            "9am-5pm",
            "25:00-26:00",
            "09:61-17:00",
            {"open": "09:00"},
            123,
        ],
    )
    def test_unusable_input_is_none_never_an_exception(self, raw: object) -> None:
        """Hours are operator-entered data, and this runs inside list queries —
        one malformed row must not 500 an entire directory page."""
        assert parse_span(raw) is None


class TestIsOpenAt:
    HOURS = {"mon": "09:00-17:00", "sat": "09:00-13:00"}

    def test_inside_the_span_is_open(self) -> None:
        assert is_open_at(self.HOURS, _at(3, 12)) is True

    def test_before_opening_is_closed(self) -> None:
        assert is_open_at(self.HOURS, _at(3, 8, 59)) is False

    def test_after_closing_is_closed(self) -> None:
        assert is_open_at(self.HOURS, _at(3, 17, 1)) is False

    def test_opening_minute_is_inclusive(self) -> None:
        assert is_open_at(self.HOURS, _at(3, 9, 0)) is True

    def test_closing_minute_is_exclusive(self) -> None:
        """At exactly 17:00 the shop is shut. Half-open [open, close) is the
        only convention that makes consecutive spans not overlap."""
        assert is_open_at(self.HOURS, _at(3, 17, 0)) is False

    def test_a_day_with_no_entry_is_closed(self) -> None:
        # Tuesday is absent from HOURS.
        assert is_open_at(self.HOURS, _at(4, 12)) is False

    def test_missing_hours_is_closed_not_open(self) -> None:
        unusable: tuple[object, ...] = (None, {}, [], "09:00-17:00", 42)
        for hours in unusable:
            assert is_open_at(hours, MON) is False

    def test_malformed_span_is_closed_and_does_not_raise(self) -> None:
        assert is_open_at({"mon": "not-a-span"}, MON) is False

    def test_zero_length_window_is_closed(self) -> None:
        assert is_open_at({"mon": "09:00-09:00"}, _at(3, 9)) is False


class TestOvernightSpans:
    """`18:00-02:00` is what a bar or filling station means. Reading it as an
    invalid window would mark those vendors as never open."""

    HOURS = {"fri": "18:00-02:00"}

    def test_open_late_on_the_day_itself(self) -> None:
        # Friday 2026-08-07, 23:00.
        assert is_open_at(self.HOURS, _at(7, 23)) is True

    def test_still_open_after_midnight_on_the_following_day(self) -> None:
        # Saturday 01:00 — the tail of Friday's span.
        assert is_open_at(self.HOURS, _at(8, 1)) is True

    def test_closed_after_the_overnight_span_ends(self) -> None:
        assert is_open_at(self.HOURS, _at(8, 2, 1)) is False

    def test_closed_before_it_opens(self) -> None:
        assert is_open_at(self.HOURS, _at(7, 17, 59)) is False


class TestServerClockWins:
    def test_utc_and_local_inputs_agree(self) -> None:
        """Same instant, two representations, one answer — the function
        converts rather than trusting the tzinfo it was handed."""
        hours = {"mon": "09:00-17:00"}
        local_noon = _at(3, 12)
        same_instant_utc = local_noon.astimezone(UTC)
        assert is_open_at(hours, local_noon) == is_open_at(hours, same_instant_utc)

    def test_a_foreign_timezone_does_not_change_the_verdict(self) -> None:
        """A device in Tokyo asking about a Lusaka shop gets Lusaka's answer."""
        hours = {"mon": "09:00-17:00"}
        tokyo_now = _at(3, 12).astimezone(ZoneInfo("Asia/Tokyo"))
        assert is_open_at(hours, tokyo_now) is True


class TestNextOpenAt:
    def test_returns_todays_opening_when_still_ahead(self) -> None:
        result = next_open_at({"mon": "09:00-17:00"}, _at(3, 7))
        assert result == _at(3, 9)

    def test_rolls_forward_to_the_next_open_day(self) -> None:
        # Monday evening, next opening is Saturday.
        result = next_open_at({"mon": "09:00-17:00", "sat": "09:00-13:00"}, _at(3, 18))
        assert result == _at(8, 9)

    def test_none_when_no_usable_hours(self) -> None:
        """Honest absence beats an invented time — the UI can then say
        'hours not published' rather than promise an opening."""
        assert next_open_at(None, MON) is None
        assert next_open_at({"mon": "garbage"}, MON) is None
