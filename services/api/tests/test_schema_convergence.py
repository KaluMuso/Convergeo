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
EQUIVALENCE_PATH = REPO_ROOT / "scripts/ci/staging-migration-equivalence.json"
REHEARSAL_SCRIPT = REPO_ROOT / "scripts" / "ci" / "rehearse-schema-convergence.sh"
PREFLIGHT_SCRIPT = REPO_ROOT / "scripts/ci/preflight-staging-schema-convergence.sh"
DEPLOY_STAGING_WORKFLOW = REPO_ROOT / ".github/workflows/deploy-staging.yml"
PRODUCTION_DEPLOY_WORKFLOW = REPO_ROOT / ".github/workflows/deploy-production.yml"
LIVE_LEDGER = REPO_ROOT / "scripts/ci/fixtures/sandbox-live-ledger-20260813.txt"
POST_REPAIR_LEDGER = REPO_ROOT / "scripts/ci/fixtures/sandbox-post-repair-ledger-20260813.txt"

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


def _equivalence_manifest() -> dict[str, Any]:
    loaded = json.loads(EQUIVALENCE_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_live_sandbox_fixture_requires_ledger_repair() -> None:
    repo_versions = _repo_versions()
    manifest = _equivalence_manifest()
    remote = schema.parse_ledger(LIVE_LEDGER.read_text(encoding="utf-8"))
    plan = schema.evaluate_staging_preflight(
        repository_versions=repo_versions,
        remote_versions=remote,
        manifest=manifest,
        migrations_dir=REPO_ROOT / "supabase" / "migrations",
    )
    assert plan.ledger_repair_required is True
    assert plan.unresolved_remote_versions == []
    assert len(plan.equivalent_remote_aliases) == 4
    assert len(plan.superseded_rehearsal_rows) == 3
    assert plan.truly_pending_repository_migrations == [
        "20260812090000",
        "20260813064106",
        "20260813150000",
    ]


def test_post_repair_canonical_fixture_passes_preflight() -> None:
    repo_versions = _repo_versions()
    manifest = _equivalence_manifest()
    remote = schema.parse_ledger(POST_REPAIR_LEDGER.read_text(encoding="utf-8"))
    plan = schema.evaluate_staging_preflight(
        repository_versions=repo_versions,
        remote_versions=remote,
        manifest=manifest,
        migrations_dir=REPO_ROOT / "supabase" / "migrations",
    )
    assert plan.ledger_repair_required is False
    assert plan.unresolved_remote_versions == []
    assert plan.equivalent_remote_aliases == []
    assert plan.superseded_rehearsal_rows == []
    assert plan.truly_pending_repository_migrations == [
        "20260812090000",
        "20260813064106",
        "20260813150000",
    ]


def test_wrong_alias_hash_rejected(tmp_path: Path) -> None:
    manifest = _equivalence_manifest()
    bad_manifest = dict(manifest)
    bad_aliases = [dict(item) for item in manifest["exact_aliases"]]
    bad_aliases[0]["canonical_normalized_sha256"] = "0" * 64
    bad_manifest["exact_aliases"] = bad_aliases
    bad_path = tmp_path / "bad-equivalence.json"
    bad_path.write_text(json.dumps(bad_manifest) + "\n", encoding="utf-8")
    with pytest.raises(schema.SchemaConvergenceError, match="hash mismatch"):
        schema.verify_alias_hashes(
            migrations_dir=REPO_ROOT / "supabase" / "migrations",
            manifest=bad_manifest,
        )


def test_unknown_remote_rehearsal_rejected(tmp_path: Path) -> None:
    manifest = _equivalence_manifest()
    remote = schema.parse_ledger(LIVE_LEDGER.read_text(encoding="utf-8")) + ["20991231235959"]
    plan = schema.classify_staging_ledger(
        repository_versions=_repo_versions(),
        remote_versions=remote,
        manifest=manifest,
    )
    assert plan.unresolved_remote_versions == ["20991231235959"]


def test_partial_equivalence_mapping_rejected(tmp_path: Path) -> None:
    manifest = _equivalence_manifest()
    bad_aliases = [dict(item) for item in manifest["exact_aliases"]]
    bad_aliases[0]["equivalence"] = "schema_equivalent"
    bad_manifest = dict(manifest)
    bad_manifest["exact_aliases"] = bad_aliases
    with pytest.raises(schema.SchemaConvergenceError, match="unsupported alias equivalence"):
        schema.verify_alias_hashes(
            migrations_dir=REPO_ROOT / "supabase" / "migrations",
            manifest=bad_manifest,
        )


def test_duplicate_remote_alias_manifest_rejected() -> None:
    manifest = _equivalence_manifest()
    dup = dict(manifest)
    dup["exact_aliases"] = manifest["exact_aliases"] + [manifest["exact_aliases"][0]]
    with pytest.raises(schema.SchemaConvergenceError, match="duplicate remote aliases"):
        schema.classify_staging_ledger(
            repository_versions=_repo_versions(),
            remote_versions=schema.parse_ledger(LIVE_LEDGER.read_text(encoding="utf-8")),
            manifest=dup,
        )


def test_staging_preflight_cli_blocks_live_fixture() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            "--staging-preflight",
            "--json-plan",
            "--expected-source-sha",
            _equivalence_manifest()["verified_source_sha"],
            "--target-kind",
            "sandbox",
            "--target-project-ref",
            schema.SANDBOX_PROJECT_REF,
            "--ledger-file",
            str(LIVE_LEDGER),
            "--ledger-source",
            "live-query",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert schema.STAGING_LEDGER_REPAIR_REQUIRED in result.stderr


def test_staging_preflight_cli_accepts_post_repair_fixture() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            "--staging-preflight",
            "--json-plan",
            "--expected-source-sha",
            _equivalence_manifest()["verified_source_sha"],
            "--target-kind",
            "sandbox",
            "--target-project-ref",
            schema.SANDBOX_PROJECT_REF,
            "--ledger-file",
            str(POST_REPAIR_LEDGER),
            "--ledger-source",
            "live-query",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ledger_repair_required"] is False


def test_deploy_staging_runs_preflight_before_db_push() -> None:
    workflow = DEPLOY_STAGING_WORKFLOW.read_text(encoding="utf-8")
    preflight = workflow.index("preflight-staging-schema-convergence.sh")
    push = workflow.index("supabase db push --include-all")
    reconcile = workflow.index("reconcile-staging-migrations.sh")
    assert preflight < push < reconcile
    assert "STAGING_LEDGER_REPAIR_REQUIRED" in workflow


def test_preflight_adapter_forbids_production_and_db_push() -> None:
    script = PREFLIGHT_SCRIPT.read_text(encoding="utf-8")
    for line in script.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert "supabase db push" not in line
    assert "production ref is forbidden" in script
    assert "schema_convergence.py" in script
