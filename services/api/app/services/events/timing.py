"""Shared event-instance timing helpers.

``event_instances.ends_at`` is nullable (migration 0034) for backward
compatibility, so every consumer must resolve an *effective* end time rather
than reading the column directly. There are two deliberately different
fallbacks, kept here so the codebase agrees on them:

* :func:`instance_display_end` — for calendar (.ics DTEND) and discovery
  "still live" cutoffs. Falls back to ``starts_at + DEFAULT_EVENT_DURATION`` so
  an event with no explicit end still occupies a sensible visible block and
  lingers briefly in discovery after it starts.
* :func:`instance_settlement_end` — for money/escrow release timing. Falls back
  to ``starts_at`` (a zero-duration anchor) so legacy instances with no end time
  keep their original ``starts_at``-anchored release schedule unchanged; only
  instances that carry a real ``ends_at`` settle relative to it.
"""

from __future__ import annotations

from datetime import datetime, timedelta

# Fallback visible duration when an instance has no explicit ``ends_at``.
# Mirrors the historical assumption previously hardcoded in event_ics.py and the
# frontend JSON-LD / sitemap helpers.
DEFAULT_EVENT_DURATION = timedelta(hours=2)


def instance_display_end(starts_at: datetime, ends_at: datetime | None) -> datetime:
    """Effective end for display/discovery: explicit end, else start + 2h."""
    if ends_at is not None:
        return ends_at
    return starts_at + DEFAULT_EVENT_DURATION


def instance_settlement_end(starts_at: datetime, ends_at: datetime | None) -> datetime:
    """Effective end for escrow settlement: explicit end, else the start itself.

    Legacy instances (no ``ends_at``) keep their original ``starts_at``-anchored
    release timing; do not extend the hold by a fabricated duration.
    """
    if ends_at is not None:
        return ends_at
    return starts_at
