"""Notification template i18n, classification, and quiet-hours compliance tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from app.services.notifications.dispatcher import (
    DEFAULT_RECIPIENT_TZ,
    TEMPLATE_CLASSIFICATION,
    TemplateClass,
    get_template_class,
    is_quiet_hours,
    next_marketing_send_at,
    should_send_now,
)
from app.services.notifications.templates.whatsapp import WHATSAPP_TEMPLATES

REPO_ROOT = Path(__file__).resolve().parents[3]
MESSAGES_DIR = REPO_ROOT / "packages" / "i18n" / "messages"

LOCALE_FALLBACK_MATRIX = (
    "whatsapp.order_confirmed.body",
    "whatsapp.payment_received.body",
    "whatsapp.payment_received.trust_narrative",
    "whatsapp.order_shipped.body",
    "whatsapp.order_ready_pickup.body",
    "whatsapp.order_delivered.body",
    "whatsapp.vendor_new_order.body",
    "whatsapp.otp_login.body",
    "sms.order_confirmed.body",
    "sms.payment_received.body",
    "email.receipt.subject",
    "email.receipt.body",
    "email.kyc.approved.subject",
    "email.kyc.rejected.body",
    "marketing.review_request.body",
    "marketing.abandoned_cart_recovery.body",
    "compliance.stopReply",
)


def _load_locale_messages(locale: str) -> dict[str, Any]:
    path = MESSAGES_DIR / locale / "notifications.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        msg = f"invalid notifications.json for locale {locale!r}"
        raise TypeError(msg)
    return raw


def _get_nested(node: dict[str, Any], key_path: str) -> Any:
    current: Any = node
    for part in key_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def resolve_notification_message(locale: str, key_path: str) -> str:
    """Resolve a dotted key from notifications.json with EN fallback markers."""
    locale_messages = _load_locale_messages(locale)
    en_messages = _load_locale_messages("en")

    locale_node = _get_nested(locale_messages, key_path)
    if isinstance(locale_node, str) and locale_node.strip():
        return locale_node

    if isinstance(locale_node, dict):
        if locale_node.get("__fallback") == "en":
            en_value = _get_nested(en_messages, key_path)
            if isinstance(en_value, str):
                return en_value
        for value in locale_node.values():
            if isinstance(value, str) and value.strip() and value != "en":
                return value

    en_value = _get_nested(en_messages, key_path)
    if isinstance(en_value, str):
        return en_value

    msg = f"missing notification message: {locale}:{key_path}"
    raise KeyError(msg)


def _lusaka_local(hour: int, minute: int = 0) -> datetime:
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(DEFAULT_RECIPIENT_TZ)
    return datetime(2026, 7, 10, hour, minute, tzinfo=tz).astimezone(UTC)


@pytest.mark.parametrize("key_path", LOCALE_FALLBACK_MATRIX)
def test_locale_fallback_matrix_resolves_en(key_path: str) -> None:
    message = resolve_notification_message("en", key_path)
    assert message.strip()


@pytest.mark.parametrize("key_path", LOCALE_FALLBACK_MATRIX)
def test_bem_nya_fallback_to_en_when_marked(key_path: str) -> None:
    en_message = resolve_notification_message("en", key_path)
    for locale in ("bem", "nya"):
        resolved = resolve_notification_message(locale, key_path)
        assert resolved.strip()
        locale_node = _get_nested(_load_locale_messages(locale), key_path)
        if isinstance(locale_node, dict) and locale_node.get("__fallback") == "en":
            assert resolved == en_message
        elif isinstance(locale_node, str):
            assert resolved == locale_node


def test_bem_whatsapp_slots_have_local_copy() -> None:
    bem_trust = resolve_notification_message("bem", "whatsapp.payment_received.trust_narrative")
    en_trust = resolve_notification_message("en", "whatsapp.payment_received.trust_narrative")
    assert bem_trust != en_trust
    assert "Vergeo5" in bem_trust


def test_nya_whatsapp_order_confirmed_has_local_copy() -> None:
    nya_body = resolve_notification_message("nya", "whatsapp.order_confirmed.body")
    en_body = resolve_notification_message("en", "whatsapp.order_confirmed.body")
    assert nya_body != en_body
    assert "Vergeo5" in nya_body


@pytest.mark.parametrize(
    ("hour", "expected_quiet"),
    [
        (20, False),
        (21, True),
        (23, True),
        (0, True),
        (6, True),
        (7, False),
    ],
)
def test_is_quiet_hours_boundaries(hour: int, expected_quiet: bool) -> None:
    from zoneinfo import ZoneInfo

    local = datetime(2026, 7, 10, hour, 0, tzinfo=ZoneInfo(DEFAULT_RECIPIENT_TZ))
    assert is_quiet_hours(local) is expected_quiet


@pytest.mark.parametrize(
    ("hour", "marketing_sends"),
    [
        (20, True),
        (21, False),
        (6, False),
        (7, True),
    ],
)
def test_should_send_now_marketing_quiet_hours(hour: int, marketing_sends: bool) -> None:
    now = _lusaka_local(hour)
    assert (
        should_send_now(TemplateClass.MARKETING, now, DEFAULT_RECIPIENT_TZ) is marketing_sends
    )


@pytest.mark.parametrize("hour", [20, 21, 6, 7, 12])
def test_should_send_now_transactional_always(hour: int) -> None:
    now = _lusaka_local(hour)
    assert should_send_now(TemplateClass.TRANSACTIONAL, now, DEFAULT_RECIPIENT_TZ) is True


def test_next_marketing_send_at_deferred_to_seven_am() -> None:
    now = _lusaka_local(21, 30)
    next_at = next_marketing_send_at(now, DEFAULT_RECIPIENT_TZ)
    from zoneinfo import ZoneInfo

    local_next = next_at.astimezone(ZoneInfo(DEFAULT_RECIPIENT_TZ))
    assert local_next.hour == 7
    assert local_next.minute == 0
    assert local_next.date() == datetime(2026, 7, 11).date()


def test_next_marketing_send_at_before_seven_same_day() -> None:
    now = _lusaka_local(3, 15)
    next_at = next_marketing_send_at(now, DEFAULT_RECIPIENT_TZ)
    from zoneinfo import ZoneInfo

    local_next = next_at.astimezone(ZoneInfo(DEFAULT_RECIPIENT_TZ))
    assert local_next.hour == 7
    assert local_next.date() == datetime(2026, 7, 10).date()


@pytest.mark.parametrize("template_id", list(WHATSAPP_TEMPLATES.keys()))
def test_whatsapp_templates_classified_transactional(template_id: str) -> None:
    assert get_template_class(template_id) is TemplateClass.TRANSACTIONAL


@pytest.mark.parametrize(
    ("template_id", "expected"),
    [
        ("review_request", TemplateClass.MARKETING),
        ("abandoned_cart_recovery", TemplateClass.MARKETING),
        ("kyc_nudge", TemplateClass.MARKETING),
        ("compliance_confirmation", TemplateClass.TRANSACTIONAL),
        ("payment_receipt", TemplateClass.TRANSACTIONAL),
        ("payout_failure_alert", TemplateClass.TRANSACTIONAL),
        ("low_stock_alert", TemplateClass.TRANSACTIONAL),
    ],
)
def test_template_classification_correctness(template_id: str, expected: TemplateClass) -> None:
    assert get_template_class(template_id) is expected
    assert TEMPLATE_CLASSIFICATION[template_id] is expected


def test_all_classified_templates_have_message_keys() -> None:
    for template_id in TEMPLATE_CLASSIFICATION:
        if template_id in WHATSAPP_TEMPLATES:
            if template_id == "compliance_confirmation":
                # STOP/START ack copy is resolved at enqueue into confirmation_body.
                continue
            resolve_notification_message("en", f"whatsapp.{template_id}.body")
        elif template_id in {"payment_receipt"}:
            resolve_notification_message("en", "email.receipt.subject")
        elif template_id == "order_receipt":
            resolve_notification_message("en", "email.order_receipt.subject")
        elif template_id == "kyc_approved":
            resolve_notification_message("en", "email.kyc.approved.subject")
        elif template_id == "kyc_rejected":
            resolve_notification_message("en", "email.kyc.rejected.subject")
        elif template_id in {
            "review_request",
            "abandoned_cart_recovery",
            "kyc_nudge",
            "low_stock_alert",
            "payout_failure_alert",
        }:
            resolve_notification_message("en", f"marketing.{template_id}.body")
