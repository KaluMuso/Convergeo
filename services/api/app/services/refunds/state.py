"""Refund state machine — provider-authoritative completion (REFUND-PROVIDER-AUTHORITY).

Ledger drains at decision time; customer MoMo delivery is confirmed only when Lenco
reports the linked ``rfd-*`` transfer successful (payout sweeper / status re-query).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol, cast

from app.errors import AppError
from app.services.orders.audit import run_sql_script, sql_literal
from app.services.payments.state import SYSTEM_ACTOR_ID

from app.services.refunds.constants import (
    ACTIVE_REFUND_STATUSES,
    AWAITING_PROVIDER_STATUSES,
    TERMINAL_REFUND_STATUSES,
)

REFUND_AUDIT_ACTION = "refund.transition"


class RefundStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    AWAITING_PAYOUT = "awaiting_payout"
    NEEDS_DESTINATION = "needs_destination"
    MANUAL_REVIEW = "manual_review"
    COMPLETED = "completed"
    FAILED = "failed"


class RefundEvent(StrEnum):
    PAYOUT_QUEUED = "payout_queued"
    PROVIDER_PAID = "provider_paid"
    PROVIDER_FAILED = "provider_failed"


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [cast(dict[str, Any], row) for row in data if isinstance(row, dict)]
    return []


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return cast(dict[str, Any], data)
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            return cast(dict[str, Any], first)
    return None


def _write_audit(
    service_client: ServiceRoleClient,
    *,
    refund_id: str,
    event: RefundEvent,
    before_status: str,
    after_status: str,
    detail: dict[str, Any] | None = None,
) -> None:
    payload = {
        "refund_id": refund_id,
        "event": event.value,
        "from_status": before_status,
        "to_status": after_status,
    }
    if detail:
        payload.update(detail)
    service_client.client.table("audit_log").insert(
        {
            "actor": SYSTEM_ACTOR_ID,
            "action": REFUND_AUDIT_ACTION,
            "entity_type": "refund",
            "entity_id": refund_id,
            "before": {"status": before_status},
            "after": payload,
        }
    ).execute()


def _load_refund_row(
    service_client: ServiceRoleClient, refund_id: str
) -> dict[str, Any] | None:
    response = (
        service_client.client.table("refunds")
        .select("id, order_id, status, payout_ref, breakdown")
        .eq("id", refund_id)
        .maybe_single()
        .execute()
    )
    return _single_row(response)


def _find_refund_by_payout_ref(
    service_client: ServiceRoleClient, payout_id: str
) -> dict[str, Any] | None:
    response = (
        service_client.client.table("refunds")
        .select("id, order_id, status, payout_ref, breakdown")
        .eq("payout_ref", payout_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = _rows(response)
    return rows[0] if rows else None


def mark_refund_awaiting_payout(
    service_client: ServiceRoleClient,
    *,
    refund_id: str,
    payout_ref: str,
    breakdown: dict[str, Any],
) -> None:
    """Transition processing → awaiting_payout after ledger + pending payout row."""
    row = _load_refund_row(service_client, refund_id)
    if row is None:
        raise AppError("refund_not_found", "Refund not found", 404, {"refund_id": refund_id})

    current = str(row.get("status") or "")
    if current == RefundStatus.COMPLETED.value:
        return
    if current == RefundStatus.AWAITING_PAYOUT.value:
        return
    if current not in {RefundStatus.PROCESSING.value, RefundStatus.PENDING.value}:
        raise AppError(
            "refund_invalid_transition",
            f"Cannot queue payout from status {current}",
            409,
            {"refund_id": refund_id, "status": current},
        )

    service_client.client.table("refunds").update(
        {
            "status": RefundStatus.AWAITING_PAYOUT.value,
            "payout_ref": payout_ref,
            "breakdown": breakdown,
        }
    ).eq("id", refund_id).execute()
    _write_audit(
        service_client,
        refund_id=refund_id,
        event=RefundEvent.PAYOUT_QUEUED,
        before_status=current,
        after_status=RefundStatus.AWAITING_PAYOUT.value,
        detail={"payout_ref": payout_ref},
    )


def complete_refund_from_provider_payout(
    service_client: ServiceRoleClient,
    *,
    payout_id: str,
    provider_status: str | None = None,
) -> bool:
    """Idempotently mark refund completed when Lenco confirms the customer payout."""
    refund = _find_refund_by_payout_ref(service_client, payout_id)
    if refund is None:
        return False

    refund_id = str(refund["id"])
    current = str(refund.get("status") or "")
    if current == RefundStatus.COMPLETED.value:
        return True
    if current not in AWAITING_PROVIDER_STATUSES:
        return False

    service_client.client.table("refunds").update(
        {"status": RefundStatus.COMPLETED.value}
    ).eq("id", refund_id).execute()
    _write_audit(
        service_client,
        refund_id=refund_id,
        event=RefundEvent.PROVIDER_PAID,
        before_status=current,
        after_status=RefundStatus.COMPLETED.value,
        detail={
            "payout_ref": payout_id,
            "provider_status": provider_status,
        },
    )
    return True


def fail_refund_from_provider_payout(
    service_client: ServiceRoleClient,
    *,
    payout_id: str,
    reason: str,
    provider_status: str | None = None,
    dead_lettered: bool = False,
) -> bool:
    """Mark refund failed when the customer payout cannot be delivered."""
    refund = _find_refund_by_payout_ref(service_client, payout_id)
    if refund is None:
        return False

    refund_id = str(refund["id"])
    current = str(refund.get("status") or "")
    if current == RefundStatus.FAILED.value:
        return True
    if current == RefundStatus.COMPLETED.value:
        return False
    if current not in AWAITING_PROVIDER_STATUSES:
        return False

    raw_breakdown = refund.get("breakdown")
    breakdown: dict[str, Any] = dict(raw_breakdown) if isinstance(raw_breakdown, dict) else {}
    breakdown["provider_failure_reason"] = reason
    if provider_status:
        breakdown["provider_status"] = provider_status
    if dead_lettered:
        breakdown["dead_lettered"] = True

    service_client.client.table("refunds").update(
        {"status": RefundStatus.FAILED.value, "breakdown": breakdown}
    ).eq("id", refund_id).execute()
    _write_audit(
        service_client,
        refund_id=refund_id,
        event=RefundEvent.PROVIDER_FAILED,
        before_status=current,
        after_status=RefundStatus.FAILED.value,
        detail={
            "payout_ref": payout_id,
            "reason": reason,
            "provider_status": provider_status,
            "dead_lettered": dead_lettered,
        },
    )
    return True


def refund_provider_complete(order_id: str) -> bool:
    """True when at least one refund for the order reached provider-paid completion."""
    order_sql = sql_literal(order_id) + "::uuid"
    script = f"""
SELECT count(*)::text
FROM public.refunds
WHERE order_id = {order_sql}
  AND status = 'completed';
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        return False
    return int(result.rows[0]) > 0


def refund_awaiting_provider(order_id: str) -> bool:
    """True when a refund is in-flight waiting on Lenco customer payout."""
    statuses_sql = ", ".join(
        sql_literal(status) for status in sorted(AWAITING_PROVIDER_STATUSES)
    )
    order_sql = sql_literal(order_id) + "::uuid"
    script = f"""
SELECT count(*)::text
FROM public.refunds
WHERE order_id = {order_sql}
  AND status IN ({statuses_sql});
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        return False
    return int(result.rows[0]) > 0
