"""T54: payments hardening — initiation failures, retry validation, fee booking."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from app.errors import AppError
from app.routers.checkout_payment import derive_momo_rail_from_number
from app.services.payments.base import (
    PaymentProviderError,
    ProviderOutcome,
    QueryStatusResult,
)
from app.services.payments.initiate import InitiatePaymentRequest, initiate_checkout_payment
from app.services.payments.lenco.client import LencoClient
from app.services.payments.lenco.models import LencoClientError, LencoCollectionRequest
from app.services.payments.reconcile import PollResult, poll_non_terminal_payments
from app.services.payments.state import (
    PaymentStatus,
    apply_payment_status,
    collection_observation_from_query,
    sweep_stale_payments,
)
from tests.test_payment_state import (
    ACTOR_ID,
    CHECKOUT_GROUP_ID,
    FakeServiceClient,
    FakeSupabaseClient,
)


class StrictRpcSupabaseClient(FakeSupabaseClient):
    """Fake whose ``record_collection_failure`` enforces the real SQL checks.

    Mirrors supabase/migrations/20260929120000_*.sql ``record_collection_failure``:
    provider='lenco', reference == lenco_reference, currency == 'ZMW',
    amount_ngwee (bigint) == payments.amount_ngwee, provider_outcome == 'failed',
    and provider_reference equals the stored raw one when the payment has one.
    """

    def __init__(self) -> None:
        super().__init__()
        self.tables["notification_outbox"] = type(self.tables["payments"])()

    def rpc(self, name: str, params: dict[str, Any]) -> Any:
        if name != "record_collection_failure":
            return super().rpc(name, params)
        payment = next(r for r in self.tables["payments"].rows if r["id"] == params["p_payment_id"])
        obs = params["p_observation"]
        json.dumps(obs)  # must be JSON-serialisable like a jsonb argument
        stored_provider_ref = (payment.get("raw") or {}).get("provider_reference")
        if (
            payment["provider"] != "lenco"
            or obs.get("reference") != payment["lenco_reference"]
            or obs.get("currency") != "ZMW"
            or int(obs["amount_ngwee"]) != payment["amount_ngwee"]
            or obs.get("provider_outcome") != "failed"
            or (stored_provider_ref and stored_provider_ref != obs.get("provider_reference"))
        ):
            raise RuntimeError("terminal collection identity mismatch")
        if payment["status"] != "success":
            payment["raw"].update({"terminal_provider_failure": True, "terminal_observation": obs})
        return MagicMock(execute=lambda: MagicMock(data=None))


def test_strict_rpc_rejects_observation_without_provider_outcome() -> None:
    """Guards the simulator itself: the pre-fix payload shape must be refused."""
    fake = StrictRpcSupabaseClient()
    fake.tables["payments"].rows.append(
        {
            "id": "p1",
            "provider": "lenco",
            "lenco_reference": "ord-x",
            "amount_ngwee": 100,
            "status": "initiated",
            "raw": {},
        }
    )
    with pytest.raises(RuntimeError, match="identity mismatch"):
        fake.rpc(
            "record_collection_failure",
            {
                "p_payment_id": "p1",
                "p_observation": {
                    "reference": "ord-x",
                    "amount_ngwee": 100,
                    "currency": "ZMW",
                    "source": "initiation_rejected",
                    "terminal_provider_failure": True,
                },
            },
        )


def test_derive_momo_rail_from_number() -> None:
    assert derive_momo_rail_from_number("+260961234567") == "mtn"
    assert derive_momo_rail_from_number("+260971234567") == "airtel"


@pytest.mark.asyncio
async def test_initiate_terminal_rejection_marks_failed() -> None:
    fake = StrictRpcSupabaseClient()
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
    assert payment["raw"]["terminal_observation"]["provider_outcome"] == "failed"


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


@pytest.mark.asyncio
async def test_initiate_ambiguous_failure_stays_initiated_without_terminal_flag() -> None:
    fake = StrictRpcSupabaseClient()
    fake.tables["checkout_groups"].rows.append(
        {"id": CHECKOUT_GROUP_ID, "total_ngwee": 10_000, "status": "pending"}
    )
    strategy = MagicMock()
    strategy.initiate_collection = AsyncMock(
        side_effect=PaymentProviderError("timeout", "lost", dispatch_may_have_succeeded=True)
    )
    result = await initiate_checkout_payment(
        FakeServiceClient(fake),
        InitiatePaymentRequest(
            checkout_group_id=CHECKOUT_GROUP_ID,
            amount_ngwee=10_000,
            rail="mtn",
            phone="+260961234567",
        ),
        strategy=strategy,
        actor_id=ACTOR_ID,
    )
    assert result.status == PaymentStatus.INITIATED
    payment = fake.tables["payments"].rows[0]
    assert payment["status"] == "initiated"
    assert "terminal_provider_failure" not in payment["raw"]


# --- LencoClient.initiate_collection: dispatch_may_have_succeeded ---------------------


def _collection_request() -> LencoCollectionRequest:
    return LencoCollectionRequest(
        amount_major="10.00", reference="ord-d-1", phone="0961111111", operator="mtn"
    )


async def _initiate_with(handler: Any) -> LencoClientError:
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.lenco.co/access/v2"
    )
    client = LencoClient(http_client=http, token="t", base_url="https://api.lenco.co/access/v2")
    with pytest.raises(LencoClientError) as exc:
        await client.initiate_collection(_collection_request())
    return exc.value


@pytest.mark.asyncio
@pytest.mark.parametrize(("status", "code"), [(400, "12"), (400, "01"), (422, "01")])
async def test_definitive_validation_rejection_is_not_dispatch_may_have_succeeded(
    status: int, code: str
) -> None:
    err = await _initiate_with(
        lambda _r: httpx.Response(
            status, json={"status": False, "message": "invalid", "errorCode": code}
        )
    )
    assert err.dispatch_may_have_succeeded is False
    assert err.observation_uncertain is False
    assert err.kind.value == "provider"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, json={"status": False, "message": "boom"}),
        httpx.Response(503, json={"status": False, "message": "down"}),
        # 04 = duplicate reference: a collection may already exist.
        httpx.Response(400, json={"status": False, "message": "dup", "errorCode": "04"}),
        httpx.Response(400, json={"status": False, "message": "no code"}),
        httpx.Response(401, json={"status": False, "message": "auth", "errorCode": "09"}),
        httpx.Response(200, json={"status": False, "message": "soft", "errorCode": "12"}),
    ],
)
async def test_ambiguous_http_failures_keep_dispatch_may_have_succeeded(
    response: httpx.Response,
) -> None:
    err = await _initiate_with(lambda _r: response)
    assert err.dispatch_may_have_succeeded is True


@pytest.mark.asyncio
async def test_timeout_and_network_keep_dispatch_may_have_succeeded() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("lost", request=request)

    def network(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    assert (await _initiate_with(timeout)).dispatch_may_have_succeeded is True
    assert (await _initiate_with(network)).dispatch_may_have_succeeded is True


# --- Poller ----------------------------------------------------------------------------


def _seed_poll_payment(
    fake: FakeSupabaseClient, *, status: str, age_minutes: int, payment_id: str | None = None
) -> str:
    pid = payment_id or str(uuid.uuid4())
    fake.tables["payments"].rows.append(
        {
            "id": pid,
            "checkout_group_id": CHECKOUT_GROUP_ID,
            "status": status,
            "lenco_reference": f"ord-{pid[:8]}",
            "amount_ngwee": 25_000,
            "rail": "mtn",
            "provider": "lenco",
            "raw": {},
            "updated_at": (datetime.now(UTC) - timedelta(minutes=age_minutes)).isoformat(),
        }
    )
    return pid


@pytest.mark.asyncio
async def test_poller_not_found_stale_initiated_stays_non_terminal_and_alerts() -> None:
    fake = StrictRpcSupabaseClient()
    pid = _seed_poll_payment(fake, status="initiated", age_minutes=120)

    async def query_status(request: Any) -> QueryStatusResult:
        return QueryStatusResult(
            requested_reference=request.reference,
            outcome=ProviderOutcome.NOT_FOUND,
            raw={"error_code": "11"},
        )

    result = await poll_non_terminal_payments(
        FakeServiceClient(fake), query_status=query_status, older_than_minutes=1
    )
    payment = fake.tables["payments"].rows[0]
    assert payment["status"] == "initiated"
    # Never grant a second claim: no terminal_provider_failure, no release.
    assert "terminal_provider_failure" not in payment["raw"]
    assert fake.tables["audit_log"].rows == []
    assert result == PollResult(scanned=1, updated=0, unchanged=1, errors=0)
    alerts = fake.tables["notification_outbox"].rows
    assert len(alerts) == 1
    assert alerts[0]["payload"]["payment_id"] == pid
    assert alerts[0]["payload"]["needs_review"] is True
    assert alerts[0]["payload"]["checkout_group_id"] == CHECKOUT_GROUP_ID
    assert alerts[0]["payload"]["amount_ngwee"] == 25_000


@pytest.mark.asyncio
async def test_poller_failed_observation_passes_strict_rpc_checks() -> None:
    fake = StrictRpcSupabaseClient()
    pid = _seed_poll_payment(fake, status="ussd_pushed", age_minutes=120)
    reference = fake.tables["payments"].rows[0]["lenco_reference"]

    async def query_status(request: Any) -> QueryStatusResult:
        return QueryStatusResult(
            requested_reference=request.reference,
            outcome=ProviderOutcome.FAILED,
            status="failed",
            reference=reference,
            amount_major="250.00",
            currency="ZMW",
            provider_reference="lenco-1",
            raw={},
        )

    result = await poll_non_terminal_payments(
        FakeServiceClient(fake), query_status=query_status, older_than_minutes=1
    )
    assert result.errors == 0
    payment = next(r for r in fake.tables["payments"].rows if r["id"] == pid)
    assert payment["status"] == "failed"
    assert payment["raw"]["terminal_provider_failure"] is True
    obs = collection_observation_from_query(
        QueryStatusResult(
            requested_reference=reference,
            outcome=ProviderOutcome.FAILED,
            status="failed",
            reference=reference,
            amount_major="250.00",
            currency="ZMW",
            provider_reference="lenco-1",
            raw={},
        ),
        source="poller",
    )
    assert obs["provider_outcome"] == "failed"


# --- Late collection alert & fee idempotency ------------------------------------------


def test_late_collection_enqueues_ops_alert() -> None:
    fake = StrictRpcSupabaseClient()
    fake.tables["payments"].rows.append(
        {
            "id": "pay-late",
            "checkout_group_id": CHECKOUT_GROUP_ID,
            "provider": "lenco",
            "rail": "mtn",
            "lenco_reference": "ord-late",
            "amount_ngwee": 1_000,
            "status": "cancelled",
            "raw": {},
        }
    )
    outcome = apply_payment_status(
        FakeServiceClient(fake),
        payment_id="pay-late",
        incoming_status=PaymentStatus.SUCCESS,
        actor_id=ACTOR_ID,
        note="late",
        observation={
            "reference": "ord-late",
            "amount_ngwee": 1_000,
            "currency": "ZMW",
            "source": "test",
            "canonical_status_verified": True,
            "provider_outcome": "successful",
        },
    )
    assert outcome is None
    rows = fake.tables["notification_outbox"].rows
    assert len(rows) == 1
    assert rows[0]["template"] == "payment_late_collection_ops"
    assert rows[0]["payload"]["payment_id"] == "pay-late"
    assert rows[0]["payload"]["amount_ngwee"] == 1_000


def test_book_collection_fee_is_idempotent_per_payment(monkeypatch: pytest.MonkeyPatch) -> None:
    """The ledger engine dedupes on idempotency_key; the key must be stable per payment."""
    from app.services.payments import fees

    posted: dict[str, int] = {}

    def fake_post(*, idempotency_key: str, fee_ngwee: int, **_kw: Any) -> object:
        posted.setdefault(idempotency_key, fee_ngwee)  # engine: same key -> no re-post
        return object()

    monkeypatch.setattr(fees, "post_transaction", fake_post)
    fees.book_collection_fee(payment_id="pay-1", fee="0.25", bearer="merchant")
    fees.book_collection_fee(payment_id="pay-1", fee="0.25", bearer="merchant")
    assert posted == {"lenco-fee-collection-pay-1": 25}


# --- Sweeper ----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sweeper_initiated_pay_offline_does_not_attempt_illegal_transition() -> None:
    fake = StrictRpcSupabaseClient()
    fake.tables["platform_config"].rows.clear()
    stuck = _seed_poll_payment(fake, status="initiated", age_minutes=120)
    ussd = _seed_poll_payment(fake, status="ussd_pushed", age_minutes=120)

    async def query_status(request: Any) -> QueryStatusResult:
        return QueryStatusResult(
            requested_reference=request.reference,
            outcome=ProviderOutcome.PENDING,
            status="pay-offline",
            reference=request.reference,
            amount_major="250.00",
            currency="ZMW",
            provider_reference="lenco-x",
            raw={},
        )

    result = await sweep_stale_payments(FakeServiceClient(fake), query_status=query_status)
    by_id = {r["id"]: r for r in fake.tables["payments"].rows}
    assert result.scanned == 2
    assert by_id[stuck]["status"] == "initiated"  # untouched, no abort of the batch
    assert by_id[ussd]["status"] == "pay_offline"  # rest of batch still processed
