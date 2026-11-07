"""Price consent stays bound to the proposal the buyer saw."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast

import pytest
from app.core.auth import CurrentUser
from app.errors import AppError
from app.routers.cart import (
    CartMergeResolutionInput,
    _price_conflicts_with_proposals,
    _validate_merge_resolution,
)
from app.services.cart.merge import MergeConflict
from app.services.cart.merge_atomic import AtomicMergeOutcome
from app.settings import Settings
from fastapi import Request, Response

USER = "11111111-1111-4111-8111-111111111111"
OTHER_USER = "22222222-2222-4222-8222-222222222222"
USER_CART = "33333333-3333-4333-8333-333333333333"
GUEST_CART = "44444444-4444-4444-8444-444444444444"
LISTING = "55555555-5555-4555-8555-555555555555"
LINE = "66666666-6666-4666-8666-666666666666"


def _proposal(
    *, price: int = 12_000, user: str = USER, authority_price: int | None = None
) -> list[MergeConflict]:
    settings = SimpleNamespace(supabase_service_role_key="local-only-signing-key-32-bytes-long")
    authority: dict[str, Any] = {
        "business_status": None,
        "listings": [{
            "id": LISTING,
            "display_name": "Copper pipe",
            "price_ngwee": authority_price or price,
            "wholesale": False,
            "moq": 1,
            "price_tiers": None,
        }],
        "rfq_threads": [],
        "location_stock": [],
    }
    return _price_conflicts_with_proposals(
        [MergeConflict(
            listing_id=LISTING,
            code="cart.price_changed",
            message_key="cart.price_changed",
            details={"previous_unit_price_ngwee": 10_000, "current_unit_price_ngwee": price},
        )],
        settings=settings,  # type: ignore[arg-type]
        user_id=user,
        user_cart_id=USER_CART,
        guest_cart_id=GUEST_CART,
        user_items=[],
        guest_items=[{
            "id": LINE,
            "listing_id": LISTING,
            "qty": 2,
            "unit_price_ngwee": 10_000,
            "wholesale": False,
            "pickup_location_id": None,
            "rfq_thread_id": None,
        }],
        authority=authority,
    )


def _accept(token: str) -> CartMergeResolutionInput:
    return CartMergeResolutionInput(
        accept_price_changes=[LISTING], accepted_price_proposals={LISTING: token}
    )


def test_stable_displayed_terms_are_accepted_and_same_proposal_can_retry() -> None:
    conflicts = _proposal()
    details = conflicts[0].details
    assert details["item_name"] == "Copper pipe"
    assert details["currency"] == "ZMW"
    assert details["quantity"] == 2
    assert details["current_line_total_ngwee"] == 24_000
    token = details["proposal_token"]
    settings = SimpleNamespace(supabase_service_role_key="local-only-signing-key-32-bytes-long")
    for _ in range(2):
        resolution = _validate_merge_resolution(_accept(token), conflicts, settings)  # type: ignore[arg-type]
        assert resolution.accept_price_changes == {LISTING}


@pytest.mark.parametrize(
    ("changed", "user"),
    [(13_000, USER), (12_000, OTHER_USER)],
)
def test_changed_price_or_cross_user_proposal_requires_fresh_review(
    changed: int, user: str
) -> None:
    old_token = _proposal()[0].details["proposal_token"]
    current = _proposal(price=changed, user=user)
    settings = SimpleNamespace(supabase_service_role_key="local-only-signing-key-32-bytes-long")
    with pytest.raises(AppError) as error:
        _validate_merge_resolution(_accept(old_token), current, settings)  # type: ignore[arg-type]
    assert error.value.code == "cart.merge_conflict"
    assert error.value.details["conflicts"][0]["details"]["current_unit_price_ngwee"] == changed


def test_forged_or_listing_only_consent_never_supplies_pricing_authority() -> None:
    current = _proposal()
    settings = SimpleNamespace(supabase_service_role_key="local-only-signing-key-32-bytes-long")
    for token in ("forged-token", ""):
        with pytest.raises(AppError) as error:
            _validate_merge_resolution(_accept(token), current, settings)  # type: ignore[arg-type]
        assert error.value.code == "cart.merge_conflict"
        assert error.value.details["conflicts"][0]["details"]["current_unit_price_ngwee"] == 12_000


def test_authority_revision_changes_invalidate_old_consent() -> None:
    old_token = _proposal()[0].details["proposal_token"]
    current = _proposal(authority_price=14_000)
    settings = SimpleNamespace(supabase_service_role_key="local-only-signing-key-32-bytes-long")
    with pytest.raises(AppError):
        _validate_merge_resolution(_accept(old_token), current, settings)  # type: ignore[arg-type]


def test_route_retries_stale_authority_without_broadening_price_consent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.routers import cart
    from app.services.cart import merge_atomic

    class _Rpc:
        def execute(self) -> SimpleNamespace:
            return SimpleNamespace(data=USER_CART)

    class _Service:
        def rpc(self, _name: str, _params: dict[str, Any]) -> _Rpc:
            return _Rpc()

    guest_line = {
        "id": LINE, "listing_id": LISTING, "qty": 2,
        "unit_price_ngwee": 10_000, "wholesale": False,
        "pickup_location_id": None, "rfq_thread_id": None,
    }
    current_price = [12_000]
    applied: list[int] = []

    def authority(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "business_status": None,
            "listings": [{
                "id": LISTING, "display_name": "Copper pipe", "status": "active",
                "price_ngwee": current_price[0], "wholesale": False,
                "moq": 1, "price_tiers": None,
            }],
            "rfq_threads": [], "location_stock": [],
        }

    def apply(*_args: Any, **_kwargs: Any) -> AtomicMergeOutcome:
        applied.append(current_price[0])
        current_price[0] = 13_000
        return AtomicMergeOutcome.STALE_AUTHORITY

    monkeypatch.setattr(cart, "_resolve_guest_token", lambda *_args: "guest-token")
    monkeypatch.setattr(cart, "get_user_client", lambda *_args: object())
    monkeypatch.setattr(cart, "service_db_client", lambda: _Service())
    monkeypatch.setattr(cart, "_business_eligible_for_user", lambda *_args: False)
    monkeypatch.setattr(
        cart, "fetch_active_cart_by_guest", lambda *_args: {"id": GUEST_CART}
    )
    monkeypatch.setattr(
        cart,
        "_fetch_cart_items",
        lambda _client, cart_id: [guest_line] if cart_id == GUEST_CART else [],
    )
    monkeypatch.setattr(merge_atomic, "fetch_cart_merge_authority", authority)
    monkeypatch.setattr(merge_atomic, "apply_login_cart_merge_atomic", apply)
    settings = SimpleNamespace(supabase_service_role_key="local-only-signing-key-32-bytes-long")

    def run(body: CartMergeResolutionInput | None = None) -> None:
        asyncio.run(cart.merge_cart_on_login(
            Response(), cast(CurrentUser, SimpleNamespace(id=USER, token="account-token")),
            cast(Settings, settings), cast(Request, SimpleNamespace()), body,
        ))

    with pytest.raises(AppError) as initial:
        run()
    assert initial.value.code == "cart.merge_conflict"
    token = initial.value.details["conflicts"][0]["details"]["proposal_token"]
    with pytest.raises(AppError) as changed:
        run(_accept(token))
    assert changed.value.code == "cart.merge_conflict"
    assert changed.value.details["conflicts"][0]["details"]["current_unit_price_ngwee"] == 13_000
    assert applied == [12_000]
