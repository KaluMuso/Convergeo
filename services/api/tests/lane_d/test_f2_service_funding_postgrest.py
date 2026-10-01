"""F2 monetary decisions on the existing isolated PostgreSQL/PostgREST harness.

Apply allocated F2 proposal after accepted baseline before this suite. Synthetic
provider observations exercise authority/SQL, not provider-backed acceptance.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from typing import Any
from uuid import uuid4

import pytest
from app.services.db import run_sql_script as native_run_sql_script
from app.services.escrow import order_money_gate
from app.services.orders import state as order_state
from postgrest import SyncPostgrestClient
from postgrest.exceptions import APIError
from tests.lane_d.test_collection_identity_postgrest import _db, _jwt, _service

pytestmark = pytest.mark.skipif(
    not os.environ.get("LANE_D_POSTGREST_URL"), reason="F2 needs isolated real PostgreSQL/PostgREST"
)


def seed(*, obligations: bool = True) -> dict[str, Any]:
    buyer, owner, vendor, checkout, order, job, quote, item = [str(uuid4()) for _ in range(8)]
    create_obligations = (
        "SELECT public.create_service_payment_obligations("
        f"'{order}','{job}','{buyer}',100000,30000);"
        if obligations
        else ""
    )
    result = _db().run_script(f"""
    BEGIN;
    INSERT INTO auth.users(id,email) VALUES
      ('{buyer}','{buyer}@test.invalid'),('{owner}','{owner}@test.invalid');
    INSERT INTO public.vendors(id,owner_user_id,slug,display_name,status)
    VALUES ('{vendor}','{owner}','f2-{vendor}','F2 synthetic','active');
    INSERT INTO public.jobs(id,customer_id,category,description,status)
    VALUES ('{job}','{buyer}','home_services','F2 synthetic','accepted');
    INSERT INTO public.job_quotes(id,job_id,provider_vendor_id,amount_ngwee,status)
    VALUES ('{quote}','{job}','{vendor}',100000,'accepted');
    INSERT INTO public.checkout_groups(id,customer_id,idempotency_key,
      subtotal_ngwee,delivery_fee_ngwee,total_ngwee,status)
    VALUES ('{checkout}','{buyer}','{checkout}',30000,0,30000,'pending');
    INSERT INTO public.orders(id,checkout_group_id,vendor_id,customer_id,
      status,fulfilment,cod,commission_snapshot)
    VALUES ('{order}','{checkout}','{vendor}','{buyer}','placed','pickup',false,
    '{{"basis":"total_job_value","lines":[{{"line_total_ngwee":100000,"rate_bps":1200,"wholesale":false}}]}}');
    INSERT INTO public.order_items(id,order_id,item_kind,qty,unit_price_ngwee)
    VALUES ('{item}','{order}','service_deposit',1,30000);
    INSERT INTO public.order_item_services(order_item_id,job_id,quote_id)
    VALUES ('{item}','{job}','{quote}');
    {create_obligations}
    INSERT INTO public.ledger_accounts(kind) VALUES
      ('platform_cash'),('escrow'),('commission_revenue')
    ON CONFLICT DO NOTHING;
    INSERT INTO public.audit_log(actor,action,entity_type,entity_id,after)
    VALUES ('{owner}','job.provider_completed','job','{job}','{{}}');
    COMMIT;
    """)
    assert result.ok, result.error
    legs = (
        _service()
        .client.table("service_payment_obligations")
        .select("*")
        .eq("order_id", order)
        .execute()
        .data
        if obligations
        else []
    )
    return {
        "buyer": buyer,
        "owner": owner,
        "vendor": vendor,
        "order": order,
        "job": job,
        "checkout": checkout,
        **{leg["leg"]: leg for leg in legs},
    }


def claim(f: dict[str, Any], leg: str, rail: str = "mtn") -> tuple[str, str, Any]:
    payment = str(uuid4())
    reference = f"ord-{f[leg]['checkout_group_id']}-{payment}"
    result = (
        _service()
        .client.rpc(
            "claim_payable_payment",
            {
                "p_checkout_id": f[leg]["checkout_group_id"],
                "p_actor_id": f["buyer"],
                "p_payment_id": payment,
                "p_rail": rail,
                "p_reference": reference,
                "p_raw": {},
                "p_resume": False,
            },
        )
        .execute()
        .data
    )
    return payment, reference, result


def fund(f: dict[str, Any], leg: str, rail: str = "mtn") -> str:
    payment, reference, claimed = claim(f, leg, rail)
    assert claimed["result"] == "claimed"
    observation = {
        "reference": reference,
        "amount_ngwee": f[leg]["amount_ngwee"],
        "currency": "ZMW",
        "provider_reference": f"synthetic-{payment}",
        "source": "f2_transport_test",
        "canonical_status_verified": True,
    }
    params = {
        "p_payment_id": payment,
        "p_actor_id": f["buyer"],
        "p_note": "F2 synthetic receipt",
        "p_observation": observation,
    }
    assert (
        _service().client.rpc("apply_prepaid_collection_success", params).execute().data["result"]
        == "applied"
    )
    assert (
        _service().client.rpc("apply_prepaid_collection_success", params).execute().data["result"]
        == "duplicate"
    )
    return payment


def confirm(f: dict[str, Any]) -> Any:
    return (
        _service()
        .client.rpc(
            "confirm_funded_service",
            {
                "p_job_id": f["job"],
                "p_actor_id": f["buyer"],
                "p_system": False,
            },
        )
        .execute()
        .data
    )


def test_deposit_and_balance_each_require_receipt_before_completion() -> None:
    f = seed()
    assert f["deposit"]["checkout_group_id"] != f["balance"]["checkout_group_id"]
    assert claim(f, "balance")[2]["result"] == "obligation_not_payable"
    fund(f, "deposit")
    assert confirm(f)["status"] == "awaiting_payment"
    tx = (
        _service()
        .client.table("ledger_transactions")
        .select("kind")
        .eq("order_id", f["order"])
        .execute()
        .data
    )
    assert [r["kind"] for r in tx] == ["escrow_hold"]
    fund(f, "balance", rail="card")
    assert confirm(f)["released"] is True
    assert confirm(f)["already_confirmed"] is True
    result = _db().run(f"""SELECT la.kind,sum(lp.amount_ngwee)::text
    FROM public.ledger_transactions t JOIN public.ledger_postings lp ON lp.transaction_id=t.id
    JOIN public.ledger_accounts la ON la.id=lp.account_id WHERE t.order_id='{f["order"]}'
    GROUP BY la.kind ORDER BY la.kind;""")
    assert result.ok and result.rows == [
        "commission_revenue|-12000",
        "escrow|0",
        "platform_cash|100000",
        "vendor_payable|-88000",
    ]


@pytest.mark.parametrize("status", ["completed", "expired", "abandoned"])
def test_terminal_checkout_claim_has_no_payment(status: str) -> None:
    f = seed()
    assert (
        _db()
        .run(
            f"UPDATE public.checkout_groups SET status='{status}' "
            f"WHERE id='{f['deposit']['checkout_group_id']}'"
        )
        .ok
    )
    assert claim(f, "deposit")[2]["result"] == "not_payable"
    assert (
        not _service()
        .client.table("payments")
        .select("id")
        .eq("checkout_group_id", f["deposit"]["checkout_group_id"])
        .execute()
        .data
    )


def test_concurrent_claims_have_one_winner() -> None:
    f = seed()
    barrier = Barrier(2)

    def work() -> str:
        barrier.wait(timeout=10)
        return str(claim(f, "deposit")[2]["result"])

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(work) for _ in range(2)]
        outcomes = [v.result(timeout=20) for v in futures]
    assert sorted(outcomes) == ["claimed", "unresolved_attempt"]


def test_browser_roles_cannot_claim_or_confirm() -> None:
    f = seed()
    for role in ["anon", "authenticated"]:
        with SyncPostgrestClient(
            os.environ["LANE_D_POSTGREST_URL"],
            headers={"Authorization": f"Bearer {_jwt(role, subject=f['buyer'])}"},
        ) as client:
            rpc: Any = client.rpc
            with pytest.raises(APIError):
                rpc(
                    "confirm_funded_service",
                    {"p_job_id": f["job"], "p_actor_id": f["buyer"], "p_system": True},
                ).execute()
            with pytest.raises(APIError):
                rpc(
                    "claim_payable_payment",
                    {
                        "p_checkout_id": f["deposit"]["checkout_group_id"],
                        "p_actor_id": f["buyer"],
                        "p_payment_id": str(uuid4()),
                        "p_rail": "card",
                        "p_reference": "ord-denied",
                        "p_raw": {},
                        "p_resume": False,
                    },
                ).execute()


def test_refund_gate_blocks_release_after_both_receipts() -> None:
    f = seed()
    fund(f, "deposit")
    confirm(f)
    fund(f, "balance")
    assert (
        _db()
        .run(
            f"INSERT INTO public.order_money_gates(order_id,gate) VALUES ('{f['order']}','refund')"
        )
        .ok
    )
    with pytest.raises(APIError):
        confirm(f)
    assert (
        not _service()
        .client.table("ledger_transactions")
        .select("id")
        .eq("order_id", f["order"])
        .eq("kind", "release_to_vendor")
        .execute()
        .data
    )


def test_release_failure_rolls_back_capture_gate_and_completion() -> None:
    f = seed()
    fund(f, "deposit")
    confirm(f)
    fund(f, "balance")
    name = "f2_fail_" + uuid4().hex
    result = _db().run_script(f"""
    CREATE FUNCTION public.{name}() RETURNS trigger LANGUAGE plpgsql AS $f$
    BEGIN IF NEW.order_id='{f["order"]}' AND NEW.kind='release_to_vendor' THEN
      RAISE EXCEPTION 'F2 injected rollback';
    END IF; RETURN NEW; END; $f$;
    CREATE TRIGGER {name} BEFORE INSERT ON public.ledger_transactions
      FOR EACH ROW EXECUTE FUNCTION public.{name}();
    """)
    assert result.ok, result.error
    try:
        with pytest.raises(APIError):
            confirm(f)
        tx = (
            _service()
            .client.table("ledger_transactions")
            .select("kind")
            .eq("order_id", f["order"])
            .execute()
            .data
        )
        assert [r["kind"] for r in tx] == ["escrow_hold", "escrow_hold"]
        # This private release gate is deliberately not REST-readable. Keep its
        # grants unchanged and inspect rollback through the bound SQL fixture.
        gates = _db().run(
            f"SELECT count(*) FROM public.order_money_gates WHERE order_id='{f['order']}';"
        )
        assert gates.ok and gates.rows == ["0"], gates.error
    finally:
        result = _db().run_script(
            f"DROP TRIGGER {name} ON public.ledger_transactions; DROP FUNCTION public.{name}();"
        )
        assert result.ok
    assert confirm(f)["released"]


def test_concurrent_acknowledgements_and_final_confirmations_are_idempotent() -> None:
    f = seed()
    fund(f, "deposit")

    def pair() -> list[Any]:
        barrier = Barrier(2)

        def work() -> Any:
            barrier.wait(timeout=10)
            return confirm(f)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(work) for _ in range(2)]
            return [future.result(timeout=20) for future in futures]

    assert [r["status"] for r in pair()] == ["awaiting_payment", "awaiting_payment"]
    fund(f, "balance")
    outcomes = pair()
    assert sum(r["released"] for r in outcomes) == 1
    assert sum(r["already_confirmed"] for r in outcomes) == 1
    result = _db().run(f"""SELECT
      (SELECT count(*) FROM public.order_items
       WHERE order_id='{f["order"]}' AND item_kind='service_balance'),
      (SELECT count(*) FROM public.audit_log
       WHERE entity_id='{f["job"]}' AND action='job.work_acknowledged'),
      (SELECT count(*) FROM public.ledger_transactions
       WHERE order_id='{f["order"]}' AND kind='commission_capture'),
      (SELECT count(*) FROM public.ledger_transactions
       WHERE order_id='{f["order"]}' AND kind='release_to_vendor');""")
    assert result.ok and result.rows == ["1|1|1|1"], result.error


def test_actual_refund_gate_and_funded_release_cannot_both_win(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    f = seed()
    fund(f, "deposit")
    confirm(f)
    fund(f, "balance")
    # Run the production gate's SQL against the same disposable database as REST.
    monkeypatch.setattr(order_money_gate, "run_sql_script", _db().run)
    barrier = Barrier(2)

    def refund() -> str:
        barrier.wait(timeout=10)
        return order_money_gate.decide_refund_phase_under_gate(f["order"]).phase

    def release() -> str:
        barrier.wait(timeout=10)
        try:
            assert confirm(f)["released"]
            return "released"
        except APIError as exc:
            assert "service funds held" in str(exc)
            return "held"

    with ThreadPoolExecutor(max_workers=2) as pool:
        refund_future, release_future = pool.submit(refund), pool.submit(release)
        outcome = (refund_future.result(timeout=20), release_future.result(timeout=20))
    assert outcome in {("pre_release", "held"), ("post_release", "released")}
    result = _db().run(f"""SELECT gate,
      (SELECT count(*) FROM public.ledger_transactions
       WHERE order_id='{f["order"]}' AND kind='release_to_vendor')
      FROM public.order_money_gates WHERE order_id='{f["order"]}';""")
    expected = "refund|0" if outcome[0] == "pre_release" else "release|1"
    assert result.ok and result.rows == [expected], result.error


def test_cancellation_racing_claim_preserves_late_money_without_fulfilment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    f = seed()
    monkeypatch.setattr(order_state, "run_sql_script", native_run_sql_script)
    barrier = Barrier(2)

    def cancel() -> Any:
        barrier.wait(timeout=10)
        return order_state.transition_order(
            order_id=f["order"],
            event=order_state.OrderEvent.CANCEL,
            actor_role=order_state.ActorRole.CUSTOMER,
            actor_id=f["buyer"],
            note="F2 claim race",
        )

    def pay() -> tuple[str, str, Any]:
        barrier.wait(timeout=10)
        return claim(f, "deposit")

    with ThreadPoolExecutor(max_workers=2) as pool:
        cancel_future, claim_future = pool.submit(cancel), pool.submit(pay)
        assert cancel_future.result(timeout=20).to_status == order_state.OrderStatus.CANCELLED
        payment, reference, claimed = claim_future.result(timeout=20)
    assert claimed["result"] in {"claimed", "order_not_payable"}
    if claimed["result"] == "claimed":
        result = (
            _service()
            .client.rpc(
                "apply_prepaid_collection_success",
                {
                    "p_payment_id": payment,
                    "p_actor_id": f["buyer"],
                    "p_note": "F2 late provider evidence",
                    "p_observation": {
                        "reference": reference,
                        "provider_reference": f"synthetic-{payment}",
                        "amount_ngwee": 30000,
                        "currency": "ZMW",
                        "source": "f2_transport_test",
                    },
                },
            )
            .execute()
            .data
        )
        assert result["result"] == "late_collection"
        exceptions = (
            _service()
            .client.table("payment_collection_exceptions")
            .select("payment_id")
            .eq("payment_id", payment)
            .execute()
            .data
        )
        assert len(exceptions) == 1
    result = _db().run(f"""SELECT status,
      (SELECT count(*) FROM public.ledger_transactions WHERE order_id='{f["order"]}')
      FROM public.orders WHERE id='{f["order"]}';""")
    assert result.ok and result.rows == ["cancelled|0"], result.error


def test_metadata_adoption_preserves_existing_receipt_and_ledger() -> None:
    f = seed(obligations=False)
    f["deposit"] = {"checkout_group_id": f["checkout"], "amount_ngwee": 30000}
    payment = fund(f, "deposit")

    def fingerprint() -> list[str]:
        result = _db().run(f"""SELECT jsonb_build_object(
          'payment',(SELECT to_jsonb(p) FROM public.payments p WHERE id='{payment}'),
          'receipt',(SELECT to_jsonb(r) FROM public.payment_collection_receipts r
                     WHERE payment_id='{payment}'),
          'ledger',(SELECT jsonb_agg(to_jsonb(t) ORDER BY id) FROM public.ledger_transactions t
                    WHERE order_id='{f["order"]}'),
          'postings',(SELECT jsonb_agg(to_jsonb(lp) ORDER BY lp.id)
                      FROM public.ledger_postings lp JOIN public.ledger_transactions t
                        ON t.id=lp.transaction_id WHERE t.order_id='{f["order"]}'))::text;""")
        assert result.ok, result.error
        return result.rows

    before = fingerprint()
    proposal = (
        Path(__file__).resolve().parents[4]
        / "supabase/migrations/20260930203100_service_adoption_ambiguity_holds.sql"
    )
    for _ in range(2):
        result = _db().run_file(proposal)
        assert result.ok, result.error
        assert fingerprint() == before
    result = _db().run(f"""SELECT leg,amount_ngwee FROM public.service_payment_obligations
      WHERE order_id='{f["order"]}' ORDER BY leg;""")
    assert result.ok and result.rows == ["balance|70000", "deposit|30000"], result.error


def test_balance_receipt_requires_refund_path_even_without_deposit_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shared orders/state.py handoff: original-checkout-only paid checks are unsafe.

    Intentionally not xfailed: the integrated candidate must satisfy this gate.
    No deposit-first business policy is assumed by the payable-obligation model.
    """
    f = seed()
    assert confirm(f)["status"] == "awaiting_payment"
    fund(f, "balance")
    monkeypatch.setattr(order_state, "run_sql_script", native_run_sql_script)
    with pytest.raises(order_state.RefundPathRequiredError):
        order_state.transition_order(
            order_id=f["order"],
            event=order_state.OrderEvent.CANCEL,
            actor_role=order_state.ActorRole.CUSTOMER,
            actor_id=f["buyer"],
            note="F2 funded balance requires refund authority",
        )
    result = _db().run(f"SELECT status FROM public.orders WHERE id='{f['order']}';")
    assert result.ok and result.rows == ["placed"], result.error


# Q1/Q2 regressions: source can prepare these, only real PostgreSQL closes them.
def _system_confirm(f: dict[str, Any]) -> Any:
    from app.services.payments.state import SYSTEM_ACTOR_ID

    return _service().client.rpc("confirm_funded_service", {
        "p_job_id": f["job"], "p_actor_id": SYSTEM_ACTOR_ID, "p_system": True,
    }).execute().data


def test_system_cannot_create_buyer_acknowledgement_or_balance_invoice() -> None:
    f = seed()
    with pytest.raises(APIError, match="buyer acknowledgement required"):
        _system_confirm(f)
    assert claim(f, "balance")[2]["result"] == "obligation_not_payable"
    result = _db().run(f"""SELECT
      (SELECT count(*) FROM public.audit_log WHERE entity_id='{f['job']}'
       AND action='job.work_acknowledged'),
      (SELECT count(*) FROM public.order_items WHERE order_id='{f['order']}'
       AND item_kind='service_balance'),
      (SELECT count(*) FROM public.service_payment_obligations WHERE order_id='{f['order']}'
       AND work_acknowledged_at IS NOT NULL);""")
    assert result.ok and result.rows == ["0|0|0"], result.error


def test_legacy_system_acknowledgement_does_not_authorize_balance() -> None:
    f = seed()
    result = _db().run_script(f"""BEGIN;
      INSERT INTO public.audit_log(actor,action,entity_type,entity_id,after)
      VALUES (NULL,'job.work_acknowledged','job','{f['job']}','{{"system":true}}');
      UPDATE public.service_payment_obligations SET work_acknowledged_at=now()
       WHERE order_id='{f['order']}'; COMMIT;""")
    assert result.ok, result.error
    assert claim(f, "balance")[2]["result"] == "obligation_not_payable"
    with pytest.raises(APIError, match="buyer acknowledgement required"):
        _system_confirm(f)
    # Preserve legacy evidence; never relabel it as customer consent.
    result = _db().run(f"""SELECT count(*)::text FROM public.audit_log
      WHERE entity_id='{f['job']}' AND action='job.work_acknowledged'
        AND actor IS NULL AND after->>'system'='true';""")
    assert result.ok and result.rows == ["1"]


def test_funded_service_still_requires_buyer_acknowledgement() -> None:
    f = seed()
    fund(f, "deposit")
    # Synthetic legacy payable marker: it is NOT explicit buyer consent under Q1/Q2.
    # Recover real funds for that old in-flight attempt without granting new initiation.
    legacy = _db().run_script(f"""BEGIN;
      UPDATE public.service_payment_obligations SET work_acknowledged_at=now()
        WHERE order_id='{f["order"]}';
      INSERT INTO public.audit_log(actor,action,entity_type,entity_id,after)
        VALUES (NULL,'job.work_acknowledged','job','{f["job"]}','{{"system":true}}');
      COMMIT;""")
    assert legacy.ok, legacy.error
    assert claim(f, "balance")[2]["result"] == "obligation_not_payable"
    # Seed the old attempt directly in the private DB; never bypass live initiation.
    payment = str(uuid4())
    reference = f"synthetic-prior-balance-{payment}"
    result = _db().run(f"""INSERT INTO public.payments
      (id,checkout_group_id,provider,rail,lenco_reference,amount_ngwee,status)
      VALUES ('{payment}','{f['balance']['checkout_group_id']}','lenco','mtn',
        '{reference}',{f['balance']['amount_ngwee']},'ussd_pushed');""")
    assert result.ok, result.error
    observed = _service().client.rpc("apply_prepaid_collection_success", {
        "p_payment_id": payment, "p_actor_id": f["buyer"], "p_note": "Synthetic old attempt",
        "p_observation": {"reference": reference, "amount_ngwee": f["balance"]["amount_ngwee"],
                          "currency": "ZMW", "provider_reference": f"synthetic-{payment}",
                          "source": "isolated_test"},
    }).execute().data
    assert observed["result"] == "applied"
    with pytest.raises(APIError, match="buyer acknowledgement required"):
        _system_confirm(f)
    result = _db().run(f"""SELECT status, (SELECT count(*) FROM public.ledger_transactions
      WHERE order_id='{f['order']}' AND kind IN ('commission_capture','release_to_vendor'))
      FROM public.orders WHERE id='{f['order']}';""")
    assert result.ok and result.rows == ["placed|0"], result.error
    assert confirm(f)["released"] is True


def test_worker_can_retry_funded_completion_after_explicit_buyer_acknowledgement() -> None:
    f = seed()
    fund(f, "deposit")
    assert confirm(f)["status"] == "awaiting_payment"
    fund(f, "balance")
    assert _system_confirm(f)["released"] is True
    assert _system_confirm(f)["already_confirmed"] is True
    result = _db().run(f"""SELECT count(*)::text FROM public.ledger_transactions
      WHERE order_id='{f['order']}' AND kind='release_to_vendor';""")
    assert result.ok and result.rows == ["1"]


def test_unpayable_balance_observation_retains_late_money_without_funding() -> None:
    f = seed()
    fund(f, "deposit")
    assert claim(f, "balance")[2]["result"] == "obligation_not_payable"
    payment = str(uuid4())
    reference = f"synthetic-unpayable-{payment}"
    result = _db().run(f"""INSERT INTO public.payments
      (id,checkout_group_id,provider,rail,lenco_reference,amount_ngwee,status)
      VALUES ('{payment}','{f['balance']['checkout_group_id']}','lenco','mtn',
        '{reference}',70000,'ussd_pushed');""")
    assert result.ok, result.error
    params = {
        "p_payment_id": payment, "p_actor_id": f["buyer"], "p_note": "Synthetic unpayable attempt",
        "p_observation": {"reference": reference, "amount_ngwee": 70000, "currency": "ZMW",
                          "provider_reference": f"synthetic-{payment}", "source": "isolated_test"},
    }
    for _ in range(2):
        observed = _service().client.rpc("apply_prepaid_collection_success", params).execute().data
        assert observed["result"] == "late_collection"
        assert observed["reason"] == "service_balance_not_payable"
    result = _db().run(f"""SELECT
      (SELECT occurrences FROM public.payment_collection_exceptions WHERE payment_id='{payment}'),
      (SELECT count(*) FROM public.payment_collection_receipts WHERE payment_id='{payment}'),
      (SELECT count(*) FROM public.ledger_transactions WHERE payment_id='{payment}'),
      (SELECT public.order_has_collected_money('{f['order']}'));
      """)
    assert result.ok and result.rows == ["2|0|0|t"], result.error
    with pytest.raises(APIError, match="buyer acknowledgement required"):
        _system_confirm(f)
    assert confirm(f)["status"] == "awaiting_payment"
    result = _db().run(f"""SELECT count(*) FROM public.ledger_transactions
      WHERE order_id='{f['order']}' AND kind IN ('commission_capture','release_to_vendor');""")
    assert result.ok and result.rows == ["0"], result.error
