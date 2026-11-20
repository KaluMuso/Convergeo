"""E1/E4: lifecycle events that used to be silent now map to full templates."""

from __future__ import annotations

from typing import Any

import pytest
from app.services.notifications.adapters.email import render_email_html
from app.services.notifications.dispatcher import TEMPLATE_CLASSIFICATION, TemplateClass
from app.services.notifications.events import EVENT_REGISTRY, Audience
from app.services.notifications.templates.sms import render_sms_body
from app.services.notifications.templates.whatsapp import (
    render_whatsapp_template,
)

NEW_EVENTS = {
    "order_cancelled": Audience.CUSTOMER,
    "order_completed": Audience.CUSTOMER,
    "payment_failed": Audience.CUSTOMER,
    "payout_sent": Audience.VENDOR,
    "payout_failed": Audience.VENDOR,
    "ticket_issued": Audience.CUSTOMER,
    "dispute_opened": Audience.VENDOR,
    "dispute_resolved": Audience.CUSTOMER,
    "quote_received": Audience.CUSTOMER,
    "quote_accepted": Audience.VENDOR,
}

PAYLOAD: dict[str, Any] = {
    "to": "+260971234567",
    "locale": "en",
    "order_reference": "ord-abc123",
    "amount_ngwee": 290000,
    "destination_label": "MTN number ending 1234",
    "event_title": "Jazz Night",
    "quote_price_ngwee": 150000,
    "deposit_ngwee": 50000,
    "total_job_ngwee": 150000,
}


@pytest.mark.parametrize(("event", "audience"), sorted(NEW_EVENTS.items()))
def test_event_is_mapped_and_renders_on_every_channel(event: str, audience: Audience) -> None:
    mapping = EVENT_REGISTRY[event]
    assert mapping is not None
    assert mapping.audience is audience
    template = mapping.template
    assert TEMPLATE_CLASSIFICATION[template] is TemplateClass.TRANSACTIONAL
    assert render_whatsapp_template(template, PAYLOAD).body_parameters
    sms = render_sms_body(template, PAYLOAD)
    assert sms
    subject, html_body, _, _ = render_email_html(template, payload=PAYLOAD)
    assert subject.strip()
    assert "{" not in html_body


def test_payout_sent_uses_formatk_and_destination() -> None:
    rendered = render_whatsapp_template("payout_sent", PAYLOAD)
    assert rendered.body_parameters == ("K2,900.00", "MTN number ending 1234")


def test_payout_sms_amount_is_integer_ngwee_derived() -> None:
    sms = render_sms_body("payout_sent", PAYLOAD) or ""
    assert "2900.00" in sms
    assert "MTN number ending 1234" in sms


def test_money_must_be_integer_ngwee() -> None:
    with pytest.raises(ValueError):
        render_whatsapp_template("payout_sent", {**PAYLOAD, "amount_ngwee": 29.5})
    with pytest.raises(ValueError):
        render_whatsapp_template("payment_failed", {**PAYLOAD, "amount_ngwee": None})


def test_optional_slots_never_empty_or_multiline() -> None:
    rendered = render_whatsapp_template(
        "order_cancelled", {**PAYLOAD, "refund_detail": "  line one\nline two  "}
    )
    assert rendered.body_parameters[1] == "line one line two"
    fallback = render_whatsapp_template("order_cancelled", PAYLOAD)
    assert fallback.body_parameters[1].strip()


def test_email_escapes_html_in_new_slots() -> None:
    _, body, _, _ = render_email_html(
        "dispute_resolved", payload={**PAYLOAD, "resolution_summary": "<script>x</script>"}
    )
    assert "<script>" not in body


def test_quote_events_reuse_approved_templates() -> None:
    assert EVENT_REGISTRY["quote_received"].template == "rfq_quoted"  # type: ignore[union-attr]
    assert EVENT_REGISTRY["quote_accepted"].template == "service_quote_accepted"  # type: ignore[union-attr]
