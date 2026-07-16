"""Single source of truth for ``event_type``-driven behaviour (D29 / Wave A).

``event_type`` is a *full behavioural driver*: it governs discovery visibility
defaults, escrow settlement timing, and UX flags. To keep that behaviour
auditable and the money path guarded, every per-type rule lives here — no
consumer branches on ``event_type`` inline. Consumers:

* organiser writes (``organiser_events.py``) read :attr:`default_visibility`
  when the organiser doesn't set visibility explicitly;
* discovery (``events_public.py``) surfaces :attr:`is_series` / ``event_type``;
* escrow settlement (``event_release.py``, **P14**) reads
  :attr:`settlement_rule` — ``"timing_default"`` means today's timing exactly,
  so landing P10 changes no money behaviour; only ``"per_instance"`` (recurring)
  will alter release timing once P14 wires this map in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

EventType = Literal["standard", "recurring", "free_rsvp", "private"]
Visibility = Literal["public", "unlisted", "private"]
SettlementRule = Literal["timing_default", "per_instance"]

EVENT_TYPES: tuple[EventType, ...] = ("standard", "recurring", "free_rsvp", "private")
VISIBILITIES: tuple[Visibility, ...] = ("public", "unlisted", "private")


@dataclass(frozen=True)
class EventTypePolicy:
    """Behaviour bundle for one ``event_type`` (see module docstring)."""

    event_type: EventType
    #: Visibility applied when the organiser doesn't set one explicitly.
    default_visibility: Visibility
    #: Escrow anchor selection, consumed by ``event_release.py`` (P14).
    #: ``"timing_default"`` == the current lead-time-based schedule (no change).
    settlement_rule: SettlementRule
    #: UX hint — the event is a recurring series.
    is_series: bool
    #: UX hint — the event is free-RSVP only (no paid tickets expected).
    is_free_only: bool


_POLICIES: dict[EventType, EventTypePolicy] = {
    "standard": EventTypePolicy("standard", "public", "timing_default", False, False),
    "recurring": EventTypePolicy("recurring", "public", "per_instance", True, False),
    "free_rsvp": EventTypePolicy("free_rsvp", "public", "timing_default", False, True),
    "private": EventTypePolicy("private", "private", "timing_default", False, False),
}

_DEFAULT_POLICY = _POLICIES["standard"]


def normalize_event_type(value: str | None) -> EventType:
    """Coerce an arbitrary/legacy value to a known event_type (default standard)."""
    for candidate in EVENT_TYPES:
        if value == candidate:
            return candidate
    return "standard"


def policy_for(event_type: str | None) -> EventTypePolicy:
    """Return the behaviour bundle for an event_type, defaulting to ``standard``."""
    return _POLICIES.get(normalize_event_type(event_type), _DEFAULT_POLICY)
