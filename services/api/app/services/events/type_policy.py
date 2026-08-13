"""Single source of truth for ``event_type``-driven behaviour (D29 / Wave A).

``event_type`` is a *full behavioural driver*: it governs discovery visibility
defaults, escrow settlement timing, and UX flags. To keep that behaviour
auditable and the money path guarded, every per-type rule lives here — no
consumer branches on ``event_type`` inline. Consumers:

* organiser writes (``organiser_events.py``) read :attr:`default_visibility`
  when the organiser doesn't set visibility explicitly;
* discovery (``events_public.py``) surfaces :attr:`is_series` / ``event_type``;
* escrow settlement (``event_release.py``, **P14**) reads
  :attr:`settlement_rule` — ``"timing_default"`` is the current lead-time-based
  schedule (≤14d full at end+24h; >14d 50% at start−7d + 50% at end+1d), while
  ``"full_only"`` (recurring) forces a single full release at end+24h with no
  pre-event phased advance. Only ``recurring`` differs from today's timing, and
  because ``event_type`` defaults to ``standard`` every existing order is
  unaffected — recurring is opt-in going forward.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

EventType = Literal["standard", "single", "multi_day", "recurring", "free_rsvp", "private"]
Visibility = Literal["public", "unlisted", "private"]
SettlementRule = Literal["timing_default", "full_only"]

EVENT_TYPES: tuple[EventType, ...] = (
    "standard",  # compatibility for events created before the strategy rollout
    "single",
    "multi_day",
    "recurring",
    "free_rsvp",
    "private",
)
VISIBILITIES: tuple[Visibility, ...] = ("public", "unlisted", "private")


@dataclass(frozen=True)
class EventTypePolicy:
    """Behaviour bundle for one ``event_type`` (see module docstring)."""

    event_type: EventType
    #: Visibility applied when the organiser doesn't set one explicitly.
    default_visibility: Visibility
    #: Escrow branch selection, consumed by ``event_release.py`` (P14).
    #: ``"timing_default"`` == the current lead-time-based schedule; ``"full_only"``
    #: forces a single full release at end+24h (no >14d phased advance).
    settlement_rule: SettlementRule
    #: UX hint — the event is a recurring series.
    is_series: bool
    #: UX hint — the event is free-RSVP only (no paid tickets expected).
    is_free_only: bool


_POLICIES: dict[EventType, EventTypePolicy] = {
    "standard": EventTypePolicy("standard", "public", "timing_default", False, False),
    "single": EventTypePolicy("single", "public", "timing_default", False, False),
    "multi_day": EventTypePolicy("multi_day", "public", "timing_default", False, False),
    "recurring": EventTypePolicy("recurring", "public", "full_only", True, False),
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


def normalize_visibility(value: str | None) -> Visibility:
    """Coerce an arbitrary value to a known visibility (default public)."""
    for candidate in VISIBILITIES:
        if value == candidate:
            return candidate
    return "public"


def policy_for(event_type: str | None) -> EventTypePolicy:
    """Return the behaviour bundle for an event_type, defaulting to ``standard``."""
    return _POLICIES.get(normalize_event_type(event_type), _DEFAULT_POLICY)
