"""Shared helpers for prepaid settlement tests."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from app.services.payments.settlement import PrepaidSettlementResult


@pytest.fixture(autouse=True)
def noop_prepaid_settlement_unless_marked(
    request: pytest.FixtureRequest,
) -> Generator[None, None, None]:
    """Fake-client payment tests skip ledger unless ``@pytest.mark.prepaid_settlement_db``."""
    if request.node.get_closest_marker("prepaid_settlement_db"):
        yield
        return

    def _noop(
        _service_client: object,
        *,
        payment_id: str,
        checkout_group_id: str,
        amount_ngwee: int,
    ) -> PrepaidSettlementResult:
        _ = checkout_group_id
        return PrepaidSettlementResult(
            payment_id=payment_id,
            transaction_id="mock-settlement-txn",
            amount_ngwee=amount_ngwee,
            created=True,
        )

    request.getfixturevalue("monkeypatch").setattr(
        "app.services.payments.settlement.settle_prepaid_collection",
        _noop,
    )
    yield
