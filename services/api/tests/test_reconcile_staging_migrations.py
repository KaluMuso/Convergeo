"""Repository-only controls for staging migration reconciliation."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "scripts" / "ci" / "reconcile_staging_migrations.py"
LIVE_LEDGER = REPO_ROOT / "scripts/ci/fixtures/sandbox-live-ledger-20260813.txt"
POST_REPAIR_LEDGER = REPO_ROOT / "scripts/ci/fixtures/sandbox-post-repair-ledger-20260813.txt"
PENDING_REPAIR_VERSIONS = {
    "20260812090000",
    "20260813064106",
    "20260813150000",
    "20260813160000",
    "20260813160100",
    "20260813160200",
    "20260815194500",
    "20260815230000",
    # Repo migrations added after the 2026-08-13 post-repair ledger snapshot.
    "20260816220000",
    "20260817200000",
    "20260827020000",
}


def _module() -> Any:
    spec = importlib.util.spec_from_file_location("reconcile_staging_migrations", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


reconcile: Any = _module()


def _repo_versions() -> list[str]:
    versions: list[str] = reconcile.repo_migration_versions(REPO_ROOT / "supabase" / "migrations")
    return versions


def _repo_versions_applied_after_repair() -> list[str]:
    return [version for version in _repo_versions() if version not in PENDING_REPAIR_VERSIONS]


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
    remote = reconcile.parse_remote_versions(POST_REPAIR_LEDGER.read_text(encoding="utf-8"))
    reconcile.reconcile_versions(_repo_versions_applied_after_repair(), remote)


def test_post_repair_ledger_does_not_accept_rehearsal_rows() -> None:
    remote = reconcile.parse_remote_versions(POST_REPAIR_LEDGER.read_text(encoding="utf-8"))
    extra = remote + ["20260813072110"]
    with pytest.raises(reconcile.MigrationReconcileError, match="absent from repository"):
        reconcile.reconcile_versions(_repo_versions_applied_after_repair(), extra)


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
