"""T54: payments hardening — initiation failures, retry validation, fee booking."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.errors import AppError
from app.routers.checkout_payment import derive_momo_rail_from_number
from app.services.payments.base import PaymentProviderError
from app.services.payments.initiate import InitiatePaymentRequest, initiate_checkout_payment
from app.services.payments.state import PaymentStatus, apply_payment_status
from tests.test_payment_state import (
    ACTOR_ID,
    CHECKOUT_GROUP_ID,
    FakeServiceClient,
    FakeSupabaseClient,
)


def test_derive_momo_rail_from_number() -> None:
    assert derive_momo_rail_from_number("+260961234567") == "mtn"
    assert derive_momo_rail_from_number("+260971234567") == "airtel"


@pytest.mark.asyncio
async def test_initiate_terminal_rejection_marks_failed() -> None:
    fake = FakeSupabaseClient()
    fake.tables["checkout_groups"].rows.append(
        {"id": CHECKOUT_GROUP_ID, "total_ngwee": 10_000, "status": "pending"}
    )
    service = FakeServiceClient(fake)
    strategy = MagicMock()
    strategy.initiate_collection = AsyncMock(
        side_effect=PaymentProviderError(
            "invalid_number",
            "bad msisdn",
            dispatch_may_have_succeeded=False,
        )
    )
    with pytest.raises(AppError) as exc:
        await initiate_checkout_payment(
            service,
            InitiatePaymentRequest(
                checkout_group_id=CHECKOUT_GROUP_ID,
                amount_ngwee=10_000,
                rail="mtn",
                phone="+260961234567",
            ),
            strategy=strategy,
            actor_id=ACTOR_ID,
        )
    assert exc.value.code == "payment.initiation_rejected"
    payment = fake.tables["payments"].rows[0]
    assert payment["status"] == PaymentStatus.FAILED.value
    assert payment["raw"].get("terminal_provider_failure") is True


def test_duplicate_settlement_still_books_fee(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import payments

    booked: list[dict[str, object]] = []
    monkeypatch.setattr(
        payments.fees,
        "book_collection_fee",
        lambda **kwargs: booked.append(kwargs) or None,
    )
    fake = FakeSupabaseClient()
    fake.tables["payments"].rows.append(
        {
            "id": "pay-1",
            "checkout_group_id": CHECKOUT_GROUP_ID,
            "provider": "lenco",
            "rail": "mtn",
            "lenco_reference": "ord-test",
            "amount_ngwee": 1_000,
            "status": "success",
            "raw": {},
        }
    )
    service = FakeServiceClient(fake)
    outcome = apply_payment_status(
        service,
        payment_id="pay-1",
        incoming_status=PaymentStatus.SUCCESS,
        actor_id=ACTOR_ID,
        note="webhook replay",
        observation={
            "reference": "ord-test",
            "amount_ngwee": 1_000,
            "currency": "ZMW",
            "source": "test",
            "canonical_status_verified": True,
            "provider_outcome": "successful",
        },
        provider_fee="0.25",
        provider_bearer="merchant",
    )
    assert outcome is None
    assert booked == [{"payment_id": "pay-1", "fee": "0.25", "bearer": "merchant"}]