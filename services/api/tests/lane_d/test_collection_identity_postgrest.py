"""Local D1 drill: signed API callback, JWT-scoped PostgREST, and real ledger."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.deps import get_supabase_client
from app.main import create_app
from app.services.payments.base import QueryStatusResult
from app.services.payments.reconcile import (
    drain_pending_webhook_events,
    poll_non_terminal_payments,
)
from app.services.payments.state import PaymentTransitionError, process_webhook_event
from app.services.payments.webhook_verify import SIGNATURE_HEADER
from fastapi.testclient import TestClient
from postgrest import SyncPostgrestClient
from tests.rls.conftest import PgConn

pytestmark = pytest.mark.prepaid_settlement_db


def _b64(document: dict[str, object]) -> str:
    raw = json.dumps(document, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _jwt(role: str, *, subject: str | None = None) -> str:
    secret = os.environ["LANE_D_JWT_SECRET"].encode()
    header = _b64({"alg": "HS256", "typ": "JWT"})
    payload: dict[str, object] = {
        "role": role,
        "aud": "authenticated",
        "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
    }
    if subject is not None:
        payload["sub"] = subject
    claims = _b64(payload)
    body = f"{header}.{claims}"
    signature = hmac.new(secret, body.encode(), hashlib.sha256).digest()
    return f"{body}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"


def _db() -> PgConn:
    return PgConn(os.environ["SUPABASE_DB_URL"])


def _service() -> SimpleNamespace:
    client = SyncPostgrestClient(
        os.environ["LANE_D_POSTGREST_URL"],
        headers={"Authorization": f"Bearer {_jwt('service_role')}"},
    )
    return SimpleNamespace(client=client)


def _seed_payment() -> tuple[str, str, str]:
    db = _db()
    customer_id = str(uuid4())
    checkout_id = str(uuid4())
    payment_id = str(uuid4())
    reference = f"ord-{payment_id}"
    provider_reference = f"lenco-local-{payment_id}"
    result = db.run_script(
        f"""
        BEGIN;
        INSERT INTO auth.users (id, email)
        VALUES ('{customer_id}', 'lane-d-{customer_id}@test.invalid');
        INSERT INTO public.checkout_groups (
          id, customer_id, idempotency_key, subtotal_ngwee,
          delivery_fee_ngwee, total_ngwee, status
        ) VALUES (
          '{checkout_id}', '{customer_id}', 'lane-d-{checkout_id}',
          25000, 0, 25000, 'completed'
        );
        INSERT INTO public.payments (
          id, checkout_group_id, provider, rail, lenco_reference,
          amount_ngwee, status, raw
        ) VALUES (
          '{payment_id}', '{checkout_id}', 'lenco', 'mtn', '{reference}',
          25000, 'ussd_pushed',
          '{{"provider_reference":"{provider_reference}"}}'::jsonb
        );
        INSERT INTO public.ledger_accounts (kind) VALUES
          ('platform_cash'), ('escrow')
        ON CONFLICT DO NOTHING;
        COMMIT;
        """
    )
    assert result.ok, result.error
    return payment_id, reference, provider_reference


def _post_signed_callback(
    service: SimpleNamespace,
    *,
    reference: str,
    provider_reference: str,
    amount: str | None,
    currency: str = "ZMW",
    event_id: str | None = None,
    event: str = "collection.successful",
    status: str = "successful",
    valid_signature: bool = True,
) -> int:
    token = os.environ["LANE_D_WEBHOOK_TOKEN"]
    body = json.dumps(
        {
            "event": event,
            "data": {
                "id": event_id or str(uuid4()),
                "reference": reference,
                "lencoReference": provider_reference,
                "status": status,
                "amount": amount,
                "currency": currency,
            },
        },
        separators=(",", ":"),
    ).encode()
    signing_key = hashlib.sha256(token.encode()).hexdigest().encode()
    signature = hmac.new(signing_key, body, hashlib.sha512).hexdigest()
    if not valid_signature:
        signature = "0" * len(signature)
    app = create_app()
    app.dependency_overrides[get_supabase_client] = lambda: service
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/webhooks/lenco", content=body, headers={SIGNATURE_HEADER: signature}
        )
    return int(response.status_code)


def _money_state(payment_id: str) -> tuple[int, int, int, str]:
    result = _db().run(
        f"""
        SELECT
          (SELECT count(*) FROM public.ledger_transactions
           WHERE payment_id = '{payment_id}'::uuid),
          (SELECT count(*) FROM public.webhook_events w
           JOIN public.payments p ON w.raw->'data'->>'reference' = p.lenco_reference
           WHERE p.id = '{payment_id}'::uuid AND w.processed_at IS NULL),
          (SELECT count(*) FROM (
             SELECT t.id FROM public.ledger_transactions t
             JOIN public.ledger_postings lp ON lp.transaction_id = t.id
             WHERE t.payment_id = '{payment_id}'::uuid
             GROUP BY t.id HAVING sum(lp.amount_ngwee) <> 0
           ) unbalanced),
          (SELECT status FROM public.payments WHERE id = '{payment_id}'::uuid);
        """
    )
    assert result.ok, result.error
    posted, pending, unbalanced, status = result.rows[0].split("|")
    return int(posted), int(pending), int(unbalanced), status


def test_signed_wrong_amount_cannot_credit_checkout() -> None:
    payment_id, reference, provider_reference = _seed_payment()
    service = _service()
    assert (
        service.client.table("payments")
        .select("id")
        .eq("id", payment_id)
        .execute()
        .data[0]["id"]
        == payment_id
    )
    assert _post_signed_callback(
        service,
        reference=reference,
        provider_reference=provider_reference,
        amount="1.00",
    ) == 200

    result = drain_pending_webhook_events(service)
    assert result.applied == 0 and result.errors >= 1
    assert _money_state(payment_id) == (0, 1, 0, "ussd_pushed")


def test_postgrest_honors_service_and_customer_claims() -> None:
    payment_id, _, _ = _seed_payment()
    service = _service()
    checkout = (
        service.client.table("payments")
        .select("checkout_group_id")
        .eq("id", payment_id)
        .execute()
        .data[0]["checkout_group_id"]
    )
    customer_id = (
        service.client.table("checkout_groups")
        .select("customer_id")
        .eq("id", checkout)
        .execute()
        .data[0]["customer_id"]
    )

    def customer_client(subject: str) -> SyncPostgrestClient:
        return SyncPostgrestClient(
            os.environ["LANE_D_POSTGREST_URL"],
            headers={"Authorization": f"Bearer {_jwt('authenticated', subject=subject)}"},
        )

    owner = customer_client(customer_id)
    stranger = customer_client(str(uuid4()))
    assert len(owner.table("payments").select("id").eq("id", payment_id).execute().data) == 1
    assert stranger.table("payments").select("id").eq("id", payment_id).execute().data == []
    assert owner.table("payments").update({"status": "success"}).eq(
        "id", payment_id
    ).execute().data == []
    assert _money_state(payment_id) == (0, 0, 0, "ussd_pushed")


@pytest.mark.parametrize(
    ("amount", "currency", "wrong_provider_reference"),
    [
        (None, "ZMW", False),
        ("250.00", "USD", False),
        ("250.00", "ZMW", True),
    ],
)
def test_signed_identity_mismatch_stays_pending(
    amount: str | None,
    currency: str,
    wrong_provider_reference: bool,
) -> None:
    payment_id, reference, provider_reference = _seed_payment()
    if wrong_provider_reference:
        provider_reference = "lenco-other-collection"
    service = _service()
    assert _post_signed_callback(
        service,
        reference=reference,
        provider_reference=provider_reference,
        amount=amount,
        currency=currency,
    ) == 200
    result = drain_pending_webhook_events(service)
    assert result.errors >= 1
    assert _money_state(payment_id) == (0, 1, 0, "ussd_pushed")


def test_valid_duplicate_callback_posts_one_balanced_charge() -> None:
    payment_id, reference, provider_reference = _seed_payment()
    service = _service()
    event_id = str(uuid4())
    for _ in range(2):
        assert _post_signed_callback(
            service,
            reference=reference,
            provider_reference=provider_reference,
            amount="250.00",
            event_id=event_id,
        ) == 200
    assert (
        len(
            service.client.table("webhook_events")
            .select("id")
            .eq("event_id", f"collection.successful:{event_id}")
            .execute()
            .data
        )
        == 1
    )
    drain_pending_webhook_events(service)
    drain_pending_webhook_events(service)
    assert _money_state(payment_id) == (1, 0, 0, "success")
    postings = _db().run(
        f"""
        SELECT la.kind, lp.amount_ngwee::text
        FROM public.ledger_transactions t
        JOIN public.ledger_postings lp ON lp.transaction_id = t.id
        JOIN public.ledger_accounts la ON la.id = lp.account_id
        WHERE t.payment_id = '{payment_id}'::uuid
        ORDER BY la.kind;
        """
    )
    assert postings.ok and postings.rows == ["escrow|-25000", "platform_cash|25000"]


def test_reordered_failed_and_success_callbacks_keep_one_charge() -> None:
    service = _service()
    payment_id, reference, provider_reference = _seed_payment()
    assert _post_signed_callback(
        service,
        reference=reference,
        provider_reference=provider_reference,
        amount="250.00",
        event="collection.failed",
        status="failed",
    ) == 200
    drain_pending_webhook_events(service)
    assert _money_state(payment_id) == (0, 0, 0, "failed")
    assert _post_signed_callback(
        service,
        reference=reference,
        provider_reference=provider_reference,
        amount="250.00",
    ) == 200
    drain_pending_webhook_events(service)
    assert _money_state(payment_id) == (1, 0, 0, "success")
    assert _post_signed_callback(
        service,
        reference=reference,
        provider_reference=provider_reference,
        amount="250.00",
        event="collection.failed",
        status="failed",
    ) == 200
    drain_pending_webhook_events(service)
    assert _money_state(payment_id) == (1, 0, 0, "success")


def test_concurrent_workers_cannot_double_post() -> None:
    payment_id, reference, provider_reference = _seed_payment()
    event_id = str(uuid4())
    service = _service()
    assert _post_signed_callback(
        service,
        reference=reference,
        provider_reference=provider_reference,
        amount="250.00",
        event_id=event_id,
    ) == 200
    webhook_id = (
        service.client.table("webhook_events")
        .select("id")
        .eq("event_id", f"collection.successful:{event_id}")
        .execute()
        .data[0]["id"]
    )
    barrier = Barrier(2)

    def work() -> None:
        barrier.wait(timeout=10)
        try:
            process_webhook_event(_service(), webhook_event_id=webhook_id)
        except PaymentTransitionError:
            # The losing worker may observe a concurrent guarded status change.
            pass

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(work) for _ in range(2)]
        for future in futures:
            future.result(timeout=30)
    assert _money_state(payment_id) == (1, 0, 0, "success")


def test_invalid_signature_never_persists_or_posts() -> None:
    payment_id, reference, provider_reference = _seed_payment()
    service = _service()
    event_id = str(uuid4())
    assert _post_signed_callback(
        service,
        reference=reference,
        provider_reference=provider_reference,
        amount="250.00",
        event_id=event_id,
        valid_signature=False,
    ) == 401
    assert (
        service.client.table("webhook_events")
        .select("id")
        .eq("event_id", f"collection.successful:{event_id}")
        .execute()
        .data
        == []
    )
    assert _money_state(payment_id) == (0, 0, 0, "ussd_pushed")


def test_transfer_status_cannot_confirm_collection() -> None:
    payment_id, reference, provider_reference = _seed_payment()
    service = _service()
    assert _post_signed_callback(
        service,
        reference=reference,
        provider_reference=provider_reference,
        amount="250.00",
        event="transfer.successful",
    ) == 200
    drain_pending_webhook_events(service)
    assert _money_state(payment_id) == (0, 0, 0, "ussd_pushed")


def test_unknown_merchant_reference_does_not_credit_payment() -> None:
    payment_id, _, provider_reference = _seed_payment()
    service = _service()
    assert _post_signed_callback(
        service,
        reference=f"ord-{uuid4()}",
        provider_reference=provider_reference,
        amount="250.00",
    ) == 200
    drain_pending_webhook_events(service)
    assert _money_state(payment_id) == (0, 0, 0, "ussd_pushed")


@pytest.mark.asyncio
async def test_poll_wrong_amount_cannot_credit_checkout() -> None:
    payment_id, reference, _ = _seed_payment()
    service = _service()

    async def wrong_value(_request: object) -> QueryStatusResult:
        return QueryStatusResult(
            reference=reference,
            status="successful",
            amount_major="1.00",
            currency="ZMW",
        )

    result = await poll_non_terminal_payments(
        service, query_status=wrong_value, older_than_minutes=-1
    )
    assert result.errors >= 1
    assert _money_state(payment_id) == (0, 0, 0, "ussd_pushed")


def test_unbalanced_posting_rolls_back_transaction() -> None:
    transaction_id = str(uuid4())
    result = _db().run_script(
        f"""
        BEGIN;
        INSERT INTO public.ledger_transactions (id, kind, idempotency_key)
        VALUES ('{transaction_id}', 'charge_received', 'lane-d-rollback-{transaction_id}');
        INSERT INTO public.ledger_postings (transaction_id, account_id, amount_ngwee)
        SELECT '{transaction_id}', id, 25000
        FROM public.ledger_accounts WHERE kind = 'platform_cash';
        COMMIT;
        """
    )
    assert not result.ok and "sum to zero" in str(result.error)
    lookup = _db().run(
        f"SELECT count(*)::text FROM public.ledger_transactions WHERE id = '{transaction_id}'"
    )
    assert lookup.ok and lookup.rows == ["0"]


@pytest.mark.xfail(
    strict=True,
    reason="S3 pre-existing late-success-after-cancelled path posts before rejecting transition",
)
def test_cancelled_payment_late_success_must_not_post() -> None:
    payment_id, reference, provider_reference = _seed_payment()
    service = _service()
    service.client.table("payments").update({"status": "cancelled"}).eq(
        "id", payment_id
    ).execute()
    assert _post_signed_callback(
        service,
        reference=reference,
        provider_reference=provider_reference,
        amount="250.00",
    ) == 200
    drain_pending_webhook_events(service)
    assert _money_state(payment_id) == (0, 1, 0, "cancelled")
