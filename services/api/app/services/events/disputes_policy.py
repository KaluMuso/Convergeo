"""Event-dispute policy (strategy §7.3).

* Openable until 7 days after the purchased instance end.
* ``event_misrepresentation`` requires at least one evidence path.
* Organiser default window is 72 hours from open.
* Three upheld (resolved_refund) event disputes suspend further ticketed publishes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.errors import AppError

EVENT_DISPUTE_WINDOW = timedelta(days=7)
ORGANISER_RESPOND_SLA = timedelta(hours=72)
UPHELD_SUSPENSION_THRESHOLD = 3
MISREPRESENTATION_KIND = "event_misrepresentation"


def event_dispute_deadline(ends_at: datetime) -> datetime:
    if ends_at.tzinfo is None:
        ends_at = ends_at.replace(tzinfo=UTC)
    return ends_at.astimezone(UTC) + EVENT_DISPUTE_WINDOW


def organiser_respond_by(opened_at: datetime | None = None) -> datetime:
    instant = opened_at or datetime.now(UTC)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=UTC)
    return instant.astimezone(UTC) + ORGANISER_RESPOND_SLA


def assert_event_dispute_openable(
    *,
    ends_at: datetime,
    now: datetime | None = None,
    kind: str,
    evidence_paths: list[str],
) -> None:
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=UTC)
    deadline = event_dispute_deadline(ends_at)
    if instant > deadline:
        raise AppError(
            code="event_dispute_window_closed",
            message="Event disputes close 7 days after the event ends",
            http_status=422,
            details={"message_key": "events.disputes.errors.windowClosed"},
        )
    if kind == MISREPRESENTATION_KIND and not evidence_paths:
        raise AppError(
            code="event_dispute_evidence_required",
            message="Photo or video evidence is required for misrepresentation disputes",
            http_status=422,
            details={"message_key": "events.disputes.errors.evidenceRequired"},
        )
