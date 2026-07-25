"""M08-P10 — refunds & clawbacks tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from app.errors import AppError
from app.services.escrow.order_money_gate import RefundGateDecision
from app.services.escrow.release_accounting import OrderReleaseLedgerSummary
from app.services.ledger.engine import PostedTransaction
from app.services.ledger.templates import LedgerTemplate
from app.services.refunds.clawback import net_clawback_across_payouts, net_clawback_from_payout
from app.services.refunds.execute import RefundPhase, execute_refund
from app.services.refunds.math import (
    DEFAULT_RESTOCKING_FEE_BPS,
    MAX_RESTOCKING_FEE_BPS,
    MIN_RESTOCKING_FEE_BPS,
    compute_lane1_refund,
    compute_lane2_refund,
    normalize_restocking_fee_bps,
    restocking_fee_ngwee,
)

ORDER_ID = "70707070-7070-7070-7070-707070707070"
VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
REFUND_ID = "a1a1a1a1-a1a1-a1a1-a1a1-a1a1a1a1a1a1a1"
CUSTOMER_MOMO = "+260971234567"


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | None = None
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

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self._pending_op = "update"
        self._payload = payload
        return self

    def execute(self) -> MagicMock:
        if self._pending_op == "insert":
            assert self._payload is not None
            row = dict(self._payload)
            self._parent.rows.append(row)
            return MagicMock(data=[row])
        if self._pending_op == "update":
            assert self._payload is not None
            for row in self._parent.rows:
                if all(row.get(col) == val for op, col, val in self._filters if op == "eq"):
                    row.update(self._payload)
            return MagicMock(data=[])
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

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).update(payload)

    def _filter_rows(self, filters: list[tuple[str, str, Any]]) -> list[dict[str, Any]]:
        result = list(self.rows)
        for op, column, value in filters:
            if op == "eq":
                result = [row for row in result if row.get(column) == value]
        return result


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "orders": FakeTable(),
            "order_items": FakeTable(),
            "refunds": FakeTable(),
            "payouts": FakeTable(),
            "ledger_transactions": FakeTable(),
            "platform_config": FakeTable(),
        }

    def table(self, name: str) -> FakeTable:
        return self.tables[name]


class FakeServiceClient:
    def __init__(self, client: FakeSupabaseClient) -> None:
        self.client = client


def _gate_decision_for_fake(
    fake: FakeSupabaseClient,
) -> Callable[[str], RefundGateDecision]:
    """DB-less stand-in for decide_refund_phase_under_gate (avoids real SQL)."""

    def _decide(order_id: str) -> RefundGateDecision:
        released = any(
            row.get("order_id") == order_id and row.get("kind") == "release_to_vendor"
            for row in fake.tables["ledger_transactions"].rows
        )
        if released:
            return RefundGateDecision(phase="post_release", claimed=False)
        return RefundGateDecision(phase="pre_release", claimed=True)

    return _decide


def _seed_order(
    fake: FakeSupabaseClient,
    *,
    item_total: int = 100_000,
    delivery_fee: int = 5_000,
    released: bool = False,
) -> None:
    fake.tables["orders"].rows.append(
        {
            "id": ORDER_ID,
            "vendor_id": VENDOR_ID,
            "delivery_fee_ngwee": delivery_fee,
            "status": "delivered",
        }
    )
    fake.tables["order_items"].rows.append(
        {
            "order_id": ORDER_ID,
            "qty": 1,
            "unit_price_ngwee": item_total,
        }
    )
    if released:
        fake.tables["ledger_transactions"].rows.append(
            {
                "id": "release-txn-1",
                "order_id": ORDER_ID,
                "kind": "release_to_vendor",
            }
        )


def _posted_txn(txn_id: str = "ledger-txn-1") -> PostedTransaction:
    return PostedTransaction(
        id=txn_id,
        kind="refund_lane1",
        idempotency_key="k",
        created=True,
    )


class TestLane2FeeMatrix:
    @pytest.mark.parametrize(
        ("bps", "item", "expected_fee"),
        [
            (MIN_RESTOCKING_FEE_BPS, 123_456, 6_172),
            (DEFAULT_RESTOCKING_FEE_BPS, 123_456, 12_345),
            (MAX_RESTOCKING_FEE_BPS, 123_456, 18_518),
            (MIN_RESTOCKING_FEE_BPS, 99, 4),
            (MAX_RESTOCKING_FEE_BPS, 10_000, 1_500),
        ],
    )
    def test_restocking_fee_ngwee_exact(self, bps: int, item: int, expected_fee: int) -> None:
        assert restocking_fee_ngwee(item_ngwee=item, restocking_fee_bps=bps) == expected_fee

    def test_lane2_refund_matrix_min_max_bps(self) -> None:
        item = 200_000
        outbound = 10_000
        transport = 5_000

        min_lane2 = compute_lane2_refund(
            item_ngwee=item,
            outbound_delivery_ngwee=outbound,
            return_transport_ngwee=transport,
            restocking_fee_bps=MIN_RESTOCKING_FEE_BPS,
        )
        assert min_lane2.restocking_fee_ngwee == 10_000
        assert min_lane2.refund_ngwee == 175_000
        assert min_lane2.escrow_release_ngwee == item

        max_lane2 = compute_lane2_refund(
            item_ngwee=item,
            outbound_delivery_ngwee=outbound,
            return_transport_ngwee=transport,
            restocking_fee_bps=MAX_RESTOCKING_FEE_BPS,
        )
        assert max_lane2.restocking_fee_ngwee == 30_000
        assert max_lane2.refund_ngwee == 155_000
        assert max_lane2.escrow_release_ngwee == item

    def test_lane2_refund_never_negative(self) -> None:
        result = compute_lane2_refund(
            item_ngwee=1_000,
            outbound_delivery_ngwee=500,
            return_transport_ngwee=400,
            restocking_fee_bps=MAX_RESTOCKING_FEE_BPS,
        )
        assert result.refund_ngwee == 0
        assert result.escrow_release_ngwee == 1_050

    def test_normalize_restocking_clamps(self) -> None:
        assert normalize_restocking_fee_bps(None) == DEFAULT_RESTOCKING_FEE_BPS
        assert normalize_restocking_fee_bps(100) == MIN_RESTOCKING_FEE_BPS
        assert normalize_restocking_fee_bps(9_999) == MAX_RESTOCKING_FEE_BPS


class TestLane1Math:
    def test_full_refund_includes_delivery(self) -> None:
        result = compute_lane1_refund(item_ngwee=80_000, delivery_fee_ngwee=12_000)
        assert result.refund_ngwee == 92_000


class TestClawbackNetting:
    def test_partial_clawback_across_three_payouts(self) -> None:
        steps = net_clawback_across_payouts(
            payout_amounts_ngwee=(40_000, 30_000, 50_000),
            initial_clawback_outstanding_ngwee=90_000,
        )
        assert len(steps) == 3
        assert steps[0].clawback_applied_ngwee == 40_000
        assert steps[0].net_payout_ngwee == 0
        assert steps[1].clawback_applied_ngwee == 30_000
        assert steps[1].net_payout_ngwee == 0
        assert steps[2].clawback_applied_ngwee == 20_000
        assert steps[2].net_payout_ngwee == 30_000
        assert steps[2].clawback_outstanding_after_ngwee == 0

    def test_no_over_claw(self) -> None:
        step = net_clawback_from_payout(
            gross_payout_ngwee=25_000,
            clawback_outstanding_ngwee=10_000,
        )
        assert step.clawback_applied_ngwee == 10_000
        assert step.net_payout_ngwee == 15_000
        assert step.clawback_outstanding_after_ngwee == 0


class TestExecuteRefundPaths:
    @patch("app.services.refunds.execute.post_transaction")
    def test_pre_release_lane1_posts_escrow_refund(
        self,
        mock_post: MagicMock,
    ) -> None:
        mock_post.return_value = _posted_txn("pre-lane1")
        fake = FakeSupabaseClient()
        _seed_order(fake, released=False)
        service = FakeServiceClient(fake)

        with patch(
            "app.services.refunds.execute.decide_refund_phase_under_gate",
            side_effect=_gate_decision_for_fake(fake),
        ):
            result = execute_refund(
                service_client=service,
                order_id=ORDER_ID,
                lane=1,
                customer_momo=CUSTOMER_MOMO,
            )

        assert result.created is True
        assert result.phase == RefundPhase.PRE_RELEASE
        assert result.amount_ngwee == 105_000
        mock_post.assert_called_once()
        call = mock_post.call_args.kwargs
        assert call["template"] == LedgerTemplate.REFUND_LANE1
        assert call["refund_ngwee"] == 105_000
        assert len(fake.tables["payouts"].rows) == 1
        assert fake.tables["refunds"].rows[0]["status"] == "completed"

    @patch("app.services.refunds.execute.post_transaction")
    def test_pre_release_refund_exceeding_remaining_escrow_blocked(
        self,
        mock_post: MagicMock,
    ) -> None:
        """Stacked PRE_RELEASE drains cannot exceed remaining escrow (money-loss guard).

        When charge legs are order-linked, the lane-1 full refund (105_000) is
        capped against remaining escrow. Prior drains here leave only 49_000, so
        the refund is refused BEFORE any payout/ledger drain — the sole guard
        stopping stacked multi-item returns from paying out more than the buyer
        put in. Previously every PRE_RELEASE test skipped this branch by letting
        charge_received read as 0 (see test_pre_release_lane1 above).
        """
        fake = FakeSupabaseClient()
        _seed_order(fake, released=False)
        service = FakeServiceClient(fake)
        # 105_000 charge − 12_000 commission − 0 released − 44_000 drained = 49_000.
        depleted = OrderReleaseLedgerSummary(
            order_id=ORDER_ID,
            charge_received_ngwee=105_000,
            commission_captured_ngwee=12_000,
            vendor_released_ngwee=0,
            refund_drained_ngwee=44_000,
        )

        with (
            patch(
                "app.services.refunds.execute.decide_refund_phase_under_gate",
                side_effect=_gate_decision_for_fake(fake),
            ),
            patch(
                "app.services.refunds.execute.summarize_order_release_ledger",
                return_value=depleted,
            ),
        ):
            with pytest.raises(AppError) as exc:
                execute_refund(
                    service_client=service,
                    order_id=ORDER_ID,
                    lane=1,
                    customer_momo=CUSTOMER_MOMO,
                )

        assert exc.value.code == "refund_exceeds_escrow"
        assert exc.value.details["remaining_escrow_ngwee"] == 49_000
        assert exc.value.details["refund_ngwee"] == 105_000
        mock_post.assert_not_called()
        assert fake.tables["refunds"].rows == []

    @patch("app.services.refunds.execute.post_transaction")
    def test_pre_release_refund_within_escrow_proceeds(
        self,
        mock_post: MagicMock,
    ) -> None:
        """The escrow cap must NOT false-block when remaining escrow covers the refund.

        Exercises the same charge_received > 0 branch as the block test, but with
        remaining escrow (150_000) >= refund (105_000): the refund proceeds and
        posts normally, proving the cap guards over-draining without penalising
        legitimate order-linked refunds.
        """
        mock_post.return_value = _posted_txn("pre-lane1-capped-ok")
        fake = FakeSupabaseClient()
        _seed_order(fake, released=False)
        service = FakeServiceClient(fake)
        sufficient = OrderReleaseLedgerSummary(
            order_id=ORDER_ID,
            charge_received_ngwee=150_000,
            commission_captured_ngwee=0,
            vendor_released_ngwee=0,
            refund_drained_ngwee=0,
        )

        with (
            patch(
                "app.services.refunds.execute.decide_refund_phase_under_gate",
                side_effect=_gate_decision_for_fake(fake),
            ),
            patch(
                "app.services.refunds.execute.summarize_order_release_ledger",
                return_value=sufficient,
            ),
        ):
            result = execute_refund(
                service_client=service,
                order_id=ORDER_ID,
                lane=1,
                customer_momo=CUSTOMER_MOMO,
            )

        assert result.created is True
        assert result.phase == RefundPhase.PRE_RELEASE
        assert result.amount_ngwee == 105_000
        mock_post.assert_called_once()
        assert fake.tables["refunds"].rows[0]["status"] == "completed"

    @patch("app.services.refunds.execute.post_transaction")
    def test_post_release_lane1_posts_clawback(
        self,
        mock_post: MagicMock,
    ) -> None:
        mock_post.return_value = _posted_txn("post-clawback")
        fake = FakeSupabaseClient()
        _seed_order(fake, released=True)
        service = FakeServiceClient(fake)
        full_release = OrderReleaseLedgerSummary(
            order_id=ORDER_ID,
            charge_received_ngwee=105_000,
            commission_captured_ngwee=0,
            vendor_released_ngwee=105_000,
            refund_drained_ngwee=0,
        )

        with (
            patch(
                "app.services.refunds.execute.decide_refund_phase_under_gate",
                side_effect=_gate_decision_for_fake(fake),
            ),
            patch(
                "app.services.refunds.execute.summarize_order_release_ledger",
                return_value=full_release,
            ),
        ):
            result = execute_refund(
                service_client=service,
                order_id=ORDER_ID,
                lane=1,
                customer_momo=CUSTOMER_MOMO,
            )

        assert result.phase == RefundPhase.POST_RELEASE
        mock_post.assert_called_once()
        call = mock_post.call_args.kwargs
        assert call["template"] == LedgerTemplate.CLAWBACK
        assert call["clawback_ngwee"] == 105_000

    @patch("app.services.refunds.execute.post_transaction")
    def test_partial_event_release_blocks_full_clawback(
        self,
        mock_post: MagicMock,
    ) -> None:
        """Phase-1 event release must not MoMo-refund while phase-2 escrow remains."""
        fake = FakeSupabaseClient()
        _seed_order(fake, released=True)
        service = FakeServiceClient(fake)
        partial = OrderReleaseLedgerSummary(
            order_id=ORDER_ID,
            charge_received_ngwee=100_000,
            commission_captured_ngwee=12_000,
            vendor_released_ngwee=44_000,  # phase-1 half of net
            refund_drained_ngwee=0,
        )

        with (
            patch(
                "app.services.refunds.execute.decide_refund_phase_under_gate",
                side_effect=_gate_decision_for_fake(fake),
            ),
            patch(
                "app.services.refunds.execute.summarize_order_release_ledger",
                return_value=partial,
            ),
        ):
            with pytest.raises(AppError) as exc:
                execute_refund(
                    service_client=service,
                    order_id=ORDER_ID,
                    lane=1,
                    customer_momo=CUSTOMER_MOMO,
                )

        assert exc.value.code == "partial_release_refund_blocked"
        assert exc.value.details["remaining_escrow_ngwee"] == 44_000
        mock_post.assert_not_called()
        assert fake.tables["refunds"].rows == []

    @patch("app.services.refunds.execute.post_transaction")
    def test_pre_release_lane2_posts_lane2_template(
        self,
        mock_post: MagicMock,
    ) -> None:
        mock_post.return_value = _posted_txn("pre-lane2")
        fake = FakeSupabaseClient()
        _seed_order(fake, item_total=200_000, delivery_fee=10_000, released=False)
        fake.tables["platform_config"].rows.append(
            {"key": "restocking_fee_bps", "value": DEFAULT_RESTOCKING_FEE_BPS}
        )
        service = FakeServiceClient(fake)

        with patch(
            "app.services.refunds.execute.decide_refund_phase_under_gate",
            side_effect=_gate_decision_for_fake(fake),
        ):
            result = execute_refund(
                service_client=service,
                order_id=ORDER_ID,
                lane=2,
                return_transport_ngwee=5_000,
                customer_momo=CUSTOMER_MOMO,
            )

        assert result.phase == RefundPhase.PRE_RELEASE
        assert result.amount_ngwee == 165_000
        call = mock_post.call_args.kwargs
        assert call["template"] == LedgerTemplate.REFUND_LANE2
        assert call["refund_to_customer_ngwee"] == 165_000
        assert call["restocking_fee_ngwee"] == 20_000
        assert call["vendor_retained_ngwee"] == 15_000

    @patch("app.services.refunds.execute.post_transaction")
    def test_double_execution_guard_returns_existing(
        self,
        mock_post: MagicMock,
    ) -> None:
        mock_post.return_value = _posted_txn()
        fake = FakeSupabaseClient()
        _seed_order(fake, released=False)
        source_key = f"refund-order-{ORDER_ID}"
        fake.tables["refunds"].rows.append(
            {
                "id": REFUND_ID,
                "order_id": ORDER_ID,
                "source_key": source_key,
                "lane": 1,
                "amount_ngwee": 105_000,
                "status": "completed",
                "payout_ref": "payout-1",
                "breakdown": {
                    "phase": "pre_release",
                    "idempotency_key": source_key,
                    "lenco_reference": "rfd-existing",
                    "ledger_transaction_ids": ["txn-1"],
                },
            }
        )
        service = FakeServiceClient(fake)

        result = execute_refund(
            service_client=service,
            order_id=ORDER_ID,
            lane=1,
            customer_momo=CUSTOMER_MOMO,
        )

        assert result.created is False
        assert result.refund_id == REFUND_ID
        mock_post.assert_not_called()
        assert len(fake.tables["payouts"].rows) == 0

    @patch("app.services.refunds.execute.post_transaction")
    def test_zero_refund_rejected(self, mock_post: MagicMock) -> None:
        fake = FakeSupabaseClient()
        _seed_order(fake, item_total=1_000, delivery_fee=500, released=False)
        service = FakeServiceClient(fake)

        with pytest.raises(AppError) as exc:
            execute_refund(
                service_client=service,
                order_id=ORDER_ID,
                lane=2,
                return_transport_ngwee=400,
                customer_momo=CUSTOMER_MOMO,
            )
        assert exc.value.code == "refund_amount_zero"
        mock_post.assert_not_called()
