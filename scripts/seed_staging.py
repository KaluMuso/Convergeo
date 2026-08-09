#!/usr/bin/env python3
"""Synthetic staging seed — no production PII, orders, payments, or credentials.

Safety:
  - Requires --env staging
  - Refuses production Supabase project ref dpadrlxukcjbewpqympu
  - Requires canonical staging ref iyasmrmbcrvlfxpzescb for --apply/--cleanup
  - Refuses if STAGING_API_HOST / API URL is api.vergeo5.com
  - Seeds only synthetic stg-rv-* handles from the staging test-data register
  - Never copies production auth users, orders, payments, or KYC documents

Usage:
  STAGING_SUPABASE_PROJECT_ID=iyasmrmbcrvlfxpzescb SUPABASE_DB_URL=<staging-db-url> \\
    python scripts/seed_staging.py --env staging --apply

  python scripts/seed_staging.py --env staging --cleanup --apply

  # Default is dry-run (prints plan, touches nothing):
  python scripts/seed_staging.py --env staging --dry-run
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "services" / "api"
sys.path.insert(0, str(API_ROOT))

from app.core.env_guards import (  # noqa: E402
    STAGING_SUPABASE_PROJECT_REF,
    StagingIsolationError,
)
from app.staging.seed_sql import (  # noqa: E402
    build_cleanup_sql,
    build_seed_sql,
    parse_verification,
    verification_queries,
)
from app.staging.synthetic_contract import (  # noqa: E402
    CATALOG_FIXTURES,
    FIXTURES,
    KYC_FIXTURES_LEGACY,
    PERSONAS,
    SEED_PREFIX,
    assert_contract_valid,
    guard_seed_targets,
)

# Back-compat re-exports for tests importing the script module directly.
CATALOG_FIXTURE = __import__(
    "app.staging.synthetic_contract", fromlist=["CATALOG_FIXTURE"]
).CATALOG_FIXTURE
KYC_FIXTURES = KYC_FIXTURES_LEGACY

DIRECT_DB_HOST_RE = re.compile(r"^db\.[a-z0-9]+\.supabase\.co$", re.IGNORECASE)


@dataclass(frozen=True)
class SqlResult:
    ok: bool
    rows: list[str]
    error: str | None = None


class StagingPgConn:
    """Minimal psql wrapper for the guarded staging seed, independent of tests."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def run(self, sql: str) -> SqlResult:
        try:
            proc = subprocess.run(
                [
                    "psql",
                    "-X",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-At",
                    "-d",
                    self.dsn,
                    "-c",
                    sql,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            return SqlResult(ok=False, rows=[], error="psql is required to seed staging")
        if proc.returncode != 0:
            return SqlResult(
                ok=False,
                rows=[],
                error=_redact_psql_error(proc.stderr, self.dsn),
            )
        return SqlResult(
            ok=True,
            rows=[line for line in proc.stdout.splitlines() if line],
        )


def _redact_psql_error(stderr: str, dsn: str) -> str:
    message = stderr.strip() or "psql exited without a diagnostic"
    parsed = urlparse(dsn)
    for secret in (dsn, parsed.password):
        if secret:
            message = message.replace(secret, "<redacted>")
    return message


def _connection_hint(dsn: str) -> str | None:
    host = (urlparse(dsn).hostname or "").strip()
    if not DIRECT_DB_HOST_RE.match(host):
        return None
    return (
        f"'{host}' is the direct database host, which resolves to IPv6 only; "
        "GitHub-hosted runners have no IPv6 egress, so this fails even when the "
        "credentials are right. Point STAGING_SUPABASE_DB_URL at the session "
        "pooler instead: postgresql://postgres.<project-ref>:<password>"
        "@aws-0-<region>.pooler.supabase.com:5432/postgres — port 5432, not 6543 "
        "(see infra/ENVIRONMENTS.md)."
    )


def _die(msg: str) -> int:
    print(f"ERROR: {msg}", file=sys.stderr)
    return 1


def _validate_fixtures() -> None:
    assert_contract_valid()


def _plan() -> None:
    print(f"Synthetic staging seed plan (prefix={SEED_PREFIX})")
    print(f"  - staging project ref required for apply/cleanup: {STAGING_SUPABASE_PROJECT_REF}")
    print("  - auth.users + profiles for synthetic personas (no production PII)")
    print("  - vendors: unverified / pending / two approved sellers")
    print("  - business_buyers verified row for B2B wholesale tests")
    print("  - products A–D (multiseller, retail, OOS, wholesale-only)")
    print("  - vendor locations + listing_location_stock for branch stock")
    print("  - staging-synthetic/* listing media (not demo/ popularity)")
    print("  - NO production orders, payments, ledger rows, or credentials")
    for persona in PERSONAS:
        print(f"  · {persona.key}: {persona.handle} <{persona.email}>")


def _require_seed_schema(conn: StagingPgConn) -> None:
    for table in (
        "vendors",
        "categories",
        "products",
        "vendor_listings",
        "vendor_locations",
        "listing_location_stock",
        "business_buyers",
    ):
        result = conn.run(f"SELECT to_regclass('public.{table}')")
        if not result.ok:
            raise RuntimeError(result.error or "cannot verify the staging schema")
        if not result.rows or result.rows[0] in {"", "null"}:
            raise RuntimeError(
                f"staging schema is missing public.{table}; "
                "run the staging migrations before seeding"
            )


def _verify_contract(conn: StagingPgConn) -> None:
    queries = verification_queries()
    results: dict[str, list[str]] = {}
    for key, sql in queries.items():
        result = conn.run(sql)
        if not result.ok:
            raise RuntimeError(result.error or f"cannot verify {key}")
        results[key] = result.rows
    parse_verification(results)


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed synthetic staging fixtures only.")
    parser.add_argument("--env", choices=("staging",), required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply inserts (requires reachable SUPABASE_DB_URL).",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Delete only deterministic stg-rv-* contract rows before optional re-seed.",
    )
    args = parser.parse_args()

    try:
        _validate_fixtures()
    except StagingIsolationError as exc:
        return _die(str(exc))

    supabase_url = os.environ.get("STAGING_SUPABASE_URL") or os.environ.get(
        "SUPABASE_URL", ""
    )
    db_url = os.environ.get("SUPABASE_DB_URL", "")
    api_host = (
        os.environ.get("STAGING_API_HOST")
        or os.environ.get("STAGING_API_BASE_URL")
        or os.environ.get("PUBLIC_API_HOST")
        or ""
    )
    staging_project_id = os.environ.get("STAGING_SUPABASE_PROJECT_ID", "")

    mutating = args.apply or args.cleanup
    if (
        supabase_url
        or db_url
        or api_host
        or staging_project_id
        or mutating
    ):
        try:
            guard_seed_targets(
                supabase_url=supabase_url,
                db_url=db_url,
                api_host=api_host,
                staging_project_id=staging_project_id,
                require_exact_project=mutating,
            )
        except StagingIsolationError as exc:
            return _die(str(exc))

    if mutating and not (
        staging_project_id or supabase_url or db_url
    ):
        return _die(
            "STAGING_SUPABASE_PROJECT_ID (or STAGING_SUPABASE_URL / SUPABASE_DB_URL) "
            "required for --apply/--cleanup"
        )

    _plan()
    print(f"  - catalogue products: {len(CATALOG_FIXTURES)}")

    if args.dry_run or not mutating:
        print("DRY RUN — no database writes. Pass --apply to seed a verified staging DB.")
        return 0

    if not db_url:
        return _die("SUPABASE_DB_URL is required for --apply/--cleanup")

    conn = StagingPgConn(db_url)
    connection = conn.run("SELECT 1")
    if not connection.ok:
        message = (
            "Cannot reach staging database at guarded URL: "
            f"{connection.error or 'psql failed without a diagnostic'}"
        )
        hint = _connection_hint(db_url)
        if hint:
            message = f"{message}\nHINT: {hint}"
        return _die(message)

    try:
        _require_seed_schema(conn)
    except RuntimeError as exc:
        return _die(str(exc))

    if args.cleanup:
        cleanup = conn.run(build_cleanup_sql())
        if not cleanup.ok:
            return _die(cleanup.error or "cleanup SQL failed")
        print(f"Cleanup complete (prefix={SEED_PREFIX})")
        if not args.apply:
            return 0

    seed = conn.run(build_seed_sql())
    if not seed.ok:
        return _die(seed.error or "seed SQL failed")

    try:
        _verify_contract(conn)
    except Exception as exc:  # noqa: BLE001
        return _die(f"seed verification failed: {exc}")

    print(
        "Seed complete "
        f"(staging, prefix={SEED_PREFIX}, products={len(CATALOG_FIXTURES)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
