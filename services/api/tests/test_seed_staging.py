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
        "postgresql://staging.example/test",
        "-v",
        "ON_ERROR_STOP=1",
        "-At",
    ]
    assert captured["kwargs"]["input"] == "SELECT 1"
    assert "tests.rls.conftest" not in Path(seed_module.__file__).read_text()


def test_staging_seed_requires_migrated_vendor_schema(seed_module: Any) -> None:
    class MissingVendors:
        def run(self, _sql: str) -> Any:
            return seed_module.SqlResult(ok=True, rows=[""])

    with pytest.raises(RuntimeError, match="missing public.vendors"):
        seed_module._require_seed_schema(MissingVendors())
