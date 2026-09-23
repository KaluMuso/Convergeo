"""Local D1 drill: signed API callback, JWT-scoped PostgREST, and real ledger."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from app.deps import get_supabase_client
from app.main import create_app
from app.services.payments.base import QueryStatusResult
from app.services.payments.reconcile import (
    drain_pending_webhook_events,
    poll_non_terminal_payments,
)
from app.services.payments.state import (
    SYSTEM_ACTOR_ID,
    PaymentEvent,
    PaymentStatus,
    PaymentTransitionError,
    apply_payment_status,
    process_webhook_event,
    transition_payment,
)
from app.services.payments.webhook_verify import SIGNATURE_HEADER
from fastapi.testclient import TestClient
from postgrest import SyncPostgrestClient
from postgrest.exceptions import APIError
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
    unknown_reference = f"ord-{uuid4()}"
    event_id = str(uuid4())
    assert _post_signed_callback(
        service,
        reference=unknown_reference,
        provider_reference=provider_reference,
        amount="250.00",
        event_id=event_id,
    ) == 200
    drain_pending_webhook_events(service)
    assert _money_state(payment_id) == (0, 0, 0, "ussd_pushed")
    event = service.client.table("webhook_events").select(
        "id, processed_at, quarantine_reason"
    ).eq("event_id", f"collection.successful:{event_id}").single().execute().data
    assert isinstance(event, dict)
    assert event["processed_at"] is not None
    assert event["quarantine_reason"] == "unknown_merchant_reference"
    drain_pending_webhook_events(service)
    replay_guard = service.client.table("webhook_events").select(
        "processed_at, quarantine_reason"
    ).eq("id", str(event["id"])).single().execute().data
    assert isinstance(replay_guard, dict)
    assert replay_guard["processed_at"] is not None
    assert replay_guard["quarantine_reason"] == "unknown_merchant_reference"

    # An operator can associate the previously unknown reference and replay the
    # retained signed observation; it was not silently discarded or poison-looped.
    service.client.table("payments").update(
        {"lenco_reference": unknown_reference}
    ).eq("id", payment_id).execute()
    service.client.table("webhook_events").update(
        {
            "processed_at": None,
            "quarantine_reason": None,
            "quarantined_at": None,
        }
    ).eq("id", str(event["id"])).execute()
    assert drain_pending_webhook_events(service).applied == 1
    assert _money_state(payment_id) == (1, 0, 0, "success")


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
    assert _money_state(payment_id) == (0, 0, 0, "cancelled")
    result = _db().run(
        f"""
        SELECT
          (SELECT count(*) FROM public.payment_collection_exceptions
           WHERE payment_id = '{payment_id}'::uuid
             AND reason = 'payment_cancelled'),
          (SELECT count(*) FROM public.notification_outbox
           WHERE payload->>'payment_id' = '{payment_id}');
        """
    )
    assert result.ok and result.rows == ["1|0"], result.error


def _observation(reference: str, provider_reference: str, source: str) -> dict[str, Any]:
    return {
        "reference": reference,
        "provider_reference": provider_reference,
        "amount_ngwee": 25000,
        "currency": "ZMW",
        "source": source,
    }


def _counts(payment_id: str) -> tuple[int, int, int, int]:
    result = _db().run(
        f"""
        SELECT
          (SELECT count(*) FROM public.ledger_transactions
           WHERE payment_id = '{payment_id}'::uuid),
          (SELECT count(*) FROM public.notification_outbox
           WHERE payload->>'payment_id' = '{payment_id}'),
          (SELECT count(*) FROM public.payment_collection_exceptions
           WHERE payment_id = '{payment_id}'::uuid),
          (SELECT count(*) FROM public.audit_log
           WHERE entity_type = 'payment'
             AND entity_id = '{payment_id}'::uuid
             AND action = 'payment.transition');
        """
    )
    assert result.ok, result.error
    return tuple(int(value) for value in result.rows[0].split("|"))  # type: ignore[return-value]


def _wait_for_db_lock(locktype: str) -> None:
    for _ in range(200):
        waiting = _db().run(
            "SELECT count(*) FROM pg_locks WHERE NOT granted "
            f"AND locktype = '{locktype}'"
        )
        assert waiting.ok, waiting.error
        if int(waiting.rows[0]) > 0:
            return
        time.sleep(0.05)
    raise AssertionError(f"expected blocked {locktype} lock was not observed")


def test_customer_claim_cannot_invoke_atomic_collection_rpc() -> None:
    payment_id, reference, provider_reference = _seed_payment()
    customer_id = _db().run(
        f"""
        SELECT c.customer_id FROM public.payments p
        JOIN public.checkout_groups c ON c.id = p.checkout_group_id
        WHERE p.id = '{payment_id}'::uuid
        """
    )
    assert customer_id.ok and customer_id.rows
    customer = SyncPostgrestClient(
        os.environ["LANE_D_POSTGREST_URL"],
        headers={"Authorization": f"Bearer {_jwt('authenticated', subject=customer_id.rows[0])}"},
    )
    params: dict[str, Any] = {
        "p_payment_id": payment_id,
        "p_actor_id": SYSTEM_ACTOR_ID,
        "p_note": "unauthorized customer attempt",
        "p_observation": _observation(reference, provider_reference, "customer"),
    }
    with pytest.raises(APIError):
        customer.rpc("apply_prepaid_collection_success", params).execute()
    assert _money_state(payment_id) == (0, 0, 0, "ussd_pushed")
    assert _counts(payment_id) == (0, 0, 0, 0)


def test_committed_success_survives_lost_response_and_duplicate_poll() -> None:
    payment_id, reference, provider_reference = _seed_payment()
    service = _service()
    observation = _observation(reference, provider_reference, "poller")
    first = apply_payment_status(
        service, payment_id=payment_id, incoming_status=PaymentStatus.SUCCESS,
        actor_id=SYSTEM_ACTOR_ID, note="simulated poll response lost",
        observation=observation,
    )
    assert first is not None and first.to_status == PaymentStatus.SUCCESS
    # The caller discards the first response and retries with a new HTTP/DB connection.
    replay = apply_payment_status(
        _service(), payment_id=payment_id, incoming_status=PaymentStatus.SUCCESS,
        actor_id=SYSTEM_ACTOR_ID, note="poll retry after lost response",
        observation=observation,
    )
    assert replay is None
    assert _money_state(payment_id) == (1, 0, 0, "success")
    assert _counts(payment_id) == (1, 1, 0, 1)
    with pytest.raises(PaymentTransitionError):
        transition_payment(
            _service(), payment_id=payment_id, event=PaymentEvent.CANCELLED,
            actor_id=SYSTEM_ACTOR_ID, note="cancellation after committed collection",
        )


def test_webhook_and_poll_race_claim_one_receipt_and_outbox_intent() -> None:
    payment_id, reference, provider_reference = _seed_payment()
    service = _service()
    event_id = str(uuid4())
    assert _post_signed_callback(
        service, reference=reference, provider_reference=provider_reference,
        amount="250.00", event_id=event_id,
    ) == 200
    event = service.client.table("webhook_events").select("id").eq(
        "event_id", f"collection.successful:{event_id}"
    ).single().execute().data
    assert isinstance(event, dict)
    barrier = Barrier(3)

    def webhook() -> object:
        barrier.wait()
        return process_webhook_event(_service(), webhook_event_id=str(event["id"]))

    def poll() -> object:
        barrier.wait()
        return apply_payment_status(
            _service(), payment_id=payment_id,
            incoming_status=PaymentStatus.SUCCESS, actor_id=SYSTEM_ACTOR_ID,
            note="concurrent poll observed provider success",
            observation=_observation(reference, provider_reference, "poller"),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        webhook_result = pool.submit(webhook)
        poll_result = pool.submit(poll)
        barrier.wait()
        outcomes = (webhook_result.result(timeout=20), poll_result.result(timeout=20))
    assert sum(outcome is not None for outcome in outcomes) == 1
    assert _money_state(payment_id) == (1, 0, 0, "success")
    assert _counts(payment_id) == (1, 1, 0, 1)


def test_multi_order_escrow_allocation_is_balanced_and_not_seller_available() -> None:
    payment_id, reference, provider_reference = _seed_payment()
    vendor_owner = str(uuid4())
    vendor_id = str(uuid4())
    second_vendor_id = str(uuid4())
    first_order = str(uuid4())
    second_order = str(uuid4())
    customer = _db().run(
        f"""
        SELECT c.customer_id FROM public.payments p
        JOIN public.checkout_groups c ON c.id = p.checkout_group_id
        WHERE p.id = '{payment_id}'::uuid
        """
    )
    checkout = _db().run(
        f"SELECT checkout_group_id FROM public.payments WHERE id = '{payment_id}'::uuid"
    )
    assert customer.ok and checkout.ok
    seed = _db().run_script(
        f"""
        BEGIN;
        INSERT INTO auth.users (id, email)
        VALUES ('{vendor_owner}', 'd2-vendor-{vendor_owner}@test.invalid');
        INSERT INTO public.vendors (id, owner_user_id, slug, display_name, status)
        VALUES
          ('{vendor_id}', '{vendor_owner}', 'd2-{vendor_id}', 'D2 vendor A', 'active'),
          ('{second_vendor_id}', '{vendor_owner}', 'd2-{second_vendor_id}',
           'D2 vendor B', 'active');
        INSERT INTO public.orders (
          id, checkout_group_id, vendor_id, customer_id, status, fulfilment, cod
        ) VALUES
          ('{first_order}', '{checkout.rows[0]}', '{vendor_id}',
           '{customer.rows[0]}', 'placed', 'pickup', false),
          ('{second_order}', '{checkout.rows[0]}', '{second_vendor_id}',
           '{customer.rows[0]}', 'placed', 'pickup', false);
        INSERT INTO public.order_items (
          order_id, item_kind, qty, unit_price_ngwee, title_snapshot
        ) VALUES
          ('{first_order}', 'product', 1, 10000, 'D2 line A'),
          ('{second_order}', 'product', 1, 15000, 'D2 line B');
        COMMIT;
        """
    )
    assert seed.ok, seed.error
    outcome = apply_payment_status(
        _service(), payment_id=payment_id,
        incoming_status=PaymentStatus.SUCCESS, actor_id=SYSTEM_ACTOR_ID,
        note="two-order prepaid settlement",
        observation=_observation(reference, provider_reference, "poller"),
    )
    assert outcome is not None
    result = _db().run(
        f"""
        SELECT
          (SELECT count(*) FROM public.ledger_transactions
           WHERE payment_id = '{payment_id}'::uuid AND kind = 'escrow_hold'),
          (SELECT coalesce(sum(lp.amount_ngwee), 0)
           FROM public.ledger_transactions t
           JOIN public.ledger_postings lp ON lp.transaction_id = t.id
           WHERE t.payment_id = '{payment_id}'::uuid),
          (SELECT count(*) FROM public.ledger_transactions t
           JOIN public.ledger_postings lp ON lp.transaction_id = t.id
           JOIN public.ledger_accounts a ON a.id = lp.account_id
           WHERE t.payment_id = '{payment_id}'::uuid
             AND a.kind = 'vendor_payable'),
          (SELECT count(*) FROM public.notification_outbox
           WHERE dedupe_key IN (
             'order_placed:{first_order}:whatsapp',
             'order_placed:{second_order}:whatsapp'
           ));
        """
    )
    assert result.ok and result.rows == ["2|0|0|2"], result.error


@pytest.mark.parametrize("prior_status", ["failed", "expired"])
def test_late_success_after_failed_or_expired_is_still_legal(prior_status: str) -> None:
    payment_id, reference, provider_reference = _seed_payment()
    service = _service()
    service.client.table("payments").update({"status": prior_status}).eq(
        "id", payment_id
    ).execute()
    outcome = apply_payment_status(
        service, payment_id=payment_id, incoming_status=PaymentStatus.SUCCESS,
        actor_id=SYSTEM_ACTOR_ID, note="late provider collection",
        observation=_observation(reference, provider_reference, "poller"),
    )
    assert outcome is not None and outcome.from_status.value == prior_status
    assert _money_state(payment_id) == (1, 0, 0, "success")
    assert _counts(payment_id) == (1, 1, 0, 1)


def test_cancel_wins_while_success_waits_on_checkout_lock() -> None:
    payment_id, reference, provider_reference = _seed_payment()
    service = _service()
    event_id = str(uuid4())
    assert _post_signed_callback(
        service, reference=reference, provider_reference=provider_reference,
        amount="250.00", event_id=event_id,
    ) == 200
    row = service.client.table("webhook_events").select("id").eq(
        "event_id", f"collection.successful:{event_id}"
    ).single().execute().data
    assert isinstance(row, dict)
    checkout = _db().run(
        f"SELECT checkout_group_id FROM public.payments WHERE id = '{payment_id}'::uuid"
    )
    assert checkout.ok and checkout.rows
    with psycopg.connect(os.environ["SUPABASE_DB_URL"]) as blocker:
        with blocker.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM public.checkout_groups WHERE id = %s FOR UPDATE",
                (checkout.rows[0],),
            )
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                process_webhook_event, _service(), webhook_event_id=str(row["id"])
            )
            try:
                _wait_for_db_lock("transactionid")
                service.client.table("payments").update({"status": "cancelled"}).eq(
                    "id", payment_id
                ).eq("status", "ussd_pushed").execute()
            finally:
                blocker.commit()
            assert future.result(timeout=20) is None
    assert _money_state(payment_id) == (0, 0, 0, "cancelled")
    assert _counts(payment_id) == (0, 0, 1, 0)


def test_success_wins_while_cancellation_waits_on_payment_lock() -> None:
    payment_id, reference, provider_reference = _seed_payment()
    service = _service()
    event_id = str(uuid4())
    assert _post_signed_callback(
        service, reference=reference, provider_reference=provider_reference,
        amount="250.00", event_id=event_id,
    ) == 200
    row = service.client.table("webhook_events").select("id").eq(
        "event_id", f"collection.successful:{event_id}"
    ).single().execute().data
    assert isinstance(row, dict)
    lock_key = 2026092302
    setup = _db().run_script(
        f"""
        CREATE FUNCTION public.lane_d2_wait_allocation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.payment_id = '{payment_id}'::uuid THEN
            PERFORM pg_advisory_xact_lock({lock_key});
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER lane_d2_wait_allocation
        BEFORE INSERT ON public.ledger_transactions
        FOR EACH ROW EXECUTE FUNCTION public.lane_d2_wait_allocation();
        """
    )
    assert setup.ok, setup.error
    try:
        with psycopg.connect(os.environ["SUPABASE_DB_URL"], autocommit=True) as blocker:
            blocker.execute("SELECT pg_advisory_lock(%s)", (lock_key,))
            with ThreadPoolExecutor(max_workers=2) as pool:
                success = pool.submit(
                    process_webhook_event, _service(), webhook_event_id=str(row["id"])
                )
                _wait_for_db_lock("advisory")
                cancel = pool.submit(
                    lambda: _service().client.table("payments").update(
                        {"status": "cancelled"}
                    ).eq("id", payment_id).eq("status", "ussd_pushed").execute()
                )
                try:
                    _wait_for_db_lock("transactionid")
                finally:
                    blocker.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))
                assert success.result(timeout=20) is not None
                cancel.result(timeout=20)
    finally:
        cleanup = _db().run_script(
            "DROP TRIGGER IF EXISTS lane_d2_wait_allocation "
            "ON public.ledger_transactions; "
            "DROP FUNCTION IF EXISTS public.lane_d2_wait_allocation();"
        )
        assert cleanup.ok, cleanup.error
    assert _money_state(payment_id) == (1, 0, 0, "success")
    assert _counts(payment_id) == (1, 1, 0, 1)


def test_notification_failure_rolls_back_status_allocation_and_claim() -> None:
    payment_id, reference, provider_reference = _seed_payment()
    setup = _db().run_script(
        f"""
        CREATE FUNCTION public.lane_d2_fail_outbox() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.payload->>'payment_id' = '{payment_id}' THEN
            RAISE EXCEPTION 'injected outbox failure';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER lane_d2_fail_outbox
        BEFORE INSERT ON public.notification_outbox
        FOR EACH ROW EXECUTE FUNCTION public.lane_d2_fail_outbox();
        """
    )
    assert setup.ok, setup.error
    try:
        with pytest.raises(Exception, match="injected outbox failure"):
            apply_payment_status(
                _service(), payment_id=payment_id,
                incoming_status=PaymentStatus.SUCCESS, actor_id=SYSTEM_ACTOR_ID,
                note="partial failure injection",
                observation=_observation(reference, provider_reference, "poller"),
            )
        assert _money_state(payment_id) == (0, 0, 0, "ussd_pushed")
        assert _counts(payment_id) == (0, 0, 0, 0)
    finally:
        cleanup = _db().run_script(
            "DROP TRIGGER IF EXISTS lane_d2_fail_outbox "
            "ON public.notification_outbox; "
            "DROP FUNCTION IF EXISTS public.lane_d2_fail_outbox();"
        )
        assert cleanup.ok, cleanup.error
    outcome = apply_payment_status(
        _service(), payment_id=payment_id,
        incoming_status=PaymentStatus.SUCCESS, actor_id=SYSTEM_ACTOR_ID,
        note="retry after rolled-back failure",
        observation=_observation(reference, provider_reference, "poller"),
    )
    assert outcome is not None
    assert _counts(payment_id) == (1, 1, 0, 1)
