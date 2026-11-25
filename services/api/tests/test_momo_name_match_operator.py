"""Operator detection and resolve-failure mapping for KYC MoMo name match."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from app.errors import AppError
from app.services.kyc.name_match import detect_momo_operator, resolve_momo_account_name


@pytest.mark.parametrize(
    ("phone", "operator"),
    [
        ("0961234567", "mtn"),
        ("0761234567", "mtn"),
        ("+260761234567", "mtn"),
        ("260961234567", "mtn"),
        ("0971234567", "airtel"),
        ("0771234567", "airtel"),
        ("0951234567", "zamtel"),
        ("0751234567", "zamtel"),
    ],
)
def test_detect_momo_operator_uses_zicta_prefixes(phone: str, operator: str) -> None:
    assert detect_momo_operator(phone) == operator


def _client(status: int) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"status": False, "message": "not found"})

    return httpx.AsyncClient(base_url="https://lenco.test", transport=httpx.MockTransport(handler))


def test_unknown_wallet_is_a_422_not_a_502(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LENCO_API_TOKEN", "test-token")
    with pytest.raises(AppError) as err:
        asyncio.run(resolve_momo_account_name("0761234567", client=_client(400)))
    assert err.value.http_status == 422
    assert err.value.code == "momo_account_not_found"


def test_lenco_outage_stays_502(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LENCO_API_TOKEN", "test-token")
    with pytest.raises(AppError) as err:
        asyncio.run(resolve_momo_account_name("0761234567", client=_client(503)))
    assert err.value.http_status == 502


def test_missing_vendor_payable_account_is_zero_balance(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.ledger.engine import LedgerAccountNotFoundError
    from app.services.payouts import eligibility

    def _missing(ref: object) -> str:
        raise LedgerAccountNotFoundError("ledger account not found")

    monkeypatch.setattr(eligibility, "resolve_account_id", _missing)
    assert eligibility.vendor_payable_balance_ngwee("v-1") == 0
    assert eligibility.released_balance_ngwee("v-1") == 0


@pytest.mark.parametrize(
    ("momo", "legal", "matched"),
    [
        ("Kaluba Musonda", "Kaluba Prosper Musonda", True),
        ("MUSONDA KALUBA", "Kaluba Prosper Musonda", True),
        ("Kaluba Prosper Musonda", "Kaluba Musonda", True),
        ("Musonda", "Kaluba Prosper Musonda", False),
        ("John Banda", "Jane Phiri", False),
        ("Kaluba Mwale", "Kaluba Prosper Musonda", False),
    ],
)
def test_name_match_accepts_missing_middle_name(momo: str, legal: str, matched: bool) -> None:
    from app.services.kyc.name_match import score_name_match

    assert score_name_match(momo, legal)[1] is matched
