"""Regression coverage for STG-SEED-04 synthetic marketplace contract."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import uuid
from collections.abc import Generator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from app.core.env_guards import (
    PROD_SUPABASE_PROJECT_REF,
    STAGING_SUPABASE_PROJECT_REF,
    StagingIsolationError,
    assert_staging_project_target,
)
from app.staging.seed_sql import (
    IMAGE_IDS,
    build_cleanup_sql,
    build_seed_sql,
    parse_verification,
    verification_queries,
)
from app.staging.synthetic_contract import (
    CATALOG_FIXTURES,
    PERSONAS,
    SEED_PREFIX,
    VENDOR_LOCATIONS,
    all_contract_uuid_literals,
    assert_contract_valid,
    guard_seed_targets,
    persona_by_key,
    product_fixture,
)
from app.staging.transactional import (
    TransactionalState,
    classify_state,
    is_service_drivable,
    plan_state,
)
from tests.rls.conftest import PgConn, apply_migrations, resolve_db_url

MIGRATION_SHIM_SQL = """
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'supabase_admin') THEN
    CREATE ROLE supabase_admin LOGIN SUPERUSER;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'supabase_auth_admin') THEN
    CREATE ROLE supabase_auth_admin NOLOGIN NOINHERIT;
  END IF;
END $$;
"""


@pytest.fixture
def seed_module() -> Any:
    script = Path(__file__).resolve().parents[3] / "scripts/seed_staging.py"
    spec = importlib.util.spec_from_file_location("seed_staging_test", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    try:
        yield module
    finally:
        sys.modules.pop(spec.name, None)


def test_contract_personas_are_deterministic() -> None:
    assert persona_by_key("CUSTOMER_A").user_id == "a1000000-0000-4000-8000-000000000001"
    assert persona_by_key("CUSTOMER_B").user_id == "a1000000-0000-4000-8000-000000000007"
    assert persona_by_key("APPROVED_VENDOR_A").vendor_id == (
        "b1000000-0000-4000-8000-000000000004"
    )
    assert persona_by_key("APPROVED_VENDOR_B").vendor_id == (
        "b1000000-0000-4000-8000-000000000005"
    )
    assert persona_by_key("PENDING_VENDOR").vendor_status == "pending_kyc"
    assert persona_by_key("BUSINESS_BUYER").business_buyer_id is not None


def test_product_a_is_multiseller_with_two_listings() -> None:
    product = product_fixture("PRODUCT_A")
    assert len(product.listings) >= 2
    vendors = {listing.vendor_key for listing in product.listings}
    assert vendors == {"APPROVED_VENDOR_A", "APPROVED_VENDOR_B"}


def test_product_c_is_out_of_stock() -> None:
    listing = product_fixture("PRODUCT_C").listings[0]
    assert listing.stock_qty == 0
    assert listing.location_stock_qty == 0


def test_product_d_is_wholesale_only() -> None:
    listing = product_fixture("PRODUCT_D").listings[0]
    assert listing.wholesale is True
    assert listing.moq >= 2


def test_contract_rejects_zero_price() -> None:
    product = product_fixture("PRODUCT_B")
    bad_listing = replace(product.listings[0], price_ngwee=0)
    bad_product = replace(product, listings=(bad_listing,))
    original = CATALOG_FIXTURES
    try:
        import app.staging.synthetic_contract as contract

        contract.CATALOG_FIXTURES = (bad_product,)
        with pytest.raises(StagingIsolationError, match="positive integer"):
            assert_contract_valid()
    finally:
        import app.staging.synthetic_contract as contract

        contract.CATALOG_FIXTURES = original


def test_guard_rejects_production_project_ref() -> None:
    with pytest.raises(StagingIsolationError, match="production"):
        guard_seed_targets(
            supabase_url="",
            db_url="",
            api_host="",
            staging_project_id=PROD_SUPABASE_PROJECT_REF,
            require_exact_project=True,
        )


def test_guard_rejects_wrong_staging_project_ref() -> None:
    with pytest.raises(StagingIsolationError, match="refusing non-staging"):
        assert_staging_project_target("abcdefghij1234567890", require_exact=True)


def test_guard_accepts_canonical_staging_ref() -> None:
    assert_staging_project_target(STAGING_SUPABASE_PROJECT_REF, require_exact=True)


def test_seed_sql_includes_multiseller_location_stock_and_business_buyer() -> None:
    assert_contract_valid()
    sql = build_seed_sql()
    product_a = product_fixture("PRODUCT_A")
    assert "INSERT INTO public.business_buyers" in sql
    assert "INSERT INTO public.vendor_locations" in sql
    assert "INSERT INTO public.listing_location_stock" in sql
    assert product_a.listings[0].sku in sql
    assert product_a.listings[1].sku in sql
    assert "staging-synthetic/" in sql
    assert "INSERT INTO public.orders" not in sql
    assert "INSERT INTO public.payments" not in sql


def test_cleanup_sql_scoped_to_prefix_and_known_ids() -> None:
    sql = build_cleanup_sql()
    assert f"LIKE '{SEED_PREFIX}-txn-%'" in sql
    assert f"sku LIKE '{SEED_PREFIX}%'" in sql
    assert persona_by_key("CUSTOMER_A").user_id in sql
    assert "DELETE FROM public.profiles" in sql


def test_verification_queries_cover_multiseller_oos_wholesale() -> None:
    queries = verification_queries()
    assert "multiseller_count" in queries
    assert "oos_stock" in queries
    assert "wholesale_product_d" in queries
    assert "zero_price_guard" in queries


def test_transactional_external_states_are_not_service_drivable() -> None:
    assert is_service_drivable(TransactionalState.COD_PLACED) is True
    assert is_service_drivable(TransactionalState.DELIVERED) is False
    assert classify_state("dispute_held").delivery == "external"


def test_transactional_plan_uses_customer_a_and_product_b() -> None:
    plan = plan_state(TransactionalState.PREPAID_AWAITING_PAYMENT)
    assert plan["customer_user_id"] == persona_by_key("CUSTOMER_A").user_id
    assert plan["listing_id"] == product_fixture("PRODUCT_B").listings[0].listing_id


def test_staging_seed_uses_psql_without_importing_test_harness(
    monkeypatch: pytest.MonkeyPatch,
    seed_module: Any,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="1\n", stderr="")

    monkeypatch.setattr(seed_module.subprocess, "run", fake_run)

    result = seed_module.StagingPgConn("postgresql://staging.example/test").run("SELECT 1")

    assert result.ok
    assert result.rows == ["1"]
    assert captured["args"][0][0] == "psql"


def test_staging_seed_redacts_dsn_from_psql_errors(
    monkeypatch: pytest.MonkeyPatch,
    seed_module: Any,
) -> None:
    dsn = "postgresql://seed_user:super-secret@staging.example/test"

    def fake_run(*args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=args,
            returncode=2,
            stdout="",
            stderr=f"psql: error: connection failed for {dsn}",
        )

    monkeypatch.setattr(seed_module.subprocess, "run", fake_run)

    result = seed_module.StagingPgConn(dsn).run("SELECT 1")

    assert not result.ok
    assert result.error == "psql: error: connection failed for <redacted>"
    assert "super-secret" not in result.error


def test_staging_seed_requires_migrated_vendor_schema(seed_module: Any) -> None:
    class MissingVendors:
        def run(self, _sql: str) -> Any:
            return seed_module.SqlResult(ok=True, rows=[""])

    with pytest.raises(RuntimeError, match="missing public.vendors"):
        seed_module._require_seed_schema(MissingVendors())


def test_staging_seed_rejects_vendor_lifecycle_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.staging.synthetic_contract as contract

    bad = replace(persona_by_key("VENDOR_UNVERIFIED"), vendor_status="pending", kyc_tier=0)
    original = contract.PERSONAS
    try:
        contract.PERSONAS = tuple(
            bad if p.key == "VENDOR_UNVERIFIED" else p for p in PERSONAS
        )
        with pytest.raises(StagingIsolationError, match="invalid synthetic vendor status"):
            assert_contract_valid()
    finally:
        contract.PERSONAS = original


def test_contract_uuid_literals_are_postgres_compatible() -> None:
    assert_contract_valid()
    for value in all_contract_uuid_literals():
        parsed = uuid.UUID(value)
        assert str(parsed) == value


def test_contract_rejects_invalid_uuid_prefix() -> None:
    import app.staging.synthetic_contract as contract

    bad = replace(
        persona_by_key("BUSINESS_BUYER"),
        business_buyer_id="h1000000-0000-4000-8000-000000000001",
    )
    original = contract.PERSONAS
    try:
        contract.PERSONAS = tuple(
            bad if p.key == "BUSINESS_BUYER" else p for p in PERSONAS
        )
        with pytest.raises(StagingIsolationError, match="Postgres-compatible"):
            assert_contract_valid()
    finally:
        contract.PERSONAS = original


@pytest.fixture(scope="module")
def migrated_db() -> Generator[PgConn, None, None]:
    url = resolve_db_url()
    conn = PgConn(url)
    if not conn.run("SELECT 1").ok:
        pytest.skip(f"Postgres not reachable at {url}")
    conn.run("DROP SCHEMA IF EXISTS public CASCADE")
    conn.run("CREATE SCHEMA public")
    conn.run("DROP SCHEMA IF EXISTS auth CASCADE")
    shim = conn.run(MIGRATION_SHIM_SQL)
    if not shim.ok:
        pytest.skip(f"migration shim unavailable: {shim.error}")
    try:
        apply_migrations(conn)
    except Exception as exc:  # noqa: BLE001 — skip when extensions/migrations unavailable
        pytest.skip(f"migrations unavailable: {exc}")
    conn.run("ALTER TABLE auth.users ADD COLUMN IF NOT EXISTS phone text")
    conn.run(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_auth_members m "
        "JOIN pg_roles r ON r.oid = m.roleid "
        "JOIN pg_roles u ON u.oid = m.member "
        "WHERE r.rolname = 'service_role' AND u.rolname = current_user) THEN "
        "EXECUTE 'GRANT service_role TO ' || quote_ident(current_user); "
        "END IF; END $$;"
    )
    yield conn


def _run_verification(conn: PgConn) -> None:
    results: dict[str, list[str]] = {}
    for key, sql in verification_queries().items():
        result = conn.run(sql)
        assert result.ok, result.error or f"verification query failed: {key}"
        results[key] = result.rows
    parse_verification(results)


def _assert_contract_proof(conn: PgConn) -> None:
    product_a = product_fixture("PRODUCT_A")
    listing_a_ids = ", ".join(f"'{listing.listing_id}'" for listing in product_a.listings)
    prices = conn.run(
        "SELECT price_ngwee::text FROM public.vendor_listings "
        f"WHERE id IN ({listing_a_ids}) ORDER BY price_ngwee"
    )
    assert prices.ok and prices.rows == ["12500", "14900"]

    product_b_price = conn.run(
        "SELECT price_ngwee::text FROM public.vendor_listings "
        f"WHERE id = '{product_fixture('PRODUCT_B').listings[0].listing_id}'"
    )
    assert product_b_price.ok and product_b_price.rows == ["8750"]

    product_c_stock = conn.run(
        "SELECT stock_qty::text FROM public.vendor_listings "
        f"WHERE id = '{product_fixture('PRODUCT_C').listings[0].listing_id}'"
    )
    assert product_c_stock.ok and product_c_stock.rows == ["0"]

    product_d = conn.run(
        "SELECT wholesale::text || ',' || moq::text FROM public.vendor_listings "
        f"WHERE id = '{product_fixture('PRODUCT_D').listings[0].listing_id}'"
    )
    assert product_d.ok and product_d.rows == ["true,10"]

    locations = conn.run("SELECT count(*)::text FROM public.vendor_locations")
    assert locations.ok and locations.rows == ["2"]

    location_stock = conn.run(
        "SELECT count(*)::text FROM public.listing_location_stock "
        f"WHERE listing_id IN ({listing_a_ids}) "
        "OR listing_id IN ("
        + ", ".join(
            f"'{listing.listing_id}'"
            for product in CATALOG_FIXTURES
            for listing in product.listings
        )
        + ")"
    )
    assert location_stock.ok and location_stock.rows == ["5"]

    business_buyer = persona_by_key("BUSINESS_BUYER")
    buyer = conn.run(
        "SELECT status FROM public.business_buyers "
        f"WHERE id = '{business_buyer.business_buyer_id}'"
    )
    assert buyer.ok and buyer.rows == ["verified"]

    zero_price = conn.run(
        "SELECT count(*)::text FROM public.vendor_listings "
        f"WHERE sku LIKE '{SEED_PREFIX}%' AND price_ngwee < 1"
    )
    assert zero_price.ok and zero_price.rows == ["0"]

    for table in ("orders", "payments", "ledger_transactions"):
        count = conn.run(f"SELECT count(*)::text FROM public.{table}")
        assert count.ok and count.rows == ["0"], (
            f"static seed must not create {table} rows"
        )


def test_seed_sql_executes_idempotently_and_cleans_up(migrated_db: PgConn) -> None:
    assert_contract_valid()
    seed_sql = build_seed_sql()

    first = migrated_db.run_script(seed_sql)
    assert first.ok, first.error or "initial seed failed"

    _run_verification(migrated_db)
    _assert_contract_proof(migrated_db)

    second = migrated_db.run_script(seed_sql)
    assert second.ok, second.error or "idempotent re-seed failed"

    _run_verification(migrated_db)

    cleanup = migrated_db.run_script(build_cleanup_sql())
    assert cleanup.ok, cleanup.error or "cleanup failed"

    for query, expected in (
        (
            f"SELECT count(*)::text FROM public.vendors WHERE slug LIKE '{SEED_PREFIX}%'",
            ["0"],
        ),
        (
            f"SELECT count(*)::text FROM public.products WHERE slug LIKE '{SEED_PREFIX}%'",
            ["0"],
        ),
        (
            f"SELECT count(*)::text FROM public.vendor_listings "
            f"WHERE sku LIKE '{SEED_PREFIX}%'",
            ["0"],
        ),
        ("SELECT count(*)::text FROM public.vendor_locations", ["0"]),
        ("SELECT count(*)::text FROM public.business_buyers", ["0"]),
        (
            "SELECT count(*)::text FROM auth.users "
            f"WHERE email LIKE '%{SEED_PREFIX}%'",
            ["0"],
        ),
    ):
        result = migrated_db.run(query)
        assert result.ok and result.rows == expected, f"cleanup left rows for: {query}"

    for image_id in IMAGE_IDS.values():
        parsed = uuid.UUID(image_id)
        assert str(parsed) == image_id

    for location in VENDOR_LOCATIONS:
        parsed = uuid.UUID(location.location_id)
        assert str(parsed) == location.location_id
