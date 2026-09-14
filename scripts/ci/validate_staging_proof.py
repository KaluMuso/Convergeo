#!/usr/bin/env python3
"""Validate staging SHA proof inputs before artifact creation.

Used by staging-evidence-bundle.sh and test-staging-guards.sh. No secrets in
output; callers pass public identifiers only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

PROD_SUPABASE_PROJECT_REF = "dpadrlxukcjbewpqympu"
REQUIRED_PORTALS = ("customer", "vendor", "admin")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
STAGING_API_HOST = "api.staging.vergeo5.com"
STAGING_SUPABASE_PROJECT_REF = "iyasmrmbcrvlfxpzescb"
VALID_HEALTH_ENVS = ("staging", "preview")
RELEASE_PROOF_VERSION = 2
RELEASE_REPOSITORY = "KaluMuso/Convergeo"
RELEASE_REPOSITORY_ID = 1290591718
RELEASE_REF = "refs/heads/staging"
CUSTOMER_STAGING_ORIGIN = "https://customer.staging.vergeo5.com"
CONFIG_REVISION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
OPAQUE_ID_RE = re.compile(r"^(?:dpl|prj)_[A-Za-z0-9]+$")
RELEASE_PROOF_OUTCOMES = (
    "portal_identity_customer",
    "portal_identity_vendor",
    "portal_identity_admin",
    "cors",
    "database_service_role",
    "customer_same_site_cart",
    "api_fingerprint",
    "migrations",
)


class ProofValidationError(ValueError):
    """Raised when staging proof inputs fail hard assertions."""


def _require_sha(value: str, label: str) -> None:
    if not SHA_RE.match(value or ""):
        raise ProofValidationError(f"{label} must be a 40-char git SHA")


def validate_api_fingerprint(
    fingerprint: dict[str, Any],
    *,
    candidate_sha: str,
    staging_supabase_project_id: str,
    expected_image_tag: str | None = None,
) -> None:
    """Assert API /fingerprint matches the candidate staging deployment."""
    _require_sha(candidate_sha, "candidate_sha")
    if not staging_supabase_project_id:
        raise ProofValidationError("staging_supabase_project_id is required")

    env = fingerprint.get("env")
    if env != "staging":
        raise ProofValidationError("fingerprint env must be staging")

    git_sha = fingerprint.get("git_sha") or ""
    if git_sha != candidate_sha:
        raise ProofValidationError("fingerprint git_sha does not match candidate_sha")

    project_ref = fingerprint.get("supabase_project_ref") or ""
    if project_ref == PROD_SUPABASE_PROJECT_REF:
        raise ProofValidationError("fingerprint supabase_project_ref is production")
    if project_ref != staging_supabase_project_id:
        raise ProofValidationError(
            "fingerprint supabase_project_ref does not match staging"
        )

    image_tag = fingerprint.get("image_tag") or ""
    if image_tag and image_tag not in {"unknown", ""}:
        want_tag = expected_image_tag or candidate_sha
        if image_tag != want_tag:
            raise ProofValidationError(
                "fingerprint image_tag does not match expected candidate"
            )


def _valid_deployment_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def validate_portal_proof(
    portal: str,
    proof: dict[str, Any],
    *,
    candidate_sha: str,
) -> None:
    """Assert one Vercel Preview evidence document is consistent.

    The deployed-health proof (vercel_preview_health_verify.py) is the
    primary, blocking release gate; a portal's evidence.json only exists at
    all once that check has already passed inside
    vercel-staging-preview-prove.sh (see PR #666), so these fields here are
    confirmatory, not a second independent gate — but they are still fully
    asserted (not just non-empty-checked), since a stale/hand-edited
    evidence file should not slip through. The Vercel env-API result
    (`env_metadata_status`) is informational only and is never checked here
    — do not reintroduce it as a blocking condition (see
    vercel_preview_env_verify.py's docstring for why Vercel can refuse to
    decrypt a row for reasons entirely outside this repo's control).

    `health_build_id` follows the same opt-in-corroboration policy as
    vercel_preview_health_verify.py: `deployment_sha` above is already the
    blocking candidate-identity proof, so an absent `health_build_id` (a
    project without Vercel's "Automatically expose System Environment
    Variables" enabled) is accepted; present-and-wrong is not.
    """
    _require_sha(candidate_sha, "candidate_sha")

    deployment_sha = proof.get("deployment_sha") or ""
    if deployment_sha != candidate_sha:
        raise ProofValidationError(
            f"{portal} deployment_sha does not match candidate_sha"
        )

    proof_candidate_sha = proof.get("candidate_sha") or ""
    if proof_candidate_sha != candidate_sha:
        raise ProofValidationError(f"{portal} evidence candidate_sha mismatch")

    target = (proof.get("target") or "").lower()
    if target != "preview":
        raise ProofValidationError(f"{portal} target must be preview")

    preview_url = proof.get("preview_url") or ""
    if not _valid_deployment_url(preview_url):
        raise ProofValidationError(f"{portal} preview_url is invalid")

    health_status = proof.get("health_status") or ""
    if health_status != "ok":
        raise ProofValidationError(f"{portal} health_status must be ok")

    health_app = proof.get("health_app") or ""
    if health_app != portal:
        raise ProofValidationError(f"{portal} health_app mismatch")

    health_env = proof.get("health_env") or ""
    if health_env not in VALID_HEALTH_ENVS:
        raise ProofValidationError(f"{portal} health_env is not a staging plane")

    health_api_host = str(proof.get("health_api_host") or "").strip().lower()
    if health_api_host != STAGING_API_HOST:
        raise ProofValidationError(f"{portal} health_api_host mismatch")

    health_build_id = proof.get("health_build_id") or ""
    if health_build_id and health_build_id != candidate_sha:
        raise ProofValidationError(
            f"{portal} health_build_id mismatch "
            "(absent is accepted; present-but-wrong is a staleness signal)"
        )


def validate_staging_proof(
    *,
    candidate_sha: str,
    previews: dict[str, dict[str, Any]],
    fingerprint: dict[str, Any] | None,
    staging_supabase_project_id: str,
    migrate_result: str = "success",
    expected_image_tag: str | None = None,
    require_migrate_success: bool = True,
) -> None:
    """Validate all inputs required for a green staging-sha-proof artifact."""
    _require_sha(candidate_sha, "candidate_sha")

    missing = [p for p in REQUIRED_PORTALS if p not in previews]
    if missing:
        raise ProofValidationError(
            f"missing preview evidence for: {', '.join(missing)}"
        )

    if fingerprint is None:
        raise ProofValidationError("api_fingerprint is required")
    validate_api_fingerprint(
        fingerprint,
        candidate_sha=candidate_sha,
        staging_supabase_project_id=staging_supabase_project_id,
        expected_image_tag=expected_image_tag,
    )

    for portal in REQUIRED_PORTALS:
        validate_portal_proof(portal, previews[portal], candidate_sha=candidate_sha)

    if require_migrate_success and migrate_result != "success":
        raise ProofValidationError("migrate_supabase_result must be success")


def validate_release_envelope(
    proof: dict[str, Any],
    *,
    candidate_sha: str,
    source_run_id: int,
    source_run_attempt: int,
    source_workflow: str,
    configuration_revision: str,
) -> None:
    """Validate the stronger v2 manifest-to-E2E release handoff contract.

    The ordinary staging validator remains compatible with diagnostic/legacy
    evidence. This release envelope is deliberately stricter: all required
    proof outcomes must have executed successfully, health must corroborate
    the full SHA, and the producer/configuration identity must be explicit.
    Authenticated run/artifact metadata and live Vercel metadata are checked by
    release_handoff_contract.py in addition to these manifest assertions.
    """
    _require_sha(candidate_sha, "candidate_sha")
    if proof.get("schema_version") != RELEASE_PROOF_VERSION:
        raise ProofValidationError("release proof schema_version mismatch")
    if type(source_run_id) is not int or source_run_id <= 0:
        raise ProofValidationError("source_run_id must be a positive integer")
    if type(source_run_attempt) is not int or source_run_attempt <= 0:
        raise ProofValidationError("source_run_attempt must be a positive integer")
    if not CONFIG_REVISION_RE.fullmatch(configuration_revision):
        raise ProofValidationError("configuration_revision is invalid or missing")

    source = proof.get("source")
    if not isinstance(source, dict):
        raise ProofValidationError("release proof source envelope is required")
    expected_source = {
        "repository": RELEASE_REPOSITORY,
        "repository_id": RELEASE_REPOSITORY_ID,
        "workflow": source_workflow,
        "ref": RELEASE_REF,
        "candidate_sha": candidate_sha,
        "run_id": source_run_id,
        "run_attempt": source_run_attempt,
    }
    for field, expected in expected_source.items():
        if source.get(field) != expected:
            raise ProofValidationError(f"release proof source.{field} mismatch")

    configuration = proof.get("configuration")
    if not isinstance(configuration, dict):
        raise ProofValidationError("release proof configuration envelope is required")
    if configuration.get("identity_scheme") != "operator-managed-non-secret-v1":
        raise ProofValidationError(
            "release proof configuration identity scheme mismatch"
        )
    if configuration.get("revision") != configuration_revision:
        raise ProofValidationError("release proof configuration revision mismatch")

    outcomes = proof.get("proof_outcomes")
    if not isinstance(outcomes, dict):
        raise ProofValidationError("release proof outcomes are required")
    if set(outcomes) != set(RELEASE_PROOF_OUTCOMES):
        raise ProofValidationError("release proof outcome set mismatch")
    for proof_id in RELEASE_PROOF_OUTCOMES:
        if outcomes.get(proof_id) != "PASS":
            raise ProofValidationError(f"release proof outcome {proof_id} did not pass")

    previews_raw = proof.get("previews")
    if not isinstance(previews_raw, dict):
        raise ProofValidationError("release proof previews object is required")
    previews: dict[str, dict[str, Any]] = {}
    for portal in REQUIRED_PORTALS:
        row = previews_raw.get(portal)
        if not isinstance(row, dict):
            raise ProofValidationError(f"release proof {portal} preview is required")
        previews[portal] = row
        if row.get("health_build_id") != candidate_sha:
            raise ProofValidationError(
                f"release proof {portal} full health SHA mismatch"
            )
        if not OPAQUE_ID_RE.fullmatch(str(row.get("deployment_id") or "")):
            raise ProofValidationError(
                f"release proof {portal} deployment identity is invalid"
            )
        if not OPAQUE_ID_RE.fullmatch(str(row.get("project_id") or "")):
            raise ProofValidationError(
                f"release proof {portal} project identity is invalid"
            )

    customer = previews["customer"]
    if customer.get("stable_hostname_status") != "verified":
        raise ProofValidationError(
            "release proof Customer stable hostname was not verified"
        )
    if customer.get("stable_hostname_url") != CUSTOMER_STAGING_ORIGIN:
        raise ProofValidationError("release proof Customer same-site origin mismatch")

    fingerprint = proof.get("api_fingerprint")
    if not isinstance(fingerprint, dict):
        raise ProofValidationError("release proof api_fingerprint is required")
    if fingerprint.get("image_tag") != candidate_sha:
        raise ProofValidationError("release proof API image tag mismatch")

    validate_staging_proof(
        candidate_sha=candidate_sha,
        previews=previews,
        fingerprint=fingerprint,
        staging_supabase_project_id=STAGING_SUPABASE_PROJECT_REF,
        migrate_result=str(proof.get("migrate_supabase_result") or ""),
        expected_image_tag=candidate_sha,
        require_migrate_success=True,
    )


def load_json_file(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ProofValidationError(f"{path} must contain a JSON object")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate staging SHA proof inputs")
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--staging-supabase-project-id", required=True)
    parser.add_argument("--preview-dir", type=Path, required=True)
    parser.add_argument("--fingerprint", type=Path)
    parser.add_argument("--migrate-result", default="success")
    parser.add_argument("--expected-image-tag", default="")
    parser.add_argument(
        "--allow-migrate-skipped",
        action="store_true",
        help="Do not require migrate_result=success (workflow_dispatch skip)",
    )
    args = parser.parse_args(argv)

    previews: dict[str, dict[str, Any]] = {}
    for portal in REQUIRED_PORTALS:
        path = args.preview_dir / portal / "evidence.json"
        if not path.is_file():
            print(f"::error::missing preview evidence: {path}", file=sys.stderr)
            return 1
        previews[portal] = load_json_file(path)

    fingerprint: dict[str, Any] | None = None
    if args.fingerprint and args.fingerprint.is_file():
        fingerprint = load_json_file(args.fingerprint)

    try:
        validate_staging_proof(
            candidate_sha=args.candidate_sha,
            previews=previews,
            fingerprint=fingerprint,
            staging_supabase_project_id=args.staging_supabase_project_id,
            migrate_result=args.migrate_result,
            expected_image_tag=args.expected_image_tag or None,
            require_migrate_success=not args.allow_migrate_skipped,
        )
    except ProofValidationError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    print("staging proof validation OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
