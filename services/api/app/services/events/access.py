"""Access-code hashing for private events (Wave A / M10-P10, decision D29).

A ``private`` event (``events.visibility='private'``) is reachable only with a
matching access code. We store a salted SHA-256 hash — never the plaintext —
in ``events.access_code_hash`` and verify with a constant-time compare. This
gates *viewing* a private listing, not money, so a salted hash (not a slow KDF)
is proportionate. A private event whose ``access_code_hash`` is NULL is
unreachable publicly (nothing verifies), which is the safe default.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

_SALT_BYTES = 8


def hash_access_code(code: str) -> str:
    """Return ``"<salt>$<sha256(salt+code)>"`` for storage. Raises on empty code."""
    normalized = code.strip()
    if not normalized:
        msg = "access code must not be empty"
        raise ValueError(msg)
    salt = secrets.token_hex(_SALT_BYTES)
    digest = hashlib.sha256(f"{salt}{normalized}".encode()).hexdigest()
    return f"{salt}${digest}"


def verify_access_code(code: str | None, stored: str | None) -> bool:
    """Constant-time check of a candidate code against a stored salted hash.

    Returns False for any missing/malformed input (incl. a NULL stored hash),
    so a private event with no code set is never accessible.
    """
    if not code or not stored or "$" not in stored:
        return False
    salt, _, digest = stored.partition("$")
    if not salt or not digest:
        return False
    expected = hashlib.sha256(f"{salt}{code.strip()}".encode()).hexdigest()
    return hmac.compare_digest(expected, digest)
