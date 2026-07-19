"""Unit tests for D17 order escrow-drain gate (refund vs release mutex)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from app.services.db import SqlResult
from app.services.escrow.order_money_gate import (
    OrderMoneyGateError,
    claim_release_gate,
    decide_refund_phase_under_gate,
)

ORDER_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_claim_release_gate_ok() -> None:
    with patch(
        "app.services.escrow.order_money_gate.run_sql_script",
        return_value=SqlResult(ok=True, rows=["ok"]),
    ) as mock_run:
        claim_release_gate(ORDER_ID)
    script = mock_run.call_args[0][0]
    assert "pg_advisory_xact_lock" in script
    assert "order_escrow:" in script
    assert "order_money_gates" in script


def test_claim_release_gate_blocks_refund_owner() -> None:
    with patch(
        "app.services.escrow.order_money_gate.run_sql_script",
        return_value=SqlResult(ok=True, rows=["order_refunded"]),
    ):
        with pytest.raises(OrderMoneyGateError) as exc_info:
            claim_release_gate(ORDER_ID)
    assert exc_info.value.code == "order_refunded"


def test_decide_refund_phase_pre_release() -> None:
    with patch(
        "app.services.escrow.order_money_gate.run_sql_script",
        return_value=SqlResult(ok=True, rows=["phase_pre_release"]),
    ):
        decision = decide_refund_phase_under_gate(ORDER_ID)
    assert decision.phase == "pre_release"
    assert decision.claimed is True


def test_decide_refund_phase_post_release() -> None:
    with patch(
        "app.services.escrow.order_money_gate.run_sql_script",
        return_value=SqlResult(ok=True, rows=["phase_post_release"]),
    ):
        decision = decide_refund_phase_under_gate(ORDER_ID)
    assert decision.phase == "post_release"
    assert decision.claimed is False


def test_decide_refund_phase_release_in_progress() -> None:
    with patch(
        "app.services.escrow.order_money_gate.run_sql_script",
        return_value=SqlResult(ok=True, rows=["release_in_progress"]),
    ):
        with pytest.raises(OrderMoneyGateError) as exc_info:
            decide_refund_phase_under_gate(ORDER_ID)
    assert exc_info.value.code == "release_in_progress"


def test_evaluate_and_release_blocks_when_gate_refunded() -> None:
    from datetime import UTC, datetime, timedelta
    from unittest.mock import MagicMock

    from app.services.escrow.release import _OrderContext, evaluate_and_release

    now = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
    context = _OrderContext(
        order_id=ORDER_ID,
        status="delivered",
        vendor_id="11111111-1111-1111-1111-111111111111",
        cod=False,
        commission_snapshot={
            "lines": [
                {
                    "listing_id": "22222222-2222-2222-2222-222222222222",
                    "category_key": "electronics",
                    "rate_bps": 800,
                    "qty": 1,
                    "unit_price_ngwee": 200_000,
                    "line_total_ngwee": 200_000,
                    "wholesale": False,
                }
            ]
        },
        gross_ngwee=200_000,
        has_open_dispute=False,
        already_released=False,
        buyer_confirmed=True,
        delivered_at=now - timedelta(hours=1),
        shipped_at=now - timedelta(hours=2),
    )
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
            "app.services.escrow.release.claim_release_gate",
            side_effect=OrderMoneyGateError("order_refunded"),
        ),
        patch("app.services.escrow.release.capture_order_commission") as capture,
        patch("app.services.escrow.release._post_release") as post_release,
    ):
        result = evaluate_and_release(MagicMock(), ORDER_ID, now=now)

    assert result.outcome == "not_eligible"
    assert result.reason == "order_refunded"
    capture.assert_not_called()
    post_release.assert_not_called()
