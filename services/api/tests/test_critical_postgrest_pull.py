"""Mock the critical job's pinned PostgREST pull; never contact a registry."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

IMAGE = "public.ecr.aws/supabase/postgrest:v14.14"
ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "scripts" / "ci" / "pull-critical-postgrest-image.sh"


def _bash_path(path: Path) -> str:
    resolved = path.resolve().as_posix()
    if os.name == "nt":
        return f"/{resolved[0].lower()}{resolved[2:]}"
    return resolved


def _bash_executable() -> str:
    if os.name == "nt":
        return r"C:\Program Files\Git\bin\bash.exe"
    return shutil.which("bash") or "bash"


def _run_pull(tmp_path: Path, scenario: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()
    for name, body in (
        (
            "docker",
            """printf '%s\\n' "$*" >> "$MOCK_DOCKER_CALLS"
case "$MOCK_SCENARIO" in
  eventual) [[ "$(wc -l < "$MOCK_DOCKER_CALLS")" -ge 3 ]] ;;
  exhausted) false ;;
  other)
    echo 'toomanyrequests: Rate exceeded' >&2
    echo 'Error response from daemon: manifest unknown' >&2
    exit 1 ;;
  *) echo 'unexpected Docker call' >&2; exit 99 ;;
esac
if [[ "$?" -ne 0 ]]; then
  echo 'toomanyrequests: Rate exceeded' >&2
  exit 1
fi
echo 'Image is up to date'
""",
        ),
    ):
        mock_command = mock_bin / name
        mock_command.write_text(
            f"#!/usr/bin/env bash\n{body}\n", encoding="utf-8", newline="\n"
        )
        mock_command.chmod(0o755)

    logs = tmp_path / "logs"
    logs.mkdir()
    environment = {
        **os.environ,
        "MOCK_SCENARIO": scenario,
        "MOCK_DOCKER_CALLS": _bash_path(tmp_path / "docker-calls"),
        "MOCK_TIMEOUT_CALLS": _bash_path(tmp_path / "timeout-calls"),
        "MOCK_SLEEP_CALLS": _bash_path(tmp_path / "sleep-calls"),
    }
    command = (
        f"PATH={shlex.quote(_bash_path(mock_bin))}:/usr/bin:$PATH; "
        "timeout() { printf '%s\\n' \"$*\" >> \"$MOCK_TIMEOUT_CALLS\"; "
        "if [[ \"$MOCK_SCENARIO\" == timed_out ]]; then "
        "echo 'toomanyrequests: Rate exceeded' >&2; return 124; fi; "
        "shift 2; \"$@\"; }; "
        "sleep() { printf '%s\\n' \"$1\" >> \"$MOCK_SLEEP_CALLS\"; }; "
        f"source {shlex.quote(_bash_path(HELPER))} "
        f"{shlex.quote(IMAGE)} {shlex.quote(_bash_path(logs))}"
    )
    result = subprocess.run(
        [_bash_executable(), "-c", command],
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    return result, tmp_path


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def test_critical_harness_uses_pinned_image_and_pull_helper() -> None:
    source = (ROOT / "scripts" / "ci" / "run-critical-real-stack.sh").read_text(
        encoding="utf-8"
    )
    assert f"rest_image='{IMAGE}'" in source
    assert (
        'bash scripts/ci/pull-critical-postgrest-image.sh "$rest_image" "$evidence/logs"'
        in source
    )


def test_rate_limit_then_success_keeps_every_attempt(tmp_path: Path) -> None:
    result, root = _run_pull(tmp_path, "eventual")
    assert result.returncode == 0, result.stderr
    assert _lines(root / "docker-calls") == [f"pull {IMAGE}"] * 3
    assert _lines(root / "sleep-calls") == ["5", "10"]
    assert _lines(root / "timeout-calls") == [
        f"--kill-after=5s 60s docker pull {IMAGE}"
    ] * 3
    logs = root / "logs"
    assert len(list(logs.glob("postgrest-pull-attempt-*.log"))) == 3
    summary = (logs / "postgrest-pull.log").read_text(encoding="utf-8")
    assert summary.count("toomanyrequests: Rate exceeded") == 2
    assert "attempt=3/3 result=success" in summary
    assert "Image is up to date" in summary


def test_repeated_rate_limit_exhausts_without_success(tmp_path: Path) -> None:
    result, root = _run_pull(tmp_path, "exhausted")
    assert result.returncode == 1
    assert _lines(root / "docker-calls") == [f"pull {IMAGE}"] * 3
    assert _lines(root / "sleep-calls") == ["5", "10"]
    assert "rate limit persisted after 3 attempts" in result.stderr
    summary = (root / "logs" / "postgrest-pull.log").read_text(encoding="utf-8")
    assert summary.count("toomanyrequests: Rate exceeded") == 3
    assert "result=success" not in summary


@pytest.mark.parametrize(
    ("scenario", "expected_status", "expected_calls"),
    [("other", 1, 1), ("timed_out", 124, 0)],
)
def test_non_rate_error_or_timeout_fails_immediately(
    tmp_path: Path, scenario: str, expected_status: int, expected_calls: int
) -> None:
    result, root = _run_pull(tmp_path, scenario)
    assert result.returncode == expected_status
    assert len(_lines(root / "docker-calls")) == expected_calls
    assert _lines(root / "sleep-calls") == []
    assert len(list((root / "logs").glob("postgrest-pull-attempt-*.log"))) == 1
    assert "result=success" not in (
        root / "logs" / "postgrest-pull.log"
    ).read_text(encoding="utf-8")
