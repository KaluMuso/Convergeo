from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from app.deps import get_supabase_client
from app.errors import AppError
from app.main import create_app
from app.routers.vendor_orders import (
    ACTION_EVENT_MAP,
    _assert_vendor_owns_order,
    _available_vendor_actions,
)
from app.services.orders.state import ActorRole, OrderEvent, OrderStatus, TransitionOutcome
from fastapi.testclient import TestClient

USER_A_ID = "11111111-1111-1111-1111-111111111111"
USER_B_ID = "22222222-2222-2222-2222-222222222222"
VENDOR_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VENDOR_B_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
CUSTOMER_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
ORDER_A_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
ORDER_B_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
CHECKOUT_GROUP_ID = "ffffffff-ffff-ffff-ffff-ffffffffffff"
TOKEN_A = "vendor-a-token"
TOKEN_B = "vendor-b-token"


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | list[dict[str, Any]] | None = None
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        _ = count
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def order(self, column: str, *, desc: bool = False) -> FakeQuery:
        self._order = (column, desc)
        return self

    def limit(self, count: int) -> FakeQuery:
        self._limit = count
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        self._pending_op = "insert"
        self._payload = payload
        return self

    def execute(self) -> MagicMock:
        if self._pending_op == "insert":
            assert isinstance(self._payload, dict)
            row = dict(self._payload)
            if "id" not in row:
                row["id"] = str(uuid4())
            self._parent.rows.append(row)
            return MagicMock(data=[row], count=None)

        rows = self._filtered_rows()
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: row.get(column, ""), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None, count=len(rows))
        return MagicMock(data=rows, count=len(rows))

    def _filtered_rows(self) -> list[dict[str, Any]]:
        rows = list(self._parent.rows)
        for op, column, value in self._filters:
            if op == "eq":
                rows = [row for row in rows if row.get(column) == value]
        return rows


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self, []).select(columns, count=count)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).insert(payload)


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "vendors": FakeTable(),
            "orders": FakeTable(),
            "order_items": FakeTable(),
            "order_events": FakeTable(),
            "payments": FakeTable(),
            "notification_outbox": FakeTable(),
        }

    def table(self, name: str) -> FakeTable:
        return self.tables[name]


def _seed_vendors(fake: FakeSupabaseClient) -> None:
    fake.tables["vendors"].rows.extend(
        [
            {
                "id": VENDOR_A_ID,
                "owner_user_id": USER_A_ID,
                "status": "active",
            },
            {
                "id": VENDOR_B_ID,
                "owner_user_id": USER_B_ID,
                "status": "active",
            },
        ]
    )


def _seed_order(
    fake: FakeSupabaseClient,
    *,
    order_id: str,
    vendor_id: str,
    status: str = "placed",
    fulfilment: str = "delivery",
    cod: bool = False,
) -> None:
    fake.tables["orders"].rows.append(
        {
            "id": order_id,
            "checkout_group_id": CHECKOUT_GROUP_ID,
            "vendor_id": vendor_id,
            "customer_id": CUSTOMER_ID,
            "status": status,
            "fulfilment": fulfilment,
            "cod": cod,
            "delivery_fee_ngwee": 0,
            "created_at": "2026-07-10T00:00:00Z",
        }
    )


def _seed_payment(fake: FakeSupabaseClient, *, status: str = "success") -> None:
    fake.tables["payments"].rows.append(
        {
            "id": str(uuid4()),
            "checkout_group_id": CHECKOUT_GROUP_ID,
            "status": status,
        }
    )


def _mock_auth(monkeypatch: pytest.MonkeyPatch, user_id: str) -> None:
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": user_id, "exp": 9_999_999_999},
    )
    monkeypatch.setattr(
        "app.core.auth._load_user_roles",
        lambda uid, service_client: frozenset({"vendor"}),
    )


def _mock_supabase(monkeypatch: pytest.MonkeyPatch, fake: FakeSupabaseClient) -> MagicMock:
    service_wrapper = MagicMock()
    service_wrapper.client = fake
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: service_wrapper)
    monkeypatch.setattr("app.supabase_client.get_supabase_service_client", lambda: service_wrapper)
    return service_wrapper


def _apply_supabase_overrides(app: Any, service_wrapper: MagicMock) -> None:
    app.dependency_overrides[get_supabase_client] = lambda: service_wrapper


def _transition_outcome(
    *,
    order_id: str,
    from_status: str,
    to_status: str,
    event: OrderEvent,
) -> TransitionOutcome:
    return TransitionOutcome(
        order_id=order_id,
        from_status=OrderStatus(from_status),
        to_status=OrderStatus(to_status),
        event=event,
        actor_id=USER_A_ID,
        note="test",
    )


@pytest.fixture
def fake_client() -> FakeSupabaseClient:
    return FakeSupabaseClient()


@pytest.fixture
def orders_client(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> Generator[TestClient, None, None]:
    _mock_auth(monkeypatch, USER_A_ID)
    _seed_vendors(fake_client)
    _seed_order(fake_client, order_id=ORDER_A_ID, vendor_id=VENDOR_A_ID, status="placed")
    service_wrapper = _mock_supabase(monkeypatch, fake_client)
    app = create_app()
    _apply_supabase_overrides(app, service_wrapper)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


def _auth_headers(token: str = TOKEN_A) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_assert_vendor_owns_order_rejects_cross_vendor() -> None:
    with pytest.raises(AppError) as exc_info:
        _assert_vendor_owns_order(
            vendor_id=VENDOR_B_ID,
            order_row={"vendor_id": VENDOR_A_ID},
        )
    assert exc_info.value.http_status == 403


def test_available_actions_placed_includes_confirm_and_reject() -> None:
    actions = _available_vendor_actions(status="placed", fulfilment="delivery")
    assert "confirm" in actions
    assert "reject" in actions
    assert "ship" not in actions


def test_available_actions_processing_delivery_includes_ship_only() -> None:
    actions = _available_vendor_actions(status="processing", fulfilment="delivery")
    assert actions == ["ship"]


def test_available_actions_processing_pickup_includes_ready_for_pickup() -> None:
    actions = _available_vendor_actions(status="processing", fulfilment="pickup")
    assert actions == ["ready_for_pickup"]


def test_get_order_returns_available_actions(orders_client: TestClient) -> None:
    response = orders_client.get(f"/vendor/orders/{ORDER_A_ID}", headers=_auth_headers())
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "placed"
    assert "confirm" in payload["available_actions"]
    assert "reject" in payload["available_actions"]


def test_vendor_b_cannot_act_on_vendor_a_order(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_auth(monkeypatch, USER_B_ID)
    _seed_vendors(fake_client)
    _seed_order(fake_client, order_id=ORDER_A_ID, vendor_id=VENDOR_A_ID, status="placed")
    service_wrapper = _mock_supabase(monkeypatch, fake_client)
    app = create_app()
    _apply_supabase_overrides(app, service_wrapper)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            f"/vendor/orders/{ORDER_A_ID}/confirm",
            headers=_auth_headers(TOKEN_B),
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"

    app.dependency_overrides.clear()


@patch("app.routers.vendor_orders.transition_order")
def test_confirm_emits_outbox(
    mock_transition: MagicMock,
    orders_client: TestClient,
    fake_client: FakeSupabaseClient,
) -> None:
    mock_transition.return_value = _transition_outcome(
        order_id=ORDER_A_ID,
        from_status="placed",
        to_status="confirmed",
        event=OrderEvent.CONFIRM,
    )

    response = orders_client.post(
        f"/vendor/orders/{ORDER_A_ID}/confirm",
        headers=_auth_headers(),
    )
    assert response.status_code == 200
    mock_transition.assert_called_once()
    call_kwargs = mock_transition.call_args.kwargs
    assert call_kwargs["event"] == OrderEvent.CONFIRM
    assert call_kwargs["actor_role"] == ActorRole.VENDOR
    assert call_kwargs["actor_id"] == USER_A_ID

    outbox = fake_client.tables["notification_outbox"].rows
    assert len(outbox) == 1
    assert outbox[0]["dedupe_key"] == f"order-status-changed:{ORDER_A_ID}:whatsapp"
    assert outbox[0]["template"] == "order_status_changed"


@patch("app.routers.vendor_orders.transition_order")
def test_illegal_action_from_state_rejected(
    mock_transition: MagicMock,
    orders_client: TestClient,
    fake_client: FakeSupabaseClient,
) -> None:
    for row in fake_client.tables["orders"].rows:
        if row["id"] == ORDER_A_ID:
            row["status"] = "shipped"

    from app.services.orders.state import OrderTransitionError

    mock_transition.side_effect = OrderTransitionError(
        "No transition for shipped + confirm",
        from_status="shipped",
        event="confirm",
        actor_role="vendor",
    )

    response = orders_client.post(
        f"/vendor/orders/{ORDER_A_ID}/confirm",
        headers=_auth_headers(),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "order_invalid_transition"


def test_reject_requires_reason(orders_client: TestClient) -> None:
    response = orders_client.post(
        f"/vendor/orders/{ORDER_A_ID}/reject",
        headers=_auth_headers(),
        json={"reason": ""},
    )
    assert response.status_code == 422


def test_ship_requires_tracking_note(
    orders_client: TestClient,
    fake_client: FakeSupabaseClient,
) -> None:
    for row in fake_client.tables["orders"].rows:
        if row["id"] == ORDER_A_ID:
            row["status"] = "processing"

    response = orders_client.post(
        f"/vendor/orders/{ORDER_A_ID}/ship",
        headers=_auth_headers(),
        json={"tracking_note": ""},
    )
    assert response.status_code == 422


@patch("app.routers.vendor_orders.transition_order")
def test_reject_on_paid_order_enqueues_refund_event(
    mock_transition: MagicMock,
    orders_client: TestClient,
    fake_client: FakeSupabaseClient,
) -> None:
    _seed_payment(fake_client, status="success")
    mock_transition.return_value = _transition_outcome(
        order_id=ORDER_A_ID,
        from_status="placed",
        to_status="cancelled",
        event=OrderEvent.REJECT,
    )

    response = orders_client.post(
        f"/vendor/orders/{ORDER_A_ID}/reject",
        headers=_auth_headers(),
        json={"reason": "Out of stock"},
    )
    assert response.status_code == 200
    mock_transition.assert_called_once()
    assert mock_transition.call_args.kwargs["refund_path"] is True

    outbox = fake_client.tables["notification_outbox"].rows
    assert len(outbox) == 2
    dedupe_keys = {row["dedupe_key"] for row in outbox}
    assert f"order-status-changed:{ORDER_A_ID}:whatsapp" in dedupe_keys
    assert f"order-refund-required:{ORDER_A_ID}:whatsapp" in dedupe_keys
    refund_rows = [row for row in outbox if row["template"] == "order_refund_required"]
    assert refund_rows[0]["payload"]["reason"] == "Out of stock"


@patch("app.routers.vendor_orders.transition_order")
def test_ship_passes_tracking_note_to_transition(
    mock_transition: MagicMock,
    orders_client: TestClient,
    fake_client: FakeSupabaseClient,
) -> None:
    for row in fake_client.tables["orders"].rows:
        if row["id"] == ORDER_A_ID:
            row["status"] = "processing"

    mock_transition.return_value = _transition_outcome(
        order_id=ORDER_A_ID,
        from_status="processing",
        to_status="shipped",
        event=OrderEvent.SHIP,
    )

    response = orders_client.post(
        f"/vendor/orders/{ORDER_A_ID}/ship",
        headers=_auth_headers(),
        json={"tracking_note": "Yango driver John 0977123456"},
    )
    assert response.status_code == 200
    assert mock_transition.call_args.kwargs["note"] == "Yango driver John 0977123456"


def test_action_event_map_covers_all_vendor_actions() -> None:
    assert set(ACTION_EVENT_MAP) == {
        "confirm",
        "reject",
        "pack",
        "ship",
        "ready_for_pickup",
    }
