"""A typed Lusaka landmark the matcher cannot place must not read as "outside Lusaka".

The fulfilment form sends a free-text landmark and no GPS. The matcher knows a
few area names, so "Plot 12, behind the blue gate" was refused with
``checkout.outside_delivery_zone``. The zone such an address gets is a pricing
choice, so it comes from ``platform_config.delivery_fallback_zone``; with the key
unset the strict refusal is unchanged.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from contextlib import ExitStack
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.main import create_app
from app.routers.checkout import (
    FALLBACK_DELIVERY_ZONE_KEY,
    _load_fallback_delivery_zone,
    landmark_names_other_town,
)
from fastapi.testclient import TestClient

CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
LISTING_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
ZONES: dict[str, dict[str, Any]] = {
    "lusaka_a": {"zone_key": "lusaka_a", "label": "Band A", "fee_ngwee": 3000},
    "lusaka_b": {"zone_key": "lusaka_b", "label": "Band B", "fee_ngwee": 4500},
}


def _service(config: dict[str, Any]) -> MagicMock:
    service = MagicMock()
    updates: list[dict[str, Any]] = []
    service.group_updates = updates

    def table(name: str) -> MagicMock:
        builder = MagicMock()
        if name == "platform_config":

            def by_key(_column: str, key: str) -> MagicMock:
                chain = MagicMock()
                row = {"value": config[key]} if key in config else None
                chain.maybe_single.return_value.execute.return_value = MagicMock(data=row)
                return chain

            builder.select.return_value.eq.side_effect = by_key
        elif name == "checkout_groups":

            def update(payload: dict[str, Any]) -> MagicMock:
                updates.append(payload)
                return MagicMock()

            builder.update.side_effect = update
        return builder

    service.client.table.side_effect = table
    return service


@pytest.fixture
def post_fulfilment() -> Generator[Any, None, None]:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=CUSTOMER_ID, roles=frozenset({"customer"}), token="tok"
    )
    item = {"id": str(uuid.uuid4()), "listing_id": LISTING_ID, "qty": 1, "unit_price_ngwee": 10_000}
    listing = {"id": LISTING_ID, "vendor_id": VENDOR_ID, "title_override": "Chitenge"}

    def call(config: dict[str, Any], address: dict[str, Any]) -> tuple[Any, MagicMock]:
        service = _service(config)
        app.dependency_overrides[get_supabase_client] = lambda: service
        pending = ({"id": "s", "status": "pending"}, datetime.now(UTC))
        with ExitStack() as stack:
            for target, value in (
                ("_ensure_session_active", pending),
                ("get_user_client", MagicMock()),
                ("_fetch_active_cart_by_user", {"id": str(uuid.uuid4())}),
                ("_fetch_cart_items", [item]),
                ("fetch_listings_for_items", {LISTING_ID: listing}),
                ("_load_free_delivery_threshold", 20_000),
                ("_load_delivery_zones", ZONES),
                ("_fetch_vendor_locations", {}),
            ):
                stack.enter_context(patch(f"app.routers.checkout.{target}", return_value=value))
            response = TestClient(app, raise_server_exceptions=False).post(
                "/checkout/steps/fulfilment",
                json={
                    "session_id": str(uuid.uuid4()),
                    "address": address,
                    "groups": [{"vendor_id": VENDOR_ID, "fulfilment": "delivery"}],
                },
            )
        return response, service

    yield call


UNMATCHED = {"landmark": "Plot 12, behind the blue gate, near the clinic"}


def test_unmatched_landmark_is_still_refused_when_no_fallback_is_configured(
    post_fulfilment: Any,
) -> None:
    response, service = post_fulfilment({}, UNMATCHED)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "checkout.outside_delivery_zone"
    assert service.group_updates == []


def test_unmatched_landmark_gets_the_configured_zone_and_its_fee(post_fulfilment: Any) -> None:
    response, service = post_fulfilment({FALLBACK_DELIVERY_ZONE_KEY: "lusaka_b"}, UNMATCHED)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["resolved_zone_key"] == "lusaka_b"
    assert body["groups"][0]["delivery_zone"] == "lusaka_b"
    assert body["delivery_fee_ngwee"] == 4500
    assert body["total_ngwee"] == 10_000 + 4500
    assert service.group_updates == [
        {"subtotal_ngwee": 10_000, "delivery_fee_ngwee": 4500, "total_ngwee": 14_500}
    ]


def test_a_matched_landmark_keeps_its_own_zone(post_fulfilment: Any) -> None:
    response, _ = post_fulfilment(
        {FALLBACK_DELIVERY_ZONE_KEY: "lusaka_b"}, {"landmark": "Woodlands Stage 2"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["resolved_zone_key"] == "lusaka_a"


@pytest.mark.parametrize(
    "address",
    [
        {"landmark": "Ndola city centre"},
        # GPS that is genuinely out of range is never overridden by the fallback.
        {"landmark": "Plot 12, behind the blue gate", "lat": -12.97, "lng": 28.63},
    ],
)
def test_fallback_never_delivers_outside_lusaka(
    post_fulfilment: Any, address: dict[str, Any]
) -> None:
    response, _ = post_fulfilment({FALLBACK_DELIVERY_ZONE_KEY: "lusaka_b"}, address)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "checkout.outside_delivery_zone"


@pytest.mark.parametrize("value", ["lusaka_z", "", 3, None, {"zone": "lusaka_b"}])
def test_fallback_must_name_an_active_zone(value: Any) -> None:
    service = _service({FALLBACK_DELIVERY_ZONE_KEY: value})

    assert _load_fallback_delivery_zone(service, ZONES) is None


def test_other_town_detection() -> None:
    assert landmark_names_other_town("Kitwe, Parklands")
    assert not landmark_names_other_town("Plot 12, behind the blue gate")
    assert not landmark_names_other_town(None)
