"""DB-backed prepaid collection settlement tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from app.services.ledger.engine import LedgerError
from app.services.ledger.templates import LedgerTemplate
from app.services.payments.reconcile import fetch_ledger_day_rows
from app.services.payments.settlement import (
    prepaid_collection_idempotency_key,
    settle_prepaid_collection,
)
from app.services.payments.state import (
    PaymentStatus,
    apply_payment_status,
    process_webhook_event,
)
from tests.rls.conftest import PgConn
from tests.test_payment_state import (
    FakeServiceClient,
    FakeSupabaseClient,
)

pytestmark = pytest.mark.prepaid_settlement_db

# Seeded by tests.test_ledger.db → seed_matrix_fixtures (pending checkout group).
CHECKOUT_GROUP_ID = "c1000000-0000-0000-0000-000000000002"
AMOUNT_NGWEE = 25_000


@pytest.fixture
def payment_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def fake_service() -> FakeServiceClient:
    fake = FakeSupabaseClient()
    fake.tables["checkout_groups"].rows.append(
        {
            "id": CHECKOUT_GROUP_ID,
            "total_ngwee": AMOUNT_NGWEE,
            "status": "pending",
        }
    )
    return FakeServiceClient(fake)


def _seed_db_payment(pg: PgConn, *, payment_id: str, reference: str) -> None:
    pg.run(
        f"""
        INSERT INTO public.payments (
          id, checkout_group_id, provider, rail, lenco_reference, amount_ngwee, status
        ) VALUES (
          '{payment_id}'::uuid,
          '{CHECKOUT_GROUP_ID}'::uuid,
          'lenco',
          'mtn',
          '{reference}',
          {AMOUNT_NGWEE},
          'ussd_pushed'
        )
        ON CONFLICT (id) DO NOTHING;
        """
    )


def _seed_ussd_payment(
    fake: FakeSupabaseClient,
    *,
    payment_id: str,
    status: str = "ussd_pushed",
    reference: str | None = None,
) -> None:
    stamp = datetime.now(UTC).isoformat()
    fake.tables["payments"].rows.append(
        {
            "id": payment_id,
            "checkout_group_id": CHECKOUT_GROUP_ID,
            "provider": "lenco",
            "rail": "mtn",
            "lenco_reference": reference or f"ord-{payment_id}",
            "amount_ngwee": AMOUNT_NGWEE,
            "status": status,
            "raw": {},
            "created_at": stamp,
            "updated_at": stamp,
        }
    )


def _seed_webhook(
    fake: FakeSupabaseClient,
    *,
    webhook_id: str,
    event_id: str,
    event: str,
    reference: str,
    processed_at: str | None = None,
) -> None:
    fake.tables["webhook_events"].rows.append(
        {
            "id": webhook_id,
            "provider": "lenco",
            "event_id": event_id,
            "signature_valid": True,
            "processed_at": processed_at,
            "created_at": datetime.now(UTC).isoformat(),
            "raw": {
                "event": event,
                "data": {
                    "id": event_id.split(":", 1)[-1],
                    "reference": reference,
                    "status": "successful" if "successful" in event else "settled",
                },
            },
        }
    )


def _ledger_txn_count(pg: PgConn, payment_id: str) -> int:
    result = pg.run(
        f"""
        SELECT count(*)::text
        FROM public.ledger_transactions
        WHERE payment_id = '{payment_id}'::uuid
          AND kind = 'charge_received';
        """
    )
    assert result.ok
    return int(result.rows[0])


def test_settlement_posts_balanced_charge_received(
    db: PgConn,
    fake_service: FakeServiceClient,
    payment_id: str,
) -> None:
    reference = f"ord-{payment_id}"
    _seed_db_payment(db, payment_id=payment_id, reference=reference)
    _seed_ussd_payment(fake_service.client, payment_id=payment_id, reference=reference)

    result = settle_prepaid_collection(
        fake_service,
        payment_id=payment_id,
        checkout_group_id=CHECKOUT_GROUP_ID,
        amount_ngwee=AMOUNT_NGWEE,
    )

    assert result.created is True
    assert _ledger_txn_count(db, payment_id) == 1

    postings = db.run(
        f"""
        SELECT la.kind, lp.amount_ngwee::text
        FROM public.ledger_postings lp
        JOIN public.ledger_accounts la ON la.id = lp.account_id
        JOIN public.ledger_transactions lt ON lt.id = lp.transaction_id
        WHERE lt.id = '{result.transaction_id}'::uuid
        ORDER BY la.kind;
        """
    )
    assert postings.ok
    assert postings.rows == ["escrow|-25000", "platform_cash|25000"]


def test_settlement_idempotent_by_payment_id(
    db: PgConn,
    fake_service: FakeServiceClient,
    payment_id: str,
) -> None:
    _seed_db_payment(db, payment_id=payment_id, reference=f"ord-{payment_id}")
    _seed_ussd_payment(fake_service.client, payment_id=payment_id)

    first = settle_prepaid_collection(
        fake_service,
        payment_id=payment_id,
        checkout_group_id=CHECKOUT_GROUP_ID,
        amount_ngwee=AMOUNT_NGWEE,
    )
    second = settle_prepaid_collection(
        fake_service,
        payment_id=payment_id,
        checkout_group_id=CHECKOUT_GROUP_ID,
        amount_ngwee=AMOUNT_NGWEE,
    )

    assert first.created is True
    assert second.created is False
    assert second.transaction_id == first.transaction_id
    assert _ledger_txn_count(db, payment_id) == 1


def test_apply_success_settles_before_status_transition(
    db: PgConn,
    fake_service: FakeServiceClient,
    payment_id: str,
) -> None:
    reference = f"ord-{payment_id}"
    _seed_db_payment(db, payment_id=payment_id, reference=reference)
    _seed_ussd_payment(fake_service.client, payment_id=payment_id, reference=reference)

    outcome = apply_payment_status(
        fake_service,
        payment_id=payment_id,
        incoming_status=PaymentStatus.SUCCESS,
        actor_id="00000000-0000-0000-0000-000000000001",
        note="Test prepaid success",
    )

    assert outcome is not None
    assert outcome.to_status == PaymentStatus.SUCCESS
    assert _ledger_txn_count(db, payment_id) == 1
    payment = fake_service.client.tables["payments"].rows[0]
    assert payment["status"] == PaymentStatus.SUCCESS.value


def test_duplicate_webhook_delivery_single_ledger_txn(
    db: PgConn,
    fake_service: FakeServiceClient,
    payment_id: str,
) -> None:
    reference = f"ord-{payment_id}"
    _seed_db_payment(db, payment_id=payment_id, reference=reference)
    _seed_ussd_payment(fake_service.client, payment_id=payment_id, reference=reference)
    webhook_id = str(uuid.uuid4())
    _seed_webhook(
        fake_service.client,
        webhook_id=webhook_id,
        event_id="collection.successful:evt-dup-1",
        event="collection.successful",
        reference=reference,
    )

    first = process_webhook_event(fake_service, webhook_event_id=webhook_id)
    second = process_webhook_event(fake_service, webhook_event_id=webhook_id)

    assert first is not None
    assert second is None
    assert _ledger_txn_count(db, payment_id) == 1


def test_webhook_and_card_parity_single_ledger_txn(
    db: PgConn,
    fake_service: FakeServiceClient,
    payment_id: str,
) -> None:
    """Webhook drain and a later apply_payment_status replay share one collection txn."""
    reference = f"ord-{payment_id}"
    _seed_db_payment(db, payment_id=payment_id, reference=reference)
    _seed_ussd_payment(fake_service.client, payment_id=payment_id, reference=reference)
    webhook_id = str(uuid.uuid4())
    _seed_webhook(
        fake_service.client,
        webhook_id=webhook_id,
        event_id="collection.successful:evt-parity-1",
        event="collection.successful",
        reference=reference,
    )

    webhook_outcome = process_webhook_event(fake_service, webhook_event_id=webhook_id)
    assert webhook_outcome is not None

    card_outcome = apply_payment_status(
        fake_service,
        payment_id=payment_id,
        incoming_status=PaymentStatus.SUCCESS,
        actor_id="00000000-0000-0000-0000-000000000001",
        note="Card verify replay",
    )
    assert card_outcome is None
    assert _ledger_txn_count(db, payment_id) == 1


def test_ledger_failure_blocks_payment_success(
    fake_service: FakeServiceClient,
    payment_id: str,
) -> None:
    _seed_ussd_payment(fake_service.client, payment_id=payment_id)

    with patch(
        "app.services.payments.settlement.post_transaction",
        side_effect=LedgerError("ledger post failed"),
    ):
        with pytest.raises(LedgerError):
            apply_payment_status(
                fake_service,
                payment_id=payment_id,
                incoming_status=PaymentStatus.SUCCESS,
                actor_id="00000000-0000-0000-0000-000000000001",
                note="Should fail closed",
            )

    payment = fake_service.client.tables["payments"].rows[0]
    assert payment["status"] == PaymentStatus.USSD_PUSHED.value
    assert fake_service.client.tables["audit_log"].rows == []


def test_reconciliation_visibility_payment_linked(
    db: PgConn,
    fake_service: FakeServiceClient,
    payment_id: str,
) -> None:
    _seed_db_payment(db, payment_id=payment_id, reference=f"ord-{payment_id}")
    _seed_ussd_payment(fake_service.client, payment_id=payment_id)
    settle_prepaid_collection(
        fake_service,
        payment_id=payment_id,
        checkout_group_id=CHECKOUT_GROUP_ID,
        amount_ngwee=AMOUNT_NGWEE,
    )

    row = db.run(
        f"""
        SELECT kind, payment_id::text, checkout_group_id::text, idempotency_key
        FROM public.ledger_transactions
        WHERE payment_id = '{payment_id}'::uuid;
        """
    )
    assert row.ok and len(row.rows) == 1
    kind, linked_payment_id, checkout_group_id, idempotency_key = row.rows[0].split("|")
    assert kind == LedgerTemplate.CHARGE_RECEIVED.value
    assert linked_payment_id == payment_id
    assert checkout_group_id == CHECKOUT_GROUP_ID
    assert idempotency_key == prepaid_collection_idempotency_key(payment_id)

    today = datetime.now(UTC).date()
    ledger_rows = fetch_ledger_day_rows(today)
    linked = [entry for entry in ledger_rows if entry.payment_id == payment_id]
    assert len(linked) == 1
    assert linked[0].amount_ngwee == AMOUNT_NGWEE
