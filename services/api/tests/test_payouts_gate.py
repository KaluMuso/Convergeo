"""Unit tests for the PAYOUTS_ENABLED kill switch."""

from __future__ import annotations

import pytest
from app.services.payouts.gate import (
    PAYOUTS_ENABLED_ENV,
    PayoutsDisabledError,
    assert_payouts_enabled,
    payouts_enabled,
)


def test_payouts_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(PAYOUTS_ENABLED_ENV, raising=False)
    assert payouts_enabled() is False
    with pytest.raises(PayoutsDisabledError):
        assert_payouts_enabled()


def test_payouts_enabled_when_truthy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PAYOUTS_ENABLED_ENV, "true")
    assert payouts_enabled() is True
    assert_payouts_enabled()
