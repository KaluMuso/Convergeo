"""Look up auth.users identity fields via the service-role admin API.

``profiles`` carries ``phone`` and ``display_name`` but deliberately NOT
``email`` — the customer email lives only in ``auth.users``, which PostgREST
does not expose. The service-role client's gotrue admin API is the supported
server-side read path (already used for account deletion in the privacy flow).

Reused by any surface that needs the email we never copied into ``profiles``:
the Lenco card widget (which requires a customer email) and the email tertiary
notification channel.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


def lookup_user_email(service_client: ServiceRoleClient, *, user_id: str) -> str | None:
    """Return the user's ``auth.users`` email, or ``None`` if absent/unavailable.

    Never raises: a gotrue error (network, missing user) is logged and returns
    ``None`` so callers apply their own "email required" handling rather than
    surfacing a 500. The value is stripped; empty/whitespace becomes ``None``.
    """
    if not user_id:
        return None
    try:
        response = service_client.client.auth.admin.get_user_by_id(user_id)
    except Exception:
        logger.exception("auth.users email lookup failed for user %s", user_id)
        return None
    user = getattr(response, "user", None)
    email = getattr(user, "email", None)
    if isinstance(email, str) and email.strip():
        return email.strip()
    return None
