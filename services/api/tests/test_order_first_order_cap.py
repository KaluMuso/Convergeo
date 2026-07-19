"""API tests: D9 T1 first-order ≤K500 enforced on order create for all payment methods."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.main import create_app
from app.services.kyc.caps import VendorCapLimits, VendorQuota, clear_vendor_cap_cache
from app.services.orders.create import (
    CreatedOrder,
    CreatedOrderItem,
    CreateOrdersResult,
)
from fastapi.testclient import TestClient

CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
LISTING_ID = "b1000000-0000-0000-0000-000000000001"
CART_ID = "c0c0c0c0-c0c0-c0c0-c0c0-c0c0c0c0c0c0"
VALID_TOKEN = "valid-test-token"
COD_CAP_NGWEE = 50_000
PAYER = "+260971234567"


def _current_user() -> CurrentUser:
    return CurrentUser(id=CUSTOMER_ID, roles=frozenset({"customer"}), token=VALID_TOKEN)


def _t1_limits(*, order_count: int = 0) -> VendorCapLimits:
    return VendorCapLimits(
        vendor_id=VENDOR_ID,
        kyc_tier=1,
        quota=VendorQuota(
            tier=1,
            max_listings=30,
            first_orders_cap_ngwee=COD_CAP_NGWEE,
            first_orders_count=5,
            payout_velocity={},
        ),
        cod_cap_ngwee=COD_CAP_NGWEE,
        listing_count=0,
        order_count=order_count,
    )


def _t2_limits() -> VendorCapLimits:
    return VendorCapLimits(
        vendor_id=VENDOR_ID,
        kyc_tier=2,
        quota=VendorQuota(
            tier=2,
            max_listings=9999,
            first_orders_cap_ngwee=None,
            first_orders_count=None,
            payout_velocity={},
        ),
        cod_cap_ngwee=COD_CAP_NGWEE,
        listing_count=0,
        order_count=0,
    )


def _mock_service(*, session_id: str, total_ngwee: int) -> MagicMock:
    service = MagicMock()

    def table_side_effect(name: str) -> MagicMock:
        table = MagicMock()
        if name == "checkout_groups":
            select_chain = table.select.return_value.eq.return_value.eq.return_value
            chain = select_chain.maybe_single.return_value
            chain.execute.return_value = MagicMock(
                data={
                    "id": session_id,
                    "customer_id": CUSTOMER_ID,
                    "subtotal_ngwee": total_ngwee,
                    "delivery_fee_ngwee": 0,
                    "total_ngwee": total_ngwee,
                    "status": "pending",
                    "created_at": "2099-01-01T00:00:00+00:00",
                }
            )
        elif name == "stock_reservations":
            chain = table.select.return_value.eq.return_value.order.return_value.limit.return_value
            chain.execute.return_value = MagicMock(
                data=[{"expires_at": "2099-01-01T00:00:00+00:00"}]
            )
        elif name == "platform_config":
            chain = table.select.return_value.eq.return_value.maybe_single.return_value
            chain.execute.return_value = MagicMock(data={"value": COD_CAP_NGWEE})
        elif name == "vendor_listings":
            table.select.return_value.in_.return_value.execute.return_value = MagicMock(
                data=[
                    {
                        "id": LISTING_ID,
                        "vendor_id": VENDOR_ID,
                        "title_override": "Test item",
                    }
                ]
            )
        return table

    service.client.table.side_effect = table_side_effect
    return service


def _mock_user_client(*, unit_price_ngwee: int) -> MagicMock:
    user_client = MagicMock()

    def table_side_effect(name: str) -> MagicMock:
        table = MagicMock()
        if name == "carts":
            chain = (
                table.select.return_value.eq.return_value.eq.return_value.limit.return_value
            )
            chain.execute.return_value = MagicMock(
                data=[{"id": CART_ID, "user_id": CUSTOMER_ID, "status": "active"}]
            )
        elif name == "cart_items":
            table.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[
                    {
                        "id": str(uuid.uuid4()),
                        "cart_id": CART_ID,
                        "listing_id": LISTING_ID,
                        "qty": 1,
                        "unit_price_ngwee": unit_price_ngwee,
                        "wholesale": False,
                    }
                ]
            )
        return table

    user_client.table.side_effect = table_side_effect
    return user_client


def _fake_create_result(*, total_ngwee: int) -> CreateOrdersResult:
    order_id = str(uuid.uuid4())
    return CreateOrdersResult(
        checkout_group_id=str(uuid.uuid4()),
        idempotency_key="idem-test",
        status="completed",
        subtotal_ngwee=total_ngwee,
        delivery_fee_ngwee=0,
        total_ngwee=total_ngwee,
        replayed=False,
        orders=(
            CreatedOrder(
                order_id=order_id,
                vendor_id=VENDOR_ID,
                fulfilment="pickup",
                delivery_zone=None,
                delivery_fee_ngwee=0,
                subtotal_ngwee=total_ngwee,
                cod=False,
                commission_snapshot={},
                items=(
                    CreatedOrderItem(
                        order_item_id=str(uuid.uuid4()),
                        listing_id=LISTING_ID,
                        qty=1,
                        unit_price_ngwee=total_ngwee,
                        line_total_ngwee=total_ngwee,
                    ),
                ),
            ),
        ),
    )


def _client_with_service(service: MagicMock) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user] = _current_user

    def _override_service() -> Generator[object, None, None]:
        yield service

    app.dependency_overrides[get_supabase_client] = _override_service
    return TestClient(app, raise_server_exceptions=False)


def _post_momo(
    client: TestClient,
    *,
    session_id: str,
    total_ngwee: int,
) -> Any:
    return client.post(
        "/orders",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={
            "session_id": session_id,
            "idempotency_key": f"idem-{uuid.uuid4()}",
            "method": "momo",
            "rail": "mtn",
            "payer_number": PAYER,
            "groups": [
                {
                    "vendor_id": VENDOR_ID,
                    "fulfilment": "pickup",
                    "delivery_fee_ngwee": 0,
                    "subtotal_ngwee": total_ngwee,
                }
            ],
        },
    )


@pytest.fixture(autouse=True)
def _clear_cap_cache() -> Generator[None, None, None]:
    clear_vendor_cap_cache()
    yield
    clear_vendor_cap_cache()


class TestFirstOrderCapOnOrderCreate:
    def test_momo_over_k500_t1_order_count_zero_rejected(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        total = COD_CAP_NGWEE + 1
        session_id = str(uuid.uuid4())
        service = _mock_service(session_id=session_id, total_ngwee=total)
        monkeypatch.setattr(
            "app.routers.orders_create.get_user_client",
            lambda *_a, **_k: _mock_user_client(unit_price_ngwee=total),
        )
        monkeypatch.setattr(
            "app.services.kyc.caps.load_vendor_cap_limits_by_id",
            lambda _sc, _vid, **_kw: _t1_limits(order_count=0),
        )
        create_called = {"value": False}

        def _boom(**_kwargs: Any) -> CreateOrdersResult:
            create_called["value"] = True
            raise AssertionError("create_orders_atomic must not run when cap blocks")

        monkeypatch.setattr("app.routers.orders_create.create_orders_atomic", _boom)

        client = _client_with_service(service)
        response = _post_momo(client, session_id=session_id, total_ngwee=total)

        assert response.status_code == 403
        body = response.json()
        assert body["error"]["code"] == "first_order_cap_exceeded"
        assert body["error"]["details"]["message_key"] == "vendor.caps.first_order_amount"
        assert create_called["value"] is False

    def test_momo_under_cap_t1_succeeds(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        total = COD_CAP_NGWEE
        session_id = str(uuid.uuid4())
        service = _mock_service(session_id=session_id, total_ngwee=total)
        monkeypatch.setattr(
            "app.routers.orders_create.get_user_client",
            lambda *_a, **_k: _mock_user_client(unit_price_ngwee=total),
        )
        monkeypatch.setattr(
            "app.services.kyc.caps.load_vendor_cap_limits_by_id",
            lambda _sc, _vid, **_kw: _t1_limits(order_count=0),
        )
        monkeypatch.setattr(
            "app.routers.orders_create.create_orders_atomic",
            lambda **_kwargs: _fake_create_result(total_ngwee=total),
        )
        monkeypatch.setattr(
            "app.routers.orders_create.emit_order_placed_funnel",
            lambda **_kwargs: None,
        )

        client = _client_with_service(service)
        response = _post_momo(client, session_id=session_id, total_ngwee=total)

        assert response.status_code == 200
        assert response.json()["total_ngwee"] == total

    def test_momo_over_k500_t2_unlimited(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        total = COD_CAP_NGWEE + 1
        session_id = str(uuid.uuid4())
        service = _mock_service(session_id=session_id, total_ngwee=total)
        monkeypatch.setattr(
            "app.routers.orders_create.get_user_client",
            lambda *_a, **_k: _mock_user_client(unit_price_ngwee=total),
        )
        monkeypatch.setattr(
            "app.services.kyc.caps.load_vendor_cap_limits_by_id",
            lambda _sc, _vid, **_kw: _t2_limits(),
        )
        monkeypatch.setattr(
            "app.routers.orders_create.create_orders_atomic",
            lambda **_kwargs: _fake_create_result(total_ngwee=total),
        )
        monkeypatch.setattr(
            "app.routers.orders_create.emit_order_placed_funnel",
            lambda **_kwargs: None,
        )

        client = _client_with_service(service)
        response = _post_momo(client, session_id=session_id, total_ngwee=total)

        assert response.status_code == 200
        assert response.json()["total_ngwee"] == total
