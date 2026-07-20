"""Unit tests for checkout-scoped prepaid settlement gate (no DB required)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.db import SqlResult
from app.services.payments.settlement import (
    prepaid_collection_idempotency_key,
    settle_prepaid_collection,
)


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

    def fake_run(script: str) -> SqlResult:
        captured.append(script)
        return SqlResult(ok=True, rows=["none"])

    posted = MagicMock()
    posted.id = "t1000000-0000-0000-0000-000000000099"
    posted.created = True

    with (
        patch(
            "app.services.payments.settlement.run_sql_script",
            side_effect=fake_run,
        ),
        patch(
            "app.services.payments.settlement.post_transaction",
            return_value=posted,
        ) as mock_post,
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
    mock_post.assert_called_once()
    assert mock_post.call_args.kwargs["idempotency_key"] == (
        f"prepaid-charge-checkout-{checkout_id}"
    )


def test_existing_sibling_charge_skips_post() -> None:
    checkout_id = "c1000000-0000-0000-0000-000000000002"
    payment_a = "a1000000-0000-0000-0000-000000000001"
    payment_b = "b1000000-0000-0000-0000-000000000002"
    txn_id = "t1000000-0000-0000-0000-000000000099"

    with (
        patch(
            "app.services.payments.settlement.run_sql_script",
            return_value=SqlResult(ok=True, rows=[f"{payment_a}|{txn_id}"]),
        ),
        patch("app.services.payments.settlement.post_transaction") as mock_post,
    ):
        result = settle_prepaid_collection(
            MagicMock(),
            payment_id=payment_b,
            checkout_group_id=checkout_id,
            amount_ngwee=25_000,
        )

    mock_post.assert_not_called()
    assert result.created is False
    assert result.skipped_sibling is True
    assert result.transaction_id == txn_id
