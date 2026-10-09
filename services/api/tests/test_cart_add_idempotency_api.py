from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from app.errors import AppError
from app.routers import cart


def _client(rows: list[list[dict]]) -> MagicMock:
    client = MagicMock()
    query = _query(client)
    query.execute.side_effect = [SimpleNamespace(data=value) for value in rows]
    return client


def _query(client: MagicMock) -> MagicMock:
    query = client.table.return_value.select.return_value
    return query.eq.return_value.eq.return_value.limit.return_value


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

    def validate(*, listing: dict, qty: int, business_eligible: bool) -> tuple[int, bool]:
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
