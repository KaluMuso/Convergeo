"""Unit tests for COD release fail-closed / heal / uncollected-refund block."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from app.errors import AppError
from app.services.escrow.order_money_gate import OrderMoneyGateError
from app.services.escrow.release_accounting import (
    ReleaseAccountingAmounts,
    ReleaseAccountingError,
)
from app.services.payments.cod import CodError, confirm_cod_collection
from app.services.refunds.execute import execute_refund


def test_confirm_cod_collection_blocks_when_gate_refunded() -> None:
    ctx = MagicMock()
    ctx.cod = True
    ctx.status = "delivered"
    ctx.collectable_ngwee = 100_000
    ctx.commission_snapshot = {"lines": [{"rate_bps": 800, "line_total_ngwee": 100_000}]}
    ctx.vendor_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

    with (
        patch("app.services.payments.cod._load_cod_order", return_value=ctx),
        patch("app.services.payments.cod._assert_cod_order"),
        patch(
            "app.services.payments.cod._fetch_transaction_by_idempotency_key",
            return_value=None,
        ),
        patch(
            "app.services.payments.cod.release_blocked_reason",
            create=True,
            return_value=None,
        ),
        patch(
            "app.services.escrow.release_accounting.release_blocked_reason",
            return_value=None,
        ),
        patch(
            "app.services.escrow.release_accounting.compute_release_amounts",
            return_value=ReleaseAccountingAmounts(
                order_id="order-1",
                gross_ngwee=100_000,
                commission_ngwee=8_000,
                net_ngwee=92_000,
            ),
        ),
        patch(
            "app.services.escrow.order_money_gate.claim_release_gate",
            side_effect=OrderMoneyGateError("order_refunded"),
        ),
        patch("app.services.payments.cod.post_transaction") as post,
    ):
        with pytest.raises(CodError) as exc_info:
            confirm_cod_collection(
                order_id="11111111-1111-1111-1111-111111111111",
                actor_id="22222222-2222-2222-2222-222222222222",
                note="collect",
            )
    assert exc_info.value.code == "release_blocked"
    assert exc_info.value.details == {"reason": "order_refunded"}
    post.assert_not_called()


def test_confirm_cod_collection_blocks_invalid_snapshot() -> None:
    ctx = MagicMock()
    ctx.cod = True
    ctx.status = "delivered"
    ctx.collectable_ngwee = 100_000
    ctx.commission_snapshot = {}
    ctx.vendor_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

    with (
        patch("app.services.payments.cod._load_cod_order", return_value=ctx),
        patch("app.services.payments.cod._assert_cod_order"),
        patch(
            "app.services.payments.cod._fetch_transaction_by_idempotency_key",
            return_value=None,
        ),
        patch(
            "app.services.escrow.release_accounting.release_blocked_reason",
            return_value=None,
        ),
        patch(
            "app.services.escrow.release_accounting.compute_release_amounts",
            side_effect=ReleaseAccountingError("invalid_commission_snapshot"),
        ),
        patch("app.services.payments.cod.post_transaction") as post,
    ):
        with pytest.raises(CodError) as exc_info:
            confirm_cod_collection(
                order_id="11111111-1111-1111-1111-111111111111",
                actor_id="22222222-2222-2222-2222-222222222222",
                note="collect",
            )
    assert exc_info.value.code == "invalid_commission_snapshot"
    post.assert_not_called()


def test_execute_refund_blocks_uncollected_cod() -> None:
    service = MagicMock()
    with (
        patch(
            "app.services.refunds.execute._find_existing_refund",
            return_value=None,
        ),
        patch(
            "app.services.refunds.execute._fetch_order",
            return_value={
                "id": "11111111-1111-1111-1111-111111111111",
                "vendor_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "delivery_fee_ngwee": 0,
                "status": "delivered",
                "cod": True,
            },
        ),
        patch(
            "app.services.refunds.execute._order_item_total_ngwee",
            return_value=50_000,
        ),
        patch(
            "app.services.refunds.execute._cod_cash_collected",
            return_value=False,
        ),
        patch("app.services.refunds.execute.decide_refund_phase_under_gate") as gate,
    ):
        with pytest.raises(AppError) as exc_info:
            execute_refund(
                service_client=service,
                order_id="11111111-1111-1111-1111-111111111111",
                lane=1,
                customer_momo="0961111111",
            )
    assert exc_info.value.code == "cod_not_collected"
    gate.assert_not_called()
