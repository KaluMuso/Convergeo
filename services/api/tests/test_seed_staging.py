"""Regression coverage for STG-SEED-04 synthetic marketplace contract."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
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
from app.staging.seed_sql import build_cleanup_sql, build_seed_sql, verification_queries
from app.staging.synthetic_contract import (
    CATALOG_FIXTURES,
    PERSONAS,
    SEED_PREFIX,
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
