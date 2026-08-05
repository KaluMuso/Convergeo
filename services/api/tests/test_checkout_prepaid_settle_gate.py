"""Unit tests for checkout-scoped prepaid settlement gate (no DB required)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.db import SqlResult
from app.services.payments.fulfillment import EscrowFulfillmentResult
from app.services.payments.settlement import (
    prepaid_collection_idempotency_key,
    settle_prepaid_collection,
)


def _mock_settlement_sql(script: str, *, payment_id: str) -> SqlResult:
    if "pg_advisory_xact_lock" in script:
        return SqlResult(ok=True, rows=["none"])
    if "WHERE id = " in script and "payment_id::text" in script:
        return SqlResult(ok=True, rows=[payment_id])
    return SqlResult(ok=True, rows=["none"])


def test_idempotency_key_is_checkout_scoped() -> None:
    checkout_id = "c1000000-0000-0000-0000-000000000002"
    assert (
        prepaid_collection_idempotency_key(checkout_id)
        == f"prepaid-charge-checkout-{checkout_id}"
    )


def test_lookup_script_uses_checkout_advisory_lock() -> None:
    checkout_id = "c1000000-0000-0000-0000-000000000002"
    payment_id = "a1000000-0000-0000-0000-000000000001"
    captured: list[str] = []

    txn_id = "a1000000-0000-4000-8000-000000000099"
    fulfilled = EscrowFulfillmentResult(
        checkout_group_id=checkout_id,
        payment_id=payment_id,
        transaction_ids=(txn_id,),
        total_ngwee=25_000,
        created_count=1,
    )

    def fake_run_with_owner(script: str) -> SqlResult:
        captured.append(script)
        return _mock_settlement_sql(script, payment_id=payment_id)

    with (
        patch(
            "app.services.payments.settlement.run_sql_script",
            side_effect=fake_run_with_owner,
        ),
        patch(
            "app.services.payments.settlement.fulfill_prepaid_checkout_escrow",
            return_value=fulfilled,
        ) as mock_fulfill,
    ):
        result = settle_prepaid_collection(
            MagicMock(),
            payment_id=payment_id,
            checkout_group_id=checkout_id,
            amount_ngwee=25_000,
        )

    assert result.created is True
    assert result.skipped_sibling is False
    assert "pg_advisory_xact_lock" in captured[0]
    assert "checkout_prepaid:" in captured[0]
    mock_fulfill.assert_called_once()
    assert mock_fulfill.call_args.kwargs["payment_id"] == payment_id


def test_existing_sibling_charge_skips_post() -> None:
    checkout_id = "c1000000-0000-0000-0000-000000000002"
    payment_a = "a1000000-0000-0000-0000-000000000001"
    payment_b = "b1000000-0000-0000-0000-000000000002"
    txn_id = "a1000000-0000-4000-8000-000000000099"

    with (
        patch(
            "app.services.payments.settlement.run_sql_script",
            return_value=SqlResult(ok=True, rows=[f"{payment_a}|{txn_id}"]),
        ),
        patch(
            "app.services.payments.settlement.fulfill_prepaid_checkout_escrow",
        ) as mock_fulfill,
    ):
        result = settle_prepaid_collection(
            MagicMock(),
            payment_id=payment_b,
            checkout_group_id=checkout_id,
            amount_ngwee=25_000,
        )

    mock_fulfill.assert_not_called()
    assert result.created is False
    assert result.skipped_sibling is True
    assert result.transaction_id == txn_id
