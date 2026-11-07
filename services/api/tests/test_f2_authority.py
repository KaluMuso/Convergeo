"""Regression probes for F2 authority boundaries (not provider acceptance)."""

from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest
from app.errors import AppError
from app.routers import job_completion as jobs
from app.routers import payments_card as cards
from tests.test_payment_state import CHECKOUT_GROUP_ID, CUSTOMER_ID
from tests.test_payments_card import (
    _mock_strategy,
    _seed_card_payment,
)
from tests.test_payments_card import card_service as card_service


@pytest.mark.asyncio
async def test_disabled_gate_prevents_card_creation(card_service: Any) -> None:
    with patch("app.services.payments.gate.payments_gate_status", return_value=(False, "disabled")):
        with patch.object(cards, "lookup_user_email", return_value="buyer@example.test"):
            with pytest.raises(AppError):
                await cards.create_card_widget_session(
                    card_service,
                    checkout_group_id=CHECKOUT_GROUP_ID,
                    customer_id=CUSTOMER_ID,
                    actor_id=CUSTOMER_ID,
                )
    assert not card_service.client.tables["payments"].rows


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["completed", "abandoned", "expired"])
async def test_terminal_checkout_prevents_card_creation(card_service: Any, status: str) -> None:
    card_service.client.tables["checkout_groups"].rows[0]["status"] = status
    with patch.object(cards, "lookup_user_email", return_value="buyer@example.test"):
        with pytest.raises(AppError):
            await cards.create_card_widget_session(
                card_service,
                checkout_group_id=CHECKOUT_GROUP_ID,
                customer_id=CUSTOMER_ID,
                actor_id=CUSTOMER_ID,
            )
    assert not card_service.client.tables["payments"].rows


@pytest.mark.asyncio
async def test_old_card_success_requires_canonical_query(card_service: Any) -> None:
    payment_id = str(uuid4())
    _seed_card_payment(card_service.client, payment_id=payment_id, status="success")
    strategy = _mock_strategy(lenco_status="pending")
    result = await cards.verify_card_payment_return(
        card_service,
        payment_id=payment_id,
        customer_id=CUSTOMER_ID,
        client_status="success",
        strategy=strategy,
    )
    strategy.query_status.assert_awaited_once()
    assert not result.order_confirmed


def test_balance_without_receipt_cannot_create_charge() -> None:
    with patch.object(jobs, "post_transaction") as post:
        with pytest.raises(AppError):
            jobs._settle_balance(str(uuid4()), 70000)
        post.assert_not_called()


@pytest.mark.asyncio
async def test_terminal_checkout_cannot_retry_collection(card_service: Any) -> None:
    from unittest.mock import AsyncMock, MagicMock

    from app.routers.payment_status import _create_retry_payment_attempt
    from app.services.payments.base import CollectionStatus, InitiateCollectionResult
    from app.services.payments.initiate import InitiatePaymentRequest

    card_service.client.tables["checkout_groups"].rows[0]["status"] = "abandoned"
    strategy = MagicMock()
    strategy.initiate_collection = AsyncMock(
        return_value=InitiateCollectionResult(
            status=CollectionStatus.PENDING, amount_major="100.00"
        )
    )
    with pytest.raises(AppError):
        await _create_retry_payment_attempt(
            card_service,
            request=InitiatePaymentRequest(CHECKOUT_GROUP_ID, 10000, "mtn", "0961111111"),
            actor_id=CUSTOMER_ID,
            strategy=strategy,
        )
    strategy.initiate_collection.assert_not_awaited()


def test_webhook_first_card_stays_unfunded_until_query(card_service: Any) -> None:
    from app.services.payments.state import process_webhook_event
    from tests.test_payments_card import _seed_success_webhook

    payment_id, event_id = str(uuid4()), str(uuid4())
    _seed_card_payment(card_service.client, payment_id=payment_id)
    _seed_success_webhook(card_service.client, webhook_id=event_id)
    process_webhook_event(card_service, webhook_event_id=event_id)
    assert card_service.client.tables["payments"].rows[0]["status"] == "ussd_pushed"
    assert card_service.client.tables["webhook_events"].rows[0]["processed_at"] is None
