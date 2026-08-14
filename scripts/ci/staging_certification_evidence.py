#!/usr/bin/env python3
"""Schema and validation for staging certification evidence artifacts (RELCTRL-03/04)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
RUN_ID_RE = re.compile(r"^\d+$")

SCHEMA_VERSION = "4"
ARTIFACT_FILENAME = "staging-certification-evidence.json"
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
        "BASELINE_FAILING",
        "BLOCKED_EXTERNAL",
        "INCOMPLETE_REQUIRED_GATES",
        "LOCAL_DEVELOPMENT_REPORT",
        "pass",
        "success",
        "SUCCESS",
    }
)


class StagingCertificationError(ValueError):
    """Raised when staging certification evidence fails validation."""


def _require_sha(value: str, label: str) -> str:
    value = (value or "").strip().lower()
    if not SHA_RE.match(value):
        raise StagingCertificationError(f"{label} must be a 40-char git SHA, got {value!r}")
    return value


def _require_run_id(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not RUN_ID_RE.match(text):
        raise StagingCertificationError(
            f"{label} must be a numeric workflow run id, got {text!r}"
        )
    return text


def _require_iso8601(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise StagingCertificationError(f"{label} is required")
    normalized = text.replace("Z", "+00:00")
    try:
        datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise StagingCertificationError(f"{label} must be ISO-8601 timestamp") from exc
    return text


def validate_staging_certification_evidence(
    evidence: dict[str, Any],
    *,
    candidate_sha: str,
    certification_run_id: str | None = None,
    current_run_id: str | None = None,
) -> None:
    candidate = _require_sha(candidate_sha, "candidate_sha")

    if str(evidence.get("schema_version")) != SCHEMA_VERSION:
        raise StagingCertificationError(f"schema_version must be {SCHEMA_VERSION!r}")

    if str(evidence.get("mode", "")).strip() != "integrated-staging":
        raise StagingCertificationError("mode must be integrated-staging")

    result = str(evidence.get("result", "")).strip()
    if result in CERT_REJECT:
        raise StagingCertificationError(f"result={result!r} is not completed PASS certification")
    if result != CERT_PASS:
        raise StagingCertificationError(f"result must be exactly {CERT_PASS!r}, got {result!r}")

    head = _require_sha(str(evidence.get("candidate_sha", "")), "candidate_sha")
    if head != candidate:
        raise StagingCertificationError(
            f"artifact candidate_sha={head[:12]} != PR head={candidate[:12]}"
        )

    for field in (
        "staging_branch_sha",
        "staging_frontend_sha",
        "staging_api_sha",
    ):
        value = _require_sha(str(evidence.get(field, "")), field)
        if value != candidate:
            raise StagingCertificationError(f"{field} must match candidate SHA exactly")

    project_ref = str(evidence.get("staging_supabase_project_ref") or "").strip()
    if not project_ref:
        raise StagingCertificationError("staging_supabase_project_ref is required")

    deploy_run_id = _require_run_id(
        evidence.get("staging_deploy_workflow_run_id"),
        "staging_deploy_workflow_run_id",
    )
    cert_run_id = _require_run_id(
        evidence.get("certification_workflow_run_id"),
        "certification_workflow_run_id",
    )
    if deploy_run_id == cert_run_id:
        raise StagingCertificationError(
            "staging deploy run id must differ from certification workflow run id"
        )

    if certification_run_id and cert_run_id != str(certification_run_id).strip():
        raise StagingCertificationError(
            "artifact certification_workflow_run_id does not match certification run"
        )

    if current_run_id:
        current = str(current_run_id).strip()
        if current in {deploy_run_id, cert_run_id}:
            raise StagingCertificationError(
                "merge gate CI run id cannot masquerade as staging deploy or certification proof"
            )

    attempt = evidence.get("certification_run_attempt")
    if not isinstance(attempt, int) or attempt < 1:
        raise StagingCertificationError("certification_run_attempt must be a positive integer")

    _require_iso8601(evidence.get("certified_at"), "certified_at")

    source_workflow = str(evidence.get("source_workflow", "")).strip()
    if source_workflow != ".github/workflows/release-certify.yml":
        raise StagingCertificationError(
            "source_workflow must be .github/workflows/release-certify.yml"
        )


def build_staging_certification_evidence(
    *,
    derived: dict[str, str],
    staging_deploy_workflow_run_id: str,
    certification_workflow_run_id: str,
    certification_run_attempt: int,
    certified_at: str,
) -> dict[str, Any]:
    candidate = _require_sha(derived["candidate_sha"], "candidate_sha")
    return {
        "schema_version": SCHEMA_VERSION,
        "result": CERT_PASS,
        "mode": "integrated-staging",
        "candidate_sha": candidate,
        "staging_branch_sha": _require_sha(derived["staging_branch_sha"], "staging_branch_sha"),
        "staging_frontend_sha": _require_sha(
            derived["staging_frontend_sha"], "staging_frontend_sha"
        ),
        "staging_api_sha": _require_sha(derived["staging_api_sha"], "staging_api_sha"),
        "staging_supabase_project_ref": derived["staging_supabase_project_ref"],
        "staging_deploy_workflow_run_id": _require_run_id(
            staging_deploy_workflow_run_id,
            "staging_deploy_workflow_run_id",
        ),
        "certification_workflow_run_id": _require_run_id(
            certification_workflow_run_id,
            "certification_workflow_run_id",
        ),
        "certification_run_attempt": certification_run_attempt,
        "certified_at": _require_iso8601(certified_at, "certified_at"),
        "source_workflow": ".github/workflows/release-certify.yml",
    }
