#!/usr/bin/env python3
"""Provision the passwordless WAHA replay login on one approved staging project."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import ssl
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
    Path(__file__).resolve().parents[2] / "infra/staging/supabase/otp-replay-login.sql"
)
SQL_SHA256 = "8097b30dd26884e628cd869979402272c96827329e21f65eb650e1c210a4464c"
GUARD_MARKER = "-- RUNNER_INJECTS_STAGING_PROJECT_GUARD"
PREFLIGHT_MARKER = "-- RUNNER_INJECTS_STAGING_PREFLIGHT_GUARD"
MAX_RESPONSE_BYTES = 65536


class BootstrapError(ValueError):
    """A fixed, operator-safe message; never remote response/exception text."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise BootstrapError("Management API redirect refused")


PREFLIGHT = """
select current_database() as database_name,
       to_regclass('otp_replay.otp_delivery_replay') is not null as table_exists,
       coalesce((select c.relrowsecurity from pg_class c
                 where c.oid = to_regclass('otp_replay.otp_delivery_replay')), false)
         as rls_enabled,
       exists(select 1 from pg_roles where rolname = 'n8n_otp_replay') as login_exists,
       (select count(*) from pg_policy
          where polrelid = to_regclass('otp_replay.otp_delivery_replay'))
         as replay_policy_count,
       (select count(*) from pg_class c join pg_namespace n on n.oid = c.relnamespace
          where n.nspname = 'otp_replay' and c.relkind in ('r', 'p', 'v', 'm', 'f'))
         as replay_relation_count,
       (select array_agg(a.attname::text || ':' || format_type(a.atttypid, a.atttypmod)
                          || ':' || a.attnotnull::text order by a.attnum)
          from pg_attribute a where a.attrelid = to_regclass('otp_replay.otp_delivery_replay')
            and a.attnum > 0 and not a.attisdropped)
         = array['request_id:text:true', 'expires_at:timestamp with time zone:true']
         as replay_columns_valid,
       (select array_agg(pg_get_constraintdef(c.oid) order by c.contype)
          from pg_constraint c where c.conrelid = to_regclass('otp_replay.otp_delivery_replay'))
         = array['CHECK ((request_id ~ ''^[A-Za-z0-9_-]{8,64}$''::text))',
                 'PRIMARY KEY (request_id)'] as replay_constraints_valid,
       exists(select 1 from pg_indexes where schemaname = 'otp_replay'
                and tablename = 'otp_delivery_replay'
                and indexname = 'otp_delivery_replay_expires_at_idx'
                and indexdef = 'CREATE INDEX otp_delivery_replay_expires_at_idx ON otp_replay.otp_delivery_replay USING btree (expires_at)')
         as replay_expiry_index_valid,
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
              and rolcanlogin and not rolinherit and not rolsuper and not rolcreatedb
              and not rolcreaterole and not rolreplication and not rolbypassrls
              and rolconnlimit = 2) as restricted_login_exists,
       exists(select 1 from pg_policies where schemaname = 'otp_replay'
              and tablename = 'otp_delivery_replay'
              and policyname = 'n8n_otp_replay_insert'
              and roles = array['n8n_otp_replay']::name[] and permissive = 'PERMISSIVE'
              and cmd = 'INSERT' and qual is null
              and with_check = '((expires_at > now()) AND (expires_at <= (now() + ''1 day 00:01:00''::interval)))')
         as insert_policy_valid,
       exists(select 1 from pg_policies where schemaname = 'otp_replay'
              and tablename = 'otp_delivery_replay'
              and policyname = 'n8n_otp_replay_select'
              and roles = array['n8n_otp_replay']::name[] and permissive = 'PERMISSIVE'
              and cmd = 'SELECT' and qual = 'true' and with_check is null)
         as select_policy_valid,
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
       has_any_column_privilege('n8n_otp_replay', 'otp_replay.otp_delivery_replay',
                                'UPDATE') as replay_update,
       has_table_privilege('n8n_otp_replay', 'otp_replay.otp_delivery_replay',
                           'TRUNCATE') as replay_truncate,
       has_database_privilege('n8n_otp_replay', 'postgres', 'CONNECT') as database_connect,
       (select c.relrowsecurity from pg_class c
          where c.oid = 'otp_replay.otp_delivery_replay'::regclass) as rls_enabled,
       (select count(*) from pg_policy
          where polrelid = 'otp_replay.otp_delivery_replay'::regclass) as replay_policy_count,
       exists(select 1 from pg_db_role_setting s join pg_database d on d.oid = s.setdatabase
                where s.setrole = 'n8n_otp_replay'::regrole and d.datname = 'postgres'
                  and s.setconfig = array['search_path=pg_catalog, otp_replay, pg_temp'])
         as restricted_search_path,
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


EXPECTED_PREFLIGHT = {
    "database_name": "postgres",
    "table_exists": True,
    "rls_enabled": True,
    "login_exists": False,
    "replay_policy_count": 0,
    "replay_relation_count": 1,
    "replay_columns_valid": True,
    "replay_constraints_valid": True,
    "replay_expiry_index_valid": True,
    "public_schema_create_count": 0,
    "public_reachable_definer_count": 0,
    "public_business_data_privilege_count": 0,
}
EXPECTED_POSTCHECK = {
    "restricted_login_exists": True,
    "insert_policy_valid": True,
    "select_policy_valid": True,
    "replay_usage": True,
    "request_id_insert": True,
    "expiry_insert": True,
    "request_id_select": True,
    "expiry_select": False,
    "replay_delete": False,
    "replay_update": False,
    "replay_truncate": False,
    "database_connect": True,
    "rls_enabled": True,
    "replay_policy_count": 2,
    "restricted_search_path": True,
    "role_membership_count": 0,
    "schema_create_count": 0,
    "business_data_privilege_count": 0,
    "reachable_definer_count": 0,
}


def exact_metadata(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    # JSON true/false must not be accepted as integer counts (or vice versa).
    return actual.keys() == expected.keys() and all(
        type(actual[key]) is type(value) and actual[key] == value
        for key, value in expected.items()
    )


def checked_sql() -> str:
    source = SQL_FILE.read_bytes()
    if hashlib.sha256(source).hexdigest() != SQL_SHA256:
        raise BootstrapError("reviewed staging bootstrap SQL hash changed")
    sql = source.decode("utf-8")
    if sql.count(GUARD_MARKER) != 1 or sql.count(PREFLIGHT_MARKER) != 1:
        raise BootstrapError("staging guard marker missing or duplicated")
    expected = json.dumps(EXPECTED_PREFLIGHT, sort_keys=True).replace("'", "''")
    transactional_preflight = f"""do $preflight$
    declare actual jsonb;
    begin
      select to_jsonb(metadata) into actual from ({PREFLIGHT}) metadata;
      if actual is distinct from '{expected}'::jsonb then
        raise exception 'OTP replay transactional preflight differs from reviewed state';
      end if;
    end $preflight$;"""
    return sql.replace(
        GUARD_MARKER, f"set local otp_replay.target_project_ref = '{PROJECT_REF}';"
    ).replace(PREFLIGHT_MARKER, transactional_preflight)


def api_json(
    token: str, url: str, *, query: str | None = None, read_only: bool = True
) -> Any:
    if url not in {API_ROOT, f"{API_ROOT}/database/query"}:
        raise BootstrapError(
            "Management API target differs from approved staging endpoint"
        )
    if (url == API_ROOT) != (query is None):
        raise BootstrapError("Management API method differs from approved endpoint")
    if (
        not token
        or token != token.strip()
        or any(ord(char) < 33 or ord(char) > 126 for char in token)
    ):
        raise BootstrapError("operator token is missing or malformed")
    body = (
        None
        if query is None
        else json.dumps({"query": query, "read_only": read_only}).encode()
    )
    request = urllib.request.Request(
        url,
        data=body,
        method="GET" if body is None else "POST",
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    request.add_unredirected_header("Authorization", f"Bearer {token}")
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        NoRedirect(),
    )
    with opener.open(request, timeout=20) as response:
        if response.geturl() != url:
            raise BootstrapError("Management API response endpoint changed")
        payload = response.read(MAX_RESPONSE_BYTES + 1)
        if len(payload) > MAX_RESPONSE_BYTES:
            raise BootstrapError(
                "Management API metadata response exceeded the reviewed bound"
            )
        return json.loads(payload)


def one_row(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        payload = payload.get("result", payload.get("data"))
    if (
        not isinstance(payload, list)
        or len(payload) != 1
        or not isinstance(payload[0], dict)
    ):
        raise BootstrapError("unexpected database metadata response")
    return payload[0]


def apply(token: str, sql: str) -> None:
    if sql != checked_sql():
        raise BootstrapError("bootstrap request differs from reviewed guarded SQL")
    project = api_json(token, API_ROOT)
    if (
        not isinstance(project, dict)
        or not isinstance(project.get("database"), dict)
        or (
            project.get("id") != PROJECT_REF
            or project.get("name") != PROJECT_NAME
            or project["database"].get("host") != DATABASE_HOST
        )
    ):
        raise BootstrapError(
            "Supabase project identity differs from approved staging target"
        )
    query_url = f"{API_ROOT}/database/query"
    before = one_row(api_json(token, query_url, query=PREFLIGHT))
    if not exact_metadata(before, EXPECTED_PREFLIGHT):
        raise BootstrapError(
            "replay table or login preflight differs from reviewed state"
        )

    # A lost write response or failed postcheck may follow a committed transaction.
    # Never retry, provision a password, drop the role, or echo the remote failure.
    try:
        api_json(token, query_url, query=sql, read_only=False)
        after = one_row(api_json(token, query_url, query=POSTCHECK))
        if not exact_metadata(after, EXPECTED_POSTCHECK):
            raise BootstrapError("restricted staging login postcheck failed")
    except (
        ValueError,
        OSError,
        urllib.error.URLError,
        http.client.HTTPException,
        TypeError,
    ):
        raise BootstrapError(
            "staging write may have committed or postcheck failed; "
            "inspect state, do not rerun automatically"
        ) from None
    print(
        f"Passwordless replay login provisioned on {PROJECT_REF}; password remains unset"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="perform the guarded staging write"
    )
    args = parser.parse_args()
    try:
        sql = checked_sql()
        if not args.apply:
            print(
                f"Reviewed staging bootstrap: {PROJECT_REF} sha256={SQL_SHA256}; no request sent"
            )
            return 0
        token = os.environ.get("SUPABASE_ACCESS_TOKEN")
        if not token:
            raise BootstrapError(
                "SUPABASE_ACCESS_TOKEN must be set privately by the operator"
            )
        apply(token, sql)
        return 0
    except BootstrapError as exc:
        print(f"Staging bootstrap stopped: {exc}", file=sys.stderr)
        return 1
    except (
        ValueError,
        OSError,
        urllib.error.URLError,
        http.client.HTTPException,
        TypeError,
    ):
        print(
            "Staging bootstrap stopped: local or API validation failure; details suppressed",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
