"""M17-P02 — the automated pre-publication screen for clips (D-V8).

This module decides only one thing: whether a clip may **queue for a human**. It
has no path to ``published`` — that edge belongs to ``pending_review`` alone and
is exercised only by the admin action in M17-P07. ``test_no_path_to_published``
asserts that structurally rather than trusting the reading.

The screen itself is the *existing* D8 word-boundary keyword + category fence
from ``services/moderation/prohibited.py``. It is imported, never re-implemented:
a second copy of a prohibited-content list is how the two copies drift, and the
one that drifts is always the one that stops blocking something.

Caption text is **untrusted data**. It is matched against patterns and never
interpolated into a query, a prompt, or a log line verbatim.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Final, Protocol

from app.services.clips import state_machine
from app.services.moderation.prohibited import screen_listing

logger = logging.getLogger(__name__)

#: Caption ceiling. Long enough for a real product pitch, short enough that the
#: keyword screen stays cheap and the feed card stays readable on 360px.
MAX_CAPTION_LEN: Final = 600


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


@dataclass(frozen=True, slots=True)
class ScreenVerdict:
    """What the automated screen decided, and why."""

    allowed: bool
    reason: str | None = None
    matched: str | None = None

    @property
    def rejection_reason(self) -> str:
        """A stable, non-user-facing reason string for the audit trail."""
        if self.allowed:
            return ""
        return f"prohibited_{self.reason or 'content'}"


def screen_text(caption: str | None, category_name: str | None = None) -> ScreenVerdict:
    """Run the shared D8 screen over a clip's caption and category.

    Pure and I/O-free so it can be called *before* an upload slot is issued —
    a prohibited caption should never receive a signed URL in the first place,
    rather than be caught after the bytes are already in Cloudinary.
    """
    if caption is not None and len(caption) > MAX_CAPTION_LEN:
        return ScreenVerdict(allowed=False, reason="caption_too_long", matched=None)

    guard = screen_listing(title=caption, description=None, category=category_name)
    if guard.allowed:
        return ScreenVerdict(allowed=True)
    return ScreenVerdict(allowed=False, reason=guard.reason, matched=guard.matched)


def apply_screen(
    service_client: ServiceRoleClient,
    *,
    clip_id: str,
    caption: str | None,
    category_name: str | None = None,
    actor_id: str | None = None,
) -> ScreenVerdict:
    """Screen a clip in ``screening`` and route it onward.

    Pass ⇒ guarded transition to ``pending_review`` (a human approves later).
    Fail ⇒ guarded transition to ``rejected`` with the reason recorded.

    Both branches go through M17-P01's state machine, so both are audited and
    both are race-safe. Neither branch can reach ``published``.
    """
    verdict = screen_text(caption, category_name)

    if verdict.allowed:
        state_machine.pass_screening(service_client, clip_id=clip_id, actor_id=actor_id)
        return verdict

    # Log the classification, never the caption: the text is untrusted and may
    # be adversarial, and the reason is what an operator actually needs.
    logger.info(
        "clip rejected by automated screen",
        extra={"clip_id": clip_id, "reason": verdict.reason},
    )
    state_machine.reject(
        service_client,
        clip_id=clip_id,
        reason=verdict.rejection_reason,
        actor_id=actor_id,
    )
    return verdict
