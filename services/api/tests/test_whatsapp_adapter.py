"""Tests for WhatsApp Cloud API adapter and template registry."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from app.services.notifications.adapters.base import FailureKind, OutboxMessage
from app.services.notifications.adapters.whatsapp import (
    WhatsAppAdapter,
    classify_whatsapp_error,
)
from app.services.notifications.templates.whatsapp import (
    WHATSAPP_TEMPLATES,
    build_cloud_api_template,
    format_k,
    render_whatsapp_template,
)

FIXTURE_TO = "+260971234567"
FIXTURE_ORDER = "ord-abc123"
FIXTURE_TRACK = "https://vergeo5.com/en/orders/ord-abc123"
MONEY_NGEWEE = 123_456
MONEY_FORMATTED = "K1,234.56"


@pytest.fixture
def base_payload() -> dict[str, Any]:
    return {
        "to": FIXTURE_TO,
        "locale": "en",
        "order_reference": FIXTURE_ORDER,
    }


def test_format_k_ngwee_correct() -> None:
    assert format_k(MONEY_NGEWEE) == MONEY_FORMATTED
    assert format_k(0) == "K0.00"
    assert format_k(1) == "K0.01"


@pytest.mark.parametrize("template_id", list(WHATSAPP_TEMPLATES.keys()))
def test_each_template_renders_with_fixture_vars(
    template_id: str,
    base_payload: dict[str, Any],
) -> None:
    payload = _fixture_payload_for(template_id, base_payload)
    rendered = render_whatsapp_template(template_id, payload)
    assert rendered.template_id == template_id
    assert rendered.to_e164 == FIXTURE_TO
    assert rendered.language_code == "en"
    assert len(rendered.body_parameters) >= 1

    if template_id == "order_confirmed":
        assert rendered.body_parameters[1] == MONEY_FORMATTED
    if template_id == "payment_received":
        assert MONEY_FORMATTED in rendered.body_parameters[0]
    if template_id == "vendor_new_order":
        assert rendered.body_parameters[2] == "2"
    if template_id == "otp_login":
        assert rendered.body_parameters[0] == "482913"
        assert rendered.button_parameters == ("482913",)


def _fixture_payload_for(template_id: str, base: dict[str, Any]) -> dict[str, Any]:
    payload = dict(base)
    if template_id == "order_confirmed":
        payload["total_ngwee"] = MONEY_NGEWEE
        payload["track_url"] = FIXTURE_TRACK
    elif template_id == "payment_received":
        payload["amount_ngwee"] = MONEY_NGEWEE
    elif template_id == "order_shipped":
        payload["tracking_info"] = f"Track: {FIXTURE_TRACK}"
    elif template_id == "order_ready_pickup":
        payload["pickup_details"] = "Collect at Kamwala Trading, stand 12."
    elif template_id == "order_delivered":
        payload["review_url"] = f"{FIXTURE_TRACK}/review"
    elif template_id == "vendor_new_order":
        payload["product_title"] = "Samsung A15 128GB"
        payload["quantity"] = 2
    elif template_id == "otp_login":
        payload["otp_code"] = "482913"
    return payload


def test_payment_received_i18n_slot(base_payload: dict[str, Any]) -> None:
    payload = {
        **base_payload,
        "locale": "bem",
        "amount_ngwee": MONEY_NGEWEE,
        "i18n_slots": {
            "trust_narrative": (
                f"K{MONEY_FORMATTED[1:]} yenu yikwata bwino na Vergeo5 mpaka kufika."
            ),
        },
    }
    rendered = render_whatsapp_template("payment_received", payload)
    assert rendered.language_code == "bem_ZM"
    assert "yikwata bwino" in rendered.body_parameters[0]


@pytest.mark.parametrize(
    ("http_status", "error_code", "error_subcode", "message", "expected"),
    [
        (429, None, None, "Too many requests", FailureKind.RETRYABLE),
        (500, None, None, "Internal error", FailureKind.RETRYABLE),
        (400, 100, 132001, "Template name does not exist", FailureKind.PERMANENT),
        (400, 100, 131026, "Recipient is not a valid WhatsApp user", FailureKind.PERMANENT),
        (400, 100, 132000, "Number of parameters does not match", FailureKind.PERMANENT),
    ],
)
def test_error_taxonomy(
    http_status: int,
    error_code: int | None,
    error_subcode: int | None,
    message: str,
    expected: FailureKind,
) -> None:
    assert (
        classify_whatsapp_error(
            http_status=http_status,
            error_code=error_code,
            error_subcode=error_subcode,
            error_message=message,
        )
        == expected
    )


@pytest.mark.asyncio
async def test_send_builds_cloud_api_payload_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"messages": [{"id": "wamid.test"}]})

    monkeypatch.setenv("WHATSAPP_TOKEN", "test-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "1234567890")

    transport = httpx.MockTransport(handler)
    adapter = WhatsAppAdapter(client=httpx.AsyncClient(transport=transport))
    message = OutboxMessage(
        id="outbox-1",
        dedupe_key="order_confirmed:ord-abc123:whatsapp",
        channel="whatsapp",
        template="order_confirmed",
        payload={
            "to": FIXTURE_TO,
            "locale": "en",
            "order_reference": FIXTURE_ORDER,
            "total_ngwee": MONEY_NGEWEE,
            "track_url": FIXTURE_TRACK,
        },
    )

    result = await adapter.send(message)
    assert result.success is True

    assert captured["url"] == "https://graph.facebook.com/v23.0/1234567890/messages"
    assert captured["headers"]["authorization"] == "Bearer test-token"

    body = captured["body"]
    assert body["messaging_product"] == "whatsapp"
    assert body["to"] == FIXTURE_TO
    assert body["type"] == "template"
    assert body["template"]["name"] == "order_confirmed"
    assert body["template"]["language"] == {"code": "en"}
    params = body["template"]["components"][0]["parameters"]
    assert params[0]["text"] == FIXTURE_ORDER
    assert params[1]["text"] == MONEY_FORMATTED
    assert params[2]["text"] == FIXTURE_TRACK


@pytest.mark.asyncio
async def test_send_rate_limit_is_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={"error": {"message": "Rate limit hit", "code": 130429}},
        )

    monkeypatch.setenv("WHATSAPP_TOKEN", "test-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "1234567890")

    transport = httpx.MockTransport(handler)
    adapter = WhatsAppAdapter(client=httpx.AsyncClient(transport=transport))
    message = OutboxMessage(
        id="outbox-2",
        dedupe_key="order_confirmed:ord-xyz:whatsapp",
        channel="whatsapp",
        template="order_confirmed",
        payload=_fixture_payload_for(
            "order_confirmed",
            {"to": FIXTURE_TO, "locale": "en", "order_reference": FIXTURE_ORDER},
        ),
    )

    result = await adapter.send(message)
    assert result.success is False
    assert result.failure_kind == FailureKind.RETRYABLE


@pytest.mark.asyncio
async def test_send_invalid_template_is_permanent(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": {
                    "message": "Template name does not exist in the translation",
                    "code": 100,
                    "error_subcode": 132001,
                }
            },
        )

    monkeypatch.setenv("WHATSAPP_TOKEN", "test-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "1234567890")

    transport = httpx.MockTransport(handler)
    adapter = WhatsAppAdapter(client=httpx.AsyncClient(transport=transport))
    message = OutboxMessage(
        id="outbox-3",
        dedupe_key="order_confirmed:ord-bad:whatsapp",
        channel="whatsapp",
        template="order_confirmed",
        payload=_fixture_payload_for(
            "order_confirmed",
            {"to": FIXTURE_TO, "locale": "en", "order_reference": FIXTURE_ORDER},
        ),
    )

    result = await adapter.send(message)
    assert result.success is False
    assert result.failure_kind == FailureKind.PERMANENT


def test_build_cloud_api_template_otp_has_button() -> None:
    rendered = render_whatsapp_template(
        "otp_login",
        {"to": FIXTURE_TO, "locale": "en", "otp_code": "482913"},
    )
    payload = build_cloud_api_template(rendered)
    components = payload["template"]["components"]
    assert components[0]["type"] == "body"
    assert components[1]["type"] == "button"
    assert components[1]["sub_type"] == "url"
    assert components[1]["parameters"][0]["text"] == "482913"


def test_access_token_fallback_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WHATSAPP_TOKEN", raising=False)
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "fallback-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "999")

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer fallback-token"
        return httpx.Response(200, json={"messages": [{"id": "wamid.fb"}]})

    async def _run() -> None:
        transport = httpx.MockTransport(handler)
        adapter = WhatsAppAdapter(client=httpx.AsyncClient(transport=transport))
        message = OutboxMessage(
            id="outbox-4",
            dedupe_key="otp:1:whatsapp",
            channel="whatsapp",
            template="otp_login",
            payload={"to": FIXTURE_TO, "locale": "en", "otp_code": "123456"},
        )
        result = await adapter.send(message)
        assert result.success is True

    import asyncio

    asyncio.run(_run())
