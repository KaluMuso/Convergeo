#!/usr/bin/env python3
"""Verify artifact-native staging certification for merge-to-master gate (RELCTRL-03)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from github_actions_provenance import (
    DEPLOY_STAGING_WORKFLOW,
    RELEASE_CERTIFY_WORKFLOW,
    STAGING_CERTIFICATION_ARTIFACT,
    GitHubActionsClient,
    LiveGitHubActionsClient,
    extract_artifact_json,
    verify_completed_success_run,
)
from staging_certification_evidence import (
    ARTIFACT_FILENAME,
    StagingCertificationError,
    validate_staging_certification_evidence,
)


class MergeGateError(ValueError):
    """Raised when merge gate staging certification verification fails."""


class FixtureGitHubActionsClient:
    """Offline GitHub API fixture client for regression tests."""

    def __init__(self, fixture_dir: Path) -> None:
        self.fixture_dir = fixture_dir

    def _load(self, name: str) -> Any:
        path = self.fixture_dir / name
        if not path.is_file():
            raise MergeGateError(f"missing fixture: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def get_workflow_runs(
        self,
        *,
        workflow_path: str,
        head_sha: str | None = None,
        status: str | None = None,
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        _ = per_page
        if workflow_path == RELEASE_CERTIFY_WORKFLOW:
            payload = self._load("certification_runs.json")
        elif workflow_path == DEPLOY_STAGING_WORKFLOW:
            payload = self._load("deploy_runs.json")
        else:
            return []
        runs = payload if isinstance(payload, list) else payload.get("workflow_runs", [])
        filtered: list[dict[str, Any]] = []
        for run in runs:
            if status and str(run.get("status")) != status:
                continue
            if head_sha and str(run.get("head_sha", "")).lower() != head_sha.lower():
                continue
            filtered.append(run)
        return filtered

    def get_run(self, run_id: str) -> dict[str, Any]:
        for name in ("certification_run.json", "deploy_run.json"):
            path = self.fixture_dir / name
            if not path.is_file():
                continue
            payload_obj: Any = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload_obj, dict):
                continue
            payload = payload_obj
            if str(payload.get("id")) == str(run_id):
                return payload
        raise MergeGateError(f"fixture run not found: {run_id}")

    def list_run_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        payload = self._load("artifacts.json")
        artifacts = payload if isinstance(payload, list) else payload.get("artifacts", [])
        return [item for item in artifacts if str(item.get("workflow_run_id")) == str(run_id)]

    def download_artifact_zip(self, artifact_id: int) -> bytes:
        for suffix in (".zip", ".json"):
            path = self.fixture_dir / f"artifact-{artifact_id}{suffix}"
            if path.is_file():
                if suffix == ".json":
                    import io
                    import zipfile

                    buffer = io.BytesIO()
                    with zipfile.ZipFile(buffer, "w") as archive:
                        archive.writestr(ARTIFACT_FILENAME, path.read_text(encoding="utf-8"))
                    return buffer.getvalue()
                return path.read_bytes()
        raise MergeGateError(f"fixture artifact not found: {artifact_id}")


def _integrated_staging_run(run: dict[str, Any]) -> bool:
    inputs = run.get("inputs") or {}
    if isinstance(inputs, dict) and str(inputs.get("mode", "")).strip() == "integrated-staging":
        return True
    # Workflow runs triggered without serialized inputs still carry display title/event.
    display = str(run.get("display_title") or "")
    return "integrated-staging" in display


def discover_certification_run(
    client: GitHubActionsClient,
    *,
    candidate_sha: str,
) -> dict[str, Any]:
    runs = client.get_workflow_runs(
        workflow_path=RELEASE_CERTIFY_WORKFLOW,
        head_sha=candidate_sha,
        status="completed",
        per_page=30,
    )
    for run in runs:
        if str(run.get("conclusion")) != "success":
            continue
        if not _integrated_staging_run(run):
            continue
        try:
            verify_completed_success_run(
                run,
                expected_workflow_path=RELEASE_CERTIFY_WORKFLOW,
                expected_head_sha=candidate_sha,
                label="release-certify",
            )
        except ValueError:
            continue
        return run
    raise MergeGateError(
        "no successful integrated-staging certification run found for candidate "
        f"{candidate_sha[:12]}"
    )


def download_certification_evidence(
    client: GitHubActionsClient,
    *,
    certification_run_id: str,
) -> dict[str, Any]:
    artifacts = client.list_run_artifacts(certification_run_id)
    target = None
    for artifact in artifacts:
        if str(artifact.get("name")) == STAGING_CERTIFICATION_ARTIFACT:
            target = artifact
            break
    if target is None:
        raise MergeGateError(
            f"certification run {certification_run_id} missing artifact "
            f"{STAGING_CERTIFICATION_ARTIFACT!r}"
        )
    if target.get("expired") is True:
        raise MergeGateError(f"certification artifact expired for run {certification_run_id}")
    zip_bytes = client.download_artifact_zip(int(target["id"]))
    return extract_artifact_json(zip_bytes, ARTIFACT_FILENAME)


def verify_staging_certification_gate(
    *,
    candidate_sha: str,
    client: GitHubActionsClient,
    current_run_id: str | None = None,
) -> dict[str, Any]:
    cert_run = discover_certification_run(client, candidate_sha=candidate_sha)
    cert_run_id = str(cert_run["id"])
    evidence = download_certification_evidence(client, certification_run_id=cert_run_id)
    validate_staging_certification_evidence(
        evidence,
        candidate_sha=candidate_sha,
        certification_run_id=cert_run_id,
        current_run_id=current_run_id,
    )

    deploy_run_id = str(evidence["staging_deploy_workflow_run_id"])
    deploy_run = client.get_run(deploy_run_id)
    verify_completed_success_run(
        deploy_run,
        expected_workflow_path=DEPLOY_STAGING_WORKFLOW,
        expected_head_sha=candidate_sha,
        label="deploy-staging",
    )

    if deploy_run_id == cert_run_id:
        raise MergeGateError("deploy-staging and certification runs must differ")

    return evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument(
        "--current-run-id",
        default=os.environ.get("GITHUB_RUN_ID", ""),
        help="Reject evidence whose run ids equal this merge-gate CI run",
    )
    parser.add_argument(
        "--repository",
        default=os.environ.get("GITHUB_REPOSITORY", ""),
    )
    parser.add_argument(
        "--github-token",
        default=os.environ.get("GITHUB_TOKEN", ""),
    )
    parser.add_argument(
        "--artifact-fixture-dir",
        type=Path,
        default=None,
        help="Offline regression mode using fixture API responses",
    )
    parser.add_argument(
        "--artifact-file",
        type=Path,
        default=None,
        help="Offline mode: validate a local artifact JSON without GitHub discovery",
    )
    args = parser.parse_args(argv)

    try:
        if args.artifact_file is not None:
            evidence = json.loads(args.artifact_file.read_text(encoding="utf-8"))
            validate_staging_certification_evidence(
                evidence,
                candidate_sha=args.candidate_sha,
                current_run_id=args.current_run_id or None,
            )
        else:
            client: GitHubActionsClient
            if args.artifact_fixture_dir is not None:
                client = FixtureGitHubActionsClient(args.artifact_fixture_dir)
            else:
                if not args.repository or not args.github_token:
                    raise MergeGateError(
                        "GITHUB_REPOSITORY and GITHUB_TOKEN are required "
                        "for live artifact discovery"
                    )
                client = LiveGitHubActionsClient(
                    repository=args.repository,
                    token=args.github_token,
                )
            evidence = verify_staging_certification_gate(
                candidate_sha=args.candidate_sha,
                client=client,
                current_run_id=args.current_run_id or None,
            )
    except (MergeGateError, StagingCertificationError, ValueError, RuntimeError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    print(
        "staging certification artifact OK for candidate "
        f"{args.candidate_sha[:12]} (cert run {evidence.get('certification_workflow_run_id')})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
