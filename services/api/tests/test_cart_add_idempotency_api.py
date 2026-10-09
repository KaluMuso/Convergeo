from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

import pytest
from app.errors import AppError
from app.routers import cart
from fastapi import Request


def _client(rows: list[list[dict[str, object]]]) -> MagicMock:
    client = MagicMock()
    query = _query(client)
    query.execute.side_effect = [SimpleNamespace(data=value) for value in rows]
    return client


def _query(client: MagicMock) -> MagicMock:
    query = client.table.return_value.select.return_value
    return cast(MagicMock, query.eq.return_value.eq.return_value.limit.return_value)


def test_keyed_add_revalidates_after_stale_quantity(monkeypatch: pytest.MonkeyPatch) -> None:
    writer = MagicMock()
    _query(writer).execute.return_value = SimpleNamespace(data=[])
    writer.rpc.return_value.execute.side_effect = [
        SimpleNamespace(data="stale"),
        SimpleNamespace(data="applied"),
    ]
    monkeypatch.setattr(cart, "service_db_client", lambda: writer)
    monkeypatch.setattr(cart, "fetch_listing", lambda *args, **kwargs: {"id": "listing"})
    monkeypatch.setattr(cart, "_resolve_line_location_id", lambda *args, **kwargs: None)
    validated: list[int] = []

    def validate(
        *, listing: dict[str, object], qty: int, business_eligible: bool
    ) -> tuple[int, bool]:
        validated.append(qty)
        return (1000 if qty == 2 else 900), False

    monkeypatch.setattr(cart, "validate_item_qty_for_listing", validate)
    monkeypatch.setattr(cart, "_enforce_listing_cart_rules", lambda *args, **kwargs: None)
    client = _client([[], [{"qty": 2, "pickup_location_id": None}]])
    applied = cart._keyed_add_result(
        body=cart.CartItemInput(listing_id="listing", qty=2),
        key="key-1",
        owner=cart.CartOwner("cart", "user", None, False),
        client=client,
        business_eligible=False,
    )
    assert applied is True
    assert validated == [2, 4]
    assert writer.rpc.call_args_list[0].args[1]["p_unit_price_ngwee"] == 1000
    assert writer.rpc.call_args_list[1].args[1]["p_unit_price_ngwee"] == 900
    assert writer.rpc.call_args_list[1].args[1]["p_expected_qty"] == 2


def test_completed_replay_skips_listing_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    writer = MagicMock()
    body = cart.CartItemInput(listing_id="listing", qty=2)
    _query(writer).execute.return_value = SimpleNamespace(
        data=[{"request_body": body.model_dump(mode="json")}]
    )
    monkeypatch.setattr(cart, "service_db_client", lambda: writer)
    fetch_listing = MagicMock()
    monkeypatch.setattr(cart, "fetch_listing", fetch_listing)
    assert (
        cart._keyed_add_result(
            body=body,
            key="key-1",
            owner=cart.CartOwner("cart", "user", None, False),
            client=MagicMock(),
            business_eligible=False,
        )
        is False
    )
    fetch_listing.assert_not_called()
    writer.rpc.assert_not_called()


def test_reusing_key_with_different_body_is_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    writer = MagicMock()
    _query(writer).execute.return_value = SimpleNamespace(
        data=[{"request_body": {"listing_id": "listing", "qty": 1}}]
    )
    monkeypatch.setattr(cart, "service_db_client", lambda: writer)
    with pytest.raises(AppError) as raised:
        cart._keyed_add_result(
            body=cart.CartItemInput(listing_id="listing", qty=2),
            key="key-1",
            owner=cart.CartOwner("cart", "user", None, False),
            client=MagicMock(),
            business_eligible=False,
        )
    assert raised.value.http_status == 409


@pytest.mark.asyncio
async def test_same_key_race_at_stock_cap_replays_without_new_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = cart.CartItemInput(listing_id="listing", qty=2)
    writer = MagicMock()
    _query(writer).execute.side_effect = [
        SimpleNamespace(data=[]),  # Request B arrives while A is uncommitted.
        SimpleNamespace(data=[]),
        SimpleNamespace(data=[{"request_body": body.model_dump(mode="json")}]),
    ]
    client = _client([[{"qty": 2, "pickup_location_id": None}]])
    monkeypatch.setattr(cart, "service_db_client", lambda: writer)
    monkeypatch.setattr(cart, "_db_client_for_owner", lambda *args, **kwargs: client)
    monkeypatch.setattr(cart, "_business_eligible_for_user", lambda *args: False)
    monkeypatch.setattr(cart, "fetch_listing", lambda *args, **kwargs: {"id": "listing"})
    monkeypatch.setattr(cart, "_resolve_line_location_id", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        cart,
        "validate_item_qty_for_listing",
        lambda **kwargs: (_ for _ in ()).throw(
            AppError("cart.out_of_stock", "Stock cap reached", 409)
        ),
    )
    monkeypatch.setattr(cart, "_fetch_cart_items", lambda *args: [])
    monkeypatch.setattr(cart, "fetch_listings_for_items", lambda *args: {})
    result = object()
    monkeypatch.setattr(cart, "_cart_response", lambda **kwargs: result)
    emit = MagicMock()
    monkeypatch.setattr(cart, "emit_cart_add", emit)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/cart/items",
            "headers": [(b"idempotency-key", b"race-key")],
        }
    )

    response = await cart.add_cart_item(
        body,
        cart.CartOwner("cart", "user", None, False),
        MagicMock(),
        MagicMock(),
        request,
    )
    assert response is result
    writer.rpc.assert_not_called()
    emit.assert_not_called()


@pytest.mark.parametrize("changed", ["listing", "location"])
def test_same_key_race_replays_after_listing_or_location_change(
    monkeypatch: pytest.MonkeyPatch,
    changed: str,
) -> None:
    body = cart.CartItemInput(listing_id="listing", qty=2)
    writer = MagicMock()
    _query(writer).execute.side_effect = [
        SimpleNamespace(data=[]),
        SimpleNamespace(data=[]),
        SimpleNamespace(data=[{"request_body": body.model_dump(mode="json")}]),
    ]
    monkeypatch.setattr(cart, "service_db_client", lambda: writer)
    monkeypatch.setattr(cart, "fetch_listing", lambda *args, **kwargs: {"id": "listing"})
    monkeypatch.setattr(cart, "_resolve_line_location_id", lambda *args, **kwargs: None)
    if changed == "listing":
        monkeypatch.setattr(
            cart,
            "fetch_listing",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                AppError("cart.listing_not_found", "Listing removed", 404)
            ),
        )
    else:
        monkeypatch.setattr(
            cart,
            "_resolve_line_location_id",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                AppError("cart.pickup_location_invalid", "Location changed", 422)
            ),
        )
    assert (
        cart._keyed_add_result(
            body=body,
            key="race-key",
            owner=cart.CartOwner("cart", "user", None, False),
            client=_client([[{"qty": 2, "pickup_location_id": None}]]),
            business_eligible=False,
        )
        is False
    )
    writer.rpc.assert_not_called()


def test_stale_retry_rechecks_replay_before_stock_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = cart.CartItemInput(listing_id="listing", qty=2)
    writer = MagicMock()
    _query(writer).execute.side_effect = [
        SimpleNamespace(data=[]),
        SimpleNamespace(data=[]),
        SimpleNamespace(data=[{"request_body": body.model_dump(mode="json")}]),
    ]
    writer.rpc.return_value.execute.return_value = SimpleNamespace(data="stale")
    monkeypatch.setattr(cart, "service_db_client", lambda: writer)
    monkeypatch.setattr(cart, "fetch_listing", lambda *args, **kwargs: {"id": "listing"})
    monkeypatch.setattr(cart, "_resolve_line_location_id", lambda *args, **kwargs: None)
    validate = MagicMock(return_value=(1000, False))
    monkeypatch.setattr(cart, "validate_item_qty_for_listing", validate)
    monkeypatch.setattr(cart, "_enforce_listing_cart_rules", lambda *args, **kwargs: None)
    assert (
        cart._keyed_add_result(
            body=body,
            key="race-key",
            owner=cart.CartOwner("cart", "user", None, False),
            client=_client([[]]),
            business_eligible=False,
        )
        is False
    )
    assert validate.call_count == 1
    assert writer.rpc.call_count == 1


def test_stale_retry_stock_rejection_creates_no_second_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer = MagicMock()
    _query(writer).execute.return_value = SimpleNamespace(data=[])
    writer.rpc.return_value.execute.return_value = SimpleNamespace(data="stale")
    monkeypatch.setattr(cart, "service_db_client", lambda: writer)
    monkeypatch.setattr(cart, "fetch_listing", lambda *args, **kwargs: {"id": "listing"})
    monkeypatch.setattr(cart, "_resolve_line_location_id", lambda *args, **kwargs: None)
    monkeypatch.setattr(cart, "_enforce_listing_cart_rules", lambda *args, **kwargs: None)
    calls = 0

    def validate(**kwargs: object) -> tuple[int, bool]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise AppError("cart.out_of_stock", "Stock cap reached", 409)
        return 1000, False

    monkeypatch.setattr(cart, "validate_item_qty_for_listing", validate)
    with pytest.raises(AppError, match="Stock cap reached"):
        cart._keyed_add_result(
            body=cart.CartItemInput(listing_id="listing", qty=2),
            key="stale-key",
            owner=cart.CartOwner("cart", "user", None, False),
            client=_client([[], [{"qty": 2, "pickup_location_id": None}]]),
            business_eligible=False,
        )
    assert writer.rpc.call_count == 1


@pytest.mark.asyncio
async def test_malformed_header_is_rejected_before_any_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer = MagicMock()
    monkeypatch.setattr(cart, "service_db_client", lambda: writer)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/cart/items",
            "headers": [(b"idempotency-key", b"unsafe key")],
        }
    )
    with pytest.raises(AppError) as raised:
        await cart.add_cart_item(
            cart.CartItemInput(listing_id="listing", qty=1),
            cart.CartOwner("cart", "user", None, False),
            MagicMock(),
            MagicMock(),
            request,
        )
    assert raised.value.http_status == 422
    writer.rpc.assert_not_called()
