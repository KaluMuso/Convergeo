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
    """Assert one Vercel Preview evidence document is consistent."""
    _require_sha(candidate_sha, "candidate_sha")

    commit_sha = proof.get("github_commit_sha") or proof.get("candidate_sha") or ""
    if commit_sha != candidate_sha:
        raise ProofValidationError(
            f"{portal} github_commit_sha={commit_sha!r} != candidate_sha={candidate_sha!r}"
        )

    target = (proof.get("target") or "").lower()
    if target != "preview":
        raise ProofValidationError(f"{portal} target={target!r} want preview")

    deployment_url = proof.get("deployment_url") or ""
    if not _valid_deployment_url(deployment_url):
        raise ProofValidationError(f"{portal} deployment_url invalid: {deployment_url!r}")

    api_env_verdict = proof.get("api_env_verdict") or ""
    if api_env_verdict == "BLOCKED_EXTERNAL":
        raise ProofValidationError(
            f"{portal} api_env_verdict=BLOCKED_EXTERNAL — staging API env not verified"
        )
    if api_env_verdict != "verified":
        raise ProofValidationError(
            f"{portal} api_env_verdict={api_env_verdict!r} want verified"
        )

    health_verdict = proof.get("health_verdict") or ""
    if portal == "admin":
        if health_verdict not in {"ok", "cf_access_gate"}:
            raise ProofValidationError(
                f"admin health_verdict={health_verdict!r} want ok or cf_access_gate"
            )
        if health_verdict == "cf_access_gate":
            health_http = str(proof.get("health_http") or "")
            if health_http != "403":
                raise ProofValidationError(
                    f"admin cf_access_gate requires health_http=403, got {health_http!r}"
                )
    elif health_verdict != "ok":
        raise ProofValidationError(f"{portal} health_verdict={health_verdict!r} want ok")


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
        raise ProofValidationError(
            f"migrate_supabase_result={migrate_result!r} want success"
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
