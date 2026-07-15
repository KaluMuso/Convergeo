"""Tests for card widget session create and server-verified return handling."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.main import create_app
from app.routers.payments_card import verify_card_payment_return
from app.services.payments.base import QueryStatusResult
from app.services.payments.state import (
    PaymentStatus,
    count_payment_audit_events,
    process_webhook_event,
)
from fastapi.testclient import TestClient
from tests.test_payment_state import (
    CHECKOUT_GROUP_ID,
    CUSTOMER_ID,
    FakeServiceClient,
    FakeSupabaseClient,
    FakeTable,
)

ACTOR_ID = "22222222-2222-2222-2222-222222222222"
VALID_TOKEN = "valid-test-token"
REFERENCE = f"ord-{CHECKOUT_GROUP_ID}"


def _current_user() -> CurrentUser:
    return CurrentUser(id=CUSTOMER_ID, roles=frozenset({"customer"}), token=VALID_TOKEN)


def _seed_profile(fake: FakeSupabaseClient) -> None:
    if "profiles" not in fake.tables:
        fake.tables["profiles"] = FakeTable()
    # Mirror the real schema: profiles has phone + display_name, NOT email
    # (email lives in auth.users, resolved via lookup_user_email).
    fake.tables["profiles"].rows.append(
        {
            "id": CUSTOMER_ID,
            "phone": "+260961111111",
            "display_name": "Jane Buyer",
        }
    )


def _seed_card_payment(
    fake: FakeSupabaseClient,
    *,
    payment_id: str,
    status: str = "ussd_pushed",
    reference: str = REFERENCE,
    raw: dict[str, Any] | None = None,
) -> None:
    stamp = datetime.now(UTC).isoformat()
    fake.tables["payments"].rows.append(
        {
            "id": payment_id,
            "checkout_group_id": CHECKOUT_GROUP_ID,
            "provider": "lenco",
            "rail": "card",
            "lenco_reference": reference,
            "amount_ngwee": 10_000,
            "status": status,
            "raw": raw or {},
            "created_at": stamp,
            "updated_at": stamp,
        }
    )


def _seed_success_webhook(
    fake: FakeSupabaseClient,
    *,
    webhook_id: str,
    reference: str = REFERENCE,
    processed_at: str | None = None,
) -> None:
    fake.tables["webhook_events"].rows.append(
        {
            "id": webhook_id,
            "provider": "lenco",
            "event_id": f"evt-{webhook_id}",
            "processed_at": processed_at,
            "raw": {
                "event": "collection.successful",
                "data": {"reference": reference, "status": "successful"},
            },
            "created_at": datetime.now(UTC).isoformat(),
        }
    )


def _mock_strategy(*, lenco_status: str) -> MagicMock:
    strategy = MagicMock()
    strategy.query_status = AsyncMock(
        return_value=QueryStatusResult(
            reference=REFERENCE,
            status=lenco_status,
            amount_major="100.00",
        )
    )
    return strategy


@pytest.fixture
def card_service() -> FakeServiceClient:
    fake = FakeSupabaseClient()
    fake.tables["checkout_groups"].rows.append(
        {
            "id": CHECKOUT_GROUP_ID,
            "customer_id": CUSTOMER_ID,
            "total_ngwee": 10_000,
            "status": "pending",
        }
    )
    _seed_profile(fake)
    return FakeServiceClient(fake)


def _client_with_service(service: FakeServiceClient) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user] = _current_user

    def _override_service() -> Generator[FakeServiceClient, None, None]:
        yield service

    app.dependency_overrides[get_supabase_client] = _override_service
    return TestClient(app, raise_server_exceptions=False)


class TestForgedReturn:
    @pytest.mark.asyncio
    async def test_client_success_claim_without_lenco_success_holds_payment(
        self,
        card_service: FakeServiceClient,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        payment_id = str(uuid.uuid4())
        _seed_card_payment(card_service.client, payment_id=payment_id)
        strategy = _mock_strategy(lenco_status="failed")

        with caplog.at_level("ERROR"):
            result = await verify_card_payment_return(
                card_service,
                payment_id=payment_id,
                customer_id=CUSTOMER_ID,
                client_status="success",
                strategy=strategy,
            )

        assert result.verified is False
        assert result.order_confirmed is False
        assert result.held is True
        payment = card_service.client.tables["payments"].rows[0]
        assert payment["status"] == PaymentStatus.USSD_PUSHED.value
        assert payment["raw"]["hold"]["reason"] == "client_claimed_success_lenco_mismatch"
        assert "Card payment verification mismatch" in caplog.text

    def test_forged_return_endpoint_does_not_confirm_order(
        self,
        card_service: FakeServiceClient,
    ) -> None:
        payment_id = str(uuid.uuid4())
        _seed_card_payment(card_service.client, payment_id=payment_id)
        strategy = _mock_strategy(lenco_status="pending")
        client = _client_with_service(card_service)

        with patch(
            "app.routers.payments_card.get_payment_strategy",
            return_value=strategy,
        ):
            response = client.post(
                f"/payments/card/{payment_id}/verify",
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
                json={"client_status": "success"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["order_confirmed"] is False
        assert body["held"] is True
        assert card_service.client.tables["payments"].rows[0]["status"] == "ussd_pushed"


class TestVerifyWebhookRace:
    @pytest.mark.asyncio
    async def test_verify_first_then_webhook_converges_once(
        self,
        card_service: FakeServiceClient,
    ) -> None:
        payment_id = str(uuid.uuid4())
        webhook_id = str(uuid.uuid4())
        _seed_card_payment(card_service.client, payment_id=payment_id)
        strategy = _mock_strategy(lenco_status="successful")

        first = await verify_card_payment_return(
            card_service,
            payment_id=payment_id,
            customer_id=CUSTOMER_ID,
            client_status="success",
            strategy=strategy,
        )
        assert first.verified is False
        assert first.order_confirmed is False
        assert card_service.client.tables["payments"].rows[0]["status"] == "ussd_pushed"

        _seed_success_webhook(card_service.client, webhook_id=webhook_id)
        second = await verify_card_payment_return(
            card_service,
            payment_id=payment_id,
            customer_id=CUSTOMER_ID,
            client_status="success",
            strategy=strategy,
        )
        assert second.verified is True
        assert second.order_confirmed is True
        assert card_service.client.tables["payments"].rows[0]["status"] == "success"
        assert count_payment_audit_events(card_service, payment_id) == 1

        third = await verify_card_payment_return(
            card_service,
            payment_id=payment_id,
            customer_id=CUSTOMER_ID,
            client_status="success",
            strategy=strategy,
        )
        assert third.verified is True
        assert count_payment_audit_events(card_service, payment_id) == 1

    @pytest.mark.asyncio
    async def test_webhook_first_then_verify_is_idempotent(
        self,
        card_service: FakeServiceClient,
    ) -> None:
        payment_id = str(uuid.uuid4())
        webhook_id = str(uuid.uuid4())
        _seed_card_payment(card_service.client, payment_id=payment_id, status="ussd_pushed")
        _seed_success_webhook(card_service.client, webhook_id=webhook_id)

        outcome = process_webhook_event(card_service, webhook_event_id=webhook_id)
        assert outcome is not None
        assert outcome.to_status == PaymentStatus.SUCCESS
        assert card_service.client.tables["payments"].rows[0]["status"] == "success"

        strategy = _mock_strategy(lenco_status="successful")
        result = await verify_card_payment_return(
            card_service,
            payment_id=payment_id,
            customer_id=CUSTOMER_ID,
            client_status="success",
            strategy=strategy,
        )
        assert result.verified is True
        assert result.order_confirmed is True
        assert count_payment_audit_events(card_service, payment_id) == 1


class TestWidgetFailureRetry:
    @pytest.mark.asyncio
    async def test_widget_close_releases_checkout_for_retry(
        self,
        card_service: FakeServiceClient,
    ) -> None:
        payment_id = str(uuid.uuid4())
        _seed_card_payment(card_service.client, payment_id=payment_id)
        card_service.client.tables["checkout_groups"].rows[0]["status"] = "completed"
        strategy = _mock_strategy(lenco_status="failed")

        result = await verify_card_payment_return(
            card_service,
            payment_id=payment_id,
            customer_id=CUSTOMER_ID,
            client_status="closed",
            strategy=strategy,
        )

        assert result.retry_checkout is True
        assert result.order_confirmed is False
        assert card_service.client.tables["payments"].rows[0]["status"] == "failed"
        checkout_audits = [
            row
            for row in card_service.client.tables["audit_log"].rows
            if row.get("action") == "checkout.release_for_retry"
        ]
        assert len(checkout_audits) == 1

    def test_failure_verify_endpoint_returns_retry_flag(
        self,
        card_service: FakeServiceClient,
    ) -> None:
        payment_id = str(uuid.uuid4())
        _seed_card_payment(card_service.client, payment_id=payment_id)
        strategy = _mock_strategy(lenco_status="failed")
        client = _client_with_service(card_service)

        with patch(
            "app.routers.payments_card.get_payment_strategy",
            return_value=strategy,
        ):
            response = client.post(
                f"/payments/card/{payment_id}/verify",
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
                json={"client_status": "closed"},
            )

        assert response.status_code == 200
        assert response.json()["retry_checkout"] is True
        assert response.json()["order_confirmed"] is False


class TestCreateCardSession:
    def test_create_session_returns_widget_parameters(
        self,
        card_service: FakeServiceClient,
    ) -> None:
        client = _client_with_service(card_service)
        with patch(
            "app.routers.payments_card.lookup_user_email",
            return_value="buyer@example.com",
        ):
            response = client.post(
                "/payments/card/session",
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
                json={"checkout_group_id": CHECKOUT_GROUP_ID},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["checkout_group_id"] == CHECKOUT_GROUP_ID
        assert body["reference"].startswith("ord-")
        assert body["amount_major"] == "100.00"
        assert body["widget_script_url"].endswith("/inline.js")
        assert body["customer"]["email"] == "buyer@example.com"
        assert body["customer"]["first_name"] == "Jane"
        assert body["customer"]["last_name"] == "Buyer"
        payment = card_service.client.tables["payments"].rows[0]
        assert payment["rail"] == "card"
        assert payment["status"] == PaymentStatus.USSD_PUSHED.value

    def test_create_session_without_email_is_rejected(
        self,
        card_service: FakeServiceClient,
    ) -> None:
        """No auth.users email → 422 profile_incomplete (widget needs an email)."""
        client = _client_with_service(card_service)
        with patch(
            "app.routers.payments_card.lookup_user_email",
            return_value=None,
        ):
            response = client.post(
                "/payments/card/session",
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
                json={"checkout_group_id": CHECKOUT_GROUP_ID},
            )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "checkout.profile_incomplete"
        # No payment row is created when the customer can't be addressed.
        assert card_service.client.tables["payments"].rows == []
