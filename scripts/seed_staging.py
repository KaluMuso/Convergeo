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
        "vendor_status": "draft",
        "kyc_tier": None,
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
        "vendor_status": "pending_kyc",
        "kyc_tier": None,
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
        "kyc_tier": 1,
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

# KYC records make the submitted and approved fixture states auditable. They
# intentionally contain no storage paths, payment data, or real identities.
KYC_FIXTURES: list[dict[str, Any]] = [
    {
        "id": "c1000000-0000-4000-8000-000000000003",
        "vendor_id": "b1000000-0000-4000-8000-000000000003",
        "tier": 1,
        "status": "submitted",
    },
    {
        "id": "c1000000-0000-4000-8000-000000000004",
        "vendor_id": "b1000000-0000-4000-8000-000000000004",
        "tier": 1,
        "status": "approved",
        "reviewed_by": "a1000000-0000-4000-8000-000000000006",
        "decision_reason": "synthetic staging approval",
    },
]

# This is the sole catalogue fixture. It is deliberately active so search, cart
# and checkout can exercise a complete staging-only product path. It has no
# media, order, payment, payout, or credential data.
CATALOG_FIXTURE: dict[str, Any] = {
    "category_id": "d1000000-0000-4000-8000-000000000001",
    "category_name": "Synthetic staging catalogue",
    "category_slug": f"{SEED_PREFIX}-catalogue",
    "category_path": f"/{SEED_PREFIX}-catalogue",
    "commission_key": "default",
    "product_id": "e1000000-0000-4000-8000-000000000001",
    "product_name": "Synthetic staging test product",
    "product_slug": f"{SEED_PREFIX}-product",
    "product_alias": f"{SEED_PREFIX}-product",
    "product_status": "active",
    "listing_id": "f1000000-0000-4000-8000-000000000001",
    "vendor_id": "b1000000-0000-4000-8000-000000000004",
    "listing_sku": f"{SEED_PREFIX}-list-prd",
    "price_ngwee": 12500,
    "condition": "new",
    "stock_mode": "tracked",
    "stock_qty": 25,
    "wholesale": False,
    "moq": 1,
    "returnable": False,
    "listing_status": "active",
}

VENDOR_STATUSES = frozenset({"draft", "pending_kyc", "active", "suspended"})
VALID_KYC_TIERS = frozenset({1, 2, 3})
KYC_RECORD_STATUSES = frozenset(
    {"submitted", "under_review", "approved", "rejected", "suspended", "revoked"}
)
PRODUCT_STATUSES = frozenset({"pending_moderation", "active", "merged"})
LISTING_STATUSES = frozenset({"draft", "active", "paused", "removed"})
LISTING_CONDITIONS = frozenset({"new", "refurbished"})
STOCK_MODES = frozenset({"tracked", "always_available"})

FORBIDDEN_SUBSTRINGS = (
    PROD_SUPABASE_PROJECT_REF,
    PROD_API_HOST,
)


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
    """Keep a controlled failure diagnostic without ever emitting DB credentials."""
    message = stderr.strip() or "psql exited without a diagnostic"
    parsed = urlparse(dsn)
    for secret in (dsn, parsed.password):
        if secret:
            message = message.replace(secret, "<redacted>")
    return message


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
    vendor_ids: set[str] = set()
    user_ids: set[str] = set()
    for row in FIXTURES:
        blob = " ".join(str(v) for v in row.values())
        _assert_no_production_markers(blob)
        if SEED_PREFIX not in str(row["handle"]):
            raise StagingIsolationError(
                f"fixture handle missing seed prefix: {row['handle']}"
            )
        user_ids.add(str(row["user_id"]))
        if "vendor_id" not in row:
            continue

        status = row.get("vendor_status")
        if status not in VENDOR_STATUSES:
            raise StagingIsolationError(f"invalid synthetic vendor status: {status}")
        tier = row.get("kyc_tier")
        if tier is not None and (
            not isinstance(tier, int) or tier not in VALID_KYC_TIERS
        ):
            raise StagingIsolationError(f"invalid synthetic vendor KYC tier: {tier}")
        vendor_ids.add(str(row["vendor_id"]))

    for record in KYC_FIXTURES:
        if record.get("vendor_id") not in vendor_ids:
            raise StagingIsolationError("synthetic KYC record references an unknown vendor")
        tier = record.get("tier")
        if not isinstance(tier, int) or tier not in VALID_KYC_TIERS:
            raise StagingIsolationError(f"invalid synthetic KYC record tier: {tier}")
        status = record.get("status")
        if status not in KYC_RECORD_STATUSES:
            raise StagingIsolationError(f"invalid synthetic KYC record status: {status}")
        if status == "approved":
            reviewer = record.get("reviewed_by")
            reason = record.get("decision_reason")
            if reviewer not in user_ids or not isinstance(reason, str) or not reason:
                raise StagingIsolationError(
                    "approved synthetic KYC record requires a seeded reviewer and reason"
                )

    catalog_blob = " ".join(str(v) for v in CATALOG_FIXTURE.values())
    _assert_no_production_markers(catalog_blob)
    for field in (
        "category_slug",
        "category_path",
        "product_slug",
        "product_alias",
        "listing_sku",
    ):
        if SEED_PREFIX not in str(CATALOG_FIXTURE[field]):
            raise StagingIsolationError(
                f"synthetic catalogue fixture field missing seed prefix: {field}"
            )

    if not str(CATALOG_FIXTURE["category_path"]).startswith(f"/{SEED_PREFIX}"):
        raise StagingIsolationError("synthetic catalogue path must be staging-prefixed")
    if CATALOG_FIXTURE["vendor_id"] not in vendor_ids:
        raise StagingIsolationError("synthetic catalogue fixture references an unknown vendor")

    approved_vendor = next(
        row for row in FIXTURES if row.get("role") == "vendor_approved"
    )
    if (
        CATALOG_FIXTURE["vendor_id"] != approved_vendor["vendor_id"]
        or approved_vendor["vendor_status"] != "active"
        or approved_vendor["kyc_tier"] not in VALID_KYC_TIERS
    ):
        raise StagingIsolationError(
            "synthetic catalogue fixture must belong to the active approved vendor"
        )

    if CATALOG_FIXTURE["product_status"] != "active" or (
        CATALOG_FIXTURE["product_status"] not in PRODUCT_STATUSES
    ):
        raise StagingIsolationError("synthetic catalogue product must be active")
    if CATALOG_FIXTURE["listing_status"] != "active" or (
        CATALOG_FIXTURE["listing_status"] not in LISTING_STATUSES
    ):
        raise StagingIsolationError("synthetic catalogue listing must be active")
    if CATALOG_FIXTURE["condition"] not in LISTING_CONDITIONS:
        raise StagingIsolationError("invalid synthetic catalogue condition")
    if CATALOG_FIXTURE["stock_mode"] != "tracked" or (
        CATALOG_FIXTURE["stock_mode"] not in STOCK_MODES
    ):
        raise StagingIsolationError("synthetic catalogue stock must be tracked")
    for field in ("price_ngwee", "stock_qty", "moq"):
        value = CATALOG_FIXTURE[field]
        if not isinstance(value, int) or value < 1:
            raise StagingIsolationError(
                f"synthetic catalogue {field} must be a positive integer"
            )
    if CATALOG_FIXTURE["wholesale"] or CATALOG_FIXTURE["returnable"]:
        raise StagingIsolationError(
            "synthetic catalogue fixture must not enable wholesale or returns"
        )


def _plan() -> None:
    print(f"Synthetic staging seed plan (prefix={SEED_PREFIX})")
    print("  - auth.users + profiles for synthetic roles (no production PII)")
    print("  - vendors with stg-rv-* slugs (unverified / submitted / approved)")
    print("  - one active stg-rv-* category/product/listing (no media, orders, or payments)")
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
            tier = "NULL" if row["kyc_tier"] is None else str(row["kyc_tier"])
            sql_parts.append(
                f"""
INSERT INTO public.vendors (
  id, owner_user_id, slug, display_name, status, kyc_tier
) VALUES (
  '{row["vendor_id"]}', '{row["user_id"]}', '{row["slug"]}', '{row["handle"]}',
  '{row["vendor_status"]}', {tier}
) ON CONFLICT (id) DO NOTHING;
"""
            )
    for record in KYC_FIXTURES:
        reviewed_by = record.get("reviewed_by")
        reviewer_sql = f"'{reviewed_by}'" if reviewed_by else "NULL"
        reviewed_at_sql = "timezone('utc', now())" if reviewed_by else "NULL"
        reason = record.get("decision_reason")
        reason_sql = f"'{reason}'" if reason else "NULL"
        sql_parts.append(
            f"""
INSERT INTO public.kyc_records (
  id, vendor_id, tier, doc_storage_paths, momo_name_match, status,
  reviewed_by, reviewed_at, decision_reason
) VALUES (
  '{record["id"]}', '{record["vendor_id"]}', {record["tier"]},
  ARRAY[]::text[], '{{"matched": true}}'::jsonb, '{record["status"]}',
  {reviewer_sql}, {reviewed_at_sql}, {reason_sql}
) ON CONFLICT (id) DO NOTHING;
"""
        )
    catalog = CATALOG_FIXTURE
    sql_parts.append(
        f"""
INSERT INTO public.categories (
  id, name, slug, path, commission_key, prohibited, position
) VALUES (
  '{catalog["category_id"]}', '{catalog["category_name"]}',
  '{catalog["category_slug"]}', '{catalog["category_path"]}',
  '{catalog["commission_key"]}', false, 9999
) ON CONFLICT (id) DO NOTHING;

INSERT INTO public.products (
  id, name, slug, spec, category_id, aliases, status
) VALUES (
  '{catalog["product_id"]}', '{catalog["product_name"]}',
  '{catalog["product_slug"]}', '{{}}'::jsonb, '{catalog["category_id"]}',
  ARRAY['{catalog["product_alias"]}']::text[], '{catalog["product_status"]}'
) ON CONFLICT (id) DO NOTHING;

INSERT INTO public.vendor_listings (
  id, vendor_id, product_id, price_ngwee, condition, stock_mode, stock_qty,
  wholesale, moq, returnable, status, sku
) VALUES (
  '{catalog["listing_id"]}', '{catalog["vendor_id"]}',
  '{catalog["product_id"]}', {catalog["price_ngwee"]}, '{catalog["condition"]}',
  '{catalog["stock_mode"]}', {catalog["stock_qty"]}, false, {catalog["moq"]},
  false, '{catalog["listing_status"]}', '{catalog["listing_sku"]}'
) ON CONFLICT (id) DO NOTHING;
"""
    )
    sql_parts.append("COMMIT;")
    return "\n".join(auth_parts) + "\n" + "\n".join(sql_parts)


def _require_seed_schema(conn: StagingPgConn) -> None:
    for table in ("vendors", "categories", "products", "vendor_listings"):
        result = conn.run(f"SELECT to_regclass('public.{table}')")
        if not result.ok:
            raise RuntimeError(result.error or "cannot verify the staging schema")
        if not result.rows or result.rows[0] in {"", "null"}:
            raise RuntimeError(
                f"staging schema is missing public.{table}; "
                "run the staging migrations before seeding"
            )


def _seed(conn: StagingPgConn) -> None:
    result = conn.run(_build_seed_sql())
    if not result.ok:
        raise RuntimeError(result.error or "seed SQL failed")


def _verify_catalog_fixture(conn: StagingPgConn) -> None:
    catalog = CATALOG_FIXTURE
    result = conn.run(
        "SELECT count(*)::int "
        "FROM public.vendor_listings listing "
        "JOIN public.products product ON product.id = listing.product_id "
        "JOIN public.categories category ON category.id = product.category_id "
        f"WHERE listing.id = '{catalog['listing_id']}' "
        f"AND listing.vendor_id = '{catalog['vendor_id']}' "
        f"AND listing.sku = '{catalog['listing_sku']}' "
        f"AND listing.price_ngwee = {catalog['price_ngwee']} "
        f"AND listing.stock_qty = {catalog['stock_qty']} "
        "AND listing.status = 'active' "
        "AND listing.wholesale = false "
        "AND product.status = 'active' "
        f"AND category.slug = '{catalog['category_slug']}'"
    )
    if not result.ok:
        raise RuntimeError(result.error or "cannot verify the synthetic catalogue fixture")
    if result.rows != ["1"]:
        raise RuntimeError("synthetic catalogue fixture verification failed")


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

    conn = StagingPgConn(db_url)
    connection = conn.run("SELECT 1")
    if not connection.ok:
        return _die(
            "Cannot reach staging database at guarded URL: "
            f"{connection.error or 'psql failed without a diagnostic'}"
        )

    try:
        _require_seed_schema(conn)
    except RuntimeError as exc:
        return _die(str(exc))

    # The deployment job owns migration application; seed only after ledger verification.
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
        _verify_catalog_fixture(conn)
    except Exception as exc:  # noqa: BLE001
        return _die(f"seed apply failed: {exc}")

    print(
        "Seed complete "
        f"(staging, prefix={SEED_PREFIX}, catalogue_sku={CATALOG_FIXTURE['listing_sku']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
