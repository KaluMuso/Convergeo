"""Run-scoped scanner credentials for the synthetic staging event fixture.

The event, its instance, ticket types and ticket IDs are canonical, deterministic
fixture identity (`synthetic_contract.EVENTS`). The credentials that let the
organiser scanner accept that ticket are NOT: they are minted fresh on every seed
with `secrets`, sealed through the same `seal_pin_storage()` path the application
itself uses, and handed to the test runner privately for that run only.

Why not a committed constant:
  - the rotating QR window code changes every 60 seconds, so no stored value can
    stay valid (see `services/tickets/qr.py::current_window`);
  - the PIN fallback — which the scanner spec actually drives — is stable per
    ticket, so a committed value would be a real, long-lived credential in source
    control for anyone who can reach staging.

Nothing here may be committed, logged, put in an artifact, or folded into
`fixture_version()`.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.tickets.qr import generate_pin, generate_qr_secret, seal_pin_storage
from app.staging.synthetic_contract import EVENTS


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


def mint_ticket_credentials() -> tuple[TicketCredential, ...]:
    """Mint and seal run-scoped credentials for every seeded ticket.

    Fails closed: `seal_pin_storage()` resolves the wrap key from
    SUPABASE_SERVICE_ROLE_KEY and raises when it is absent, so a seed run without
    the staging service-role key cannot silently produce tickets the scanner will
    never accept.
    """
    credentials: list[TicketCredential] = []
    for event in EVENTS:
        for ticket in event.tickets:
            pin = generate_pin()
            credentials.append(
                TicketCredential(
                    ticket_id=ticket.ticket_id,
                    pin=pin,
                    pin_hash=seal_pin_storage(pin=pin, ticket_id=ticket.ticket_id),
                    qr_secret=generate_qr_secret(),
                )
            )
    return tuple(credentials)


def primary_ticket_pin(credentials: tuple[TicketCredential, ...]) -> str:
    """The PIN the scanner spec drives (the first issued ticket)."""
    if not credentials:
        raise RuntimeError("no synthetic ticket credentials were minted")
    return credentials[0].pin


__all__ = ["TicketCredential", "mint_ticket_credentials", "primary_ticket_pin"]
