from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from app.errors import AppError
from app.services.orders.create import _fetch_checkout_session, _fetch_existing_by_idempotency_key


def test_missing_postgrest_single_allows_first_order_and_reports_missing_session() -> None:
    client = MagicMock()
    (
        client.table.return_value.select.return_value.eq.return_value.eq.return_value
        .maybe_single.return_value.execute
    ).return_value = None

    assert _fetch_existing_by_idempotency_key(
        client, idempotency_key="new-order", customer_id="customer"
    ) is None
    with pytest.raises(AppError) as exc:
        _fetch_checkout_session(client, session_id="missing", customer_id="customer")
    assert exc.value.code == "checkout.session_not_found"
