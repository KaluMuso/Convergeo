"""Private scanner credential recovery for staging certification.

The real free-RSVP service generates a fresh ticket PIN and QR secret on every
issuance. Staging needs the holder-visible PIN only long enough to hand it to
the E2E runner through its private runtime file. This module therefore unwraps
the production-issued PIN and re-seals it after the ticket ID is normalised; it
never derives a stable credential from an environment secret.

Nothing here may be committed, logged, put in an artifact, or folded into
``fixture_version()``.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.tickets.qr import extract_pin_for_holder, seal_pin_storage


@dataclass(frozen=True, slots=True)
class TicketCredential:
    """Private runtime material for the canonical scanner ticket."""

    ticket_id: str
    pin: str
    pin_hash: str

    def __repr__(self) -> str:  # pragma: no cover - defensive
        # A stray repr() in a traceback must not print the PIN or its sealed form.
        return f"TicketCredential(ticket_id={self.ticket_id!r}, pin=<redacted>)"


def recover_service_issued_credential(
    *,
    issued_ticket_id: str,
    canonical_ticket_id: str,
    stored_pin_hash: str,
) -> TicketCredential:
    """Recover a real RSVP PIN and re-seal it for the canonical ticket ID.

    Production sealing binds the PIN to the ticket ID. The staging fixture
    preserves a canonical public ticket ID, so changing that ID requires
    re-sealing the already-issued random PIN. No new PIN is generated here.
    """
    pin = extract_pin_for_holder(stored_pin_hash, ticket_id=issued_ticket_id)
    if pin is None:
        raise RuntimeError("service-issued scanner PIN could not be recovered")
    return TicketCredential(
        ticket_id=canonical_ticket_id,
        pin=pin,
        pin_hash=seal_pin_storage(pin=pin, ticket_id=canonical_ticket_id),
    )


def primary_ticket_pin(credentials: tuple[TicketCredential, ...]) -> str:
    """Return the private PIN the scanner spec drives."""
    if not credentials:
        raise RuntimeError("no synthetic ticket credentials were issued")
    return credentials[0].pin


__all__ = [
    "TicketCredential",
    "primary_ticket_pin",
    "recover_service_issued_credential",
]
