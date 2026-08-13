#!/usr/bin/env python3
"""Read-only Production DB migration head for RELCTRL-01 evidence.

Uses PRODUCTION_READONLY_DB_URL or SUPABASE_DB_URL. Emits JSON to stdout only;
never prints connection strings or credentials.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from typing import Any


class MigrationQueryError(RuntimeError):
    """Raised when the read-only migration ledger query fails."""


def query_migration_head(db_url: str) -> dict[str, str]:
    if not db_url.strip():
        raise MigrationQueryError("database URL is empty")

    count_sql = "SELECT count(*) FROM supabase_migrations.schema_migrations;"
    tip_sql = "SELECT coalesce(max(version),'') FROM supabase_migrations.schema_migrations;"

    def psql(sql: str) -> str:
        proc = subprocess.run(
            ["psql", db_url, "-tA", "-v", "ON_ERROR_STOP=1", "-c", sql],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "psql failed").strip()
            raise MigrationQueryError(detail[:300])
        return (proc.stdout or "").strip()

    count = psql(count_sql)
    tip = psql(tip_sql)
    if not tip:
        raise MigrationQueryError("schema_migrations max(version) is empty")
    return {"migration_count": count, "migration_head": tip}


def build_evidence(
    *,
    candidate_sha: str,
    workflow_run_id: str,
    repository: str,
    db_url: str,
) -> dict[str, Any]:
    observed = query_migration_head(db_url)
    return {
        "schema_version": "1",
        "gate": "RELCTRL-01-production-db",
        "repository": repository,
        "workflow": "capture-production-db-evidence.yml",
        "workflow_run_id": str(workflow_run_id),
        "candidate_sha": candidate_sha.lower(),
        "migration_head": observed["migration_head"],
        "migration_count": int(observed["migration_count"] or "0"),
        "observed_at": datetime.now(UTC).isoformat(),
        "observation_method": "readonly_psql",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture read-only Production DB migration evidence")
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--workflow-run-id", default=os.environ.get("GITHUB_RUN_ID", "local"))
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", "KaluMuso/Convergeo"))
    parser.add_argument(
        "--db-url-env",
        default="PRODUCTION_READONLY_DB_URL",
        help="Environment variable holding a read-only Postgres URL",
    )
    parser.add_argument("--output", type=str, help="Write JSON evidence to path (default stdout)")
    args = parser.parse_args(argv)

    db_url = os.environ.get(args.db_url_env) or os.environ.get("SUPABASE_DB_URL", "")
    try:
        payload = build_evidence(
            candidate_sha=args.candidate_sha,
            workflow_run_id=args.workflow_run_id,
            repository=args.repository,
            db_url=db_url,
        )
    except MigrationQueryError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    text = json.dumps(payload, indent=2) + "\n"
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
