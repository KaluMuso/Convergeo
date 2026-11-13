"""Dockerless command-double controls for database CI shell helpers."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def _command(path: Path, body: str) -> None:
    path.write_text(f"#!/usr/bin/env bash\n{body}\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _run(script: str, bin_dir: Path, **extra: str) -> subprocess.CompletedProcess[str]:
    env = os.environ | {"PATH": f"{bin_dir}:{os.environ['PATH']}"} | extra
    return subprocess.run(
        ["bash", str(REPO_ROOT / script)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
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


# The mirror preserves the exact pinned generator name/version used by gen types.
_ECR_META = "public.ecr.aws/supabase/postgres-meta:v0.96.6"
_GHCR_META = "ghcr.io/supabase/postgres-meta:v0.96.6"
_IMAGE_ID = "sha256:" + "a" * 64


def _mirror_docker(bin_dir: Path) -> Path:
    log = bin_dir / "docker-commands"
    _command(
        bin_dir / "docker",
        r'''set -eu
printf '%s\n' "$*" >> "$DOCKER_COMMAND_LOG"
case "$1" in
  pull)
    if [[ "$2" == public.ecr.aws/* ]]; then exit 23; fi
    [[ "$2" == ghcr.io/supabase/postgres-meta:v0.96.6 ]] || exit 91
    [[ "${MIRROR_MODE:-}" != exhausted ]] || exit 47
    ;;
  tag)
    [[ "$2" == "$MIRROR_IMAGE_ID" &&
       "$3" == public.ecr.aws/supabase/postgres-meta:v0.96.6 ]] || exit 92
    [[ "${MIRROR_MODE:-}" != tag-failure ]] || exit 48
    ;;
  image)
    [[ "$2" == inspect ]] || exit 93
    target="${*: -1}"
    if [[ "$3" == '--format={{.Id}}' ]]; then
      if [[ "$target" == ghcr.io/* ]]; then
        [[ "${MIRROR_MODE:-}" != mirror-inspect-failure ]] || exit 49
        if [[ "${MIRROR_MODE:-}" == malformed-id ]]; then
          echo invalid
        elif [[ "${MIRROR_MODE:-}" == empty-id ]]; then
          :
        else
          printf '%s\n' "$MIRROR_IMAGE_ID"
          [[ "${MIRROR_MODE:-}" != valid-then-failure ]] || exit 50
        fi
      else
        [[ "${MIRROR_MODE:-}" != alias-inspect-failure ]] || exit 51
        if [[ "${MIRROR_MODE:-}" == alias-mismatch ]]; then
          printf 'sha256:%064d\n' 7
        else
          printf '%s\n' "$MIRROR_IMAGE_ID"
        fi
      fi
    else
      [[ "${MIRROR_MODE:-}" != final-inspect-failure ]] || exit 52
      printf 'postgres-meta image=ghcr.io/supabase/postgres-meta@sha256:%064d id=%s\n' \
        8 "$MIRROR_IMAGE_ID"
    fi
    ;;
  *) exit 94 ;;
esac''',
    )
    return log


def _mirror_run(tmp_path: Path, mode: str = "", **extra: str) -> subprocess.CompletedProcess[str]:
    log = _mirror_docker(tmp_path)
    return _run(
        "scripts/ci/prefetch-postgres-meta.sh",
        tmp_path,
        DOCKER_COMMAND_LOG=str(log),
        MIRROR_IMAGE_ID=_IMAGE_ID,
        MIRROR_MODE=mode,
        POSTGRES_META_PULL_BACKOFF_SECONDS="0",
        **extra,
    )


def test_postgres_meta_official_mirror_preserves_generator_alias(tmp_path: Path) -> None:
    result = _mirror_run(tmp_path)
    assert result.returncode == 0, result.stderr
    commands = (tmp_path / "docker-commands").read_text().splitlines()
    assert commands[:4] == [f"pull {_ECR_META}"] * 4
    assert commands[4] == f"pull {_GHCR_META}"
    assert f"tag {_IMAGE_ID} {_ECR_META}" in commands
    assert f"pull_source={_GHCR_META} local_alias={_ECR_META} image_id={_IMAGE_ID}" in result.stdout
    assert "image=ghcr.io/supabase/postgres-meta@sha256:" in result.stdout


@pytest.mark.parametrize(
    ("mode", "status"),
    [
        ("exhausted", 47),
        ("tag-failure", 48),
        ("mirror-inspect-failure", 49),
        ("valid-then-failure", 50),
        ("alias-inspect-failure", 51),
        ("final-inspect-failure", 52),
        ("alias-mismatch", 1),
        ("malformed-id", 1),
        ("empty-id", 1),
    ],
)
def test_postgres_meta_mirror_failures_stop_prefetch(
    tmp_path: Path, mode: str, status: int
) -> None:
    result = _mirror_run(tmp_path, mode)
    assert result.returncode == status, result.stderr
    commands = (tmp_path / "docker-commands").read_text().splitlines()
    if mode == "exhausted":
        assert commands == [f"pull {_ECR_META}"] * 4 + [f"pull {_GHCR_META}"] * 4
    if mode in {
        "exhausted",
        "mirror-inspect-failure",
        "valid-then-failure",
        "malformed-id",
        "empty-id",
    }:
        assert not any(command.startswith("tag ") for command in commands)


def test_postgres_meta_override_does_not_use_unrelated_mirror(tmp_path: Path) -> None:
    override = "public.ecr.aws/supabase/postgres-meta:v0.96.5"
    result = _mirror_run(tmp_path, POSTGRES_META_IMAGE=override)
    assert result.returncode == 23
    assert (tmp_path / "docker-commands").read_text().splitlines() == [f"pull {override}"] * 4


@pytest.mark.parametrize("attempts", ["0", "-1", "abc", "11"])
def test_postgres_meta_prefetch_rejects_invalid_budget(tmp_path: Path, attempts: str) -> None:
    result = _mirror_run(tmp_path, POSTGRES_META_PULL_ATTEMPTS=attempts)
    assert result.returncode == 2
    assert not (tmp_path / "docker-commands").exists()
