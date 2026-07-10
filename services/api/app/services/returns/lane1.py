"""Lane-1 returns (faulty/wrong) — window/evidence gates, accept→refund, contest→dispute."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, cast
from uuid import uuid4

from app.errors import AppError
from app.services.ledger.engine import post_transaction
from app.services.ledger.templates import LedgerTemplate
from app.services.notifications.dedupe import enqueue_outbox_row
from app.services.refunds.execute import execute_refund
from app.services.refunds.math import compute_lane1_refund

logger = logging.getLogger(__name__)

REPORT_WINDOW_HOURS = 48
DEFAULT_RETURN_SHIPPING_NGWEE = 5_000
RETURN_VENDOR_NOTIFY_TEMPLATE = "return-vendor-action-required"


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
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
    created_at = str(rows[0].get("created_at") or "")
    return _parse_timestamp(created_at)


def _within_report_window(delivered_at: datetime | None, *, now: datetime | None = None) -> bool:
    if delivered_at is None:
        return False
    reference = now or datetime.now(tz=UTC)
    return reference - delivered_at <= timedelta(hours=REPORT_WINDOW_HOURS)


def _load_order_item_context(
    service_client: ServiceRoleClient,
    order_item_id: str,
) -> dict[str, Any]:
    response = (
        service_client.client.table("order_items")
        .select("id, order_id, qty, unit_price_ngwee, title_snapshot")
        .eq("id", order_item_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(code="not_found", message="Order item not found", http_status=404)
    return row


def _load_order_row(service_client: ServiceRoleClient, order_id: str) -> dict[str, Any]:
    response = (
        service_client.client.table("orders")
        .select("id, customer_id, vendor_id, delivery_fee_ngwee, status")
        .eq("id", order_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(code="not_found", message="Order not found", http_status=404)
    return row


def _assert_customer_owns_item(
    service_client: ServiceRoleClient,
    *,
    order_item_id: str,
    customer_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    item = _load_order_item_context(service_client, order_item_id)
    order = _load_order_row(service_client, str(item["order_id"]))
    if str(order.get("customer_id")) != customer_id:
        raise AppError(code="not_found", message="Order item not found", http_status=404)
    return item, order


def _assert_evidence_paths(
    evidence_paths: list[str],
    *,
    customer_id: str,
    order_id: str,
) -> None:
    if len(evidence_paths) < 1:
        raise AppError(
            code="validation_error",
            message="At least one photo evidence file is required",
            http_status=400,
            details={"evidence_paths": "required"},
        )
    expected_prefix = f"orders/{customer_id}/{order_id}/"
    for path in evidence_paths:
        normalized = path.replace("\\", "/").lstrip("/")
        if not normalized.startswith(expected_prefix) or ".." in normalized:
            raise AppError(
                code="validation_error",
                message="Evidence path must belong to this order",
                http_status=422,
                details={"path": path},
            )


def _item_ngwee(item: dict[str, Any]) -> int:
    qty = item.get("qty", 0)
    unit = item.get("unit_price_ngwee", 0)
    if not isinstance(qty, int) or not isinstance(unit, int):
        return 0
    return qty * unit


def _lane1_fee_breakdown(*, item: dict[str, Any], order: dict[str, Any]) -> dict[str, int | str]:
    item_total = _item_ngwee(item)
    delivery = int(order.get("delivery_fee_ngwee", 0))
    amounts = compute_lane1_refund(item_ngwee=item_total, delivery_fee_ngwee=delivery)
    return {
        "item_ngwee": amounts.item_ngwee,
        "delivery_ngwee": amounts.delivery_fee_ngwee,
        "total_ngwee": amounts.refund_ngwee,
        "return_shipping_charged_to": "vendor",
    }


def preview_lane1_breakdown(
    service_client: ServiceRoleClient,
    *,
    order_item_id: str,
    customer_id: str,
) -> dict[str, Any]:
    """Return lane-1 refund breakdown for customer preview (no side effects)."""
    item, order = _assert_customer_owns_item(
        service_client,
        order_item_id=order_item_id,
        customer_id=customer_id,
    )
    delivered_at = _load_delivered_at(service_client, str(order["id"]))
    return {
        "lane": 1,
        "order_item_id": order_item_id,
        "order_id": str(order["id"]),
        "within_window": _within_report_window(delivered_at),
        "fee_breakdown": _lane1_fee_breakdown(item=item, order=order),
    }


def _load_return_shipping_ngwee(service_client: ServiceRoleClient, *, order: dict[str, Any]) -> int:
    delivery_fallback = int(order.get("delivery_fee_ngwee", 0)) or DEFAULT_RETURN_SHIPPING_NGWEE
    try:
        response = (
            service_client.client.table("platform_config")
            .select("value")
            .eq("key", "lane1_return_shipping_ngwee")
            .maybe_single()
            .execute()
        )
        row = _single_row(response)
        if row is None:
            return delivery_fallback
        value = row.get("value")
        if isinstance(value, int):
            return max(value, 0)
        if isinstance(value, str) and value.isdigit():
            return int(value)
    except Exception:
        logger.warning(
            "Could not read lane1_return_shipping_ngwee; using delivery fallback",
            exc_info=True,
        )
    return delivery_fallback


def _notify_vendor(
    service_client: ServiceRoleClient,
    *,
    return_id: str,
    order_id: str,
    vendor_id: str,
) -> None:
    enqueue_outbox_row(
        service_client.client,
        event_type="return-vendor-action",
        entity_id=return_id,
        channel="whatsapp",
        template=RETURN_VENDOR_NOTIFY_TEMPLATE,
        payload={
            "return_id": return_id,
            "order_id": order_id,
            "vendor_id": vendor_id,
        },
    )


def create_lane1_return(
    service_client: ServiceRoleClient,
    *,
    order_item_id: str,
    customer_id: str,
    evidence_paths: list[str],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Create a lane-1 return request after window/evidence gates."""
    item, order = _assert_customer_owns_item(
        service_client,
        order_item_id=order_item_id,
        customer_id=customer_id,
    )
    order_id = str(order["id"])
    status = str(order.get("status", ""))
    if status not in {"shipped", "delivered", "completed"}:
        raise AppError(
            code="validation_error",
            message="Returns can only be filed after the order has shipped",
            http_status=409,
            details={"status": status},
        )

    _assert_evidence_paths(evidence_paths, customer_id=customer_id, order_id=order_id)

    delivered_at = _load_delivered_at(service_client, order_id)
    if not _within_report_window(delivered_at, now=now):
        raise AppError(
            code="validation_error",
            message="The 48-hour return window has expired",
            http_status=400,
            details={"window_hours": REPORT_WINDOW_HOURS},
        )

    existing = (
        service_client.client.table("returns")
        .select("id, status")
        .eq("order_item_id", order_item_id)
        .in_("status", ["requested", "approved"])
        .limit(1)
        .execute()
    )
    if _rows(existing):
        raise AppError(
            code="validation_error",
            message="A return is already in progress for this item",
            http_status=409,
        )

    fee_breakdown = _lane1_fee_breakdown(item=item, order=order)
    return_id = str(uuid4())
    row = {
        "id": return_id,
        "order_item_id": order_item_id,
        "lane": 1,
        "evidence_paths": evidence_paths,
        "fee_breakdown": fee_breakdown,
        "status": "requested",
    }
    response = service_client.client.table("returns").insert(row).execute()
    inserted = _single_row(response)
    if inserted is None:
        rows = _rows(response)
        inserted = rows[0] if rows else row

    _notify_vendor(
        service_client,
        return_id=str(inserted.get("id", return_id)),
        order_id=order_id,
        vendor_id=str(order["vendor_id"]),
    )
    return inserted


def _load_return_row(service_client: ServiceRoleClient, return_id: str) -> dict[str, Any]:
    response = (
        service_client.client.table("returns")
        .select("*")
        .eq("id", return_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(code="not_found", message="Return not found", http_status=404)
    return row


def _load_vendor_for_owner(service_client: ServiceRoleClient, owner_user_id: str) -> dict[str, Any]:
    response = (
        service_client.client.table("vendors")
        .select("id, owner_user_id")
        .eq("owner_user_id", owner_user_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(code="forbidden", message="Vendor profile not found", http_status=403)
    return row


def _assert_vendor_owns_return(
    service_client: ServiceRoleClient,
    *,
    return_row: dict[str, Any],
    vendor_owner_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    vendor = _load_vendor_for_owner(service_client, vendor_owner_id)
    item = _load_order_item_context(service_client, str(return_row["order_item_id"]))
    order = _load_order_row(service_client, str(item["order_id"]))
    if str(order.get("vendor_id")) != str(vendor["id"]):
        raise AppError(code="not_found", message="Return not found", http_status=404)
    return vendor, item, order


def _load_customer_momo(service_client: ServiceRoleClient, customer_id: str) -> str:
    response = (
        service_client.client.table("profiles")
        .select("phone")
        .eq("id", customer_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    phone = row.get("phone") if row else None
    if not isinstance(phone, str) or len(phone.strip()) < 8:
        raise AppError(
            code="validation_error",
            message="Customer mobile-money number is required for refund",
            http_status=422,
        )
    return phone.strip()


def _charge_return_shipping_to_vendor(
    *,
    return_id: str,
    order_id: str,
    vendor_id: str,
    return_shipping_ngwee: int,
) -> str | None:
    if return_shipping_ngwee <= 0:
        return None
    posted = post_transaction(
        idempotency_key=f"return-{return_id}-shipping",
        template=LedgerTemplate.CLAWBACK,
        order_id=order_id,
        clawback_ngwee=return_shipping_ngwee,
        vendor_id=vendor_id,
    )
    return posted.id


def vendor_accept_lane1_return(
    service_client: ServiceRoleClient,
    *,
    return_id: str,
    vendor_owner_id: str,
) -> dict[str, Any]:
    """Vendor accepts lane-1 return → approve, full refund, return-shipping charge."""
    return_row = _load_return_row(service_client, return_id)
    if int(return_row.get("lane", 0)) != 1:
        raise AppError(code="validation_error", message="Not a lane-1 return", http_status=409)
    if str(return_row.get("status")) != "requested":
        raise AppError(
            code="validation_error",
            message="Return is not awaiting vendor response",
            http_status=409,
            details={"status": return_row.get("status")},
        )

    _vendor, item, order = _assert_vendor_owns_return(
        service_client,
        return_row=return_row,
        vendor_owner_id=vendor_owner_id,
    )
    order_id = str(order["id"])
    customer_id = str(order["customer_id"])
    vendor_id = str(order["vendor_id"])

    service_client.client.table("returns").update({"status": "approved"}).eq(
        "id", return_id
    ).execute()

    customer_momo = _load_customer_momo(service_client, customer_id)
    refund_result = execute_refund(
        service_client=cast(Any, service_client),
        order_id=order_id,
        lane=1,
        customer_momo=customer_momo,
        idempotency_key=f"return-{return_id}-refund",
    )

    return_shipping_ngwee = _load_return_shipping_ngwee(service_client, order=order)
    shipping_txn_id = _charge_return_shipping_to_vendor(
        return_id=return_id,
        order_id=order_id,
        vendor_id=vendor_id,
        return_shipping_ngwee=return_shipping_ngwee,
    )

    service_client.client.table("returns").update({"status": "completed"}).eq(
        "id", return_id
    ).execute()

    updated = _load_return_row(service_client, return_id)
    updated["_refund"] = {
        "refund_id": refund_result.refund_id,
        "phase": refund_result.phase.value,
        "amount_ngwee": refund_result.amount_ngwee,
        "ledger_transaction_ids": list(refund_result.ledger_transaction_ids),
    }
    if shipping_txn_id:
        updated["_return_shipping_ledger_txn_id"] = shipping_txn_id
    updated["_order_item_title"] = item.get("title_snapshot")
    return updated


def vendor_contest_lane1_return(
    service_client: ServiceRoleClient,
    *,
    return_id: str,
    vendor_owner_id: str,
) -> dict[str, Any]:
    """Vendor contests lane-1 return → dispute queue, no auto-refund."""
    return_row = _load_return_row(service_client, return_id)
    if int(return_row.get("lane", 0)) != 1:
        raise AppError(code="validation_error", message="Not a lane-1 return", http_status=409)
    if str(return_row.get("status")) != "requested":
        raise AppError(
            code="validation_error",
            message="Return is not awaiting vendor response",
            http_status=409,
            details={"status": return_row.get("status")},
        )

    _vendor, _item, order = _assert_vendor_owns_return(
        service_client,
        return_row=return_row,
        vendor_owner_id=vendor_owner_id,
    )
    order_id = str(order["id"])
    customer_id = str(order["customer_id"])
    evidence_paths = return_row.get("evidence_paths", [])
    if not isinstance(evidence_paths, list):
        evidence_paths = []

    dispute_response = (
        service_client.client.table("disputes")
        .insert(
            {
                "order_id": order_id,
                "opener_user_id": customer_id,
                "evidence_paths": evidence_paths,
                "status": "open",
            }
        )
        .execute()
    )
    dispute_row = _single_row(dispute_response)
    if dispute_row is None:
        rows = _rows(dispute_response)
        dispute_row = rows[0] if rows else None
    if dispute_row is None or not dispute_row.get("id"):
        raise AppError(code="internal_error", message="Could not create dispute", http_status=500)

    service_client.client.table("returns").update({"status": "rejected"}).eq(
        "id", return_id
    ).execute()

    updated = _load_return_row(service_client, return_id)
    updated["_dispute_id"] = str(dispute_row["id"])
    return updated


def list_vendor_pending_returns(
    service_client: ServiceRoleClient,
    *,
    vendor_owner_id: str,
) -> list[dict[str, Any]]:
    """List lane-1 returns awaiting vendor accept/contest."""
    vendor = _load_vendor_for_owner(service_client, vendor_owner_id)
    vendor_id = str(vendor["id"])

    orders_response = (
        service_client.client.table("orders")
        .select("id, customer_id, delivery_fee_ngwee, created_at")
        .eq("vendor_id", vendor_id)
        .execute()
    )
    order_rows = _rows(orders_response)
    order_ids = {str(row["id"]) for row in order_rows}
    order_by_id = {str(row["id"]): row for row in order_rows}

    if not order_ids:
        return []

    items_response = service_client.client.table("order_items").select("*").execute()
    item_by_id = {
        str(row["id"]): row
        for row in _rows(items_response)
        if str(row.get("order_id")) in order_ids
    }

    returns_response = (
        service_client.client.table("returns")
        .select("*")
        .eq("status", "requested")
        .eq("lane", 1)
        .execute()
    )
    pending: list[dict[str, Any]] = []
    for ret in _rows(returns_response):
        item = item_by_id.get(str(ret.get("order_item_id")))
        if item is None:
            continue
        order = order_by_id.get(str(item.get("order_id")))
        if order is None:
            continue
        pending.append(
            {
                "id": str(ret["id"]),
                "order_id": str(item["order_id"]),
                "order_item_id": str(item["id"]),
                "lane": 1,
                "status": str(ret["status"]),
                "fee_breakdown": ret.get("fee_breakdown", {}),
                "evidence_count": len(ret.get("evidence_paths") or []),
                "item_title": item.get("title_snapshot") or "Item",
                "item_qty": item.get("qty", 1),
                "created_at": ret.get("created_at"),
                "order_created_at": order.get("created_at"),
            }
        )
    pending.sort(key=lambda row: str(row.get("created_at", "")), reverse=True)
    return pending
