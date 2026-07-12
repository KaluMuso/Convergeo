"""Sentry initialisation + PII scrubbing for the Vergeo5 API.

The scrubber (`scrub`) is the core invariant of this module: no phone number,
street/landmark address, email, or auth token may ever leave the process inside a
Sentry event or breadcrumb. It runs on BOTH the event body (`before_send`) and every
breadcrumb (`before_breadcrumb`).

`init_sentry` is a strict no-op when `SENTRY_DSN` is unset, so development and CI never
talk to Sentry and never need a DSN. Live capture is founder-gated on a real DSN.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.settings import Settings

# --- Redaction markers (stable — asserted by tests) --------------------------
REDACTED = "[redacted]"
EMAIL_MASK = "[redacted-email]"
PHONE_MASK = "[redacted-phone]"
TOKEN_MASK = "[redacted-token]"

# Keys whose VALUE is PII regardless of content — redacted wholesale (recursively).
# Matched case-insensitively as a substring of the key, so `user_email`,
# `delivery_address`, `x-authorization` etc. all match.
_SENSITIVE_KEY_PARTS: tuple[str, ...] = (
    "phone",
    "msisdn",
    "mobile",
    "tel",
    "email",
    "address",
    "street",
    "landmark",
    "gps",
    "latitude",
    "longitude",
    "coordinate",
    "token",
    "authorization",
    "password",
    "passwd",
    "secret",
    "api_key",
    "apikey",
    "otp",
    "pin",
)

# Value-level patterns applied to free-text strings (e.g. a log message or a
# stringified payload) where PII is not isolated behind a well-known key.
_TOKEN_RE = re.compile(
    r"(?i)bearer\s+[A-Za-z0-9._\-]+"  # `Bearer <jwt|opaque>`
    r"|\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b"  # bare JWT
)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(
    r"\+260\d{9}"  # Zambia E.164
    r"|(?<!\d)0\d{9}(?!\d)"  # Zambia local (0977xxxxxx)
    r"|\+\d{10,15}"  # generic international E.164
)


def _scrub_text(text: str) -> str:
    """Mask PII patterns inside a free-text string. Order matters: tokens first
    (they can embed `.`), then emails, then phone numbers."""
    text = _TOKEN_RE.sub(TOKEN_MASK, text)
    text = _EMAIL_RE.sub(EMAIL_MASK, text)
    text = _PHONE_RE.sub(PHONE_MASK, text)
    return text


def _key_is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)


def scrub(obj: Any) -> Any:
    """Recursively scrub PII from an arbitrary JSON-like structure.

    - dict: a key that names PII (phone/address/email/token/...) has its whole
      value redacted; other values are recursed into.
    - list/tuple: every item is scrubbed.
    - str: PII patterns (email/phone/token) are masked in place.
    - other scalars: returned unchanged.
    """
    if isinstance(obj, dict):
        scrubbed: dict[Any, Any] = {}
        for key, value in obj.items():
            if isinstance(key, str) and _key_is_sensitive(key):
                scrubbed[key] = REDACTED
            else:
                scrubbed[key] = scrub(value)
        return scrubbed
    if isinstance(obj, (list, tuple)):
        return [scrub(item) for item in obj]
    if isinstance(obj, str):
        return _scrub_text(obj)
    return obj


def before_send(event: dict[str, Any], _hint: dict[str, Any] | None = None) -> dict[str, Any]:
    """Sentry `before_send` hook — scrub the entire event body."""
    return scrub(event)  # type: ignore[no-any-return]


def before_breadcrumb(
    crumb: dict[str, Any], _hint: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Sentry `before_breadcrumb` hook — scrub each breadcrumb (message + data)."""
    return scrub(crumb)  # type: ignore[no-any-return]


def init_sentry(settings: Settings) -> bool:
    """Initialise Sentry from settings. No-op (returns False) when no DSN is set,
    so dev/CI never emit events and no DSN is required. Returns True when init ran."""
    dsn = settings.sentry_dsn
    if not dsn:
        return False

    import sentry_sdk

    sentry_sdk.init(
        dsn=dsn,
        environment=settings.sentry_environment or settings.env,
        release=settings.sentry_release or None,
        # PII scrubbing invariant — both hooks are mandatory. The SDK types these
        # against its Event TypedDict; our hooks operate on the plain event dict.
        before_send=before_send,  # type: ignore[arg-type]
        before_breadcrumb=before_breadcrumb,
        # Never let the SDK attach request bodies / headers / cookies itself.
        send_default_pii=False,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        max_breadcrumbs=50,
    )
    return True
