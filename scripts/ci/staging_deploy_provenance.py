#!/usr/bin/env python3
"""Certifiable deploy-staging run and staging-sha-proof handling (RELCTRL-04)."""

from __future__ import annotations

from typing import Any

from github_actions_provenance import (
    DEPLOY_STAGING_WORKFLOW,
    RELEASE_CERTIFY_WORKFLOW,
    GitHubActionsClient,
    download_named_artifact_json,
)
from validate_staging_proof import ProofValidationError, validate_staging_proof

STAGING_BRANCH = "staging"
STAGING_SUPABASE_PROJECT_REF = "iyasmrmbcrvlfxpzescb"
STAGING_SHA_PROOF_ARTIFACT = "staging-sha-proof"
STAGING_SHA_PROOF_FILENAME = "staging-sha-proof.json"


class StagingDeployProvenanceError(ValueError):
    """Raised when deploy or staging-sha-proof provenance fails certification checks."""


def verify_certifiable_deploy_run(
    run: dict[str, Any],
    *,
    candidate_sha: str,
) -> None:
    if str(run.get("status")) != "completed":
        raise StagingDeployProvenanceError("deploy-staging run is not completed")
    if str(run.get("conclusion")) != "success":
        raise StagingDeployProvenanceError(
            f"deploy-staging run did not succeed (conclusion={run.get('conclusion')!r})"
        )
    if str(run.get("path") or "") != DEPLOY_STAGING_WORKFLOW:
        raise StagingDeployProvenanceError("deploy-staging workflow path mismatch")
    if str(run.get("event") or "") != "push":
        raise StagingDeployProvenanceError(
            f"deploy-staging event={run.get('event')!r} is not certifiable (want push)"
        )
    if str(run.get("head_branch") or "") != STAGING_BRANCH:
        raise StagingDeployProvenanceError(
            f"deploy-staging head_branch={run.get('head_branch')!r} want {STAGING_BRANCH!r}"
        )
    head_sha = str(run.get("head_sha") or "").lower()
    if head_sha != candidate_sha.lower():
        raise StagingDeployProvenanceError(
            f"deploy-staging head_sha {head_sha[:12]} != candidate {candidate_sha[:12]}"
        )


def verify_certification_run_metadata(
    run: dict[str, Any],
    *,
    candidate_sha: str,
) -> None:
    if str(run.get("status")) != "completed":
        raise StagingDeployProvenanceError("release-certify run is not completed")
    if str(run.get("conclusion")) != "success":
        raise StagingDeployProvenanceError(
            f"release-certify run did not succeed (conclusion={run.get('conclusion')!r})"
        )
    if str(run.get("path") or "") != RELEASE_CERTIFY_WORKFLOW:
        raise StagingDeployProvenanceError("release-certify workflow path mismatch")
    if str(run.get("event") or "") != "workflow_dispatch":
        raise StagingDeployProvenanceError(
            f"release-certify event={run.get('event')!r} want workflow_dispatch"
        )
    if str(run.get("head_branch") or "") != STAGING_BRANCH:
        raise StagingDeployProvenanceError(
            f"release-certify head_branch={run.get('head_branch')!r} want {STAGING_BRANCH!r}"
        )
    head_sha = str(run.get("head_sha") or "").lower()
    if head_sha != candidate_sha.lower():
        raise StagingDeployProvenanceError(
            f"release-certify head_sha {head_sha[:12]} != candidate {candidate_sha[:12]}"
        )


def discover_certifiable_deploy_run(
    client: GitHubActionsClient,
    *,
    candidate_sha: str,
) -> dict[str, Any]:
    runs = client.get_workflow_runs(
        workflow_path=DEPLOY_STAGING_WORKFLOW,
        head_sha=candidate_sha,
        status="completed",
        per_page=20,
    )
    for run in runs:
        try:
            verify_certifiable_deploy_run(run, candidate_sha=candidate_sha)
        except StagingDeployProvenanceError:
            continue
        return run
    raise StagingDeployProvenanceError(
        "no certifiable deploy-staging push run found for candidate "
        f"{candidate_sha[:12]} on branch {STAGING_BRANCH}"
    )


def download_staging_sha_proof(
    client: GitHubActionsClient,
    *,
    deploy_run_id: str,
) -> dict[str, Any]:
    return download_named_artifact_json(
        client,
        run_id=deploy_run_id,
        artifact_name=STAGING_SHA_PROOF_ARTIFACT,
        filename=STAGING_SHA_PROOF_FILENAME,
        label="staging-sha-proof",
    )


def validate_staging_sha_proof_for_certification(
    proof: dict[str, Any],
    *,
    candidate_sha: str,
) -> dict[str, str]:
    """Validate staging-sha-proof and return derived certification fields."""
    if not isinstance(proof, dict):
        raise StagingDeployProvenanceError("staging-sha-proof must be a JSON object")

    proof_candidate = str(proof.get("candidate_sha") or "").lower()
    if proof_candidate != candidate_sha.lower():
        raise StagingDeployProvenanceError(
            f"staging-sha-proof candidate_sha={proof_candidate[:12]} "
            f"!= candidate {candidate_sha[:12]}"
        )

    previews_raw = proof.get("previews")
    if not isinstance(previews_raw, dict):
        raise StagingDeployProvenanceError("staging-sha-proof previews object is required")

    fingerprint_raw = proof.get("api_fingerprint")
    if not isinstance(fingerprint_raw, dict):
        raise StagingDeployProvenanceError("staging-sha-proof api_fingerprint is required")

    migrate_result = str(proof.get("migrate_supabase_result") or "")
    project_ref = str(fingerprint_raw.get("supabase_project_ref") or "")
    if project_ref != STAGING_SUPABASE_PROJECT_REF:
        raise StagingDeployProvenanceError(
            "staging-sha-proof supabase_project_ref "
            f"{project_ref!r} != {STAGING_SUPABASE_PROJECT_REF!r}"
        )

    previews: dict[str, dict[str, Any]] = {}
    for portal, row in previews_raw.items():
        if isinstance(row, dict):
            previews[str(portal)] = row

    try:
        validate_staging_proof(
            candidate_sha=candidate_sha,
            previews=previews,
            fingerprint=fingerprint_raw,
            staging_supabase_project_id=STAGING_SUPABASE_PROJECT_REF,
            migrate_result=migrate_result,
            expected_image_tag=candidate_sha,
            require_migrate_success=True,
        )
    except ProofValidationError as exc:
        raise StagingDeployProvenanceError(str(exc)) from exc

    api_sha = str(fingerprint_raw.get("git_sha") or "").lower()
    for portal in ("customer", "vendor", "admin"):
        portal_sha = str(previews[portal].get("github_commit_sha") or "").lower()
        if portal_sha != candidate_sha.lower():
            raise StagingDeployProvenanceError(
                f"{portal} preview SHA {portal_sha[:12]} != candidate {candidate_sha[:12]}"
            )

    return {
        "candidate_sha": candidate_sha.lower(),
        "staging_branch_sha": candidate_sha.lower(),
        "staging_frontend_sha": candidate_sha.lower(),
        "staging_api_sha": api_sha,
        "staging_supabase_project_ref": STAGING_SUPABASE_PROJECT_REF,
    }


def cross_check_certification_evidence_with_proof(
    evidence: dict[str, Any],
    *,
    derived: dict[str, str],
) -> None:
    for field in (
        "candidate_sha",
        "staging_branch_sha",
        "staging_frontend_sha",
        "staging_api_sha",
    ):
        got = str(evidence.get(field) or "").lower()
        want = str(derived.get(field) or "").lower()
        if got != want:
            raise StagingDeployProvenanceError(
                f"certification evidence {field}={got!r} != staging-sha-proof derived {want!r}"
            )

    got_ref = str(evidence.get("staging_supabase_project_ref") or "")
    want_ref = str(derived.get("staging_supabase_project_ref") or "")
    if got_ref != want_ref:
        raise StagingDeployProvenanceError(
            "certification evidence staging_supabase_project_ref="
            f"{got_ref!r} != staging-sha-proof derived {want_ref!r}"
        )
