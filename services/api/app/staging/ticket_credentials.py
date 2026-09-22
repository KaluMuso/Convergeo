"""Run-scoped credentials for the STATICALLY seeded synthetic tickets.

The event, its instance, ticket types and the static ticket IDs are canonical,
deterministic fixture identity (`synthetic_contract.EVENTS`). The credentials
that unlock those tickets are NOT: they are minted fresh on every seed with
`secrets` and sealed through the same `seal_pin_storage()` path the application
itself uses.

Scope note: the tickets covered here are the static UNPAID HOLDS — the paid-lane
rows the seed SQL writes directly, which `/tickets/verify` rejects with
`ticket_unpaid_hold`. Sealing a real PIN into them is what makes that rejection
provable on live staging (correct PIN, correct organiser, still refused) rather
than indistinguishable from a bad credential. The ticket the organiser scanner
actually checks in is a different row entirely: `app.staging.event_scanner`
drives the real `rsvp()` service path, and that path seals its own PIN, which is
read back through the holder-retrieval path rather than minted here.

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
    """Mint and seal run-scoped credentials for every statically seeded ticket.

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
    """The PIN of the first static hold — the `ticket_unpaid_hold` control.

    Deliberately NOT the PIN the E2E scanner leg drives. That one belongs to the
    rsvp()-issued ticket and is read back from the row the service sealed
    (`app.staging.event_scanner`), because only that ticket has an
    `order_item_id` and can therefore be checked in at all.
    """
    if not credentials:
        raise RuntimeError("no synthetic ticket credentials were minted")
    return credentials[0].pin


__all__ = ["TicketCredential", "mint_ticket_credentials", "primary_ticket_pin"]
