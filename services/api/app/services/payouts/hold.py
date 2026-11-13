"""Escrow minimum-hold enforcement before vendor payouts."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from app.errors import AppError
from app.services.orders.audit import run_sql_script
from app.services.payouts.gate import MIN_ESCROW_HOLD_HOURS

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class EscrowHoldNotElapsedError(AppError):
    """Raised when a payout is attempted before the minimum escrow hold window."""

    def __init__(self, *, hold_until: datetime) -> None:
        super().__init__(
            code="escrow_hold_not_elapsed",
            message=(
                "Payouts are held for 48 hours after payment collection "
                "for buyer protection."
            ),
            http_status=409,
            details={
                "message_key": "vendor.payouts.errors.escrowHoldNotElapsed",
                "hold_until": hold_until.isoformat(),
                "min_hold_hours": MIN_ESCROW_HOLD_HOURS,
            },
        )


def _sql_uuid(value: str, field: str) -> str:
    if not _UUID_RE.match(value):
        msg = f"{field} must be a valid UUID"
        raise ValueError(msg)
    return f"'{value}'::uuid"


def assert_escrow_minimum_hold_elapsed(vendor_id: str) -> None:
    """Block payout when the vendor's newest unreleased escrow is younger than 48h."""
    vendor_sql = _sql_uuid(vendor_id, "vendor_id")
    script = f"""
SELECT max(lt.created_at)::text
FROM public.ledger_transactions lt
JOIN public.orders o ON o.id = lt.order_id
WHERE o.vendor_id = {vendor_sql}
  AND lt.kind IN ('charge_received', 'escrow_hold')
  AND NOT EXISTS (
    SELECT 1
    FROM public.ledger_transactions rel
    WHERE rel.order_id = lt.order_id
      AND rel.kind = 'release_to_vendor'
  );
"""
    result = run_sql_script(script)
    if not result.ok:
        raise AppError(
            code="ledger_query_failed",
            message="Failed to evaluate escrow hold window",
            http_status=500,
            details={"error": result.error},
        )
    if not result.rows or not result.rows[0]:
        return

    raw = result.rows[0]
    try:
        collected_at = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return
    if collected_at.tzinfo is None:
        collected_at = collected_at.replace(tzinfo=UTC)

    hold_until = collected_at + timedelta(hours=MIN_ESCROW_HOLD_HOURS)
    if datetime.now(UTC) < hold_until:
        raise EscrowHoldNotElapsedError(hold_until=hold_until)
