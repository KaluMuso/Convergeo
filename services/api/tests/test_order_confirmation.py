from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.main import create_app
from app.services.orders.state import OrderEvent, OrderStatus, TransitionOutcome
from fastapi import FastAPI
from fastapi.testclient import TestClient

CUSTOMER_A_ID = "11111111-1111-1111-1111-111111111111"
CUSTOMER_B_ID = "22222222-2222-2222-2222-222222222222"
ORDER_A_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
TOKEN_A = "customer-a-token"


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | None = None
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


class _FakeBucket:
    def __init__(self, recorder: dict[str, Any]) -> None:
        self._recorder = recorder

    def create_signed_upload_url(self, path: str) -> dict[str, str]:
        self._recorder["path"] = path
        return {"signed_url": f"https://stack.local/upload/{path}?token=abc", "token": "abc"}


class _FakeStorage:
    def __init__(self, recorder: dict[str, Any]) -> None:
        self._recorder = recorder

    def from_(self, bucket: str) -> _FakeBucket:
        self._recorder["bucket"] = bucket
        return _FakeBucket(self._recorder)


class FakeSupabaseClient:
    def __init__(self, recorder: dict[str, Any] | None = None) -> None:
        self.tables: dict[str, FakeTable] = {
            "orders": FakeTable(),
            "order_events": FakeTable(),
            "disputes": FakeTable(),
            "notification_outbox": FakeTable(),
        }
        self._storage_recorder = recorder if recorder is not None else {}
        self.storage = _FakeStorage(self._storage_recorder)

    def table(self, name: str) -> FakeTable:
        return self.tables[name]


class _FakeServiceWrapper:
    def __init__(self, client: FakeSupabaseClient) -> None:
        self.client = client


def _make_client(
    *,
    customer_id: str,
    fake: FakeSupabaseClient,
) -> TestClient:
    app: FastAPI = create_app()

    async def override_current_user() -> CurrentUser:
        return CurrentUser(id=customer_id, roles=frozenset({"customer"}), token=TOKEN_A)

    def override_service_client() -> _FakeServiceWrapper:
        return _FakeServiceWrapper(fake)

    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_supabase_client] = override_service_client
    return TestClient(app, raise_server_exceptions=False)


def _seed_order(
    fake: FakeSupabaseClient,
    *,
    order_id: str,
    customer_id: str,
    status: str = "delivered",
) -> None:
    fake.tables["orders"].rows.append(
        {
            "id": order_id,
            "customer_id": customer_id,
            "status": status,
            "fulfilment": "delivery",
            "checkout_group_id": str(uuid4()),
        }
    )


def _seed_delivered_event(
    fake: FakeSupabaseClient,
    *,
    order_id: str,
    delivered_at: datetime,
) -> None:
    fake.tables["order_events"].rows.append(
        {
            "order_id": order_id,
            "to_status": "delivered",
            "created_at": delivered_at.isoformat(),
        }
    )


def _transition_outcome() -> TransitionOutcome:
    return TransitionOutcome(
        order_id=ORDER_A_ID,
        from_status=OrderStatus.DELIVERED,
        to_status=OrderStatus.COMPLETED,
        event=OrderEvent.CONFIRM_RECEIVED,
        actor_id=CUSTOMER_A_ID,
        note="Customer confirmed receipt",
    )


@patch("app.routers.order_confirmation._evaluate_and_release")
@patch("app.routers.order_confirmation.transition_order")
def test_double_confirm_idempotent_single_release(
    mock_transition: MagicMock,
    mock_release: MagicMock,
) -> None:
    fake = FakeSupabaseClient()
    _seed_order(fake, order_id=ORDER_A_ID, customer_id=CUSTOMER_A_ID, status="delivered")
    mock_transition.return_value = _transition_outcome()
    client = _make_client(customer_id=CUSTOMER_A_ID, fake=fake)

    first = client.post(f"/orders/{ORDER_A_ID}/confirm-received")
    assert first.status_code == 200, first.text
    assert first.json()["already_confirmed"] is False

    fake.tables["orders"].rows[0]["status"] = "completed"
    second = client.post(f"/orders/{ORDER_A_ID}/confirm-received")
    assert second.status_code == 200, second.text
    assert second.json()["already_confirmed"] is True

    mock_transition.assert_called_once()
    mock_release.assert_called_once()
    # _evaluate_and_release(service_client, order_id) — order_id is the 2nd positional arg.
    assert mock_release.call_args.args[1] == ORDER_A_ID


@patch("app.routers.order_confirmation.transition_order")
def test_confirm_calls_real_release_with_client_and_order_id(
    mock_transition: MagicMock,
) -> None:
    """Regression: confirm-received must call the M08-P08 engine as
    evaluate_and_release(service_client, order_id) — NOT order_id= alone (which
    raises TypeError against the real signature and 500s the endpoint)."""
    import app.services.escrow.release as release_mod

    calls: list[tuple[Any, str]] = []

    # Spy carries the REAL M08-P08 signature; a mis-call would TypeError here.
    def _spy(service_client: Any, order_id: str, *, now: Any = None) -> None:
        calls.append((service_client, order_id))

    fake = FakeSupabaseClient()
    _seed_order(fake, order_id=ORDER_A_ID, customer_id=CUSTOMER_A_ID, status="delivered")
    mock_transition.return_value = _transition_outcome()
    client = _make_client(customer_id=CUSTOMER_A_ID, fake=fake)

    with patch.object(release_mod, "evaluate_and_release", _spy):
        response = client.post(f"/orders/{ORDER_A_ID}/confirm-received")

    assert response.status_code == 200, response.text
    assert len(calls) == 1
    assert calls[0][1] == ORDER_A_ID  # order_id passed positionally as the 2nd arg


@patch("app.routers.order_confirmation._within_report_window", return_value=True)
def test_faulty_within_window_routes_lane1(_mock_window: MagicMock) -> None:
    fake = FakeSupabaseClient()
    _seed_order(fake, order_id=ORDER_A_ID, customer_id=CUSTOMER_A_ID, status="delivered")
    _seed_delivered_event(
        fake,
        order_id=ORDER_A_ID,
        delivered_at=datetime.now(tz=UTC) - timedelta(hours=12),
    )
    client = _make_client(customer_id=CUSTOMER_A_ID, fake=fake)

    response = client.post(
        f"/orders/{ORDER_A_ID}/report-problem",
        json={"category": "faulty", "description": "Screen cracked", "evidence_paths": []},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["route"] == "lane1"
    assert body["within_window"] is True
    outbox = fake.tables["notification_outbox"].rows
    assert len(outbox) == 1
    assert outbox[0]["template"] == "lane1-return-intent"


@patch("app.routers.order_confirmation._within_report_window", return_value=False)
def test_faulty_after_window_routes_guidance(_mock_window: MagicMock) -> None:
    fake = FakeSupabaseClient()
    _seed_order(fake, order_id=ORDER_A_ID, customer_id=CUSTOMER_A_ID, status="delivered")
    _seed_delivered_event(
        fake,
        order_id=ORDER_A_ID,
        delivered_at=datetime.now(tz=UTC) - timedelta(hours=49),
    )
    client = _make_client(customer_id=CUSTOMER_A_ID, fake=fake)

    response = client.post(
        f"/orders/{ORDER_A_ID}/report-problem",
        json={"category": "wrong", "description": "Wrong colour", "evidence_paths": []},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["route"] == "guidance"
    assert body["within_window"] is False
    assert body["guidance_key"] == "report.guidance.expired"
    assert fake.tables["notification_outbox"].rows == []


def test_not_delivered_creates_dispute_row() -> None:
    fake = FakeSupabaseClient()
    _seed_order(fake, order_id=ORDER_A_ID, customer_id=CUSTOMER_A_ID, status="shipped")
    evidence_path = f"orders/{CUSTOMER_A_ID}/{ORDER_A_ID}/evidence-1.jpg"
    client = _make_client(customer_id=CUSTOMER_A_ID, fake=fake)

    response = client.post(
        f"/orders/{ORDER_A_ID}/report-problem",
        json={
            "category": "not_delivered",
            "description": "Never arrived",
            "evidence_paths": [evidence_path],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["route"] == "dispute"
    disputes = fake.tables["disputes"].rows
    assert len(disputes) == 1
    assert disputes[0]["order_id"] == ORDER_A_ID
    assert disputes[0]["opener_user_id"] == CUSTOMER_A_ID
    assert disputes[0]["evidence_paths"] == [evidence_path]
    assert body["dispute_id"] == disputes[0]["id"]


def test_other_routes_support() -> None:
    fake = FakeSupabaseClient()
    _seed_order(fake, order_id=ORDER_A_ID, customer_id=CUSTOMER_A_ID, status="delivered")
    client = _make_client(customer_id=CUSTOMER_A_ID, fake=fake)

    response = client.post(
        f"/orders/{ORDER_A_ID}/report-problem",
        json={"category": "other", "description": "Need help", "evidence_paths": []},
    )
    assert response.status_code == 200, response.text
    assert response.json()["route"] == "support"
    outbox = fake.tables["notification_outbox"].rows
    assert len(outbox) == 1
    assert outbox[0]["template"] == "order-support-request"


def test_48h_window_boundary_within() -> None:
    from app.routers.order_confirmation import _within_report_window

    delivered_at = datetime.now(tz=UTC) - timedelta(hours=47, minutes=59)
    assert _within_report_window(delivered_at) is True


def test_48h_window_boundary_after() -> None:
    from app.routers.order_confirmation import _within_report_window

    delivered_at = datetime.now(tz=UTC) - timedelta(hours=48, minutes=1)
    assert _within_report_window(delivered_at) is False


def test_evidence_sign_owner_scoped() -> None:
    recorder: dict[str, Any] = {}
    fake = FakeSupabaseClient(recorder)
    _seed_order(fake, order_id=ORDER_A_ID, customer_id=CUSTOMER_A_ID, status="delivered")
    client = _make_client(customer_id=CUSTOMER_A_ID, fake=fake)

    response = client.post(
        f"/orders/{ORDER_A_ID}/evidence/sign",
        json={"file_size_bytes": 500_000, "content_type": "image/jpeg"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["bucket"] == "order-evidence"
    assert body["path"].startswith(f"orders/{CUSTOMER_A_ID}/{ORDER_A_ID}/evidence-")
    assert body["token"] == "abc"
    assert recorder["bucket"] == "order-evidence"


def test_other_customer_gets_404() -> None:
    fake = FakeSupabaseClient()
    _seed_order(fake, order_id=ORDER_A_ID, customer_id=CUSTOMER_A_ID, status="delivered")
    client = _make_client(customer_id=CUSTOMER_B_ID, fake=fake)

    response = client.post(f"/orders/{ORDER_A_ID}/confirm-received")
    assert response.status_code == 404
