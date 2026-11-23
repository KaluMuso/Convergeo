"""Customer-borne Lenco collection fee (bearer=customer) — config, payloads, ledger.

Business rule: the customer pays Lenco's collection fee on top of the order
total. Lenco charges the payer ``amount + fee`` and settles ``amount`` to us, so
the ledger records exactly ``payment.amount_ngwee`` collected and books NO fee
expense. ``LENCO_COLLECTION_FEE_BEARER=merchant`` is the rollback and must keep
the historical behaviour (fee netted from settlement, booked to ``fees``).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.main import create_app
from app.services.ledger.engine import PostedTransaction
from app.services.ledger.templates import LedgerTemplate, lenco_fee
from app.services.payments import fees as fees_mod
from app.services.payments.base import (
    CollectionStatus,
    InitiateCollectionRequest,
    InitiateCollectionResult,
    QueryStatusResult,
)
from app.services.payments.bearer import (
    LENCO_COLLECTION_FEE_BEARER_ENV,
    RAW_BEARER_KEY,
    InvalidBearerConfigError,
    get_collection_fee_bearer,
    net_collected_ngwee,
    normalize_observation_amount,
    resolve_collection_bearer,
)
from app.services.payments.initiate import InitiatePaymentRequest, initiate_checkout_payment
from app.services.payments.lenco.client import LencoClient
from app.services.payments.lenco.models import LencoCollectionRequest
from app.services.payments.reconcile import (
    LedgerDayRow,
    LencoTransactionRow,
    PollResult,
    build_reconciliation_diff,
    poll_non_terminal_payments,
)
from app.services.payments.state import (
    PaymentObservationMismatch,
    PaymentStatus,
    process_webhook_event,
)
from fastapi.testclient import TestClient
from tests.support.webhook_evidence import verified_webhook_row
from tests.test_payment_state import (
    CHECKOUT_GROUP_ID,
    CUSTOMER_ID,
    FakeServiceClient,
    FakeSupabaseClient,
    FakeTable,
)
from tests.test_reconcile import FakeServiceClient as ReconcileFakeService

PAYMENT_ID = "feeb0000-0000-4000-8000-000000000001"
REFERENCE = "ord-fee-bearer-1"
ACTOR_ID = "22222222-2222-2222-2222-222222222222"
BASE_URL = "https://api.lenco.co/access/v2"


class _LedgerSpy:
    """Stands in for ``post_transaction`` so fee bookings are observable."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> PostedTransaction:
        self.calls.append(kwargs)
        return PostedTransaction(
            id=str(uuid.uuid4()),
            kind=str(kwargs["template"]),
            idempotency_key=kwargs["idempotency_key"],
            created=True,
        )


@pytest.fixture
def ledger_spy(monkeypatch: pytest.MonkeyPatch) -> _LedgerSpy:
    spy = _LedgerSpy()
    monkeypatch.setattr(fees_mod, "post_transaction", spy)
    return spy


@pytest.fixture
def rpc_observations(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Capture the observation handed to the atomic settlement RPC."""
    seen: list[dict[str, Any]] = []
    original = FakeSupabaseClient.rpc

    def _rpc(self: FakeSupabaseClient, name: str, params: dict[str, Any]) -> MagicMock:
        if name == "apply_prepaid_collection_success":
            seen.append(dict(params["p_observation"]))
        return original(self, name, params)

    monkeypatch.setattr(FakeSupabaseClient, "rpc", _rpc)
    return seen


# ---------------------------------------------------------------------------
# Config: one value, default customer, merchant for rollback, invalid rejected
# ---------------------------------------------------------------------------


def test_bearer_defaults_to_customer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(LENCO_COLLECTION_FEE_BEARER_ENV, raising=False)
    assert get_collection_fee_bearer() == "customer"
    monkeypatch.setenv(LENCO_COLLECTION_FEE_BEARER_ENV, "  ")
    assert get_collection_fee_bearer() == "customer"


@pytest.mark.parametrize(
    ("raw", "expected"), [("merchant", "merchant"), (" Customer ", "customer")]
)
def test_bearer_accepts_both_values(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: str
) -> None:
    monkeypatch.setenv(LENCO_COLLECTION_FEE_BEARER_ENV, raw)
    assert get_collection_fee_bearer() == expected
    assert (
        InitiateCollectionRequest(
            reference=REFERENCE, amount_ngwee=1_000, phone="0961111111", operator="mtn"
        ).bearer
        == expected
    )


@pytest.mark.parametrize("raw", ["either", "both", "vendor", "0", "merchant,customer"])
def test_invalid_bearer_config_is_rejected(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    monkeypatch.setenv(LENCO_COLLECTION_FEE_BEARER_ENV, raw)
    with pytest.raises(InvalidBearerConfigError):
        get_collection_fee_bearer()


def test_lenco_request_models_reject_unknown_bearer() -> None:
    with pytest.raises(ValueError):
        LencoCollectionRequest(
            amount_major="10.00",
            reference=REFERENCE,
            phone="0961111111",
            operator="mtn",
            bearer="either",  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError):
        InitiateCollectionRequest(
            reference=REFERENCE,
            amount_ngwee=1_000,
            phone="0961111111",
            operator="mtn",
            bearer="vendor",  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# MoMo request payload
# ---------------------------------------------------------------------------


async def _lenco_payload(bearer: str) -> dict[str, Any]:
    captured: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content, parse_float=Decimal)
        captured.append(body)
        return httpx.Response(
            200,
            json={
                "status": True,
                "message": "ok",
                "data": {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "initiatedAt": "2026-11-23T10:00:00Z",
                    "amount": "10.00",
                    "fee": None,
                    "bearer": body["bearer"],
                    "currency": "ZMW",
                    "reference": body["reference"],
                    "lencoReference": "240730001",
                    "type": "mobile-money",
                    "status": "pay-offline",
                    "source": "api",
                },
            },
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=BASE_URL)
    client = LencoClient(http_client=http, token="t", base_url=BASE_URL)
    await client.initiate_collection(
        LencoCollectionRequest(
            amount_major="10.00",
            reference=REFERENCE,
            phone="0961111111",
            operator="mtn",
            bearer=bearer,  # type: ignore[arg-type]
        )
    )
    return captured[0]


@pytest.mark.parametrize("bearer", ["customer", "merchant"])
async def test_momo_payload_carries_bearer(monkeypatch: pytest.MonkeyPatch, bearer: str) -> None:
    monkeypatch.setenv("LENCO_ENV", "production")
    payload = await _lenco_payload(bearer)
    assert payload["bearer"] == bearer
    assert payload["amount"] == Decimal("10.00")  # order amount only; Lenco adds the fee


def _initiate_service() -> FakeServiceClient:
    fake = FakeSupabaseClient()
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


@pytest.mark.parametrize(("env", "expected"), [(None, "customer"), ("merchant", "merchant")])
async def test_momo_initiation_sends_configured_bearer_and_records_it(
    monkeypatch: pytest.MonkeyPatch, env: str | None, expected: str
) -> None:
    if env is None:
        monkeypatch.delenv(LENCO_COLLECTION_FEE_BEARER_ENV, raising=False)
    else:
        monkeypatch.setenv(LENCO_COLLECTION_FEE_BEARER_ENV, env)
    service = _initiate_service()
    strategy = _pending_strategy()
    await initiate_checkout_payment(
        service,
        InitiatePaymentRequest(
            checkout_group_id=CHECKOUT_GROUP_ID,
            amount_ngwee=10_000,
            rail="mtn",
            phone="+260961111111",
        ),
        strategy=strategy,
        actor_id=ACTOR_ID,
    )
    sent: InitiateCollectionRequest = strategy.initiate_collection.await_args.args[0]
    assert sent.bearer == expected
    assert sent.amount_ngwee == 10_000
    payment = service.client.tables["payments"].rows[0]
    assert payment["raw"][RAW_BEARER_KEY] == expected


async def test_momo_initiation_with_invalid_bearer_claims_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(LENCO_COLLECTION_FEE_BEARER_ENV, "either")
    service = _initiate_service()
    strategy = _pending_strategy()
    with pytest.raises(InvalidBearerConfigError):
        await initiate_checkout_payment(
            service,
            InitiatePaymentRequest(
                checkout_group_id=CHECKOUT_GROUP_ID,
                amount_ngwee=10_000,
                rail="mtn",
                phone="+260961111111",
            ),
            strategy=strategy,
            actor_id=ACTOR_ID,
        )
    assert service.client.tables["payments"].rows == []
    strategy.initiate_collection.assert_not_awaited()


# ---------------------------------------------------------------------------
# Card widget session carries the bearer for LencoPay.getPaid({bearer})
# ---------------------------------------------------------------------------


def _card_client() -> tuple[TestClient, FakeServiceClient]:
    fake = FakeSupabaseClient()
    fake.tables["checkout_groups"].rows.append(
        {
            "id": CHECKOUT_GROUP_ID,
            "customer_id": CUSTOMER_ID,
            "total_ngwee": 10_000,
            "status": "pending",
        }
    )
    fake.tables["profiles"] = FakeTable()
    fake.tables["profiles"].rows.append(
        {"id": CUSTOMER_ID, "phone": "+260961111111", "display_name": "Jane Buyer"}
    )
    service = FakeServiceClient(fake)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=CUSTOMER_ID, roles=frozenset({"customer"}), token="tok"
    )

    def _svc() -> Generator[FakeServiceClient, None, None]:
        yield service

    app.dependency_overrides[get_supabase_client] = _svc
    return TestClient(app, raise_server_exceptions=False), service


@pytest.mark.parametrize(("env", "expected"), [(None, "customer"), ("merchant", "merchant")])
def test_card_session_carries_bearer(
    monkeypatch: pytest.MonkeyPatch, env: str | None, expected: str
) -> None:
    if env is None:
        monkeypatch.delenv(LENCO_COLLECTION_FEE_BEARER_ENV, raising=False)
    else:
        monkeypatch.setenv(LENCO_COLLECTION_FEE_BEARER_ENV, env)
    client, service = _card_client()
    with patch("app.routers.payments_card.lookup_user_email", return_value="b@example.com"):
        created = client.post(
            "/payments/card/session",
            headers={"Authorization": "Bearer tok"},
            json={"checkout_group_id": CHECKOUT_GROUP_ID},
        )
        assert created.status_code == 200
        body = created.json()
        assert body["bearer"] == expected
        assert body["amount_major"] == "100.00"  # order amount; widget adds the fee
        payment = service.client.tables["payments"].rows[0]
        assert payment["raw"][RAW_BEARER_KEY] == expected

        # Resume keeps the attempt's bearer even if config flips afterwards.
        monkeypatch.setenv(
            LENCO_COLLECTION_FEE_BEARER_ENV,
            "merchant" if expected == "customer" else "customer",
        )
        resumed = client.get(
            f"/payments/card/{body['payment_id']}/session",
            headers={"Authorization": "Bearer tok"},
        )
    assert resumed.status_code == 200
    assert resumed.json()["bearer"] == expected


def test_card_session_with_invalid_bearer_creates_no_payment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(LENCO_COLLECTION_FEE_BEARER_ENV, "either")
    client, service = _card_client()
    with patch("app.routers.payments_card.lookup_user_email", return_value="b@example.com"):
        response = client.post(
            "/payments/card/session",
            headers={"Authorization": "Bearer tok"},
            json={"checkout_group_id": CHECKOUT_GROUP_ID},
        )
    assert response.status_code == 500
    assert service.client.tables["payments"].rows == []


# ---------------------------------------------------------------------------
# Webhook: customer-borne fee settles SUCCESS, exact amount, no fee booking
# ---------------------------------------------------------------------------


def _webhook_service(*, raw: dict[str, Any] | None = None) -> FakeServiceClient:
    fake = FakeSupabaseClient()
    fake.tables["payments"].rows.append(
        {
            "id": PAYMENT_ID,
            "checkout_group_id": CHECKOUT_GROUP_ID,
            "provider": "lenco",
            "rail": "mtn",
            "lenco_reference": REFERENCE,
            "amount_ngwee": 1_000,
            "status": "pay_offline",
            "raw": raw if raw is not None else {},
        }
    )
    return FakeServiceClient(fake)


def _deliver(service: FakeServiceClient, data: dict[str, Any]) -> Any:
    webhook_id = str(uuid.uuid4())
    service.client.tables["webhook_events"].rows.append(
        verified_webhook_row(
            {
                "id": webhook_id,
                "provider": "lenco",
                "event_id": f"evt-{webhook_id}",
                "processed_at": None,
                "raw": {
                    "event": "collection.successful",
                    "data": {
                        "reference": REFERENCE,
                        "status": "successful",
                        "currency": "ZMW",
                        **data,
                    },
                },
            }
        )
    )
    return process_webhook_event(service, webhook_event_id=webhook_id)


@pytest.mark.parametrize(
    "amount",
    [
        "10.00",  # documented: amount = what we settle, fee charged on top
        "10.25",  # defensive: provider reports the gross the payer was charged
    ],
)
def test_customer_fee_webhook_settles_exact_amount_without_fee_booking(
    ledger_spy: _LedgerSpy, rpc_observations: list[dict[str, Any]], amount: str
) -> None:
    service = _webhook_service(raw={RAW_BEARER_KEY: "customer"})
    outcome = _deliver(service, {"amount": amount, "fee": "0.25", "bearer": "customer"})

    assert outcome is not None
    assert outcome.to_status == PaymentStatus.SUCCESS
    # Escrow/platform_cash posting comes from the observation: exactly the order amount.
    assert rpc_observations[0]["amount_ngwee"] == 1_000
    if amount == "10.25":
        assert rpc_observations[0]["provider_gross_ngwee"] == 1_025
        assert rpc_observations[0]["customer_fee_ngwee"] == 25
    assert ledger_spy.calls == []  # no fees expense, platform_cash not reduced


def test_customer_fee_without_provider_bearer_uses_requested_bearer(
    ledger_spy: _LedgerSpy, rpc_observations: list[dict[str, Any]]
) -> None:
    service = _webhook_service(raw={RAW_BEARER_KEY: "customer"})
    outcome = _deliver(service, {"amount": "10.00", "fee": "0.25"})
    assert outcome is not None and outcome.to_status == PaymentStatus.SUCCESS
    assert ledger_spy.calls == []


@pytest.mark.parametrize(
    ("amount", "fee", "bearer"),
    [
        ("10.25", "0.25", "merchant"),  # gross only accepted for a customer bearer
        ("10.26", "0.25", "customer"),  # must be exactly amount + fee
        ("10.25", "0.20", "customer"),
        ("10.25", None, "customer"),
        ("10.25", 0.25, "customer"),  # float fee is never money
        ("9.75", "0.25", "customer"),  # net-of-fee is an underpayment
    ],
)
def test_customer_fee_amount_mismatch_still_holds(
    ledger_spy: _LedgerSpy, amount: str, fee: object, bearer: str
) -> None:
    service = _webhook_service()
    with pytest.raises(PaymentObservationMismatch):
        _deliver(service, {"amount": amount, "fee": fee, "bearer": bearer})
    payment = service.client.tables["payments"].rows[0]
    assert payment["status"] == "pay_offline"
    assert payment["raw"]["hold"]["reason"] == "provider_amount_mismatch"
    assert ledger_spy.calls == []


def test_merchant_fee_webhook_still_books_fee(
    ledger_spy: _LedgerSpy, rpc_observations: list[dict[str, Any]]
) -> None:
    """Rollback / regression: merchant bearer nets the fee and books it to ``fees``."""
    service = _webhook_service(raw={RAW_BEARER_KEY: "merchant"})
    outcome = _deliver(service, {"amount": "10.00", "fee": "0.25", "bearer": "merchant"})
    assert outcome is not None and outcome.to_status == PaymentStatus.SUCCESS
    assert rpc_observations[0]["amount_ngwee"] == 1_000
    assert len(ledger_spy.calls) == 1
    assert ledger_spy.calls[0]["template"] == LedgerTemplate.LENCO_FEE
    assert ledger_spy.calls[0]["fee_ngwee"] == 25
    assert ledger_spy.calls[0]["payment_id"] == PAYMENT_ID


def test_legacy_payment_without_any_bearer_books_fee_as_merchant(
    ledger_spy: _LedgerSpy,
) -> None:
    service = _webhook_service(raw={})
    _deliver(service, {"amount": "10.00", "fee": "0.25"})
    assert [c["fee_ngwee"] for c in ledger_spy.calls] == [25]


def test_provider_reported_bearer_wins_over_requested(ledger_spy: _LedgerSpy) -> None:
    # We asked for customer, but Lenco says it netted the fee from us: book it.
    service = _webhook_service(raw={RAW_BEARER_KEY: "customer"})
    _deliver(service, {"amount": "10.00", "fee": "0.25", "bearer": "merchant"})
    assert [c["fee_ngwee"] for c in ledger_spy.calls] == [25]


# ---------------------------------------------------------------------------
# Poller: same rules via canonical status query
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("amount", "bearer", "fees_booked"),
    [("10.00", "customer", []), ("10.25", "customer", []), ("10.00", "merchant", [25])],
)
async def test_poller_customer_fee_settles_without_fee_booking(
    ledger_spy: _LedgerSpy, amount: str, bearer: str, fees_booked: list[int]
) -> None:
    service = ReconcileFakeService()
    service.client.tables["payments"].rows.append(
        {
            "id": PAYMENT_ID,
            "checkout_group_id": CHECKOUT_GROUP_ID,
            "status": PaymentStatus.USSD_PUSHED.value,
            "lenco_reference": REFERENCE,
            "amount_ngwee": 1_000,
            "rail": "mtn",
            "provider": "lenco",
            "raw": {RAW_BEARER_KEY: bearer},
            "updated_at": (datetime.now(UTC) - timedelta(minutes=10)).isoformat(),
        }
    )

    async def query_status(request: Any) -> QueryStatusResult:
        return QueryStatusResult(
            reference=request.reference,
            status="successful",
            amount_major=amount,
            raw={"data": {"fee": "0.25", "bearer": bearer}},
        )

    result = await poll_non_terminal_payments(
        service, query_status=query_status, older_than_minutes=1
    )
    assert result == PollResult(scanned=1, updated=1, unchanged=0, errors=0)
    assert service.client.tables["payments"].rows[0]["status"] == PaymentStatus.SUCCESS.value
    assert [c["fee_ngwee"] for c in ledger_spy.calls] == fees_booked


# ---------------------------------------------------------------------------
# Reconciliation: Lenco balance vs platform_cash
# ---------------------------------------------------------------------------


def _platform_cash_after(*, collected: int, fee: int, bearer: str) -> int:
    """platform_cash after one collection, using the real fee template legs."""
    balance = collected
    if bearer == "merchant" and fee > 0:
        balance += sum(
            leg.amount_ngwee
            for leg in lenco_fee(fee_ngwee=fee).legs
            if leg.account.kind == "platform_cash"
        )
    return balance


@pytest.mark.parametrize(
    ("bearer", "lenco_credit"),
    [
        ("customer", 1_000),  # payer paid 10.25, Lenco settles the full 10.00
        ("merchant", 975),  # payer paid 10.00, Lenco nets the 0.25 fee
    ],
)
def test_reconciliation_shows_zero_difference(bearer: str, lenco_credit: int) -> None:
    ledger_balance = _platform_cash_after(collected=1_000, fee=25, bearer=bearer)
    diff = build_reconciliation_diff(
        lenco_balance_ngwee=lenco_credit,
        ledger_balance_ngwee=ledger_balance,
        lenco_rows=[
            LencoTransactionRow(
                id="t1",
                amount_ngwee=lenco_credit,
                txn_type="credit",
                narration=f"Collection / {REFERENCE}",
                reference=REFERENCE,
                datetime="2026-11-23T10:00:00Z",
            )
        ],
        ledger_rows=[
            LedgerDayRow(
                transaction_id="l1",
                kind="collection",
                payment_id=PAYMENT_ID,
                lenco_reference=REFERENCE,
                amount_ngwee=ledger_balance,
                created_at="2026-11-23T10:00:00Z",
            )
        ],
    )
    assert diff.balance_diff_ngwee == 0
    assert diff.ngwee_mismatches == ()
    assert not diff.has_discrepancies


def test_reconciliation_flags_a_wrongly_booked_customer_fee() -> None:
    """Failure path: booking the fee on a customer-borne collection would drift."""
    wrong_ledger = _platform_cash_after(collected=1_000, fee=25, bearer="merchant")
    diff = build_reconciliation_diff(
        lenco_balance_ngwee=1_000,
        ledger_balance_ngwee=wrong_ledger,
        lenco_rows=[],
        ledger_rows=[],
    )
    assert diff.balance_diff_ngwee == 25
    assert diff.has_discrepancies


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("observed", "fee", "bearer", "expected"),
    [
        (1_000, "0.25", "customer", 1_000),
        (1_025, "0.25", "customer", 1_000),
        (1_025, "0.25", "CUSTOMER", 1_000),
        (1_025, 25, "customer", 1_025),  # int = major units (K25), not 25 ngwee
        (1_025, "0.25", "merchant", 1_025),
        (1_025, "0.25", None, 1_025),
        (1_025, "0.00", "customer", 1_025),
        (1_025, "abc", "customer", 1_025),
        (1_025, 0.25, "customer", 1_025),
        (1_025, True, "customer", 1_025),
        (1_026, "0.25", "customer", 1_026),
    ],
)
def test_net_collected_ngwee(observed: int, fee: object, bearer: object, expected: int) -> None:
    assert net_collected_ngwee(observed, expected_ngwee=1_000, fee=fee, bearer=bearer) == expected


def test_normalize_observation_amount_keeps_gross_for_audit() -> None:
    obs = {"reference": REFERENCE, "amount_ngwee": 1_025}
    out = normalize_observation_amount(obs, expected_ngwee=1_000, fee="0.25", bearer="customer")
    assert out == {
        **obs,
        "amount_ngwee": 1_000,
        "provider_gross_ngwee": 1_025,
        "customer_fee_ngwee": 25,
    }
    assert obs["amount_ngwee"] == 1_025  # input not mutated
    assert (
        normalize_observation_amount(None, expected_ngwee=1_000, fee="0.25", bearer="customer")
        is None
    )


def test_resolve_collection_bearer_precedence() -> None:
    assert resolve_collection_bearer("merchant", {RAW_BEARER_KEY: "customer"}) == "merchant"
    assert resolve_collection_bearer(None, {RAW_BEARER_KEY: "customer"}) == "customer"
    assert resolve_collection_bearer("bogus", {}) is None
    assert resolve_collection_bearer(None, None) is None
