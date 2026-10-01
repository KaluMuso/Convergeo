"""Synthetic before/after evidence for a disposable accepted-baseline upgrade.

Run from services/api with PYTHONPATH=. and the isolated SQL/REST environment.
Never use this on shared or live databases. No provider or notification dispatch.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from tests.lane_d.test_collection_identity_postgrest import _db
from tests.lane_d.test_f2_service_funding_postgrest import seed


def sql(query: str) -> list[str]:
    result = _db().run(query)
    if not result.ok:
        raise RuntimeError(result.error)
    return result.rows


def fingerprint(order: str, payment: str) -> list[str]:
    return sql(f"""SELECT jsonb_build_object(
      'payment',(SELECT to_jsonb(p) FROM public.payments p WHERE id='{payment}'),
      'receipt',(SELECT to_jsonb(r)-'canonical_status_verified_at'
        FROM public.payment_collection_receipts r WHERE payment_id='{payment}'),
      'ledger',(SELECT jsonb_agg(to_jsonb(t) ORDER BY id)
        FROM public.ledger_transactions t WHERE order_id='{order}'),
      'postings',(SELECT jsonb_agg(to_jsonb(lp) ORDER BY lp.id)
        FROM public.ledger_postings lp JOIN public.ledger_transactions t
        ON t.id=lp.transaction_id WHERE t.order_id='{order}'))::text;""")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("seed", "verify"))
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    parsed = urlsplit(os.environ["SUPABASE_DB_URL"])
    if (
        parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.path != "/ci_critical_prepaid"
    ):
        raise RuntimeError(
            "upgrade probe requires the dedicated loopback ci_critical_prepaid database"
        )
    if sql("SELECT current_database()") != ["ci_critical_prepaid"]:
        raise RuntimeError("SQL binding mismatch")
    if args.phase == "seed":
        if sql("SELECT to_regclass('public.service_payment_obligations') IS NULL") != ["t"]:
            raise RuntimeError("seed must run on accepted baseline before F2 migrations")
        fixtures = []
        shared: dict[str, str] | None = None
        for kind in (
            "pending", "receipt", "card", "ambiguous", "healthy",
            "shared_primary", "shared_secondary", "foreign_balance",
        ):
            fixture = seed(obligations=False)
            if kind == "shared_primary":
                shared = fixture
            elif kind == "shared_secondary":
                assert shared is not None
                # Distinct jobs/vendors are each otherwise eligible. Both legacy
                # orders reference the same valid buyer/deposit checkout.
                sql(f"""BEGIN;
                  UPDATE public.orders SET customer_id='{shared['buyer']}',
                    checkout_group_id='{shared['checkout']}' WHERE id='{fixture['order']}';
                  UPDATE public.jobs SET customer_id='{shared['buyer']}'
                    WHERE id='{fixture['job']}'; COMMIT;""")
                fixture["buyer"], fixture["checkout"] = shared["buyer"], shared["checkout"]
            elif kind == "foreign_balance":
                sql(f"""INSERT INTO public.checkout_groups(customer_id,idempotency_key,
                  subtotal_ngwee,delivery_fee_ngwee,total_ngwee,status)
                  VALUES ('{fixture['buyer']}','service-balance-{fixture['order']}',
                    70000,0,70000,'pending');""")
            payment = str(uuid4())
            reference = f"f2-upgrade-{payment}"
            rail = "card" if kind == "card" else "mtn"
            sql(f"""INSERT INTO public.payments
              (id,checkout_group_id,provider,rail,lenco_reference,amount_ngwee,status,raw)
              VALUES ('{payment}','{fixture["checkout"]}','lenco','{rail}',
                '{reference}',30000,'initiated','{{}}');""")
            if kind in {"receipt", "card"}:
                # Invoke the actual accepted-baseline settlement function. This is
                # labelled synthetic transport evidence, never a provider receipt claim.
                result = sql(f"""SELECT public.apply_prepaid_collection_success(
                  '{payment}','{fixture["buyer"]}','F2 synthetic baseline upgrade',
                  '{{"reference":"{reference}","currency":"ZMW","amount_ngwee":30000,
                    "provider_reference":"synthetic-{payment}","source":"f2_upgrade_fixture"}}'
                  ::jsonb)::text;""")
                if json.loads(result[0])["result"] != "applied":
                    raise RuntimeError("baseline fixture settlement did not apply")
            if kind == "ambiguous":
                sql(
                    "UPDATE public.orders SET commission_snapshot='{}' "
                    f"WHERE id='{fixture['order']}'"
                )
            fixtures.append(
                {
                    "kind": kind,
                    "order": fixture["order"],
                    "payment": payment,
                    "before": fingerprint(fixture["order"], payment),
                }
            )
        # Capture after all fixture construction, including checkout sharing.
        for fixture in fixtures:
            order = fixture["order"]
            fixture["spine_before"] = sql(f"""SELECT jsonb_build_object(
              'order',(SELECT to_jsonb(o) FROM public.orders o WHERE id='{order}'),
              'items',(SELECT jsonb_agg(to_jsonb(i) ORDER BY i.id)
                FROM public.order_items i WHERE i.order_id='{order}'),
              'checkout',(SELECT to_jsonb(c) FROM public.checkout_groups c
                JOIN public.orders o ON o.checkout_group_id=c.id WHERE o.id='{order}'),
              'balance_checkout',(SELECT to_jsonb(c) FROM public.checkout_groups c
                WHERE c.idempotency_key='service-balance-'||'{order}'))::text;""")
        args.evidence.write_text(json.dumps(fixtures, indent=2) + "\n")
    else:
        fixtures = json.loads(args.evidence.read_text())
        if {f["kind"] for f in fixtures} != {
            "pending", "receipt", "card", "ambiguous", "healthy",
            "shared_primary", "shared_secondary", "foreign_balance",
        } or len(fixtures) != 8:
            raise RuntimeError("upgrade evidence is incomplete")
        for fixture in fixtures:
            order, payment = fixture["order"], fixture["payment"]
            if fingerprint(order, payment) != fixture["before"]:
                raise RuntimeError(f"legacy monetary evidence changed: {fixture['kind']}")
            spine = json.loads(fixture["spine_before"][0])
            after_spine = json.loads(sql(f"""SELECT jsonb_build_object(
              'order',(SELECT to_jsonb(o) FROM public.orders o WHERE id='{order}'),
              'items',(SELECT jsonb_agg(to_jsonb(i) ORDER BY i.id)
                FROM public.order_items i WHERE i.order_id='{order}'),
              'checkout',(SELECT to_jsonb(c) FROM public.checkout_groups c
                JOIN public.orders o ON o.checkout_group_id=c.id WHERE o.id='{order}'),
              'balance_checkout',(SELECT to_jsonb(c) FROM public.checkout_groups c
                WHERE c.idempotency_key='service-balance-'||'{order}'))::text;""")[0])
            # Healthy adoption creates one new balance checkout; all existing
            # order/item/checkout data and any foreign balance remain identical.
            if spine["balance_checkout"] is None:
                after_spine["balance_checkout"] = None
            if after_spine != spine:
                raise RuntimeError(f"legacy order/checkout evidence changed: {fixture['kind']}")
            if sql(
                "SELECT count(*) FROM public.payment_collection_receipts "
                f"WHERE payment_id='{payment}' "
                "AND canonical_status_verified_at IS NOT NULL"
            ) != ["0"]:
                raise RuntimeError("upgrade fabricated canonical card-query evidence")
            count = sql(
                f"SELECT count(*) FROM public.service_payment_obligations WHERE order_id='{order}'"
            )
            if fixture["kind"] in {
                "ambiguous", "shared_primary", "shared_secondary", "foreign_balance",
            }:
                if count != ["0"] or sql(
                    f"SELECT count(*) FROM public.audit_log WHERE entity_id='{order}' "
                    "AND action='service.obligation_adoption_held'"
                ) != ["1"]:
                    raise RuntimeError("ambiguous legacy order was not durably held")
            elif count != ["2"]:
                raise RuntimeError("valid legacy metadata was not adopted")
        print("F2_UPGRADE_EVIDENCE_PRESERVED")


if __name__ == "__main__":
    main()
