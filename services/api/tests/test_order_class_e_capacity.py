from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from app.errors import AppError
from app.services.db import SqlResult
from app.services.orders import create as order_create
from app.services.orders.create import CartLineInput, VendorFulfilmentInput

CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
SESSION_ID = "22222222-2222-2222-2222-222222222222"
VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
LISTING_A = "11111111-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
LISTING_B = "22222222-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def _line(*, cart_item_id: str, listing_id: str, qty: int) -> CartLineInput:
    return CartLineInput(
        cart_item_id=cart_item_id,
        listing_id=listing_id,
        vendor_id=VENDOR_ID,
        qty=qty,
        unit_price_ngwee=100,
        title_snapshot="Made-to-order item",
    )


def test_aggregate_listing_quantities_sums_duplicates_in_uuid_order() -> None:
    lines = [
        _line(
            cart_item_id="33333333-3333-3333-3333-333333333333",
            listing_id=LISTING_B,
            qty=1,
        ),
        _line(
            cart_item_id="44444444-4444-4444-4444-444444444444",
            listing_id=LISTING_A,
            qty=2,
        ),
        _line(
            cart_item_id="55555555-5555-5555-5555-555555555555",
            listing_id=LISTING_B,
            qty=3,
        ),
    ]

    assert order_create._aggregate_listing_quantities(lines) == {
        LISTING_A: 2,
        LISTING_B: 4,
    }


def test_capacity_sql_locks_before_check_and_counts_only_current_live_orders() -> None:
    sql = order_create._lock_and_check_class_e_capacity_sql({LISTING_B: 4, LISTING_A: 2})

    assert sql.index(LISTING_A) < sql.index(LISTING_B)
    assert sql.index("FOR UPDATE OF vl") < sql.index("IF v_product_class = 'E'")
    assert "JOIN public.order_items AS oi ON oi.id = oip.order_item_id" in sql
    assert "JOIN public.orders AS o ON o.id = oi.order_id" in sql
    assert "o.status NOT IN ('cancelled', 'refunded')" in sql
    assert "date_trunc('week', timezone('UTC', now())) AT TIME ZONE 'UTC'" in sql
    assert "o.created_at < v_week_start + interval '1 week'" in sql
    assert "v_committed + v_requested > v_capacity" in sql


def test_capacity_marker_maps_to_stable_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lines = [
        _line(
            cart_item_id="33333333-3333-3333-3333-333333333333",
            listing_id=LISTING_A,
            qty=1,
        ),
        _line(
            cart_item_id="44444444-4444-4444-4444-444444444444",
            listing_id=LISTING_A,
            qty=2,
        ),
    ]
    session: dict[str, Any] = {
        "id": SESSION_ID,
        "status": "pending",
        "idempotency_key": "checkout-session-key",
        "subtotal_ngwee": 300,
        "delivery_fee_ngwee": 0,
        "total_ngwee": 300,
    }
    captured: dict[str, str] = {}

    monkeypatch.setattr(
        order_create,
        "_fetch_existing_by_idempotency_key",
        MagicMock(return_value=None),
    )
    monkeypatch.setattr(
        order_create,
        "_fetch_checkout_session",
        MagicMock(return_value=session),
    )
    monkeypatch.setattr(order_create, "_session_expired", MagicMock(return_value=False))
    monkeypatch.setattr(
        order_create,
        "_load_commission_rates",
        MagicMock(return_value={"default": 0}),
    )
    monkeypatch.setattr(
        order_create,
        "_load_listing_commission_keys",
        MagicMock(return_value={}),
    )
    monkeypatch.setattr(
        order_create,
        "_load_product_ids",
        MagicMock(return_value={}),
    )

    def _capacity_failure(script: str) -> SqlResult:
        captured["script"] = script
        return SqlResult(
            ok=False,
            rows=[],
            error=(
                "FIXA_CLASS_E_CAPACITY_EXCEEDED:"
                f"{LISTING_A}:1:3\nCONTEXT: PL/pgSQL function inline_code_block"
            ),
        )

    monkeypatch.setattr(order_create, "run_sql_script", _capacity_failure)

    with pytest.raises(AppError) as exc_info:
        order_create.create_orders_atomic(
            client=MagicMock(),
            customer_id=CUSTOMER_ID,
            session_id=SESSION_ID,
            idempotency_key="submit-key",
            payment_method="momo",
            cart_lines=lines,
            vendor_groups=[
                VendorFulfilmentInput(
                    vendor_id=VENDOR_ID,
                    fulfilment="pickup",
                    delivery_zone=None,
                    delivery_fee_ngwee=0,
                    subtotal_ngwee=300,
                )
            ],
        )

    error = exc_info.value
    assert error.code == "cart.class_e_capacity_exceeded"
    assert error.http_status == 409
    assert error.details == {
        "message_key": "cart.class_e_capacity_exceeded",
        "listing_id": LISTING_A,
        "remaining": 1,
        "requested_qty": 3,
        "retry": True,
    }
    script = captured["script"]
    assert script.index("DO $capacity$") < script.index("INSERT INTO public.orders")
    assert f"'{LISTING_A}'::uuid, 3" in script


def test_hold_consumption_skips_class_e_and_legacy_made_to_order() -> None:
    sql = order_create._consume_reservation_conditional_sql(
        checkout_group_id=SESSION_ID,
        listing_id=LISTING_A,
        qty=2,
    )

    assert "SELECT stock_mode, product_class, fulfilment_mode" in sql
    assert "v_product_class IS DISTINCT FROM 'E'" in sql
    assert "v_fulfilment_mode IS DISTINCT FROM 'made_to_order'" in sql
    assert "DELETE FROM public.stock_reservations" in sql
