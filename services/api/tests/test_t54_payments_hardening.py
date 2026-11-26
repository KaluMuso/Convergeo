"""T54: payments hardening — initiation failures, retry validation, fee booking."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from app.errors import AppError
from app.routers.checkout_payment import derive_momo_rail_from_number
from app.services.payments.base import (
    InitiateCollectionRequest,
    PaymentProviderError,
    ProviderOutcome,
    QueryStatusResult,
)
from app.services.payments.initiate import InitiatePaymentRequest, initiate_checkout_payment
from app.services.payments.lenco import client as lenco_client_module
from app.services.payments.lenco.client import LencoClient, LencoStrategy
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
    FakeTable,
)


class ChannelCheckedOutbox(FakeTable):
    """Mirrors the notification_outbox CHECK (channel in whatsapp/sms/email)."""

    def insert(self, payload: dict[str, Any]) -> Any:
        if payload.get("channel") not in {"whatsapp", "sms", "email"}:
            raise RuntimeError(
                "23514 new row violates check constraint notification_outbox_channel_check"
            )
        return super().insert(payload)


class StrictRpcSupabaseClient(FakeSupabaseClient):
    """Fake whose ``record_collection_failure`` enforces the real SQL checks.

    Mirrors supabase/migrations/20260929120000_*.sql ``record_collection_failure``:
    provider='lenco', reference == lenco_reference, currency == 'ZMW',
    amount_ngwee (bigint) == payments.amount_ngwee, provider_outcome == 'failed',
    and provider_reference equals the stored raw one when the payment has one.
    """

    def __init__(self) -> None:
        super().__init__()
        self.tables["notification_outbox"] = ChannelCheckedOutbox()

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
            definitive_rejection=True,
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


# --- Through LencoStrategy: only a positive rejection is terminal --------------------


def _initiate_request() -> InitiatePaymentRequest:
    return InitiatePaymentRequest(
        checkout_group_id=CHECKOUT_GROUP_ID,
        amount_ngwee=10_000,
        rail="mtn",
        phone="+260961234567",
    )


def _fresh_checkout_fake() -> StrictRpcSupabaseClient:
    fake = StrictRpcSupabaseClient()
    fake.tables["checkout_groups"].rows.append(
        {"id": CHECKOUT_GROUP_ID, "total_ngwee": 10_000, "status": "pending"}
    )
    return fake


async def _initiate_via_strategy(fake: StrictRpcSupabaseClient, strategy: LencoStrategy) -> Any:
    return await initiate_checkout_payment(
        FakeServiceClient(fake), _initiate_request(), strategy=strategy, actor_id=ACTOR_ID
    )


class _ParseFailureClient:
    async def initiate_collection(self, _request: Any) -> Any:
        raise ValueError("response parse failure after HTTP 200")


@pytest.mark.asyncio
async def test_strategy_parse_failure_after_200_stays_initiated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lenco_client_module, "payments_enabled", lambda: True)
    fake = _fresh_checkout_fake()
    result = await _initiate_via_strategy(fake, LencoStrategy(_ParseFailureClient()))  # type: ignore[arg-type]
    assert result.status == PaymentStatus.INITIATED
    payment = fake.tables["payments"].rows[0]
    assert payment["status"] == "initiated"
    assert "terminal_provider_failure" not in payment["raw"]


@pytest.mark.asyncio
async def test_strategy_200_without_data_stays_initiated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lenco_client_module, "payments_enabled", lambda: True)
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _r: httpx.Response(200, json={"status": True, "message": "ok", "data": None})
        ),
        base_url="https://api.lenco.co/access/v2",
    )
    strategy = LencoStrategy(
        LencoClient(http_client=http, token="t", base_url="https://api.lenco.co/access/v2")
    )
    fake = _fresh_checkout_fake()
    result = await _initiate_via_strategy(fake, strategy)
    assert result.status == PaymentStatus.INITIATED
    payment = fake.tables["payments"].rows[0]
    assert payment["status"] == "initiated"
    assert "terminal_provider_failure" not in payment["raw"]


@pytest.mark.asyncio
async def test_strategy_wrap_sites_flag_dispatch_may_have_succeeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lenco_client_module, "payments_enabled", lambda: True)
    request = InitiateCollectionRequest(
        reference="ord-x", amount_ngwee=1000, phone="+260971234567", operator="airtel"
    )
    with pytest.raises(PaymentProviderError) as parse_exc:
        await LencoStrategy(_ParseFailureClient()).initiate_collection(request)  # type: ignore[arg-type]
    assert parse_exc.value.dispatch_may_have_succeeded is True
    assert parse_exc.value.definitive_rejection is False


@pytest.mark.asyncio
@pytest.mark.parametrize(("status", "code"), [(400, "12"), (400, "01"), (422, "01")])
async def test_strategy_definitive_rejection_marks_failed_terminal(
    monkeypatch: pytest.MonkeyPatch, status: int, code: str
) -> None:
    monkeypatch.setattr(lenco_client_module, "payments_enabled", lambda: True)
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _r: httpx.Response(
                status, json={"status": False, "message": "invalid", "errorCode": code}
            )
        ),
        base_url="https://api.lenco.co/access/v2",
    )
    strategy = LencoStrategy(
        LencoClient(http_client=http, token="t", base_url="https://api.lenco.co/access/v2")
    )
    fake = _fresh_checkout_fake()
    with pytest.raises(AppError) as exc:
        await _initiate_via_strategy(fake, strategy)
    assert exc.value.code == "payment.initiation_rejected"
    payment = fake.tables["payments"].rows[0]
    assert payment["status"] == PaymentStatus.FAILED.value
    assert payment["raw"]["terminal_provider_failure"] is True


@pytest.mark.asyncio
async def test_unflagged_provider_error_is_never_terminal() -> None:
    """No flags at all (legacy/unknown wrap) must not be read as a refusal."""
    fake = _fresh_checkout_fake()
    strategy = MagicMock()
    strategy.initiate_collection = AsyncMock(side_effect=PaymentProviderError("x", "unknown"))
    result = await initiate_checkout_payment(
        FakeServiceClient(fake), _initiate_request(), strategy=strategy, actor_id=ACTOR_ID
    )
    assert result.status == PaymentStatus.INITIATED
    assert "terminal_provider_failure" not in fake.tables["payments"].rows[0]["raw"]


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
    assert err.definitive_rejection is True
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
    assert err.definitive_rejection is False


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
async def test_poller_not_found_stale_initiated_stays_non_terminal_and_alerts(
    caplog: pytest.LogCaptureFixture,
) -> None:
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
    assert result == PollResult(scanned=1, updated=0, unchanged=1, errors=0)
    # Admin-visible: one deduped audit_log row; nothing written to the outbox.
    assert fake.tables["notification_outbox"].rows == []
    audit = fake.tables["audit_log"].rows
    assert len(audit) == 1
    assert audit[0]["action"] == "payment.stale_initiated_not_found"
    assert audit[0]["entity_type"] == "payment"
    assert audit[0]["entity_id"] == pid
    assert audit[0]["after"]["needs_review"] is True
    assert audit[0]["after"]["checkout_group_id"] == CHECKOUT_GROUP_ID
    assert audit[0]["after"]["amount_ngwee"] == 25_000
    alert_records = [r for r in caplog.records if getattr(r, "alert", None)]
    assert [r.alert for r in alert_records] == ["payment_stale_initiated_not_found"]  # type: ignore[attr-defined]
    assert alert_records[0].levelno == logging.ERROR
    # A second tick must not duplicate the audit row (alert log still repeats).
    await poll_non_terminal_payments(
        FakeServiceClient(fake), query_status=query_status, older_than_minutes=1
    )
    assert len(fake.tables["audit_log"].rows) == 1


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


def test_late_collection_raises_structured_ops_alert(caplog: pytest.LogCaptureFixture) -> None:
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
    assert fake.tables["notification_outbox"].rows == []
    records = [r for r in caplog.records if getattr(r, "alert", None) == "payment_late_collection"]
    assert len(records) == 1
    assert records[0].levelno == logging.ERROR
    assert records[0].payment_id == "pay-late"  # type: ignore[attr-defined]
    assert records[0].amount_ngwee == 1_000  # type: ignore[attr-defined]


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
