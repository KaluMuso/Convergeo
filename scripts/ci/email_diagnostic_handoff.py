#!/usr/bin/env python3
"""Resolve a completed staging deployment for the email-only diagnostic.

This is deliberately an operational handoff, not release certification. The
GitHub adapter supplies authenticated run/job/artifact data and the current
staging ref; this module validates it without printing provider-supplied data.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from release_handoff_contract import (
    ContractError,
    REPOSITORY,
    REPOSITORY_ID,
    STAGING_PROJECT,
    WORKFLOW,
    full_sha,
    positive_id,
    preview_origin,
    read_proof_archive,
    require,
    timestamp,
)
from validate_staging_proof import ProofValidationError, validate_staging_proof

PORTALS = ("customer", "vendor", "admin")
REQUIRED_JOBS = (
    "Environment separation",
    "Supabase migrations + checks",
    "Build API image (SHA tag)",
    "Supabase edge functions (staging)",
    "Deploy API to OCI staging",
    "Vercel Preview proof (customer)",
    "Vercel Preview proof (vendor)",
    "Vercel Preview proof (admin)",
    "Staging smoke + evidence",
)


def resolve_email_handoff(
    archive: bytes,
    *,
    run: Mapping[str, Any],
    artifact: Mapping[str, Any],
    jobs: Sequence[Mapping[str, Any]],
    candidate_sha: str,
    current_staging_sha: str,
    run_id: int,
    attempt: int,
    project_ids: Mapping[str, str],
    now: datetime,
) -> tuple[str, str]:
    """Return the two allowlisted portal origins or a sanitized error code."""
    candidate = full_sha(candidate_sha)
    require(full_sha(current_staging_sha) == candidate, "STAGING_MOVED")
    run_id, attempt = positive_id(run_id), positive_id(attempt)
    require(
        run.get("id") == run_id
        and run.get("run_attempt") == attempt
        and run.get("repository", {}).get("full_name") == REPOSITORY
        and run.get("repository", {}).get("id") == REPOSITORY_ID
        and run.get("head_repository", {}).get("id") == REPOSITORY_ID
        and run.get("head_branch") == "staging"
        and run.get("head_sha") == candidate
        and run.get("path") == WORKFLOW
        and run.get("event") == "workflow_dispatch"
        and run.get("status") == "completed"
        and run.get("conclusion") == "success",
        "UNTRUSTED_DEPLOY_RUN",
    )
    require(
        artifact.get("workflow_run", {}).get("id") == run_id
        and artifact.get("workflow_run", {}).get("head_sha") == candidate
        and artifact.get("workflow_run", {}).get("head_branch") == "staging"
        and artifact.get("workflow_run", {}).get("repository_id") == REPOSITORY_ID
        and artifact.get("workflow_run", {}).get("path") == WORKFLOW,
        "ARTIFACT_PROVENANCE_MISMATCH",
    )
    require(
        now.tzinfo is not None and now.utcoffset() is not None,
        "NAIVE_CURRENT_TIME",
    )
    proof = read_proof_archive(
        archive,
        artifact,
        expected_name=f"staging-sha-proof-{run_id}-attempt-{attempt}",
    )
    require(proof.get("candidate_sha") == candidate, "PROOF_SHA_MISMATCH")
    proved_at = timestamp(proof.get("proved_at"))
    require(
        timestamp(run.get("run_started_at"))
        <= proved_at
        <= timestamp(run.get("updated_at"))
        <= now
        and (now - proved_at).total_seconds() <= 86400,
        "STALE_OR_INVALID_PROOF_WINDOW",
    )
    for name in REQUIRED_JOBS:
        matches = [
            job
            for job in jobs
            if job.get("run_attempt") == attempt and job.get("name") == name
        ]
        require(len(matches) == 1, "MISSING_OR_AMBIGUOUS_DEPLOY_JOB")
        job = matches[0]
        require(
            job.get("run_id") == run_id
            and job.get("head_sha") == candidate
            and job.get("status") == "completed"
            and job.get("conclusion") == "success",
            "DEPLOY_JOB_NOT_SUCCESSFUL",
        )
        if name == "Staging smoke + evidence":
            require(
                timestamp(job.get("started_at"))
                <= proved_at
                <= timestamp(job.get("completed_at")),
                "PROOF_OUTSIDE_SMOKE_JOB",
            )
            created = timestamp(artifact.get("created_at"))
            require(
                timestamp(job.get("started_at"))
                <= created
                <= timestamp(job.get("completed_at")),
                "ARTIFACT_OUTSIDE_SMOKE_JOB",
            )
    previews = proof.get("previews")
    require(
        type(previews) is dict and set(previews) == set(PORTALS),
        "INCOMPLETE_PORTAL_SET",
    )
    require(set(project_ids) == set(PORTALS), "INCOMPLETE_PROJECT_IDENTITY")
    for portal in PORTALS:
        row = previews[portal]
        require(type(row) is dict, "INVALID_PORTAL_PROOF")
        require(
            isinstance(project_ids[portal], str)
            and re.fullmatch(r"prj_[A-Za-z0-9]+", project_ids[portal]) is not None
            and row.get("project_id") == project_ids[portal],
            "VERCEL_PROJECT_MISMATCH",
        )
    try:
        validate_staging_proof(
            candidate_sha=candidate,
            previews=previews,
            fingerprint=proof.get("api_fingerprint"),
            staging_supabase_project_id=STAGING_PROJECT,
            migrate_result=proof.get("migrate_supabase_result"),
            expected_image_tag=candidate,
        )
    except ProofValidationError:
        raise ContractError("INVALID_STAGING_PROOF") from None
    return (
        preview_origin("customer", previews["customer"].get("preview_url")),
        preview_origin("vendor", previews["vendor"].get("preview_url")),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata-dir", type=Path, required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--attempt", type=int, required=True)
    parser.add_argument("--customer-project-id", required=True)
    parser.add_argument("--vendor-project-id", required=True)
    parser.add_argument("--admin-project-id", required=True)
    parser.add_argument("--github-env", type=Path, required=True)
    args = parser.parse_args()
    try:
        directory = args.metadata_dir
        customer, vendor = resolve_email_handoff(
            (directory / "proof.zip").read_bytes(),
            run=json.loads((directory / "run.json").read_text()),
            artifact=json.loads((directory / "artifact.json").read_text()),
            jobs=json.loads((directory / "jobs.json").read_text()),
            candidate_sha=args.candidate_sha,
            current_staging_sha=(directory / "staging-sha.txt").read_text().strip(),
            run_id=args.run_id,
            attempt=args.attempt,
            project_ids={
                "customer": args.customer_project_id,
                "vendor": args.vendor_project_id,
                "admin": args.admin_project_id,
            },
            now=datetime.now(timezone.utc),
        )
        with args.github_env.open("a") as output:
            output.write(f"E2E_BASE_URL={customer}\n")
            output.write(f"E2E_VENDOR_BASE_URL={vendor}\n")
            output.write(f"E2E_EXPECT_SHA={args.candidate_sha}\n")
    except (ContractError, OSError, ValueError, TypeError, KeyError):
        raise SystemExit("EMAIL_DIAGNOSTIC_HANDOFF_REJECTED") from None


if __name__ == "__main__":
    main()
