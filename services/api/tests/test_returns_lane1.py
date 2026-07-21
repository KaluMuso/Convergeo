"""M09-P07 — returns lane 1 (faulty/wrong) tests.

CI: unit tests only; DB integration tests require psql locally.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.errors import AppError
from app.main import create_app
from app.services.ledger.engine import PostedTransaction
from app.services.refunds.execute import RefundExecutionResult, RefundPhase
from app.services.returns import lane1 as lane1_service
from fastapi import FastAPI
from fastapi.testclient import TestClient

CUSTOMER_A_ID = "11111111-1111-1111-1111-111111111111"
CUSTOMER_B_ID = "22222222-2222-2222-2222-222222222222"
VENDOR_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VENDOR_B_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
VENDOR_OWNER_A = "33333333-3333-3333-3333-333333333333"
VENDOR_OWNER_B = "44444444-4444-4444-4444-444444444444"
ORDER_A_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
ORDER_ITEM_A_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
RETURN_A_ID = "ffffffff-ffff-ffff-ffff-ffffffffffff"
ITEM_NGWEE = 100_000
DELIVERY_NGWEE = 5_000
EVIDENCE_PATH = f"orders/{CUSTOMER_A_ID}/{ORDER_A_ID}/evidence-1.jpg"


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | None = None
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._in_filter: tuple[str, list[Any]] | None = None

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        _ = count
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._in_filter = (column, values)
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

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self._pending_op = "update"
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

        if self._pending_op == "update":
            assert isinstance(self._payload, dict)
            updated: list[dict[str, Any]] = []
            for row in self._parent.rows:
                if self._matches(row):
                    row.update(self._payload)
                    updated.append(dict(row))
            return MagicMock(data=updated, count=None)

        rows = self._filtered_rows()
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: row.get(column, ""), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None, count=len(rows))
        return MagicMock(data=rows, count=len(rows))

    def _matches(self, row: dict[str, Any]) -> bool:
        for op, column, value in self._filters:
            if op == "eq" and row.get(column) != value:
                return False
        if self._in_filter is not None:
            column, values = self._in_filter
            if row.get(column) not in values:
                return False
        return True

    def _filtered_rows(self) -> list[dict[str, Any]]:
        rows = list(self._parent.rows)
        for op, column, value in self._filters:
            if op == "eq":
                rows = [row for row in rows if row.get(column) == value]
        if self._in_filter is not None:
            column, values = self._in_filter
            rows = [row for row in rows if row.get(column) in values]
        return rows


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self, []).select(columns, count=count)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).insert(payload)

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).update(payload)


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "orders": FakeTable(),
            "order_items": FakeTable(),
            "order_events": FakeTable(),
            "returns": FakeTable(),
            "disputes": FakeTable(),
            "vendors": FakeTable(),
            "profiles": FakeTable(),
            "notification_outbox": FakeTable(),
            "platform_config": FakeTable(),
        }

    def table(self, name: str) -> FakeTable:
        if name not in self.tables:
            self.tables[name] = FakeTable()
        return self.tables[name]

    def rpc(self, *_args: Any, **_kwargs: Any) -> MagicMock:
        payload = MagicMock(data=[{"allowed": True, "retry_after_seconds": 0}])
        return MagicMock(execute=MagicMock(return_value=payload))


class _FakeServiceWrapper:
    def __init__(self, client: FakeSupabaseClient) -> None:
        self.client = client


def _seed_fixture(
    fake: FakeSupabaseClient,
    *,
    customer_id: str = CUSTOMER_A_ID,
    vendor_id: str = VENDOR_A_ID,
    vendor_owner_id: str = VENDOR_OWNER_A,
    delivered_at: datetime | None = None,
) -> None:
    fake.tables["orders"].rows.append(
        {
            "id": ORDER_A_ID,
            "customer_id": customer_id,
            "vendor_id": vendor_id,
            "delivery_fee_ngwee": DELIVERY_NGWEE,
            "status": "delivered",
        }
    )
    fake.tables["order_items"].rows.append(
        {
            "id": ORDER_ITEM_A_ID,
            "order_id": ORDER_A_ID,
            "qty": 1,
            "unit_price_ngwee": ITEM_NGWEE,
            "title_snapshot": "Test widget",
        }
    )
    fake.tables["vendors"].rows.append(
        {"id": vendor_id, "owner_user_id": vendor_owner_id},
    )
    fake.tables["profiles"].rows.append(
        {"id": customer_id, "phone": "+260971234567"},
    )
    if delivered_at is not None:
        fake.tables["order_events"].rows.append(
            {
                "order_id": ORDER_A_ID,
                "to_status": "delivered",
                "created_at": delivered_at.isoformat(),
            }
        )


def _make_client(
    *,
    user_id: str,
    roles: frozenset[str],
    fake: FakeSupabaseClient,
) -> TestClient:
    app: FastAPI = create_app()

    async def override_current_user() -> CurrentUser:
        return CurrentUser(id=user_id, roles=roles, token="test-token")

    def override_service_client() -> _FakeServiceWrapper:
        return _FakeServiceWrapper(fake)

    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_supabase_client] = override_service_client
    return TestClient(app, raise_server_exceptions=False)


def test_window_enforcement_47h59m_ok() -> None:
    fake = FakeSupabaseClient()
    delivered_at = datetime.now(tz=UTC) - timedelta(hours=47, minutes=59)
    _seed_fixture(fake, delivered_at=delivered_at)

    with patch("app.services.returns.lane1.enqueue_outbox_row"):
        row = lane1_service.create_lane1_return(
            _FakeServiceWrapper(fake),
            order_item_id=ORDER_ITEM_A_ID,
            customer_id=CUSTOMER_A_ID,
            evidence_paths=[EVIDENCE_PATH],
            now=datetime.now(tz=UTC),
        )

    assert row["lane"] == 1
    assert row["status"] == "requested"


def test_window_enforcement_48h01m_blocked() -> None:
    fake = FakeSupabaseClient()
    delivered_at = datetime.now(tz=UTC) - timedelta(hours=48, minutes=1)
    _seed_fixture(fake, delivered_at=delivered_at)

    with pytest.raises(Exception) as exc_info:
        lane1_service.create_lane1_return(
            _FakeServiceWrapper(fake),
            order_item_id=ORDER_ITEM_A_ID,
            customer_id=CUSTOMER_A_ID,
            evidence_paths=[EVIDENCE_PATH],
            now=datetime.now(tz=UTC),
        )

    assert getattr(exc_info.value, "http_status", None) == 400


def test_evidence_gate_zero_photos_blocked() -> None:
    fake = FakeSupabaseClient()
    _seed_fixture(fake, delivered_at=datetime.now(tz=UTC) - timedelta(hours=1))

    with pytest.raises(Exception) as exc_info:
        lane1_service.create_lane1_return(
            _FakeServiceWrapper(fake),
            order_item_id=ORDER_ITEM_A_ID,
            customer_id=CUSTOMER_A_ID,
            evidence_paths=[],
        )

    assert getattr(exc_info.value, "http_status", None) == 400


def test_refund_composition_item_plus_delivery_golden() -> None:
    fake = FakeSupabaseClient()
    _seed_fixture(fake, delivered_at=datetime.now(tz=UTC) - timedelta(hours=1))

    preview = lane1_service.preview_lane1_breakdown(
        _FakeServiceWrapper(fake),
        order_item_id=ORDER_ITEM_A_ID,
        customer_id=CUSTOMER_A_ID,
    )
    breakdown = preview["fee_breakdown"]
    assert breakdown["item_ngwee"] == ITEM_NGWEE
    assert breakdown["delivery_ngwee"] == DELIVERY_NGWEE
    assert breakdown["total_ngwee"] == ITEM_NGWEE + DELIVERY_NGWEE
    assert breakdown["return_shipping_charged_to"] == "vendor"


@patch("app.services.returns.lane1.post_transaction")
@patch("app.services.returns.lane1.execute_refund")
def test_vendor_accept_invokes_lane1_refund_and_shipping_ledger(
    mock_execute_refund: MagicMock,
    mock_post_transaction: MagicMock,
) -> None:
    fake = FakeSupabaseClient()
    _seed_fixture(fake, delivered_at=datetime.now(tz=UTC) - timedelta(hours=1))
    fake.tables["returns"].rows.append(
        {
            "id": RETURN_A_ID,
            "order_item_id": ORDER_ITEM_A_ID,
            "lane": 1,
            "evidence_paths": [EVIDENCE_PATH],
            "fee_breakdown": {
                "item_ngwee": ITEM_NGWEE,
                "delivery_ngwee": DELIVERY_NGWEE,
                "total_ngwee": ITEM_NGWEE + DELIVERY_NGWEE,
                "return_shipping_charged_to": "vendor",
            },
            "status": "requested",
        }
    )

    mock_execute_refund.return_value = RefundExecutionResult(
        refund_id=str(uuid4()),
        order_id=ORDER_A_ID,
        lane=1,
        phase=RefundPhase.PRE_RELEASE,
        amount_ngwee=ITEM_NGWEE + DELIVERY_NGWEE,
        payout_id=str(uuid4()),
        lenco_reference="pay-test",
        ledger_transaction_ids=("ledger-refund-1",),
        breakdown={},
        created=True,
    )
    mock_post_transaction.return_value = PostedTransaction(
        id="ledger-shipping-1",
        kind="clawback",
        idempotency_key=f"return-{RETURN_A_ID}-shipping",
        created=True,
    )

    result = lane1_service.vendor_accept_lane1_return(
        _FakeServiceWrapper(fake),
        return_id=RETURN_A_ID,
        vendor_owner_id=VENDOR_OWNER_A,
    )

    mock_execute_refund.assert_called_once()
    call_kwargs = mock_execute_refund.call_args.kwargs
    assert call_kwargs["order_id"] == ORDER_A_ID
    assert call_kwargs["lane"] == 1

    mock_post_transaction.assert_called_once()
    shipping_kwargs = mock_post_transaction.call_args.kwargs
    assert shipping_kwargs["idempotency_key"] == f"return-{RETURN_A_ID}-shipping"
    assert result["status"] == "completed"


def test_vendor_contest_creates_dispute_row() -> None:
    fake = FakeSupabaseClient()
    _seed_fixture(fake, delivered_at=datetime.now(tz=UTC) - timedelta(hours=1))
    fake.tables["returns"].rows.append(
        {
            "id": RETURN_A_ID,
            "order_item_id": ORDER_ITEM_A_ID,
            "lane": 1,
            "evidence_paths": [EVIDENCE_PATH],
            "fee_breakdown": {},
            "status": "requested",
        }
    )

    result = lane1_service.vendor_contest_lane1_return(
        _FakeServiceWrapper(fake),
        return_id=RETURN_A_ID,
        vendor_owner_id=VENDOR_OWNER_A,
    )

    assert result["status"] == "rejected"
    assert len(fake.tables["disputes"].rows) == 1
    assert fake.tables["disputes"].rows[0]["status"] == "open"
    assert fake.tables["disputes"].rows[0]["order_id"] == ORDER_A_ID


def test_authz_cross_customer_404() -> None:
    fake = FakeSupabaseClient()
    _seed_fixture(fake, delivered_at=datetime.now(tz=UTC) - timedelta(hours=1))
    client = _make_client(user_id=CUSTOMER_B_ID, roles=frozenset({"customer"}), fake=fake)

    response = client.post(
        "/returns",
        json={
            "order_item_id": ORDER_ITEM_A_ID,
            "lane": 1,
            "evidence_paths": [EVIDENCE_PATH],
        },
    )

    assert response.status_code == 404


def test_authz_cross_vendor_404() -> None:
    fake = FakeSupabaseClient()
    _seed_fixture(fake, delivered_at=datetime.now(tz=UTC) - timedelta(hours=1))
    fake.tables["vendors"].rows.append(
        {"id": VENDOR_B_ID, "owner_user_id": VENDOR_OWNER_B},
    )
    fake.tables["returns"].rows.append(
        {
            "id": RETURN_A_ID,
            "order_item_id": ORDER_ITEM_A_ID,
            "lane": 1,
            "evidence_paths": [EVIDENCE_PATH],
            "fee_breakdown": {},
            "status": "requested",
        }
    )
    client = _make_client(user_id=VENDOR_OWNER_B, roles=frozenset({"vendor"}), fake=fake)

    response = client.post(
        f"/returns/{RETURN_A_ID}/respond",
        json={"action": "accept"},
    )

    assert response.status_code == 404


def test_lane2_requires_unused_declaration() -> None:
    fake = FakeSupabaseClient()
    _seed_fixture(fake, delivered_at=datetime.now(tz=UTC) - timedelta(hours=1))
    client = _make_client(user_id=CUSTOMER_A_ID, roles=frozenset({"customer"}), fake=fake)

    response = client.post(
        "/returns",
        json={
            "order_item_id": ORDER_ITEM_A_ID,
            "lane": 2,
            "unused_declaration": False,
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["details"]["reason"] == "unused_not_declared"


def test_submit_return_api_success() -> None:
    fake = FakeSupabaseClient()
    _seed_fixture(fake, delivered_at=datetime.now(tz=UTC) - timedelta(hours=1))
    client = _make_client(user_id=CUSTOMER_A_ID, roles=frozenset({"customer"}), fake=fake)

    with patch("app.services.returns.lane1.enqueue_outbox_row"):
        response = client.post(
            "/returns",
            json={
                "order_item_id": ORDER_ITEM_A_ID,
                "lane": 1,
                "evidence_paths": [EVIDENCE_PATH],
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["lane"] == 1
    assert body["fee_breakdown"]["total_ngwee"] == ITEM_NGWEE + DELIVERY_NGWEE


def test_cas_update_return_status_raises_conflict_on_stale_state() -> None:
    fake = FakeSupabaseClient()
    fake.tables["returns"].rows.append(
        {
            "id": RETURN_A_ID,
            "order_item_id": ORDER_ITEM_A_ID,
            "lane": 1,
            "status": "rejected",
        }
    )

    with pytest.raises(AppError) as exc_info:
        lane1_service._cas_update_return_status(
            _FakeServiceWrapper(fake),
            RETURN_A_ID,
            expected_status="requested",
            new_status="approved",
        )

    assert exc_info.value.code == "return_transition_conflict"
    assert exc_info.value.http_status == 409


@patch("app.services.returns.lane1.post_transaction")
@patch("app.services.returns.lane1.execute_refund")
def test_concurrent_accept_and_contest_exactly_one_wins(
    mock_execute_refund: MagicMock,
    mock_post_transaction: MagicMock,
) -> None:
    import concurrent.futures

    fake = FakeSupabaseClient()
    _seed_fixture(fake, delivered_at=datetime.now(tz=UTC) - timedelta(hours=1))
    fake.tables["returns"].rows.append(
        {
            "id": RETURN_A_ID,
            "order_item_id": ORDER_ITEM_A_ID,
            "lane": 1,
            "evidence_paths": [EVIDENCE_PATH],
            "fee_breakdown": {},
            "status": "requested",
        }
    )

    mock_execute_refund.return_value = RefundExecutionResult(
        refund_id=str(uuid4()),
        order_id=ORDER_A_ID,
        lane=1,
        phase=RefundPhase.PRE_RELEASE,
        amount_ngwee=ITEM_NGWEE + DELIVERY_NGWEE,
        payout_id=str(uuid4()),
        lenco_reference="pay-test",
        ledger_transaction_ids=("ledger-refund-1",),
        breakdown={},
        created=True,
    )
    mock_post_transaction.return_value = PostedTransaction(
        id="ledger-shipping-1",
        kind="clawback",
        idempotency_key=f"return-{RETURN_A_ID}-shipping",
        created=True,
    )

    def accept() -> object:
        try:
            return lane1_service.vendor_accept_lane1_return(
                _FakeServiceWrapper(fake),
                return_id=RETURN_A_ID,
                vendor_owner_id=VENDOR_OWNER_A,
            )
        except AppError as exc:
            if exc.code in {"return_transition_conflict", "validation_error"}:
                return None
            raise

    def contest() -> object:
        try:
            return lane1_service.vendor_contest_lane1_return(
                _FakeServiceWrapper(fake),
                return_id=RETURN_A_ID,
                vendor_owner_id=VENDOR_OWNER_A,
            )
        except AppError as exc:
            if exc.code in {"return_transition_conflict", "validation_error"}:
                return None
            raise

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(accept), executor.submit(contest)]
        results = [future.result() for future in futures]

    final_status = fake.tables["returns"].rows[0]["status"]
    assert final_status in {"approved", "rejected", "completed"}
    successes = [result for result in results if result is not None]
    assert len(successes) == 1
    assert len(fake.tables["disputes"].rows) <= 1


def test_concurrent_contest_exactly_one_wins_no_duplicate_dispute() -> None:
    import concurrent.futures

    fake = FakeSupabaseClient()
    _seed_fixture(fake, delivered_at=datetime.now(tz=UTC) - timedelta(hours=1))
    fake.tables["returns"].rows.append(
        {
            "id": RETURN_A_ID,
            "order_item_id": ORDER_ITEM_A_ID,
            "lane": 1,
            "evidence_paths": [EVIDENCE_PATH],
            "fee_breakdown": {},
            "status": "requested",
        }
    )

    def contest() -> object:
        try:
            return lane1_service.vendor_contest_lane1_return(
                _FakeServiceWrapper(fake),
                return_id=RETURN_A_ID,
                vendor_owner_id=VENDOR_OWNER_A,
            )
        except AppError as exc:
            if exc.code in {"return_transition_conflict", "validation_error"}:
                return None
            raise

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(contest), executor.submit(contest)]
        results = [future.result() for future in futures]

    assert fake.tables["returns"].rows[0]["status"] == "rejected"
    successes = [result for result in results if result is not None]
    assert len(successes) == 1
    assert len(fake.tables["disputes"].rows) == 1
