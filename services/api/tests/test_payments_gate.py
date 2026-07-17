"""Tests for the safe-by-default payment kill switch (app.services.payments.gate).

The gate blocks all Lenco payment *initiation* (mobile money + card) unless
explicitly enabled. COD is never gated. These tests drive the env contract
directly via monkeypatch (overriding the suite-wide enable defaults set in
conftest), so both the disabled and enabled states are exercised.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.routers.checkout_payment import (
    _validate_payment_method,
    available_payment_methods,
)
from app.services.payments.base import InitiateCollectionRequest, PaymentProviderError
from app.services.payments.gate import (
    PAYMENTS_ALLOW_PRODUCTION_ENV,
    PAYMENTS_ENABLED_ENV,
    PaymentsDisabledError,
    payments_enabled,
    payments_gate_status,
)
from app.services.payments.initiate import (
    InitiatePaymentRequest,
    initiate_checkout_payment,
)
from app.services.payments.lenco.client import LencoStrategy
from app.services.payments.lenco.config import LENCO_ENV_ENV
from app.services.payments.references import make_order_reference

PAYER_PHONE = "+260971234567"


def _set_gate(
    monkeypatch: pytest.MonkeyPatch,
    *,
    enabled: str | None = None,
    lenco_env: str | None = None,
    allow_prod: str | None = None,
) -> None:
    """Set (or clear) the three env vars that drive the gate for one test."""
    for name, value in (
        (PAYMENTS_ENABLED_ENV, enabled),
        (LENCO_ENV_ENV, lenco_env),
        (PAYMENTS_ALLOW_PRODUCTION_ENV, allow_prod),
    ):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)


def _collection_request() -> InitiateCollectionRequest:
    reference = make_order_reference(
        "11111111-1111-1111-1111-111111111111",
        attempt="22222222-2222-2222-2222-222222222222",
    )
    return InitiateCollectionRequest(
        reference=reference,
        amount_ngwee=1000,
        phone=PAYER_PHONE,
        operator="mtn",
    )


# --- env contract matrix -------------------------------------------------------


@pytest.mark.parametrize(
    ("enabled", "lenco_env", "allow_prod", "expected"),
    [
        (None, None, None, (False, "disabled_by_default")),
        ("false", "sandbox", "true", (False, "disabled_by_default")),
        ("true", "sandbox", None, (True, "enabled_sandbox")),
        ("true", "production", None, (False, "production_not_acknowledged")),
        ("true", None, None, (False, "production_not_acknowledged")),  # unset -> production
        ("true", "production", "true", (True, "enabled_production")),
        ("TRUE", "production", "on", (True, "enabled_production")),
    ],
)
def test_gate_matrix(
    monkeypatch: pytest.MonkeyPatch,
    enabled: str | None,
    lenco_env: str | None,
    allow_prod: str | None,
    expected: tuple[bool, str],
) -> None:
    _set_gate(monkeypatch, enabled=enabled, lenco_env=lenco_env, allow_prod=allow_prod)
    assert payments_gate_status() == expected
    assert payments_enabled() is expected[0]


# --- provider backstop (defence in depth) -------------------------------------


async def test_provider_backstop_blocks_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_gate(monkeypatch)  # all off -> disabled
    inner = MagicMock()
    inner.initiate_collection = AsyncMock()
    strategy = LencoStrategy(client=inner)

    with pytest.raises(PaymentsDisabledError):
        await strategy.initiate_collection(MagicMock())

    inner.initiate_collection.assert_not_awaited()


async def test_provider_reaches_client_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_gate(monkeypatch, enabled="true", lenco_env="sandbox")
    inner = MagicMock()
    # data=None makes LencoStrategy raise provider_error *after* the network call,
    # which proves the backstop let us through to the client.
    inner.initiate_collection = AsyncMock(return_value=SimpleNamespace(data=None))
    strategy = LencoStrategy(client=inner)

    with pytest.raises(PaymentProviderError):
        await strategy.initiate_collection(_collection_request())

    inner.initiate_collection.assert_awaited_once()


# --- boundary guard: initiate_checkout_payment --------------------------------


async def test_initiate_blocked_when_disabled_writes_no_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_gate(monkeypatch)  # off
    service = MagicMock()
    strategy = MagicMock()
    strategy.initiate_collection = AsyncMock()
    request = InitiatePaymentRequest(
        checkout_group_id="cg-1", amount_ngwee=1000, rail="mtn", phone=PAYER_PHONE
    )

    with pytest.raises(PaymentsDisabledError):
        await initiate_checkout_payment(
            service, request, strategy=strategy, actor_id="actor-1"
        )

    strategy.initiate_collection.assert_not_awaited()
    service.client.table.assert_not_called()  # no payments row created


async def test_block_logs_reason_without_pii(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _set_gate(monkeypatch)  # off
    service = MagicMock()
    request = InitiatePaymentRequest(
        checkout_group_id="cg-42", amount_ngwee=1000, rail="mtn", phone=PAYER_PHONE
    )

    with caplog.at_level(logging.WARNING):
        with pytest.raises(PaymentsDisabledError):
            await initiate_checkout_payment(service, request, actor_id="actor-1")

    blocked = [r for r in caplog.records if r.getMessage() == "payment_initiation_blocked"]
    assert blocked, "expected a payment_initiation_blocked warning"
    record = blocked[0]
    assert getattr(record, "reason_code", None) == "disabled_by_default"
    assert getattr(record, "method", None) == "mtn"
    assert getattr(record, "reference", None) == "cg-42"
    # the payer phone must never appear anywhere on the log record
    assert all(PAYER_PHONE not in str(value) for value in record.__dict__.values())


# --- payment-options + method validation --------------------------------------


def test_available_methods_hides_prepaid_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_gate(monkeypatch)  # off
    assert available_payment_methods(cod_eligible=True) == ["cod"]
    assert available_payment_methods(cod_eligible=False) == []


def test_available_methods_lists_prepaid_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_gate(monkeypatch, enabled="true", lenco_env="sandbox")
    assert available_payment_methods(cod_eligible=True) == ["momo", "card", "cod"]
    assert available_payment_methods(cod_eligible=False) == ["momo", "card"]


@pytest.mark.parametrize("method", ["momo", "card"])
def test_validate_rejects_prepaid_when_disabled(
    monkeypatch: pytest.MonkeyPatch, method: str
) -> None:
    _set_gate(monkeypatch)  # off
    with pytest.raises(PaymentsDisabledError):
        _validate_payment_method(
            method=method,  # type: ignore[arg-type]
            rail="mtn",
            payer_number=PAYER_PHONE,
            total_ngwee=1000,
            cod_cap_ngwee=50_000,
        )


def test_validate_allows_cod_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_gate(monkeypatch)  # off -> COD must still work
    rail, payer = _validate_payment_method(
        method="cod",
        rail=None,
        payer_number=None,
        total_ngwee=1000,
        cod_cap_ngwee=50_000,
    )
    assert rail is None
    assert payer is None


# --- user-safe error body ------------------------------------------------------


def test_disabled_error_is_user_safe() -> None:
    err = PaymentsDisabledError()
    assert err.code == "payments_disabled"
    assert err.http_status == 503
    assert err.details == {}
    lowered = err.message.lower()
    assert "cash on delivery" in lowered
    for leak in (
        "payments_enabled",
        "payments_allow_production",
        "lenco",
        "disabled_by_default",
        "production_not_acknowledged",
        "sandbox",
        "token",
    ):
        assert leak not in lowered
