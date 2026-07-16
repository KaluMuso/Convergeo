"""Per-`event_type` behavior policy map (D29 / Events Wave A · M10-P10).

D29 makes `events.event_type` a **behavioral driver**, not a display label, and
requires that behavior to live in **one guarded source of truth** — never scattered
`if event_type == …` branches across discovery, escrow, and UX code.

This module is that source of truth. Every consumer (discovery filtering now;
`event_release.py` escrow timing in P14; organiser/attendee UX flags) reads the policy
here instead of hard-coding a type. A coverage test asserts every enum value has an
entry, so a new `event_type` cannot be added without giving it a policy.

**Money note:** P10 is money-free. The `escrow_schedule` field is *declared* here as the
single source of truth but is **not yet consumed** by the escrow engine — P14 wires
`event_release.py` to read it. Adding a value here changes no money behavior on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

EventType = Literal["single", "multi_day", "experience", "free"]

#: Canonical enum order — mirrors the DB CHECK on `events.event_type` (migration 0041).
EVENT_TYPES: tuple[EventType, ...] = ("single", "multi_day", "experience", "free")

#: Default applied to pre-Wave-A events and any create that omits the field. 'single'
#: preserves the current date-anchored escrow + standard-browse behavior.
DEFAULT_EVENT_TYPE: EventType = "single"

#: Escrow release schedule selector (consumed by event_release.py in P14, not P10).
EscrowSchedule = Literal["date_anchored", "phased", "post_completion", "none"]


@dataclass(frozen=True, slots=True)
class EventTypePolicy:
    """Immutable per-type behavior. Grouped by the three D29 buckets."""

    event_type: EventType
    # discovery
    browsable: bool
    # ux
    paid: bool
    named_tickets_default: bool
    multi_instance: bool
    # escrow (declared now; wired by P14)
    escrow_schedule: EscrowSchedule


EVENT_TYPE_POLICY: dict[EventType, EventTypePolicy] = {
    "single": EventTypePolicy(
        event_type="single",
        browsable=True,
        paid=True,
        named_tickets_default=False,
        multi_instance=False,
        escrow_schedule="date_anchored",
    ),
    "multi_day": EventTypePolicy(
        event_type="multi_day",
        browsable=True,
        paid=True,
        named_tickets_default=False,
        multi_instance=True,
        escrow_schedule="phased",
    ),
    "experience": EventTypePolicy(
        event_type="experience",
        browsable=True,
        paid=True,
        named_tickets_default=True,
        multi_instance=False,
        escrow_schedule="post_completion",
    ),
    "free": EventTypePolicy(
        event_type="free",
        browsable=True,
        paid=False,
        named_tickets_default=False,
        multi_instance=False,
        escrow_schedule="none",
    ),
}


def policy_for(event_type: str | None) -> EventTypePolicy:
    """Resolve the policy for a stored `event_type`, defaulting for unknown/None.

    The DB CHECK + the organiser API's ``Literal`` guarantee only valid values persist,
    so the default branch is defensive (a pre-Wave-A row read as its column default, or
    an unexpected value) and never a money decision in P10.
    """
    if event_type in EVENT_TYPE_POLICY:
        return EVENT_TYPE_POLICY[event_type]
    return EVENT_TYPE_POLICY[DEFAULT_EVENT_TYPE]
