"""Every email goes out under a fixed, filterable sender and subject prefix (King, 28 Nov 2026)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from app.services.notifications.adapters.base import OutboxMessage
from app.services.notifications.adapters.email import (
    EMAIL_TEMPLATES,
    TEMPLATE_STREAMS,
    ResendEmailAdapter,
    email_stream_for,
    render_email_html,
)

EXPECTED = {
    "order_confirmed": ("Vergeo5 Orders <orders@mail.vergeo5.com>", "[Vergeo5 Order] "),
    "vendor_new_order": ("Vergeo5 Orders <orders@mail.vergeo5.com>", "[Vergeo5 Order] "),
    "ticket_issued": ("Vergeo5 Orders <orders@mail.vergeo5.com>", "[Vergeo5 Order] "),
    "payment_receipt": ("Vergeo5 Payments <payments@mail.vergeo5.com>", "[Vergeo5 Payment] "),
    "payment_failed": ("Vergeo5 Payments <payments@mail.vergeo5.com>", "[Vergeo5 Payment] "),
    "payout_sent": ("Vergeo5 Payments <payments@mail.vergeo5.com>", "[Vergeo5 Payment] "),
    "payout_failed": ("Vergeo5 Payments <payments@mail.vergeo5.com>", "[Vergeo5 Payment] "),
    "kyc_approved": ("Vergeo5 Vendors <vendors@mail.vergeo5.com>", "[Vergeo5 Vendor] "),
    "kyc_rejected": ("Vergeo5 Vendors <vendors@mail.vergeo5.com>", "[Vergeo5 Vendor] "),
    "business_verified": ("Vergeo5 Vendors <vendors@mail.vergeo5.com>", "[Vergeo5 Vendor] "),
}


def test_every_template_has_an_explicit_stream() -> None:
    assert set(TEMPLATE_STREAMS) == set(EMAIL_TEMPLATES)


def test_unknown_template_uses_payment_receipt_stream() -> None:
    # render_email_html falls back to payment_receipt, so the sender must match it.
    assert email_stream_for("no_such_template") is TEMPLATE_STREAMS["payment_receipt"]
    assert email_stream_for(None) is TEMPLATE_STREAMS["payment_receipt"]


@pytest.mark.parametrize("template", sorted(EMAIL_TEMPLATES))
def test_subject_starts_with_stream_prefix_once(template: str) -> None:
    subject, _, _, _ = render_email_html(template, payload={"order_id": "ord-1"})
    prefix = TEMPLATE_STREAMS[template].subject_prefix
    assert subject.startswith(prefix + " ")
    assert subject.count("[Vergeo5") == 1
    assert "Convergeo" not in subject


@pytest.mark.asyncio
@pytest.mark.parametrize(("template", "expected"), sorted(EXPECTED.items()))
async def test_resend_payload_uses_stream_sender_and_support_reply_to(
    template: str, expected: tuple[str, str]
) -> None:
    sender, prefix = expected
    bodies: list[dict[str, Any]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "email-1"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = ResendEmailAdapter(api_key="re_test", client=client)
    message = OutboxMessage(
        id=f"msg-{template}",
        dedupe_key=f"{template}:email",
        channel="email",
        template=template,
        payload={"email": "buyer@example.com", "order_id": "ord-7"},
    )
    assert (await adapter.send(message)).success is True
    body = bodies[0]
    assert body["from"] == sender
    assert body["reply_to"] == "support@vergeo5.com"
    assert body["subject"].startswith(prefix)


def test_from_env_reads_domain_and_reply_to(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("RESEND_SENDER_DOMAIN", "vergeo5.com")
    monkeypatch.setenv("RESEND_REPLY_TO", "help@vergeo5.com")
    adapter = ResendEmailAdapter.from_env()
    assert adapter.sender_domain == "vergeo5.com"
    assert adapter.reply_to == "help@vergeo5.com"
    assert email_stream_for("payout_sent").sender(adapter.sender_domain) == (
        "Vergeo5 Payments <payments@vergeo5.com>"
    )


def test_from_env_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("RESEND_SENDER_DOMAIN", "")
    monkeypatch.delenv("RESEND_REPLY_TO", raising=False)
    adapter = ResendEmailAdapter.from_env()
    assert adapter.sender_domain == "mail.vergeo5.com"
    assert adapter.reply_to == "support@vergeo5.com"
