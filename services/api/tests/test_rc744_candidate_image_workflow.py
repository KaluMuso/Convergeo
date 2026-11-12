"""Exercise the frozen RC image controls locally without contacting a registry."""

from __future__ import annotations

import hashlib
import itertools
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github/workflows/api-image.yml"
SHA = "ef8dae53a2d7512aea353" + "380b90f8563f9be1082"
TREE = "ed63b38b5c84c62adf091" + "6ea543e896a86f9425b"
REPOSITORY = "KaluMuso/Convergeo"
REF = "refs/heads/wp/integrate-auth-catalog-wave1"


def _parse(raw: str) -> dict[str, Any]:
    return cast(dict[str, Any], yaml.load(raw, Loader=yaml.BaseLoader))


def _job() -> dict[str, Any]:
    return cast(dict[str, Any], _parse(WORKFLOW.read_text())["jobs"]["build-rc744-candidate"])


def _step(name: str) -> dict[str, Any]:
    return next(cast(dict[str, Any], item) for item in _job()["steps"] if item["name"] == name)


def _environment(tmp_path: Path) -> dict[str, str]:
    return {
        "PATH": os.defpath,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_REF": REF,
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_RUN_ID": "12345",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_SHA": "a" * 40,
        "EXPECTED_CONTROL_SHA": "a" * 40,
        "GITHUB_OUTPUT": str(tmp_path / "outputs"),
        "EXPECTED_SHA": SHA,
        "CANDIDATE_SHA": SHA,
        "CANDIDATE_TREE": TREE,
    }


def _run(script: str, tmp_path: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", script], cwd=tmp_path, env=env, capture_output=True, text=True, check=False
    )


def _candidate_environment(checkout_root: Path, tmp_path: Path) -> dict[str, str]:
    checkout = checkout_root / "candidate"
    sha = subprocess.check_output(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True
    ).strip()
    tree = subprocess.check_output(
        ["git", "-C", str(checkout), "rev-parse", "HEAD^{tree}"], text=True
    ).strip()
    return _environment(tmp_path) | {
        "EXPECTED_SHA": sha,
        "CANDIDATE_SHA": sha,
        "CANDIDATE_TREE": tree,
    }


@pytest.fixture(scope="module")
def candidate_checkout(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("rc744-image")
    checkout = path / "candidate"
    checkout.mkdir()
    env = _environment(path)
    for args in (
        ["init"],
        ["config", "user.name", "Local test"],
        ["config", "user.email", "test@example.invalid"],
    ):
        subprocess.run(
            ["git", "-C", str(checkout), *args], env=env, check=True, capture_output=True
        )
    # Real local Git objects keep these failure-path tests independent of CI's shallow history.
    for content in ("previous source\n", "frozen fixture source\n"):
        (checkout / "source.txt").write_text(content)
        for args in (["add", "source.txt"], ["commit", "-m", "Local fixture"]):
            subprocess.run(
                ["git", "-C", str(checkout), *args], env=env, check=True, capture_output=True
            )
    return path


def test_existing_workflow_jobs_and_dispatch_registration_are_unchanged() -> None:
    current = _parse(WORKFLOW.read_text())
    new_job = current["jobs"].pop("build-rc744-candidate")
    control_input = current["on"]["workflow_dispatch"]["inputs"].pop("expected_control_sha")
    assert control_input == {
        "description": "Reviewed workflow commit SHA for the RC744 candidate image job",
        "required": "false",
        "type": "string",
    }
    # SHA256 of normalized workflow at the frozen application commit; no history fetch needed.
    original_hash = "41d422b6a3c547be1f12a39351694770c3de4180d3312fb4ab6ac8feb30c3627"
    assert hashlib.sha256(json.dumps(current, sort_keys=True).encode()).hexdigest() == original_hash
    assert "workflow_dispatch" in current["on"]
    assert new_job["permissions"] == {"contents": "read", "packages": "write"}
    assert "environment" not in new_job
    assert new_job["env"] == {"CANDIDATE_SHA": SHA, "CANDIDATE_TREE": TREE}


@pytest.mark.parametrize(
    ("event", "ref", "repository"),
    list(
        itertools.product(
            ["workflow_dispatch", "push"],
            [REF, "refs/heads/master"],
            [REPOSITORY, "Another/Convergeo"],
        )
    ),
)
def test_job_selection_accepts_only_the_named_manual_branch_operation(
    event: str, ref: str, repository: str
) -> None:
    values = {"event_name": event, "ref": ref, "repository": repository}
    terms = _job()["if"].split("&&")
    allowed = True
    keys = []
    for term in terms:
        match = re.fullmatch(r"\s*github\.(event_name|ref|repository)\s*==\s*'([^']+)'\s*", term)
        assert match is not None
        key, expected = match.groups()
        keys.append(key)
        allowed = allowed and values[key] == expected
    assert set(keys) == set(values)
    assert allowed == (event == "workflow_dispatch" and ref == REF and repository == REPOSITORY)


@pytest.mark.parametrize(
    "changes",
    [
        {},
        {"EXPECTED_SHA": ""},
        {"EXPECTED_SHA": "0" * 40},
        {"EXPECTED_CONTROL_SHA": ""},
        {"EXPECTED_CONTROL_SHA": "a" * 12},
        {"EXPECTED_CONTROL_SHA": "0" * 40},
        {"GITHUB_REF": "refs/heads/master"},
        {"GITHUB_REPOSITORY": "Another/Convergeo"},
        {"GITHUB_EVENT_NAME": "push"},
        {"CANDIDATE_TREE": "0" * 40},
        {"GITHUB_RUN_ID": "../existing"},
        {"GITHUB_RUN_ATTEMPT": "0"},
    ],
)
def test_source_gate_uses_real_frozen_git_objects_and_fails_before_a_tag_is_emitted(
    candidate_checkout: Path, tmp_path: Path, changes: dict[str, str]
) -> None:
    env = _candidate_environment(candidate_checkout, tmp_path) | changes
    result = _run(_step("Bind candidate source and unique tag")["run"], candidate_checkout, env)
    outputs = Path(env["GITHUB_OUTPUT"])
    if changes:
        assert result.returncode != 0
        assert not outputs.exists()
    else:
        assert result.returncode == 0, result.stderr
        assert (
            outputs.read_text()
            == f"tag=ghcr.io/kalumuso/convergeo-api:rc744-{env['CANDIDATE_SHA']}-12345-1\n"
        )


def test_changed_checkout_is_rejected(candidate_checkout: Path, tmp_path: Path) -> None:
    checkout = candidate_checkout / "candidate"
    env = _candidate_environment(candidate_checkout, tmp_path)
    subprocess.run(
        ["git", "-C", str(checkout), "checkout", "--detach", f"{env['CANDIDATE_SHA']}^"],
        check=True,
        capture_output=True,
    )
    try:
        result = _run(_step("Bind candidate source and unique tag")["run"], candidate_checkout, env)
        assert result.returncode != 0
        assert not Path(env["GITHUB_OUTPUT"]).exists()
    finally:
        subprocess.run(
            ["git", "-C", str(checkout), "checkout", "--detach", env["CANDIDATE_SHA"]],
            check=True,
            capture_output=True,
        )


@pytest.mark.parametrize("attempt", ["1", "2"])
def test_reruns_receive_distinct_tags(
    candidate_checkout: Path, tmp_path: Path, attempt: str
) -> None:
    env = _candidate_environment(candidate_checkout, tmp_path) | {"GITHUB_RUN_ATTEMPT": attempt}
    result = _run(_step("Bind candidate source and unique tag")["run"], candidate_checkout, env)
    assert result.returncode == 0
    assert Path(env["GITHUB_OUTPUT"]).read_text().endswith(f"-12345-{attempt}\n")


@pytest.mark.parametrize("response", ["exists", "absent", "denied", "timeout", "mixed"])
def test_registry_probe_accepts_only_unambiguous_absence(tmp_path: Path, response: str) -> None:
    docker = tmp_path / "docker"
    docker.write_text(
        "#!/bin/bash\n"
        'test "$1 $2 $3" = "buildx imagetools inspect" || exit 99\n'
        'case "$PROBE_RESPONSE" in\n'
        "exists) exit 0;;\n"
        'absent) echo "ERROR: $4: not found" >&2;;\n'
        'denied) echo "ERROR: access denied" >&2;;\n'
        'timeout) echo "ERROR: connection timed out" >&2;;\n'
        'mixed) echo "ERROR: $4: not found" >&2; echo "ERROR: access denied" >&2;;\n'
        "esac\nexit 1\n"
    )
    docker.chmod(0o755)
    env = _environment(tmp_path) | {
        "PATH": f"{tmp_path}:{os.defpath}",
        "PROBE_RESPONSE": response,
        "IMAGE_TAG": f"ghcr.io/kalumuso/convergeo-api:rc744-{SHA}-12345-1",
    }
    result = _run(
        _step("Refuse existing tags and ambiguous registry failures")["run"], tmp_path, env
    )
    assert (result.returncode == 0) == (response == "absent")
    assert "access denied" not in result.stderr


def test_build_context_and_only_credential_are_scoped_to_the_candidate_job() -> None:
    steps = _job()["steps"]
    checkout = _step("Checkout frozen application candidate")
    assert checkout["with"] == {
        "ref": "${{ env.CANDIDATE_SHA }}",
        "path": "candidate",
        "persist-credentials": "false",
    }
    build = _step("Publish only the frozen candidate under its unique RC tag")["with"]
    assert build["context"] == "candidate"
    assert build["file"] == "candidate/infra/api.Dockerfile"
    assert build["tags"] == "${{ steps.source.outputs.tag }}"
    assert build["push"] == "true"
    assert "github.sha" not in build["build-args"]
    assert "GIT_SHA=${{ env.CANDIDATE_SHA }}" in build["build-args"]
    assert "API_IMAGE_TAG=${{ env.CANDIDATE_SHA }}" in build["build-args"]
    secrets = re.findall(r"secrets\.([A-Z_]+)", json.dumps(steps))
    assert secrets == ["GITHUB_TOKEN"]
    assert steps.index(_step("Bind candidate source and unique tag")) < steps.index(
        _step("Log in to GHCR with the job token")
    )
    assert steps.index(_step("Refuse existing tags and ambiguous registry failures")) < steps.index(
        _step("Publish only the frozen candidate under its unique RC tag")
    )


@pytest.mark.parametrize("digest", ["sha256:" + "b" * 64, "", "sha256:123", "latest"])
def test_receipt_binds_source_control_commit_and_digest_without_recording_a_token(
    tmp_path: Path, digest: str
) -> None:
    env = _environment(tmp_path) | {
        "IMAGE_TAG": f"ghcr.io/kalumuso/convergeo-api:rc744-{SHA}-12345-1",
        "IMAGE_DIGEST": digest,
        "WORKFLOW_SHA": "a" * 40,
        "GITHUB_TOKEN": "local-sentinel-do-not-record",
    }
    result = _run(_step("Record public candidate image receipt")["run"], tmp_path, env)
    receipt_file = tmp_path / "candidate-image-receipt.json"
    if len(digest) != 71:
        assert result.returncode != 0
        assert not receipt_file.exists()
        return
    assert result.returncode == 0, result.stderr
    receipt = json.loads(receipt_file.read_text())
    assert receipt == {
        "source_sha": SHA,
        "source_tree": TREE,
        "workflow_sha": "a" * 40,
        "run_id": "12345",
        "run_attempt": "1",
        "tag": env["IMAGE_TAG"],
        "digest": digest,
        "image": "ghcr.io/kalumuso/convergeo-api@" + digest,
    }
    assert env["GITHUB_TOKEN"] not in receipt_file.read_text() + result.stdout + result.stderr
    upload = _step("Upload candidate image receipt")
    assert upload["with"]["path"] == "candidate-image-receipt.json"
    assert upload["with"]["if-no-files-found"] == "error"
