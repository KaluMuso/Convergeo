"""FP-06/07/08: real independent-connection authority and opposing schedules.

Provider observations and commercial values are isolated synthetic fixtures.
These tests are not provider-backed acceptance and may not run on a shared DB.
"""

import os
import time
from collections.abc import Callable, Generator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import psycopg
import pytest
from app.errors import AppError
from app.services.escrow import order_money_gate
from app.services.orders import state
from app.services.payments.lenco import LencoClient, LencoStrategy
from app.services.payments.reconcile import poll_non_terminal_payments
from tests.lane_d.test_collection_identity_postgrest import _db, _service, _wait_for_db_lock
from tests.lane_d.test_f2_service_funding_postgrest import claim, confirm, fund, seed
from tests.test_lenco_client import STATUS_FIXTURE

pytestmark = [
    pytest.mark.prepaid_settlement_db,
    pytest.mark.skipif(
        not os.environ.get("LANE_D_POSTGREST_URL"), reason="isolated real stack required"
    ),
]


@pytest.fixture(autouse=True)
def bind_real_sql(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(state, "run_sql_script", _db().run)
    monkeypatch.setattr(order_money_gate, "run_sql_script", _db().run)


def cancel(f: dict[str, Any], *, vendor: bool = False, refund_path: bool = False) -> Any:
    return state.transition_order(
        order_id=f["order"],
        event=state.OrderEvent.REJECT if vendor else state.OrderEvent.CANCEL,
        actor_role=state.ActorRole.VENDOR if vendor else state.ActorRole.CUSTOMER,
        actor_id=f["owner"] if vendor else f["buyer"],
        note="F2 synthetic cancellation authority",
        refund_path=refund_path,
    )


def observe(f: dict[str, Any], payment: str, reference: str, leg: str) -> Any:
    return (
        _service()
        .client.rpc(
            "apply_prepaid_collection_success",
            {
                "p_payment_id": payment,
                "p_actor_id": f["buyer"],
                "p_note": "F2 synthetic observation",
                "p_observation": {
                    "reference": reference,
                    "provider_reference": f"synthetic-{payment}",
                    "currency": "ZMW",
                    "amount_ngwee": f[leg]["amount_ngwee"],
                    "canonical_status_verified": True,
                    "source": "f2_isolated_fixture",
                },
            },
        )
        .execute()
        .data
    )


@pytest.mark.parametrize("legs", [(), ("deposit",), ("balance",), ("deposit", "balance")])
@pytest.mark.parametrize("vendor", [False, True])
def test_any_funded_leg_requires_resolution(legs: tuple[str, ...], vendor: bool) -> None:
    f = seed()
    confirm(f)  # Work acknowledgement, no invented funds or deposit-first policy.
    for leg in legs:
        fund(f, leg)
    snapshot = state._fetch_order_snapshot(f["order"])
    assert snapshot is not None and snapshot.has_collected_money is bool(legs)
    if legs:
        with pytest.raises(state.RefundPathRequiredError):
            cancel(f, vendor=vendor)
    else:
        assert cancel(f, vendor=vendor).to_status == state.OrderStatus.CANCELLED


def test_refund_flag_is_not_authority_and_vendor_resolution_is_durable() -> None:
    f = seed()
    confirm(f)
    payment = fund(f, "balance")
    with pytest.raises(state.RefundPathRequiredError):
        cancel(f, refund_path=True)
    stranger = seed()
    with pytest.raises(AppError) as exc:
        cancel({**f, "owner": stranger["owner"]}, vendor=True, refund_path=True)
    assert exc.value.http_status == 403
    assert cancel(f, vendor=True, refund_path=True).to_status == state.OrderStatus.CANCELLED
    result = _db().run(f"""SELECT
      (SELECT gate FROM public.order_money_gates WHERE order_id='{f["order"]}'),
      (SELECT count(*) FROM public.audit_log WHERE entity_id='{f["order"]}'
        AND action='order.financial_resolution_required'),
      (SELECT count(*) FROM public.payment_collection_receipts WHERE payment_id='{payment}');""")
    assert result.ok and result.rows == ["refund|1|1"], result.error


def test_wrong_owner_obligation_does_not_import_unrelated_funding() -> None:
    f, stranger = seed(obligations=False), seed(obligations=False)
    stranger["deposit"] = {"checkout_group_id": stranger["checkout"], "amount_ngwee": 30000}
    fund(stranger, "deposit")
    # A corrupt server-side association is not genuine order ownership evidence.
    result = _db().run(f"""INSERT INTO public.service_payment_obligations
      (order_id,job_id,checkout_group_id,leg,amount_ngwee) VALUES
      ('{f["order"]}','{f["job"]}','{stranger["checkout"]}','balance',30000);""")
    assert result.ok, result.error
    result = _db().run(f"""SELECT public.order_has_collected_money('{f["order"]}');""")
    assert result.ok and result.rows == ["f"], result.error
    assert cancel(f).to_status == state.OrderStatus.CANCELLED


@contextmanager
def stalled_write(table: str, predicate: str) -> Generator[Callable[[], None], None, None]:
    name = "f2_barrier_" + uuid4().hex
    key = uuid4().int % (2**31)
    result = _db().run_script(f"""
      CREATE FUNCTION public.{name}() RETURNS trigger LANGUAGE plpgsql AS $f$
      BEGIN IF {predicate} THEN PERFORM pg_advisory_xact_lock({key}); END IF; RETURN NEW; END; $f$;
      CREATE TRIGGER {name} BEFORE INSERT OR UPDATE ON public.{table}
      FOR EACH ROW EXECUTE FUNCTION public.{name}();
    """)
    assert result.ok, result.error
    try:
        with psycopg.connect(os.environ["SUPABASE_DB_URL"], autocommit=True) as blocker:
            blocker.execute("SELECT pg_advisory_lock(%s)", (key,))

            def release() -> None:
                blocker.execute("SELECT pg_advisory_unlock(%s)", (key,))

            try:
                yield release
            finally:
                release()
    finally:
        result = _db().run_script(
            f"DROP TRIGGER {name} ON public.{table}; DROP FUNCTION public.{name}();"
        )
        assert result.ok, result.error


@pytest.mark.parametrize("first", ["cancellation", "receipt"])
def test_receipt_and_cancellation_opposing_schedules(first: str) -> None:
    f = seed()
    confirm(f)
    payment, reference, claimed = claim(f, "balance")
    assert claimed["result"] == "claimed"
    table = "orders" if first == "cancellation" else "ledger_transactions"
    predicate = (
        f"NEW.id='{f['order']}' AND NEW.status='cancelled'"
        if first == "cancellation"
        else f"NEW.payment_id='{payment}'"
    )
    with stalled_write(table, predicate) as release, ThreadPoolExecutor(max_workers=2) as pool:
        leading = (
            pool.submit(cancel, f)
            if first == "cancellation"
            else pool.submit(observe, f, payment, reference, "balance")
        )
        try:
            _wait_for_db_lock("advisory")
            trailing = (
                pool.submit(observe, f, payment, reference, "balance")
                if first == "cancellation"
                else pool.submit(cancel, f)
            )
            _wait_for_db_lock("transactionid")
        finally:
            release()
        if first == "cancellation":
            assert leading.result(timeout=20).to_status == state.OrderStatus.CANCELLED
            assert trailing.result(timeout=20)["result"] == "late_collection"
        else:
            assert leading.result(timeout=20)["result"] == "applied"
            with pytest.raises(state.RefundPathRequiredError):
                trailing.result(timeout=20)
    result = _db().run(f"""SELECT status,
      (SELECT count(*) FROM public.payment_collection_receipts WHERE payment_id='{payment}'),
      (SELECT count(*) FROM public.payment_collection_exceptions WHERE payment_id='{payment}')
      FROM public.orders WHERE id='{f["order"]}';""")
    expected = "cancelled|0|1" if first == "cancellation" else "placed|1|0"
    assert result.ok and result.rows == [expected], result.error


@pytest.mark.parametrize("first", ["cancellation", "claim"])
def test_claim_and_cancellation_opposing_schedules(first: str) -> None:
    f = seed()
    table = "orders" if first == "cancellation" else "payments"
    predicate = (
        f"NEW.id='{f['order']}' AND NEW.status='cancelled'"
        if first == "cancellation"
        else f"NEW.checkout_group_id='{f['checkout']}'"
    )
    with stalled_write(table, predicate) as release, ThreadPoolExecutor(max_workers=2) as pool:
        leading = (
            pool.submit(cancel, f) if first == "cancellation" else pool.submit(claim, f, "deposit")
        )
        try:
            _wait_for_db_lock("advisory")
            trailing = (
                pool.submit(claim, f, "deposit")
                if first == "cancellation"
                else pool.submit(cancel, f)
            )
            _wait_for_db_lock("transactionid")
        finally:
            release()
        leading_result, trailing_result = leading.result(timeout=20), trailing.result(timeout=20)
    result = trailing_result if first == "cancellation" else leading_result
    assert result[2]["result"] == ("order_not_payable" if first == "cancellation" else "claimed")
    assert claim(f, "deposit")[2]["result"] == "order_not_payable"


@pytest.mark.parametrize("first", ["refund", "release"])
def test_refund_and_release_opposing_schedules(first: str) -> None:
    f = seed()
    fund(f, "deposit")
    confirm(f)
    fund(f, "balance")
    table = "order_money_gates" if first == "refund" else "ledger_transactions"
    predicate = (
        f"NEW.order_id='{f['order']}' AND NEW.gate='refund'"
        if first == "refund"
        else f"NEW.order_id='{f['order']}' AND NEW.kind='release_to_vendor'"
    )
    with stalled_write(table, predicate) as release, ThreadPoolExecutor(max_workers=2) as pool:

        def refund() -> Any:
            return order_money_gate.decide_refund_phase_under_gate(f["order"])

        leading = pool.submit(refund) if first == "refund" else pool.submit(confirm, f)
        try:
            _wait_for_db_lock("advisory")
            trailing = pool.submit(confirm, f) if first == "refund" else pool.submit(refund)
            # Both are scoped advisory waits; inspect the lock count, not a delay.
            for _ in range(200):
                result = _db().run(
                    "SELECT count(*) FROM pg_locks WHERE NOT granted AND locktype='advisory'"
                )
                assert result.ok, result.error
                if int(result.rows[0]) >= 2:
                    break
                time.sleep(0.05)
            else:
                raise AssertionError("second escrow waiter did not block")
        finally:
            release()
        if first == "refund":
            assert leading.result(timeout=20).phase == "pre_release"
            with pytest.raises(Exception, match="service funds held"):
                trailing.result(timeout=20)
        else:
            assert leading.result(timeout=20)["released"]
            assert trailing.result(timeout=20).phase == "post_release"


@pytest.mark.parametrize("kind", ["pending", "legacy_card"])
def test_legacy_adoption_does_not_upgrade_payment_evidence(kind: str) -> None:
    f = seed(obligations=False)
    f["deposit"] = {"checkout_group_id": f["checkout"], "amount_ngwee": 30000}
    if kind == "pending":
        payment, _, result = claim(f, "deposit")
        assert result["result"] == "claimed"
    else:
        payment = fund(f, "deposit", rail="card")
        result = _db().run(f"""UPDATE public.payment_collection_receipts
          SET canonical_status_verified_at=null WHERE payment_id='{payment}';""")
        assert result.ok, result.error
    query = f"""SELECT jsonb_build_object(
      'payment',(SELECT to_jsonb(p) FROM public.payments p WHERE id='{payment}'),
      'receipt',(SELECT to_jsonb(r) FROM public.payment_collection_receipts r
                  WHERE payment_id='{payment}'))::text;"""
    before = _db().run(query)
    assert before.ok, before.error
    path = (
        Path(__file__).resolve().parents[4]
        / "supabase/migrations/20260929120003_adopt_existing_service_obligations.sql"
    )
    adopted = _db().run_file(path)
    assert adopted.ok, adopted.error
    after = _db().run(query)
    assert after.ok and after.rows == before.rows, after.error
    assert confirm(f)["status"] == "awaiting_payment"
    if kind == "legacy_card":
        # No receipt canonical timestamp was invented by adoption or acknowledgement.
        result = _db().run(f"""SELECT canonical_status_verified_at IS NULL
          FROM public.payment_collection_receipts WHERE payment_id='{payment}';""")
        assert result.ok and result.rows == ["t"], result.error


def test_ambiguous_adoption_records_hold_without_financial_mutation() -> None:
    f = seed(obligations=False)
    result = _db().run(f"""INSERT INTO public.order_items(order_id,item_kind,qty,unit_price_ngwee)
      VALUES ('{f["order"]}','service_deposit',1,30000);""")
    assert result.ok, result.error
    path = (
        Path(__file__).resolve().parents[4]
        / "supabase/migrations/20260929120003_adopt_existing_service_obligations.sql"
    )
    for _ in range(2):
        result = _db().run_file(path)
        assert result.ok, result.error
    result = _db().run(f"""SELECT
      (SELECT count(*) FROM public.service_payment_obligations WHERE order_id='{f["order"]}'),
      (SELECT count(*) FROM public.audit_log WHERE entity_id='{f["order"]}'
        AND action='service.obligation_adoption_held'),
      (SELECT count(*) FROM public.ledger_transactions WHERE order_id='{f["order"]}');""")
    assert result.ok and result.rows == ["0|1|0"], result.error


def test_cancellation_failure_rolls_back_resolution_gate_and_audit() -> None:
    f = seed()
    confirm(f)
    payment = fund(f, "balance")
    name = "f2_cancel_failure_" + uuid4().hex
    result = _db().run_script(f"""CREATE FUNCTION public.{name}() RETURNS trigger
      LANGUAGE plpgsql AS $f$ BEGIN IF NEW.id='{f["order"]}' AND NEW.status='cancelled'
      THEN RAISE EXCEPTION 'F2 injected cancellation rollback'; END IF; RETURN NEW; END; $f$;
      CREATE TRIGGER {name} BEFORE UPDATE ON public.orders
      FOR EACH ROW EXECUTE FUNCTION public.{name}();""")
    assert result.ok, result.error
    try:
        with pytest.raises(RuntimeError, match="F2 injected cancellation rollback"):
            cancel(f, vendor=True, refund_path=True)
        result = _db().run(f"""SELECT status,
          (SELECT count(*) FROM public.order_money_gates WHERE order_id='{f["order"]}'),
          (SELECT count(*) FROM public.audit_log WHERE entity_id='{f["order"]}'
            AND action='order.financial_resolution_required'),
          (SELECT count(*) FROM public.payment_collection_receipts WHERE payment_id='{payment}')
          FROM public.orders WHERE id='{f["order"]}';""")
        assert result.ok and result.rows == ["placed|0|0|1"], result.error
    finally:
        result = _db().run_script(
            f"DROP TRIGGER {name} ON public.orders; DROP FUNCTION public.{name}();"
        )
        assert result.ok, result.error


@pytest.mark.asyncio
@pytest.mark.parametrize("valid_identity", [True, False])
async def test_real_f1_poller_to_f2_failure_evidence_controls_retry(valid_identity: bool) -> None:
    """Requires the F1-owned FAILED-observation handoff on the combined tree."""
    f = seed()
    payment, reference, claimed = claim(f, "deposit")
    assert claimed["result"] == "claimed"
    seen: list[str] = []

    def transport(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        if request.url.path != f"/collections/status/{reference}":
            return httpx.Response(404, json={"status": False, "errorCode": "11"})
        seen.append(reference)
        body = deepcopy(STATUS_FIXTURE)
        body["data"].update(reference=reference, amount="300.00", status="failed")
        if not valid_identity:
            body["data"].pop("amount")
        return httpx.Response(200, json=body)

    async with httpx.AsyncClient(
        base_url="https://lenco.test", transport=httpx.MockTransport(transport)
    ) as http:
        strategy = LencoStrategy(
            LencoClient(http_client=http, token="synthetic", base_url="https://lenco.test")
        )
        await poll_non_terminal_payments(
            _service(), query_status=strategy.query_status, older_than_minutes=0
        )
    assert seen == [reference]
    row = (
        _service()
        .client.table("payments")
        .select("raw,status")
        .eq("id", payment)
        .single()
        .execute()
        .data
    )
    assert bool(row["raw"].get("terminal_provider_failure")) is valid_identity
    assert claim(f, "deposit")[2]["result"] == (
        "claimed" if valid_identity else "unresolved_attempt"
    )
