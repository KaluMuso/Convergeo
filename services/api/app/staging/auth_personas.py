"""Supported Supabase Auth Admin API persona creation for staging fixtures.

Replaces the previous raw `INSERT INTO auth.users` seed path. Live staging
inspection (post-#688) found the canonical Customer and Vendor personas both
had `auth.identities` count = 0 despite `auth.users` rows existing with
`phone_confirmed_at` set — because a hand-authored `auth.users` row was never
a real Auth-managed user: GoTrue's phone-login `signInWithOtp
(shouldCreateUser: false)` requires an actual phone IDENTITY, not merely a
confirmed `phone_confirmed_at` column, and rejects the identity-less row with
`422 otp_disabled` regardless of that column's value.

The Auth Admin API (`POST /auth/v1/admin/users` — `client.auth.admin.
create_user`) is GoTrue's own supported path for provisioning a user: it
creates the `auth.identities` row itself, atomically, as part of accepting
the request — something a caller cannot correctly reproduce by hand (see
D35's ban on writing directly into GoTrue-owned tables, and 0002_identity_
vendors.sql's comment that `auth.users`/`auth.identities` are the platform's,
not this repo's, to write into).

Fails closed by design: any Admin API error propagates as AuthPersonaError,
never silently continues past a partially-created persona.
"""

from __future__ import annotations

import re
from typing import Any

PHONE_PROVIDER = "phone"

_PHONE_DIGITS_RE = re.compile(r"^[0-9]+$")


def canonical_auth_phone(value: str) -> str:
    """Canonicalizes a phone number for cross-source comparison against
    Supabase Auth's stored form.

    Live evidence (staging Deploy run #55): hosted Supabase Auth normalizes
    a `create_user()` call's E.164 input `+260970000001` to a stored
    `auth.users.phone` of `260970000001` — an optional single leading '+'
    is the only transformation the platform is known to apply. This
    function accepts exactly that and nothing more: no stripping of
    spaces, hyphens, parentheses, other punctuation, or leading zeroes,
    since no repository/Supabase evidence establishes those as part of the
    supported contract. Anything else is malformed and must fail closed
    rather than being silently treated as equivalent.

    Raises ValueError on any value that is not `[+]?[0-9]+`.
    """
    digits = value[1:] if value.startswith("+") else value
    if not digits or not _PHONE_DIGITS_RE.match(digits):
        raise ValueError(f"not a canonical-comparable phone number: {value!r}")
    return digits


def _phones_equivalent(actual: str | None, expected: str) -> bool:
    """True only when both canonicalize to the same digit string.

    Fails closed: a missing or malformed `actual` value returns False
    (never raises, never treated as a match) — the caller's own
    mismatch-handling path takes it from there.
    """
    if actual is None:
        return False
    try:
        return canonical_auth_phone(actual) == canonical_auth_phone(expected)
    except ValueError:
        return False


class AuthPersonaError(RuntimeError):
    """Raised when a canonical Auth persona cannot be established.

    Callers must treat this as fatal to the seed step — never continue
    (E2E must not run against a partially-created persona).
    """


def _identity_phone_matches(identity: Any, persona: Any) -> bool:
    """Best-effort extra check: when the identity's own identity_data
    exposes a 'phone' key (GoTrue's typical phone-provider payload), it
    must also match persona.phone — but the key's absence is not itself a
    failure, since the top-level user.phone check in
    _matches_phone_contract is already authoritative on its own."""
    data = getattr(identity, "identity_data", None) or {}
    if not isinstance(data, dict) or "phone" not in data:
        return True
    return _phones_equivalent(data.get("phone"), persona.phone)


def _has_owned_phone_identity(user: Any, persona: Any) -> bool:
    identities = getattr(user, "identities", None) or ()
    return any(
        getattr(identity, "provider", None) == PHONE_PROVIDER
        and getattr(identity, "user_id", None) == persona.user_id
        and _identity_phone_matches(identity, persona)
        for identity in identities
    )


def _matches_phone_contract(user: Any, persona: Any) -> bool:
    """The full deterministic-fixture contract: same user id (defensive —
    always true by construction, since callers look up by persona.user_id,
    but a mismatch here would mean the caller/mock is broken), same E.164
    phone, and a phone identity owned by that exact user id. A wrong phone
    (a canonical UUID reused with a different number, e.g. after a fixture
    edit) must NEVER be treated as already correct — that is exactly what
    would leave a deterministic OTP fixture silently signing in with the
    wrong number."""
    if getattr(user, "id", None) != persona.user_id:
        return False
    if not _phones_equivalent(getattr(user, "phone", None), persona.phone):
        return False
    return _has_owned_phone_identity(user, persona)


def _fetch_existing(client: Any, user_id: str) -> Any | None:
    try:
        response = client.auth.admin.get_user_by_id(user_id)
    except Exception as exc:  # noqa: BLE001 — reclassified below
        status = getattr(exc, "status", None)
        if status == 404:
            return None
        raise AuthPersonaError(f"cannot look up Auth persona {user_id}: {exc}") from exc
    return getattr(response, "user", None)


def _create(client: Any, persona: Any) -> None:
    try:
        client.auth.admin.create_user(
            {
                "id": persona.user_id,
                "phone": persona.phone,
                "phone_confirm": True,
                "email": persona.email,
                "email_confirm": True,
                "user_metadata": {"handle": persona.handle},
                "role": "authenticated",
            }
        )
    except Exception as exc:  # noqa: BLE001 — reclassified as AuthPersonaError
        raise AuthPersonaError(
            f"cannot create Auth persona {persona.key} ({persona.user_id}): {exc}"
        ) from exc


def _delete(client: Any, persona: Any) -> None:
    try:
        client.auth.admin.delete_user(persona.user_id)
    except Exception as exc:  # noqa: BLE001 — reclassified as AuthPersonaError
        raise AuthPersonaError(
            f"cannot remove legacy synthetic persona {persona.key} "
            f"({persona.user_id}) before recreation: {exc}"
        ) from exc


def _repair_phone_confirmation(client: Any, persona: Any) -> None:
    try:
        client.auth.admin.update_user_by_id(persona.user_id, {"phone_confirm": True})
    except Exception as exc:  # noqa: BLE001 — reclassified as AuthPersonaError
        raise AuthPersonaError(
            f"cannot repair phone confirmation for {persona.key} "
            f"({persona.user_id}): {exc}"
        ) from exc


def ensure_auth_personas(client: Any, *, personas: tuple[Any, ...]) -> dict[str, str]:
    """Idempotently ensures every entry in `personas` is a real Auth-managed
    user matching the full deterministic contract, through the Auth Admin
    API only: same user id, same E.164 phone number (an optional leading
    '+' difference is treated as equivalent — hosted Supabase Auth
    normalizes it away on storage, see canonical_auth_phone()), phone
    confirmed, and a provider='phone' identity owned by that exact user id.

    For each persona (deterministic, hardcoded UUID from PERSONAS — never a
    dynamically discovered id, so this can only ever touch these exact known
    synthetic users, never an unrelated or real one):

      - missing entirely                 -> create_user()
      - exists, full contract matches    -> no-op (repair confirmation only
                                             if somehow unconfirmed — a pure
                                             attribute flip, never touches
                                             phone/identity)
      - exists, contract does NOT match  -> delete_user() then create_user().
        (zero/mismatched identity, or a   Covers both the legacy raw-SQL
         wrong phone on this UUID)        state (zero identities) and a
                                           wrong-phone UUID reuse — only
                                           create_user() is proven to
                                           correctly (re)populate
                                           auth.identities for the canonical
                                           phone, so this is the one
                                           deterministic repair used for any
                                           contract mismatch.

    Returns {persona.key: outcome} for the caller to log/verify. Raises
    AuthPersonaError (fail closed) on the first Admin API error — never
    partially applies the batch.
    """
    outcomes: dict[str, str] = {}
    for persona in personas:
        existing = _fetch_existing(client, persona.user_id)

        if existing is not None and _matches_phone_contract(existing, persona):
            if getattr(existing, "phone_confirmed_at", None) is None:
                _repair_phone_confirmation(client, persona)
                outcomes[persona.key] = "repaired-confirmation"
            else:
                outcomes[persona.key] = "already-ok"
            continue

        if existing is not None:
            _delete(client, persona)
            _create(client, persona)
            outcomes[persona.key] = "recreated-mismatched-row"
            continue

        _create(client, persona)
        outcomes[persona.key] = "created"

    return outcomes


def verify_auth_personas(client: Any, *, personas: tuple[Any, ...]) -> None:
    """Post-condition check: every persona must be a real Auth-managed user
    matching the full deterministic contract — same user id, same E.164
    phone number (an optional leading '+' difference is treated as
    equivalent, see canonical_auth_phone() — but a wrong phone must never
    verify as correct, since that is exactly what would leave a
    deterministic OTP fixture silently signing in with the wrong number),
    `phone_confirmed_at` set, AND a `provider='phone'` identity owned by
    that exact user id. Raises AuthPersonaError (fail closed) otherwise —
    the caller must not let E2E proceed against a fixture that fails this.
    """
    for persona in personas:
        user = _fetch_existing(client, persona.user_id)
        if user is None:
            raise AuthPersonaError(
                f"canonical persona {persona.key} ({persona.user_id}) does not exist "
                "after seeding"
            )
        if getattr(user, "id", None) != persona.user_id:
            raise AuthPersonaError(
                f"canonical persona {persona.key}: Admin API returned a user id "
                f"mismatch ({getattr(user, 'id', None)!r} != {persona.user_id!r})"
            )
        if not _phones_equivalent(getattr(user, "phone", None), persona.phone):
            raise AuthPersonaError(
                f"canonical persona {persona.key} ({persona.user_id}) has phone "
                f"{getattr(user, 'phone', None)!r}, expected {persona.phone!r}"
            )
        if getattr(user, "phone_confirmed_at", None) is None:
            raise AuthPersonaError(
                f"canonical persona {persona.key} ({persona.user_id}) has no "
                "phone_confirmed_at after seeding"
            )
        if not _has_owned_phone_identity(user, persona):
            raise AuthPersonaError(
                f"canonical persona {persona.key} ({persona.user_id}) has no "
                "provider='phone' identity owned by that user id and matching "
                "persona.phone after seeding"
            )


__all__ = [
    "AuthPersonaError",
    "canonical_auth_phone",
    "ensure_auth_personas",
    "verify_auth_personas",
]
