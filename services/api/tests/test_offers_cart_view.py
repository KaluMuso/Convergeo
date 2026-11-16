"""W8: the cart view shows the offer discount lines and the free gift."""

from __future__ import annotations

import pytest
from app.routers import cart as cart_router
from tests.test_vendor_offers_api import LA1, LA2, VENDOR_A, FakeClient

OFFER_ID = "0ffe0000-0000-4000-8000-0000000000aa"
GIFT_OFFER_ID = "0ffe0000-0000-4000-8000-0000000000bb"
GIFT = "a9000000-0000-4000-8000-000000000009"
LISTINGS = {
    LA1: {"id": LA1, "vendor_id": VENDOR_A},
    LA2: {"id": LA2, "vendor_id": VENDOR_A},
}
ITEMS = [
    {"id": "c1", "listing_id": LA1, "qty": 1, "unit_price_ngwee": 10_000},
    {"id": "c2", "listing_id": LA2, "qty": 3, "unit_price_ngwee": 1_000},
]


def _fake(enabled: bool) -> FakeClient:
    fake = FakeClient()
    fake.table("feature_flags").rows.append({"flag": "bundles", "enabled": enabled})
    fake.table("offers").rows.extend(
        [
            {
                "id": OFFER_ID,
                "vendor_id": VENDOR_A,
                "offer_type": "buy_n_pay_m",
                "status": "active",
                "title": "3 for 2",
                "starts_at": "2026-01-01T00:00:00+00:00",
                "ends_at": None,
                "buy_n": 3,
                "pay_m": 2,
                "max_applications_per_order": 1,
                "paused_by_admin": False,
                "gift_stock_reserved": 0,
            },
            {
                "id": GIFT_OFFER_ID,
                "vendor_id": VENDOR_A,
                "offer_type": "free_gift",
                "status": "active",
                "title": "Free tote",
                "starts_at": "2026-01-01T00:00:00+00:00",
                "ends_at": None,
                "gift_stock_total": 5,
                "gift_stock_reserved": 1,
                "max_applications_per_order": 1,
                "paused_by_admin": False,
            },
        ]
    )
    fake.table("offer_items").rows.extend(
        [
            {
                "offer_id": OFFER_ID,
                "role": "eligible",
                "item_kind": "product",
                "listing_id": LA2,
                "qty": 1,
                "sort_order": 0,
            },
            {
                "offer_id": GIFT_OFFER_ID,
                "role": "trigger",
                "item_kind": "product",
                "listing_id": LA1,
                "qty": 1,
                "sort_order": 0,
            },
            {
                "offer_id": GIFT_OFFER_ID,
                "role": "reward",
                "item_kind": "product",
                "listing_id": GIFT,
                "qty": 1,
                "sort_order": 1,
            },
        ]
    )
    fake.table("vendor_listings").rows.append(
        {
            "id": GIFT,
            "vendor_id": VENDOR_A,
            "price_ngwee": 2_500,
            "status": "active",
            "title_override": "Tote",
        }
    )
    return fake


def test_cart_view_applies_offers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cart_router, "service_db_client", lambda: _fake(True))
    res = cart_router._build_cart_response(cart_id="cart", items=ITEMS, listings_by_id=LISTINGS)
    by_id = {line.id: line for line in res.items}
    assert by_id["c2"].list_line_total_ngwee == 3_000
    assert by_id["c2"].line_total_ngwee == 2_000
    assert by_id["c2"].offer_id == OFFER_ID
    assert by_id["c1"].line_total_ngwee == 10_000
    assert res.subtotal_ngwee == 12_000
    assert res.savings_ngwee == 1_000
    group = res.vendor_groups[0]
    assert group.subtotal_ngwee == 12_000
    assert [(g.listing_id, g.qty, g.reference_unit_price_ngwee) for g in group.gifts] == [
        (GIFT, 1, 2_500)
    ]
    assert {o.offer_id for o in res.offers} == {OFFER_ID, GIFT_OFFER_ID}


def test_cart_view_unchanged_when_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cart_router, "service_db_client", lambda: _fake(False))
    res = cart_router._build_cart_response(cart_id="cart", items=ITEMS, listings_by_id=LISTINGS)
    assert res.subtotal_ngwee == 13_000
    assert res.savings_ngwee == 0
    assert res.offers == []
    assert all(line.list_line_total_ngwee is None for line in res.items)
