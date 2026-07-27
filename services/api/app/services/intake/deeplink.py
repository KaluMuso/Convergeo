"""M18-P05 — single-use, short-TTL review links for intake sessions (D35).

The security claim this module makes is narrow and worth stating precisely:

    **The token is not the authorisation.**

Redeeming a link tells the API *which* intake session the vendor is opening and
proves the link was minted by us and has not been used or expired. It does not,
on its own, grant access to anything: the redeeming request must still carry an
authenticated vendor session that owns the session (enforced by the router).
A leaked or forwarded link is therefore useless to anyone but its owner.

Only ``sha256(token)`` is stored. The plaintext exists exactly once, in the mint
response, and is never written to the database or to a log line.

Delivery is **Lane 1 only** (official Cloud API / outbox) or in-app. The WAHA
lane is strictly inbound-only and may never carry this link.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Final, Protocol

from app.errors import AppError

LINKS_TABLE: Final = "intake_deep_links"

# Short enough that a forwarded link goes stale quickly, long enough that a
# vendor on a slow connection can still act on it.
DEFAULT_TTL_SECONDS: Final = 30 * 60
TOKEN_BYTES: Final = 32


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def mint(
    service_client: ServiceRoleClient,
    *,
    session_id: str,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    now: datetime | None = None,
) -> tuple[str, datetime]:
    """Create one link. Returns ``(plaintext_token, expires_at)``.

    The plaintext is returned to the caller and forgotten here.
    """
    reference = now or datetime.now(UTC)
    expires_at = reference + timedelta(seconds=ttl_seconds)
    token = secrets.token_urlsafe(TOKEN_BYTES)
    service_client.client.table(LINKS_TABLE).insert(
        {
            "session_id": session_id,
            "token_hash": hash_token(token),
            "expires_at": expires_at.isoformat(),
        }
    ).execute()
    return token, expires_at


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _invalid() -> AppError:
    # One indistinguishable error for unknown / expired / already-redeemed. A
    # caller must not be able to probe which tokens ever existed.
    return AppError(
        code="intake_link_invalid",
        message="Intake review link is not usable",
        http_status=404,
        details={"message_key": "vendor.intake.errors.linkInvalid"},
    )


def redeem(
    service_client: ServiceRoleClient,
    *,
    token: str,
    now: datetime | None = None,
) -> str:
    """Consume one link and return its ``session_id``.

    Raises ``intake_link_invalid`` (404) for unknown, expired, or already-used
    tokens — the same error in every case, so the endpoint is not an oracle.

    Single use is enforced by the ``redeemed_at is null`` predicate *in the
    UPDATE*, so two concurrent redemptions cannot both succeed.
    """
    reference = now or datetime.now(UTC)
    found = _rows(
        service_client.client.table(LINKS_TABLE)
        .select("id, session_id, expires_at, redeemed_at")
        .eq("token_hash", hash_token(token))
        .maybe_single()
        .execute()
    )
    if not found:
        raise _invalid()

    row = found[0]
    if row.get("redeemed_at") is not None:
        raise _invalid()

    expires_at = _parse_timestamp(row.get("expires_at"))
    if expires_at is None or expires_at <= reference:
        raise _invalid()

    claimed = _rows(
        service_client.client.table(LINKS_TABLE)
        .update({"redeemed_at": reference.isoformat()})
        .eq("id", row["id"])
        .is_("redeemed_at", "null")
        .execute()
    )
    if not claimed:
        # Lost the race to a concurrent redemption.
        raise _invalid()

    return str(row["session_id"])
