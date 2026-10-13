from __future__ import annotations

import os
import re
import shlex
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[3]
PRELOAD = ROOT / "scripts/ci/preload-typegen-meta.sh"
IMAGE = (
    "ghcr.io/supabase/postgres-meta@"
    "sha256:a84cc713585eea7b401e4a2561ec4a1e48c87083d1c7ecb4502f204bb4391300"
)
TAG = "public.ecr.aws/supabase/postgres-meta:v0.96.6"
IMAGE_ID = "sha256:" + "1" * 64
QUALIFYING_STEPS = [
    "Setup Supabase CLI",
    "Start local database",
    "Reset local database",
    "Preload qualified postgres-meta from official GHCR",
    "Regenerate types",
    "Fail on stale committed types",
]

DOCKER_STUB = r"""#!/usr/bin/env bash
set -euo pipefail
printf 'docker %s\n' "$*" >> "$TRACE"
case "$1 $2" in
  'version --format')
    if [[ "$PRELOAD_SCENARIO" == runner ]]; then echo linux/arm64; else echo linux/amd64; fi ;;
  'pull --platform')
    [[ "$3" == linux/amd64 && "$4" == "$EXPECTED_IMAGE" ]] || exit 90
    [[ "$PRELOAD_SCENARIO" != pull ]] || exit 71 ;;
  'image inspect')
    [[ "$PRELOAD_SCENARIO" != inspect ]] || exit 73
    case "$4" in
      '{{range .RepoDigests}}{{println .}}{{end}}')
        case "$PRELOAD_SCENARIO" in
          digest) echo 'ghcr.io/supabase/postgres-meta@sha256:wrong' ;;
          digest-prefix) echo "${EXPECTED_IMAGE}extra" ;;
          *) echo "$EXPECTED_IMAGE" ;;
        esac ;;
      '{{.Os}}/{{.Architecture}}')
        if [[ "$PRELOAD_SCENARIO" == platform ]]; then
          echo linux/arm64
        else
          echo linux/amd64
        fi ;;
      '{{.Id}}')
        if [[ "$PRELOAD_SCENARIO" == identity ]]; then echo ''; exit 0; fi
        if [[ "$5" == "$EXPECTED_TAG" && "$PRELOAD_SCENARIO" == alias ]]; then
          echo "sha256:$(printf '2%.0s' {1..64})"
        else
          echo "$EXPECTED_ID"
        fi ;;
      *) exit 90 ;;
    esac ;;
  tag*)
    [[ "$2" == "$EXPECTED_IMAGE" && "$3" == "$EXPECTED_TAG" ]] || exit 90
    [[ "$PRELOAD_SCENARIO" != tag ]] || exit 72 ;;
  *) exit 90 ;;
esac
"""


def write_command(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


def environment(tmp_path: Path, scenario: str) -> dict[str, str]:
    bin_path = tmp_path / "bin"
    bin_path.mkdir()
    write_command(bin_path / "docker", DOCKER_STUB)
    return {
        "PATH": f"{bin_path}:{os.defpath}",
        "TRACE": str(tmp_path / "trace"),
        "PRELOAD_SCENARIO": scenario,
        "EXPECTED_IMAGE": IMAGE,
        "EXPECTED_TAG": TAG,
        "EXPECTED_ID": IMAGE_ID,
    }


def trace(env: dict[str, str]) -> list[str]:
    return Path(env["TRACE"]).read_text(encoding="utf-8").splitlines()


def test_verified_image_is_cached_under_the_unchanged_ecr_name(tmp_path: Path) -> None:
    env = environment(tmp_path, "success")
    result = subprocess.run(["bash", str(PRELOAD)], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    calls = trace(env)
    assert f"docker pull --platform linux/amd64 {IMAGE}" in calls
    assert f"docker tag {IMAGE} {TAG}" in calls
    assert calls[-1] == f"docker image inspect --format {{{{.Id}}}} {TAG}"
    assert sum(call.startswith("docker pull ") for call in calls) == 1
    assert "image cached" in result.stdout


@pytest.mark.parametrize(
    ("scenario", "expected_message", "tag_attempted"),
    [
        ("runner", "runner platform", False),
        ("pull", "", False),
        ("inspect", "", False),
        ("digest", "digest is absent", False),
        ("digest-prefix", "digest is absent", False),
        ("platform", "Pulled postgres-meta platform", False),
        ("identity", "image identity is invalid", False),
        ("tag", "", True),
        ("alias", "ECR alias does not match", True),
    ],
)
def test_preload_failures_stop_without_fallback(
    tmp_path: Path, scenario: str, expected_message: str, tag_attempted: bool
) -> None:
    env = environment(tmp_path, scenario)
    result = subprocess.run(["bash", str(PRELOAD)], env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert expected_message in result.stderr
    calls = trace(env)
    assert any(call.startswith("docker tag ") for call in calls) is tag_attempted
    assert sum(call.startswith("docker pull ") for call in calls) <= 1
    assert all(not call.startswith(("docker login", "docker push", "docker run")) for call in calls)
    assert "image cached" not in result.stdout


@pytest.mark.parametrize(("failure", "exit_code"), [("generator", 42), ("drift", 43)])
def test_preload_does_not_mask_generation_or_type_comparison_failure(
    tmp_path: Path, failure: str, exit_code: int
) -> None:
    env = environment(tmp_path, "success")
    env["PIPELINE_FAILURE"] = failure
    fixture = tmp_path / "checkout"
    scripts = fixture / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "gen-types.sh").write_text((ROOT / "scripts/gen-types.sh").read_text())
    output = fixture / "packages/types/src/db.ts"
    output.parent.mkdir(parents=True)
    output.write_text("unchanged\n")
    bin_path = Path(env["PATH"].split(":")[0])
    write_command(
        bin_path / "supabase",
        """#!/usr/bin/env bash
set -euo pipefail
printf 'supabase %s\n' "$*" >> "$TRACE"
if [[ "$1" == status ]]; then exit 0; fi
[[ "$*" == 'gen types typescript --local' ]] || exit 90
[[ "$PIPELINE_FAILURE" != generator ]] || exit 42
printf 'export type Database = {};\n'
""",
    )
    write_command(
        bin_path / "git",
        """#!/usr/bin/env bash
set -euo pipefail
printf 'git %s\n' "$*" >> "$TRACE"
[[ "$*" == 'diff --exit-code packages/types/src/db.ts' ]] || exit 90
[[ "$PIPELINE_FAILURE" != drift ]] || exit 43
""",
    )
    commands = "\n".join(
        [
            shlex.join(["bash", str(PRELOAD)]),
            "bash scripts/gen-types.sh",
            "git diff --exit-code packages/types/src/db.ts",
        ]
    )
    result = subprocess.run(
        ["bash", "-e", "-c", commands], cwd=fixture, env=env, capture_output=True, text=True
    )
    assert result.returncode == exit_code, result.stderr
    calls = trace(env)
    assert calls.count("supabase gen types typescript --local") == 1
    if failure == "generator":
        assert output.read_text() == "unchanged\n"
        assert all(not call.startswith("git ") for call in calls)
    else:
        assert "git diff --exit-code packages/types/src/db.ts" in calls


def assert_qualifying_steps_blocking(job: dict[str, Any]) -> None:
    assert "if" not in job
    assert "continue-on-error" not in job
    steps = job["steps"]
    positions = []
    for name in QUALIFYING_STEPS:
        matches = [step for step in steps if step.get("name") == name]
        assert len(matches) == 1
        step = matches[0]
        assert "if" not in step
        assert "continue-on-error" not in step
        positions.append(steps.index(step))
    assert positions == sorted(positions)


def test_workflow_keeps_the_qualified_stack_and_comparison_blocking() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    match = re.search(r"(?ms)^  db:\n.*?(?=^  [a-z0-9-]+:\n|\Z)", workflow)
    assert match is not None
    db = match.group(0)
    positions = [db.index(name) for name in QUALIFYING_STEPS]
    assert positions == sorted(positions)
    assert "version: 2.109.1" in db
    assert "run: bash scripts/ci/preload-typegen-meta.sh" in db
    assert "run: bash scripts/gen-types.sh" in db
    assert "run: git diff --exit-code packages/types/src/db.ts" in db
    assert "continue-on-error:" not in db
    # Artifact steps legitimately run conditionally after a drift failure;
    # each authoritative setup/reset/generation/comparison step stays blocking.
    assert_qualifying_steps_blocking(yaml.safe_load(workflow)["jobs"]["db"])
    assert "|| true" not in db
    assert "SUPABASE_INTERNAL_IMAGE_REGISTRY" not in db
    assert "permissions:" not in db
    permissions = re.search(r"(?ms)^permissions:\n.*?(?=^\S|\Z)", workflow)
    assert permissions is not None
    assert permissions.group(0).strip() == "permissions:\n  contents: read\n  pull-requests: read"


@pytest.mark.parametrize("name", QUALIFYING_STEPS)
@pytest.mark.parametrize("field,value", [("if", "success()"), ("continue-on-error", True)])
def test_conditional_or_waived_qualifying_step_is_rejected(
    name: str, field: str, value: str | bool
) -> None:
    job = deepcopy(yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]["db"])
    next(step for step in job["steps"] if step.get("name") == name)[field] = value
    with pytest.raises(AssertionError):
        assert_qualifying_steps_blocking(job)


@pytest.mark.parametrize("field,value", [("if", "success()"), ("continue-on-error", True)])
def test_conditional_or_waived_typegen_job_is_rejected(field: str, value: str | bool) -> None:
    job = deepcopy(yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]["db"])
    job[field] = value
    with pytest.raises(AssertionError):
        assert_qualifying_steps_blocking(job)
