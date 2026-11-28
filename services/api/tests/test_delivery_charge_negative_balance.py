"""A vendor whose free-delivery charges exceed their earnings is never paid out.

The courier fee for vendor-funded free delivery is a debit on ``vendor_payable``
(``delivery_fee_vendor_charge``). When it exceeds what the vendor has earned, the
account goes positive (the vendor owes the platform). That debt must carry forward:
nothing is payable until later earnings clear it, and it is never netted away.

The ledger balance is built here from the real posting templates (so a template
change that breaks the sign convention fails this test) and fed to the real
eligibility code.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from app.errors import AppError
from app.services.ledger.templates import delivery_fee_vendor_charge, release_to_vendor
from app.services.payouts.eligibility import (
    assert_payout_eligible,
    compute_eligibility,
    released_balance_ngwee,
)

VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


class _Payouts:
    """Minimal ``payouts`` table: no reserved payouts."""

    def select(self, *_a: Any, **_k: Any) -> _Payouts:
        return self

    def eq(self, *_a: Any, **_k: Any) -> _Payouts:
        return self

    def in_(self, *_a: Any, **_k: Any) -> _Payouts:
        return self

    def execute(self) -> MagicMock:
        return MagicMock(data=[])


def _service_client() -> MagicMock:
    wrapper = MagicMock()
    wrapper.client.table.return_value = _Payouts()
    return wrapper


def _balance(*results: Any) -> int:
    """Signed vendor_payable balance after posting the given template results."""
    return sum(
        leg.amount_ngwee
        for result in results
        for leg in result.legs
        if leg.account.kind == "vendor_payable" and leg.account.vendor_id == VENDOR_ID
    )


def _with_balance(balance: int):  # type: ignore[no-untyped-def]
    return patch(
        "app.services.payouts.eligibility.vendor_payable_balance_ngwee", return_value=balance
    )


def test_charge_larger_than_earnings_leaves_a_debt_and_nothing_payable() -> None:
    earned = release_to_vendor(net_ngwee=1_000, vendor_id=VENDOR_ID)  # K10 earned
    charge = delivery_fee_vendor_charge(funded_ngwee=4_500, vendor_id=VENDOR_ID)  # K45 fee
    balance = _balance(earned, charge)
    assert balance == 3_500  # positive: the vendor owes K35

    with _with_balance(balance):
        snapshot = compute_eligibility(_service_client(), VENDOR_ID)
        assert snapshot.released_balance_ngwee == 0
        assert snapshot.available_ngwee == 0
        assert released_balance_ngwee(VENDOR_ID) == 0
        with pytest.raises(AppError) as exc:
            assert_payout_eligible(_service_client(), vendor_id=VENDOR_ID, amount_ngwee=1)
        assert exc.value.code == "insufficient_released_balance"


def test_debt_carries_forward_and_later_earnings_clear_it_first() -> None:
    earned = release_to_vendor(net_ngwee=1_000, vendor_id=VENDOR_ID)
    charge = delivery_fee_vendor_charge(funded_ngwee=4_500, vendor_id=VENDOR_ID)
    later = release_to_vendor(net_ngwee=10_000, vendor_id=VENDOR_ID)  # K100 next order

    balance = _balance(earned, charge, later)
    assert balance == -6_500  # K100 − K35 debt = K65 payable, not K100

    with _with_balance(balance):
        snapshot = compute_eligibility(_service_client(), VENDOR_ID)
        assert snapshot.available_ngwee == 6_500
        # The K35 debt is never paid out: asking for the gross K100 is refused.
        with pytest.raises(AppError) as exc:
            assert_payout_eligible(_service_client(), vendor_id=VENDOR_ID, amount_ngwee=10_000)
        assert exc.value.code == "insufficient_released_balance"


def test_each_band_fee_reduces_payable_by_exactly_the_fee() -> None:
    earned = release_to_vendor(net_ngwee=20_000, vendor_id=VENDOR_ID)
    for fee in (3_000, 4_500, 6_500):  # K30 / K45 / K65 bands
        charge = delivery_fee_vendor_charge(funded_ngwee=fee, vendor_id=VENDOR_ID)
        with _with_balance(_balance(earned, charge)):
            snapshot = compute_eligibility(_service_client(), VENDOR_ID)
        assert snapshot.available_ngwee == 20_000 - fee
