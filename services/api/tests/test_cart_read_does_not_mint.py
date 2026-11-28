"""A cookieless visitor's cart read must not mint a guest cart or a cookie."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest
from app.routers import cart
from app.settings import Settings
from fastapi import Request, Response


def _request(
    headers: dict[str, str] | None = None, cookies: dict[str, str] | None = None
) -> Request:
    return cast(Request, SimpleNamespace(headers=headers or {}, cookies=cookies or {}))


def _settings() -> Settings:
    return cast(Settings, SimpleNamespace(env="development", supabase_service_role_key="k" * 40))


@pytest.mark.asyncio
async def test_cookieless_read_resolves_unminted_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("a read must not mint a guest cart")

    monkeypatch.setattr(cart, "create_guest_cart", forbidden)
    response = Response()
    owner = await cart._resolve_cart_owner_for_read(_request(), response, _settings())
    assert owner.cart_id is None
    assert owner.is_guest is True
    assert "set-cookie" not in response.headers


@pytest.mark.asyncio
async def test_cookieless_get_cart_returns_an_empty_cart_without_database_access() -> None:
    owner = cart.CartOwner(cart_id=None, user_id=None, guest_token=None, is_guest=True)
    result = await cart.get_cart(owner, _settings(), _request())
    assert result.cart_id == cart.UNMINTED_GUEST_CART_ID
    assert result.items == []
    assert result.subtotal_ngwee == 0


@pytest.mark.asyncio
async def test_a_mutation_still_mints(monkeypatch: pytest.MonkeyPatch) -> None:
    minted: list[str] = []

    def create(token: str) -> dict[str, object]:
        minted.append(token)
        return {"id": "cart-1", "guest_token": token}

    monkeypatch.setattr(cart, "create_guest_cart", create)
    response = Response()
    owner = await cart._resolve_cart_owner(_request(), response, _settings())
    assert owner.cart_id == "cart-1"
    assert len(minted) == 1
    assert cart.GUEST_CART_COOKIE in response.headers["set-cookie"]
