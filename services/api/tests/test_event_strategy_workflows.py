"""Pure-function coverage for remaining events-strategy workflows."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.errors import AppError
from app.services.events.buyer_cancellation import buyer_cancel_band, compute_buyer_cancel_refund
from app.services.events.capacity_tree import assert_allocation_capacity_tree
from app.services.events.date_windows import (
    next_month_window,
    next_week_window,
    on_date_window,
    tonight_window,
    weekend_window,
    window_bounds,
)
from app.services.events.disputes_policy import (
    MISREPRESENTATION_KIND,
    assert_event_dispute_openable,
    event_dispute_deadline,
    organiser_respond_by,
)
from app.services.events.fees import (
    EVENT_TICKETS_RATE_BPS,
    checkout_total_ngwee,
    commission_rate_bps,
    platform_fee_ngwee,
)
from app.services.events.promo import apply_promo_discount
from app.services.events.ranking import browse_rank_tuple, is_selling_fast
from app.services.events.teams import digest_invite_token, normalize_invite_phone

REF = datetime(2026, 8, 13, 15, 0, tzinfo=UTC)  # Thursday afternoon Lusaka = 17:00


def test_absorb_fee_leaves_buyer_total_unchanged() -> None:
    assert platform_fee_ngwee(line_total_ngwee=10_000, fee_payer="organiser", is_free=False) == 0
    assert commission_rate_bps(fee_payer="organiser", is_free=False) == EVENT_TICKETS_RATE_BPS
    assert checkout_total_ngwee(subtotal_ngwee=10_000, platform_fee=0) == 10_000


def test_pass_through_fee_is_5_percent_integer_ngwee() -> None:
    fee = platform_fee_ngwee(line_total_ngwee=10_000, fee_payer="buyer", is_free=False)
    assert fee == 500
    assert commission_rate_bps(fee_payer="buyer", is_free=False) == 0
    assert checkout_total_ngwee(subtotal_ngwee=10_000, platform_fee=fee) == 10_500


def test_free_tickets_never_take_a_platform_fee() -> None:
    assert platform_fee_ngwee(line_total_ngwee=0, fee_payer="buyer", is_free=True) == 0
    assert commission_rate_bps(fee_payer="buyer", is_free=True) == 0


def test_buyer_cancel_bands() -> None:
    start = datetime(2026, 9, 1, 18, 0, tzinfo=UTC)
    now = datetime(2026, 8, 1, 18, 0, tzinfo=UTC)
    assert buyer_cancel_band(start, now=now) == "full_minus_admin"
    policy = compute_buyer_cancel_refund(paid_ngwee=10_000, starts_at=start, now=now)
    assert policy.refund_ngwee == 9_500
    assert policy.admin_fee_ngwee == 500

    mid = datetime(2026, 8, 28, 18, 0, tzinfo=UTC)
    assert buyer_cancel_band(start, now=mid) == "half"
    half = compute_buyer_cancel_refund(paid_ngwee=10_000, starts_at=start, now=mid)
    assert half.refund_ngwee == 5_000

    late = datetime(2026, 9, 1, 6, 0, tzinfo=UTC)
    assert buyer_cancel_band(start, now=late) == "none"
    none = compute_buyer_cancel_refund(paid_ngwee=10_000, starts_at=start, now=late)
    assert none.refund_ngwee == 0


def test_selling_fast_is_70_percent_and_not_sold_out() -> None:
    assert is_selling_fast(spots_sold=70, spots_total=100, is_sold_out=False) is True
    assert is_selling_fast(spots_sold=69, spots_total=100, is_sold_out=False) is False
    assert is_selling_fast(spots_sold=100, spots_total=100, is_sold_out=True) is False


def test_verified_and_selling_fast_rank_ahead_of_later_start() -> None:
    early = datetime(2026, 8, 20, 18, 0, tzinfo=UTC)
    later = datetime(2026, 8, 21, 18, 0, tzinfo=UTC)
    fast_verified = browse_rank_tuple(
        next_starts_at=later,
        spots_sold=80,
        spots_total=100,
        is_sold_out=False,
        verified=True,
        event_lat=None,
        event_lng=None,
        user_lat=None,
        user_lng=None,
        category=None,
        affinity_categories=frozenset(),
    )
    slow_unverified = browse_rank_tuple(
        next_starts_at=early,
        spots_sold=10,
        spots_total=100,
        is_sold_out=False,
        verified=False,
        event_lat=None,
        event_lng=None,
        user_lat=None,
        user_lng=None,
        category=None,
        affinity_categories=frozenset(),
    )
    assert fast_verified < slow_unverified


def test_date_windows_cover_next_week_month_and_on_date() -> None:
    local = datetime(2026, 8, 13, 17, 0, tzinfo=REF.tzinfo)
    # Thursday 13 Aug 2026 Lusaka — next week is Mon 17–Sun 23.
    week = next_week_window(local)
    assert week[0].date().isoformat() == "2026-08-17"
    assert week[1].date().isoformat() == "2026-08-23"
    month = next_month_window(local)
    assert month[0].date().isoformat() == "2026-09-01"
    on_day = on_date_window(local.date())
    bounds = window_bounds("tonight", on_date=local.date(), ref=local)
    assert bounds == on_day
    tonight = tonight_window(local)
    weekend = weekend_window(local)
    assert tonight[1].date() == local.date()
    assert weekend[0].date().isoformat() == "2026-08-14"


def test_promo_percent_and_fixed_never_exceed_line() -> None:
    assert (
        apply_promo_discount(line_total_ngwee=10_000, discount_kind="percent", discount_value=10)
        == 1_000
    )
    assert (
        apply_promo_discount(line_total_ngwee=10_000, discount_kind="fixed", discount_value=50_000)
        == 10_000
    )
    assert apply_promo_discount(line_total_ngwee=0, discount_kind="percent", discount_value=10) == 0


def test_capacity_tree_rejects_over_allocation() -> None:
    with pytest.raises(AppError) as exc:
        assert_allocation_capacity_tree(
            instance_capacities={"i1": 100},
            other_allocated={"i1": 80},
            proposed={"i1": 30},
        )
    assert exc.value.code == "allocation_exceeds_capacity"
    assert_allocation_capacity_tree(
        instance_capacities={"i1": 100},
        other_allocated={"i1": 80},
        proposed={"i1": 20},
    )


def test_event_dispute_requires_evidence_and_seven_day_window() -> None:
    ends = datetime(2026, 8, 1, 20, 0, tzinfo=UTC)
    deadline = event_dispute_deadline(ends)
    assert deadline == datetime(2026, 8, 8, 20, 0, tzinfo=UTC)
    sla = organiser_respond_by(datetime(2026, 8, 2, 12, 0, tzinfo=UTC))
    assert sla == datetime(2026, 8, 5, 12, 0, tzinfo=UTC)
    with pytest.raises(AppError):
        assert_event_dispute_openable(
            ends_at=ends,
            now=datetime(2026, 8, 10, tzinfo=UTC),
            kind=MISREPRESENTATION_KIND,
            evidence_paths=["path/a.jpg"],
        )
    with pytest.raises(AppError):
        assert_event_dispute_openable(
            ends_at=ends,
            now=datetime(2026, 8, 2, tzinfo=UTC),
            kind=MISREPRESENTATION_KIND,
            evidence_paths=[],
        )
    assert_event_dispute_openable(
        ends_at=ends,
        now=datetime(2026, 8, 2, tzinfo=UTC),
        kind=MISREPRESENTATION_KIND,
        evidence_paths=["path/a.jpg"],
    )


def test_invite_phone_normalises_zambian_local() -> None:
    assert normalize_invite_phone("0977123456") == "+260977123456"
    assert digest_invite_token("abc") == digest_invite_token("abc")
    assert digest_invite_token("abc") != digest_invite_token("abd")
