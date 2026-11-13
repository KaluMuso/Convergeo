"""Partial item PRE_RELEASE refund must leave remainder escrow releasable to vendor."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from app.services.db import SqlResult
from app.services.escrow.order_money_gate import (
    OrderMoneyGateError,
    claim_release_gate,
)
from app.services.escrow.release import _OrderContext, evaluate_and_release
from app.services.escrow.release_accounting import (
    OrderReleaseLedgerSummary,
    order_is_refund_blocked,
    scale_commission_snapshot_for_gross,
)

ORDER_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
VENDOR_ID = "11111111-1111-1111-1111-111111111111"


def _snapshot(*, line_a: int = 100_000, line_b: int = 100_000) -> dict[str, Any]:
    return {
        "lines": [
            {
                "listing_id": "22222222-2222-2222-2222-222222222222",
                "category_key": "electronics",
                "rate_bps": 800,
                "qty": 1,
                "unit_price_ngwee": line_a,
                "line_total_ngwee": line_a,
                "wholesale": False,
            },
            {
                "listing_id": "33333333-3333-3333-3333-333333333333",
                "category_key": "electronics",
                "rate_bps": 800,
                "qty": 1,
                "unit_price_ngwee": line_b,
                "line_total_ngwee": line_b,
                "wholesale": False,
            },
        ]
    }


def test_scale_snapshot_absorbs_remainder_on_last_line() -> None:
    scaled = scale_commission_snapshot_for_gross(
        _snapshot(),
        target_gross_ngwee=100_000,
        original_gross_ngwee=205_000,
    )
    totals = [int(line["line_total_ngwee"]) for line in scaled["lines"]]
    assert sum(totals) == 100_000
    assert totals[0] == (100_000 * 100_000) // 205_000


def test_full_refund_still_blocks_release() -> None:
    """Refund row + no remainder (full drain or no ledger yet) stays blocked."""
    with (
        patch(
            "app.services.escrow.release_accounting.order_has_active_refund",
            return_value=True,
        ),
        patch(
            "app.services.escrow.release_accounting.order_has_refund_ledger",
            return_value=True,
        ),
        patch(
            "app.services.escrow.release_accounting.summarize_order_release_ledger",
            return_value=OrderReleaseLedgerSummary(
                order_id=ORDER_ID,
                charge_received_ngwee=205_000,
                commission_captured_ngwee=0,
                vendor_released_ngwee=0,
                refund_drained_ngwee=205_000,
            ),
        ),
    ):
        assert order_is_refund_blocked(ORDER_ID) is True


def test_partial_refund_remainder_does_not_block() -> None:
    with (
        patch(
            "app.services.escrow.release_accounting.order_has_active_refund",
            return_value=True,
        ),
        patch(
            "app.services.escrow.release_accounting.order_has_refund_ledger",
            return_value=True,
        ),
        patch(
            "app.services.escrow.release_accounting.summarize_order_release_ledger",
            return_value=OrderReleaseLedgerSummary(
                order_id=ORDER_ID,
                charge_received_ngwee=205_000,
                commission_captured_ngwee=0,
                vendor_released_ngwee=0,
                refund_drained_ngwee=105_000,
            ),
        ),
    ):
        assert order_is_refund_blocked(ORDER_ID) is False


def test_refund_row_without_ledger_still_blocks() -> None:
    """In-flight refund before ledger drain must not unlock full-order release."""
    with (
        patch(
            "app.services.escrow.release_accounting.order_has_active_refund",
            return_value=True,
        ),
        patch(
            "app.services.escrow.release_accounting.order_has_refund_ledger",
            return_value=False,
        ),
        patch(
            "app.services.escrow.release_accounting.summarize_order_release_ledger",
            return_value=OrderReleaseLedgerSummary(
                order_id=ORDER_ID,
                charge_received_ngwee=205_000,
                commission_captured_ngwee=0,
                vendor_released_ngwee=0,
                refund_drained_ngwee=0,
            ),
        ),
    ):
        assert order_is_refund_blocked(ORDER_ID) is True


def test_claim_release_gate_promotes_refund_remainder() -> None:
    with patch(
        "app.services.escrow.order_money_gate.run_sql_script",
        return_value=SqlResult(ok=True, rows=["ok"]),
    ) as mock_run:
        claim_release_gate(ORDER_ID)
    script = mock_run.call_args[0][0]
    assert "remainder_ok" in script
    assert "SET gate = 'release'" in script
    assert "pg_advisory_xact_lock" in script


def test_claim_release_gate_still_blocks_full_refund() -> None:
    with patch(
        "app.services.escrow.order_money_gate.run_sql_script",
        return_value=SqlResult(ok=True, rows=["order_refunded"]),
    ):
        with pytest.raises(OrderMoneyGateError) as exc_info:
            claim_release_gate(ORDER_ID)
    assert exc_info.value.code == "order_refunded"


def test_evaluate_and_release_caps_gross_to_remainder() -> None:
    now = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
    context = _OrderContext(
        order_id=ORDER_ID,
        status="delivered",
        vendor_id=VENDOR_ID,
        checkout_group_id="c1000000-0000-0000-0000-000000000099",
        cod=False,
        commission_snapshot=_snapshot(),
        gross_ngwee=205_000,
        has_open_dispute=False,
        already_released=False,
        buyer_confirmed=True,
        delivered_at=now - timedelta(hours=1),
        shipped_at=now - timedelta(hours=2),
        has_escrow_evidence=True,
    )
    captured_gross: int | None = None
    captured_snapshot: dict[str, Any] | None = None

    def fake_compute(
        *,
        order_id: str,
        gross_ngwee: int,
        commission_snapshot: dict[str, Any],
    ) -> MagicMock:
        nonlocal captured_gross, captured_snapshot
        _ = order_id
        captured_gross = gross_ngwee
        captured_snapshot = commission_snapshot
        result = MagicMock()
        result.net_ngwee = 92_000
        result.commission_ngwee = 8_000
        result.gross_ngwee = gross_ngwee
        return result

    with (
        patch(
            "app.services.escrow.release._load_order_context",
            return_value=context,
        ),
        patch(
            "app.services.escrow.release.release_blocked_reason",
            return_value=None,
        ),
        patch(
            "app.services.escrow.release.order_has_refund_remainder",
            return_value=True,
        ),
        patch(
            "app.services.escrow.release.remaining_escrow_ngwee",
            return_value=100_000,
        ),
        patch(
            "app.services.escrow.release.compute_release_amounts",
            side_effect=fake_compute,
        ),
        patch("app.services.escrow.release.claim_release_gate"),
        patch("app.services.escrow.release.capture_order_commission") as capture,
        patch(
            "app.services.escrow.release._post_release",
            return_value="txn-1",
        ) as post_release,
    ):
        result = evaluate_and_release(MagicMock(), ORDER_ID, now=now)

    assert result.outcome == "released"
    assert captured_gross == 100_000
    assert captured_snapshot is not None
    lines = captured_snapshot["lines"]
    assert isinstance(lines, list)
    assert sum(int(line["line_total_ngwee"]) for line in lines) == 100_000
    capture.assert_called_once()
    assert capture.call_args.kwargs["commission_snapshot"] is captured_snapshot
    post_release.assert_called_once_with(
        order_id=ORDER_ID,
        vendor_id=VENDOR_ID,
        net_ngwee=92_000,
    )


@pytest.mark.parametrize(
    ("refunded_fee", "remaining", "expected_fee_capture", "expected_gross"),
    [
        # Lane-1 item return already refunded item + fee: the fee is gone from
        # escrow, so nothing is captured and the kept items reach the vendor.
        (4_500, 105_000, 0, 105_000),
        # No fee refunded (e.g. lane 2): the fee is still in escrow for the platform.
        (0, 109_500, 4_500, 105_000),
    ],
)
def test_release_after_partial_refund_never_captures_a_refunded_fee(
    refunded_fee: int, remaining: int, expected_fee_capture: int, expected_gross: int
) -> None:
    now = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
    context = _OrderContext(
        order_id=ORDER_ID,
        status="delivered",
        vendor_id=VENDOR_ID,
        checkout_group_id="c1000000-0000-0000-0000-000000000099",
        cod=False,
        commission_snapshot=_snapshot(),
        gross_ngwee=205_000,
        has_open_dispute=False,
        already_released=False,
        buyer_confirmed=True,
        delivered_at=now - timedelta(hours=1),
        shipped_at=now - timedelta(hours=2),
        has_escrow_evidence=True,
        delivery_fee_ngwee=4_500,
    )
    captured: dict[str, int] = {}

    def fake_compute(
        *, order_id: str, gross_ngwee: int, commission_snapshot: dict[str, Any]
    ) -> MagicMock:
        _ = (order_id, commission_snapshot)
        captured["gross"] = gross_ngwee
        result = MagicMock()
        result.net_ngwee = gross_ngwee - 1_000
        result.commission_ngwee = 1_000
        result.gross_ngwee = gross_ngwee
        return result

    with (
        patch("app.services.escrow.release._load_order_context", return_value=context),
        patch("app.services.escrow.release.release_blocked_reason", return_value=None),
        patch("app.services.escrow.release.delivery_fee_already_captured", return_value=False),
        patch("app.services.escrow.release.delivery_fee_refunded_ngwee", return_value=refunded_fee),
        patch("app.services.escrow.release.order_has_refund_remainder", return_value=True),
        patch("app.services.escrow.release.remaining_escrow_ngwee", return_value=remaining),
        patch("app.services.escrow.release.compute_release_amounts", side_effect=fake_compute),
        patch("app.services.escrow.release.claim_release_gate"),
        patch("app.services.escrow.release.capture_order_commission"),
        patch("app.services.escrow.release.capture_order_delivery_fee") as capture_fee,
        patch("app.services.escrow.release._post_release", return_value="txn-1"),
    ):
        result = evaluate_and_release(MagicMock(), ORDER_ID, now=now)

    assert result.outcome == "released"
    assert captured["gross"] == expected_gross
    capture_fee.assert_called_once_with(order_id=ORDER_ID, delivery_fee_ngwee=expected_fee_capture)
