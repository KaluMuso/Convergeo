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
    artifact_id: int,
    project_ids: Mapping[str, str],
    now: datetime,
) -> tuple[str, str]:
    """Return the two allowlisted portal origins or a sanitized error code."""
    require(type(run) is dict and type(artifact) is dict, "INVALID_METADATA_SHAPE")
    require(
        type(jobs) in (list, tuple) and all(type(job) is dict for job in jobs),
        "INVALID_METADATA_SHAPE",
    )
    for value in (
        run.get("repository"),
        run.get("head_repository"),
        artifact.get("workflow_run"),
    ):
        require(type(value) is dict, "INVALID_METADATA_SHAPE")
    require(type(project_ids) is dict, "INVALID_METADATA_SHAPE")
    require(isinstance(now, datetime), "INVALID_CURRENT_TIME")
    candidate = full_sha(candidate_sha)
    require(full_sha(current_staging_sha) == candidate, "STAGING_MOVED")
    run_id, attempt, artifact_id = (
        positive_id(run_id),
        positive_id(attempt),
        positive_id(artifact_id),
    )
    require(
        run_id <= 2**53 - 1 and artifact_id <= 2**53 - 1 and attempt <= 100,
        "UNBOUNDED_IDENTIFIER",
    )
    require(
        type(run.get("id")) is int and type(run.get("run_attempt")) is int,
        "INVALID_IDENTIFIER",
    )
    require(
        type(artifact.get("id")) is int and artifact.get("id") == artifact_id,
        "ARTIFACT_ID_MISMATCH",
    )
    require(
        type(artifact.get("size_in_bytes")) is int
        and 0 < artifact["size_in_bytes"] <= 1024 * 1024,
        "INVALID_ARTIFACT_SIZE",
    )
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
    require(isinstance(archive, bytes), "INVALID_PROOF_ARCHIVE")
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
            type(job.get("run_id")) is int and type(job.get("run_attempt")) is int,
            "INVALID_IDENTIFIER",
        )
        require(
            timestamp(run.get("run_started_at"))
            <= timestamp(job.get("started_at"))
            <= timestamp(job.get("completed_at"))
            <= timestamp(run.get("updated_at")),
            "INVALID_DEPLOY_JOB_WINDOW",
        )
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
    require(
        all(isinstance(value, str) for value in project_ids.values())
        and len(set(project_ids.values())) == 3,
        "AMBIGUOUS_PROJECT_IDENTITY",
    )
    deployment_ids: list[str] = []
    for portal in PORTALS:
        row = previews[portal]
        require(type(row) is dict, "INVALID_PORTAL_PROOF")
        require(row.get("health_build_id") == candidate, "PORTAL_HEALTH_SHA_MISMATCH")
        deployment_id = row.get("deployment_id")
        require(
            isinstance(deployment_id, str)
            and re.fullmatch(r"dpl_[A-Za-z0-9]+", deployment_id) is not None,
            "INVALID_DEPLOYMENT_IDENTITY",
        )
        deployment_ids.append(deployment_id)
        # Check every URL, including the admin portal not used by this browser.
        preview_origin(portal, row.get("preview_url"))
        require(
            isinstance(project_ids[portal], str)
            and re.fullmatch(r"prj_[A-Za-z0-9]+", project_ids[portal]) is not None
            and row.get("project_id") == project_ids[portal],
            "VERCEL_PROJECT_MISMATCH",
        )
    require(len(set(deployment_ids)) == 3, "AMBIGUOUS_DEPLOYMENT_IDENTITY")
    fingerprint = proof.get("api_fingerprint")
    require(
        type(fingerprint) is dict and fingerprint.get("image_tag") == candidate,
        "API_IMAGE_SHA_MISMATCH",
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


class PrivateParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise SystemExit("EMAIL_DIAGNOSTIC_ARGUMENTS_REJECTED") from None


def public_identifier(value: Any) -> str:
    return (
        str(value)
        if isinstance(value, (str, int))
        and not isinstance(value, bool)
        and re.fullmatch(r"[1-9][0-9]{0,15}", str(value))
        and int(value) <= 2**53 - 1
        else "UNKNOWN"
    )


def render_email_completion(
    *,
    candidate_sha: Any,
    operation_sha: Any,
    operation_run_id: Any,
    operation_attempt: Any,
    source_run_id: Any,
    source_attempt: Any,
    artifact_id: Any,
    authorize_outcome: Any,
    diagnostic_outcome: Any,
) -> str:
    candidate = (
        candidate_sha
        if isinstance(candidate_sha, str)
        and re.fullmatch(r"[0-9a-f]{40}", candidate_sha)
        else "UNKNOWN"
    )
    operation = (
        operation_sha
        if isinstance(operation_sha, str)
        and re.fullmatch(r"[0-9a-f]{40}", operation_sha)
        else "UNKNOWN"
    )
    states = {"success", "failure", "cancelled", "skipped"}
    authorize = (
        authorize_outcome
        if isinstance(authorize_outcome, str) and authorize_outcome in states
        else "UNKNOWN"
    )
    diagnostic = (
        diagnostic_outcome
        if isinstance(diagnostic_outcome, str) and diagnostic_outcome in states
        else "UNKNOWN"
    )
    return (
        "## Protected staging email diagnostic completion\n\n"
        f"- Candidate: `{candidate}`\n"
        f"- Operation SHA: `{operation}`\n"
        f"- Operation run/attempt: `{public_identifier(operation_run_id)}/{public_identifier(operation_attempt)}`\n"
        f"- Source deployment run/attempt/artifact: `{public_identifier(source_run_id)}/{public_identifier(source_attempt)}/{public_identifier(artifact_id)}`\n"
        f"- Authorization outcome: `{authorize}`\n"
        f"- Diagnostic outcome: `{diagnostic}`\n"
        "- Scope: synthetic customer/vendor password login only\n"
        "- Release eligible: `NO`\n"
        "- Deployments, fixture reset, credential writes and OTP delivery: `NONE`\n"
    )


def main(argv: Sequence[str] | None = None, *, now: datetime | None = None) -> None:
    parser = PrivateParser()
    for flag in (
        "metadata-dir",
        "candidate-sha",
        "run-id",
        "attempt",
        "artifact-id",
        "customer-project-id",
        "vendor-project-id",
        "admin-project-id",
        "github-env",
        "completion-summary",
        "operation-sha",
        "operation-run-id",
        "operation-attempt",
        "authorize-outcome",
        "diagnostic-outcome",
    ):
        parser.add_argument("--" + flag)
    args = parser.parse_args(argv)
    try:
        if args.completion_summary:
            text = render_email_completion(
                candidate_sha=args.candidate_sha,
                operation_sha=args.operation_sha,
                operation_run_id=args.operation_run_id,
                operation_attempt=args.operation_attempt,
                source_run_id=args.run_id,
                source_attempt=args.attempt,
                artifact_id=args.artifact_id,
                authorize_outcome=args.authorize_outcome,
                diagnostic_outcome=args.diagnostic_outcome,
            )
            with Path(args.completion_summary).open("a", encoding="utf-8") as output:
                output.write(text)
            return
        require(
            all(
                (
                    args.metadata_dir,
                    args.candidate_sha,
                    args.run_id,
                    args.attempt,
                    args.artifact_id,
                    args.customer_project_id,
                    args.vendor_project_id,
                    args.admin_project_id,
                    args.github_env,
                )
            ),
            "MISSING_HANDOFF_INPUT",
        )
        directory = Path(args.metadata_dir)
        customer, vendor = resolve_email_handoff(
            (directory / "proof.zip").read_bytes(),
            run=json.loads((directory / "run.json").read_text()),
            artifact=json.loads((directory / "artifact.json").read_text()),
            jobs=json.loads((directory / "jobs.json").read_text()),
            candidate_sha=args.candidate_sha,
            current_staging_sha=(directory / "staging-sha.txt").read_text().strip(),
            run_id=int(args.run_id),
            attempt=int(args.attempt),
            artifact_id=int(args.artifact_id),
            project_ids={
                "customer": args.customer_project_id,
                "vendor": args.vendor_project_id,
                "admin": args.admin_project_id,
            },
            now=now if now is not None else datetime.now(timezone.utc),
        )
        # Derived public values only, one bounded append; no token/password/metadata dump.
        text = (
            f"E2E_BASE_URL={customer}\nE2E_VENDOR_BASE_URL={vendor}\n"
            f"E2E_EXPECT_SHA={args.candidate_sha}\n"
            f"E2E_SOURCE_RUN_ID={int(args.run_id)}\nE2E_SOURCE_RUN_ATTEMPT={int(args.attempt)}\n"
            f"E2E_SOURCE_ARTIFACT_ID={int(args.artifact_id)}\n"
        )
        with Path(args.github_env).open("a", encoding="utf-8") as output:
            output.write(text)
    except (
        ContractError,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        OverflowError,
        RuntimeError,
        NotImplementedError,
    ):
        raise SystemExit("EMAIL_DIAGNOSTIC_HANDOFF_REJECTED") from None


if __name__ == "__main__":
    main()
