"""Repository-only controls for staging migration reconciliation."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "scripts" / "ci" / "reconcile_staging_migrations.py"
LIVE_LEDGER = REPO_ROOT / "scripts/ci/fixtures/sandbox-live-ledger-20260813.txt"
POST_REPAIR_LEDGER = REPO_ROOT / "scripts/ci/fixtures/sandbox-post-repair-ledger-20260813.txt"


def _module():
    spec = importlib.util.spec_from_file_location("reconcile_staging_migrations", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


reconcile = _module()


def _repo_versions() -> list[str]:
    return reconcile.repo_migration_versions(REPO_ROOT / "supabase" / "migrations")


def test_matching_repository_remote_succeeds(tmp_path: Path) -> None:
    repo_versions = _repo_versions()
    ledger = tmp_path / "ledger.txt"
    ledger.write_text("\n".join(repo_versions) + "\n", encoding="utf-8")
    reconcile.reconcile_versions(repo_versions, reconcile.parse_remote_versions(ledger.read_text()))


def test_missing_repository_migration_fails(tmp_path: Path) -> None:
    repo_versions = _repo_versions()
    remote = repo_versions[:-1]
    with pytest.raises(reconcile.MigrationReconcileError, match="missing repository migrations"):
        reconcile.reconcile_versions(repo_versions, remote)


def test_live_sandbox_ledger_with_aliases_fails(tmp_path: Path) -> None:
    repo_versions = _repo_versions()
    remote = reconcile.parse_remote_versions(LIVE_LEDGER.read_text(encoding="utf-8"))
    with pytest.raises(reconcile.MigrationReconcileError, match="missing repository migrations"):
        reconcile.reconcile_versions(repo_versions, remote)


def test_post_repair_canonical_prefix_passes_with_pending_tip() -> None:
    repo_versions = _repo_versions()
    remote = reconcile.parse_remote_versions(POST_REPAIR_LEDGER.read_text(encoding="utf-8"))
    reconcile.reconcile_versions(
        [version for version in repo_versions if version not in {"20260812090000", "20260813064106", "20260813150000"}],
        remote,
    )


def test_post_repair_ledger_does_not_accept_rehearsal_rows() -> None:
    repo_versions = _repo_versions()
    remote = reconcile.parse_remote_versions(POST_REPAIR_LEDGER.read_text(encoding="utf-8"))
    extra = remote + ["20260813072110"]
    with pytest.raises(reconcile.MigrationReconcileError, match="absent from repository"):
        reconcile.reconcile_versions(
            [version for version in repo_versions if version not in {"20260812090000", "20260813064106", "20260813150000"}],
            extra,
        )


def test_cli_live_fixture_fails() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            "--migrations-dir",
            str(REPO_ROOT / "supabase" / "migrations"),
            "--remote-versions-file",
            str(LIVE_LEDGER),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "missing repository migrations" in result.stderr


def test_cli_post_repair_prefix_reports_missing_pending() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            "--migrations-dir",
            str(REPO_ROOT / "supabase" / "migrations"),
            "--remote-versions-file",
            str(POST_REPAIR_LEDGER),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "missing repository migrations" in result.stderr
