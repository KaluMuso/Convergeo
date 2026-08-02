"""RLS test harness: role-scoped DB sessions and matrix fixture seed."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable, Generator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, cast

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "demo"
REPO_ROOT = Path(__file__).resolve().parents[4]
MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"

DEFAULT_DB_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
LOCAL_FALLBACK_DB_URL = "postgresql:///vergeo5_rls_test"

Outcome = Literal["permit", "deny", "filter"]
Verb = Literal["select", "insert", "update", "delete"]

VERBS: tuple[Verb, ...] = ("select", "insert", "update", "delete")


class Persona(StrEnum):
    ANON = "anon"
    CUSTOMER = "customer"
    OTHER_CUSTOMER = "other_customer"
    VENDOR = "vendor"
    OTHER_VENDOR = "other_vendor"
    ADMIN = "admin"


PERSONA_UIDS: dict[Persona, str | None] = {
    Persona.ANON: None,
    Persona.CUSTOMER: "11111111-1111-1111-1111-111111111111",
    Persona.OTHER_CUSTOMER: "22222222-2222-2222-2222-222222222222",
    Persona.VENDOR: "33333333-3333-3333-3333-333333333333",
    Persona.OTHER_VENDOR: "44444444-4444-4444-4444-444444444444",
    Persona.ADMIN: "66666666-6666-6666-6666-666666666666",
}


class PgError(RuntimeError):
    def __init__(self, message: str, sqlstate: str | None = None) -> None:
        super().__init__(message)
        self.sqlstate = sqlstate


@dataclass
class SqlResult:
    ok: bool
    rows: list[str]
    error: str | None = None
    sqlstate: str | None = None


class PgConn:
    """Thin psql wrapper — no extra Python DB deps."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def run(self, sql: str) -> SqlResult:
        proc = subprocess.run(
            ["psql", self.dsn, "-v", "ON_ERROR_STOP=1", "-At", "-c", sql],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            sqlstate = _extract_sqlstate(proc.stderr)
            return SqlResult(ok=False, rows=[], error=proc.stderr.strip(), sqlstate=sqlstate)
        rows = [line for line in proc.stdout.splitlines() if line]
        if sql.strip().upper().startswith("BEGIN"):
            if rows and rows[-1] == "COMMIT":
                rows = rows[:-1]
            noise = {"BEGIN", "SET", "DO", "ROLLBACK"}
            data = [row for row in rows if row not in noise]
            return SqlResult(ok=True, rows=data[-1:] if data else [])
        return SqlResult(ok=True, rows=rows)

    def run_file(self, path: Path) -> SqlResult:
        proc = subprocess.run(
            ["psql", self.dsn, "-v", "ON_ERROR_STOP=1", "-f", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            sqlstate = _extract_sqlstate(proc.stderr)
            return SqlResult(ok=False, rows=[], error=proc.stderr.strip(), sqlstate=sqlstate)
        return SqlResult(ok=True, rows=[])

    def run_script(self, script: str) -> SqlResult:
        proc = subprocess.run(
            ["psql", self.dsn, "-v", "ON_ERROR_STOP=1", "-At"],
            input=script,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            sqlstate = _extract_sqlstate(proc.stderr)
            return SqlResult(ok=False, rows=[], error=proc.stderr.strip(), sqlstate=sqlstate)
        rows = [line for line in proc.stdout.splitlines() if line]
        return SqlResult(ok=True, rows=rows)


def _extract_sqlstate(stderr: str) -> str | None:
    for line in stderr.splitlines():
        if line.startswith("ERROR:") and "(SQLSTATE " in line:
            start = line.rfind("(SQLSTATE ") + len("(SQLSTATE ")
            end = line.rfind(")")
            if end > start:
                return line[start:end]
    return None


def get_db_url() -> str:
    return os.environ.get("SUPABASE_DB_URL", DEFAULT_DB_URL)


def _db_reachable(url: str) -> bool:
    return PgConn(url).run("SELECT 1").ok


def resolve_db_url() -> str:
    primary = get_db_url()
    fallback = LOCAL_FALLBACK_DB_URL
    if "vergeo5_rls_test" in primary or primary == fallback:
        ensure_local_test_database(primary if "vergeo5_rls_test" in primary else fallback)
    if _db_reachable(primary):
        return primary
    target = fallback if primary != fallback else primary
    if primary != fallback:
        ensure_local_test_database(fallback)
    if _db_reachable(target):
        return target
    return primary


# The roles this harness impersonates. Kept SEPARATE from the schema bootstrap
# below, and applied unconditionally, because of the defect described on the
# `db` fixture: when the database already carries a schema (CI runs
# `supabase db reset` first), the schema bootstrap is skipped — and if the role
# creation rides along with it, `vergeo_rls_tester` never exists.
#
# When that role is missing, `SET LOCAL ROLE vergeo_rls_tester` errors, the
# session stays `postgres` — superuser, BYPASSRLS — and every "expected deny"
# assertion sees the query SUCCEED. The suite then reports over a thousand
# failures rather than silently passing, which is the one mercy in it, but the
# effect is that RLS was not actually being exercised.
#
# Idempotent by construction: safe to run against a bare Postgres, a
# half-built database, or a fully migrated Supabase stack.
# Existence is checked BEFORE each CREATE, and that ordering is load-bearing.
#
# On a Supabase stack the connecting `postgres` role is NOT a superuser, and
# Postgres checks privileges before it checks for a duplicate name: a plain
# `CREATE ROLE service_role ... BYPASSRLS` therefore fails with `must be
# superuser to create bypassrls users` even though service_role already
# exists — a permission error, which a `duplicate_object` handler does not
# catch (observed: CI run 30736608352, 2314 errors). Checking pg_roles first
# means the CREATE simply never runs where the role pre-exists, which is
# every Supabase environment; the duplicate_object guard stays only for the
# race where two sessions bootstrap a bare Postgres at once.
ROLE_BOOTSTRAP_SQL = """
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    CREATE ROLE anon NOLOGIN;
  END IF;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    CREATE ROLE authenticated NOLOGIN;
  END IF;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    CREATE ROLE service_role NOLOGIN BYPASSRLS;
  END IF;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'vergeo_rls_tester') THEN
    CREATE ROLE vergeo_rls_tester LOGIN PASSWORD 'test' NOSUPERUSER NOBYPASSRLS;
  END IF;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- NOSUPERUSER NOBYPASSRLS above is the whole point: the tester must be subject
-- to policy. If this role is ever created with BYPASSRLS, every deny assertion
-- in the matrix silently becomes a no-op.
GRANT authenticated TO vergeo_rls_tester;
GRANT anon TO vergeo_rls_tester;
GRANT vergeo_rls_tester TO CURRENT_USER;
"""

AUTH_BOOTSTRAP_SQL = """
CREATE SCHEMA IF NOT EXISTS auth;
CREATE SCHEMA IF NOT EXISTS extensions;

GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
GRANT USAGE ON SCHEMA auth TO postgres, anon, authenticated, service_role;

CREATE TABLE IF NOT EXISTS auth.users (
  instance_id uuid,
  id uuid PRIMARY KEY,
  aud text,
  role text,
  email text,
  encrypted_password text,
  email_confirmed_at timestamptz,
  raw_app_meta_data jsonb,
  raw_user_meta_data jsonb,
  created_at timestamptz,
  updated_at timestamptz
);

CREATE OR REPLACE FUNCTION auth.uid()
RETURNS uuid
LANGUAGE sql
STABLE
AS $$
  SELECT COALESCE(
    NULLIF(current_setting('request.jwt.claim.sub', true), ''),
    NULLIF(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub'
  )::uuid;
$$;

CREATE OR REPLACE FUNCTION auth.jwt()
RETURNS jsonb
LANGUAGE sql
STABLE
AS $$
  SELECT COALESCE(NULLIF(current_setting('request.jwt.claims', true), '')::jsonb, '{}'::jsonb);
$$;

GRANT USAGE ON SCHEMA auth TO anon, authenticated, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON auth.users TO postgres, service_role;
"""


def ensure_local_test_database(url: str) -> None:
    if "vergeo5_rls_test" not in url:
        return
    admin = PgConn("postgresql:///postgres")
    exists = admin.run("SELECT 1 FROM pg_database WHERE datname = 'vergeo5_rls_test'")
    if exists.ok and exists.rows and exists.rows[0] == "1":
        return
    admin.run("CREATE DATABASE vergeo5_rls_test")


def ensure_roles(conn: PgConn) -> None:
    """Create the impersonation roles. Must run on EVERY session, migrated or not."""
    result = conn.run(ROLE_BOOTSTRAP_SQL)
    if not result.ok:
        raise PgError(f"Role bootstrap failed: {result.error}", result.sqlstate)


def grant_tester_access(conn: PgConn) -> None:
    """Grants the tester needs that only exist once the schema does."""
    conn.run("GRANT USAGE ON SCHEMA auth TO vergeo_rls_tester")
    conn.run("GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO vergeo_rls_tester")


def assert_tester_is_rls_bound(conn: PgConn) -> None:
    """Refuse to run the matrix against a tester that cannot be denied.

    A superuser or BYPASSRLS tester turns every 'expected deny' cell into a
    guaranteed pass. That is a false green on the only mechanism separating
    tenants in this product, so it fails loudly instead.
    """
    result = conn.run(
        "SELECT rolsuper::text || ',' || rolbypassrls::text "
        "FROM pg_roles WHERE rolname = 'vergeo_rls_tester'"
    )
    if not result.ok or not result.rows:
        raise PgError(f"vergeo_rls_tester missing after bootstrap: {result.error}")
    if result.rows[0] != "false,false":
        raise PgError(
            "vergeo_rls_tester has SUPERUSER or BYPASSRLS "
            f"(rolsuper,rolbypassrls = {result.rows[0]}) — every deny assertion "
            "in the matrix would pass without testing anything"
        )

    # Membership matters as much as the attributes: the harness impersonates
    # via `SET LOCAL ROLE vergeo_rls_tester; SET LOCAL role anon|authenticated`,
    # which requires membership in both. If the GRANTs failed (on PG16+ a
    # CREATEROLE user needs ADMIN OPTION on a role to grant it), fail here with
    # ONE targeted message instead of thousands of impersonation errors.
    membership = conn.run(
        "SELECT count(*) FROM pg_auth_members m "
        "JOIN pg_roles granted ON granted.oid = m.roleid "
        "JOIN pg_roles member ON member.oid = m.member "
        "WHERE member.rolname = 'vergeo_rls_tester' "
        "AND granted.rolname IN ('anon', 'authenticated')"
    )
    if not membership.ok or not membership.rows or int(membership.rows[0]) != 2:
        got = membership.rows[0] if membership.ok and membership.rows else membership.error
        raise PgError(
            "vergeo_rls_tester is not a member of both anon and authenticated "
            f"(memberships found: {got}). The GRANTs in ROLE_BOOTSTRAP_SQL failed — "
            "on PG16+ the connecting role needs ADMIN OPTION on anon/authenticated "
            "to grant them. Without membership, SET LOCAL ROLE cannot impersonate "
            "and no policy is actually exercised."
        )


def apply_migrations(conn: PgConn) -> None:
    # Roles FIRST, and inside this function rather than only at its call sites.
    #
    # `apply_migrations` is a public entry point with 35+ direct callers across
    # tests/ — most of them module-scoped `db` fixtures that never touch the
    # `db` fixture in this file. When the role creation was split out of
    # AUTH_BOOTSTRAP_SQL, those callers started failing on
    # `GRANT USAGE ON SCHEMA public TO anon` with `role "anon" does not exist`,
    # because AUTH_BOOTSTRAP_SQL grants to roles it no longer creates.
    #
    # Keeping this call here preserves the original contract exactly — roles
    # were previously created by AUTH_BOOTSTRAP_SQL's opening statements — while
    # the `db` fixture additionally calls ensure_roles on the path where
    # apply_migrations is skipped.
    ensure_roles(conn)
    bootstrap = conn.run(AUTH_BOOTSTRAP_SQL)
    if not bootstrap.ok:
        raise PgError(f"Auth bootstrap failed: {bootstrap.error}", bootstrap.sqlstate)
    for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
        result = conn.run_file(migration)
        if not result.ok:
            raise PgError(f"Migration {migration.name} failed: {result.error}", result.sqlstate)
    # Tester grants now live in `grant_tester_access`, called by the `db` fixture
    # on every path — not just this one. Kept here too so a direct caller of
    # apply_migrations still ends up with a usable tester.
    grant_tester_access(conn)


def load_fixture_ids() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES_DIR / "ids.json").read_text()))


def load_fixture_entities() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES_DIR / "entities.json").read_text()))


# ruff: noqa: E501
def seed_matrix_fixtures(conn: PgConn) -> None:
    """Idempotent seed for RLS matrix + demo browsing."""
    ids = load_fixture_ids()
    entities = load_fixture_entities()

    users = ids["users"]

    # auth.users is owned by supabase_auth_admin; seed as postgres before SET ROLE.
    auth_parts = ["BEGIN;"]
    for key, uid in users.items():
        email = f"{key}@rls-matrix.test"
        auth_parts.append(
            f"""
INSERT INTO auth.users (
  instance_id, id, aud, role, email, encrypted_password,
  email_confirmed_at, raw_app_meta_data, raw_user_meta_data, created_at, updated_at
) VALUES (
  '00000000-0000-0000-0000-000000000000', '{uid}', 'authenticated', 'authenticated',
  '{email}', 'hash', timezone('utc', now()), '{{}}'::jsonb, '{{}}'::jsonb,
  timezone('utc', now()), timezone('utc', now())
) ON CONFLICT (id) DO NOTHING;
"""
        )
    auth_parts.append("COMMIT;")
    auth_result = conn.run("\n".join(auth_parts))
    if not auth_result.ok:
        raise PgError(f"auth.users seed failed: {auth_result.error}", auth_result.sqlstate)

    sql_parts = [
        "BEGIN;",
        "SET LOCAL role service_role;",
        'SET LOCAL "request.jwt.claims" = \'{"role":"service_role"}\';',
    ]

    profiles = [
        (users["customer_a"], "+260971000001", "Customer A"),
        (users["customer_b"], "+260971000002", "Customer B"),
        (users["vendor_a_owner"], "+260971000003", "Vendor A Owner"),
        (users["vendor_b_owner"], "+260971000004", "Vendor B Owner"),
        (users["admin"], "+260971000005", "Admin User"),
    ]
    for uid, phone, name in profiles:
        # The 0010 on_auth_user_created trigger inserts a bare profile row
        # (id only) the moment we seed auth.users above, so ON CONFLICT DO
        # NOTHING would silently drop the seed phone/display_name. DO UPDATE so
        # the intended values actually land for tests that read profiles.phone.
        sql_parts.append(
            f"INSERT INTO public.profiles (id, phone, display_name) "
            f"VALUES ('{uid}', '{phone}', '{name}') "
            f"ON CONFLICT (id) DO UPDATE SET "
            f"phone = EXCLUDED.phone, display_name = EXCLUDED.display_name;"
        )

    roles = [
        (users["customer_a"], "customer"),
        (users["customer_a"], "vendor"),
        (users["customer_b"], "customer"),
        (users["vendor_a_owner"], "vendor"),
        (users["vendor_b_owner"], "vendor"),
        (users["admin"], "admin"),
    ]
    for uid, role in roles:
        sql_parts.append(
            f"INSERT INTO public.user_roles (user_id, role) "
            f"VALUES ('{uid}', '{role}') ON CONFLICT (user_id, role) DO NOTHING;"
        )

    for vendor in entities["vendors"]:
        vid = ids["vendors"][vendor["id_key"]]
        owner = users[vendor["owner_key"]]
        caps = json.dumps(vendor["caps_snapshot"]).replace("'", "''")
        sql_parts.append(
            f"""
INSERT INTO public.vendors (
  id, owner_user_id, slug, display_name, description, status, kyc_tier, caps_snapshot
) VALUES (
  '{vid}', '{owner}', '{vendor["slug"]}', '{vendor["display_name"]}',
  '{vendor["description"]}', '{vendor["status"]}', {vendor["kyc_tier"]}, '{caps}'::jsonb
) ON CONFLICT (id) DO NOTHING;
"""
        )

    for loc in entities["vendor_locations"]:
        vendor_id = ids["vendors"][loc["vendor_key"]]
        sql_parts.append(
            f"""
INSERT INTO public.vendor_locations (id, vendor_id, lat, lng, landmark)
VALUES ('{loc["id"]}', '{vendor_id}', {loc["lat"]}, {loc["lng"]}, '{loc["landmark"]}')
ON CONFLICT (id) DO NOTHING;
"""
        )

    for cat in entities["categories"]:
        cid = ids["categories"][cat["id_key"]]
        sql_parts.append(
            f"""
INSERT INTO public.categories (id, name, slug, path, commission_key)
VALUES ('{cid}', '{cat["name"]}', '{cat["slug"]}', '{cat["path"]}', '{cat["commission_key"]}')
ON CONFLICT (id) DO NOTHING;
"""
        )

    for product in entities["products"]:
        pid = ids["products"][product["id_key"]]
        cid = ids["categories"][product["category_key"]]
        aliases = "{" + ",".join(f'"{a}"' for a in product["aliases"]) + "}"
        sql_parts.append(
            f"""
INSERT INTO public.products (id, name, slug, category_id, status, aliases)
VALUES ('{pid}', '{product["name"]}', '{product["slug"]}', '{cid}', '{product["status"]}', '{aliases}')
ON CONFLICT (id) DO NOTHING;
"""
        )

    for listing in entities["listings"]:
        lid = ids["listings"][listing["id_key"]]
        vendor_id = ids["vendors"][listing["vendor_key"]]
        product_id = ids["products"][listing["product_key"]]
        sql_parts.append(
            f"""
INSERT INTO public.vendor_listings (
  id, vendor_id, product_id, title_override, price_ngwee, condition,
  stock_mode, stock_qty, status
) VALUES (
  '{lid}', '{vendor_id}', '{product_id}', '{listing["title_override"]}',
  {listing["price_ngwee"]}, '{listing["condition"]}', '{listing["stock_mode"]}',
  {listing["stock_qty"]}, '{listing["status"]}'
) ON CONFLICT (id) DO NOTHING;
"""
        )

    for image in entities["listing_images"]:
        listing_id = ids["listings"][image["listing_key"]]
        sql_parts.append(
            f"""
INSERT INTO public.listing_images (id, listing_id, cloudinary_public_id, position)
VALUES ('{image["id"]}', '{listing_id}', '{image["cloudinary_public_id"]}', {image["position"]})
ON CONFLICT (id) DO NOTHING;
"""
        )

    for service in entities["services"]:
        sid = ids["services"][service["id_key"]]
        vendor_id = ids["vendors"][service["vendor_key"]]
        portfolio_images = service.get("portfolio_images") or []
        portfolio_sql = ", ".join(f"'{image}'" for image in portfolio_images)
        sql_parts.append(
            f"""
INSERT INTO public.services (
  id, vendor_id, category, title, description, service_area, from_price_ngwee,
  portfolio_images, status
) VALUES (
  '{sid}', '{vendor_id}', '{service["category"]}', '{service["title"]}',
  '{service["description"]}', '{service["service_area"]}', {service["from_price_ngwee"]},
  ARRAY[{portfolio_sql}]::text[], '{service["status"]}'
) ON CONFLICT (id) DO NOTHING;
"""
        )

    for event in entities["events"]:
        eid = ids["events"][event["id_key"]]
        organiser = ids["vendors"][event["organiser_key"]]
        event_images = event.get("images") or []
        images_sql = ", ".join(f"'{image}'" for image in event_images)
        sql_parts.append(
            f"""
INSERT INTO public.events (
  id, organiser_vendor_id, title, slug, venue, lat, lng, images, status
) VALUES (
  '{eid}', '{organiser}', '{event["title"]}', '{event["slug"]}', '{event["venue"]}',
  {event["lat"]}, {event["lng"]}, ARRAY[{images_sql}]::text[], '{event["status"]}'
) ON CONFLICT (id) DO NOTHING;
"""
        )

    for inst in entities["event_instances"]:
        iid = ids["event_instances"][inst["id_key"]]
        event_id = ids["events"][inst["event_key"]]
        sql_parts.append(
            f"""
INSERT INTO public.event_instances (id, event_id, starts_at, capacity)
VALUES ('{iid}', '{event_id}', '{inst["starts_at"]}', {inst["capacity"]})
ON CONFLICT (id) DO NOTHING;
"""
        )

    for tt in entities["ticket_types"]:
        tid = ids["ticket_types"][tt["id_key"]]
        event_id = ids["events"][tt["event_key"]]
        sql_parts.append(
            f"""
INSERT INTO public.ticket_types (id, event_id, kind, name, price_ngwee, qty_cap)
VALUES ('{tid}', '{event_id}', '{tt["kind"]}', '{tt["name"]}', {tt["price_ngwee"]}, {tt["qty_cap"]})
ON CONFLICT (id) DO NOTHING;
"""
        )

    for job in entities["jobs"]:
        jid = ids["jobs"][job["id_key"]]
        customer_id = users[job["customer_key"]]
        sql_parts.append(
            f"""
INSERT INTO public.jobs (
  id, customer_id, category, description, budget_band_min_ngwee, budget_band_max_ngwee, status
) VALUES (
  '{jid}', '{customer_id}', '{job["category"]}', '{job["description"]}',
  {job["budget_band_min_ngwee"]}, {job["budget_band_max_ngwee"]}, '{job["status"]}'
) ON CONFLICT (id) DO NOTHING;
"""
        )

    for quote in entities["job_quotes"]:
        qid = ids["job_quotes"][quote["id_key"]]
        job_id = ids["jobs"][quote["job_key"]]
        provider_id = ids["vendors"][quote["provider_key"]]
        sql_parts.append(
            f"""
INSERT INTO public.job_quotes (id, job_id, provider_vendor_id, amount_ngwee, message, status)
VALUES ('{qid}', '{job_id}', '{provider_id}', {quote["amount_ngwee"]},
        '{quote["message"]}', '{quote["status"]}')
ON CONFLICT (id) DO NOTHING;
"""
        )

    address_id = ids["addresses"]["customer_a_home"]
    customer_a = users["customer_a"]
    sql_parts.append(
        f"""
INSERT INTO public.addresses (id, user_id, label, landmark, lat, lng, phone)
VALUES ('{address_id}', '{customer_a}', 'Home', 'Woodlands Stage 2', -15.4167, 28.2833, '+260971000001')
ON CONFLICT (id) DO NOTHING;
"""
    )

    checkout_groups = [
        (
            ids["checkout_groups"]["paid"],
            users["customer_a"],
            "seed-paid-cg",
            535000,
            15000,
            550000,
            "completed",
        ),
        (
            ids["checkout_groups"]["pending"],
            users["customer_a"],
            "seed-pending-cg",
            450000,
            15000,
            465000,
            "pending",
        ),
    ]
    for cg_id, cust, key, sub, fee, total, status in checkout_groups:
        sql_parts.append(
            f"""
INSERT INTO public.checkout_groups (
  id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee, total_ngwee, status
) VALUES ('{cg_id}', '{cust}', '{key}', {sub}, {fee}, {total}, '{status}')
ON CONFLICT (id) DO NOTHING;
"""
        )

    for order in entities["orders"]:
        oid = ids["orders"][order["id_key"]]
        cg_id = ids["checkout_groups"][order["checkout_group_key"]]
        vendor_id = ids["vendors"][order["vendor_key"]]
        customer_id = users[order["customer_key"]]
        zone = "NULL" if order["delivery_zone"] is None else f"'{order['delivery_zone']}'"
        sql_parts.append(
            f"""
INSERT INTO public.orders (
  id, checkout_group_id, vendor_id, customer_id, status, fulfilment, delivery_zone, address_id
) VALUES (
  '{oid}', '{cg_id}', '{vendor_id}', '{customer_id}', '{order["status"]}',
  '{order["fulfilment"]}', {zone}, '{address_id}'
) ON CONFLICT (id) DO NOTHING;
"""
        )

    order_items = [
        (ids["order_items"]["paid"], ids["orders"]["paid"], "product", 1, 450000),
        (ids["order_items"]["delivered"], ids["orders"]["delivered"], "product", 1, 85000),
    ]
    for oi_id, order_id, kind, qty, price in order_items:
        sql_parts.append(
            f"""
INSERT INTO public.order_items (id, order_id, item_kind, qty, unit_price_ngwee)
VALUES ('{oi_id}', '{order_id}', '{kind}', {qty}, {price})
ON CONFLICT (id) DO NOTHING;
"""
        )

    sql_parts.append(
        f"""
INSERT INTO public.order_item_products (order_item_id, listing_id, product_id)
VALUES ('{ids["order_items"]["paid"]}', '{ids["listings"]["phone_a"]}', '{ids["products"]["phone"]}')
ON CONFLICT (order_item_id) DO NOTHING;
"""
    )
    sql_parts.append(
        f"""
INSERT INTO public.order_item_products (order_item_id, listing_id, product_id)
VALUES ('{ids["order_items"]["delivered"]}', '{ids["listings"]["chitenge_b"]}', '{ids["products"]["chitenge"]}')
ON CONFLICT (order_item_id) DO NOTHING;
"""
    )

    pay_id = ids["payments"]["paid"]
    sql_parts.append(
        f"""
INSERT INTO public.payments (
  id, checkout_group_id, provider, rail, lenco_reference, amount_ngwee, status
) VALUES (
  '{pay_id}', '{ids["checkout_groups"]["paid"]}', 'lenco', 'mtn', 'pay-seed-001', 550000, 'success'
) ON CONFLICT (id) DO NOTHING;
"""
    )

    payout_id = ids["payouts"]["vendor_a"]
    sql_parts.append(
        f"""
INSERT INTO public.payouts (
  id, vendor_id, amount_ngwee, rail, lenco_reference, status
) VALUES (
  '{payout_id}', '{ids["vendors"]["shop_a"]}', 400000, 'mtn', 'po-seed-001', 'paid'
) ON CONFLICT (id) DO NOTHING;
"""
    )

    inv_id = ids["invoices"]["paid"]
    sql_parts.append(
        f"""
INSERT INTO public.invoices (id, series, no, order_id, snapshot)
VALUES ('{inv_id}', 'STD', 9001, '{ids["orders"]["paid"]}', '{{"total_ngwee": 450000}}'::jsonb)
ON CONFLICT (id) DO NOTHING;
"""
    )

    sql_parts.append("COMMIT;")
    result = conn.run("\n".join(sql_parts))
    if not result.ok:
        raise PgError(f"Matrix seed failed: {result.error}", result.sqlstate)


@dataclass
class RoleSession:
    conn: PgConn
    persona: Persona

    def _role_preamble(self) -> str:
        if self.persona == Persona.ANON:
            return (
                "SET LOCAL ROLE vergeo_rls_tester; "
                "SET LOCAL role anon; "
                "DO $$ BEGIN PERFORM set_config('request.jwt.claims', '', true); END $$;"
            )
        uid = PERSONA_UIDS[self.persona]
        assert uid is not None
        claims = json.dumps({"sub": uid, "role": "authenticated", "aal": "aal1"})
        escaped = claims.replace("'", "''")
        return (
            "SET LOCAL ROLE vergeo_rls_tester; "
            "SET LOCAL role authenticated; "
            f"DO $$ BEGIN PERFORM set_config('request.jwt.claims', '{escaped}', true); END $$;"
        )

    def execute(self, sql: str) -> SqlResult:
        script = f"BEGIN; {self._role_preamble().replace(chr(10), ' ')} {sql}; COMMIT;"
        return self.conn.run(script)


@pytest.fixture(scope="session")
def db_url() -> str:
    url = resolve_db_url()
    ensure_local_test_database(url)
    return url


def schema_ready(conn: PgConn) -> bool:
    result = conn.run(
        """
        SELECT count(*)::int
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        """
    )
    return result.ok and bool(result.rows) and int(result.rows[0]) >= 45


@pytest.fixture(scope="session")
def db(db_url: str) -> Generator[PgConn, None, None]:
    """Session database, with the impersonation roles guaranteed to exist.

    `ensure_roles` runs OUTSIDE the `schema_ready` branch, and that placement is
    the fix for a defect that made this entire suite decorative in CI.

    CI runs `supabase db start` + `supabase db reset` before pytest, so the
    database arrives fully migrated and `schema_ready` is True. The branch below
    was therefore skipped — and it used to be the only caller of the bootstrap
    that creates `vergeo_rls_tester`. No role meant `SET LOCAL ROLE` failed,
    sessions stayed `postgres` (superuser, BYPASSRLS), and the CI job logged
    1125 failed / 1070 passed on master while reporting GREEN, because the step
    carried `continue-on-error: true`.

    Only the bare-Postgres path needs the schema built; every path needs roles.
    """
    conn = PgConn(db_url)
    if not _db_reachable(db_url):
        pytest.skip(f"Postgres not reachable at {db_url}")
    ensure_roles(conn)
    if not schema_ready(conn):
        conn.run("DROP SCHEMA IF EXISTS public CASCADE")
        conn.run("CREATE SCHEMA public")
        conn.run("DROP SCHEMA IF EXISTS auth CASCADE")
        # Re-create the roles: dropping and rebuilding the schemas above does not
        # drop roles, but apply_migrations' grants need them present, and this
        # keeps the ordering obvious to the next reader.
        ensure_roles(conn)
        apply_migrations(conn)
    grant_tester_access(conn)
    assert_tester_is_rls_bound(conn)
    seed_matrix_fixtures(conn)
    yield conn


@pytest.fixture
def role_factory(db: PgConn) -> Callable[[Persona], RoleSession]:
    def _make(persona: Persona) -> RoleSession:
        return RoleSession(db, persona)

    return _make


@pytest.fixture
def as_anon(role_factory: Callable[[Persona], RoleSession]) -> RoleSession:
    return role_factory(Persona.ANON)


@pytest.fixture
def as_customer(role_factory: Callable[[Persona], RoleSession]) -> RoleSession:
    return role_factory(Persona.CUSTOMER)


@pytest.fixture
def as_other_customer(role_factory: Callable[[Persona], RoleSession]) -> RoleSession:
    return role_factory(Persona.OTHER_CUSTOMER)


@pytest.fixture
def as_vendor(role_factory: Callable[[Persona], RoleSession]) -> RoleSession:
    return role_factory(Persona.VENDOR)


@pytest.fixture
def as_other_vendor(role_factory: Callable[[Persona], RoleSession]) -> RoleSession:
    return role_factory(Persona.OTHER_VENDOR)


@pytest.fixture
def as_admin(role_factory: Callable[[Persona], RoleSession]) -> RoleSession:
    return role_factory(Persona.ADMIN)


@pytest.fixture
def fixture_ids() -> dict[str, Any]:
    return load_fixture_ids()
