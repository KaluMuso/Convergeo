"""F2 through F1's real HTTP transport and adapter; synthetic, not Lenco acceptance."""

from copy import deepcopy
from typing import Any
from uuid import uuid4

import httpx
import pytest
from app.routers.payments_card import verify_card_payment_return
from app.services.payments.lenco import LencoClient, LencoStrategy
from tests.test_lenco_client import STATUS_FIXTURE
from tests.test_payment_state import CUSTOMER_ID
from tests.test_payments_card import REFERENCE, _seed_card_payment
from tests.test_payments_card import card_service as card_service


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome", ["successful", "failed", "pending", "not_found", "wrong_amount"]
)
async def test_card_actual_transport_outcome(card_service: Any, outcome: str) -> None:
    payment_id = str(uuid4())
    _seed_card_payment(card_service.client, payment_id=payment_id)
    calls: list[str] = []

    def transport(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        assert request.method == "GET"
        assert request.url.path == f"/collections/status/{REFERENCE}"
        if outcome == "not_found":
            return httpx.Response(
                404, json={"status": False, "errorCode": "11", "message": "not found"}
            )
        body = deepcopy(STATUS_FIXTURE)
        body["data"].update(
            reference=REFERENCE,
            amount="100.00",
            status="successful" if outcome == "wrong_amount" else outcome,
        )
        if outcome == "wrong_amount":
            body["data"]["amount"] = "101.00"
        return httpx.Response(200, json=body)

    async with httpx.AsyncClient(
        base_url="https://lenco.test", transport=httpx.MockTransport(transport)
    ) as http:
        strategy = LencoStrategy(
            LencoClient(http_client=http, token="synthetic", base_url="https://lenco.test")
        )
        result = await verify_card_payment_return(
            card_service,
            payment_id=payment_id,
            customer_id=CUSTOMER_ID,
            client_status="pending",
            strategy=strategy,
        )
    assert calls
    assert result.order_confirmed is (outcome == "successful")
    if outcome == "failed":
        assert result.retry_checkout
        assert card_service.client.tables["payments"].rows[0]["raw"]["terminal_provider_failure"]
    elif outcome != "successful":
        assert not result.retry_checkout
        assert not card_service.client.tables["payment_collection_receipts"].rows
