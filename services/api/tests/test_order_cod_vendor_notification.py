"""A new cash-on-delivery order must produce a vendor notification that can be sent.

The outbox row written at COD order creation carried only ids: no
``recipient_id`` (the dispatcher's only way to address a row) and none of the
variables the ``vendor_new_order`` template requires. Every channel failed, so
the vendor learned about a COD order only by opening the app.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from app.services.notifications.templates.sms import render_sms_body
from app.services.notifications.templates.whatsapp import render_whatsapp_template
from app.services.orders.create import (
    CartLineInput,
    VendorFulfilmentInput,
    create_orders_atomic,
    order_display_reference,
)
from app.services.stock.claim import claim_reservation
from app.supabase_client import SupabaseServiceClient
from tests.rls.conftest import PgConn
from tests.test_order_creation import (
    CUSTOMER_ID,
    VENDOR_A,
    _insert_checkout_group,
    _insert_tracked_listing,
    _load_ids,
    db,  # noqa: F401  (module-scoped fixture reuse)
    db_url_env,  # noqa: F401
    pg_service,  # noqa: F401
)

PRICE = 20_000
VENDOR_PHONE = "+260971234567"


def _vendor_owner(conn: PgConn) -> str:
    result = conn.run(f"SELECT owner_user_id::text FROM public.vendors WHERE id = '{VENDOR_A}';")
    assert result.ok and result.rows and result.rows[0], result.error
    return result.rows[0]


def _product_name(conn: PgConn, product_id: str) -> str:
    result = conn.run(f"SELECT name FROM public.products WHERE id = '{product_id}';")
    assert result.ok and result.rows, result.error
    return result.rows[0]


def _outbox_payload(conn: PgConn, order_id: str) -> dict[str, Any]:
    result = conn.run(
        f"""
        SELECT payload::text FROM public.notification_outbox
        WHERE dedupe_key = 'order.placed:{order_id}:whatsapp';
        """
    )
    assert result.ok and len(result.rows) == 1, result.error
    payload = json.loads(result.rows[0])
    assert isinstance(payload, dict)
    return payload


def _place_cod(
    conn: PgConn,
    pg_service: SupabaseServiceClient,  # noqa: F811
    lines: list[tuple[str | None, int]],
) -> str:
    """Place one COD order for VENDOR_A with ``(title_snapshot, qty)`` lines."""
    product_id = _load_ids()["products"]["phone"]
    session_id = str(uuid.uuid4())
    subtotal = sum(qty * PRICE for _, qty in lines)
    cart_lines: list[CartLineInput] = []
    _insert_checkout_group(
        conn,
        session_id=session_id,
        idempotency_key=f"chk-{session_id}",
        subtotal=subtotal,
        delivery_fee=0,
        total=subtotal,
    )
    for title, qty in lines:
        listing_id = str(uuid.uuid4())
        _insert_tracked_listing(
            conn,
            listing_id=listing_id,
            vendor_id=VENDOR_A,
            product_id=product_id,
            stock_qty=10,
            price_ngwee=PRICE,
        )
        claim_reservation(
            listing_id=listing_id, checkout_group_id=session_id, qty=qty, ttl_minutes=15
        )
        cart_lines.append(
            CartLineInput(
                cart_item_id=str(uuid.uuid4()),
                listing_id=listing_id,
                vendor_id=VENDOR_A,
                qty=qty,
                unit_price_ngwee=PRICE,
                title_snapshot=title,
            )
        )
    result = create_orders_atomic(
        client=pg_service.client,
        customer_id=CUSTOMER_ID,
        session_id=session_id,
        idempotency_key=f"notify-{uuid.uuid4()}",
        payment_method="cod",
        cart_lines=cart_lines,
        vendor_groups=[
            VendorFulfilmentInput(
                vendor_id=VENDOR_A,
                fulfilment="pickup",
                delivery_zone=None,
                delivery_fee_ngwee=0,
                subtotal_ngwee=subtotal,
            )
        ],
    )
    assert len(result.orders) == 1
    return result.orders[0].order_id


def test_cod_notification_is_addressed_to_the_vendor_owner_and_renders(
    db: PgConn,  # noqa: F811
    db_url_env: None,  # noqa: F811
    pg_service: SupabaseServiceClient,  # noqa: F811
) -> None:
    order_id = _place_cod(db, pg_service, [("Chitenge wrap", 2)])

    payload = _outbox_payload(db, order_id)

    assert payload["recipient_id"] == _vendor_owner(db)
    assert payload["order_reference"] == order_display_reference(order_id)
    assert payload["product_title"] == "Chitenge wrap"
    assert payload["quantity"] == 2
    # What the dispatcher does next: inject the owner's phone, then render.
    deliverable = {**payload, "to": VENDOR_PHONE, "phone": VENDOR_PHONE}
    rendered = render_whatsapp_template("vendor_new_order", deliverable)
    assert rendered.to_e164 == VENDOR_PHONE
    assert rendered.body_parameters == (order_display_reference(order_id), "Chitenge wrap", "2")
    sms = render_sms_body("vendor_new_order", deliverable)
    assert sms is not None and "2 x Chitenge wrap" in sms


def test_cod_notification_falls_back_to_the_catalogue_product_name(
    db: PgConn,  # noqa: F811
    db_url_env: None,  # noqa: F811
    pg_service: SupabaseServiceClient,  # noqa: F811
) -> None:
    order_id = _place_cod(db, pg_service, [(None, 1)])

    payload = _outbox_payload(db, order_id)

    assert payload["product_title"] == _product_name(db, _load_ids()["products"]["phone"])
    render_whatsapp_template("vendor_new_order", {**payload, "to": VENDOR_PHONE})


def test_cod_notification_summarises_a_multi_line_order(
    db: PgConn,  # noqa: F811
    db_url_env: None,  # noqa: F811
    pg_service: SupabaseServiceClient,  # noqa: F811
) -> None:
    order_id = _place_cod(db, pg_service, [("Chitenge wrap", 2), ("Headscarf", 1)])

    payload = _outbox_payload(db, order_id)

    assert payload["product_title"] == "Chitenge wrap +1"
    assert payload["quantity"] == 3


def test_order_reference_matches_what_the_apps_display() -> None:
    assert order_display_reference("1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d") == "1A2B3C4D"


@pytest.mark.parametrize("locale", ["fr", "zh", "FR"])
def test_whatsapp_falls_back_to_english_for_storefront_only_locales(locale: str) -> None:
    rendered = render_whatsapp_template(
        "vendor_new_order",
        {
            "to": VENDOR_PHONE,
            "locale": locale,
            "order_reference": "1A2B3C4D",
            "product_title": "Chitenge wrap",
            "quantity": 1,
        },
    )

    assert rendered.language_code == "en"


@pytest.mark.parametrize(("locale", "expected"), [("bem", "bem_ZM"), ("nya", "nya_ZM")])
def test_whatsapp_keeps_supported_locales(locale: str, expected: str) -> None:
    rendered = render_whatsapp_template(
        "vendor_new_order",
        {
            "to": VENDOR_PHONE,
            "locale": locale,
            "order_reference": "1A2B3C4D",
            "product_title": "Chitenge wrap",
            "quantity": 1,
        },
    )

    assert rendered.language_code == expected
