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
VALID_HEALTH_ENVS = ("staging", "preview")


class ProofValidationError(ValueError):
    """Raised when staging proof inputs fail hard assertions."""


def _require_sha(value: str, label: str) -> None:
    if not SHA_RE.match(value or ""):
        raise ProofValidationError(f"{label} must be a 40-char git SHA, got {value!r}")


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
        raise ProofValidationError(f"fingerprint env={env!r} want staging")

    git_sha = fingerprint.get("git_sha") or ""
    if git_sha != candidate_sha:
        raise ProofValidationError(
            f"fingerprint git_sha={git_sha!r} != candidate_sha={candidate_sha!r}"
        )

    project_ref = fingerprint.get("supabase_project_ref") or ""
    if project_ref == PROD_SUPABASE_PROJECT_REF:
        raise ProofValidationError("fingerprint supabase_project_ref is production")
    if project_ref != staging_supabase_project_id:
        raise ProofValidationError(
            "fingerprint supabase_project_ref "
            f"{project_ref!r} != staging project {staging_supabase_project_id!r}"
        )

    image_tag = fingerprint.get("image_tag") or ""
    if image_tag and image_tag not in {"unknown", ""}:
        want_tag = expected_image_tag or candidate_sha
        if image_tag != want_tag:
            raise ProofValidationError(
                f"fingerprint image_tag={image_tag!r} != expected {want_tag!r}"
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
            f"{portal} deployment_sha={deployment_sha!r} != candidate_sha={candidate_sha!r}"
        )

    proof_candidate_sha = proof.get("candidate_sha") or ""
    if proof_candidate_sha != candidate_sha:
        raise ProofValidationError(
            f"{portal} evidence candidate_sha={proof_candidate_sha!r} != {candidate_sha!r}"
        )

    target = (proof.get("target") or "").lower()
    if target != "preview":
        raise ProofValidationError(f"{portal} target={target!r} want preview")

    preview_url = proof.get("preview_url") or ""
    if not _valid_deployment_url(preview_url):
        raise ProofValidationError(f"{portal} preview_url invalid: {preview_url!r}")

    health_status = proof.get("health_status") or ""
    if health_status != "ok":
        raise ProofValidationError(f"{portal} health_status={health_status!r} want ok")

    health_app = proof.get("health_app") or ""
    if health_app != portal:
        raise ProofValidationError(f"{portal} health_app={health_app!r} want {portal!r}")

    health_env = proof.get("health_env") or ""
    if health_env not in VALID_HEALTH_ENVS:
        raise ProofValidationError(
            f"{portal} health_env={health_env!r} want one of {VALID_HEALTH_ENVS}"
        )

    health_api_host = str(proof.get("health_api_host") or "").strip().lower()
    if health_api_host != STAGING_API_HOST:
        raise ProofValidationError(
            f"{portal} health_api_host={health_api_host!r} != {STAGING_API_HOST!r}"
        )

    health_build_id = proof.get("health_build_id") or ""
    if health_build_id and health_build_id != candidate_sha:
        raise ProofValidationError(
            f"{portal} health_build_id={health_build_id!r} != candidate_sha={candidate_sha!r} "
            "(absent is accepted — deployment_sha above already proves candidate identity; "
            "present-but-wrong is a staleness signal and is not)"
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
        raise ProofValidationError(f"missing preview evidence for: {', '.join(missing)}")

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
        raise ProofValidationError(f"migrate_supabase_result={migrate_result!r} want success")


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
