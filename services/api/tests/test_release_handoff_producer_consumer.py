"""Offline producer-to-consumer compatibility for the release proof artifact."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
from release_handoff_contract import (  # noqa: E402
    API_HOST,
    CUSTOMER_ORIGIN,
    PORTALS,
    REPOSITORY,
    REPOSITORY_ID,
    REQUIRED_JOBS,
    SMOKE_STEPS,
    STAGING_PROJECT,
    WORKFLOW,
    resolve_handoff,
)

SHA = "a" * 40
CONFIGURATION = "rev_fixture"


def iso(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_v2_bundle_flows_from_shell_producer_into_authenticated_resolver(
    tmp_path: Path,
) -> None:
    git_bash = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/bin/bash.exe"
    bash = str(git_bash) if os.name == "nt" and git_bash.is_file() else shutil.which("bash")
    if bash is None:
        pytest.skip("bash is required for the shell producer contract")

    preview_dir = tmp_path / "previews"
    live: dict[str, dict[str, object]] = {}
    project_ids: dict[str, str] = {}
    for portal in PORTALS:
        action = "reused" if portal == "admin" else "created"
        project_id = f"prj_{portal}"
        deployment_id = f"dpl_{portal}"
        project_ids[portal] = project_id
        evidence: dict[str, object] = {
            "candidate_sha": SHA,
            "deployment_sha": SHA,
            "deployment_id": deployment_id,
            "project_id": project_id,
            "target": "preview",
            "health_status": "ok",
            "health_app": portal,
            "health_env": "staging",
            "health_api_host": API_HOST,
            "health_build_id": SHA,
            "preview_url": (f"https://convergeo-{portal}-abc123-vergeo-projects.vercel.app"),
            "configuration_revision": CONFIGURATION,
            "checkpoint_stage": "PRE_PROBE",
            "deployment_action": action,
            "deployment_origin_attempt": 1 if action == "reused" else 2,
            "deployment_create_calls": 0 if action == "reused" else 1,
            "reused_deployments": 1 if action == "reused" else 0,
        }
        if portal == "customer":
            evidence.update(
                stable_hostname_status="verified",
                stable_hostname_url=CUSTOMER_ORIGIN,
            )
        write_json(preview_dir / portal / "evidence.json", evidence)
        live[portal] = {
            "id": deployment_id,
            "projectId": project_id,
            "readyState": "READY",
            "target": None,
            "meta": {
                "githubCommitSha": SHA,
                "convergeoBuildConfigRevision": CONFIGURATION,
                "convergeoRepositoryId": str(REPOSITORY_ID),
                "convergeoSourceRunId": "10",
                "convergeoCreationAttempt": str(evidence["deployment_origin_attempt"]),
            },
            "url": f"convergeo-{portal}-abc123-vergeo-projects.vercel.app",
        }

    fingerprint = tmp_path / "fingerprint.json"
    write_json(
        fingerprint,
        {
            "env": "staging",
            "git_sha": SHA,
            "image_tag": SHA,
            "supabase_project_ref": STAGING_PROJECT,
        },
    )
    proof_path = tmp_path / "staging-sha-proof.json"
    env = dict(os.environ)
    env["PYTHON_BIN"] = sys.executable
    completed = subprocess.run(
        [
            bash,
            str(REPO_ROOT / "scripts" / "ci" / "staging-evidence-bundle.sh"),
            "--candidate-sha",
            SHA,
            "--preview-dir",
            str(preview_dir),
            "--fingerprint",
            str(fingerprint),
            "--staging-supabase-project-id",
            STAGING_PROJECT,
            "--migrate-result",
            "success",
            "--expected-image-tag",
            SHA,
            "--release-envelope",
            "--source-repository",
            REPOSITORY,
            "--source-repository-id",
            str(REPOSITORY_ID),
            "--source-workflow",
            WORKFLOW,
            "--source-ref",
            "refs/heads/staging",
            "--source-run-id",
            "10",
            "--source-run-attempt",
            "2",
            "--configuration-revision",
            CONFIGURATION,
            "--output",
            str(proof_path),
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    assert proof["schema_version"] == 2
    assert proof["deployment_efficiency"] == {
        "create_calls": 2,
        "reused_deployments": 1,
        "portals": {
            "customer": {"action": "created", "origin_attempt": 2},
            "vendor": {"action": "created", "origin_attempt": 2},
            "admin": {"action": "reused", "origin_attempt": 1},
        },
    }

    archive_path = tmp_path / "proof.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(proof_path, "staging-sha-proof.json")
    archive_bytes = archive_path.read_bytes()
    proved_at = datetime.fromisoformat(proof["proved_at"].replace("Z", "+00:00"))
    smoke_started = proved_at - timedelta(seconds=30)
    smoke_completed = proved_at + timedelta(seconds=30)
    jobs = [
        {
            "name": name,
            "run_id": 10,
            "run_attempt": 2,
            "started_at": iso(smoke_started),
            "completed_at": iso(smoke_completed),
            "head_sha": SHA,
            "status": "completed",
            "conclusion": "success",
            "steps": [
                {"name": step, "status": "completed", "conclusion": "success"}
                for step in SMOKE_STEPS
            ]
            if name == "Staging smoke + evidence"
            else [],
        }
        for name in REQUIRED_JOBS
    ]
    handoff = resolve_handoff(
        archive_bytes,
        run={
            "id": 10,
            "run_attempt": 2,
            "head_sha": SHA,
            "head_branch": "staging",
            "path": WORKFLOW,
            "event": "push",
            "status": "completed",
            "conclusion": "success",
            "repository": {"id": REPOSITORY_ID, "full_name": REPOSITORY},
            "head_repository": {"id": REPOSITORY_ID},
            "run_started_at": iso(proved_at - timedelta(minutes=1)),
            "updated_at": iso(proved_at + timedelta(minutes=1)),
        },
        artifact={
            "id": 20,
            "name": "staging-sha-proof-10-attempt-2",
            "expired": False,
            "created_at": iso(proved_at + timedelta(seconds=1)),
            "digest": "sha256:" + hashlib.sha256(archive_bytes).hexdigest(),
            "workflow_run": {
                "id": 10,
                "head_sha": SHA,
                "head_branch": "staging",
                "repository_id": REPOSITORY_ID,
            },
        },
        jobs=jobs,
        live_deployments=live,
        expected_project_ids=project_ids,
        expected_sha=SHA,
        current_staging_sha=SHA,
        expected_run_id=10,
        expected_attempt=2,
        configuration_revision=CONFIGURATION,
        now=proved_at + timedelta(minutes=2),
        max_age_seconds=3600,
    )
    assert handoff.deployment_create_calls == 2
    assert handoff.reused_deployments == 1
    assert handoff.workflow_inputs("full")["source_artifact_id"] == 20
