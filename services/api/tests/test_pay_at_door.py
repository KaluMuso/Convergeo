"""Pay at the door by mobile money (flag ``pay_at_door``).

Pure tests always run. DB tests replay the real migrations against a local
Postgres (same harness as ``test_courier_dispatch.py``) and skip when none is
reachable. Lenco is a deterministic in-process fake: no network, no real money.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.deps import get_supabase_client
from app.errors import AppError
from app.main import create_app
from app.services.dispatch import service as dispatch_service
from app.services.dispatch.state import DispatchStatus, fetch_dispatch
from app.services.ledger.templates import (
    LedgerTemplate,
    door_payment_collected,
    door_payment_exception,
)
from app.services.orders.state import ActorRole
from app.services.payments import door
from app.services.payments.base import (
    CollectionStatus,
    InitiateCollectionRequest,
    InitiateCollectionResult,
    PaymentProviderError,
    ProviderErrorKind,
    ProviderOutcome,
    ProviderResult,
    QueryStatusRequest,
)
from app.services.payments.cod import refuse_cod_collection
from app.services.payments.money import ngwee_to_major_str
from app.services.payments.registry import LENCO_PROVIDER, register
from app.services.payments.registry import get as get_strategy
from app.services.payments.state import process_webhook_event
from app.services.payments.webhook_verify import (
    WEBHOOK_VERIFICATION_VERSION,
    canonical_payload_sha256,
)
from fastapi.testclient import TestClient
from tests.rls.conftest import (
    PgConn,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)

CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_CUSTOMER_ID = "22222222-2222-2222-2222-222222222222"
ADMIN_ID = "66666666-6666-6666-6666-666666666666"
SHOP_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
AUTH = {"Authorization": "Bearer test.jwt.placeholder"}

SUBTOTAL_NGWEE = 42_000  # K420.00
DELIVERY_FEE_NGWEE = 3_000  # K30.00
TOTAL_NGWEE = SUBTOTAL_NGWEE + DELIVERY_FEE_NGWEE  # K450.00 (under the K500 cash cap)
RATE_BPS = 500
CUSTOMER_PHONE = "+260961111111"  # Lenco sandbox MTN "success" number


# ---------------------------------------------------------------------------
# Fake Lenco (sandbox-shaped, in process)
# ---------------------------------------------------------------------------


class FakeLenco:
    def __init__(self) -> None:
        self.initiated: list[InitiateCollectionRequest] = []
        self.status: dict[str, tuple[str, str, str]] = {}
        self.init_status = CollectionStatus.PAY_OFFLINE
        self.init_error: PaymentProviderError | None = None

    async def initiate_collection(
        self, request: InitiateCollectionRequest
    ) -> InitiateCollectionResult:
        self.initiated.append(request)
        if self.init_error is not None:
            raise self.init_error
        self.status.setdefault(
            request.reference, ("pay-offline", ngwee_to_major_str(request.amount_ngwee), "ZMW")
        )
        return InitiateCollectionResult(
            status=self.init_status,
            amount_major=ngwee_to_major_str(request.amount_ngwee),
            provider_reference=f"lenco-{len(self.initiated)}",
        )

    async def query_status(self, request: QueryStatusRequest) -> ProviderResult:
        observed = self.status.get(request.reference)
        if observed is None:
            return ProviderResult(
                requested_reference=request.reference, outcome=ProviderOutcome.NOT_FOUND
            )
        status, amount, currency = observed
        return ProviderResult(
            reference=request.reference,
            status=status,
            amount_major=amount,
            currency=currency,
            provider_reference="lenco-q",
        )

    def pay(self, reference: str, amount_ngwee: int | None = None) -> None:
        amount = ngwee_to_major_str(amount_ngwee if amount_ngwee is not None else TOTAL_NGWEE)
        self.status[reference] = ("successful", amount, "ZMW")

    async def initiate_payout(self, request: Any) -> Any:
        raise NotImplementedError

    async def resolve_account(self, request: Any) -> Any:
        raise NotImplementedError

    async def verify_webhook(self, request: Any) -> Any:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Pure
# ---------------------------------------------------------------------------


def test_python_attempt_transitions_match_sql_guard() -> None:
    migration = next(
        (Path(__file__).resolve().parents[3] / "supabase" / "migrations").glob("*_pay_at_door.sql")
    )
    sql = migration.read_text(encoding="utf-8")
    block = sql.split("allowed := (old.status, new.status) in (")[1].split(");")[0]
    pairs = set(re.findall(r"\('([a-z_]+)', '([a-z_]+)'\)", block))
    assert pairs == set(door.ATTEMPT_TRANSITIONS)


def test_terminal_attempt_statuses_have_no_exits() -> None:
    for frm, _to in door.ATTEMPT_TRANSITIONS:
        assert frm not in {"successful", "failed"}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0961111111", "+260961111111"),
        ("+260 97 111 1111", "+260971111111"),
        ("260771234567", "+260771234567"),
    ],
)
def test_normalize_phone(raw: str, expected: str) -> None:
    assert door.normalize_phone(raw) == expected


@pytest.mark.parametrize("bad", ["12345", "+260211234567", "+2609611111111", "abc"])
def test_normalize_phone_rejects(bad: str) -> None:
    with pytest.raises(AppError) as exc:
        door.normalize_phone(bad)
    assert exc.value.code == "door_payment_invalid_phone"


def test_zamtel_cannot_get_a_prompt() -> None:
    with pytest.raises(AppError) as exc:
        door._operator_for("+260991234567")
    assert exc.value.code == "door_payment_operator_unsupported"


@pytest.mark.parametrize(
    ("amount", "currency", "expected"),
    [
        ("450.00", "ZMW", (45_000, True)),
        ("450", "ZMW", (45_000, True)),
        ("450.005", "ZMW", (None, True)),
        (450.0, "ZMW", (None, True)),  # a float is never read as money
        (True, "ZMW", (None, True)),
        ("450.00", "USD", (None, False)),
        (None, "ZMW", (None, True)),
    ],
)
def test_observed_amount_is_decimal_exact(amount: Any, currency: Any, expected: Any) -> None:
    assert door._observed_ngwee(amount, currency) == expected


def test_door_templates_balance_and_hit_the_right_accounts() -> None:
    collected = door_payment_collected(collected_ngwee=TOTAL_NGWEE, vendor_id=SHOP_A)
    assert collected.kind == LedgerTemplate.DOOR_PAYMENT_COLLECTED
    assert {(leg.account.kind, leg.amount_ngwee) for leg in collected.legs} == {
        ("platform_cash", TOTAL_NGWEE),
        ("cod_receivable", -TOTAL_NGWEE),
    }
    suspense = door_payment_exception(received_ngwee=1_000)
    assert sum(leg.amount_ngwee for leg in suspense.legs) == 0
    assert {leg.account.kind for leg in suspense.legs} == {
        "platform_cash",
        "door_payment_suspense",
    }


def test_collection_key_is_shared_with_cash_cod() -> None:
    from app.services.payments.cod import collection_idempotency_key

    order_id = str(uuid.uuid4())
    assert door.collection_idempotency_key(order_id) == collection_idempotency_key(order_id)


# ---------------------------------------------------------------------------
# DB fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def db() -> Generator[PgConn, None, None]:
    url = resolve_db_url()
    conn = PgConn(url)
    if not conn.run("SELECT 1").ok:
        pytest.skip(f"Postgres not reachable at {url}")
    if not schema_ready(conn):
        conn.run("DROP SCHEMA IF EXISTS public CASCADE")
        conn.run("CREATE SCHEMA public")
        conn.run("DROP SCHEMA IF EXISTS auth CASCADE")
        apply_migrations(conn)
    if not conn.run("SELECT 1 FROM public.door_payment_sessions LIMIT 1").ok:
        pytest.skip("pay-at-door migration not applied to this database")
    seed_matrix_fixtures(conn)
    yield conn


def _sql(db: PgConn, sql: str) -> list[str]:
    result = db.run(sql)
    assert result.ok, result.error
    return result.rows


def _set_flag(db: PgConn, flag: str, enabled: bool) -> None:
    _sql(
        db,
        "INSERT INTO public.feature_flags (flag, enabled, description) "
        f"VALUES ('{flag}', {str(enabled).lower()}, 'test') "
        f"ON CONFLICT (flag) DO UPDATE SET enabled = {str(enabled).lower()};",
    )


def _set_config(db: PgConn, key: str, value: int) -> None:
    _sql(
        db,
        "INSERT INTO public.platform_config (key, value, description) "
        f"VALUES ('{key}', '{value}'::jsonb, 'test') "
        f"ON CONFLICT (key) DO UPDATE SET value = '{value}'::jsonb;",
    )


@pytest.fixture
def env(db: PgConn) -> Generator[None, None, None]:
    previous = os.environ.get("SUPABASE_DB_URL")
    os.environ["SUPABASE_DB_URL"] = db.dsn
    _set_flag(db, "courier_dispatch", True)
    _set_config(db, "cod_cap_ngwee", 50_000)
    _set_config(db, "pay_at_door_max_attempts", 3)
    _set_config(db, "pay_at_door_attempt_ttl_seconds", 120)
    yield
    _set_flag(db, "courier_dispatch", False)
    _set_flag(db, "pay_at_door", False)
    if previous is None:
        os.environ.pop("SUPABASE_DB_URL", None)
    else:
        os.environ["SUPABASE_DB_URL"] = previous


@pytest.fixture
def flag_on(db: PgConn, env: None) -> None:
    _set_flag(db, "pay_at_door", True)


@pytest.fixture
def lenco() -> Generator[FakeLenco, None, None]:
    previous = get_strategy(LENCO_PROVIDER)
    fake = FakeLenco()
    register(LENCO_PROVIDER, fake)
    yield fake
    register(LENCO_PROVIDER, previous)


def _make_order(db: PgConn, *, customer_id: str = CUSTOMER_ID) -> str:
    order_id = str(uuid.uuid4())
    group_id = str(uuid.uuid4())
    address_id = str(uuid.uuid4())
    line = {
        "listing_id": str(uuid.uuid4()),
        "category_key": "electronics",
        "rate_bps": RATE_BPS,
        "qty": 1,
        "unit_price_ngwee": SUBTOTAL_NGWEE,
        "line_total_ngwee": SUBTOTAL_NGWEE,
        "wholesale": False,
    }
    snapshot = json.dumps({"lines": [line]})
    _sql(
        db,
        f"""
BEGIN;
INSERT INTO public.addresses (id, user_id, landmark, lat, lng, phone)
VALUES ('{address_id}', '{customer_id}', 'Behind Arcades', -15.41, 28.32, '{CUSTOMER_PHONE}');
INSERT INTO public.checkout_groups (
  id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee, total_ngwee
) VALUES ('{group_id}', '{customer_id}', 'door-{group_id}', {SUBTOTAL_NGWEE},
          {DELIVERY_FEE_NGWEE}, {TOTAL_NGWEE});
INSERT INTO public.orders (
  id, checkout_group_id, vendor_id, customer_id, status, fulfilment, cod,
  delivery_zone, address_id, delivery_fee_ngwee, commission_snapshot
) VALUES ('{order_id}', '{group_id}', '{SHOP_A}', '{customer_id}', 'processing',
          'delivery', true, 'lusaka_a', '{address_id}', {DELIVERY_FEE_NGWEE},
          '{snapshot}'::jsonb);
INSERT INTO public.order_items (order_id, item_kind, qty, unit_price_ngwee, title_snapshot)
VALUES ('{order_id}', 'product', 1, {SUBTOTAL_NGWEE}, 'Rice cooker');
COMMIT;
""",
    )
    return order_id


def _at_door(db: PgConn, **kwargs: Any) -> tuple[str, str]:
    """COD order whose rider has picked up (order shipped). Returns (order, dispatch)."""
    order_id = _make_order(db, **kwargs)
    courier_id = str(uuid.uuid4())
    _sql(
        db,
        "INSERT INTO public.courier_partners (id, name, contact_whatsapp_e164) "
        f"VALUES ('{courier_id}', 'Rider {courier_id[:6]}', '+260977000001');",
    )
    created = dispatch_service.create_dispatch(
        order_id=order_id, courier_partner_id=courier_id, actor_id=ADMIN_ID
    )
    dispatch_id = created.dispatch.id
    dispatch_service.transition_dispatch_admin(
        dispatch_id=dispatch_id, to_status=DispatchStatus.ACCEPTED, actor_id=ADMIN_ID
    )
    dispatch_service.transition_dispatch_admin(
        dispatch_id=dispatch_id, to_status=DispatchStatus.PICKED_UP, actor_id=ADMIN_ID
    )
    return order_id, dispatch_id


_BACKDATE_SQL = (
    "UPDATE public.door_payment_attempts SET created_at = created_at - interval '10 minutes' "
    "WHERE dispatch_request_id = '{dispatch_id}';"
)


def _code(db: PgConn, dispatch_id: str) -> str:
    return _sql(
        db,
        "SELECT code FROM public.dispatch_handover_codes "
        f"WHERE dispatch_request_id = '{dispatch_id}';",
    )[0]


def _order_status(db: PgConn, order_id: str) -> str:
    return _sql(db, f"SELECT status FROM public.orders WHERE id = '{order_id}';")[0]


def _postings(db: PgConn, order_id: str) -> list[tuple[str, str, int]]:
    rows = _sql(
        db,
        f"""
SELECT t.kind, la.kind, p.amount_ngwee::text
FROM public.ledger_postings p
JOIN public.ledger_transactions t ON t.id = p.transaction_id
JOIN public.ledger_accounts la ON la.id = p.account_id
WHERE t.order_id = '{order_id}'
ORDER BY t.created_at, p.amount_ngwee;
""",
    )
    out = []
    for row in rows:
        txn_kind, account_kind, amount = row.split("|")
        out.append((txn_kind, account_kind, int(amount)))
    return out


def _by_account(db: PgConn, order_id: str) -> dict[str, int]:
    totals: dict[str, int] = {}
    for _txn, account, amount in _postings(db, order_id):
        totals[account] = totals.get(account, 0) + amount
    return totals


def _attempts(dispatch_id: str) -> list[door.DoorAttempt]:
    return door.list_attempts(dispatch_id)


def _exceptions(db: PgConn, order_id: str) -> list[str]:
    return _sql(
        db,
        "SELECT reason || '|' || coalesce(observed_amount_ngwee::text, '') || '|' || "
        "(ledger_transaction_id IS NOT NULL)::text "
        f"FROM public.door_payment_exceptions WHERE order_id = '{order_id}' ORDER BY created_at;",
    )


def _webhook(event: str, reference: str, amount_ngwee: int, status: str) -> dict[str, Any]:
    return {
        "event": event,
        "data": {
            "id": str(uuid.uuid4()),
            "reference": reference,
            "lencoReference": "lenco-wh",
            "amount": ngwee_to_major_str(amount_ngwee),
            "currency": "ZMW",
            "status": status,
            "type": "mobile-money",
        },
    }


async def _request(
    dispatch_id: str, fake: FakeLenco, *, role: str = "customer", phone: str | None = None
) -> door.DoorStatus:
    return await door.request_door_payment(
        dispatch_id=dispatch_id,
        actor_id=CUSTOMER_ID if role == "customer" else ADMIN_ID,
        actor_role=role,  # type: ignore[arg-type]
        phone=phone,
        strategy=fake,
    )


# ---------------------------------------------------------------------------
# Flag OFF: behaviour unchanged
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("env")
class TestFlagOff:
    async def test_code_shown_and_handover_works_without_payment(
        self, db: PgConn, lenco: FakeLenco
    ) -> None:
        order_id, dispatch_id = _at_door(db)
        view = dispatch_service.party_dispatch_view(order_id, include_handover_code=True)
        assert view is not None and view["handover_code"] == _code(db, dispatch_id)

        with pytest.raises(AppError) as exc:
            await _request(dispatch_id, lenco)
        assert exc.value.code == "door_payment_disabled"
        assert lenco.initiated == []

        result = dispatch_service.verify_handover_code(
            dispatch_id=dispatch_id, code=_code(db, dispatch_id), actor_id=ADMIN_ID
        )
        assert result.order_status == "delivered"
        assert door.load_session(dispatch_id) is None
        # Cash COD stays an ops confirmation: no ledger collection on delivery.
        assert not any(t == "door_payment_collected" for t, _a, _n in _postings(db, order_id))


# ---------------------------------------------------------------------------
# Flag ON: happy path, webhook idempotency, withholding
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("flag_on")
class TestPayAtDoor:
    async def test_code_withheld_until_verified_payment_then_released(
        self, db: PgConn, lenco: FakeLenco
    ) -> None:
        order_id, dispatch_id = _at_door(db)
        code = _code(db, dispatch_id)

        view = dispatch_service.party_dispatch_view(order_id, include_handover_code=True)
        assert view is not None and view["handover_code"] is None
        for path in ("code", "pod"):
            with pytest.raises(AppError) as exc:
                if path == "code":
                    dispatch_service.verify_handover_code(
                        dispatch_id=dispatch_id, code=code, actor_id=ADMIN_ID
                    )
                else:
                    dispatch_service.transition_dispatch_admin(
                        dispatch_id=dispatch_id,
                        to_status=DispatchStatus.DELIVERED,
                        actor_id=ADMIN_ID,
                        pod_photo_public_id="vergeo5/pod/door-test",
                    )
            assert exc.value.code == "door_payment_required"

        # Customer cannot prompt before the rider is at the door.
        with pytest.raises(AppError) as exc:
            await _request(dispatch_id, lenco)
        assert exc.value.code == "door_payment_awaiting_arrival"

        door.mark_arrived(dispatch_id=dispatch_id, actor_id=ADMIN_ID)
        status = await _request(dispatch_id, lenco)
        assert status.state == "pending"
        assert lenco.initiated[-1].amount_ngwee == TOTAL_NGWEE
        assert lenco.initiated[-1].phone == CUSTOMER_PHONE
        assert lenco.initiated[-1].reference.startswith("ord-")

        # The phone screen is not evidence: still withheld while pending.
        view = dispatch_service.party_dispatch_view(order_id, include_handover_code=True)
        assert view is not None and view["handover_code"] is None

        reference = _attempts(dispatch_id)[-1].lenco_reference
        outcome = door.apply_webhook(
            event_name="collection.successful",
            data=_webhook("collection.successful", reference, TOTAL_NGWEE, "successful")["data"],
        )
        assert outcome is not None and outcome.settled is True

        view = dispatch_service.party_dispatch_view(order_id, include_handover_code=True)
        assert view is not None and view["handover_code"] == code
        assert _by_account(db, order_id) == {
            "cod_receivable": 0,
            "escrow": -TOTAL_NGWEE,
            "platform_cash": TOTAL_NGWEE,
        }

        delivered = dispatch_service.verify_handover_code(
            dispatch_id=dispatch_id, code=code, actor_id=ADMIN_ID
        )
        assert delivered.order_status == "delivered"
        # Release followed the COD rules: commission, fee → delivery_revenue, vendor net.
        commission = SUBTOTAL_NGWEE * RATE_BPS // 10_000
        totals = _by_account(db, order_id)
        assert sum(totals.values()) == 0
        assert totals["platform_cash"] == TOTAL_NGWEE
        assert totals["escrow"] == 0
        assert totals["cod_receivable"] == 0
        assert totals["delivery_revenue"] == -DELIVERY_FEE_NGWEE
        assert totals["commission_revenue"] == -commission
        assert totals["vendor_payable"] == -(SUBTOTAL_NGWEE - commission)
        assert _order_status(db, order_id) == "completed"
        kinds = [t for t, _a, _n in _postings(db, order_id)]
        assert "door_payment_collected" in kinds and "cod_collected" not in kinds

    async def test_duplicate_and_late_webhooks_are_idempotent(
        self, db: PgConn, lenco: FakeLenco
    ) -> None:
        order_id, dispatch_id = _at_door(db)
        await _request(dispatch_id, lenco, role="admin")
        reference = _attempts(dispatch_id)[-1].lenco_reference
        data = _webhook("collection.successful", reference, TOTAL_NGWEE, "successful")["data"]
        for _ in range(3):
            door.apply_webhook(event_name="collection.successful", data=data)
        lenco.pay(reference)
        await door.poll_door_payment(dispatch_id=dispatch_id, strategy=lenco)
        # A late "failed" for the same reference never undoes the success.
        door.apply_webhook(
            event_name="collection.failed",
            data=_webhook("collection.failed", reference, TOTAL_NGWEE, "failed")["data"],
        )
        assert _attempts(dispatch_id)[-1].status == "successful"
        postings = _postings(db, order_id)
        assert [t for t, _a, _n in postings].count("door_payment_collected") == 2  # two legs
        assert sum(n for _t, _a, n in postings) == 0
        audit = _sql(
            db,
            "SELECT count(*) FROM public.audit_log "
            f"WHERE action = 'door_payment.session.settled' AND entity_id = '{dispatch_id}';",
        )
        assert audit == ["1"]

    async def test_stored_webhook_drains_through_payment_worker(
        self, db: PgConn, lenco: FakeLenco
    ) -> None:
        order_id, dispatch_id = _at_door(db)
        await _request(dispatch_id, lenco, role="admin")
        reference = _attempts(dispatch_id)[-1].lenco_reference
        raw = _webhook("collection.successful", reference, TOTAL_NGWEE, "successful")
        updates: list[dict[str, Any]] = []
        row = {
            "id": "wh-1",
            "provider": "lenco",
            "event_id": "evt-1",
            "raw": raw,
            "processed_at": None,
            "signature_valid": True,
            "verification_version": WEBHOOK_VERIFICATION_VERSION,
            "verified_at": "2026-11-13T10:00:00+00:00",
            "payload_sha256": canonical_payload_sha256(raw),
        }
        client = _FakeSupabase({"webhook_events": row, "payments": None}, updates)
        assert process_webhook_event(client, webhook_event_id="wh-1") is None
        assert updates and "processed_at" in updates[-1]
        assert "quarantine_reason" not in updates[-1]
        assert door.load_session(dispatch_id).settled_via == "mobile_money"  # type: ignore[union-attr]
        assert _by_account(db, order_id)["platform_cash"] == TOTAL_NGWEE

    async def test_untrusted_webhook_never_pays(self, db: PgConn, lenco: FakeLenco) -> None:
        _order_id, dispatch_id = _at_door(db)
        await _request(dispatch_id, lenco, role="admin")
        reference = _attempts(dispatch_id)[-1].lenco_reference
        raw = _webhook("collection.successful", reference, TOTAL_NGWEE, "successful")
        row = {
            "id": "wh-2",
            "provider": "lenco",
            "event_id": "evt-2",
            "raw": raw,
            "processed_at": None,
            "signature_valid": False,
            "verification_version": WEBHOOK_VERIFICATION_VERSION,
            "verified_at": None,
            "payload_sha256": "forged",
        }
        updates: list[dict[str, Any]] = []
        process_webhook_event(
            _FakeSupabase({"webhook_events": row, "payments": None}, updates),
            webhook_event_id="wh-2",
        )
        assert updates[-1].get("quarantine_reason") == "untrusted_webhook_evidence"
        assert door.load_session(dispatch_id).settled_via is None  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("flag_on")
class TestDoorFailures:
    async def test_wrong_number_refused_by_lenco_then_retry_other_phone(
        self, db: PgConn, lenco: FakeLenco
    ) -> None:
        _order_id, dispatch_id = _at_door(db)
        lenco.init_error = PaymentProviderError("12", "invalid mobile number")
        status = await _request(dispatch_id, lenco, role="admin", phone="0962222222")
        assert status.state == "failed" and status.latest_failure_reason == "12"
        assert status.can_request is True

        lenco.init_error = None
        status = await _request(dispatch_id, lenco, role="admin", phone="0971111111")
        assert status.state == "pending"
        assert lenco.initiated[-1].operator == "airtel"
        assert [a.status for a in _attempts(dispatch_id)] == ["failed", "pushed"]

    async def test_unanswered_prompt_expires_then_retry_then_cap(
        self, db: PgConn, lenco: FakeLenco
    ) -> None:
        _set_config(db, "pay_at_door_max_attempts", 2)
        _order_id, dispatch_id = _at_door(db)
        await _request(dispatch_id, lenco, role="admin")

        # A second prompt while the first is live is refused (no parallel pushes).
        with pytest.raises(AppError) as exc:
            await _request(dispatch_id, lenco, role="admin")
        assert exc.value.code == "door_payment_in_flight"
        # Cash cannot be chosen while a prompt may still be approved.
        with pytest.raises(AppError) as exc:
            door.settle_with_cash(dispatch_id=dispatch_id, actor_id=ADMIN_ID)
        assert exc.value.code == "door_payment_in_flight"

        _sql(
            db,
            _BACKDATE_SQL.format(dispatch_id=dispatch_id),
        )
        status = await door.poll_door_payment(dispatch_id=dispatch_id, strategy=lenco)
        assert status.state == "failed" and status.latest_attempt_status == "expired"
        assert status.latest_failure_reason == "timeout"

        await _request(dispatch_id, lenco, role="admin")
        _sql(
            db,
            _BACKDATE_SQL.format(dispatch_id=dispatch_id),
        )
        with pytest.raises(AppError) as exc:
            await _request(dispatch_id, lenco, role="admin")
        assert exc.value.code == "door_payment_attempts_exhausted"
        status = door.settle_with_cash(dispatch_id=dispatch_id, actor_id=ADMIN_ID)
        assert status.state == "cash"

    async def test_network_loss_at_initiation_then_poll_confirms(
        self, db: PgConn, lenco: FakeLenco
    ) -> None:
        order_id, dispatch_id = _at_door(db)
        lenco.init_error = PaymentProviderError(
            "timeout", "read timed out", kind=ProviderErrorKind.TRANSPORT
        )
        status = await _request(dispatch_id, lenco, role="admin")
        assert status.state == "pending"  # reference is durable; outcome unknown
        assert _attempts(dispatch_id)[-1].status == "initiated"

        lenco.pay(_attempts(dispatch_id)[-1].lenco_reference)
        status = await door.poll_door_payment(dispatch_id=dispatch_id, strategy=lenco)
        assert status.state == "paid"
        view = dispatch_service.party_dispatch_view(order_id, include_handover_code=True)
        assert view is not None and view["handover_code"] == _code(db, dispatch_id)

    async def test_partial_amount_is_refused_and_held_in_suspense(
        self, db: PgConn, lenco: FakeLenco
    ) -> None:
        order_id, dispatch_id = _at_door(db)
        await _request(dispatch_id, lenco, role="admin")
        reference = _attempts(dispatch_id)[-1].lenco_reference
        partial = TOTAL_NGWEE - 10_000
        outcome = door.apply_webhook(
            event_name="collection.successful",
            data=_webhook("collection.successful", reference, partial, "successful")["data"],
        )
        assert outcome is not None and outcome.settled is False
        assert outcome.exception_reason == "amount_mismatch"
        assert _exceptions(db, order_id) == [f"amount_mismatch|{partial}|true"]
        totals = _by_account(db, order_id)
        assert totals["door_payment_suspense"] == -partial
        # Nothing settled: no collection was booked against the order.
        assert "door_payment_collected" not in {t for t, _a, _n in _postings(db, order_id)}
        assert set(totals) == {"platform_cash", "door_payment_suspense"}
        view = dispatch_service.party_dispatch_view(order_id, include_handover_code=True)
        assert view is not None and view["handover_code"] is None

    async def test_payment_after_cancellation_goes_to_exception_queue(
        self, db: PgConn, lenco: FakeLenco
    ) -> None:
        order_id, dispatch_id = _at_door(db)
        await _request(dispatch_id, lenco, role="admin")
        reference = _attempts(dispatch_id)[-1].lenco_reference
        refuse_cod_collection(
            order_id=order_id, actor_role=ActorRole.ADMIN, actor_id=ADMIN_ID, note="Refused"
        )
        assert _order_status(db, order_id) == "cancelled"

        outcome = door.apply_webhook(
            event_name="collection.successful",
            data=_webhook("collection.successful", reference, TOTAL_NGWEE, "successful")["data"],
        )
        assert outcome is not None and outcome.exception_reason == "order_not_payable"
        assert _order_status(db, order_id) == "cancelled"  # never revived
        assert door.load_session(dispatch_id).settled_via is None  # type: ignore[union-attr]
        totals = _by_account(db, order_id)
        assert totals["door_payment_suspense"] == -TOTAL_NGWEE
        assert "door_payment_collected" not in {t for t, _a, _n in _postings(db, order_id)}
        assert len(door.list_open_exceptions()) >= 1
        exc_id = _sql(
            db, f"SELECT id FROM public.door_payment_exceptions WHERE order_id = '{order_id}';"
        )[0]
        door.resolve_exception(exception_id=exc_id, actor_id=ADMIN_ID, note="Refunded by payout")
        assert _sql(
            db, f"SELECT status FROM public.door_payment_exceptions WHERE id = '{exc_id}';"
        ) == ["resolved"]

    async def test_late_mobile_money_after_cash_is_an_exception(
        self, db: PgConn, lenco: FakeLenco
    ) -> None:
        order_id, dispatch_id = _at_door(db)
        await _request(dispatch_id, lenco, role="admin")
        reference = _attempts(dispatch_id)[-1].lenco_reference
        _sql(
            db,
            _BACKDATE_SQL.format(dispatch_id=dispatch_id),
        )
        await door.poll_door_payment(dispatch_id=dispatch_id, strategy=lenco)
        status = door.settle_with_cash(dispatch_id=dispatch_id, actor_id=ADMIN_ID)
        assert status.state == "cash"
        view = dispatch_service.party_dispatch_view(order_id, include_handover_code=True)
        assert view is not None and view["handover_code"] == _code(db, dispatch_id)

        # The customer approves the old, expired prompt after paying cash.
        outcome = door.apply_webhook(
            event_name="collection.successful",
            data=_webhook("collection.successful", reference, TOTAL_NGWEE, "successful")["data"],
        )
        assert outcome is not None and outcome.exception_reason == "already_settled"
        assert door.load_session(dispatch_id).settled_via == "cash"  # type: ignore[union-attr]
        assert "door_payment_collected" not in {t for t, _a, _n in _postings(db, order_id)}

    async def test_refusal_after_door_payment_is_refused(
        self, db: PgConn, lenco: FakeLenco
    ) -> None:
        order_id, dispatch_id = _at_door(db)
        await _request(dispatch_id, lenco, role="admin")
        lenco.pay(_attempts(dispatch_id)[-1].lenco_reference)
        await door.poll_door_payment(dispatch_id=dispatch_id, strategy=lenco)
        with pytest.raises(AppError) as exc:
            refuse_cod_collection(
                order_id=order_id, actor_role=ActorRole.ADMIN, actor_id=ADMIN_ID, note="Refused"
            )
        assert exc.value.code == "cod_already_collected"
        assert _order_status(db, order_id) == "shipped"
        assert sum(_by_account(db, order_id).values()) == 0

    async def test_cash_fallback_respects_cap(self, db: PgConn, lenco: FakeLenco) -> None:
        _set_config(db, "cod_cap_ngwee", TOTAL_NGWEE - 1)
        _order_id, dispatch_id = _at_door(db)
        with pytest.raises(AppError) as exc:
            door.settle_with_cash(dispatch_id=dispatch_id, actor_id=ADMIN_ID)
        assert exc.value.code == "door_payment_cash_over_cap"
        assert door.door_status(fetch_dispatch(dispatch_id)).cash_allowed is False

    async def test_settlement_is_write_once_in_the_database(
        self, db: PgConn, lenco: FakeLenco
    ) -> None:
        _order_id, dispatch_id = _at_door(db)
        door.settle_with_cash(dispatch_id=dispatch_id, actor_id=ADMIN_ID)
        result = db.run(
            "UPDATE public.door_payment_sessions SET settled_via = 'mobile_money', "
            f"settled_attempt_id = gen_random_uuid() WHERE dispatch_request_id = '{dispatch_id}';"
        )
        assert not result.ok and "write-once" in (result.error or "")

    async def test_db_guard_rejects_illegal_attempt_transition(
        self, db: PgConn, lenco: FakeLenco
    ) -> None:
        _order_id, dispatch_id = _at_door(db)
        await _request(dispatch_id, lenco, role="admin")
        attempt = _attempts(dispatch_id)[-1]
        door.apply_webhook(
            event_name="collection.failed",
            data=_webhook("collection.failed", attempt.lenco_reference, TOTAL_NGWEE, "failed")[
                "data"
            ],
        )
        result = db.run(
            "UPDATE public.door_payment_attempts SET status = 'successful' "
            f"WHERE id = '{attempt.id}';"
        )
        assert not result.ok and "invalid door payment transition" in (result.error or "")
        amount = db.run(
            f"UPDATE public.door_payment_attempts SET amount_ngwee = 1 WHERE id = '{attempt.id}';"
        )
        assert not amount.ok


# ---------------------------------------------------------------------------
# HTTP: customer + admin
# ---------------------------------------------------------------------------


class _FakeQuery:
    def __init__(self, row: Any, updates: list[dict[str, Any]]) -> None:
        self._row = row
        self._updates = updates
        self._is_update = False

    def select(self, *_a: Any, **_k: Any) -> _FakeQuery:
        return self

    def eq(self, *_a: Any) -> _FakeQuery:
        return self

    def maybe_single(self) -> _FakeQuery:
        return self

    def update(self, values: dict[str, Any]) -> _FakeQuery:
        self._updates.append(values)
        self._is_update = True
        return self

    def insert(self, _values: Any) -> _FakeQuery:
        return self

    def execute(self) -> MagicMock:
        return MagicMock(data=None if self._is_update else self._row)


class _FakeSupabase:
    def __init__(self, rows: dict[str, Any], updates: list[dict[str, Any]]) -> None:
        self._rows = rows
        self._updates = updates
        self.client = self

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(self._rows.get(name), self._updates)


@pytest.fixture
def http(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[TestClient, dict[str, str]], None, None]:
    who: dict[str, str] = {"user": CUSTOMER_ID}
    roles = {
        CUSTOMER_ID: frozenset({"customer"}),
        OTHER_CUSTOMER_ID: frozenset({"customer"}),
        ADMIN_ID: frozenset({"admin"}),
    }
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": who["user"], "exp": 9_999_999_999},
    )
    monkeypatch.setattr(
        "app.core.auth._load_user_roles",
        lambda uid, service_client: roles.get(uid, frozenset()),
    )
    audit_client = MagicMock()
    audit_client.client.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": "audit-0001"}]
    )
    monkeypatch.setattr("app.core.admin_audit.get_supabase_service_client", lambda: audit_client)
    monkeypatch.setattr(
        "app.core.ratelimit.bump_rate_counter", lambda **_kwargs: (True, 0), raising=False
    )
    monkeypatch.setattr("app.routers.admin_dispatch.bump_rate_counter", lambda **_kwargs: (True, 0))
    wrapper = MagicMock()
    app = create_app()
    app.dependency_overrides[get_supabase_client] = lambda: wrapper
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, who


@pytest.mark.usefixtures("flag_on")
class TestDoorHttp:
    def test_customer_flow_and_isolation(
        self, db: PgConn, lenco: FakeLenco, http: tuple[TestClient, dict[str, str]]
    ) -> None:
        client, who = http
        order_id, dispatch_id = _at_door(db)

        who["user"] = CUSTOMER_ID
        before = client.get(f"/account/orders/{order_id}/door-payment", headers=AUTH)
        assert before.status_code == 200, before.text
        assert before.json()["state"] == "awaiting_arrival"
        assert before.json()["amount_ngwee"] == TOTAL_NGWEE
        early = client.post(f"/account/orders/{order_id}/door-payment", json={}, headers=AUTH)
        assert early.status_code == 409
        assert early.json()["error"]["code"] == "door_payment_awaiting_arrival"

        who["user"] = ADMIN_ID
        arrived = client.post(
            f"/admin/dispatch/requests/{dispatch_id}/door-payment/arrived", headers=AUTH
        )
        assert arrived.status_code == 200, arrived.text

        who["user"] = OTHER_CUSTOMER_ID
        other = client.post(f"/account/orders/{order_id}/door-payment", json={}, headers=AUTH)
        assert other.status_code == 404
        assert lenco.initiated == []

        who["user"] = CUSTOMER_ID
        sent = client.post(f"/account/orders/{order_id}/door-payment", json={}, headers=AUTH)
        assert sent.status_code == 200, sent.text
        assert sent.json()["state"] == "pending"
        assert CUSTOMER_PHONE not in sent.text and "ord-" not in sent.text

        lenco.pay(lenco.initiated[-1].reference)
        polled = client.post(f"/account/orders/{order_id}/door-payment/poll", headers=AUTH)
        assert polled.json()["state"] == "paid"
        delivery = client.get(f"/account/orders/{order_id}/delivery", headers=AUTH)
        assert delivery.json()["dispatch"]["handover_code"] == _code(db, dispatch_id)

        who["user"] = ADMIN_ID
        board = client.get("/admin/dispatch/board", headers=AUTH)
        assert board.status_code == 200, board.text
        mine = [d for d in board.json()["dispatches"] if d["id"] == dispatch_id]
        assert mine and mine[0]["door_payment_state"] == "paid"

    def test_customer_cannot_use_admin_door_actions(
        self, db: PgConn, lenco: FakeLenco, http: tuple[TestClient, dict[str, str]]
    ) -> None:
        client, who = http
        _order_id, dispatch_id = _at_door(db)
        who["user"] = CUSTOMER_ID
        for action in ("arrived", "request", "poll", "cash"):
            response = client.post(
                f"/admin/dispatch/requests/{dispatch_id}/door-payment/{action}",
                json={},
                headers=AUTH,
            )
            assert response.status_code == 403, (action, response.text)
        assert lenco.initiated == []

    def test_flag_off_customer_view_is_disabled(
        self, db: PgConn, lenco: FakeLenco, http: tuple[TestClient, dict[str, str]]
    ) -> None:
        client, who = http
        _set_flag(db, "pay_at_door", False)
        order_id, _dispatch_id = _at_door(db)
        who["user"] = CUSTOMER_ID
        view = client.get(f"/account/orders/{order_id}/door-payment", headers=AUTH)
        assert view.status_code == 200 and view.json()["enabled"] is False
        sent = client.post(f"/account/orders/{order_id}/door-payment", json={}, headers=AUTH)
        assert sent.status_code == 409
        assert sent.json()["error"]["code"] == "door_payment_disabled"
