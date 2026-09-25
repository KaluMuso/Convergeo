"""Dockerless command-double controls for database CI shell helpers."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _command(path: Path, body: str) -> None:
    path.write_text(f"#!/usr/bin/env bash\n{body}\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _run(script: str, bin_dir: Path, **extra: str) -> subprocess.CompletedProcess[str]:
    env = os.environ | {"PATH": f"{bin_dir}:{os.environ['PATH']}"} | extra
    return subprocess.run(
        ["bash", str(REPO_ROOT / script)], env=env, text=True, capture_output=True, check=False
    )


def test_postgres_meta_prefetch_immediate_success(tmp_path: Path) -> None:
    _command(tmp_path / "docker", "exit 0")
    result = _run("scripts/ci/prefetch-postgres-meta.sh", tmp_path)
    assert result.returncode == 0
    assert "1/4" in result.stderr


def test_postgres_meta_prefetch_retries_then_succeeds(tmp_path: Path) -> None:
    count = tmp_path / "count"
    _command(
        tmp_path / "docker",
        f"if [[ $1 == pull ]]; then n=$(cat {count} 2>/dev/null || echo 0); "
        f"n=$((n+1)); echo $n > {count}; ((n >= 2)); else exit 0; fi",
    )
    result = _run(
        "scripts/ci/prefetch-postgres-meta.sh",
        tmp_path,
        POSTGRES_META_PULL_BACKOFF_SECONDS="0",
    )
    assert result.returncode == 0
    assert count.read_text().strip() == "2"


def test_postgres_meta_prefetch_exhaustion_preserves_final_status(tmp_path: Path) -> None:
    _command(tmp_path / "docker", "[[ $1 != pull ]] || exit 23")
    result = _run(
        "scripts/ci/prefetch-postgres-meta.sh",
        tmp_path,
        POSTGRES_META_PULL_BACKOFF_SECONDS="0",
    )
    assert result.returncode == 23
    assert "4/4" in result.stderr


def test_postgres_meta_prefetch_propagates_inspect_error(tmp_path: Path) -> None:
    _command(tmp_path / "docker", "[[ $1 == pull ]] && exit 0; exit 29")
    result = _run("scripts/ci/prefetch-postgres-meta.sh", tmp_path)
    assert result.returncode == 29


def test_runtime_verifier_accepts_exact_versions_and_roles(tmp_path: Path) -> None:
    _command(
        tmp_path / "psql",
        "case \"$*\" in *server_version_num*) echo 170006;; *extversion*) echo 0.8.0;; "
        "*) printf 'anon|f|f\\nauthenticated|f|f\\nservice_role|f|t\\n"
        "vergeo_rls_tester|f|f\\n';; esac",
    )
    result = _run(
        "scripts/ci/verify-postgres-runtime.sh", tmp_path, SUPABASE_DB_URL="postgresql://fixture"
    )
    assert result.returncode == 0, result.stderr


def test_runtime_verifier_rejects_version_and_command_errors(tmp_path: Path) -> None:
    _command(tmp_path / "psql", "echo 160010")
    mismatch = _run(
        "scripts/ci/verify-postgres-runtime.sh", tmp_path, SUPABASE_DB_URL="postgresql://fixture"
    )
    assert mismatch.returncode != 0
    _command(tmp_path / "psql", "exit 19")
    command_error = _run(
        "scripts/ci/verify-postgres-runtime.sh", tmp_path, SUPABASE_DB_URL="postgresql://fixture"
    )
    assert command_error.returncode == 19


def test_typegen_failure_or_malformed_output_preserves_destination(tmp_path: Path) -> None:
    destination = REPO_ROOT / "packages/types/src/db.ts"
    original = destination.read_bytes()
    try:
        _command(tmp_path / "supabase", "exit 17")
        failed = _run(
            "scripts/gen-types.sh", tmp_path, SUPABASE_DB_URL="postgresql://fixture"
        )
        assert failed.returncode == 17
        assert destination.read_bytes() == original

        _command(tmp_path / "supabase", "printf 'not typescript\\n'")
        malformed = _run(
            "scripts/gen-types.sh", tmp_path, SUPABASE_DB_URL="postgresql://fixture"
        )
        assert malformed.returncode != 0
        assert destination.read_bytes() == original
    finally:
        destination.write_bytes(original)
