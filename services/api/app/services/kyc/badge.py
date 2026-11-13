from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from app.deps import get_supabase_service_client  # type: ignore[attr-defined]
from app.errors import AppError
from app.services.kyc.state_machine import ServiceRoleClient, write_kyc_audit_log

ServiceClient = Any

MIN_COMPLETED_ORDERS = 20
MIN_AVERAGE_RATING = 4.5
MAX_DISPUTE_RATE = 0.02
MAX_CANCEL_RATE = 0.05
TERMINAL_ORDER_STATUSES = frozenset({"completed", "cancelled"})
UPHELD_DISPUTE_STATUSES = frozenset({"resolved_refund"})


@dataclass(frozen=True, slots=True)
class BadgeMetrics:
    completed_orders: int
    average_rating: float | None
    dispute_rate: float
    cancel_rate: float


@dataclass(frozen=True, slots=True)
class BadgeEvaluation:
    vendor_id: str
    qualifies: bool
    metrics: BadgeMetrics
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BadgeChange:
    vendor_id: str
    previous: bool
    current: bool
    evaluation: BadgeEvaluation


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


def _count_rows(response: Any) -> int:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return len(data)
    count = getattr(response, "count", None)
    if isinstance(count, int):
        return count
    return 0


def _load_vendor_badge_state(
    service_client: ServiceRoleClient,
    vendor_id: str,
) -> tuple[bool, dict[str, Any]]:
    response = (
        service_client.client.table("vendors")
        .select("id, preferred_badge")
        .eq("id", vendor_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(code="not_found", message="Vendor not found", http_status=404)
    return bool(row.get("preferred_badge")), row


def compute_badge_metrics(
    service_client: ServiceRoleClient,
    vendor_id: str,
) -> BadgeMetrics:
    client: ServiceClient = service_client.client

    orders_response = (
        client.table("orders")
        .select("id, status", count="exact")
        .eq("vendor_id", vendor_id)
        .execute()
    )
    orders = _rows(orders_response)
    count = orders_response.count
    total_orders = _count_rows(orders_response) if count is not None else len(orders)
    if total_orders == 0:
        return BadgeMetrics(
            completed_orders=0,
            average_rating=None,
            dispute_rate=0.0,
            cancel_rate=0.0,
        )

    completed_orders = sum(1 for row in orders if row.get("status") == "completed")
    cancelled_orders = sum(1 for row in orders if row.get("status") == "cancelled")

    vendor_order_ids = [str(row["id"]) for row in orders]
    upheld_disputes = 0
    if vendor_order_ids:
        disputes_response = (
            client.table("disputes")
            .select("id, status, order_id", count="exact")
            .in_("order_id", vendor_order_ids)
            .in_("status", list(UPHELD_DISPUTE_STATUSES))
            .execute()
        )
        upheld_disputes = _count_rows(disputes_response)

    reviews_response = (
        client.table("reviews")
        .select("rating, order_item_id")
        .eq("status", "published")
        .execute()
    )
    reviews = _rows(reviews_response)
    order_items_response = (
        client.table("order_items")
        .select("id, order_id")
        .execute()
    )
    order_items = _rows(order_items_response)
    order_id_by_item = {
        str(item["id"]): str(item["order_id"])
        for item in order_items
        if item.get("id") is not None and item.get("order_id") is not None
    }
    vendor_ratings = [
        int(review["rating"])
        for review in reviews
        if str(order_id_by_item.get(str(review.get("order_item_id")), "")) in vendor_order_ids
        and isinstance(review.get("rating"), int)
    ]
    average_rating = (
        sum(vendor_ratings) / len(vendor_ratings) if vendor_ratings else None
    )

    dispute_rate = upheld_disputes / total_orders
    cancel_rate = cancelled_orders / total_orders
    return BadgeMetrics(
        completed_orders=completed_orders,
        average_rating=average_rating,
        dispute_rate=dispute_rate,
        cancel_rate=cancel_rate,
    )


def evaluate_preferred_badge(
    service_client: ServiceRoleClient,
    vendor_id: str,
) -> BadgeEvaluation:
    metrics = compute_badge_metrics(service_client, vendor_id)
    reasons: list[str] = []

    if metrics.completed_orders < MIN_COMPLETED_ORDERS:
        reasons.append("insufficient_completed_orders")
    if metrics.average_rating is None or metrics.average_rating < MIN_AVERAGE_RATING:
        reasons.append("rating_below_threshold")
    if metrics.dispute_rate >= MAX_DISPUTE_RATE:
        reasons.append("dispute_rate_too_high")
    if metrics.cancel_rate >= MAX_CANCEL_RATE:
        reasons.append("cancel_rate_too_high")

    return BadgeEvaluation(
        vendor_id=vendor_id,
        qualifies=not reasons,
        metrics=metrics,
        reasons=tuple(reasons),
    )


def apply_preferred_badge_for_vendor(
    service_client: ServiceRoleClient,
    vendor_id: str,
    *,
    actor_id: str = "system:preferred-badge-job",
) -> BadgeChange | None:
    current_badge, vendor_row = _load_vendor_badge_state(service_client, vendor_id)
    evaluation = evaluate_preferred_badge(service_client, vendor_id)
    should_have_badge = evaluation.qualifies

    if current_badge == should_have_badge:
        return None

    before = {"preferred_badge": current_badge}
    response = (
        service_client.client.table("vendors")
        .update({"preferred_badge": should_have_badge})
        .eq("id", vendor_id)
        .execute()
    )
    after_row = _single_row(response) or vendor_row
    after = {"preferred_badge": bool(after_row.get("preferred_badge"))}

    action = (
        "vendor.preferred_badge.grant"
        if should_have_badge
        else "vendor.preferred_badge.revoke"
    )
    write_kyc_audit_log(
        service_client,
        actor_id=actor_id,
        action=action,
        entity_type="vendor",
        entity_id=vendor_id,
        before=before,
        after={
            **after,
            "evaluation": {
                "qualifies": evaluation.qualifies,
                "reasons": list(evaluation.reasons),
                "metrics": {
                    "completed_orders": evaluation.metrics.completed_orders,
                    "average_rating": evaluation.metrics.average_rating,
                    "dispute_rate": evaluation.metrics.dispute_rate,
                    "cancel_rate": evaluation.metrics.cancel_rate,
                },
            },
        },
    )
    return BadgeChange(
        vendor_id=vendor_id,
        previous=current_badge,
        current=should_have_badge,
        evaluation=evaluation,
    )


@dataclass(slots=True)
class PreferredBadgeJob:
    service_client: ServiceRoleClient

    @classmethod
    def default(cls) -> PreferredBadgeJob:
        return cls(get_supabase_service_client())

    def run(self, *, actor_id: str = "system:preferred-badge-job") -> list[BadgeChange]:
        response = (
            self.service_client.client.table("vendors")
            .select("id")
            .eq("status", "active")
            .execute()
        )
        vendors = _rows(response)
        changes: list[BadgeChange] = []
        for vendor in vendors:
            vendor_id = str(vendor["id"])
            change = apply_preferred_badge_for_vendor(
                self.service_client,
                vendor_id,
                actor_id=actor_id,
            )
            if change is not None:
                changes.append(change)
        return changes


def payout_velocity_window_start(hours: int = 24) -> str:
    return (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
