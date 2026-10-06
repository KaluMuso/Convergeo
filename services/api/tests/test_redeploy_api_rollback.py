"""Exercise rollback output with only local command doubles, never Docker."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest


def _bash_path(path: Path) -> str:
    resolved = path.resolve().as_posix()
    if os.name == "nt":
        return f"/{resolved[0].lower()}{resolved[2:]}"
    return resolved


def _bash_executable() -> str:
    if os.name == "nt":
        return r"C:\Program Files\Git\bin\bash.exe"
    return shutil.which("bash") or "bash"


def test_api_image_records_its_own_source_revision() -> None:
    dockerfile = Path(__file__).resolve().parents[3] / "infra" / "api.Dockerfile"
    assert 'LABEL org.opencontainers.image.revision="${GIT_SHA}"' in dockerfile.read_text(
        encoding="utf-8"
    )


def test_staging_deploy_requires_full_source_sha() -> None:
    script = Path(__file__).resolve().parents[3] / "infra" / "staging" / "redeploy-api-staging.sh"
    source = script.read_text(encoding="utf-8")
    assert '[[ ! "$TAG" =~ ^[0-9a-f]{40}$ ]]' in source
    assert '-e "GIT_SHA=${TAG}"' in source


@pytest.mark.parametrize(
    ("previous_sha", "candidate_sha", "tag"),
    [
        ("d" * 40, "c" * 40, "c" * 40),
        ("unknown", "c" * 40, "c" * 40),
        ("d" * 7, "c" * 40, "c" * 40),
        ("d" * 40, "e" * 40, "c" * 40),
        ("d" * 40, "c" * 40, "latest"),
    ],
)
def test_failed_redeploy_uses_only_verified_previous_image_identity(
    tmp_path: Path, previous_sha: str, candidate_sha: str, tag: str
) -> None:
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()
    docker = mock_bin / "docker"
    docker.write_text(
        """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$MOCK_LOG"
case "$1" in
  pull|rm|run|ps) exit 0 ;;
  inspect) printf 'sha256:%064d\\n' 1 ;;
  image)
    if [[ "$3" == sha256:* ]]; then
      printf '%s\\n' "$MOCK_PREV_SHA"
    elif [[ "$5" == *RepoDigests* ]]; then
      printf 'ghcr.io/kalumuso/convergeo-api@sha256:%064d\\n' 2
    else
      printf '%s\\n' "$MOCK_CANDIDATE_SHA"
    fi ;;
  *) exit 99 ;;
esac
""",
        encoding="utf-8",
        newline="\n",
    )
    docker.chmod(0o755)
    for name, body in (
        ("curl", "exit 22"),
        ("sleep", "exit 0"),
        ("seq", "printf '1\\n'"),
    ):
        mock_command = mock_bin / name
        mock_command.write_text(
            f"#!/usr/bin/env bash\n{body}\n", encoding="utf-8", newline="\n"
        )
        mock_command.chmod(0o755)
    env_file = tmp_path / "api.env"
    env_file.write_text(f"GIT_SHA={'b' * 40}\n", encoding="utf-8")
    log = tmp_path / "docker.log"
    environment = {
        **os.environ,
        "API_ENV_FILE": _bash_path(env_file),
        "MOCK_LOG": _bash_path(log),
        "MOCK_PREV_SHA": previous_sha,
        "MOCK_CANDIDATE_SHA": candidate_sha,
    }
    candidate = "c" * 40
    script = Path(__file__).resolve().parents[3] / "infra" / "redeploy-api.sh"
    command = (
        f"PATH={shlex.quote(_bash_path(mock_bin))}:$PATH "
        f"bash {shlex.quote(_bash_path(script))} {tag}"
    )
    result = subprocess.run(
        [_bash_executable(), "-c", command],
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 1, result.stderr
    calls = log.read_text(encoding="utf-8")
    assert f"image inspect ghcr.io/kalumuso/convergeo-api:{tag}" in calls
    if candidate_sha != candidate:
        assert "candidate image source SHA differs" in result.stderr
        assert "rm -f" not in calls and "run -d" not in calls
        return
    assert "inspect --format {{.Image}}" in calls
    previous_image_id = "sha256:" + "0" * 63 + "1"
    assert f"image inspect {previous_image_id}" in calls
    expected_tag = candidate if tag != "latest" else "0" * 63 + "2"
    assert f"API_IMAGE_TAG={expected_tag}" in calls
    assert f"--env-file {_bash_path(env_file)} -e GIT_SHA={candidate}" in calls
    if previous_sha == "d" * 40:
        rollback = next(line for line in result.stderr.splitlines() if "rollback:" in line)
        assert f"GIT_SHA={previous_sha}" in rollback
        assert f"API_IMAGE_TAG={previous_sha}" in rollback
        assert "sha256:" in rollback
        assert candidate not in rollback
    else:
        assert "verify its identity before redeploying" in result.stderr
        assert "rollback: docker rm" not in result.stderr
