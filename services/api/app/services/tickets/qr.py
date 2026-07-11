"""Rotating ticket QR window codes and PIN helpers (stdlib HMAC/PBKDF2 only)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import math
import os
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

_PIN_RE = re.compile(r"^\d{6}$")
_PIN_STORAGE_SEP = "$"
_SIG_TRUNCATE_LEN = 16
DEFAULT_HORIZON_WINDOWS = 12
MAX_HORIZON_WINDOWS = 60
WINDOW_SECONDS = 60


def resolve_signing_secret() -> str:
    secret = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not secret:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is required for ticket PIN sealing")
    return secret


def current_window(now: datetime | None = None) -> int:
    """Return the 60-second rotation window for *now* (UTC)."""
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=UTC)
    else:
        instant = instant.astimezone(UTC)
    return math.floor(instant.timestamp() / WINDOW_SECONDS)


def seconds_remaining_in_window(now: datetime | None = None) -> int:
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=UTC)
    else:
        instant = instant.astimezone(UTC)
    elapsed = int(instant.timestamp()) % WINDOW_SECONDS
    return WINDOW_SECONDS - elapsed


def window_code(ticket_secret: str, window: int) -> str:
    """Truncated HMAC-SHA256(secret, str(window)) — first 16 hex chars."""
    if not ticket_secret:
        raise ValueError("ticket_secret is required")
    digest = hmac.new(
        ticket_secret.encode("utf-8"),
        str(window).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest[:_SIG_TRUNCATE_LEN]


def build_qr_payload(*, ticket_id: str, window: int, ticket_secret: str) -> str:
    code = window_code(ticket_secret, window)
    return f"{ticket_id}:{window}:{code}"


@dataclass(frozen=True, slots=True)
class HorizonEntry:
    window: int
    code: str
    qr_payload: str


def issue_horizon(
    ticket_secret: str,
    *,
    ticket_id: str,
    from_window: int,
    n: int,
) -> list[HorizonEntry]:
    """Issue the next *n* window codes starting at *from_window* (inclusive)."""
    if n < 1:
        raise ValueError("horizon size must be at least 1")
    if n > MAX_HORIZON_WINDOWS:
        raise ValueError(f"horizon size cannot exceed {MAX_HORIZON_WINDOWS}")
    entries: list[HorizonEntry] = []
    for offset in range(n):
        window = from_window + offset
        code = window_code(ticket_secret, window)
        entries.append(
            HorizonEntry(
                window=window,
                code=code,
                qr_payload=build_qr_payload(
                    ticket_id=ticket_id,
                    window=window,
                    ticket_secret=ticket_secret,
                ),
            )
        )
    return entries


def generate_pin() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def generate_qr_secret() -> str:
    """Per-ticket rotating QR secret (64 hex chars)."""
    return secrets.token_hex(32)


def hash_pin(*, pin: str, ticket_id: str, secret: str | None = None) -> str:
    if not _PIN_RE.match(pin):
        raise ValueError("PIN must be exactly 6 digits")
    pepper = secret or resolve_signing_secret()
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        pin.encode("utf-8"),
        f"ticket-pin:{pepper}:{ticket_id}".encode(),
        120_000,
    )
    return digest.hex()


def _pin_wrap_key(ticket_id: str, secret: str) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        f"ticket-pin-wrap:{secret}:{ticket_id}".encode(),
        b"vergeo5-ticket-pin-wrap",
        120_000,
    )


def _wrap_pin_plaintext(*, pin: str, ticket_id: str, secret: str) -> str:
    key = _pin_wrap_key(ticket_id, secret)
    masked = bytes(byte ^ key[index % len(key)] for index, byte in enumerate(pin.encode("utf-8")))
    return base64.urlsafe_b64encode(masked).decode("ascii").rstrip("=")


def _unwrap_pin_plaintext(*, wrapped: str, ticket_id: str, secret: str) -> str | None:
    try:
        padded = wrapped + "=" * (-len(wrapped) % 4)
        masked = base64.urlsafe_b64decode(padded.encode("ascii"))
    except (ValueError, UnicodeDecodeError):
        return None
    key = _pin_wrap_key(ticket_id, secret)
    try:
        payload = bytes(byte ^ key[index % len(key)] for index, byte in enumerate(masked))
        pin = payload.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return pin if _PIN_RE.match(pin) else None


def seal_pin_storage(*, pin: str, ticket_id: str, secret: str | None = None) -> str:
    """Persist verify hash + holder-retrievable ciphertext in ``pin_hash`` (M10-P03 seam)."""
    pepper = secret or resolve_signing_secret()
    digest = hash_pin(pin=pin, ticket_id=ticket_id, secret=pepper)
    wrapped = _wrap_pin_plaintext(pin=pin, ticket_id=ticket_id, secret=pepper)
    return f"{digest}{_PIN_STORAGE_SEP}{wrapped}"


def _pin_verify_digest(stored: str) -> str:
    if _PIN_STORAGE_SEP in stored:
        return stored.split(_PIN_STORAGE_SEP, 1)[0]
    return stored


def extract_pin_for_holder(stored_pin_hash: str | None, *, ticket_id: str) -> str | None:
    if not stored_pin_hash or _PIN_STORAGE_SEP not in stored_pin_hash:
        return None
    wrapped = stored_pin_hash.split(_PIN_STORAGE_SEP, 1)[1]
    try:
        secret = resolve_signing_secret()
    except RuntimeError:
        return None
    return _unwrap_pin_plaintext(wrapped=wrapped, ticket_id=ticket_id, secret=secret)


def verify_pin(*, pin: str, ticket_id: str, pin_hash: str, secret: str | None = None) -> bool:
    if not pin_hash:
        return False
    try:
        expected = hash_pin(pin=pin, ticket_id=ticket_id, secret=secret)
    except ValueError:
        return False
    return hmac.compare_digest(expected, _pin_verify_digest(pin_hash))


def horizon_entry_to_dict(entry: HorizonEntry) -> dict[str, Any]:
    return {
        "window": entry.window,
        "code": entry.code,
        "qr_payload": entry.qr_payload,
    }
