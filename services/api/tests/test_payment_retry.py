"""Retry safety for Lenco collections (FIX-C: per-attempt reference salt).

A second `initiate` after a failed/expired attempt on the same order must get a
DISTINCT `lenco_reference` so it does not collide on the UNIQUE
`payments.lenco_reference` constraint, while the webhook still resolves the correct
payment from the stored reference and a single attempt never double-charges.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.services.payments.base import CollectionStatus, InitiateCollectionResult
from app.services.payments.initiate import InitiatePaymentRequest, initiate_checkout_payment
from app.services.payments.references import (
    make_order_reference,
    parse_reference,
)
from app.services.payments.state import (
    PaymentEvent,
    PaymentStatus,
    process_webhook_event,
    transition_payment,
)
from postgrest.exceptions import APIError
from tests.test_payment_state import (
    ACTOR_ID,
    CHECKOUT_GROUP_ID,
    FakeQuery,
    FakeServiceClient,
    FakeSupabaseClient,
    FakeTable,
)


class _UniqueRefInsert:
    """Insert that emulates the DB UNIQUE(lenco_reference) constraint."""

    def __init__(self, table: FakeTable, payload: dict[str, Any]) -> None:
        self._table = table
        self._payload = payload

    def execute(self) -> Any:
        reference = self._payload.get("lenco_reference")
        if reference is not None and any(
            row.get("lenco_reference") == reference for row in self._table.rows
        ):
            raise APIError(
                {
                    "message": "duplicate key value violates unique constraint",
                    "code": "23505",
                    "hint": None,
                    "details": None,
                }
            )
        return FakeQuery(self._table, []).insert(self._payload).execute()


class UniqueRefPaymentsTable(FakeTable):
    """payments table that rejects a duplicate lenco_reference like the real UNIQUE."""

    def insert(self, payload: dict[str, Any]) -> Any:
        return _UniqueRefInsert(self, payload)


def _service_with_unique_payments() -> FakeServiceClient:
    fake = FakeSupabaseClient()
    fake.tables["payments"] = UniqueRefPaymentsTable()
    fake.tables["checkout_groups"].rows.append(
        {"id": CHECKOUT_GROUP_ID, "total_ngwee": 10_000, "status": "pending"}
    )
    return FakeServiceClient(fake)


def _pending_strategy() -> MagicMock:
    strategy = MagicMock()
    strategy.initiate_collection = AsyncMock(
        return_value=InitiateCollectionResult(
            provider_reference="lenco-txn",
            status=CollectionStatus.PENDING,
            amount_major="100.00",
        )
    )
    return strategy


def _request() -> InitiatePaymentRequest:
    return InitiatePaymentRequest(
        checkout_group_id=CHECKOUT_GROUP_ID,
        amount_ngwee=10_000,
        rail="mtn",
        phone="+260961111111",
    )


async def _initiate(service: FakeServiceClient, strategy: MagicMock) -> Any:
    return await initiate_checkout_payment(
        service, _request(), strategy=strategy, actor_id=ACTOR_ID
    )


class TestRetryReference:
    @pytest.mark.asyncio
    async def test_retry_after_failed_gets_distinct_reference_no_collision(self) -> None:
        service = _service_with_unique_payments()

        first = await _initiate(service, _pending_strategy())
        # First attempt fails (Lenco declined / expired).
        transition_payment(
            service,
            payment_id=first.payment_id,
            event=PaymentEvent.FAILED,
            actor_id=ACTOR_ID,
            note="first attempt failed",
        )

        # Retry: same order, new attempt. Must NOT raise a UNIQUE collision.
        second = await _initiate(service, _pending_strategy())

        assert second.payment_id != first.payment_id
        assert second.lenco_reference != first.lenco_reference
        assert second.status == PaymentStatus.USSD_PUSHED

        # Both references still round-trip back to the same order/checkout group.
        for ref in (first.lenco_reference, second.lenco_reference):
            kind, decoded = parse_reference(ref)
            assert kind == "order"
            assert decoded == CHECKOUT_GROUP_ID

        rows = service.client.tables["payments"].rows
        assert len(rows) == 2
        assert {r["lenco_reference"] for r in rows} == {
            first.lenco_reference,
            second.lenco_reference,
        }

    @pytest.mark.asyncio
    async def test_webhook_resolves_retry_payment_from_new_reference(self) -> None:
        service = _service_with_unique_payments()

        first = await _initiate(service, _pending_strategy())
        transition_payment(
            service,
            payment_id=first.payment_id,
            event=PaymentEvent.FAILED,
            actor_id=ACTOR_ID,
            note="first attempt failed",
        )
        second = await _initiate(service, _pending_strategy())

        # Lenco delivers a success webhook carrying the RETRY attempt's reference.
        webhook_id = str(uuid.uuid4())
        service.client.tables["webhook_events"].rows.append(
            {
                "id": webhook_id,
                "provider": "lenco",
                "event_id": f"evt-{webhook_id}",
                "processed_at": None,
                "raw": {
                    "event": "collection.successful",
                    "data": {
                        "reference": second.lenco_reference,
                        "status": "successful",
                    },
                },
                "created_at": datetime.now(UTC).isoformat(),
            }
        )

        outcome = process_webhook_event(service, webhook_event_id=webhook_id)

        assert outcome is not None
        assert outcome.to_status == PaymentStatus.SUCCESS

        by_id = {r["id"]: r for r in service.client.tables["payments"].rows}
        # The webhook resolved the retry payment (by stored reference), not the first.
        assert by_id[second.payment_id]["status"] == PaymentStatus.SUCCESS.value
        assert by_id[first.payment_id]["status"] == PaymentStatus.FAILED.value

    @pytest.mark.asyncio
    async def test_single_attempt_does_not_double_charge(self) -> None:
        service = _service_with_unique_payments()
        strategy = _pending_strategy()

        result = await _initiate(service, strategy)

        # One click == one collection call == one payment row == one reference.
        strategy.initiate_collection.assert_awaited_once()
        rows = service.client.tables["payments"].rows
        assert len(rows) == 1
        assert rows[0]["lenco_reference"] == result.lenco_reference

    def test_encoder_salt_is_unique_and_decodable(self) -> None:
        order_id = CHECKOUT_GROUP_ID
        attempt_a = str(uuid.uuid4())
        attempt_b = str(uuid.uuid4())

        ref_a = make_order_reference(order_id, attempt=attempt_a)
        ref_b = make_order_reference(order_id, attempt=attempt_b)
        plain = make_order_reference(order_id)

        # Distinct per attempt, distinct from the un-salted form.
        assert ref_a != ref_b != plain
        assert ref_a.startswith("ord-")

        # All three still decode back to the same order id.
        for ref in (ref_a, ref_b, plain):
            kind, decoded = parse_reference(ref)
            assert kind == "order"
            assert decoded == order_id
