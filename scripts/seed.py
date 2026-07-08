#!/usr/bin/env python3
"""Idempotent demo dataset seed for local/staging browsing (home / PLP / PDP)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "services" / "api"
sys.path.insert(0, str(API_ROOT))

from tests.rls.conftest import (  # noqa: E402
    PgConn,
    apply_migrations,
    ensure_local_test_database,
    resolve_db_url,
    seed_matrix_fixtures,
)

ENV_URLS = {
    "local": os.environ.get(
        "SUPABASE_DB_URL", "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
    ),
    "staging": os.environ.get("SUPABASE_DB_URL", ""),
}


def _counts(conn: PgConn) -> dict[str, int]:
    tables = (
        "vendors",
        "vendor_listings",
        "products",
        "events",
        "services",
        "orders",
        "search_documents",
    )
    counts: dict[str, int] = {}
    for table in tables:
        result = conn.run(f"SELECT count(*)::int FROM public.{table}")
        if not result.ok:
            counts[table] = -1
        else:
            counts[table] = int(result.rows[0])
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Vergeo5 demo data (idempotent).")
    parser.add_argument(
        "--env",
        choices=("local", "staging"),
        default="local",
        help="Target environment (staging uses SUPABASE_DB_URL)",
    )
    args = parser.parse_args()

    if args.env == "staging" and not ENV_URLS["staging"]:
        print("SUPABASE_DB_URL is required for --env staging", file=sys.stderr)
        return 1

    os.environ["SUPABASE_DB_URL"] = ENV_URLS[args.env] if args.env == "staging" else ENV_URLS["local"]
    url = resolve_db_url()
    ensure_local_test_database(url)
    conn = PgConn(url)

    if not conn.run("SELECT 1").ok:
        print(f"Cannot reach database at {url}", file=sys.stderr)
        return 1

    if not conn.run("SELECT to_regclass('public.vendors')").rows:
        print("Applying migrations…")
        apply_migrations(conn)

    before = _counts(conn)
    seed_matrix_fixtures(conn)
    after = _counts(conn)

    print(f"Seed complete ({args.env})")
    for table, count in after.items():
        delta = count - before.get(table, 0)
        print(f"  {table}: {count} ({'+' if delta >= 0 else ''}{delta})")

    active_listings = conn.run(
        "SELECT count(*)::int FROM public.vendor_listings WHERE status = 'active'"
    )
    public_search = conn.run(
        "SELECT count(*)::int FROM public.search_documents WHERE is_public = true"
    )
    if active_listings.ok:
        print(f"  active_listings: {active_listings.rows[0]}")
    if public_search.ok:
        print(f"  public_search_documents: {public_search.rows[0]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
