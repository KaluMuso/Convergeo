"""Signed pickup QR tokens and hashed PIN helpers (stdlib HMAC/PBKDF2 only)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
from dataclasses import dataclass

_PIN_RE = re.compile(r"^\d{6}$")
_TOKEN_PARTS = 5


def resolve_signing_secret() -> str:
    secret = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not secret:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is required for pickup token signing")
    return secret


def generate_pin() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_pin(*, pin: str, order_id: str, secret: str | None = None) -> str:
    if not _PIN_RE.match(pin):
        raise ValueError("PIN must be exactly 6 digits")
    pepper = secret or resolve_signing_secret()
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        pin.encode("utf-8"),
        f"pickup-pin:{pepper}:{order_id}".encode(),
        120_000,
    )
    return digest.hex()


def verify_pin(*, pin: str, order_id: str, pin_hash: str, secret: str | None = None) -> bool:
    if not pin_hash:
        return False
    try:
        expected = hash_pin(pin=pin, order_id=order_id, secret=secret)
    except ValueError:
        return False
    return hmac.compare_digest(expected, pin_hash)


@dataclass(frozen=True, slots=True)
class PickupTokenPayload:
    order_id: str
    vendor_id: str
    nonce: str
    version: int


def sign_pickup_qr_token(
    *,
    order_id: str,
    vendor_id: str,
    nonce: str,
    version: int,
    secret: str | None = None,
) -> str:
    signing_key = (secret or resolve_signing_secret()).encode("utf-8")
    payload = f"{order_id}:{vendor_id}:{nonce}:{version}"
    signature = hmac.new(signing_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    raw = f"{payload}:{signature}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def parse_pickup_qr_token(token: str) -> PickupTokenPayload:
    padded = token + "=" * (-len(token) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Invalid pickup QR token encoding") from exc

    parts = decoded.split(":")
    if len(parts) != _TOKEN_PARTS:
        raise ValueError("Invalid pickup QR token structure")

    order_id, vendor_id, nonce, version_raw, signature = parts
    if not order_id or not vendor_id or not nonce:
        raise ValueError("Invalid pickup QR token payload")

    try:
        version = int(version_raw)
    except ValueError as exc:
        raise ValueError("Invalid pickup QR token version") from exc
    if version < 1:
        raise ValueError("Invalid pickup QR token version")

    signing_key = resolve_signing_secret().encode("utf-8")
    payload = f"{order_id}:{vendor_id}:{nonce}:{version}"
    expected = hmac.new(signing_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise ValueError("Invalid pickup QR token signature")

    return PickupTokenPayload(
        order_id=order_id,
        vendor_id=vendor_id,
        nonce=nonce,
        version=version,
    )
