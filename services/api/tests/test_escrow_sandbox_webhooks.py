"""Sandbox E2E drills — Lenco webhook → escrow_hold ledger + payout lock."""

from __future__ import annotations

import hashlib
import hmac
import json
import shutil
import uuid
from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from app.deps import get_supabase_client
from app.main import create_app
from app.services.db import SqlResult
from app.services.ledger.templates import LedgerTemplate
from app.services.payments.fulfillment import EscrowFulfillmentResult, escrow_hold_idempotency_key
from app.services.payments.reconcile import drain_pending_webhook_events
from app.services.payments.state import PaymentStatus, apply_payment_status, process_webhook_event
from app.services.payments.webhook_verify import SIGNATURE_HEADER
from app.services.payouts.execution import execute_vendor_payout
from app.services.payouts.gate import PayoutsDisabledError
from app.services.payouts.hold import EscrowHoldNotElapsedError
from fastapi.testclient import TestClient
from tests.rls.conftest import PgConn
from tests.test_payment_state import FakeServiceClient, FakeSupabaseClient

TOKEN = "sandbox-escrow-webhook-token"
WEBHOOK_PATH = "/webhooks/lenco"
CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
CHECKOUT_GROUP_ID = "d1000000-0000-4000-8000-000000000001"
ORDER_ID = "d2000000-0000-4000-8000-000000000001"
AMOUNT_NGWEE = 45_000
LEDGER_TXN_ID = "a1000000-0000-4000-8000-000000000099"


def _mock_settlement_sql(script: str, *, payment_id: str) -> SqlResult:
    if "pg_advisory_xact_lock" in script:
        return SqlResult(ok=True, rows=["none"])
    if "WHERE id = " in script and "payment_id::text" in script:
        return SqlResult(ok=True, rows=[payment_id])
    return SqlResult(ok=True, rows=["none"])


def _settlement_sql_side_effect(
    payment_id: str,
) -> Any:
    return lambda script: _mock_settlement_sql(script, payment_id=payment_id)


def _sign_body(raw_body: bytes, *, token: str = TOKEN) -> str:
    signing_key = hashlib.sha256(token.encode("utf-8")).hexdigest().encode("utf-8")
    return hmac.new(signing_key, raw_body, hashlib.sha512).hexdigest()


def _collection_payload(
    *,
    event: str = "collection.successful",
    event_id: str = "evt-sandbox-1",
    reference: str,
    status: str = "successful",
) -> dict[str, Any]:
    return {
        "event": event,
        "data": {
            "id": event_id,
            "reference": reference,
            "status": status,
            "amount": "450.00",
            "currency": "ZMW",
        },
    }


@pytest.fixture
def webhook_client(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[TestClient, FakeSupabaseClient], None, None]:
    monkeypatch.setenv("LENCO_API_TOKEN", TOKEN)
    fake = FakeSupabaseClient()
    fake.tables["checkout_groups"].rows.append(
        {
            "id": CHECKOUT_GROUP_ID,
            "total_ngwee": AMOUNT_NGWEE,
            "status": "completed",
        }
    )
    app = create_app()
    app.dependency_overrides[get_supabase_client] = lambda: FakeServiceClient(fake)

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, fake


def _seed_payment_row(
    fake: FakeSupabaseClient,
    *,
    payment_id: str,
    reference: str,
    status: str = "ussd_pushed",
) -> None:
    stamp = datetime.now(UTC).isoformat()
    fake.tables["payments"].rows.append(
        {
            "id": payment_id,
            "checkout_group_id": CHECKOUT_GROUP_ID,
            "provider": "lenco",
            "rail": "mtn",
            "lenco_reference": reference,
            "amount_ngwee": AMOUNT_NGWEE,
            "status": status,
            "raw": {},
            "created_at": stamp,
            "updated_at": stamp,
        }
    )


class TestEscrowSandboxWebhooks:
    pytestmark = pytest.mark.prepaid_settlement_db
    def test_successful_momo_webhook_marks_paid_and_settles_escrow(
        self,
        webhook_client: tuple[TestClient, FakeSupabaseClient],
    ) -> None:
        client, fake = webhook_client
        payment_id = str(uuid.uuid4())
        reference = f"ord-{payment_id}"
        _seed_payment_row(fake, payment_id=payment_id, reference=reference)

        payload = _collection_payload(event_id="evt-success-1", reference=reference)
        raw_body = json.dumps(payload).encode("utf-8")
        response = client.post(
            WEBHOOK_PATH,
            content=raw_body,
            headers={SIGNATURE_HEADER: _sign_body(raw_body)},
        )
        assert response.status_code == 200
        assert response.json() == {"status": "accepted"}
        assert len(fake.tables["webhook_events"].rows) == 1

        fulfilled = EscrowFulfillmentResult(
            checkout_group_id=CHECKOUT_GROUP_ID,
            payment_id=payment_id,
            transaction_ids=(LEDGER_TXN_ID,),
            total_ngwee=AMOUNT_NGWEE,
            created_count=1,
        )
        with (
            patch(
                "app.services.payments.settlement.run_sql_script",
                side_effect=_settlement_sql_side_effect(payment_id),
            ),
            patch(
                "app.services.payments.settlement.fulfill_prepaid_checkout_escrow",
                return_value=fulfilled,
            ) as mock_fulfill,
        ):
            webhook_id = str(fake.tables["webhook_events"].rows[0]["id"])
            outcome = process_webhook_event(
                FakeServiceClient(fake),
                webhook_event_id=webhook_id,
            )

        assert outcome is not None
        assert outcome.to_status == PaymentStatus.SUCCESS
        assert fake.tables["payments"].rows[0]["status"] == "success"
        mock_fulfill.assert_called_once()
        assert mock_fulfill.call_args.kwargs["amount_ngwee"] == AMOUNT_NGWEE

    def test_failed_momo_webhook_does_not_settle_escrow(
        self,
        webhook_client: tuple[TestClient, FakeSupabaseClient],
    ) -> None:
        client, fake = webhook_client
        payment_id = str(uuid.uuid4())
        reference = f"ord-{payment_id}"
        _seed_payment_row(fake, payment_id=payment_id, reference=reference)

        payload = _collection_payload(
            event="collection.failed",
            event_id="evt-fail-1",
            reference=reference,
            status="failed",
        )
        raw_body = json.dumps(payload).encode("utf-8")
        response = client.post(
            WEBHOOK_PATH,
            content=raw_body,
            headers={SIGNATURE_HEADER: _sign_body(raw_body)},
        )
        assert response.status_code == 200

        with patch(
            "app.services.payments.settlement.fulfill_prepaid_checkout_escrow",
        ) as mock_fulfill:
            webhook_id = str(fake.tables["webhook_events"].rows[0]["id"])
            outcome = process_webhook_event(
                FakeServiceClient(fake),
                webhook_event_id=webhook_id,
            )

        assert outcome is not None
        assert outcome.to_status == PaymentStatus.FAILED
        assert fake.tables["payments"].rows[0]["status"] == "failed"
        mock_fulfill.assert_not_called()

    def test_duplicate_success_webhook_is_idempotent_on_settlement(
        self,
        webhook_client: tuple[TestClient, FakeSupabaseClient],
    ) -> None:
        client, fake = webhook_client
        payment_id = str(uuid.uuid4())
        reference = f"ord-{payment_id}"
        _seed_payment_row(fake, payment_id=payment_id, reference=reference)

        payload = _collection_payload(event_id="evt-dup-escrow-1", reference=reference)
        raw_body = json.dumps(payload).encode("utf-8")
        headers = {SIGNATURE_HEADER: _sign_body(raw_body)}
        assert client.post(WEBHOOK_PATH, content=raw_body, headers=headers).status_code == 200
        assert client.post(WEBHOOK_PATH, content=raw_body, headers=headers).status_code == 200

        fulfilled = EscrowFulfillmentResult(
            checkout_group_id=CHECKOUT_GROUP_ID,
            payment_id=payment_id,
            transaction_ids=(LEDGER_TXN_ID,),
            total_ngwee=AMOUNT_NGWEE,
            created_count=1,
        )
        service = FakeServiceClient(fake)
        webhook_id = str(fake.tables["webhook_events"].rows[0]["id"])
        with (
            patch(
                "app.services.payments.settlement.run_sql_script",
                side_effect=_settlement_sql_side_effect(payment_id),
            ),
            patch(
                "app.services.payments.settlement.fulfill_prepaid_checkout_escrow",
                return_value=fulfilled,
            ) as mock_fulfill,
        ):
            first = process_webhook_event(service, webhook_event_id=webhook_id)
            second = process_webhook_event(service, webhook_event_id=webhook_id)

        assert first is not None
        assert second is None
        mock_fulfill.assert_called_once()

    def test_webhook_drain_applies_stored_success_event(
        self,
        webhook_client: tuple[TestClient, FakeSupabaseClient],
    ) -> None:
        client, fake = webhook_client
        payment_id = str(uuid.uuid4())
        reference = f"ord-{payment_id}"
        _seed_payment_row(fake, payment_id=payment_id, reference=reference)

        payload = _collection_payload(event_id="evt-drain-1", reference=reference)
        raw_body = json.dumps(payload).encode("utf-8")
        assert (
            client.post(
                WEBHOOK_PATH,
                content=raw_body,
                headers={SIGNATURE_HEADER: _sign_body(raw_body)},
            ).status_code
            == 200
        )

        fulfilled = EscrowFulfillmentResult(
            checkout_group_id=CHECKOUT_GROUP_ID,
            payment_id=payment_id,
            transaction_ids=(LEDGER_TXN_ID,),
            total_ngwee=AMOUNT_NGWEE,
            created_count=1,
        )
        service = FakeServiceClient(fake)
        with (
            patch(
                "app.services.payments.settlement.run_sql_script",
                side_effect=_settlement_sql_side_effect(payment_id),
            ),
            patch(
                "app.services.payments.settlement.fulfill_prepaid_checkout_escrow",
                return_value=fulfilled,
            ),
        ):
            drain = drain_pending_webhook_events(service, limit=10)

        assert drain.applied == 1
        assert fake.tables["payments"].rows[0]["status"] == "success"


class TestPayoutEscrowLock:
    @pytest.mark.asyncio
    async def test_payouts_disabled_blocks_execution(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("PAYOUTS_ENABLED", raising=False)
        with pytest.raises(PayoutsDisabledError):
            await execute_vendor_payout(
                AsyncMock(),
                vendor_id=VENDOR_ID,
                resolve_account=AsyncMock(),
                initiate_momo_payout=AsyncMock(),
                initiate_bank_payout=AsyncMock(),
                skip_velocity=True,
            )

    @pytest.mark.asyncio
    async def test_escrow_minimum_hold_blocks_payout(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("PAYOUTS_ENABLED", "true")
        with (
            patch(
                "app.services.payouts.execution.assert_payout_method_not_held",
                return_value=None,
            ),
            patch(
                "app.services.payouts.hold.assert_escrow_minimum_hold_elapsed",
                side_effect=EscrowHoldNotElapsedError(
                    hold_until=datetime.now(UTC),
                ),
            ),
            pytest.raises(EscrowHoldNotElapsedError),
        ):
            await execute_vendor_payout(
                AsyncMock(),
                vendor_id=VENDOR_ID,
                resolve_account=AsyncMock(),
                initiate_momo_payout=AsyncMock(),
                initiate_bank_payout=AsyncMock(),
                skip_velocity=True,
            )


@pytest.mark.prepaid_settlement_db
@pytest.mark.skipif(shutil.which("psql") is None, reason="psql not available")
class TestEscrowLedgerIntegration:
    @pytest.fixture
    def db_url_env(self, db: PgConn) -> Generator[None, None, None]:
        import os

        previous = os.environ.get("SUPABASE_DB_URL")
        os.environ["SUPABASE_DB_URL"] = db.dsn
        yield
        if previous is None:
            os.environ.pop("SUPABASE_DB_URL", None)
        else:
            os.environ["SUPABASE_DB_URL"] = previous

    def _seed_checkout_with_order(self, db: PgConn, *, payment_id: str, reference: str) -> None:
        db.run(
            f"""
            INSERT INTO public.checkout_groups (
              id, customer_id, idempotency_key, subtotal_ngwee,
              delivery_fee_ngwee, total_ngwee, status
            ) VALUES (
              '{CHECKOUT_GROUP_ID}', '{CUSTOMER_ID}', 'sandbox-escrow-{CHECKOUT_GROUP_ID}',
              {AMOUNT_NGWEE - 5_000}, 5000, {AMOUNT_NGWEE}, 'completed'
            ) ON CONFLICT (id) DO NOTHING;

            INSERT INTO public.orders (
              id, checkout_group_id, vendor_id, customer_id, status, fulfilment, cod,
              delivery_fee_ngwee, subtotal_ngwee
            ) VALUES (
              '{ORDER_ID}', '{CHECKOUT_GROUP_ID}', '{VENDOR_ID}', '{CUSTOMER_ID}',
              'placed', 'delivery', false, 5000, {AMOUNT_NGWEE - 5_000}
            ) ON CONFLICT (id) DO NOTHING;

            INSERT INTO public.order_items (
              id, order_id, listing_id, qty, unit_price_ngwee, title_snapshot
            )
            SELECT
              '{uuid.uuid4()}', '{ORDER_ID}', vl.id, 1, {AMOUNT_NGWEE - 5_000}, 'Sandbox SKU'
            FROM public.vendor_listings vl
            WHERE vl.vendor_id = '{VENDOR_ID}'
            LIMIT 1
            ON CONFLICT DO NOTHING;

            INSERT INTO public.payments (
              id, checkout_group_id, provider, rail, lenco_reference, amount_ngwee, status
            ) VALUES (
              '{payment_id}', '{CHECKOUT_GROUP_ID}', 'lenco', 'mtn', '{reference}',
              {AMOUNT_NGWEE}, 'ussd_pushed'
            ) ON CONFLICT (id) DO NOTHING;
            """
        )

    def test_apply_success_posts_escrow_hold_ledger_row(
        self,
        db: PgConn,
        db_url_env: None,
    ) -> None:
        payment_id = str(uuid.uuid4())
        reference = f"ord-{payment_id}"
        self._seed_checkout_with_order(db, payment_id=payment_id, reference=reference)

        fake = FakeSupabaseClient()
        fake.tables["checkout_groups"].rows.append(
            {"id": CHECKOUT_GROUP_ID, "total_ngwee": AMOUNT_NGWEE, "status": "completed"}
        )
        fake.tables["payments"].rows.append(
            {
                "id": payment_id,
                "checkout_group_id": CHECKOUT_GROUP_ID,
                "provider": "lenco",
                "rail": "mtn",
                "lenco_reference": reference,
                "amount_ngwee": AMOUNT_NGWEE,
                "status": "ussd_pushed",
                "raw": {},
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )

        outcome = apply_payment_status(
            FakeServiceClient(fake),
            payment_id=payment_id,
            incoming_status=PaymentStatus.SUCCESS,
            actor_id="00000000-0000-0000-0000-000000000001",
            note="Sandbox prepaid success",
        )
        assert outcome is not None
        assert outcome.to_status == PaymentStatus.SUCCESS

        row = db.run(
            f"""
            SELECT kind, idempotency_key
            FROM public.ledger_transactions
            WHERE order_id = '{ORDER_ID}'::uuid
            LIMIT 1;
            """
        )
        assert row.ok and row.rows
        kind, idem_key = row.rows[0].split("|")
        assert kind == LedgerTemplate.ESCROW_HOLD.value
        assert idem_key == escrow_hold_idempotency_key(ORDER_ID)

        postings = db.run(
            f"""
            SELECT la.kind, lp.amount_ngwee::text
            FROM public.ledger_postings lp
            JOIN public.ledger_accounts la ON la.id = lp.account_id
            JOIN public.ledger_transactions lt ON lt.id = lp.transaction_id
            WHERE lt.order_id = '{ORDER_ID}'::uuid
            ORDER BY la.kind;
            """
        )
        assert postings.ok
        assert postings.rows == ["escrow|-45000", "platform_cash|45000"]

    def test_duplicate_success_apply_is_idempotent_on_escrow_hold(
        self,
        db: PgConn,
        db_url_env: None,
    ) -> None:
        payment_id = str(uuid.uuid4())
        reference = f"ord-{payment_id}"
        self._seed_checkout_with_order(db, payment_id=payment_id, reference=reference)
        fake = FakeSupabaseClient()
        fake.tables["checkout_groups"].rows.append(
            {"id": CHECKOUT_GROUP_ID, "total_ngwee": AMOUNT_NGWEE, "status": "completed"}
        )
        fake.tables["payments"].rows.append(
            {
                "id": payment_id,
                "checkout_group_id": CHECKOUT_GROUP_ID,
                "provider": "lenco",
                "rail": "mtn",
                "lenco_reference": reference,
                "amount_ngwee": AMOUNT_NGWEE,
                "status": "success",
                "raw": {},
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )

        first = apply_payment_status(
            FakeServiceClient(fake),
            payment_id=payment_id,
            incoming_status=PaymentStatus.SUCCESS,
            actor_id="00000000-0000-0000-0000-000000000001",
            note="Replay",
        )
        assert first is None

        count = db.run(
            f"""
            SELECT count(*)::text
            FROM public.ledger_transactions
            WHERE order_id = '{ORDER_ID}'::uuid AND kind = 'escrow_hold';
            """
        )
        assert count.ok and count.rows == ["1"]
