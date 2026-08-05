"""Tests for order.created n8n payload shaping."""

from __future__ import annotations

from app.services.orders.create import CreatedOrder, CreatedOrderItem
from app.services.orders.n8n_payload import (
    build_order_created_payload,
    mask_display_name,
    mask_phone_e164,
)


def test_mask_phone_e164_hides_middle_digits() -> None:
    assert mask_phone_e164("+260971234567") == "+260 ••• ••567"


def test_mask_display_name_partial() -> None:
    assert mask_display_name("Chanda Banda") == "C***"
    assert mask_display_name(None) is None


def test_build_order_created_payload_shape() -> None:
    order = CreatedOrder(
        order_id="ord-1",
        vendor_id="ven-1",
        fulfilment="delivery",
        delivery_zone="lusaka_central",
        delivery_fee_ngwee=5_000,
        subtotal_ngwee=120_000,
        cod=False,
        commission_snapshot={"rate_bps": 500},
        items=(
            CreatedOrderItem(
                order_item_id="item-1",
                listing_id="list-1",
                qty=2,
                unit_price_ngwee=60_000,
                line_total_ngwee=120_000,
            ),
        ),
    )
    customer = {
        "id": "cust-1",
        "masked_phone": "+260 ••• ••567",
        "masked_name": "C***",
    }
    payload = build_order_created_payload(
        order=order,
        checkout_group_id="chk-1",
        customer=customer,
    )
    assert payload["order_id"] == "ord-1"
    assert payload["customer"]["masked_phone"] == "+260 ••• ••567"
    assert payload["items"][0]["qty"] == 2
    assert payload["subtotal_ngwee"] == 120_000
