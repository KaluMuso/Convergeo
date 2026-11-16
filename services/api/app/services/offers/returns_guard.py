"""W8: a free-gift order line cannot be returned or refunded on its own.

The gift was priced 0, so it carries no refundable value; its reference value
lives on the line (``list_unit_price_ngwee``) for the vendor. When the paid
parent line is returned, the gift travels back with it; the vendor return
queue lists it (``bundled_gifts`` in returns/lane1.py) with that value.
"""

from __future__ import annotations

from typing import Any

from app.errors import AppError


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def assert_not_offer_gift(service_client: Any, order_item_id: str) -> None:
    rows = _rows(
        service_client.client.table("order_items")
        .select("id, is_offer_gift, offer_parent_item_id")
        .eq("id", order_item_id)
        .execute()
    )
    if rows and rows[0].get("is_offer_gift") is True:
        raise AppError(
            code="returns.offer_gift_not_returnable",
            message="A free gift cannot be returned on its own",
            http_status=409,
            details={
                "message_key": "returns.errors.offerGiftNotReturnable",
                "parent_order_item_id": rows[0].get("offer_parent_item_id"),
            },
        )
