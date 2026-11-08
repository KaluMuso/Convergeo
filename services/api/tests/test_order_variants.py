"""Order lines persist the chosen variant and consume its stock atomically."""

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
LISTING = "11111111-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VARIANT = "e0000000-0000-0000-0000-000000000002"


def _patch_preconditions(monkeypatch: pytest.MonkeyPatch) -> None:
    session: dict[str, Any] = {
        "id": SESSION_ID,
        "status": "pending",
        "idempotency_key": "k",
        "subtotal_ngwee": 50_000,
        "delivery_fee_ngwee": 0,
        "total_ngwee": 50_000,
    }
    monkeypatch.setattr(order_create, "_fetch_existing_by_idempotency_key", lambda *a, **k: None)
    monkeypatch.setattr(order_create, "_fetch_checkout_session", lambda *a, **k: session)
    monkeypatch.setattr(order_create, "_session_expired", lambda *a, **k: False)
    monkeypatch.setattr(order_create, "_load_commission_rates", lambda *a: {"default": 0})
    monkeypatch.setattr(order_create, "_load_listing_commission_keys", lambda *a: {})
    monkeypatch.setattr(order_create, "_load_product_ids", lambda *a: {})


def _create() -> None:
    order_create.create_orders_atomic(
        client=MagicMock(),
        customer_id=CUSTOMER_ID,
        session_id=SESSION_ID,
        idempotency_key="submit-key",
        payment_method="momo",
        cart_lines=[
            CartLineInput(
                cart_item_id="33333333-3333-3333-3333-333333333333",
                listing_id=LISTING,
                vendor_id=VENDOR_ID,
                qty=2,
                unit_price_ngwee=25_000,
                title_snapshot="Chitenge dress",
                listing_variant_id=VARIANT,
                variant_snapshot={
                    "listing_variant_id": VARIANT,
                    "sku": "DRS-R-M",
                    "options": [
                        {"group": "Colour", "value": "Red"},
                        {"group": "Size", "value": "M"},
                    ],
                },
            )
        ],
        vendor_groups=[
            VendorFulfilmentInput(
                vendor_id=VENDOR_ID,
                fulfilment="pickup",
                delivery_zone=None,
                delivery_fee_ngwee=0,
                subtotal_ngwee=50_000,
            )
        ],
    )


def test_order_sql_persists_variant_and_consumes_its_stock_in_the_same_tx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_preconditions(monkeypatch)
    captured: dict[str, str] = {}

    def _fail_after_capture(script: str) -> SqlResult:
        captured["script"] = script
        return SqlResult(ok=False, rows=[], error="stop")

    monkeypatch.setattr(order_create, "run_sql_script", _fail_after_capture)
    with pytest.raises(RuntimeError):
        _create()

    script = captured["script"]
    assert "listing_variant_id, variant_snapshot" in script
    assert f"'{VARIANT}'::uuid" in script
    assert '"value":"Red"' in script
    consume = f"SELECT public.consume_listing_variant_stock('{VARIANT}'::uuid, 2);"
    assert consume in script
    # Inside the transaction: after BEGIN, before COMMIT.
    assert script.index("BEGIN;") < script.index(consume) < script.index("COMMIT;")


@pytest.mark.parametrize(
    ("marker", "code"),
    [
        (f"VARIANT_OUT_OF_STOCK:{VARIANT}:1", "cart.variant_out_of_stock"),
        (f"VARIANT_UNAVAILABLE:{VARIANT}", "cart.variant_unavailable"),
    ],
)
def test_variant_stock_failure_maps_to_stable_conflict(
    monkeypatch: pytest.MonkeyPatch, marker: str, code: str
) -> None:
    _patch_preconditions(monkeypatch)
    monkeypatch.setattr(
        order_create,
        "run_sql_script",
        lambda _script: SqlResult(ok=False, rows=[], error=f"ERROR: {marker}\nCONTEXT: x"),
    )
    with pytest.raises(AppError) as excinfo:
        _create()
    assert excinfo.value.code == code
    assert excinfo.value.http_status == 409
    assert excinfo.value.details["listing_variant_id"] == VARIANT
