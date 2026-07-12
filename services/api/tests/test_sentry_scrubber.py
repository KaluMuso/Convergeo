"""PII-scrubber invariant tests for app.core.sentry.

Asserts that phone / address / email / token are masked in BOTH the event body and
breadcrumbs, and that init_sentry no-ops without a DSN (dev/CI safe)."""

from __future__ import annotations

import json

from app.core.sentry import (
    EMAIL_MASK,
    PHONE_MASK,
    REDACTED,
    TOKEN_MASK,
    before_breadcrumb,
    before_send,
    init_sentry,
    scrub,
)
from app.settings import Settings

PHONE = "+260977123456"
LOCAL_PHONE = "0977123456"
EMAIL = "buyer@example.com"
ADDRESS = "Plot 12, Great East Road, near Manda Hill, Lusaka"
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abc-123_XYZ"
BEARER = "Bearer sk_live_supersecrettoken0099"


def _blob(value: object) -> str:
    return json.dumps(value)


def test_sensitive_keys_redacted_in_event() -> None:
    event = {
        "request": {
            "data": {
                "phone": PHONE,
                "delivery_address": ADDRESS,
                "user_email": EMAIL,
                "access_token": BEARER,
                "quantity": 3,
            }
        },
        "user": {"id": "user-1", "email": EMAIL, "phone_number": PHONE},
    }
    scrubbed = before_send(event)
    data = scrubbed["request"]["data"]
    assert data["phone"] == REDACTED
    assert data["delivery_address"] == REDACTED
    assert data["user_email"] == REDACTED
    assert data["access_token"] == REDACTED
    # Non-PII field untouched.
    assert data["quantity"] == 3
    assert scrubbed["user"]["id"] == "user-1"
    assert scrubbed["user"]["email"] == REDACTED
    assert scrubbed["user"]["phone_number"] == REDACTED
    # None of the raw PII survives anywhere in the serialised event.
    blob = _blob(scrubbed)
    for pii in (PHONE, EMAIL, ADDRESS, "supersecrettoken"):
        assert pii not in blob


def test_free_text_patterns_masked_in_event_message() -> None:
    event = {
        "message": (
            f"login failed for {EMAIL} from {PHONE} using {BEARER} and jwt {JWT}"
        ),
        "logentry": {"message": f"local number {LOCAL_PHONE} bounced"},
    }
    scrubbed = before_send(event)
    msg = scrubbed["message"]
    assert EMAIL not in msg and EMAIL_MASK in msg
    assert PHONE not in msg and PHONE_MASK in msg
    assert "supersecrettoken" not in msg and TOKEN_MASK in msg
    assert JWT not in msg and TOKEN_MASK in msg
    assert LOCAL_PHONE not in scrubbed["logentry"]["message"]
    assert PHONE_MASK in scrubbed["logentry"]["message"]


def test_breadcrumbs_scrubbed() -> None:
    crumb = {
        "category": "http",
        "message": f"POST /orders phone={PHONE} email={EMAIL}",
        "data": {
            "authorization": BEARER,
            "address": ADDRESS,
            "note": f"contact {LOCAL_PHONE}",
        },
    }
    scrubbed = before_breadcrumb(crumb)
    assert scrubbed["data"]["authorization"] == REDACTED
    assert scrubbed["data"]["address"] == REDACTED
    assert PHONE_MASK in scrubbed["message"]
    assert EMAIL_MASK in scrubbed["message"]
    assert LOCAL_PHONE not in scrubbed["data"]["note"]
    blob = _blob(scrubbed)
    for pii in (PHONE, EMAIL, ADDRESS, "supersecrettoken", LOCAL_PHONE):
        assert pii not in blob


def test_nested_lists_scrubbed() -> None:
    event = {
        "exception": {
            "values": [
                {"type": "ValueError", "value": f"bad phone {PHONE}"},
                {"type": "KeyError", "value": f"missing {EMAIL}"},
            ]
        },
        "extra": {"recipients": [{"email": EMAIL}, {"phone": PHONE}]},
    }
    scrubbed = before_send(event)
    values = scrubbed["exception"]["values"]
    assert PHONE_MASK in values[0]["value"]
    assert EMAIL_MASK in values[1]["value"]
    assert scrubbed["extra"]["recipients"][0]["email"] == REDACTED
    assert scrubbed["extra"]["recipients"][1]["phone"] == REDACTED


def test_scrub_leaves_non_pii_scalars() -> None:
    assert scrub(42) == 42
    assert scrub(True) is True
    assert scrub(None) is None
    assert scrub("order ord-abc123 total K1,234.56") == "order ord-abc123 total K1,234.56"


def test_init_sentry_noop_without_dsn() -> None:
    settings = Settings(
        SUPABASE_URL="https://example.supabase.co",
        SUPABASE_SERVICE_ROLE_KEY="k",
        SUPABASE_ANON_KEY="k",
    )
    assert settings.sentry_dsn == ""
    # No DSN -> must not initialise the SDK (no network, CI-safe).
    assert init_sentry(settings) is False
