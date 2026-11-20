"""F1 buy-again endpoint: authz (own orders only), unavailable items, price changes."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.deps import get_supabase_client
from app.errors import AppError
from app.main import create_app
from fastapi.testclient import TestClient

USER = "11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"
ORDER = "dddddddd-dddd-dddd-dddd-dddddddddddd"
L1 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1"
L2 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa2"
L3 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa3"


class _Query:
    def __init__(self, data: Any) -> None:
        self._data = data

    def select(self, *_a: Any, **_k: Any) -> _Query:
        return self

    def eq(self, *_a: Any, **_k: Any) -> _Query:
        return self

    def maybe_single(self) -> _Query:
        return self

    def execute(self) -> Any:
        return MagicMock(data=self._data)


class _FakeService:
    def __init__(self, order: dict[str, Any] | None, items: list[dict[str, Any]]) -> None:
        self._order = order
        self._items = items

    def table(self, name: str) -> _Query:
        return _Query(self._order if name == "orders" else self._items)


def _item(listing: str, qty: int, price: int, variant: str | None = None) -> dict[str, Any]:
    return {
        "id": f"item-{listing[-1]}",
        "qty": qty,
        "unit_price_ngwee": price,
        "title_snapshot": f"Item {listing[-1]}",
        "item_kind": "product",
        "order_item_products": {"listing_id": listing, "listing_variant_id": variant},
    }


@pytest.fixture
def reorder_api(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[TestClient, dict[str, Any]], None, None]:
    from app.routers import cart as cart_router

    state: dict[str, Any] = {
        "order": {"id": ORDER, "customer_id": USER, "status": "delivered"},
        "items": [_item(L1, 2, 5000), _item(L2, 1, 12000), _item(L3, 1, 900)],
        "cart_rows": [
            {"listing_id": L1, "unit_price_ngwee": 5000},
            {"listing_id": L2, "unit_price_ngwee": 13500},
        ],
        "reject": {L3: AppError(code="cart.listing_inactive", message="x", http_status=409)},
        "added_keys": [],
        "bumped": [],
        "allowed": True,
    }

    def fake_add(*, body: Any, key: str, **_k: Any) -> bool:
        err = state["reject"].get(body.listing_id)
        if err is not None:
            raise err
        state["added_keys"].append((body.listing_id, body.qty, key))
        return True

    def fake_bump(**kwargs: Any) -> tuple[bool, int]:
        state["bumped"].append(kwargs["scope"])
        return state["allowed"], 7

    monkeypatch.setattr(cart_router, "_keyed_add_result", fake_add)
    monkeypatch.setattr(cart_router, "bump_rate_counter", fake_bump)
    monkeypatch.setattr(
        cart_router, "service_db_client", lambda: _FakeService(state["order"], state["items"])
    )
    monkeypatch.setattr(cart_router, "_db_client_for_owner", lambda *_a, **_k: MagicMock())
    monkeypatch.setattr(cart_router, "_business_eligible_for_user", lambda _uid: False)
    monkeypatch.setattr(cart_router, "_fetch_cart_items", lambda *_a, **_k: state["cart_rows"])

    owner = cart_router.CartOwner(cart_id="cart-1", user_id=USER, guest_token=None, is_guest=False)
    app = create_app()
    app.dependency_overrides[cart_router._resolve_cart_owner] = lambda: owner
    app.dependency_overrides[get_supabase_client] = lambda: MagicMock()
    state["app"] = app
    state["owner_cls"] = cart_router.CartOwner
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, state
    app.dependency_overrides.clear()


def test_reorder_adds_available_lines_reports_skips_and_price_change(
    reorder_api: tuple[TestClient, dict[str, Any]],
) -> None:
    client, state = reorder_api
    response = client.post(f"/cart/reorder/{ORDER}", headers={"Idempotency-Key": "click-1"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert [line["listing_id"] for line in body["added"]] == [L1, L2]
    assert body["added"][1]["unit_price_ngwee"] == 13500  # CURRENT price, integer ngwee
    assert body["skipped"] == [{"listing_id": L3, "title": "Item 3", "reason": "unavailable"}]
    assert body["price_changes"] == [
        {
            "listing_id": L2,
            "title": "Item 2",
            "previous_unit_price_ngwee": 12000,
            "current_unit_price_ngwee": 13500,
        }
    ]
    assert state["added_keys"][0] == (L1, 2, "reorder:click-1:0")
    assert state["bumped"] == ["write_sensitive"]


def test_out_of_stock_is_reported_with_reason(
    reorder_api: tuple[TestClient, dict[str, Any]],
) -> None:
    client, state = reorder_api
    state["reject"][L3] = AppError(code="cart.variant_out_of_stock", message="x", http_status=409)
    body = client.post(f"/cart/reorder/{ORDER}").json()
    assert body["skipped"][0]["reason"] == "out_of_stock"


def test_other_customers_order_is_404_and_adds_nothing(
    reorder_api: tuple[TestClient, dict[str, Any]],
) -> None:
    client, state = reorder_api
    state["order"] = {"id": ORDER, "customer_id": OTHER, "status": "delivered"}
    response = client.post(f"/cart/reorder/{ORDER}")
    assert response.status_code == 404
    assert state["added_keys"] == []


def test_unknown_or_malformed_order_is_404(
    reorder_api: tuple[TestClient, dict[str, Any]],
) -> None:
    client, state = reorder_api
    state["order"] = None
    assert client.post(f"/cart/reorder/{ORDER}").status_code == 404
    assert client.post("/cart/reorder/not-a-uuid").status_code == 404


def test_in_flight_order_cannot_be_reordered(
    reorder_api: tuple[TestClient, dict[str, Any]],
) -> None:
    client, state = reorder_api
    state["order"]["status"] = "shipped"
    response = client.post(f"/cart/reorder/{ORDER}")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "cart.reorder_not_available"
    assert state["added_keys"] == []


def test_guest_is_rejected(reorder_api: tuple[TestClient, dict[str, Any]]) -> None:
    client, state = reorder_api
    guest = state["owner_cls"](cart_id="c", user_id=None, guest_token="g", is_guest=True)
    from app.routers import cart as cart_router

    state["app"].dependency_overrides[cart_router._resolve_cart_owner] = lambda: guest
    assert client.post(f"/cart/reorder/{ORDER}").status_code == 401
    assert state["added_keys"] == []


def test_rate_limited_before_any_write(reorder_api: tuple[TestClient, dict[str, Any]]) -> None:
    client, state = reorder_api
    state["allowed"] = False
    response = client.post(f"/cart/reorder/{ORDER}")
    assert response.status_code == 429
    assert state["added_keys"] == []
