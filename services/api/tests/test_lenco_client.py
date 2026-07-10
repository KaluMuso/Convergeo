"""Contract tests for the Lenco HTTP client (httpx MockTransport; respx-compatible patterns)."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from app.services.payments.base import (
    InitiateCollectionRequest,
    QueryStatusRequest,
    ResolveAccountRequest,
    VerifyWebhookRequest,
)
from app.services.payments.lenco.client import LencoClient, LencoStrategy, _build_json_body
from app.services.payments.lenco.config import MAX_IDEMPOTENT_RETRIES
from app.services.payments.lenco.models import (
    LencoBankPayoutRequest,
    LencoClientError,
    LencoCollectionRequest,
    LencoErrorCategory,
    LencoMomoPayoutRequest,
    map_lenco_failure,
)
from app.services.payments.money import ngwee_to_major_str
from app.services.payments.registry import get

BASE_URL = "https://api.lenco.co/access/v2"
TOKEN = "test-lenco-token"

COLLECTION_FIXTURE: dict[str, Any] = {
    "status": True,
    "message": "Collection initiated",
    "data": {
        "id": "11111111-1111-1111-1111-111111111111",
        "initiatedAt": "2026-07-10T10:00:00Z",
        "completedAt": None,
        "amount": "13.00",
        "fee": None,
        "bearer": "merchant",
        "currency": "ZMW",
        "reference": "ord-order-1-attempt-1",
        "lencoReference": "240730001",
        "type": "mobile-money",
        "status": "pay-offline",
        "source": "api",
        "reasonForFailure": None,
        "settlementStatus": None,
        "settlement": None,
        "mobileMoneyDetails": {
            "country": "zm",
            "phone": "0961111111",
            "operator": "mtn",
            "accountName": "Sandbox User",
            "operatorTransactionId": None,
        },
        "bankAccountDetails": None,
        "cardDetails": None,
    },
}

STATUS_FIXTURE: dict[str, Any] = {
    "status": True,
    "message": "ok",
    "data": {
        **COLLECTION_FIXTURE["data"],
        "status": "successful",
        "completedAt": "2026-07-10T10:05:00Z",
        "fee": "0.33",
        "mobileMoneyDetails": {
            **COLLECTION_FIXTURE["data"]["mobileMoneyDetails"],
            "operatorTransactionId": "MM-12345",
        },
    },
}

RESOLVE_FIXTURE: dict[str, Any] = {
    "status": True,
    "message": "resolved",
    "data": {"accountName": "JOHN BANDA"},
}

MOMO_PAYOUT_FIXTURE: dict[str, Any] = {
    "status": True,
    "message": "transfer initiated",
    "data": {
        "id": "22222222-2222-2222-2222-222222222222",
        "amount": "50.00",
        "fee": "2.50",
        "currency": "ZMW",
        "reference": "pay-vendor-42",
        "lencoReference": "240730050",
        "status": "pending",
        "reasonForFailure": None,
        "narration": "Vendor payout",
        "creditAccount": {
            "type": "mobile-money",
            "phone": "0961111111",
            "operator": "mtn",
            "accountName": "JOHN BANDA",
        },
    },
}

BANK_PAYOUT_FIXTURE: dict[str, Any] = {
    "status": True,
    "message": "transfer initiated",
    "data": {
        "id": "33333333-3333-3333-3333-333333333333",
        "amount": "200.00",
        "fee": "8.50",
        "currency": "ZMW",
        "reference": "pay-vendor-99",
        "lencoReference": "240730099",
        "status": "pending",
        "reasonForFailure": None,
        "narration": None,
        "creditAccount": {
            "type": "bank-account",
            "accountName": "ACME TRADERS LTD",
            "accountNumber": "1234567890",
            "bank": {"id": "bank-zm-1", "name": "Zanaco", "country": "zm"},
        },
    },
}


@pytest.fixture(autouse=True)
def lenco_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LENCO_API_TOKEN", TOKEN)
    monkeypatch.setenv("LENCO_ENV", "production")


def _make_transport(
    handler: Callable[[httpx.Request], httpx.Response],
) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def _route_handler(routes: dict[tuple[str, str], Any]) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.startswith("/access/v2"):
            path = path[len("/access/v2") :]
        key = (request.method.upper(), path)
        if key not in routes:
            return httpx.Response(404, json={"status": False, "message": "not found"})
        spec = routes[key]
        if callable(spec):
            return spec(request)
        status_code, body = spec
        return httpx.Response(status_code, json=body)

    return handler


@pytest.fixture
def lenco_client() -> LencoClient:
    routes: dict[tuple[str, str], Any] = {
        ("POST", "/collections/mobile-money"): (200, COLLECTION_FIXTURE),
        ("GET", "/collections/status/ord-order-1-attempt-1"): (200, STATUS_FIXTURE),
        ("POST", "/resolve/mobile-money"): (200, RESOLVE_FIXTURE),
        ("POST", "/transfers/mobile-money"): (200, MOMO_PAYOUT_FIXTURE),
        ("POST", "/transfers/bank-account"): (200, BANK_PAYOUT_FIXTURE),
    }
    transport = _make_transport(_route_handler(routes))
    http = httpx.AsyncClient(transport=transport, base_url=BASE_URL)
    return LencoClient(http_client=http, token=TOKEN, base_url=BASE_URL)


@pytest.fixture
def lenco_strategy(lenco_client: LencoClient) -> LencoStrategy:
    return LencoStrategy(lenco_client)


async def test_registry_registers_lenco_strategy() -> None:
    strategy = get("lenco")
    assert isinstance(strategy, LencoStrategy)


async def test_collection_contract_request_and_response(lenco_strategy: LencoStrategy) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        captured["raw"] = request.content.decode()
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json=COLLECTION_FIXTURE)

    transport = _make_transport(handler)
    http = httpx.AsyncClient(transport=transport, base_url=BASE_URL)
    client = LencoStrategy(LencoClient(http_client=http, token=TOKEN, base_url=BASE_URL))

    result = await client.initiate_collection(
        InitiateCollectionRequest(
            reference="ord-order-1-attempt-1",
            amount_ngwee=1300,
            phone="0961111111",
            operator="mtn",
        )
    )

    assert captured["auth"] == f"Bearer {TOKEN}"
    assert f'"amount":{ngwee_to_major_str(1300)}' in captured["raw"]
    assert captured["body"]["reference"] == "ord-order-1-attempt-1"
    assert captured["body"]["operator"] == "mtn"
    assert result.status.value == "pay-offline"
    assert result.amount_major == "13.00"
    assert result.provider_reference == "240730001"


async def test_query_status_contract(lenco_strategy: LencoStrategy) -> None:
    result = await lenco_strategy.query_status(
        QueryStatusRequest(reference="ord-order-1-attempt-1")
    )
    assert result.status == "successful"
    assert result.amount_major == "13.00"
    assert result.provider_reference == "240730001"


async def test_resolve_account_contract(lenco_strategy: LencoStrategy) -> None:
    result = await lenco_strategy.resolve_account(
        ResolveAccountRequest(phone="0961111111", operator="mtn")
    )
    assert result.account_name == "JOHN BANDA"


async def test_momo_payout_contract(lenco_strategy: LencoStrategy) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        captured["raw"] = request.content.decode()
        return httpx.Response(200, json=MOMO_PAYOUT_FIXTURE)

    transport = _make_transport(handler)
    http = httpx.AsyncClient(transport=transport, base_url=BASE_URL)
    client = LencoStrategy(LencoClient(http_client=http, token=TOKEN, base_url=BASE_URL))

    result = await client.initiate_momo_payout(
        LencoMomoPayoutRequest(
            reference="pay-vendor-42",
            amount_ngwee=5000,
            account_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            phone="0961111111",
            operator="mtn",
            narration="Vendor payout",
        )
    )

    assert f'"amount":{ngwee_to_major_str(5000)}' in captured["raw"]
    assert captured["body"]["accountId"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert captured["body"]["phone"] == "0961111111"
    assert result.amount_major == "50.00"
    assert result.status.value == "pending"


async def test_bank_payout_contract(lenco_strategy: LencoStrategy) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        captured["raw"] = request.content.decode()
        return httpx.Response(200, json=BANK_PAYOUT_FIXTURE)

    transport = _make_transport(handler)
    http = httpx.AsyncClient(transport=transport, base_url=BASE_URL)
    client = LencoStrategy(LencoClient(http_client=http, token=TOKEN, base_url=BASE_URL))

    result = await client.initiate_bank_payout(
        LencoBankPayoutRequest(
            reference="pay-vendor-99",
            amount_ngwee=20000,
            account_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            account_number="1234567890",
            bank_id="bank-zm-1",
        )
    )

    assert f'"amount":{ngwee_to_major_str(20000)}' in captured["raw"]
    assert captured["body"]["accountNumber"] == "1234567890"
    assert captured["body"]["bankId"] == "bank-zm-1"
    assert result.amount_major == "200.00"


@pytest.mark.parametrize(
    ("error_code", "message", "reason", "expected"),
    [
        ("02", "Insufficient funds", None, LencoErrorCategory.INSUFFICIENT),
        ("12", "Invalid mobile number", None, LencoErrorCategory.INVALID_NUMBER),
        ("09", "Auth denied", None, LencoErrorCategory.DECLINED),
        (None, "request timeout", None, LencoErrorCategory.TIMEOUT),
        (None, "Payment declined by operator", None, LencoErrorCategory.DECLINED),
        (None, "failed", "insufficient funds on wallet", LencoErrorCategory.INSUFFICIENT),
        (None, "failed", "invalid mobile number", LencoErrorCategory.INVALID_NUMBER),
    ],
)
def test_error_taxonomy_mapping(
    error_code: str | None,
    message: str | None,
    reason: str | None,
    expected: LencoErrorCategory,
) -> None:
    assert (
        map_lenco_failure(
            error_code=error_code,
            message=message,
            reason_for_failure=reason,
        )
        == expected
    )


async def test_collection_post_is_not_retried_on_server_error() -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(500, json={"status": False, "message": "server error"})

    transport = _make_transport(handler)
    http = httpx.AsyncClient(transport=transport, base_url=BASE_URL)
    client = LencoClient(http_client=http, token=TOKEN, base_url=BASE_URL)

    with pytest.raises(LencoClientError):
        await client.initiate_collection(
            LencoCollectionRequest(
                amount_major="10.00",
                reference="ord-retry-post-1",
                phone="0961111111",
                operator="mtn",
            )
        )

    assert attempts == 1


async def test_status_get_is_retried_on_server_error() -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < MAX_IDEMPOTENT_RETRIES:
            return httpx.Response(500, json={"status": False, "message": "server error"})
        return httpx.Response(200, json=STATUS_FIXTURE)

    transport = _make_transport(handler)
    http = httpx.AsyncClient(transport=transport, base_url=BASE_URL)
    client = LencoClient(http_client=http, token=TOKEN, base_url=BASE_URL)

    response = await client.query_collection_status("ord-order-1-attempt-1")
    assert response.data is not None
    assert response.data.status == "successful"
    assert attempts == MAX_IDEMPOTENT_RETRIES


async def test_zamtel_collection_blocked_without_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LENCO_ENABLE_ZAMTEL_COLLECTIONS", raising=False)
    client = LencoStrategy()

    with pytest.raises(LencoClientError) as exc_info:
        await client.initiate_collection(
            InitiateCollectionRequest(
                reference="ord-zamtel-1",
                amount_ngwee=1000,
                phone="0951111111",
                operator="zamtel",
            )
        )

    assert exc_info.value.category == LencoErrorCategory.PROVIDER_ERROR


async def test_zamtel_collection_allowed_with_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LENCO_ENABLE_ZAMTEL_COLLECTIONS", "true")

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        assert body["operator"] == "zamtel"
        return httpx.Response(200, json=COLLECTION_FIXTURE)

    transport = _make_transport(handler)
    http = httpx.AsyncClient(transport=transport, base_url=BASE_URL)
    client = LencoStrategy(LencoClient(http_client=http, token=TOKEN, base_url=BASE_URL))

    await client.initiate_collection(
        InitiateCollectionRequest(
            reference="ord-zamtel-2",
            amount_ngwee=1000,
            phone="0951111111",
            operator="zamtel",
        )
    )


def test_build_json_body_embeds_amount_as_json_number_literal() -> None:
    body = _build_json_body({"amount": "1234.56", "reference": "ord-1"})
    assert '"amount":1234.56' in body
    parsed = json.loads(body)
    assert parsed["amount"] == 1234.56
    assert parsed["reference"] == "ord-1"


def test_verify_webhook_signature() -> None:
    raw_body = b'{"event":"collection.successful","data":{"id":"evt-1"}}'
    signing_key = hashlib.sha256(TOKEN.encode("utf-8")).hexdigest().encode("utf-8")
    signature = hmac.new(signing_key, raw_body, hashlib.sha512).hexdigest()

    client = LencoClient(token=TOKEN, base_url=BASE_URL)
    assert client.verify_webhook_signature(raw_body=raw_body, signature=signature) is True
    assert client.verify_webhook_signature(raw_body=raw_body, signature="deadbeef") is False


async def test_verify_webhook_strategy_extracts_event_id() -> None:
    raw_body = b'{"event":"collection.successful","data":{"id":"evt-abc-123"}}'
    signing_key = hashlib.sha256(TOKEN.encode("utf-8")).hexdigest().encode("utf-8")
    signature = hmac.new(signing_key, raw_body, hashlib.sha512).hexdigest()

    client = LencoStrategy(LencoClient(token=TOKEN, base_url=BASE_URL))
    result = await client.verify_webhook(
        VerifyWebhookRequest(raw_body=raw_body, signature=signature)
    )
    assert result.valid is True
    assert result.event_id == "evt-abc-123"


async def test_insufficient_funds_error_from_api_envelope() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"status": False, "message": "Insufficient funds", "errorCode": "02"},
        )

    transport = _make_transport(handler)
    http = httpx.AsyncClient(transport=transport, base_url=BASE_URL)
    client = LencoClient(http_client=http, token=TOKEN, base_url=BASE_URL)

    with pytest.raises(LencoClientError) as exc_info:
        await client.query_collection_status("ord-insufficient-1")

    assert exc_info.value.category == LencoErrorCategory.INSUFFICIENT
