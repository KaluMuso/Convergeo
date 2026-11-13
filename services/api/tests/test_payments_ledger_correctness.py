"""Pilot money-path gaps: C2 (buyer-paid ticket fee) and C6 (Lenco fee booking).

Unit-level: SQL and the ledger writer are faked so the tests pin the exact
postings each path asks for, including failure paths. DB-backed coverage of the
templates lives in ``test_ledger.py``.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from app.services.db import SqlResult
from app.services.ledger.engine import LedgerError, PostedTransaction
from app.services.ledger.templates import LedgerTemplate
from app.services.payments import fees as fees_mod
from app.services.payments import fulfillment as ful
from app.services.payments.fees import (
    book_collection_fee,
    book_transfer_fee,
    collection_fee_idempotency_key,
    fee_fields_from_provider_raw,
    parse_fee_ngwee,
    transfer_fee_idempotency_key,
)

CG = "c0ffee00-0000-4000-8000-000000000001"
PAYMENT = "c0ffee00-0000-4000-8000-000000000002"
ORDER_A = "c0ffee00-0000-4000-8000-0000000000a1"
ORDER_B = "c0ffee00-0000-4000-8000-0000000000b1"


class _NoClient:
    client: Any = None


_SVC = _NoClient()


class _Recorder:
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


# ---------------------------------------------------------------------------
# C2: payment = items + delivery + buyer-paid platform fee, with a separate fee leg
# ---------------------------------------------------------------------------


def _fake_orders(monkeypatch: pytest.MonkeyPatch, rows: list[str]) -> _Recorder:
    monkeypatch.setattr(ful, "run_sql_script", lambda _s: SqlResult(ok=True, rows=rows))
    recorder = _Recorder()
    monkeypatch.setattr(ful, "post_transaction", recorder)
    return recorder


def test_buyer_paid_fee_reconciles_and_posts_separate_fee_hold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # K50 ticket + 5% buyer-paid fee (K2.50) → Lenco collected K52.50.
    recorder = _fake_orders(monkeypatch, [f"{ORDER_A}|5000|250"])

    result = ful.fulfill_prepaid_checkout_escrow(
        _SVC, payment_id=PAYMENT, checkout_group_id=CG, amount_ngwee=5_250
    )

    assert result.total_ngwee == 5_250
    assert [c["idempotency_key"] for c in recorder.calls] == [
        ful.escrow_hold_idempotency_key(ORDER_A),
        ful.platform_fee_hold_idempotency_key(ORDER_A),
    ]
    assert all(c["template"] == LedgerTemplate.ESCROW_HOLD for c in recorder.calls)
    assert [c["order_amount_ngwee"] for c in recorder.calls] == [5_000, 250]
    assert all(c["payment_id"] == PAYMENT and c["order_id"] == ORDER_A for c in recorder.calls)


def test_organiser_absorbed_fee_posts_single_hold(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _fake_orders(monkeypatch, [f"{ORDER_A}|5000|0"])
    ful.fulfill_prepaid_checkout_escrow(
        _SVC, payment_id=PAYMENT, checkout_group_id=CG, amount_ngwee=5_000
    )
    assert [c["order_amount_ngwee"] for c in recorder.calls] == [5_000]


def test_multi_order_checkout_sums_fee_per_order(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _fake_orders(monkeypatch, [f"{ORDER_A}|10000|0", f"{ORDER_B}|4000|200"])
    ful.fulfill_prepaid_checkout_escrow(
        _SVC, payment_id=PAYMENT, checkout_group_id=CG, amount_ngwee=14_200
    )
    assert sum(c["order_amount_ngwee"] for c in recorder.calls) == 14_200


@pytest.mark.parametrize("paid", [5_000, 5_249, 5_251])
def test_payment_not_equal_to_items_plus_fee_is_refused(
    monkeypatch: pytest.MonkeyPatch, paid: int
) -> None:
    """Fee ignored (old bug) or under/over-payment → LedgerError, nothing posted."""
    recorder = _fake_orders(monkeypatch, [f"{ORDER_A}|5000|250"])
    with pytest.raises(LedgerError, match="does not match payment amount"):
        ful.fulfill_prepaid_checkout_escrow(
            _SVC, payment_id=PAYMENT, checkout_group_id=CG, amount_ngwee=paid
        )
    assert recorder.calls == []


def test_negative_platform_fee_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _fake_orders(monkeypatch, [f"{ORDER_A}|5000|-250"])
    with pytest.raises(LedgerError, match="negative platform fee"):
        ful.fulfill_prepaid_checkout_escrow(
            _SVC, payment_id=PAYMENT, checkout_group_id=CG, amount_ngwee=4_750
        )
    assert recorder.calls == []


def test_legacy_row_without_fee_column_reads_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _fake_orders(monkeypatch, [f"{ORDER_A}|7000|"])
    ful.fulfill_prepaid_checkout_escrow(
        _SVC, payment_id=PAYMENT, checkout_group_id=CG, amount_ngwee=7_000
    )
    assert [c["order_amount_ngwee"] for c in recorder.calls] == [7_000]


def test_order_lookup_reads_platform_fee_tolerantly(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[str] = []

    def _run(script: str) -> SqlResult:
        captured.append(script)
        return SqlResult(ok=True, rows=[])

    monkeypatch.setattr(ful, "run_sql_script", _run)
    ful._fetch_checkout_orders(CG)
    assert "to_jsonb(o) ->> 'platform_fee_ngwee'" in captured[0]


def test_event_release_captures_held_fee_to_commission(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.escrow import event_release as er

    monkeypatch.setattr(er, "held_platform_fee_ngwee", lambda _o: 250)
    monkeypatch.setattr(er, "remaining_escrow_ngwee", lambda _o: 5_250)
    recorder = _Recorder()
    monkeypatch.setattr(er, "post_transaction", recorder)

    er._capture_held_platform_fee(ORDER_A)

    assert len(recorder.calls) == 1
    call = recorder.calls[0]
    assert call["template"] == LedgerTemplate.COMMISSION_CAPTURE
    assert call["gross_ngwee"] == 250 and call["commission_bps"] == 10_000
    assert call["idempotency_key"] == er.platform_fee_capture_key(ORDER_A)


@pytest.mark.parametrize(("fee", "remaining", "expected"), [(0, 5_000, None), (250, 0, None)])
def test_event_release_skips_fee_capture_when_nothing_to_capture(
    monkeypatch: pytest.MonkeyPatch, fee: int, remaining: int, expected: None
) -> None:
    from app.services.escrow import event_release as er

    monkeypatch.setattr(er, "held_platform_fee_ngwee", lambda _o: fee)
    monkeypatch.setattr(er, "remaining_escrow_ngwee", lambda _o: remaining)
    recorder = _Recorder()
    monkeypatch.setattr(er, "post_transaction", recorder)
    assert er._capture_held_platform_fee(ORDER_A) is expected
    assert recorder.calls == []


# ---------------------------------------------------------------------------
# C6: Lenco fees booked to the `fees` account
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, 0), ("", 0), ("0.25", 25), ("8.50", 850), ("0", 0), (3, 300)],
)
def test_parse_fee_ngwee(raw: object, expected: int) -> None:
    assert parse_fee_ngwee(raw) == expected


@pytest.mark.parametrize("raw", [0.25, "abc", "0.255", "-1.00", True, {"x": 1}])
def test_parse_fee_rejects_non_money(raw: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        parse_fee_ngwee(raw)


def test_fee_fields_from_status_raw_and_webhook_data() -> None:
    assert fee_fields_from_provider_raw({"data": {"fee": "0.25", "bearer": "merchant"}}) == (
        "0.25",
        "merchant",
    )
    assert fee_fields_from_provider_raw({"fee": "1.00"}) == ("1.00", None)
    assert fee_fields_from_provider_raw(None) == (None, None)


def test_collection_fee_booked_once_with_payment_link(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _Recorder()
    monkeypatch.setattr(fees_mod, "post_transaction", recorder)

    book_collection_fee(payment_id=PAYMENT, fee="0.25", bearer="merchant")

    assert recorder.calls == [
        {
            "idempotency_key": collection_fee_idempotency_key(PAYMENT),
            "template": LedgerTemplate.LENCO_FEE,
            "payment_id": PAYMENT,
            "payout_id": None,
            "fee_ngwee": 25,
        }
    ]


@pytest.mark.parametrize(
    ("fee", "bearer"), [(None, "merchant"), ("0.00", "merchant"), ("0.25", "customer")]
)
def test_collection_fee_not_booked_when_zero_or_customer_bears(
    monkeypatch: pytest.MonkeyPatch, fee: object, bearer: object
) -> None:
    recorder = _Recorder()
    monkeypatch.setattr(fees_mod, "post_transaction", recorder)
    assert book_collection_fee(payment_id=PAYMENT, fee=fee, bearer=bearer) is None
    assert recorder.calls == []


def test_unparseable_fee_is_logged_not_booked(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    recorder = _Recorder()
    monkeypatch.setattr(fees_mod, "post_transaction", recorder)
    with caplog.at_level("ERROR"):
        assert book_transfer_fee(payout_id=PAYMENT, fee=0.5) is None
    assert recorder.calls == []
    assert "Lenco fee not booked" in caplog.text


def test_transfer_fee_ledger_failure_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(**_kwargs: Any) -> PostedTransaction:
        raise LedgerError("ledger post failed")

    monkeypatch.setattr(fees_mod, "post_transaction", _boom)
    with pytest.raises(LedgerError):
        book_transfer_fee(payout_id=PAYMENT, fee="8.50")


def test_transfer_fee_key_is_payout_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _Recorder()
    monkeypatch.setattr(fees_mod, "post_transaction", recorder)
    book_transfer_fee(payout_id=PAYMENT, fee="8.50")
    assert recorder.calls[0]["idempotency_key"] == transfer_fee_idempotency_key(PAYMENT)
    assert recorder.calls[0]["fee_ngwee"] == 850
    assert recorder.calls[0]["payout_id"] == PAYMENT


def test_successful_webhook_books_collection_fee(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.support.webhook_evidence import verified_webhook_row
    from tests.test_payment_state import FakeServiceClient, FakeSupabaseClient

    booked: list[dict[str, Any]] = []
    monkeypatch.setattr(
        fees_mod, "book_collection_fee", lambda **kwargs: booked.append(kwargs)
    )
    fake = FakeSupabaseClient()
    service = FakeServiceClient(fake)
    fake.tables["payments"].rows.append(
        {
            "id": PAYMENT,
            "checkout_group_id": CG,
            "provider": "lenco",
            "rail": "mtn",
            "lenco_reference": "ord-fee-1",
            "amount_ngwee": 1_000,
            "status": "pay_offline",
            "raw": {},
        }
    )
    webhook_id = str(uuid.uuid4())
    # Verified signature evidence (untrusted rows are quarantined first).
    fake.tables["webhook_events"].rows.append(
        verified_webhook_row(
            {
                "id": webhook_id,
                "provider": "lenco",
                "event_id": "evt-fee-1",
                "processed_at": None,
                "raw": {
                    "event": "collection.successful",
                    "data": {
                        "reference": "ord-fee-1",
                        "status": "successful",
                        "amount": "10.00",
                        "currency": "ZMW",
                        "fee": "0.25",
                        "bearer": "merchant",
                    },
                },
            }
        )
    )
    from app.services.payments.state import process_webhook_event

    outcome = process_webhook_event(service, webhook_event_id=webhook_id)

    assert outcome is not None
    assert booked == [{"payment_id": PAYMENT, "fee": "0.25", "bearer": "merchant"}]


# ---------------------------------------------------------------------------
# B1 / C1: migration contract (static — DB replay runs in CI `migrations` job)
# ---------------------------------------------------------------------------


def _seed_migration_sql() -> str:
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    migrations = root / "supabase/migrations"
    return "\n".join(
        (migrations / name).read_text()
        for name in (
            "20261107130000_seed_ledger_accounts.sql",
            # Platform delivery revenue (pilot money fix): the fee is not vendor money.
            "20261113120500_delivery_revenue_ledger_account.sql",
        )
    )


def test_seed_migration_covers_every_kind_the_engine_resolves() -> None:
    from app.services.ledger.templates import PLATFORM_ACCOUNT_KINDS, VENDOR_ACCOUNT_KINDS

    sql = _seed_migration_sql()
    for kind in PLATFORM_ACCOUNT_KINDS | VENDOR_ACCOUNT_KINDS:
        assert f"'{kind}'" in sql, kind
    # Idempotent against the 0006 partial unique indexes.
    assert "on conflict (kind) where vendor_id is null do nothing" in sql
    assert sql.count("on conflict (kind, vendor_id) where vendor_id is not null do nothing") >= 2


def test_seed_migration_provisions_accounts_inside_atomic_kyc_approve() -> None:
    sql = _seed_migration_sql()
    body = sql[sql.index("create or replace function public.approve_kyc_vendor") :]
    # Both the first-approval and the idempotent re-approval paths provision.
    assert body.count("public.ensure_vendor_ledger_accounts(v_vendor.id)") == 2
    fn = "public.ensure_vendor_ledger_accounts(uuid)"
    assert f"grant execute on function {fn} to postgres, service_role" in sql
    assert f"revoke execute on function {fn} from public, anon, authenticated" in sql


def test_seed_migration_sets_pilot_full_deposit_without_overriding() -> None:
    sql = _seed_migration_sql()
    assert "'service_deposit_pct',\n    '100'::jsonb" in sql
    tail = sql[sql.index("'service_deposit_pct'") :]
    assert "on conflict (key) do nothing" in tail


def test_service_deposit_code_default_is_full_upfront() -> None:
    from app.services.rfq.engagement import DEFAULT_SERVICE_DEPOSIT_PCT, compute_deposit_ngwee

    assert DEFAULT_SERVICE_DEPOSIT_PCT == 100
    assert compute_deposit_ngwee(total_job_ngwee=123_457, deposit_pct=100) == 123_457


# ---------------------------------------------------------------------------
# C2 on #718's live path: the atomic settlement RPC posts the fee leg
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def settlement_db() -> Any:
    from tests.rls.conftest import (
        PgConn,
        apply_migrations,
        resolve_db_url,
        schema_ready,
        seed_matrix_fixtures,
    )

    url = resolve_db_url()
    conn = PgConn(url)
    if not conn.run("SELECT 1").ok:
        pytest.skip(f"Postgres not reachable at {url}")
    if not schema_ready(conn):
        conn.run("DROP SCHEMA IF EXISTS public CASCADE")
        conn.run("CREATE SCHEMA public")
        conn.run("DROP SCHEMA IF EXISTS auth CASCADE")
        apply_migrations(conn)
    seed_matrix_fixtures(conn)
    return conn


def _seed_fee_checkout(
    conn: Any, *, item: int, delivery: int, fee: int, paid: int
) -> tuple[str, str]:
    import json

    cg, order, payment = (str(uuid.uuid4()) for _ in range(3))
    observation = json.dumps(
        {
            "reference": f"ord-{payment}",
            "currency": "ZMW",
            "amount_ngwee": paid,
            "provider_reference": f"synthetic-{payment}",
            "source": "c2-fee-leg-test",
        }
    )
    seeded = conn.run_script(
        f"""
        INSERT INTO public.checkout_groups (
          id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee,
          total_ngwee, status
        ) VALUES ('{cg}', '11111111-1111-1111-1111-111111111111', 'cg-{cg}', {item},
          {delivery}, {paid}, 'pending');
        INSERT INTO public.orders (
          id, checkout_group_id, vendor_id, customer_id, status, fulfilment,
          delivery_fee_ngwee, platform_fee_ngwee, cod, commission_snapshot
        ) VALUES ('{order}', '{cg}', 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
          '11111111-1111-1111-1111-111111111111', 'placed', 'delivery', {delivery},
          {fee}, false, '{{}}'::jsonb);
        INSERT INTO public.order_items (
          id, order_id, item_kind, qty, unit_price_ngwee, title_snapshot
        ) VALUES ('{uuid.uuid4()}', '{order}', 'product', 1, {item}, 'C2 ticket');
        INSERT INTO public.payments (
          id, checkout_group_id, provider, rail, lenco_reference, amount_ngwee, status
        ) VALUES ('{payment}', '{cg}', 'lenco', 'mtn', 'ord-{payment}', {paid},
          'ussd_pushed');
        """
    )
    assert seeded.ok, seeded.error
    applied = conn.run(
        f"SELECT public.apply_prepaid_collection_success('{payment}', NULL, "
        f"'c2 fee leg', '{observation}'::jsonb)::text;"
    )
    return order, (applied.rows[0] if applied.ok and applied.rows else applied.error or "")


def _hold_amounts(conn: Any, order_id: str) -> dict[str, int]:
    result = conn.run(
        "SELECT lt.idempotency_key || '|' || (-lp.amount_ngwee)::text "
        "FROM public.ledger_transactions lt "
        "JOIN public.ledger_postings lp ON lp.transaction_id = lt.id "
        "JOIN public.ledger_accounts la ON la.id = lp.account_id "
        f"WHERE lt.order_id = '{order_id}' AND lt.kind = 'escrow_hold' "
        "AND la.kind = 'escrow';"
    )
    assert result.ok
    return {row.split("|")[0]: int(row.split("|")[1]) for row in result.rows}


def test_settlement_rpc_posts_separate_buyer_fee_hold(settlement_db: Any) -> None:
    # K50 ticket + K5 delivery + K2.50 buyer-paid fee; Lenco collected K57.50.
    order, outcome = _seed_fee_checkout(
        settlement_db, item=5_000, delivery=500, fee=250, paid=5_750
    )
    assert '"result": "applied"' in outcome, outcome
    assert _hold_amounts(settlement_db, order) == {
        f"escrow-hold-{order}": 5_500,
        ful.platform_fee_hold_idempotency_key(order): 250,
    }


def test_settlement_rpc_refuses_payment_missing_the_buyer_fee(settlement_db: Any) -> None:
    # Collected only items + delivery: the fee is owed, so nothing settles.
    order, outcome = _seed_fee_checkout(
        settlement_db, item=5_000, delivery=500, fee=250, paid=5_500
    )
    assert '"result": "applied"' not in outcome
    assert _hold_amounts(settlement_db, order) == {}
