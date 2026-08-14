#!/usr/bin/env python3
"""Emit immutable staging certification evidence for GitHub Actions artifacts."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from github_actions_provenance import (
    DEPLOY_STAGING_WORKFLOW,
    LiveGitHubActionsClient,
    verify_completed_success_run,
)
from staging_certification_evidence import (
    ARTIFACT_FILENAME,
    build_staging_certification_evidence,
)


def discover_deploy_run_id(
    *,
    repository: str,
    token: str,
    candidate_sha: str,
) -> str:
    client = LiveGitHubActionsClient(repository=repository, token=token)
    runs = client.get_workflow_runs(
        workflow_path=DEPLOY_STAGING_WORKFLOW,
        head_sha=candidate_sha,
        status="completed",
        per_page=20,
    )
    for run in runs:
        try:
            verify_completed_success_run(
                run,
                expected_workflow_path=DEPLOY_STAGING_WORKFLOW,
                expected_head_sha=candidate_sha,
                label="deploy-staging",
            )
        except ValueError:
            continue
        return str(run["id"])
    raise RuntimeError(
        f"no successful deploy-staging run found for candidate {candidate_sha[:12]}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--certification-run-id", required=True)
    parser.add_argument("--certification-run-attempt", type=int, required=True)
    parser.add_argument(
        "--staging-deploy-workflow-run-id",
        default="",
        help="Optional explicit deploy-staging run id (otherwise discovered via GitHub API)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("staging-certification-evidence"),
    )
    parser.add_argument(
        "--certified-at",
        default=datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    )
    args = parser.parse_args(argv)

    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    deploy_run_id = args.staging_deploy_workflow_run_id.strip()
    if not deploy_run_id:
        if not repository or not token:
            print(
                "::error::GITHUB_REPOSITORY and GITHUB_TOKEN required "
                "to discover deploy-staging run",
                file=sys.stderr,
            )
            return 1
        try:
            deploy_run_id = discover_deploy_run_id(
                repository=repository,
                token=token,
                candidate_sha=args.candidate_sha,
            )
        except RuntimeError as exc:
            print(f"::error::{exc}", file=sys.stderr)
            return 1

    evidence = build_staging_certification_evidence(
        candidate_sha=args.candidate_sha,
        staging_deploy_workflow_run_id=deploy_run_id,
        certification_workflow_run_id=args.certification_run_id,
        certification_run_attempt=args.certification_run_attempt,
        certified_at=args.certified_at,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.output_dir / ARTIFACT_FILENAME
    out_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
