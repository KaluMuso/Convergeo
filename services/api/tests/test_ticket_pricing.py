"""DB-free unit tests for the M10-P12 server-side price resolution."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.tickets.purchase import resolve_unit_price

NOW = datetime(2026, 7, 1, tzinfo=UTC)
BASE = 50_000


def _resolve(**kwargs: object) -> int:
    defaults: dict[str, object] = {
        "base_price_ngwee": BASE,
        "early_bird_price_ngwee": None,
        "early_bird_until": None,
        "tiers": [],
        "qty": 1,
        "now": NOW,
    }
    defaults.update(kwargs)
    return resolve_unit_price(**defaults)  # type: ignore[arg-type]


def test_base_price_when_no_discounts() -> None:
    assert _resolve() == BASE


def test_early_bird_active_before_cutoff() -> None:
    assert (
        _resolve(early_bird_price_ngwee=40_000, early_bird_until=NOW + timedelta(days=1))
        == 40_000
    )


def test_early_bird_ignored_after_cutoff() -> None:
    assert (
        _resolve(early_bird_price_ngwee=40_000, early_bird_until=NOW - timedelta(days=1)) == BASE
    )


def test_early_bird_ignored_exactly_at_cutoff() -> None:
    # now == cutoff -> not before it -> base.
    assert _resolve(early_bird_price_ngwee=40_000, early_bird_until=NOW) == BASE


def test_group_tier_applies_at_and_above_threshold() -> None:
    tiers = [(5, 45_000), (10, 40_000)]
    assert _resolve(tiers=tiers, qty=5) == 45_000
    assert _resolve(tiers=tiers, qty=9) == 45_000
    assert _resolve(tiers=tiers, qty=10) == 40_000
    assert _resolve(tiers=tiers, qty=12) == 40_000


def test_group_tier_below_threshold_uses_base() -> None:
    assert _resolve(tiers=[(5, 45_000)], qty=4) == BASE


def test_lowest_of_early_bird_and_tier_wins() -> None:
    tiers = [(10, 40_000)]
    # qty 10: tier (40k) < early-bird (42k) -> 40k
    assert (
        _resolve(
            early_bird_price_ngwee=42_000,
            early_bird_until=NOW + timedelta(days=1),
            tiers=tiers,
            qty=10,
        )
        == 40_000
    )
    # qty 5: tier does not qualify -> early-bird (42k) wins over base
    assert (
        _resolve(
            early_bird_price_ngwee=42_000,
            early_bird_until=NOW + timedelta(days=1),
            tiers=tiers,
            qty=5,
        )
        == 42_000
    )


def test_discounts_never_exceed_base() -> None:
    # A misconfigured "discount" above base never raises the price (min wins).
    assert (
        _resolve(early_bird_price_ngwee=99_000, early_bird_until=NOW + timedelta(days=1)) == BASE
    )
    assert _resolve(tiers=[(2, 99_000)], qty=5) == BASE
