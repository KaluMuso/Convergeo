"""Cart/checkout lines must carry a human title, never force the UI onto the listing UUID."""

from __future__ import annotations

import pytest
from app.routers import cart as cart_router
from app.services.cart.grouping import listing_display_title

LISTING = "1633639e-0000-4000-8000-000000000001"
VENDOR = "9e000000-0000-4000-8000-000000000001"


def test_title_prefers_override() -> None:
    assert (
        listing_display_title({"title_override": " Tote ", "products": {"name": "Bag"}}) == "Tote"
    )


def test_title_falls_back_to_product_name() -> None:
    assert listing_display_title({"title_override": None, "products": {"name": "Bag"}}) == "Bag"
    assert listing_display_title({"title_override": "  ", "products": [{"name": "Bag"}]}) == "Bag"


def test_title_none_when_nothing_known() -> None:
    assert listing_display_title({"title_override": None, "products": None}) is None


def test_cart_response_uses_product_name_when_no_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cart_router, "_load_ticket_lines_for_read", lambda *_a, **_k: [])
    monkeypatch.setattr(cart_router, "_price_cart_offers", lambda views, _customer: (views, None))
    res = cart_router._build_cart_response(
        cart_id="cart",
        items=[{"id": "c1", "listing_id": LISTING, "qty": 1, "unit_price_ngwee": 1000}],
        listings_by_id={
            LISTING: {
                "id": LISTING,
                "vendor_id": VENDOR,
                "title_override": None,
                "products": {"name": "Blue Kettle"},
            }
        },
    )
    assert res.items[0].title_override == "Blue Kettle"
    assert res.vendor_groups[0].items[0].title_override == "Blue Kettle"
