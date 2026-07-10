"""Dispute lifecycle — state machine and service entrypoints."""

from app.services.disputes.service import (
    DisputeRecord,
    OpenDisputeResult,
    escalate_to_review,
    get_dispute_for_party,
    list_vendor_disputes,
    open_dispute,
    resolve,
    vendor_respond,
)
from app.services.disputes.state import (
    ActorRole,
    DisputeEvent,
    DisputeStatus,
    DisputeTransitionError,
    transition_dispute,
)

__all__ = [
    "ActorRole",
    "DisputeEvent",
    "DisputeRecord",
    "DisputeStatus",
    "DisputeTransitionError",
    "OpenDisputeResult",
    "escalate_to_review",
    "get_dispute_for_party",
    "list_vendor_disputes",
    "open_dispute",
    "resolve",
    "transition_dispute",
    "vendor_respond",
]
