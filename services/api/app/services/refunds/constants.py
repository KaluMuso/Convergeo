"""Shared refund status constants (no service imports — safe for escrow modules)."""

from __future__ import annotations

ACTIVE_REFUND_STATUSES = frozenset(
    {
        "pending",
        "processing",
        "awaiting_payout",
        "needs_destination",
        "manual_review",
        "completed",
    }
)
TERMINAL_REFUND_STATUSES = frozenset({"completed", "failed"})
AWAITING_PROVIDER_STATUSES = frozenset(
    {"awaiting_payout", "needs_destination", "manual_review"}
)
