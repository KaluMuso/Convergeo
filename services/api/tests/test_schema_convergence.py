"""Repository-only controls for the schema convergence release contract."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "scripts" / "ci" / "schema_convergence.py"
COHORTS_PATH = REPO_ROOT / "scripts" / "ci" / "schema-convergence-cohorts.json"
REHEARSAL_SCRIPT = REPO_ROOT / "scripts" / "ci" / "rehearse-schema-convergence.sh"
PRODUCTION_DEPLOY_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy-production.yml"


def _module() -> Any:
    spec = importlib.util.spec_from_file_location("schema_convergence", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


schema: Any = _module()


def _repo_versions() -> list[str]:
    migrations = schema.repository_migrations(REPO_ROOT / "supabase" / "migrations")
    return [migration.version for migration in migrations]


def _manifest() -> dict[str, Any]:
    loaded = json.loads(COHORTS_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_v1_profile_is_d33_d34_exact_and_blocks_future_activation() -> None:
    manifest = _manifest()
    schema.assert_v1_profile(manifest)
    profile = manifest["v1_release_profile"]
    assert profile["allowed_product_classes"] == ["A"]
    assert profile["allowed_conditions"] == ["new", "refurbished"]
    assert profile["allowed_sale_units"] == ["each"]
    assert profile["allowed_admin_roles"] == ["admin"]
    assert set(profile["blocked_roles"]) == {"superadmin", "moderator"}


def test_repository_migrations_have_unique_versions_and_manifest_is_deterministic() -> None:
    migrations = schema.repository_migrations(REPO_ROOT / "supabase" / "migrations")
    assert len(migrations) == len({migration.version for migration in migrations})
    assert schema.manifest_digest(migrations, _manifest()) == schema.manifest_digest(
        migrations, _manifest()
    )


def test_production_and_unknown_targets_are_rejected() -> None:
    with pytest.raises(schema.SchemaConvergenceError, match="production project ref"):
        schema.assert_sandbox_target(
            target_kind="sandbox", target_project_ref=schema.PRODUCTION_PROJECT_REF
        )
    with pytest.raises(schema.SchemaConvergenceError, match="only target-kind=sandbox"):
        schema.assert_sandbox_target(
            target_kind="production", target_project_ref=schema.SANDBOX_PROJECT_REF
        )
    with pytest.raises(schema.SchemaConvergenceError, match="does not match"):
        schema.assert_sandbox_target(target_kind="sandbox", target_project_ref="not-a-project")


def test_contiguous_prefix_accepts_sandbox_ledger_and_reports_pending() -> None:
    versions = _repo_versions()
    pending = schema.assert_contiguous_ledger(
        repository_versions=versions, remote_versions=versions[:79]
    )
    assert pending == versions[79:]


@pytest.mark.parametrize(
    ("remote", "message"),
    [
        ([], "empty"),
        (["0001", "0001"], "duplicate"),
        (["0001", "0003"], "ordered repository prefix"),
        (["999999"], "ordered repository prefix"),
    ],
)
def test_contiguous_prefix_rejects_missing_reordered_or_unknown_history(
    remote: list[str], message: str
) -> None:
    with pytest.raises(schema.SchemaConvergenceError, match=message):
        schema.assert_contiguous_ledger(
            repository_versions=_repo_versions(), remote_versions=remote
        )


def test_contiguous_prefix_rejects_reordered_history() -> None:
    versions = _repo_versions()
    with pytest.raises(schema.SchemaConvergenceError, match="ordered repository prefix"):
        schema.assert_contiguous_ledger(
            repository_versions=versions, remote_versions=[versions[1], versions[0]]
        )


def test_rehearsal_requires_live_query_and_declared_completed_tip(tmp_path: Path) -> None:
    versions = _repo_versions()
    manifest = _manifest()
    cohort = schema.cohort_by_id(manifest, "dark-ship-foundation")
    end = versions.index(cohort["through_version"]) + 1
    ledger = tmp_path / "ledger.txt"
    ledger.write_text("\n".join(versions[:end]) + "\n", encoding="utf-8")

    result = schema.main(
        [
            "--migrations-dir",
            str(REPO_ROOT / "supabase" / "migrations"),
            "--cohorts-file",
            str(COHORTS_PATH),
            "--target-kind",
            "sandbox",
            "--target-project-ref",
            schema.SANDBOX_PROJECT_REF,
            "--ledger-file",
            str(ledger),
            "--ledger-source",
            "fixture",
            "--cohort",
            "dark-ship-foundation",
        ]
    )
    assert result == 1

    assert (
        schema.main(
            [
                "--migrations-dir",
                str(REPO_ROOT / "supabase" / "migrations"),
                "--cohorts-file",
                str(COHORTS_PATH),
                "--target-kind",
                "sandbox",
                "--target-project-ref",
                schema.SANDBOX_PROJECT_REF,
                "--ledger-file",
                str(ledger),
                "--ledger-source",
                "live-query",
                "--cohort",
                "dark-ship-foundation",
            ]
        )
        == 0
    )


def test_rehearsal_adapter_contains_no_apply_command_or_production_escape_hatch() -> None:
    script = REHEARSAL_SCRIPT.read_text(encoding="utf-8")
    for line in script.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert "supabase db push" not in line
    assert "select version from supabase_migrations.schema_migrations" in script
    assert "SCHEMA_TARGET_KIND" in script
    assert "production ref is forbidden" in script


def test_production_workflow_cannot_apply_schema() -> None:
    workflow = PRODUCTION_DEPLOY_WORKFLOW.read_text(encoding="utf-8")
    assert "supabase db push" not in workflow
    assert "workflow_dispatch" in workflow


def test_cli_refuses_green_result_without_ledger_file() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            "--target-kind",
            "sandbox",
            "--target-project-ref",
            schema.SANDBOX_PROJECT_REF,
            "--cohort",
            "dark-ship-foundation",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "ledger-file" in result.stderr
