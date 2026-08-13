"""Private-event credentials and short-lived signed access proofs.

Credentials live in the service-only ``event_access_credentials`` table. A
browser first exchanges a code for a signed proof, then sends that proof in a
header/body to detail, calendar and purchase endpoints. Plaintext codes never
appear in URLs, logs, or ticket checkout records.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

_SALT_BYTES = 16
_PBKDF2_ITERATIONS = 210_000
_PROOF_TTL_SECONDS = 15 * 60


def hash_access_code(code: str) -> str:
    """Return a slow, versioned digest for a non-empty organiser code."""
    normalized = code.strip()
    if not normalized:
        msg = "access code must not be empty"
        raise ValueError(msg)
    salt = secrets.token_hex(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        normalized.encode("utf-8"),
        salt.encode("ascii"),
        _PBKDF2_ITERATIONS,
    ).hex()
    return f"v2${salt}${digest}"


def verify_access_code(code: str | None, stored: str | None) -> bool:
    """Constant-time verify a current or pre-completion credential digest."""
    if not code or not stored:
        return False
    parts = stored.split("$")
    normalized = code.strip()
    if not normalized:
        return False
    if len(parts) == 3 and parts[0] == "v2":
        _, salt, digest = parts
        if not salt or not digest:
            return False
        expected = hashlib.pbkdf2_hmac(
            "sha256",
            normalized.encode("utf-8"),
            salt.encode("ascii"),
            _PBKDF2_ITERATIONS,
        ).hex()
        return hmac.compare_digest(expected, digest)

    # Compatibility for existing private events. A successful unlock should be
    # followed by an organiser rotation, which writes the v2 digest above.
    if len(parts) == 2:
        salt, digest = parts
        expected = hashlib.sha256(f"{salt}{normalized}".encode()).hexdigest()
        return hmac.compare_digest(expected, digest)
    return False


@dataclass(frozen=True, slots=True)
class EventAccessProof:
    event_id: str
    credential_version: int
    expires_at: datetime
    subject_id: str | None


def _proof_secret(secret: str | None = None) -> bytes:
    value = (secret or os.environ.get("EVENT_ACCESS_SIGNING_SECRET") or os.environ.get(
        "SUPABASE_SERVICE_ROLE_KEY", ""
    )).strip()
    if not value:
        raise RuntimeError("EVENT_ACCESS_SIGNING_SECRET is required for private-event access")
    return value.encode("utf-8")


def _b64_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode((value + "=" * (-len(value) % 4)).encode("ascii"))


def issue_event_access_proof(
    *,
    event_id: str,
    credential_version: int,
    subject_id: str | None = None,
    now: datetime | None = None,
    ttl_seconds: int = _PROOF_TTL_SECONDS,
    secret: str | None = None,
) -> str:
    """Mint a short-lived, event- and credential-version-bound proof."""
    if credential_version < 1 or ttl_seconds <= 0:
        raise ValueError("credential_version and ttl_seconds must be positive")
    issued_at = now or datetime.now(UTC)
    if issued_at.tzinfo is None:
        issued_at = issued_at.replace(tzinfo=UTC)
    payload = {
        "e": event_id,
        "exp": int((issued_at + timedelta(seconds=ttl_seconds)).timestamp()),
        "s": subject_id,
        "v": credential_version,
    }
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded = _b64_encode(payload_json)
    signature = hmac.new(
        _proof_secret(secret), encoded.encode("ascii"), hashlib.sha256
    ).hexdigest()
    return f"{encoded}.{signature}"


def verify_event_access_proof(
    proof: str | None,
    *,
    event_id: str,
    credential_version: int,
    subject_id: str | None = None,
    now: datetime | None = None,
    secret: str | None = None,
) -> EventAccessProof | None:
    """Validate a proof without leaking which part of validation failed."""
    if not proof or "." not in proof or credential_version < 1:
        return None
    encoded, signature = proof.rsplit(".", 1)
    expected = hmac.new(_proof_secret(secret), encoded.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return None
    try:
        payload = json.loads(_b64_decode(encoded).decode("utf-8"))
        expires_at = datetime.fromtimestamp(int(payload["exp"]), tz=UTC)
        proof_subject = payload.get("s")
        if proof_subject is not None and not isinstance(proof_subject, str):
            return None
        if (
            payload.get("e") != event_id
            or int(payload.get("v")) != credential_version
            or proof_subject != subject_id
            or expires_at.timestamp() < (now or datetime.now(UTC)).timestamp()
        ):
            return None
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return EventAccessProof(
        event_id=event_id,
        credential_version=credential_version,
        expires_at=expires_at,
        subject_id=proof_subject,
    )
