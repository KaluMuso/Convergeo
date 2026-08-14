#!/usr/bin/env python3
"""Validate staging certification evidence required before merging to master.

Fail-closed merge gate (RELCTRL-02). Uses offline evidence only — no Production
DB credentials. CI must VERIFY evidence; it must never rewrite or manufacture it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
RUN_ID_RE = re.compile(r"^\d+$")

CERT_PASS = "PASS"
CERT_REJECT = frozenset(
    {
        "CERTIFIABLE_AFTER_INTEGRATION",
        "PENDING",
        "PLANNED",
        "READY_TO_TEST",
        "BLOCKED",
        "SKIPPED",
        "UNKNOWN",
        "pass",
        "success",
        "SUCCESS",
    }
)

DEFAULT_EVIDENCE = Path("infra/merge-release-evidence.json")
SCHEMA_VERSION = "2"


class MergeEvidenceError(ValueError):
    """Raised when merge release evidence fails validation."""


def _require_sha(value: str, label: str) -> str:
    value = (value or "").strip().lower()
    if not SHA_RE.match(value):
        raise MergeEvidenceError(f"{label} must be a 40-char git SHA, got {value!r}")
    return value


def _require_run_id(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not RUN_ID_RE.match(text):
        raise MergeEvidenceError(f"{label} must be a numeric workflow run id, got {text!r}")
    return text


def load_evidence(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise MergeEvidenceError(f"merge evidence not found: {path}")
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise MergeEvidenceError(f"{path} must contain a JSON object")
    return data


def _verify_github_run(
    *,
    repository: str,
    run_id: str,
    expected_workflow: str,
    token: str,
) -> None:
    owner, repo = repository.split("/", 1)
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        raise MergeEvidenceError(
            f"GitHub run provenance lookup failed for run_id={run_id}: HTTP {exc.code}"
        ) from exc
    except urllib.error.URLError as exc:
        raise MergeEvidenceError(
            f"GitHub run provenance lookup failed for run_id={run_id}: {exc.reason}"
        ) from exc

    if str(payload.get("status")) != "completed":
        raise MergeEvidenceError(f"GitHub run {run_id} is not completed")
    if str(payload.get("conclusion")) != "success":
        raise MergeEvidenceError(f"GitHub run {run_id} did not succeed")

    workflow_path = str(payload.get("path") or "").strip()
    workflow_name = str(payload.get("name") or "").strip()
    if expected_workflow not in {workflow_path, workflow_name} and not workflow_path.endswith(
        expected_workflow
    ):
        raise MergeEvidenceError(
            "provenance.source_workflow "
            f"{expected_workflow!r} does not match GitHub run {run_id} "
            f"(path={workflow_path!r}, name={workflow_name!r})"
        )


def validate_merge_release_evidence(
    evidence: dict[str, Any],
    *,
    candidate_sha: str,
    current_run_id: str | None = None,
    verify_github_provenance: bool = True,
    github_repository: str | None = None,
    github_token: str | None = None,
) -> None:
    candidate = _require_sha(candidate_sha, "candidate_sha")

    if str(evidence.get("schema_version")) != SCHEMA_VERSION:
        raise MergeEvidenceError(f"schema_version must be {SCHEMA_VERSION!r}")

    head = _require_sha(str(evidence.get("candidate_sha", "")), "candidate_sha")
    if head != candidate:
        raise MergeEvidenceError(
            f"evidence candidate_sha={head[:12]} != PR head={candidate[:12]}"
        )

    staging = evidence.get("staging_certification")
    if not isinstance(staging, dict):
        raise MergeEvidenceError("staging_certification object is required")

    result = str(staging.get("result", "")).strip()
    if result in CERT_REJECT:
        raise MergeEvidenceError(
            f"staging_certification.result={result!r} is not an completed PASS certification"
        )
    if result != CERT_PASS:
        raise MergeEvidenceError(
            f"staging_certification.result must be exactly {CERT_PASS!r}, got {result!r}"
        )

    staging_sha = _require_sha(
        str(staging.get("candidate_sha", "")), "staging_certification.candidate_sha"
    )
    staging_frontend = _require_sha(
        str(staging.get("staging_frontend_sha", "")), "staging_certification.staging_frontend_sha"
    )
    staging_api = _require_sha(
        str(staging.get("staging_api_sha", "")), "staging_certification.staging_api_sha"
    )
    if staging_sha != candidate or staging_frontend != candidate or staging_api != candidate:
        raise MergeEvidenceError("staging certification SHAs must match PR head exactly")

    branch_sha_raw = staging.get("staging_branch_sha")
    if branch_sha_raw not in (None, ""):
        branch_sha = _require_sha(str(branch_sha_raw), "staging_certification.staging_branch_sha")
        if branch_sha != candidate:
            raise MergeEvidenceError("staging_certification.staging_branch_sha must match PR head")

    if not staging.get("certified_at"):
        raise MergeEvidenceError("staging_certification.certified_at is required")
    if not staging.get("certification_completed_at"):
        raise MergeEvidenceError("staging_certification.certification_completed_at is required")

    deploy_run_id = _require_run_id(
        staging.get("staging_deploy_workflow_run_id"),
        "staging_certification.staging_deploy_workflow_run_id",
    )
    cert_run_id = _require_run_id(
        staging.get("evidence_run_id"),
        "staging_certification.evidence_run_id",
    )
    if deploy_run_id == cert_run_id:
        raise MergeEvidenceError(
            "staging deploy run id must differ from certification evidence run id"
        )

    if current_run_id:
        current = str(current_run_id).strip()
        if current in {deploy_run_id, cert_run_id}:
            raise MergeEvidenceError(
                "merge gate CI run id cannot masquerade as staging deploy or certification evidence"
            )

    provenance = evidence.get("provenance")
    if not isinstance(provenance, dict):
        raise MergeEvidenceError("provenance object is required")

    source_workflow = str(provenance.get("source_workflow", "")).strip()
    if not source_workflow:
        raise MergeEvidenceError("provenance.source_workflow is required")

    source_run_id = _require_run_id(provenance.get("source_run_id"), "provenance.source_run_id")
    if source_run_id != cert_run_id:
        raise MergeEvidenceError(
            "provenance.source_run_id must equal staging_certification.evidence_run_id"
        )

    attempt = provenance.get("source_run_attempt")
    if not isinstance(attempt, int) or attempt < 1:
        raise MergeEvidenceError("provenance.source_run_attempt must be a positive integer")

    artifact_name = str(provenance.get("artifact_name", "")).strip()
    if not artifact_name:
        raise MergeEvidenceError("provenance.artifact_name is required")

    digest = str(provenance.get("artifact_digest_sha256", "")).strip().lower()
    if not DIGEST_RE.match(digest):
        raise MergeEvidenceError("provenance.artifact_digest_sha256 must be a 64-char sha256 hex")

    if verify_github_provenance:
        repository = github_repository or os.environ.get("GITHUB_REPOSITORY", "").strip()
        token = github_token or os.environ.get("GITHUB_TOKEN", "").strip()
        if not repository or not token:
            raise MergeEvidenceError(
                "GitHub provenance verification requires GITHUB_REPOSITORY and GITHUB_TOKEN"
            )
        _verify_github_run(
            repository=repository,
            run_id=cert_run_id,
            expected_workflow=source_workflow,
            token=token,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate merge-to-master staging evidence")
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument(
        "--current-run-id",
        default=os.environ.get("GITHUB_RUN_ID", ""),
        help="Reject evidence whose run ids equal this merge-gate CI run",
    )
    parser.add_argument(
        "--skip-github-provenance",
        action="store_true",
        help="Offline/self-test mode — skip GitHub Actions run lookup",
    )
    args = parser.parse_args(argv)

    try:
        evidence = load_evidence(args.evidence)
        validate_merge_release_evidence(
            evidence,
            candidate_sha=args.candidate_sha,
            current_run_id=args.current_run_id or None,
            verify_github_provenance=not args.skip_github_provenance,
        )
    except MergeEvidenceError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    print(f"merge evidence OK for candidate {args.candidate_sha[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
