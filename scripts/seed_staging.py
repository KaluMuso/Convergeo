#!/usr/bin/env python3
"""Synthetic staging seed — no production PII, orders, payments, or credentials.

Safety:
  - Requires --env staging
  - Refuses production Supabase project ref dpadrlxukcjbewpqympu
  - Refuses if STAGING_API_HOST / API URL is api.vergeo5.com
  - Seeds only synthetic stg-rv-* handles from the staging test-data register
  - Never copies production auth users, orders, payments, or KYC documents

Usage:
  STAGING_SUPABASE_PROJECT_ID=<ref> SUPABASE_DB_URL=<staging-db-url> \\
    python scripts/seed_staging.py --env staging --apply

  # Default is dry-run (prints plan, touches nothing):
  python scripts/seed_staging.py --env staging --dry-run
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "services" / "api"
sys.path.insert(0, str(API_ROOT))

from app.core.env_guards import (  # noqa: E402
    PROD_API_HOST,
    PROD_SUPABASE_PROJECT_REF,
    StagingIsolationError,
    assert_staging_api_host_isolated,
    assert_staging_supabase_isolated,
    extract_supabase_project_ref,
)

# Synthetic prefix reserved in staging-test-data-register.md
SEED_PREFIX = "stg-rv-20260719"

# Stable synthetic UUIDs (v4-shaped, not from production).
FIXTURES: list[dict[str, Any]] = [
    {
        "role": "customer_buyer",
        "handle": f"{SEED_PREFIX}-cust-01",
        "email": f"{SEED_PREFIX}-cust-01@staging.vergeo5.test",
        "phone": "+260970000001",
        "user_id": "a1000000-0000-4000-8000-000000000001",
        "user_role": "customer",
    },
    {
        "role": "vendor_unverified",
        "handle": f"{SEED_PREFIX}-vend-unv",
        "email": f"{SEED_PREFIX}-vend-unv@staging.vergeo5.test",
        "phone": "+260970000002",
        "user_id": "a1000000-0000-4000-8000-000000000002",
        "vendor_id": "b1000000-0000-4000-8000-000000000002",
        "slug": f"{SEED_PREFIX}-vend-unv",
        "user_role": "vendor",
        "vendor_status": "pending",
        "kyc_tier": 0,
    },
    {
        "role": "vendor_kyc_submitted",
        "handle": f"{SEED_PREFIX}-vend-sub",
        "email": f"{SEED_PREFIX}-vend-sub@staging.vergeo5.test",
        "phone": "+260970000003",
        "user_id": "a1000000-0000-4000-8000-000000000003",
        "vendor_id": "b1000000-0000-4000-8000-000000000003",
        "slug": f"{SEED_PREFIX}-vend-sub",
        "user_role": "vendor",
        "vendor_status": "pending",
        "kyc_tier": 1,
    },
    {
        "role": "vendor_approved",
        "handle": f"{SEED_PREFIX}-vend-apr",
        "email": f"{SEED_PREFIX}-vend-apr@staging.vergeo5.test",
        "phone": "+260970000004",
        "user_id": "a1000000-0000-4000-8000-000000000004",
        "vendor_id": "b1000000-0000-4000-8000-000000000004",
        "slug": f"{SEED_PREFIX}-vend-apr",
        "user_role": "vendor",
        "vendor_status": "active",
        "kyc_tier": 2,
    },
    {
        "role": "admin_unauthorized",
        "handle": f"{SEED_PREFIX}-adm-bad",
        "email": f"{SEED_PREFIX}-adm-bad@staging.vergeo5.test",
        "phone": "+260970000005",
        "user_id": "a1000000-0000-4000-8000-000000000005",
        "user_role": "customer",
    },
    {
        "role": "admin_kyc_reviewer",
        "handle": f"{SEED_PREFIX}-adm-kyc",
        "email": f"{SEED_PREFIX}-adm-kyc@staging.vergeo5.test",
        "phone": "+260970000006",
        "user_id": "a1000000-0000-4000-8000-000000000006",
        "user_role": "admin",
    },
]

FORBIDDEN_SUBSTRINGS = (
    PROD_SUPABASE_PROJECT_REF,
    PROD_API_HOST,
)


def _die(msg: str) -> int:
    print(f"ERROR: {msg}", file=sys.stderr)
    return 1


def _assert_no_production_markers(payload: str) -> None:
    lower = payload.lower()
    for marker in FORBIDDEN_SUBSTRINGS:
        if marker.lower() in lower:
            raise StagingIsolationError(
                f"synthetic seed payload must not contain production marker: {marker}"
            )
    # Reject anything that looks like a real consumer email domain.
    if re.search(r"@(gmail|yahoo|outlook|hotmail)\.", lower):
        raise StagingIsolationError("synthetic seed must not use consumer email domains")


def _resolve_project_ref(supabase_url: str, db_url: str) -> str | None:
    if supabase_url:
        ref = extract_supabase_project_ref(supabase_url)
        if ref:
            return ref
    if db_url:
        host = urlparse(db_url).hostname or ""
        match = re.search(r"([a-z0-9]{20})\.supabase\.", host)
        if match:
            return match.group(1)
    staging_id = os.environ.get("STAGING_SUPABASE_PROJECT_ID", "").strip().lower()
    return staging_id or None


def _guard_targets(*, supabase_url: str, db_url: str, api_host: str) -> None:
    ref = _resolve_project_ref(supabase_url, db_url)
    if ref:
        assert_staging_supabase_isolated(f"https://{ref}.supabase.co", env="staging")
    elif supabase_url:
        assert_staging_supabase_isolated(supabase_url, env="staging")

    staging_id = os.environ.get("STAGING_SUPABASE_PROJECT_ID", "").strip().lower()
    if staging_id == PROD_SUPABASE_PROJECT_REF:
        raise StagingIsolationError(
            "STAGING_SUPABASE_PROJECT_ID equals production project ref"
        )
    if api_host:
        assert_staging_api_host_isolated(api_host, env="staging")


def _validate_fixtures() -> None:
    for row in FIXTURES:
        blob = " ".join(str(v) for v in row.values())
        _assert_no_production_markers(blob)
        if SEED_PREFIX not in str(row["handle"]):
            raise StagingIsolationError(
                f"fixture handle missing seed prefix: {row['handle']}"
            )


def _plan() -> None:
    print(f"Synthetic staging seed plan (prefix={SEED_PREFIX})")
    print("  - auth.users + profiles for synthetic roles (no production PII)")
    print("  - vendors with stg-rv-* slugs (unverified / submitted / approved)")
    print("  - NO production orders, payments, KYC document blobs, or credentials")
    print("  - NO copy from production database")
    for row in FIXTURES:
        print(f"  · {row['role']}: {row['handle']} <{row['email']}>")


def _build_seed_sql() -> str:
    """Build idempotent SQL from fixed synthetic constants (no user input)."""
    auth_parts = ["BEGIN;"]
    for row in FIXTURES:
        auth_parts.append(
            f"""
INSERT INTO auth.users (
  instance_id, id, aud, role, email, phone, encrypted_password,
  email_confirmed_at, raw_app_meta_data, raw_user_meta_data, created_at, updated_at
) VALUES (
  '00000000-0000-0000-0000-000000000000', '{row["user_id"]}', 'authenticated',
  'authenticated', '{row["email"]}', '{row["phone"]}', 'staging-hash-not-real',
  timezone('utc', now()), '{{}}'::jsonb, '{{}}'::jsonb,
  timezone('utc', now()), timezone('utc', now())
) ON CONFLICT (id) DO NOTHING;
"""
        )
    auth_parts.append("COMMIT;")

    sql_parts = [
        "BEGIN;",
        "SET LOCAL role service_role;",
        "SET LOCAL \"request.jwt.claims\" = '{\"role\":\"service_role\"}';",
    ]
    for row in FIXTURES:
        sql_parts.append(
            f"INSERT INTO public.profiles (id, phone, display_name) "
            f"VALUES ('{row['user_id']}', '{row['phone']}', '{row['handle']}') "
            f"ON CONFLICT (id) DO UPDATE SET "
            f"phone = EXCLUDED.phone, display_name = EXCLUDED.display_name;"
        )
        sql_parts.append(
            f"INSERT INTO public.user_roles (user_id, role) "
            f"VALUES ('{row['user_id']}', '{row['user_role']}') "
            f"ON CONFLICT (user_id, role) DO NOTHING;"
        )
        if "vendor_id" in row:
            sql_parts.append(
                f"""
INSERT INTO public.vendors (
  id, owner_user_id, slug, display_name, status, kyc_tier
) VALUES (
  '{row["vendor_id"]}', '{row["user_id"]}', '{row["slug"]}', '{row["handle"]}',
  '{row["vendor_status"]}', {row["kyc_tier"]}
) ON CONFLICT (id) DO NOTHING;
"""
            )
    sql_parts.append("COMMIT;")
    return "\n".join(auth_parts) + "\n" + "\n".join(sql_parts)


def _seed(conn: Any) -> None:
    result = conn.run(_build_seed_sql())
    if not result.ok:
        raise RuntimeError(result.error or "seed SQL failed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed synthetic staging fixtures only.")
    parser.add_argument("--env", choices=("staging",), required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply inserts (requires reachable SUPABASE_DB_URL).",
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

    # Dry-run without identifiers still validates fixture purity; when identifiers
    # are present they must pass separation.
    if (
        supabase_url
        or db_url
        or api_host
        or os.environ.get("STAGING_SUPABASE_PROJECT_ID")
        or args.apply
    ):
        try:
            _guard_targets(supabase_url=supabase_url, db_url=db_url, api_host=api_host)
        except StagingIsolationError as exc:
            return _die(str(exc))

    if args.apply and not (
        os.environ.get("STAGING_SUPABASE_PROJECT_ID") or supabase_url or db_url
    ):
        return _die(
            "STAGING_SUPABASE_PROJECT_ID (or STAGING_SUPABASE_URL / SUPABASE_DB_URL) "
            "required for --apply"
        )

    _plan()

    if args.dry_run or not args.apply:
        print("DRY RUN — no database writes. Pass --apply to seed a verified staging DB.")
        return 0

    if not db_url:
        return _die("SUPABASE_DB_URL is required for --apply")

    from tests.rls.conftest import (  # noqa: E402
        PgConn,
        apply_migrations,
        ensure_local_test_database,
        resolve_db_url,
    )

    os.environ["SUPABASE_DB_URL"] = db_url
    url = resolve_db_url()
    ensure_local_test_database(url)
    conn = PgConn(url)
    if not conn.run("SELECT 1").ok:
        return _die("Cannot reach staging database at guarded URL")

    vendors = conn.run("SELECT to_regclass('public.vendors')")
    if not vendors.ok or not vendors.rows or vendors.rows[0] in {"", "null"}:
        print("Applying migrations (including 0056)…")
        apply_migrations(conn)

    # Prefer ledger evidence when the shim provides it.
    ledger = conn.run(
        "SELECT count(*)::int FROM supabase_migrations.schema_migrations "
        "WHERE version LIKE '0056%'"
    )
    if ledger.ok and ledger.rows and int(ledger.rows[0]) < 1:
        print(
            "WARN: migration ledger has no 0056 row (shim may omit ledger)",
            file=sys.stderr,
        )

    try:
        _seed(conn)
    except Exception as exc:  # noqa: BLE001
        return _die(f"seed apply failed: {exc}")

    print(f"Seed complete (staging, prefix={SEED_PREFIX})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
