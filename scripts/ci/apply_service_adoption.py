"""Apply immutable legacy adoption with a transaction-local ambiguity guard.

The guard exists only inside this migration transaction. The original routine is
restored before commit; failure rolls back both metadata adoption and all DDL.
Shared deployment still requires the release operator's reviewed migration plan.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADOPTION = "20260929120003_adopt_existing_service_obligations.sql"
AUTHORITY = "20260929120000_service_payment_obligations_and_claims.sql"
AUTHORITY_SHA256 = "b41aea0c3d5655d219bf775761a03aeb529e542bf965ec01c1b8ea15381d9663"
ADOPTION_SHA256 = "9a06f01acfb190274228e41022c19edf0dad25520ac9f121856e5ae70375aa8c"

GUARD = """
 -- Only the legacy adoption transaction sees this guard. Runtime authority is
 -- restored before commit, with the original owner, signature and grants.
 if exists(select 1 from public.service_payment_obligations
           where checkout_group_id=o.checkout_group_id and order_id<>o.id)
    or exists(select 1 from public.orders
              where checkout_group_id=o.checkout_group_id and id<>o.id)
    or exists(select 1 from public.checkout_groups
              where idempotency_key='service-balance-'||o.id::text) then
   insert into public.audit_log(actor,action,entity_type,entity_id,after)
   select null,'service.obligation_adoption_held','order',o.id,
     jsonb_build_object('reason',case
       when exists(select 1 from public.service_payment_obligations
         where checkout_group_id=o.checkout_group_id and order_id<>o.id)
         then 'checkout_linked_to_other_obligation'
       when exists(select 1 from public.orders
         where checkout_group_id=o.checkout_group_id and id<>o.id)
         then 'checkout_shared_by_orders'
       else 'balance_checkout_already_exists' end)
   where not exists(select 1 from public.audit_log
     where entity_type='order' and entity_id=o.id
       and action='service.obligation_adoption_held');
   return;
 end if;
"""


def migration_sql(migrations: Path) -> str:
    authority = (migrations / AUTHORITY).read_bytes()
    adoption = (migrations / ADOPTION).read_bytes()
    for content, expected in ((authority, AUTHORITY_SHA256), (adoption, ADOPTION_SHA256)):
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError("Immutable service adoption input changed")
    source = authority.decode()
    start = source.index("create function public.create_service_payment_obligations(")
    end = source.index("\ncreate function public.record_collection_failure", start)
    original = source[start:end].replace("create function", "create or replace function", 1)
    anchor = " select * into strict o from public.orders where id=p_order_id for update;"
    if original.count(anchor) != 1:
        raise ValueError("Service authority lock boundary changed")
    guarded = original.replace(anchor, anchor + GUARD)
    # Fail closed if a different routine is installed: never overwrite newer
    # financial authority. Check security metadata and the actual routine body.
    body = original.split("as $$", 1)[1].split("$$;", 1)[0]
    check = """do $adoption_check$ declare authority pg_proc%rowtype; begin
 select * into strict authority from pg_proc where oid=
   'public.create_service_payment_obligations(uuid,uuid,uuid,bigint,bigint)'::regprocedure;
 -- Owner is retained by CREATE OR REPLACE; compare privileges relative to that
 -- actual owner rather than assuming a hosted/local role name.
 if not authority.prosecdef or authority.proisstrict or authority.proleakproof
    or authority.provolatile<>'v' or authority.proparallel<>'u'
    or authority.proconfig is distinct from array['search_path=""']::text[]
    or exists(select 1 from aclexplode(coalesce(authority.proacl,
                 acldefault('f',authority.proowner))) a
              where a.grantee<>authority.proowner
                and (a.grantee<>'service_role'::regrole or a.is_grantable))
    or not exists(select 1 from aclexplode(coalesce(authority.proacl,
                     acldefault('f',authority.proowner))) a
                  where a.grantee='service_role'::regrole
                    and a.privilege_type='EXECUTE') then
   raise exception 'Service obligation authority metadata differs from reviewed legacy input';
 end if;
 if (select prosrc from pg_proc where oid=
   'public.create_service_payment_obligations(uuid,uuid,uuid,bigint,bigint)'::regprocedure)
   is distinct from $adoption_body$""" + body + """$adoption_body$ then
   raise exception 'Service obligation authority differs from reviewed legacy input';
 end if;
end; $adoption_check$;
"""
    return (
        "SET LOCAL lock_timeout='10s';\n" + check + guarded
        + "\n" + adoption.decode() + "\n" + original
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--migrations-dir", type=Path, default=ROOT / "supabase/migrations")
    parser.add_argument("--render", action="store_true", help="Print SQL without executing it")
    args = parser.parse_args()
    sql = migration_sql(args.migrations_dir)
    if args.render:
        print(sql)
        return
    # PG* bindings are supplied by the existing replay/financial job. Never
    # interpolate a DSN into SQL or log credentials.
    result = subprocess.run(
        ["psql", "-X", "--single-transaction", "-v", "ON_ERROR_STOP=1"],
        input=sql, text=True, check=False,
    )
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
