"""Regression coverage for the isolated staging seed helper."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


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
    assert captured["args"][0] == [
        "psql",
        "-X",
        "-v",
        "ON_ERROR_STOP=1",
        "-At",
        "-d",
        "postgresql://staging.example/test",
        "-c",
        "SELECT 1",
    ]
    assert "input" not in captured["kwargs"]
    assert "tests.rls.conftest" not in Path(seed_module.__file__).read_text()


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


def test_staging_seed_uses_constraint_aligned_auditable_kyc_fixtures(
    seed_module: Any,
) -> None:
    seed_module._validate_fixtures()
    sql = seed_module._build_seed_sql()

    assert "'draft', NULL" in sql
    assert "'pending_kyc', NULL" in sql
    assert "'active', 1" in sql
    assert "'pending', 0" not in sql
    assert "'pending', 1" not in sql
    assert "'submitted'" in sql
    assert "'approved'" in sql
    assert "'synthetic staging approval'" in sql
    assert "ARRAY[]::text[]" in sql


def test_staging_seed_adds_one_constraint_aligned_catalogue_fixture(
    seed_module: Any,
) -> None:
    seed_module._validate_fixtures()
    sql = seed_module._build_seed_sql()
    fixture = seed_module.CATALOG_FIXTURE

    assert "INSERT INTO public.categories" in sql
    assert "INSERT INTO public.products" in sql
    assert "INSERT INTO public.vendor_listings" in sql
    assert fixture["listing_sku"] in sql
    assert f"{fixture['price_ngwee']}" in sql
    assert f"{fixture['stock_qty']}" in sql
    assert "'active'" in sql
    assert "false, 1, false" in sql
    assert "INSERT INTO public.listing_images" not in sql
    assert "INSERT INTO public.orders" not in sql
    assert "INSERT INTO public.payments" not in sql


def test_staging_seed_rejects_vendor_lifecycle_drift(
    monkeypatch: pytest.MonkeyPatch,
    seed_module: Any,
) -> None:
    bad_vendor = dict(seed_module.FIXTURES[1], vendor_status="pending", kyc_tier=0)
    monkeypatch.setattr(seed_module, "FIXTURES", [bad_vendor])

    with pytest.raises(seed_module.StagingIsolationError, match="invalid synthetic vendor status"):
        seed_module._validate_fixtures()


def test_staging_seed_rejects_invalid_vendor_kyc_tier(
    monkeypatch: pytest.MonkeyPatch,
    seed_module: Any,
) -> None:
    bad_vendor = dict(seed_module.FIXTURES[1], kyc_tier=0)
    monkeypatch.setattr(seed_module, "FIXTURES", [bad_vendor])

    with pytest.raises(
        seed_module.StagingIsolationError,
        match="invalid synthetic vendor KYC tier",
    ):
        seed_module._validate_fixtures()


def test_staging_seed_rejects_non_positive_catalogue_price(
    monkeypatch: pytest.MonkeyPatch,
    seed_module: Any,
) -> None:
    bad_catalogue = dict(seed_module.CATALOG_FIXTURE, price_ngwee=0)
    monkeypatch.setattr(seed_module, "CATALOG_FIXTURE", bad_catalogue)

    with pytest.raises(
        seed_module.StagingIsolationError,
        match="price_ngwee must be a positive integer",
    ):
        seed_module._validate_fixtures()
