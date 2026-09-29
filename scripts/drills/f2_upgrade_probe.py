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
        for kind in ("pending", "receipt", "card", "ambiguous"):
            fixture = seed(obligations=False)
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
        args.evidence.write_text(json.dumps(fixtures, indent=2) + "\n")
    else:
        fixtures = json.loads(args.evidence.read_text())
        if {f["kind"] for f in fixtures} != {"pending", "receipt", "card", "ambiguous"}:
            raise RuntimeError("upgrade evidence is incomplete")
        for fixture in fixtures:
            order, payment = fixture["order"], fixture["payment"]
            if fingerprint(order, payment) != fixture["before"]:
                raise RuntimeError(f"legacy monetary evidence changed: {fixture['kind']}")
            if sql(
                "SELECT count(*) FROM public.payment_collection_receipts "
                f"WHERE payment_id='{payment}' "
                "AND canonical_status_verified_at IS NOT NULL"
            ) != ["0"]:
                raise RuntimeError("upgrade fabricated canonical card-query evidence")
            count = sql(
                f"SELECT count(*) FROM public.service_payment_obligations WHERE order_id='{order}'"
            )
            if fixture["kind"] == "ambiguous":
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
