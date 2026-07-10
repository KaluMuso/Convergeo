"""M09-P08 — lane-2 (change-of-mind) returns tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from app.errors import AppError
from app.services.refunds.execute import RefundExecutionResult, RefundPhase
from app.services.refunds.math import compute_lane2_refund
from app.services.returns.lane2 import (
    DEFAULT_RESTOCKING_PCT,
    MAX_RESTOCKING_PCT,
    MIN_RESTOCKING_PCT,
    check_eligibility,
    compute_lane2_breakdown,
    create_lane2_return,
    load_restocking_pct,
    normalize_restocking_pct,
    normalize_return_window_hours,
)

CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_CUSTOMER_ID = "22222222-2222-2222-2222-222222222222"
ORDER_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
ORDER_ITEM_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
LISTING_ID = "ffffffff-ffff-ffff-ffff-ffffffffffff"
CUSTOMER_MOMO = "+260971234567"


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | None = None
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._selected = "*"

    def select(self, columns: str) -> FakeQuery:
        self._selected = columns
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
            assert self._payload is not None
            row = dict(self._payload)
            if "id" not in row:
                row["id"] = str(uuid4())
            self._parent.rows.append(row)
            return MagicMock(data=[row])
        rows = self._parent._filter_rows(self._filters)
        if self._order is not None:
            col, desc = self._order
            rows = sorted(rows, key=lambda r: r.get(col, ""), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=rows)


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str) -> FakeQuery:
        return FakeQuery(self, []).select(columns)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).insert(payload)

    def _filter_rows(self, filters: list[tuple[str, str, Any]]) -> list[dict[str, Any]]:
        result = list(self.rows)
        for op, column, value in filters:
            if op == "eq":
                result = [row for row in result if row.get(column) == value]
        return result


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "order_items": FakeTable(),
            "orders": FakeTable(),
            "order_item_products": FakeTable(),
            "vendor_listings": FakeTable(),
            "order_events": FakeTable(),
            "returns": FakeTable(),
            "platform_config": FakeTable(),
            "refunds": FakeTable(),
            "payouts": FakeTable(),
            "ledger_transactions": FakeTable(),
        }

    def table(self, name: str) -> FakeTable:
        return self.tables[name]


class FakeServiceClient:
    def __init__(self, client: FakeSupabaseClient) -> None:
        self.client = client


def _seed_eligible_order(
    fake: FakeSupabaseClient,
    *,
    customer_id: str = CUSTOMER_ID,
    returnable: bool = True,
    return_window_hours: int = 72,
    delivered_at: datetime | None = None,
    item_ngwee: int = 200_000,
    delivery_fee: int = 10_000,
) -> None:
    fake.tables["order_items"].rows.append(
        {
            "id": ORDER_ITEM_ID,
            "order_id": ORDER_ID,
            "qty": 1,
            "unit_price_ngwee": item_ngwee,
        }
    )
    fake.tables["orders"].rows.append(
        {
            "id": ORDER_ID,
            "customer_id": customer_id,
            "delivery_fee_ngwee": delivery_fee,
            "status": "delivered",
        }
    )
    fake.tables["order_item_products"].rows.append(
        {
            "order_item_id": ORDER_ITEM_ID,
            "listing_id": LISTING_ID,
        }
    )
    fake.tables["vendor_listings"].rows.append(
        {
            "id": LISTING_ID,
            "returnable": returnable,
            "return_window_hours": return_window_hours,
        }
    )
    if delivered_at is not None:
        fake.tables["order_events"].rows.append(
            {
                "order_id": ORDER_ID,
                "to_status": "delivered",
                "created_at": delivered_at.isoformat(),
            }
        )


class TestNormalizeHelpers:
    def test_return_window_clamp(self) -> None:
        assert normalize_return_window_hours(None) == 48
        assert normalize_return_window_hours(24) == 48
        assert normalize_return_window_hours(72) == 72
        assert normalize_return_window_hours(999) == 168

    def test_restocking_pct_default_and_clamp(self) -> None:
        assert normalize_restocking_pct(None) == DEFAULT_RESTOCKING_PCT
        assert normalize_restocking_pct(3) == MIN_RESTOCKING_PCT
        assert normalize_restocking_pct(20) == MAX_RESTOCKING_PCT


class TestLane2FeeMath:
    @pytest.mark.parametrize(
        ("pct", "item", "outbound", "transport", "expected_restocking", "expected_refund"),
        [
            (5, 200_000, 10_000, 5_000, 10_000, 175_000),
            (10, 200_000, 10_000, 5_000, 20_000, 165_000),
            (15, 200_000, 10_000, 5_000, 30_000, 155_000),
            (10, 123_456, 0, 0, 12_345, 111_111),
            (15, 1_000, 500, 400, 150, 0),
        ],
    )
    def test_compute_lane2_breakdown_goldens(
        self,
        pct: int,
        item: int,
        outbound: int,
        transport: int,
        expected_restocking: int,
        expected_refund: int,
    ) -> None:
        breakdown = compute_lane2_breakdown(
            item_ngwee=item,
            outbound_delivery_ngwee=outbound,
            return_transport_ngwee=transport,
            restocking_pct=pct,
        )
        assert breakdown.item == max(0, item)
        assert breakdown.outbound_delivery == max(0, outbound)
        assert breakdown.return_transport == max(0, transport)
        assert breakdown.restocking == expected_restocking
        assert breakdown.refund_ngwee == expected_refund
        assert breakdown.refund_ngwee >= 0

    def test_breakdown_matches_m08_lane2_execution(self) -> None:
        item = 250_000
        outbound = 12_500
        transport = 7_500
        pct = 10
        preview = compute_lane2_breakdown(
            item_ngwee=item,
            outbound_delivery_ngwee=outbound,
            return_transport_ngwee=transport,
            restocking_pct=pct,
        )
        executed = compute_lane2_refund(
            item_ngwee=item,
            outbound_delivery_ngwee=outbound,
            return_transport_ngwee=transport,
            restocking_fee_bps=pct * 100,
        )
        assert preview.restocking == executed.restocking_fee_ngwee
        assert preview.refund_ngwee == executed.refund_ngwee


class TestEligibilityMatrix:
    def test_flag_off_ineligible(self) -> None:
        fake = FakeSupabaseClient()
        _seed_eligible_order(fake, returnable=False)
        result = check_eligibility(
            FakeServiceClient(fake),
            order_item_id=ORDER_ITEM_ID,
            customer_id=CUSTOMER_ID,
        )
        assert result.eligible is False
        assert result.reason == "listing_not_returnable"

    def test_window_expired_ineligible(self) -> None:
        fake = FakeSupabaseClient()
        _seed_eligible_order(
            fake,
            return_window_hours=48,
            delivered_at=datetime.now(tz=UTC) - timedelta(hours=49),
        )
        result = check_eligibility(
            FakeServiceClient(fake),
            order_item_id=ORDER_ITEM_ID,
            customer_id=CUSTOMER_ID,
        )
        assert result.eligible is False
        assert result.reason == "return_window_expired"

    def test_owner_mismatch_ineligible(self) -> None:
        fake = FakeSupabaseClient()
        _seed_eligible_order(
            fake,
            delivered_at=datetime.now(tz=UTC) - timedelta(hours=12),
        )
        result = check_eligibility(
            FakeServiceClient(fake),
            order_item_id=ORDER_ITEM_ID,
            customer_id=OTHER_CUSTOMER_ID,
        )
        assert result.eligible is False
        assert result.reason == "owner_mismatch"

    def test_eligible_within_window(self) -> None:
        fake = FakeSupabaseClient()
        _seed_eligible_order(
            fake,
            return_window_hours=72,
            delivered_at=datetime.now(tz=UTC) - timedelta(hours=71, minutes=59),
        )
        result = check_eligibility(
            FakeServiceClient(fake),
            order_item_id=ORDER_ITEM_ID,
            customer_id=CUSTOMER_ID,
        )
        assert result.eligible is True
        assert result.return_window_hours == 72


class TestRestockingConfig:
    def test_load_restocking_pct_from_platform_config(self) -> None:
        fake = FakeSupabaseClient()
        fake.tables["platform_config"].rows.append(
            {"key": "restocking_fee_pct", "value": 12}
        )
        assert load_restocking_pct(FakeServiceClient(fake)) == 12

    def test_load_restocking_pct_falls_back_to_bps_config(self) -> None:
        fake = FakeSupabaseClient()
        fake.tables["platform_config"].rows.append(
            {"key": "restocking_fee_bps", "value": 1500}
        )
        assert load_restocking_pct(FakeServiceClient(fake)) == 15


class TestCreateLane2Return:
    @patch("app.services.returns.lane2.execute_refund")
    def test_create_lane2_return_executes_matching_refund(self, mock_execute: MagicMock) -> None:
        fake = FakeSupabaseClient()
        _seed_eligible_order(
            fake,
            delivered_at=datetime.now(tz=UTC) - timedelta(hours=24),
            item_ngwee=200_000,
            delivery_fee=10_000,
        )
        preview = compute_lane2_breakdown(
            item_ngwee=200_000,
            outbound_delivery_ngwee=10_000,
            return_transport_ngwee=5_000,
            restocking_pct=10,
        )
        mock_execute.return_value = RefundExecutionResult(
            refund_id="refund-1",
            order_id=ORDER_ID,
            lane=2,
            phase=RefundPhase.PRE_RELEASE,
            amount_ngwee=preview.refund_ngwee,
            payout_id="payout-1",
            lenco_reference="pay-ref",
            ledger_transaction_ids=("ledger-1",),
            breakdown={"refund_ngwee": preview.refund_ngwee},
            created=True,
        )

        record = create_lane2_return(
            FakeServiceClient(fake),
            order_item_id=ORDER_ITEM_ID,
            customer_id=CUSTOMER_ID,
            unused_declared=True,
            return_transport_ngwee=5_000,
            customer_momo=CUSTOMER_MOMO,
        )

        assert record.fee_breakdown["refund_ngwee"] == preview.refund_ngwee
        assert record.refund.amount_ngwee == preview.refund_ngwee
        assert fake.tables["returns"].rows[0]["lane"] == 2
        mock_execute.assert_called_once()
        assert mock_execute.call_args.kwargs["lane"] == 2
        assert mock_execute.call_args.kwargs["return_transport_ngwee"] == 5_000

    def test_create_requires_unused_declaration(self) -> None:
        fake = FakeSupabaseClient()
        _seed_eligible_order(
            fake,
            delivered_at=datetime.now(tz=UTC) - timedelta(hours=12),
        )
        with pytest.raises(AppError) as exc:
            create_lane2_return(
                FakeServiceClient(fake),
                order_item_id=ORDER_ITEM_ID,
                customer_id=CUSTOMER_ID,
                unused_declared=False,
                customer_momo=CUSTOMER_MOMO,
            )
        assert exc.value.code == "validation_error"
