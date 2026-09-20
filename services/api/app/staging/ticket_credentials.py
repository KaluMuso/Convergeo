"""Deterministic, environment-bound scanner credentials for staging certification.

The event, instance, free-RSVP type and ticket ID are canonical fixture identity.
The six-digit PIN and QR secret are derived with HMAC from the staging
service-role key and that ticket identity, then the PIN is sealed through the same
`seal_pin_storage()` path used by production issuance.  This makes cleanup/reseed
reproducible without committing a usable credential.

Why not a committed PIN:
  - the rotating QR window code changes every 60 seconds, so no stored value can
    stay valid (see `services/tickets/qr.py::current_window`);
  - a committed PIN would be a long-lived credential for anyone who can reach
    staging; deriving it from the environment secret keeps it out of source.

Nothing here may be committed, logged, put in an artifact, or folded into
`fixture_version()`.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from app.services.tickets.qr import resolve_signing_secret, seal_pin_storage
from app.staging.synthetic_contract import EVENTS

_PIN_CONTEXT = b"convergeo:staging:scanner-certification:pin:v1"
_QR_CONTEXT = b"convergeo:staging:scanner-certification:qr:v1"


@dataclass(frozen=True, slots=True)
class TicketCredential:
    """One run's scanner credentials for one seeded ticket."""

    ticket_id: str
    pin: str
    pin_hash: str
    qr_secret: str

    def __repr__(self) -> str:  # pragma: no cover - defensive
        # A stray repr() in a traceback must not print the PIN.
        return f"TicketCredential(ticket_id={self.ticket_id!r}, pin=<redacted>)"


def certification_ticket_credentials() -> tuple[TicketCredential, ...]:
    """Derive and seal deterministic credentials for every scanner fixture.

    Fails closed when the service-role key is absent.  The secret is never stored
    in the fixture document or returned by this module.
    """
    secret = resolve_signing_secret()
    credentials: list[TicketCredential] = []
    for event in EVENTS:
        for ticket in event.tickets:
            identity = ticket.ticket_id.encode("ascii")
            pin_digest = hmac.new(secret.encode(), _PIN_CONTEXT + identity, hashlib.sha256).digest()
            pin = f"{int.from_bytes(pin_digest[:8], 'big') % 1_000_000:06d}"
            qr_secret = hmac.new(
                secret.encode(), _QR_CONTEXT + identity, hashlib.sha256
            ).hexdigest()
            credentials.append(
                TicketCredential(
                    ticket_id=ticket.ticket_id,
                    pin=pin,
                    pin_hash=seal_pin_storage(
                        pin=pin, ticket_id=ticket.ticket_id, secret=secret
                    ),
                    qr_secret=qr_secret,
                )
            )
    return tuple(credentials)


# Compatibility alias for callers/tests on the S3 contract.  The semantics are
# now deterministic rather than random; keeping the name avoids a wide, unrelated
# call-site churn.
def mint_ticket_credentials() -> tuple[TicketCredential, ...]:
    return certification_ticket_credentials()


def primary_ticket_pin(credentials: tuple[TicketCredential, ...]) -> str:
    """The PIN the scanner spec drives (the first issued ticket)."""
    if not credentials:
        raise RuntimeError("no synthetic ticket credentials were minted")
    return credentials[0].pin


__all__ = [
    "TicketCredential",
    "certification_ticket_credentials",
    "mint_ticket_credentials",
    "primary_ticket_pin",
]
