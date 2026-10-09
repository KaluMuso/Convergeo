#!/usr/bin/env python3
"""Provision the passwordless WAHA replay login on one approved staging project."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


PROJECT_REF = "iyasmrmbcrvlfxpzescb"
PROJECT_NAME = "vergeo-sandbox"
DATABASE_HOST = f"db.{PROJECT_REF}.supabase.co"
API_ROOT = f"https://api.supabase.com/v1/projects/{PROJECT_REF}"
SQL_FILE = (
    Path(__file__).resolve().parents[2]
    / "infra/staging/supabase/otp-replay-login.sql"
)
SQL_SHA256 = "8b720b37e9900edb1eea52ed42e017fc173afd2844217dfdad8305da1ec0c9dc"
GUARD_MARKER = "-- RUNNER_INJECTS_STAGING_PROJECT_GUARD"

PREFLIGHT = """
select current_database() as database_name,
       to_regclass('otp_replay.otp_delivery_replay') is not null as table_exists,
       coalesce((select c.relrowsecurity from pg_class c
                 where c.oid = to_regclass('otp_replay.otp_delivery_replay')), false)
         as rls_enabled,
       exists(select 1 from pg_roles where rolname = 'n8n_otp_replay') as login_exists,
       (select count(*) from pg_namespace n
          cross join lateral aclexplode(coalesce(n.nspacl, acldefault('n', n.nspowner))) a
         where a.grantee = 0 and a.privilege_type = 'CREATE'
           and n.nspname not like 'pg_%' and n.nspname <> 'information_schema')
         as public_schema_create_count,
       (select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace
          cross join lateral aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) f
         where p.prosecdef and f.grantee = 0 and f.privilege_type = 'EXECUTE'
           and n.nspname not like 'pg_%' and n.nspname <> 'information_schema'
           and exists (select 1 from aclexplode(coalesce(n.nspacl, acldefault('n', n.nspowner))) s
                        where s.grantee = 0 and s.privilege_type = 'USAGE'))
         as public_reachable_definer_count,
       (select count(*) from pg_class c join pg_namespace n on n.oid = c.relnamespace
         where c.relkind in ('r', 'p', 'v', 'm', 'f')
           and n.nspname not like 'pg_%'
           and n.nspname not in ('information_schema', 'extensions', 'otp_replay')
           and (has_any_column_privilege('public', c.oid, 'SELECT')
             or has_any_column_privilege('public', c.oid, 'INSERT')
             or has_any_column_privilege('public', c.oid, 'UPDATE')
             or has_table_privilege('public', c.oid, 'DELETE')
             or has_table_privilege('public', c.oid, 'TRUNCATE')))
         as public_business_data_privilege_count
"""
POSTCHECK = """
select exists(select 1 from pg_roles where rolname = 'n8n_otp_replay'
              and rolcanlogin and not rolsuper and not rolcreatedb
              and not rolcreaterole and not rolreplication and not rolbypassrls
              and rolconnlimit = 2) as restricted_login_exists,
       exists(select 1 from pg_policies where schemaname = 'otp_replay'
              and tablename = 'otp_delivery_replay'
              and policyname = 'n8n_otp_replay_insert') as insert_policy_exists,
       exists(select 1 from pg_policies where schemaname = 'otp_replay'
              and tablename = 'otp_delivery_replay'
              and policyname = 'n8n_otp_replay_select') as select_policy_exists,
       has_schema_privilege('n8n_otp_replay', 'otp_replay', 'USAGE') as replay_usage,
       has_column_privilege('n8n_otp_replay', 'otp_replay.otp_delivery_replay',
                            'request_id', 'INSERT') as request_id_insert,
       has_column_privilege('n8n_otp_replay', 'otp_replay.otp_delivery_replay',
                            'expires_at', 'INSERT') as expiry_insert,
       has_column_privilege('n8n_otp_replay', 'otp_replay.otp_delivery_replay',
                            'request_id', 'SELECT') as request_id_select,
       has_column_privilege('n8n_otp_replay', 'otp_replay.otp_delivery_replay',
                            'expires_at', 'SELECT') as expiry_select,
       has_table_privilege('n8n_otp_replay', 'otp_replay.otp_delivery_replay',
                           'DELETE') as replay_delete,
       (select count(*) from pg_auth_members where member = 'n8n_otp_replay'::regrole)
         as role_membership_count,
       (select count(*) from pg_namespace n
         where n.nspname not like 'pg_%' and n.nspname <> 'information_schema'
           and has_schema_privilege('n8n_otp_replay', n.oid, 'CREATE'))
         as schema_create_count,
       (select count(*) from pg_class c join pg_namespace n on n.oid = c.relnamespace
         where c.relkind in ('r', 'p', 'v', 'm', 'f')
           and n.nspname not like 'pg_%'
           and n.nspname not in ('information_schema', 'extensions', 'otp_replay')
           and (has_any_column_privilege('n8n_otp_replay', c.oid, 'SELECT')
             or has_any_column_privilege('n8n_otp_replay', c.oid, 'INSERT')
             or has_any_column_privilege('n8n_otp_replay', c.oid, 'UPDATE')
             or has_table_privilege('n8n_otp_replay', c.oid, 'DELETE')
             or has_table_privilege('n8n_otp_replay', c.oid, 'TRUNCATE')))
         as business_data_privilege_count,
       (select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace
         where p.prosecdef and n.nspname not like 'pg_%'
           and n.nspname <> 'information_schema'
           and has_schema_privilege('n8n_otp_replay', n.oid, 'USAGE')
           and has_function_privilege('n8n_otp_replay', p.oid, 'EXECUTE'))
         as reachable_definer_count
"""


def checked_sql() -> str:
    source = SQL_FILE.read_bytes()
    if hashlib.sha256(source).hexdigest() != SQL_SHA256:
        raise ValueError("reviewed staging bootstrap SQL hash changed")
    sql = source.decode("utf-8")
    if sql.count(GUARD_MARKER) != 1:
        raise ValueError("staging project guard marker missing or duplicated")
    return sql.replace(
        GUARD_MARKER,
        f"set local otp_replay.target_project_ref = '{PROJECT_REF}';",
    )


def api_json(token: str, url: str, *, query: str | None = None, read_only: bool = True) -> Any:
    body = None if query is None else json.dumps({"query": query, "read_only": read_only}).encode()
    request = urllib.request.Request(
        url,
        data=body,
        method="GET" if body is None else "POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def one_row(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        payload = payload.get("result", payload.get("data"))
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise ValueError("unexpected database metadata response")
    return payload[0]


def apply(token: str, sql: str) -> None:
    project = api_json(token, API_ROOT)
    if not isinstance(project, dict) or (
        project.get("id") != PROJECT_REF
        or project.get("name") != PROJECT_NAME
        or (project.get("database") or {}).get("host") != DATABASE_HOST
    ):
        raise ValueError("Supabase project identity differs from approved staging target")

    query_url = f"{API_ROOT}/database/query"
    before = one_row(api_json(token, query_url, query=PREFLIGHT))
    if before != {
        "database_name": "postgres",
        "table_exists": True,
        "rls_enabled": True,
        "login_exists": False,
        "public_schema_create_count": 0,
        "public_reachable_definer_count": 0,
        "public_business_data_privilege_count": 0,
    }:
        raise ValueError("replay table or login preflight differs from reviewed state")

    api_json(token, query_url, query=sql, read_only=False)

    after = one_row(api_json(token, query_url, query=POSTCHECK))
    if after != {
        "restricted_login_exists": True,
        "insert_policy_exists": True,
        "select_policy_exists": True,
        "replay_usage": True,
        "request_id_insert": True,
        "expiry_insert": True,
        "request_id_select": True,
        "expiry_select": False,
        "replay_delete": False,
        "role_membership_count": 0,
        "schema_create_count": 0,
        "business_data_privilege_count": 0,
        "reachable_definer_count": 0,
    }:
        raise ValueError(
            "staging login postcheck failed after commit; inspect state, do not rerun automatically"
        )
    print(f"Passwordless replay login provisioned on {PROJECT_REF}; password remains unset")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="perform the guarded staging write")
    args = parser.parse_args()
    try:
        sql = checked_sql()
        if not args.apply:
            print(f"Reviewed staging bootstrap: {PROJECT_REF} sha256={SQL_SHA256}; no request sent")
            return 0
        token = os.environ.get("SUPABASE_ACCESS_TOKEN")
        if not token:
            raise ValueError("SUPABASE_ACCESS_TOKEN must be set privately by the operator")
        apply(token, sql)
        return 0
    except (ValueError, OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        print(f"Staging bootstrap stopped: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
