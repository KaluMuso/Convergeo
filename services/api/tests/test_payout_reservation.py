"""Unit tests for cross-worker payout reservation (advisory lock + balance check)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from app.errors import AppError
from app.services.db import SqlResult
from app.services.payouts.reservation import reserve_payout_row

PAYOUT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
VENDOR_ID = "11111111-2222-3333-4444-555555555555"


def test_reserve_payout_row_success() -> None:
    with patch(
        "app.services.payouts.reservation.run_sql_script",
        return_value=SqlResult(ok=True, rows=[]),
    ) as mock_run:
        reserve_payout_row(
            payout_id=PAYOUT_ID,
            vendor_id=VENDOR_ID,
            amount_ngwee=50_000,
            rail="mtn",
            lenco_reference="pay-test-1",
            resolve_snapshot={"matched": True},
            status="processing",
        )
    assert mock_run.called
    script = mock_run.call_args[0][0]
    assert "pg_advisory_xact_lock" in script
    assert "vendor_payout_reserve:" in script
    assert "insufficient_released_balance" in script
    assert PAYOUT_ID in script
    assert VENDOR_ID in script


def test_reserve_payout_row_maps_insufficient_balance() -> None:
    with patch(
        "app.services.payouts.reservation.run_sql_script",
        return_value=SqlResult(ok=False, rows=[], error="insufficient_released_balance"),
    ):
        with pytest.raises(AppError) as exc_info:
            reserve_payout_row(
                payout_id=PAYOUT_ID,
                vendor_id=VENDOR_ID,
                amount_ngwee=50_000,
                rail="mtn",
                lenco_reference="pay-test-2",
                resolve_snapshot={},
            )
    assert exc_info.value.code == "insufficient_released_balance"
    assert exc_info.value.http_status == 409


def test_reserve_payout_row_rejects_non_positive_amount() -> None:
    with pytest.raises(AppError) as exc_info:
        reserve_payout_row(
            payout_id=PAYOUT_ID,
            vendor_id=VENDOR_ID,
            amount_ngwee=0,
            rail="mtn",
            lenco_reference="pay-test-3",
            resolve_snapshot={},
        )
    assert exc_info.value.code == "invalid_amount"
