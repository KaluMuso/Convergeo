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

from typing import Any

PHONE_PROVIDER = "phone"


class AuthPersonaError(RuntimeError):
    """Raised when a canonical Auth persona cannot be established.

    Callers must treat this as fatal to the seed step — never continue
    (E2E must not run against a partially-created persona).
    """


def _has_phone_identity(user: Any) -> bool:
    identities = getattr(user, "identities", None) or ()
    return any(getattr(identity, "provider", None) == PHONE_PROVIDER for identity in identities)


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
    user with a confirmed phone identity, through the Auth Admin API only.

    For each persona (deterministic, hardcoded UUID from PERSONAS — never a
    dynamically discovered id, so this can only ever touch these exact known
    synthetic users, never an unrelated or real one):

      - missing entirely            -> create_user()
      - exists, has a phone identity -> no-op (repair confirmation if somehow
                                         unconfirmed)
      - exists, zero identities      -> the legacy raw-SQL state this
                                         replaces: delete_user() then
                                         create_user(), since only create_user
                                         actually populates auth.identities

    Returns {persona.key: outcome} for the caller to log/verify. Raises
    AuthPersonaError (fail closed) on the first Admin API error — never
    partially applies the batch.
    """
    outcomes: dict[str, str] = {}
    for persona in personas:
        existing = _fetch_existing(client, persona.user_id)

        if existing is not None and _has_phone_identity(existing):
            if getattr(existing, "phone_confirmed_at", None) is None:
                _repair_phone_confirmation(client, persona)
                outcomes[persona.key] = "repaired-confirmation"
            else:
                outcomes[persona.key] = "already-ok"
            continue

        if existing is not None:
            _delete(client, persona)
            _create(client, persona)
            outcomes[persona.key] = "recreated-legacy-row"
            continue

        _create(client, persona)
        outcomes[persona.key] = "created"

    return outcomes


def verify_auth_personas(client: Any, *, personas: tuple[Any, ...]) -> None:
    """Post-condition check: every persona must be a real Auth-managed user
    with `phone_confirmed_at` set AND a `provider='phone'` identity owned by
    that exact user id. Raises AuthPersonaError (fail closed) otherwise — the
    caller must not let E2E proceed against a fixture that fails this.
    """
    for persona in personas:
        user = _fetch_existing(client, persona.user_id)
        if user is None:
            raise AuthPersonaError(
                f"canonical persona {persona.key} ({persona.user_id}) does not exist "
                "after seeding"
            )
        if getattr(user, "phone_confirmed_at", None) is None:
            raise AuthPersonaError(
                f"canonical persona {persona.key} ({persona.user_id}) has no "
                "phone_confirmed_at after seeding"
            )
        identities = getattr(user, "identities", None) or ()
        owned_phone_identity = any(
            getattr(identity, "provider", None) == PHONE_PROVIDER
            and getattr(identity, "user_id", None) == persona.user_id
            for identity in identities
        )
        if not owned_phone_identity:
            raise AuthPersonaError(
                f"canonical persona {persona.key} ({persona.user_id}) has no "
                "provider='phone' identity owned by that user id after seeding"
            )


__all__ = ["AuthPersonaError", "ensure_auth_personas", "verify_auth_personas"]
