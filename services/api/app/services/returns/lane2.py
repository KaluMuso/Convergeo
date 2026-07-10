"""Lane-2 (change-of-mind) returns — eligibility, fee breakdown, return creation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol, cast

from app.errors import AppError
from app.services.refunds.config import load_restocking_fee_bps
from app.services.refunds.execute import RefundExecutionResult, execute_refund
from app.services.refunds.math import compute_lane2_refund, normalize_restocking_fee_bps
from app.services.refunds.payout_port import CustomerRail

MIN_RETURN_WINDOW_HOURS = 48
MAX_RETURN_WINDOW_HOURS = 168
DEFAULT_RETURN_WINDOW_HOURS = 48

DEFAULT_RESTOCKING_PCT = 10
MIN_RESTOCKING_PCT = 5
MAX_RESTOCKING_PCT = 15

# TODO(M09-P08): read from platform_config when admin exposes restocking_fee_pct.
RESTOCKING_PCT_CONFIG_KEY = "restocking_fee_pct"

IneligibleReason = Literal[
    "order_item_not_found",
    "owner_mismatch",
    "listing_not_returnable",
    "return_window_expired",
    "order_not_delivered",
    "unused_not_declared",
]


class ServiceRoleClient(Protocol):
    client: Any


@dataclass(frozen=True, slots=True)
class Lane2Eligibility:
    eligible: bool
    reason: IneligibleReason | None = None
    return_window_hours: int | None = None


@dataclass(frozen=True, slots=True)
class Lane2Breakdown:
    item: int
    outbound_delivery: int
    return_transport: int
    restocking: int
    refund_ngwee: int

    def as_dict(self) -> dict[str, int]:
        return {
            "item": self.item,
            "outbound_delivery": self.outbound_delivery,
            "return_transport": self.return_transport,
            "restocking": self.restocking,
            "refund_ngwee": self.refund_ngwee,
        }


@dataclass(frozen=True, slots=True)
class Lane2ReturnRecord:
    return_id: str
    order_id: str
    order_item_id: str
    fee_breakdown: dict[str, int]
    refund: RefundExecutionResult


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


def _parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def normalize_return_window_hours(raw: int | None) -> int:
    """Clamp listing return window to 48h–168h; default 48h when absent."""
    if raw is None:
        return DEFAULT_RETURN_WINDOW_HOURS
    return max(MIN_RETURN_WINDOW_HOURS, min(MAX_RETURN_WINDOW_HOURS, raw))


def normalize_restocking_pct(raw: int | None) -> int:
    """Clamp restocking percentage to 5–15; default 10 when absent."""
    if raw is None:
        return DEFAULT_RESTOCKING_PCT
    return max(MIN_RESTOCKING_PCT, min(MAX_RESTOCKING_PCT, raw))


def _single_config_value(response: Any) -> Any | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data.get("value")
    return None


def load_restocking_pct(service_client: ServiceRoleClient) -> int:
    """Read restocking % from platform config, else derive from M08 bps config."""
    response = (
        service_client.client.table("platform_config")
        .select("value")
        .eq("key", RESTOCKING_PCT_CONFIG_KEY)
        .maybe_single()
        .execute()
    )
    raw = _single_config_value(response)
    if isinstance(raw, bool):
        return normalize_restocking_pct(None)
    if isinstance(raw, int):
        return normalize_restocking_pct(raw)
    if isinstance(raw, float):
        return normalize_restocking_pct(int(raw))
    if isinstance(raw, str):
        try:
            return normalize_restocking_pct(int(raw))
        except ValueError:
            return normalize_restocking_pct(None)
    # Align with M08-P10 execution when pct key is not configured yet.
    bps = load_restocking_fee_bps(service_client)
    return normalize_restocking_pct(bps // 100)


def _restocking_bps_from_pct(restocking_pct: int) -> int:
    return normalize_restocking_fee_bps(normalize_restocking_pct(restocking_pct) * 100)


def compute_lane2_breakdown(
    *,
    item_ngwee: int,
    outbound_delivery_ngwee: int,
    return_transport_ngwee: int,
    restocking_pct: int,
) -> Lane2Breakdown:
    """Itemized lane-2 refund preview — integer ngwee, matches M08-P10 lane-2 math."""
    lane2 = compute_lane2_refund(
        item_ngwee=item_ngwee,
        outbound_delivery_ngwee=outbound_delivery_ngwee,
        return_transport_ngwee=return_transport_ngwee,
        restocking_fee_bps=_restocking_bps_from_pct(restocking_pct),
    )
    return Lane2Breakdown(
        item=lane2.item_ngwee,
        outbound_delivery=lane2.outbound_delivery_ngwee,
        return_transport=lane2.return_transport_ngwee,
        restocking=lane2.restocking_fee_ngwee,
        refund_ngwee=lane2.refund_ngwee,
    )


def _load_delivered_at(service_client: ServiceRoleClient, order_id: str) -> datetime | None:
    response = (
        service_client.client.table("order_events")
        .select("created_at, to_status")
        .eq("order_id", order_id)
        .eq("to_status", "delivered")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = _rows(response)
    if not rows:
        return None
    return _parse_timestamp(str(rows[0].get("created_at") or ""))


def _within_return_window(
    delivered_at: datetime | None,
    *,
    window_hours: int,
    now: datetime | None = None,
) -> bool:
    if delivered_at is None:
        return False
    reference = now or datetime.now(tz=UTC)
    return reference - delivered_at <= timedelta(hours=window_hours)


def _load_order_item_context(
    service_client: ServiceRoleClient,
    *,
    order_item_id: str,
) -> dict[str, Any]:
    response = (
        service_client.client.table("order_items")
        .select("id, order_id, qty, unit_price_ngwee")
        .eq("id", order_item_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError("not_found", "Order item not found", 404)
    return row


def _load_order(
    service_client: ServiceRoleClient,
    *,
    order_id: str,
) -> dict[str, Any]:
    response = (
        service_client.client.table("orders")
        .select("id, customer_id, delivery_fee_ngwee")
        .eq("id", order_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError("not_found", "Order not found", 404)
    return row


def _load_listing_for_order_item(
    service_client: ServiceRoleClient,
    *,
    order_item_id: str,
) -> dict[str, Any]:
    link_response = (
        service_client.client.table("order_item_products")
        .select("listing_id")
        .eq("order_item_id", order_item_id)
        .maybe_single()
        .execute()
    )
    link = _single_row(link_response)
    if link is None or not link.get("listing_id"):
        raise AppError("not_found", "Listing not found for order item", 404)

    listing_response = (
        service_client.client.table("vendor_listings")
        .select("returnable, return_window_hours")
        .eq("id", str(link["listing_id"]))
        .maybe_single()
        .execute()
    )
    listing = _single_row(listing_response)
    if listing is None:
        raise AppError("not_found", "Listing not found for order item", 404)
    return listing


def _item_ngwee(order_item: dict[str, Any]) -> int:
    qty = int(order_item.get("qty", 0))
    unit = int(order_item.get("unit_price_ngwee", 0))
    return max(0, qty * unit)


def _prorated_outbound_delivery(
    service_client: ServiceRoleClient,
    *,
    order_id: str,
    order_item: dict[str, Any],
    delivery_fee_ngwee: int,
) -> int:
    response = (
        service_client.client.table("order_items")
        .select("qty, unit_price_ngwee")
        .eq("order_id", order_id)
        .execute()
    )
    items = _rows(response)
    if len(items) <= 1:
        return max(0, delivery_fee_ngwee)

    order_subtotal = 0
    for row in items:
        qty = int(row.get("qty", 0))
        unit = int(row.get("unit_price_ngwee", 0))
        order_subtotal += max(0, qty * unit)
    if order_subtotal <= 0:
        return 0

    item_subtotal = _item_ngwee(order_item)
    return (max(0, delivery_fee_ngwee) * item_subtotal) // order_subtotal


def check_eligibility(
    service_client: ServiceRoleClient,
    *,
    order_item_id: str,
    customer_id: str,
    now: datetime | None = None,
) -> Lane2Eligibility:
    """Returnable listing + owner-scoped + within listing return window."""
    try:
        order_item = _load_order_item_context(service_client, order_item_id=order_item_id)
    except AppError:
        return Lane2Eligibility(eligible=False, reason="order_item_not_found")

    order = _load_order(service_client, order_id=str(order_item["order_id"]))
    if str(order.get("customer_id")) != customer_id:
        return Lane2Eligibility(eligible=False, reason="owner_mismatch")

    listing = _load_listing_for_order_item(service_client, order_item_id=order_item_id)
    if not bool(listing.get("returnable")):
        return Lane2Eligibility(eligible=False, reason="listing_not_returnable")

    window_hours = normalize_return_window_hours(
        int(listing["return_window_hours"])
        if listing.get("return_window_hours") is not None
        else None
    )
    delivered_at = _load_delivered_at(service_client, str(order_item["order_id"]))
    if not _within_return_window(delivered_at, window_hours=window_hours, now=now):
        return Lane2Eligibility(
            eligible=False,
            reason="return_window_expired" if delivered_at is not None else "order_not_delivered",
            return_window_hours=window_hours,
        )

    return Lane2Eligibility(eligible=True, return_window_hours=window_hours)


def create_lane2_return(
    service_client: ServiceRoleClient,
    *,
    order_item_id: str,
    customer_id: str,
    unused_declared: bool = False,
    return_transport_ngwee: int = 0,
    customer_momo: str | None = None,
    customer_rail: CustomerRail = "mtn",
) -> Lane2ReturnRecord:
    """Insert lane-2 return row and execute M08-P10 lane-2 refund."""
    if not unused_declared:
        raise AppError(
            "validation_error",
            "Customer must declare the item is unused and in original condition",
            422,
            {"reason": "unused_not_declared"},
        )

    eligibility = check_eligibility(
        service_client,
        order_item_id=order_item_id,
        customer_id=customer_id,
    )
    if not eligibility.eligible:
        raise AppError(
            "return_ineligible",
            "This order item is not eligible for a change-of-mind return",
            422,
            {"reason": eligibility.reason},
        )

    order_item = _load_order_item_context(service_client, order_item_id=order_item_id)
    order_id = str(order_item["order_id"])
    order = _load_order(service_client, order_id=order_id)
    if str(order.get("customer_id")) != customer_id:
        raise AppError("not_found", "Order item not found", 404)

    item_ngwee = _item_ngwee(order_item)
    outbound_delivery = _prorated_outbound_delivery(
        service_client,
        order_id=order_id,
        order_item=order_item,
        delivery_fee_ngwee=int(order.get("delivery_fee_ngwee", 0)),
    )
    restocking_pct = load_restocking_pct(service_client)
    breakdown = compute_lane2_breakdown(
        item_ngwee=item_ngwee,
        outbound_delivery_ngwee=outbound_delivery,
        return_transport_ngwee=max(0, return_transport_ngwee),
        restocking_pct=restocking_pct,
    )

    if breakdown.refund_ngwee <= 0:
        raise AppError(
            "refund_amount_zero",
            "Computed lane-2 refund amount is zero",
            422,
            {"order_item_id": order_item_id},
        )

    if not customer_momo:
        raise AppError(
            "validation_error",
            "customer_momo is required to execute lane-2 refund",
            422,
        )

    return_id = str(uuid.uuid4())
    fee_breakdown = breakdown.as_dict()
    insert_row = {
        "id": return_id,
        "order_item_id": order_item_id,
        "lane": 2,
        "evidence_paths": [],
        "fee_breakdown": fee_breakdown,
        "status": "requested",
    }
    insert_response = service_client.client.table("returns").insert(insert_row).execute()
    inserted = _single_row(insert_response)
    if inserted is not None and inserted.get("id"):
        return_id = str(inserted["id"])

    refund = execute_refund(
        service_client=service_client,
        order_id=order_id,
        lane=2,
        return_transport_ngwee=breakdown.return_transport,
        customer_rail=customer_rail,
        customer_momo=customer_momo,
        idempotency_key=f"return-{return_id}",
    )

    if refund.amount_ngwee != breakdown.refund_ngwee:
        raise AppError(
            "refund_mismatch",
            "Executed lane-2 refund does not match preview breakdown",
            500,
            {
                "expected_ngwee": breakdown.refund_ngwee,
                "actual_ngwee": refund.amount_ngwee,
            },
        )

    return Lane2ReturnRecord(
        return_id=return_id,
        order_id=order_id,
        order_item_id=order_item_id,
        fee_breakdown=fee_breakdown,
        refund=refund,
    )
