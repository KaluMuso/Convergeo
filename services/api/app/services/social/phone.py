"""Phone hashing for contact discovery — client SHA-256, server HMAC pepper."""

from __future__ import annotations

import hashlib
import hmac
import re
from typing import Final

from app.errors import AppError
from app.settings import Settings, get_settings

_HEX64: Final = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)
_ZM_MOBILE: Final = re.compile(r"^260[79][5-7]\d{7}$")


def normalize_to_e164(raw: str) -> str | None:
    """Zambian local numbers → +260…; other numbers keep a leading + if present."""
    trimmed = raw.strip()
    if not trimmed:
        return None
    if trimmed.startswith("+"):
        digits = "+" + "".join(char for char in trimmed[1:] if char.isdigit())
        return digits if len(digits) > 1 else None
    digits_only = "".join(char for char in trimmed if char.isdigit())
    if not digits_only:
        return None
    if len(digits_only) == 10 and digits_only.startswith("0"):
        local = digits_only[1:]
        return f"+260{local}"
    if len(digits_only) == 9 and digits_only[0] in {"7", "9"}:
        return f"+260{digits_only}"
    if digits_only.startswith("260"):
        return f"+{digits_only}"
    if len(digits_only) >= 10:
        return f"+{digits_only}"
    return None


def e164_sha256_hex(e164: str) -> str:
    return hashlib.sha256(e164.encode("utf-8")).hexdigest().lower()


def require_phone_pepper(settings: Settings | None = None) -> str:
    resolved = settings or get_settings()
    pepper = (getattr(resolved, "social_phone_pepper", None) or "").strip()
    if pepper:
        return pepper
    if resolved.env == "development":
        return "dev-social-phone-pepper"
    raise AppError(
        code="service_unavailable",
        message="Phone discovery is temporarily unavailable",
        http_status=503,
        details={"message_key": "social.errors.pepperMissing"},
    )


def client_hash_to_storage_hash(client_hash: str, *, settings: Settings | None = None) -> str:
    cleaned = client_hash.strip().lower()
    if not _HEX64.fullmatch(cleaned):
        msg = "invalid phone hash"
        raise AppError(
            code="validation_error",
            message=msg,
            http_status=422,
            details={"message_key": "social.errors.invalidPhoneHash"},
        )
    pepper = require_phone_pepper(settings)
    return hmac.new(
        pepper.encode("utf-8"),
        cleaned.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest().lower()


def zm_e164_from_profile_phone(phone: str | None) -> str | None:
    """Normalise a stored profile phone to E.164 for opt-in hashing."""
    if not phone:
        return None
    e164 = normalize_to_e164(phone)
    if e164 is None:
        return None
    bare = e164.removeprefix("+")
    if _ZM_MOBILE.fullmatch(bare):
        return e164
    return e164