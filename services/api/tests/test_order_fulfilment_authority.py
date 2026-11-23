"""POST /orders: fulfilment type and delivery fees are server-authoritative.

The request body's ``groups`` used to be trusted as long as their sums matched
the checkout session, so a crafted request could get delivery at the pickup fee
or move a fee from one vendor to another. Order creation now re-prices each
vendor group from the choices the fulfilment step recorded and the live zone
rules, and refuses a request that disagrees.
"""

from __future__ import annotations

import uuid
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from app.errors import AppError
from app.services.orders.create import CartLineInput, CreateOrdersResult
from app.services.orders.fulfilment import (
    FULFILMENT_MISMATCH,
    FULFILMENT_NOT_CONFIRMED,
    DeclaredGroup,
    StoredChoice,
    authoritative_vendor_groups,
    parse_stored_choices,
)
from tests.test_order_first_order_cap import (
    CUSTOMER_ID,
    LISTING_ID,
    PAYER,
    VALID_TOKEN,
    VENDOR_ID,
    _client_with_service,
    _fake_create_result,
    _mock_service,
    _mock_user_client,
    _patch_order_create_price_context,
    _t2_limits,
)

VENDOR_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
ZONE_FEES = {"lusaka_a": 3_000, "lusaka_b": 4_500}
FREE_THRESHOLD = 200_000


def _fee(subtotal: int, zone: str | None) -> int:
    if zone is None or subtotal >= FREE_THRESHOLD:
        return 0
    return ZONE_FEES.get(zone, 0)


def _line(vendor_id: str, price: int) -> CartLineInput:
    return CartLineInput(
        cart_item_id=str(uuid.uuid4()),
        listing_id=str(uuid.uuid4()),
        vendor_id=vendor_id,
        qty=1,
        unit_price_ngwee=price,
        title_snapshot=None,
    )


def _declared(
    vendor_id: str, fulfilment: str, zone: str | None, fee: int, subtotal: int
) -> DeclaredGroup:
    return DeclaredGroup(
        vendor_id=vendor_id,
        fulfilment=fulfilment,
        delivery_zone=zone,
        delivery_fee_ngwee=fee,
        subtotal_ngwee=subtotal,
    )


def _resolve(
    *,
    stored: dict[str, StoredChoice],
    declared: list[DeclaredGroup],
    address_zone: str | None = "lusaka_a",
    lines: list[CartLineInput] | None = None,
) -> list[Any]:
    return authoritative_vendor_groups(
        cart_lines=lines or [_line(VENDOR_ID, 10_000), _line(VENDOR_B, 20_000)],
        stored_choices=stored,
        declared_groups=declared,
        address_zone=address_zone,
        compute_fee=_fee,
    )


def _code(exc: pytest.ExceptionInfo[AppError]) -> str:
    return exc.value.code


MIXED = {
    VENDOR_ID: StoredChoice(VENDOR_ID, "delivery", "lusaka_a"),
    VENDOR_B: StoredChoice(VENDOR_B, "pickup", None),
}


class TestAuthoritativeVendorGroups:
    def test_server_values_are_returned_for_an_honest_request(self) -> None:
        groups = _resolve(
            stored=MIXED,
            declared=[
                _declared(VENDOR_ID, "delivery", "lusaka_a", 3_000, 10_000),
                _declared(VENDOR_B, "pickup", None, 0, 20_000),
            ],
        )
        summary = [
            (g.vendor_id, g.fulfilment, g.delivery_zone, g.delivery_fee_ngwee) for g in groups
        ]
        assert summary == [
            (VENDOR_ID, "delivery", "lusaka_a", 3_000),
            (VENDOR_B, "pickup", None, 0),
        ]

    def test_delivery_at_the_pickup_fee_is_refused(self) -> None:
        with pytest.raises(AppError) as exc:
            _resolve(
                stored=MIXED,
                declared=[
                    _declared(VENDOR_ID, "delivery", "lusaka_a", 0, 10_000),
                    _declared(VENDOR_B, "pickup", None, 0, 20_000),
                ],
            )
        assert _code(exc) == FULFILMENT_MISMATCH
        assert exc.value.http_status == 409
        assert exc.value.details["field"] == "delivery_fee_ngwee"

    def test_claiming_delivery_for_a_group_confirmed_as_pickup_is_refused(self) -> None:
        with pytest.raises(AppError) as exc:
            _resolve(
                stored=MIXED,
                declared=[
                    _declared(VENDOR_ID, "delivery", "lusaka_a", 3_000, 10_000),
                    _declared(VENDOR_B, "delivery", "lusaka_a", 0, 20_000),
                ],
            )
        assert _code(exc) == FULFILMENT_MISMATCH
        assert exc.value.details["vendor_id"] == VENDOR_B

    def test_moving_a_fee_between_vendor_groups_is_refused(self) -> None:
        both_delivery = {
            VENDOR_ID: StoredChoice(VENDOR_ID, "delivery", "lusaka_a"),
            VENDOR_B: StoredChoice(VENDOR_B, "delivery", "lusaka_a"),
        }
        # Same total delivery (6 000) as the honest split 3 000 / 3 000.
        with pytest.raises(AppError) as exc:
            _resolve(
                stored=both_delivery,
                declared=[
                    _declared(VENDOR_ID, "delivery", "lusaka_a", 6_000, 10_000),
                    _declared(VENDOR_B, "delivery", "lusaka_a", 0, 20_000),
                ],
            )
        assert _code(exc) == FULFILMENT_MISMATCH

    def test_address_that_no_longer_prices_into_the_quoted_zone_is_refused(self) -> None:
        with pytest.raises(AppError) as exc:
            _resolve(
                stored=MIXED,
                declared=[
                    _declared(VENDOR_ID, "delivery", "lusaka_a", 3_000, 10_000),
                    _declared(VENDOR_B, "pickup", None, 0, 20_000),
                ],
                address_zone="lusaka_b",
            )
        assert _code(exc) == FULFILMENT_MISMATCH
        assert exc.value.details["field"] == "delivery_zone"

    def test_cart_vendors_changed_after_fulfilment_needs_reconfirmation(self) -> None:
        with pytest.raises(AppError) as exc:
            _resolve(
                stored={VENDOR_ID: MIXED[VENDOR_ID]},
                declared=[_declared(VENDOR_ID, "delivery", "lusaka_a", 3_000, 10_000)],
            )
        assert _code(exc) == FULFILMENT_NOT_CONFIRMED

    def test_missing_or_malformed_record_is_not_confirmed(self) -> None:
        for raw in (None, [], [{"vendor_id": VENDOR_ID, "fulfilment": "drone"}], "x"):
            with pytest.raises(AppError) as exc:
                parse_stored_choices(raw)
            assert _code(exc) == FULFILMENT_NOT_CONFIRMED


def _service_with_choices(*, total: int, choices: object) -> MagicMock:
    service = _mock_service(session_id=str(uuid.uuid4()), total_ngwee=total)
    original = service.client.table.side_effect

    def table(name: str) -> MagicMock:
        builder: MagicMock = original(name)
        if name == "checkout_groups":
            chain = builder.select.return_value.eq.return_value.eq.return_value.maybe_single
            row = dict(chain.return_value.execute.return_value.data)
            row["fulfilment_choices"] = choices
            chain.return_value.execute.return_value = MagicMock(data=row)
        return builder

    service.client.table.side_effect = table
    return service


def _post(client: Any, *, group: dict[str, Any], address_id: str | None = None) -> Any:
    return client.post(
        "/orders",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={
            "session_id": str(uuid.uuid4()),
            "idempotency_key": f"idem-{uuid.uuid4()}",
            "method": "momo",
            "rail": "mtn",
            "payer_number": PAYER,
            "address_id": address_id,
            "groups": [group],
        },
    )


@pytest.fixture
def order_endpoint(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    total = 30_000
    monkeypatch.setattr(
        "app.routers.orders_create.get_user_client",
        lambda *_a, **_k: _mock_user_client(unit_price_ngwee=total),
    )
    _patch_order_create_price_context(monkeypatch, unit_price_ngwee=total)
    monkeypatch.setattr(
        "app.services.kyc.caps.load_vendor_cap_limits_by_id",
        lambda _sc, _vid, **_kw: _t2_limits(),
    )
    monkeypatch.setattr(
        "app.routers.orders_create.emit_order_placed_funnel", lambda **_kwargs: None
    )
    calls: list[dict[str, Any]] = []

    def _create(**kwargs: Any) -> CreateOrdersResult:
        calls.append(kwargs)
        return _fake_create_result(total_ngwee=total)

    monkeypatch.setattr("app.routers.orders_create.create_orders_atomic", _create)
    return {"total": total, "calls": calls}


class TestCreateOrdersEndpointAuthority:
    def test_crafted_delivery_on_a_pickup_session_is_refused(
        self, order_endpoint: dict[str, Any]
    ) -> None:
        total = order_endpoint["total"]
        service = _service_with_choices(
            total=total,
            choices=[{"vendor_id": VENDOR_ID, "fulfilment": "pickup", "delivery_zone": None}],
        )
        response = _post(
            _client_with_service(service),
            group={
                "vendor_id": VENDOR_ID,
                "fulfilment": "delivery",
                "delivery_zone": "lusaka_a",
                "delivery_fee_ngwee": 0,
                "subtotal_ngwee": total,
            },
            address_id=str(uuid.uuid4()),
        )
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == FULFILMENT_MISMATCH
        assert order_endpoint["calls"] == []

    def test_session_without_recorded_choices_is_refused(
        self, order_endpoint: dict[str, Any]
    ) -> None:
        total = order_endpoint["total"]
        service = _service_with_choices(total=total, choices=None)
        response = _post(
            _client_with_service(service),
            group={
                "vendor_id": VENDOR_ID,
                "fulfilment": "pickup",
                "delivery_fee_ngwee": 0,
                "subtotal_ngwee": total,
            },
        )
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == FULFILMENT_NOT_CONFIRMED
        assert order_endpoint["calls"] == []

    def test_delivery_groups_are_priced_from_the_saved_address(
        self, order_endpoint: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        total = order_endpoint["total"]
        address_id = str(uuid.uuid4())
        service = _service_with_choices(
            total=total + 3_000,
            choices=[
                {"vendor_id": VENDOR_ID, "fulfilment": "delivery", "delivery_zone": "lusaka_a"}
            ],
        )
        # The session mock reports subtotal == total; keep the cart consistent.
        original = service.client.table.side_effect
        seen_address_filters: list[tuple[str, Any]] = []

        def table(name: str) -> MagicMock:
            if name == "addresses":
                builder = MagicMock()

                def eq(column: str, value: Any) -> MagicMock:
                    seen_address_filters.append((column, value))
                    return cast(MagicMock, builder.select.return_value)

                builder.select.return_value.eq.side_effect = eq
                builder.select.return_value.maybe_single.return_value.execute.return_value = (
                    MagicMock(data={"id": address_id, "landmark": "Woodlands Stage 2"})
                )
                return builder
            builder = cast(MagicMock, original(name))
            if name == "checkout_groups":
                chain = builder.select.return_value.eq.return_value.eq.return_value.maybe_single
                row = dict(chain.return_value.execute.return_value.data)
                row.update(subtotal_ngwee=total, delivery_fee_ngwee=3_000)
                chain.return_value.execute.return_value = MagicMock(data=row)
            return builder

        service.client.table.side_effect = table
        monkeypatch.setattr(
            "app.routers.orders_create._load_delivery_zones",
            lambda _s: {"lusaka_a": {"zone_key": "lusaka_a", "fee_ngwee": 3_000}},
        )

        response = _post(
            _client_with_service(service),
            group={
                "vendor_id": VENDOR_ID,
                "fulfilment": "delivery",
                "delivery_zone": "lusaka_a",
                "delivery_fee_ngwee": 3_000,
                "subtotal_ngwee": total,
            },
            address_id=address_id,
        )
        assert response.status_code == 200, response.text
        (call,) = order_endpoint["calls"]
        (group,) = call["vendor_groups"]
        assert (group.fulfilment, group.delivery_zone, group.delivery_fee_ngwee) == (
            "delivery",
            "lusaka_a",
            3_000,
        )
        # Only the buyer's own address is ever priced.
        assert ("user_id", CUSTOMER_ID) in seen_address_filters
        assert call["cart_lines"][0].listing_id == LISTING_ID
