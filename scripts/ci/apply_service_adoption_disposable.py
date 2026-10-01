"""DISPOSABLE ONLY: rehearse atomic guarded adoption and truthful migration history.

This is an application proposal, not a production installer. Execution is bound
to a marked, loopback-only ci_adoption_* database. It does not change the shared
deployment workflow or authorize migration-history repair on a hosted target.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import apply_service_adoption as adoption

ROOT = adoption.ROOT
PURPOSE = "LOCAL_DISPOSABLE_ADOPTION_REHEARSAL_ONLY"
DATABASE_RE = re.compile(r"ci_adoption_[a-f0-9]{12}_[a-z0-9_]{1,32}\Z")
MARKER_PREFIX = "CONVERGEO_DISPOSABLE_ADOPTION_REHEARSAL:"
VERSION = adoption.ADOPTION.split("_", 1)[0]
SIGNATURE = "public.create_service_payment_obligations(uuid,uuid,uuid,bigint,bigint)"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fixture_binding() -> dict[str, str]:
    """Bind the local fixture or the exact repository job's explicit service CID."""
    container = os.environ.get("ADOPTION_REHEARSAL_POSTGRES_CONTAINER", "convergeo-continuity-pg")
    hosted_disposable = container != "convergeo-continuity-pg"
    if hosted_disposable:
        # No generic container/DSN escape hatch: alternate IDs are allowed only
        # in the existing exact-source repository disposable GitHub job.
        import run_financial_real_stack as financial

        financial.validate_host()
        source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        if (
            not re.fullmatch(r"[0-9a-f]{64}", container)
            or os.environ.get("QUALIFICATION_SHA") != source
        ):
            raise ValueError("Disposable CI container must bind the exact qualified checkout")
    inspected = json.loads(
        subprocess.check_output(
            [
                "docker",
                "inspect",
                "--format",
                "{{json .}}",
                container,
            ],
            text=True,
        )
    )
    ports = inspected["NetworkSettings"]["Ports"].get("5432/tcp")
    allowed_ips = {"127.0.0.1"} if not hosted_disposable else {"127.0.0.1", "0.0.0.0", "::"}
    valid_ports = (
        isinstance(ports, list)
        and 1 <= len(ports) <= 2
        and all(
            set(binding) == {"HostIp", "HostPort"}
            and binding["HostIp"] in allowed_ips
            and binding["HostPort"] == "54322"
            for binding in ports
        )
        and len({binding["HostIp"] for binding in ports}) == len(ports)
    )
    if (
        not inspected["State"]["Running"]
        or inspected["Config"]["Image"] != "pgvector/pgvector:0.8.0-pg17-trixie"
        or not valid_ports
        or (hosted_disposable and inspected["Id"] != container)
    ):
        raise ValueError("Owned PostgreSQL fixture has an unreviewed image or published port")
    addresses = [
        network["IPAddress"]
        for network in inspected["NetworkSettings"]["Networks"].values()
        if network["IPAddress"]
    ]
    if len(addresses) != 1:
        raise ValueError("Unreviewed fixture network binding")
    return {
        "container_id": inspected["Id"],
        "image_id": inspected["Image"],
        "server_address": addresses[0],
    }


def literal(value: str) -> str:
    """A PostgreSQL dollar literal with a delimiter absent from its contents."""
    tag = "$bound_" + digest(value.encode())[:20] + "$"
    if tag in value:
        raise ValueError("Unexpected literal delimiter collision")
    return tag + value + tag


def inventory(migrations: Path) -> list[dict[str, str]]:
    result = []
    for path in sorted(migrations.glob("*.sql")):
        version, name = path.stem.split("_", 1)
        if not version.isdigit():
            raise ValueError("Unexpected migration version")
        result.append({"version": version, "name": name, "sha256": digest(path.read_bytes())})
    if not result or len({row["version"] for row in result}) != len(result):
        raise ValueError("Missing or duplicate migration versions")
    return result


def history_rows(migrations: Path) -> list[dict[str, Any]]:
    """The fixture ledger records SQL actually applied, never fabricated aliases.

    The adoption file is one original DO statement. Keeping its original bytes
    in statements[1] preserves truthful authority input, not the guarded wrapper.
    Other fixture entries keep their entire executed original file as one array
    element; this is not a claim about the segmentation of historical CLI rows.
    """
    return [
        {"version": row["version"], "name": row["name"], "statements": [path.read_text()]}
        for row, path in zip(inventory(migrations), sorted(migrations.glob("*.sql")), strict=True)
    ]


def plan(database: str, marker: str, migrations: Path) -> dict[str, Any]:
    if not DATABASE_RE.fullmatch(database) or marker != MARKER_PREFIX + database:
        raise ValueError("Only an explicitly marked disposable database can be bound")
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True).strip()
    rows = history_rows(migrations)
    before = next(index for index, row in enumerate(rows) if row["version"] == VERSION)
    # Also verify the two immutable inputs and the guarded composition now.
    adoption.migration_sql(migrations)
    return {
        "schema": 1,
        "purpose": PURPOSE,
        "source_commit": source,
        "source_tree": tree,
        "database": database,
        "database_marker": marker,
        "host": "127.0.0.1",
        "port": 54322,
        "fixture": fixture_binding(),
        "migration_inventory": inventory(migrations),
        "helper_sha256": digest(Path(adoption.__file__).read_bytes()),
        "installer_sha256": digest(Path(__file__).read_bytes()),
        "ledger_before_count": before,
        "expected_ordered_ledger": rows,
    }


def validate_plan(bound: dict[str, Any], migrations: Path) -> None:
    if bound != plan(bound["database"], bound["database_marker"], migrations):
        raise ValueError("Disposable plan no longer matches source, target, helper or history")


def catalog_sql() -> str:
    """Full pg_proc, definition and expanded grantor/grant-option evidence."""
    return f"""SELECT jsonb_build_object(
      'pg_proc',to_jsonb(p), 'owner',pg_get_userbyid(p.proowner),
      'signature',p.oid::regprocedure::text, 'definition',pg_get_functiondef(p.oid),
      'acl',coalesce((SELECT jsonb_agg(to_jsonb(a) ORDER BY
          a.grantor,a.grantee,a.privilege_type,a.is_grantable)
        FROM aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a),'[]'::jsonb))
      FROM pg_proc p WHERE p.oid='{SIGNATURE}'::regprocedure"""


def render(bound: dict[str, Any], migrations: Path) -> str:
    validate_plan(bound, migrations)
    rows = bound["expected_ordered_ledger"]
    row = rows[bound["ledger_before_count"]]
    expected = literal(json.dumps(rows, separators=(",", ":")))
    database, marker = literal(bound["database"]), literal(bound["database_marker"])
    server_address = literal(bound["fixture"]["server_address"])
    before = int(bound["ledger_before_count"])
    guarded_adoption = adoption.migration_sql(migrations)
    authority_check = guarded_adoption.split(
        "create or replace function public.create_service_payment_obligations", 1
    )[0]
    # History comparison is performed after the lock, in the same transaction
    # as guarded execution and insertion. A concurrent wrapper resumes only
    # after it has observed the first wrapper's committed ledger row.
    preflight = f"""SET LOCAL lock_timeout='10s';
SET LOCAL statement_timeout='60s';
DO $target_check$ BEGIN
 IF current_database() IS DISTINCT FROM {database}
    OR inet_server_addr() IS DISTINCT FROM {server_address}::inet
    OR inet_server_port()<>5432
    OR (SELECT shobj_description(oid,'pg_database') FROM pg_database
        WHERE datname=current_database()) IS DISTINCT FROM {marker} THEN
   RAISE EXCEPTION 'Refusing non-owned or non-loopback disposable target';
 END IF;
 IF to_regclass('supabase_migrations.schema_migrations') IS NULL THEN
   RAISE EXCEPTION 'Installed migration history is missing';
 END IF;
END; $target_check$;
SELECT pg_advisory_xact_lock(hashtextextended('convergeo-guarded-service-adoption',0));
LOCK TABLE supabase_migrations.schema_migrations IN EXCLUSIVE MODE;
DO $history_check$ DECLARE
 expected jsonb := {expected}::jsonb;
 actual jsonb;
 prefix jsonb;
BEGIN
 IF (SELECT jsonb_agg(jsonb_build_array(attname,format_type(atttypid,atttypmod))
       ORDER BY attnum) FROM pg_attribute
     WHERE attrelid='supabase_migrations.schema_migrations'::regclass
       AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM
     '[ ["version","text"], ["statements","text[]"], ["name","text"] ]'::jsonb
    OR NOT EXISTS(SELECT 1 FROM pg_attribute
        WHERE attrelid='supabase_migrations.schema_migrations'::regclass
          AND attname='version' AND attnotnull)
    OR NOT EXISTS(SELECT 1 FROM pg_constraint
        WHERE conrelid='supabase_migrations.schema_migrations'::regclass
          AND contype='p' AND conkey=ARRAY[(SELECT attnum FROM pg_attribute
            WHERE attrelid='supabase_migrations.schema_migrations'::regclass
              AND attname='version')]::smallint[]) THEN
   RAISE EXCEPTION 'Unreviewed migration ledger schema';
 END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(m) ORDER BY version),'[]'::jsonb)
   INTO actual FROM supabase_migrations.schema_migrations m;
 SELECT coalesce(jsonb_agg(value ORDER BY ordinal),'[]'::jsonb) INTO prefix
   FROM jsonb_array_elements(expected) WITH ORDINALITY e(value,ordinal)
   WHERE ordinal<=jsonb_array_length(actual);
 IF jsonb_array_length(actual)<{before}
    OR jsonb_array_length(actual)>jsonb_array_length(expected)
    OR actual IS DISTINCT FROM prefix THEN
   RAISE EXCEPTION 'Installed history differs from reviewed executed SQL prefix';
 END IF;
END; $history_check$;
{authority_check}
SELECT EXISTS(SELECT 1 FROM supabase_migrations.schema_migrations
 WHERE version={literal(VERSION)}) AS adoption_already_applied \\gset
\\if :adoption_already_applied
\\echo ADOPTION_RESUMED_NO_SQL_REEXECUTION
\\else
CREATE TEMP TABLE ci_adoption_catalog_before ON COMMIT DROP AS
{catalog_sql()};
"""
    restoration = f"""
DO $restoration_check$ DECLARE actual jsonb; BEGIN
 {catalog_sql()} INTO actual;
 IF actual IS DISTINCT FROM (SELECT jsonb_build_object FROM ci_adoption_catalog_before) THEN
   RAISE EXCEPTION 'Service authority catalog was not restored exactly';
 END IF;
END; $restoration_check$;
"""
    record = (
        "INSERT INTO supabase_migrations.schema_migrations(version,statements,name) VALUES ("
        + literal(row["version"])
        + ",ARRAY["
        + literal(row["statements"][0])
        + "],"
        + literal(row["name"])
        + ");\n"
    )
    return (
        preflight
        + guarded_adoption
        + restoration
        + "-- CI_ADOPTION_BEFORE_HISTORY_BOUNDARY\n"
        + record
        + "-- CI_ADOPTION_AFTER_HISTORY_BOUNDARY\n"
        + "\\echo ADOPTION_APPLIED_AND_RECORDED_ATOMICALLY\n\\endif\n"
    )


def connection_arguments(bound: dict[str, Any]) -> list[str]:
    for key in ("PGSERVICE", "PGSERVICEFILE", "PGHOSTADDR", "PGOPTIONS"):
        if os.environ.get(key):
            raise ValueError("Connection indirection is forbidden for a disposable rehearsal")
    return [
        "psql",
        "-X",
        "-h",
        "127.0.0.1",
        "-p",
        "54322",
        "-U",
        "postgres",
        "-d",
        bound["database"],
        "--single-transaction",
        "-v",
        "ON_ERROR_STOP=1",
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--migrations-dir", type=Path, default=ROOT / "supabase/migrations")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--render", action="store_true")
    action.add_argument("--execute-disposable", action="store_true")
    args = parser.parse_args()
    bound = json.loads(args.plan.read_text())
    sql = render(bound, args.migrations_dir)
    if args.render:
        print(sql)
        return
    result = subprocess.run(connection_arguments(bound), input=sql, text=True, check=False)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
