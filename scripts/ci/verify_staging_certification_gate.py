#!/usr/bin/env python3
"""Verify artifact-native staging certification for the merge-to-master gate."""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).resolve().parent))

from github_actions_provenance import (
    RELEASE_CERTIFY_WORKFLOW,
    STAGING_CERTIFICATION_ARTIFACT,
    STAGING_OPERATION_WORKFLOW,
    GitHubActionsClient,
    LiveGitHubActionsClient,
    WorkflowRunsPage,
    extract_artifact_json,
)
from release_handoff_contract import REPOSITORY_ID, ContractError, require, timestamp
from staging_certification_evidence import (
    ARTIFACT_FILENAME,
    StagingCertificationError,
    validate_staging_certification_evidence,
)
from staging_deploy_provenance import (
    StagingDeployProvenanceError,
    cross_check_certification_evidence_with_proof,
    download_staging_sha_proof,
    validate_staging_sha_proof_for_certification,
    verify_certifiable_deploy_run,
    verify_certification_run_metadata,
)
from staging_operation_certification import (
    CERTIFICATION_JOB,
    cross_check_operation_evidence_with_proof,
    operation_certification_artifact_name,
    read_operation_certification_archive,
    read_operation_source,
    require_operation_jobs,
    validate_operation_certification_evidence,
    verify_operation_run,
)


class MergeGateError(ValueError):
    """Raised when merge gate staging certification verification fails."""


class FixtureGitHubActionsClient:
    """Offline GitHub API fixture client for legacy regression tests."""

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
        elif workflow_path.endswith("deploy-staging.yml"):
            payload = self._load("deploy_runs.json")
        elif workflow_path == STAGING_OPERATION_WORKFLOW:
            path = self.fixture_dir / "operation_runs.json"
            if not path.is_file():
                return []
            payload = json.loads(path.read_text(encoding="utf-8"))
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

    def get_workflow_runs_page(
        self,
        *,
        workflow_path: str,
        head_sha: str | None = None,
        status: str | None = None,
        per_page: int = 30,
    ) -> WorkflowRunsPage:
        runs = self.get_workflow_runs(
            workflow_path=workflow_path,
            head_sha=head_sha,
            status=status,
            per_page=per_page,
        )
        return WorkflowRunsPage(runs=runs, total_count=len(runs))

    def get_run(self, run_id: str) -> dict[str, Any]:
        for name in ("certification_run.json", "deploy_run.json", "operation_run.json"):
            path = self.fixture_dir / name
            if not path.is_file():
                continue
            payload_obj: Any = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload_obj, dict) and str(payload_obj.get("id")) == str(run_id):
                return payload_obj
        raise MergeGateError(f"fixture run not found: {run_id}")

    def get_run_attempt(self, run_id: str, attempt: int) -> dict[str, Any]:
        run = self.get_run(run_id)
        if run.get("run_attempt") != attempt:
            raise MergeGateError(f"fixture run attempt not found: {run_id}/{attempt}")
        return run

    def list_run_attempt_jobs(self, run_id: str, attempt: int) -> list[dict[str, Any]]:
        path = self.fixture_dir / f"operation-jobs-{run_id}-attempt-{attempt}.json"
        if not path.is_file():
            return []
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, list):
            raise MergeGateError(f"invalid fixture jobs: {path}")
        return [item for item in value if isinstance(item, dict)]

    def list_run_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        payload = self._load("artifacts.json")
        artifacts = payload if isinstance(payload, list) else payload.get("artifacts", [])
        return [item for item in artifacts if str(item.get("workflow_run_id")) == str(run_id)]

    def download_artifact_zip(self, artifact_id: int) -> bytes:
        for name in (
            f"artifact-{artifact_id}.json",
            f"staging-sha-proof-{artifact_id}.json",
        ):
            path = self.fixture_dir / name
            if not path.is_file():
                continue
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as archive:
                filename = (
                    "staging-sha-proof.json"
                    if "staging-sha-proof" in name
                    else ARTIFACT_FILENAME
                )
                archive.writestr(filename, path.read_text(encoding="utf-8"))
            return buffer.getvalue()
        raise MergeGateError(f"fixture artifact not found: {artifact_id}")


def discover_certification_run(
    client: GitHubActionsClient,
    *,
    candidate_sha: str,
) -> dict[str, Any]:
    """Discover explicitly retained legacy schema-4 certification evidence."""
    runs = client.get_workflow_runs(
        workflow_path=RELEASE_CERTIFY_WORKFLOW,
        head_sha=candidate_sha,
        status="completed",
        per_page=30,
    )
    for run in runs:
        if str(run.get("conclusion")) != "success":
            continue
        try:
            verify_certification_run_metadata(run, candidate_sha=candidate_sha)
            run_id = str(run["id"])
            evidence = download_certification_evidence(client, certification_run_id=run_id)
            validate_staging_certification_evidence(
                evidence,
                candidate_sha=candidate_sha,
                certification_run_id=run_id,
            )
        except (MergeGateError, StagingCertificationError, ValueError):
            continue
        return run
    raise MergeGateError(
        "no successful legacy integrated-staging certification run found for candidate "
        f"{candidate_sha[:12]}"
    )


def download_certification_evidence(
    client: GitHubActionsClient,
    *,
    certification_run_id: str,
) -> dict[str, Any]:
    artifacts = client.list_run_artifacts(certification_run_id)
    matching = [
        artifact
        for artifact in artifacts
        if str(artifact.get("name")) == STAGING_CERTIFICATION_ARTIFACT
    ]
    if len(matching) != 1:
        raise MergeGateError(
            f"certification run {certification_run_id} must contain exactly one "
            f"{STAGING_CERTIFICATION_ARTIFACT!r} artifact"
        )
    target = matching[0]
    if target.get("expired") is True:
        raise MergeGateError(f"certification artifact expired for run {certification_run_id}")
    zip_bytes = client.download_artifact_zip(int(target["id"]))
    return extract_artifact_json(zip_bytes, ARTIFACT_FILENAME)


def _exact_artifact(
    artifacts: list[dict[str, Any]],
    *,
    artifact_id: int | None,
    name: str,
) -> dict[str, Any]:
    matching = [
        artifact
        for artifact in artifacts
        if artifact.get("name") == name
        and (artifact_id is None or artifact.get("id") == artifact_id)
    ]
    require(len(matching) == 1, "MISSING_OR_AMBIGUOUS_ARTIFACT")
    return matching[0]


def _operation_jobs(
    client: GitHubActionsClient,
    *,
    run_id: str,
    attempt: int,
    candidate_sha: str,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for run_attempt in range(1, attempt + 1):
        jobs = client.list_run_attempt_jobs(run_id, run_attempt)
        for raw in jobs:
            result.append(
                {
                    **raw,
                    "run_id": int(run_id),
                    "run_attempt": run_attempt,
                    "head_sha": candidate_sha,
                }
            )
    return result


def _certification_artifact_window(
    artifact: dict[str, Any],
    jobs: list[dict[str, Any]],
    *,
    run_id: int,
    attempt: int,
    candidate_sha: str,
    evidence: dict[str, Any],
) -> None:
    workflow_run = artifact.get("workflow_run")
    require(type(workflow_run) is dict, "ARTIFACT_PROVENANCE_MISMATCH")
    workflow_run = cast(dict[str, Any], workflow_run)
    require(
        workflow_run.get("id") == run_id
        and workflow_run.get("head_sha") == candidate_sha
        and workflow_run.get("head_branch") == "staging"
        and workflow_run.get("repository_id") == REPOSITORY_ID,
        "ARTIFACT_PROVENANCE_MISMATCH",
    )
    matching = [
        job
        for job in jobs
        if job.get("run_attempt") == attempt
        and (
            job.get("name") == CERTIFICATION_JOB
            or str(job.get("name") or "").endswith(f" / {CERTIFICATION_JOB}")
        )
    ]
    require(len(matching) == 1, "MISSING_OR_AMBIGUOUS_OPERATION_JOB")
    started = timestamp(matching[0].get("started_at"))
    completed = timestamp(matching[0].get("completed_at"))
    created = timestamp(artifact.get("created_at"))
    certified = timestamp(evidence.get("certified_at"))
    require(started <= certified <= created <= completed, "CERTIFICATION_ARTIFACT_NOT_BOUND")


OPERATION_RUN_RETRIEVAL_LIMIT = 100


def _operation_run_order_key(run: dict[str, Any]) -> tuple[datetime, datetime, int]:
    raw_run_id = run.get("id")
    require(type(raw_run_id) is int and raw_run_id > 0, "INVALID_OPERATION_RUN_ID")
    run_id = cast(int, raw_run_id)
    return (
        timestamp(run.get("created_at")),
        timestamp(run.get("run_started_at")),
        run_id,
    )


def _verify_operation_candidate(
    client: GitHubActionsClient,
    *,
    candidate_sha: str,
    current_run_id: str | None,
) -> dict[str, Any]:
    page = client.get_workflow_runs_page(
        workflow_path=STAGING_OPERATION_WORKFLOW,
        head_sha=candidate_sha,
        status=None,
        per_page=OPERATION_RUN_RETRIEVAL_LIMIT,
    )
    if not page.complete:
        raise MergeGateError(
            "staging operation run history is incomplete "
            f"({len(page.runs)} of {page.total_count} runs returned)"
        )
    if not page.runs:
        raise MergeGateError(
            "no protected staging operation found for candidate "
            f"{candidate_sha[:12]}"
        )

    try:
        discovered = max(page.runs, key=_operation_run_order_key)
        discovered_id = discovered.get("id")
        require(type(discovered_id) is int, "INVALID_OPERATION_RUN_ID")
        current = client.get_run(str(discovered_id))
        run_id, attempt = verify_operation_run(
            current,
            candidate_sha=candidate_sha,
            expected_run_id=discovered_id,
            require_completed=True,
        )
        run = client.get_run_attempt(str(run_id), attempt)
        verify_operation_run(
            run,
            candidate_sha=candidate_sha,
            expected_run_id=run_id,
            expected_attempt=attempt,
            require_completed=True,
        )
        artifacts = client.list_run_artifacts(str(run_id))
        cert_artifact = _exact_artifact(
            artifacts,
            artifact_id=None,
            name=operation_certification_artifact_name(run_id, attempt),
        )
        evidence = read_operation_certification_archive(
            client.download_artifact_zip(int(cert_artifact["id"])),
            cert_artifact,
            run_id=run_id,
            attempt=attempt,
        )
        validate_operation_certification_evidence(
            evidence,
            candidate_sha=candidate_sha,
            operation_run_id=str(run_id),
            operation_run_attempt=attempt,
            current_run_id=current_run_id,
            now=datetime.now(UTC),
        )
        jobs = _operation_jobs(
            client,
            run_id=str(run_id),
            attempt=attempt,
            candidate_sha=candidate_sha,
        )
        require_operation_jobs(
            jobs,
            run_id=run_id,
            candidate_sha=candidate_sha,
            attempt=attempt,
            completed_consumer=True,
        )
        _certification_artifact_window(
            cert_artifact,
            jobs,
            run_id=run_id,
            attempt=attempt,
            candidate_sha=candidate_sha,
            evidence=evidence,
        )
        source = evidence["source_proof"]
        assert isinstance(source, dict)
        source_artifact = _exact_artifact(
            artifacts,
            artifact_id=int(source["artifact_id"]),
            name=str(source["name"]),
        )
        proof, _, _ = read_operation_source(
            archive=client.download_artifact_zip(int(source_artifact["id"])),
            run=run,
            artifact=source_artifact,
            jobs=jobs,
            candidate_sha=candidate_sha,
        )
        cross_check_operation_evidence_with_proof(
            evidence,
            proof=proof,
            artifact=source_artifact,
            jobs=jobs,
        )
        return evidence
    except (
        ContractError,
        StagingDeployProvenanceError,
        StagingCertificationError,
        KeyError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        raise MergeGateError(
            "newest protected staging operation rejected for candidate "
            f"{candidate_sha[:12]} ({exc})"
        ) from exc


def _verify_legacy_candidate(
    client: GitHubActionsClient,
    *,
    candidate_sha: str,
    current_run_id: str | None,
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
    verify_certifiable_deploy_run(deploy_run, candidate_sha=candidate_sha)
    if deploy_run_id == cert_run_id:
        raise MergeGateError("deploy-staging and certification runs must differ")
    proof = download_staging_sha_proof(client, deploy_run_id=deploy_run_id)
    derived = validate_staging_sha_proof_for_certification(proof, candidate_sha=candidate_sha)
    cross_check_certification_evidence_with_proof(evidence, derived=derived)
    return evidence


def verify_staging_certification_gate(
    *,
    candidate_sha: str,
    client: GitHubActionsClient,
    current_run_id: str | None = None,
) -> dict[str, Any]:
    return _verify_operation_candidate(
        client,
        candidate_sha=candidate_sha,
        current_run_id=current_run_id,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument(
        "--current-run-id",
        default=os.environ.get("GITHUB_RUN_ID", ""),
        help="Reject evidence whose source run id equals this merge-gate CI run",
    )
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--github-token", default=os.environ.get("GITHUB_TOKEN", ""))
    parser.add_argument("--artifact-fixture-dir", type=Path, default=None)
    parser.add_argument(
        "--artifact-file",
        type=Path,
        default=None,
        help="Offline mode: validate local schema-5 operation evidence without discovery",
    )
    args = parser.parse_args(argv)

    try:
        if args.artifact_file is not None:
            evidence = json.loads(args.artifact_file.read_text(encoding="utf-8"))
            validate_operation_certification_evidence(
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
    except (
        ContractError,
        MergeGateError,
        StagingCertificationError,
        StagingDeployProvenanceError,
        ValueError,
        RuntimeError,
    ) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    source_run = evidence.get("staging_operation_workflow_run_id") or evidence.get(
        "certification_workflow_run_id"
    )
    print(
        "staging certification artifact OK for candidate "
        f"{args.candidate_sha[:12]} (source run {source_run})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
