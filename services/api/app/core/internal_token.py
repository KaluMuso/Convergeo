"""Fail-closed resolution for X-Internal-Token secrets.

Development may fall back to well-known ``dev-internal-*`` defaults. Staging and
production must set a non-empty env var that is NOT the known default — otherwise
money-moving and operational cron endpoints refuse to authorize (503).
"""

from __future__ import annotations

import os

# Settings Literal is development|staging|production; also treat "prod" as strict.
_STRICT_ENVS = frozenset({"production", "staging", "prod"})


class InternalTokenMisconfigured(RuntimeError):
    """Raised when a strict ENV lacks a safe internal-token secret."""


def resolve_internal_token(
    env_var: str,
    *,
    dev_default: str,
    env: str | None = None,
) -> str:
    """Return the expected internal token for ``env_var``.

    - ``ENV`` in {production, staging, prod}: require a non-empty value that is
      not equal to ``dev_default``. Raises ``InternalTokenMisconfigured`` otherwise.
    - development / test / unset (defaults to development): allow ``dev_default``
      when the env var is missing or blank.
    """
    if env is not None:
        resolved_env = env.strip().lower()
    else:
        resolved_env = os.environ.get("ENV", "development").strip().lower()
    if not resolved_env:
        resolved_env = "development"

    raw = os.environ.get(env_var)
    value = raw.strip() if raw is not None else ""

    if resolved_env in _STRICT_ENVS:
        if not value:
            raise InternalTokenMisconfigured(
                f"{env_var} must be set to a non-default secret when ENV={resolved_env}"
            )
        if value == dev_default:
            raise InternalTokenMisconfigured(
                f"{env_var} must not use the well-known development default when ENV={resolved_env}"
            )
        return value

    return value if value else dev_default
