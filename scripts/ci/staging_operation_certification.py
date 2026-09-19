#!/usr/bin/env python3
"""Strict adapter from a protected staging operation to certification evidence."""

from __future__ import annotations

import hashlib
import io
import json
import re
import stat
import zipfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from release_handoff_contract import (
    ORCHESTRATION_WORKFLOW,
    PORTALS,
    REPOSITORY,
    REPOSITORY_ID,
    REQUIRED_JOBS,
    ContractError,
    full_sha,
    positive_id,
    read_proof_archive,
    require,
    require_executed_jobs,
    timestamp,
)
from staging_deploy_provenance import (
    cross_check_certification_evidence_with_proof,
    validate_staging_sha_proof_for_certification,
)
from validate_staging_proof import ProofValidationError, validate_release_envelope

OPERATION_SCHEMA_VERSION = "5"
OPERATION_CERTIFICATION_FILENAME = "staging-certification-evidence.json"
OPERATION_CERTIFICATION_PREFIX = "staging-certification-evidence"
OPERATION_MAX_AGE_SECONDS = 24 * 60 * 60
MAX_ARTIFACT_BYTES = 1024 * 1024

E2E_JOB = "Playwright critical paths (Fast-3G · 360px)"
HANDOFF_JOB = "Resolve authenticated release handoff"
CERTIFICATION_JOB = "Certify completed full staging operation"
COMPLETION_JOB = "One sanitized operation completion"

E2E_STEPS = (
    "Guard trusted staging operation entry",
    "Recheck staging ref immediately before protected mutation",
    "Guard — strict certification must run the full matrix",
    "Probe staging customer (identity + protection)",
    "Probe staging vendor (identity + protection)",
    "Guard canonical seed target (fail closed before any mutation)",
    "Canonical cleanup + seed (once per run)",
    "Preflight synthetic test-OTP contract (strict certification)",
    "Resolve focused spec selection",
    "Record expected matrix (static --list, no browser)",
    "Run E2E suite",
    "Guard — browser tests must have executed",
    "Guard — E2E execution-completeness contract",
    "Remove private runtime material",
)
HANDOFF_STEPS = (
    "Read exact run, jobs, artifact and current staging ref",
    "Validate proof and expose allowlisted E2E inputs",
)
CERTIFICATION_STEPS = (
    "Read exact operation attempt and source proof",
    "Emit operation-bound staging certification evidence",
    "Upload operation-bound staging certification evidence",
)


def _strict_dict(value: Any, code: str) -> dict[str, Any]:
    require(type(value) is dict, code)
    return cast(dict[str, Any], value)


def operation_certification_artifact_name(run_id: int, attempt: int) -> str:
    return f"{OPERATION_CERTIFICATION_PREFIX}-{positive_id(run_id)}-attempt-{positive_id(attempt)}"


def verify_operation_run(
    run: Mapping[str, Any],
    *,
    candidate_sha: str,
    expected_run_id: int | None = None,
    expected_attempt: int | None = None,
    require_completed: bool,
) -> tuple[int, int]:
    candidate = full_sha(candidate_sha)
    run_id = positive_id(run.get("id"))
    attempt = positive_id(run.get("run_attempt"))
    if expected_run_id is not None:
        require(run_id == positive_id(expected_run_id), "RUN_ATTEMPT_MISMATCH")
    if expected_attempt is not None:
        require(attempt == positive_id(expected_attempt), "RUN_ATTEMPT_MISMATCH")
    require(
        run.get("repository", {}).get("full_name") == REPOSITORY
        and run.get("repository", {}).get("id") == REPOSITORY_ID
        and run.get("head_repository", {}).get("id") == REPOSITORY_ID,
        "WRONG_REPOSITORY",
    )
    require(
        run.get("path") == ORCHESTRATION_WORKFLOW
        and run.get("head_branch") == "staging",
        "UNTRUSTED_WORKFLOW_REF",
    )
    require(run.get("event") == "push", "UNTRUSTED_EVENT")
    require(run.get("head_sha") == candidate, "RUN_SHA_MISMATCH")
    if require_completed:
        require(
            run.get("status") == "completed" and run.get("conclusion") == "success",
            "RUN_NOT_SUCCESSFUL",
        )
    else:
        require(
            run.get("status") in {"in_progress", "completed"}
            and run.get("conclusion") in {None, "success"},
            "RUN_NOT_SUCCESSFUL",
        )
    return run_id, attempt


def _logical_job(
    jobs: Sequence[Mapping[str, Any]],
    name: str,
    *,
    run_id: int,
    candidate: str,
    attempt: int,
) -> Mapping[str, Any]:
    matches = [
        job
        for job in jobs
        if job.get("run_attempt") == attempt
        and (job.get("name") == name or str(job.get("name") or "").endswith(f" / {name}"))
    ]
    require(len(matches) == 1, "MISSING_OR_AMBIGUOUS_OPERATION_JOB")
    job = matches[0]
    require(
        job.get("run_id") == run_id and job.get("head_sha") == candidate,
        "JOB_PROVENANCE_MISMATCH",
    )
    return job


def _require_successful_job(
    jobs: Sequence[Mapping[str, Any]],
    name: str,
    steps: Sequence[str],
    *,
    run_id: int,
    candidate: str,
    attempt: int,
) -> Mapping[str, Any]:
    job = _logical_job(
        jobs,
        name,
        run_id=run_id,
        candidate=candidate,
        attempt=attempt,
    )
    require(
        job.get("status") == "completed" and job.get("conclusion") == "success",
        "OPERATION_JOB_NOT_SUCCESSFUL",
    )
    raw_steps = job.get("steps")
    if not isinstance(raw_steps, list):
        raise ContractError("OPERATION_STEPS_UNAVAILABLE")
    step_rows = [_strict_dict(step, "OPERATION_STEPS_UNAVAILABLE") for step in raw_steps]
    for step_name in steps:
        matches = [step for step in step_rows if step.get("name") == step_name]
        require(len(matches) == 1, "MISSING_OR_AMBIGUOUS_OPERATION_STEP")
        require(
            matches[0].get("status") == "completed"
            and matches[0].get("conclusion") == "success",
            "OPERATION_STEP_NOT_SUCCESSFUL",
        )
    return job


def require_operation_jobs(
    jobs: Sequence[Mapping[str, Any]],
    *,
    run_id: int,
    candidate_sha: str,
    attempt: int,
    completed_consumer: bool,
) -> None:
    candidate = full_sha(candidate_sha)
    require_executed_jobs(jobs, run_id, candidate, attempt)
    _require_successful_job(
        jobs,
        "Authorize protected staging graph",
        ("Bind repository, ref and full candidate",),
        run_id=run_id,
        candidate=candidate,
        attempt=attempt,
    )
    _require_successful_job(
        jobs,
        HANDOFF_JOB,
        HANDOFF_STEPS,
        run_id=run_id,
        candidate=candidate,
        attempt=attempt,
    )
    _require_successful_job(
        jobs,
        E2E_JOB,
        E2E_STEPS,
        run_id=run_id,
        candidate=candidate,
        attempt=attempt,
    )
    if completed_consumer:
        _require_successful_job(
            jobs,
            CERTIFICATION_JOB,
            CERTIFICATION_STEPS,
            run_id=run_id,
            candidate=candidate,
            attempt=attempt,
        )
        _require_successful_job(
            jobs,
            COMPLETION_JOB,
            ("Publish truthful final record",),
            run_id=run_id,
            candidate=candidate,
            attempt=attempt,
        )


def _job_at_or_before_attempt(
    jobs: Sequence[Mapping[str, Any]],
    logical_name: str,
    *,
    attempt: int,
    current_attempt_required: bool,
) -> Mapping[str, Any]:
    matching = [
        job
        for job in jobs
        if job.get("name") == logical_name
        or str(job.get("name") or "").endswith(f" / {logical_name}")
    ]
    current = [job for job in matching if job.get("run_attempt") == attempt]
    if current:
        require(len(current) == 1, "MISSING_OR_AMBIGUOUS_OPERATION_JOB")
        return current[0]
    require(not current_attempt_required, "MISSING_OR_AMBIGUOUS_OPERATION_JOB")
    prior = [
        job
        for job in matching
        if type(job.get("run_attempt")) is int
        and 1 <= job["run_attempt"] < attempt
        and job.get("status") == "completed"
        and job.get("conclusion") == "success"
    ]
    require(bool(prior), "MISSING_OR_AMBIGUOUS_OPERATION_JOB")
    selected_attempt = max(int(job["run_attempt"]) for job in prior)
    selected = [job for job in prior if job.get("run_attempt") == selected_attempt]
    require(len(selected) == 1, "MISSING_OR_AMBIGUOUS_OPERATION_JOB")
    return selected[0]


def operation_job_binding(
    jobs: Sequence[Mapping[str, Any]],
    *,
    run_id: int,
    candidate_sha: str,
    attempt: int,
) -> list[dict[str, Any]]:
    logical_names = (
        "Authorize protected staging graph",
        *REQUIRED_JOBS,
        HANDOFF_JOB,
        E2E_JOB,
    )
    result: list[dict[str, Any]] = []
    for logical_name in logical_names:
        job = _job_at_or_before_attempt(
            jobs,
            logical_name,
            attempt=attempt,
            current_attempt_required=(
                logical_name not in REQUIRED_JOBS
                or logical_name == "Staging smoke + evidence"
            ),
        )
        require(
            job.get("run_id") == run_id
            and job.get("head_sha") == candidate_sha
            and job.get("status") == "completed"
            and job.get("conclusion") == "success",
            "JOB_PROVENANCE_MISMATCH",
        )
        result.append(
            {
                "logical_name": logical_name,
                "job_id": positive_id(job.get("id")),
                "name": job.get("name"),
                "run_id": run_id,
                "run_attempt": positive_id(job.get("run_attempt")),
                "head_sha": candidate_sha,
                "status": "completed",
                "conclusion": "success",
                "started_at": timestamp(job.get("started_at")).isoformat().replace(
                    "+00:00", "Z"
                ),
                "completed_at": timestamp(job.get("completed_at")).isoformat().replace(
                    "+00:00", "Z"
                ),
            }
        )
    return result


def _proof_binding(proof: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    previews = _strict_dict(proof.get("previews"), "INCOMPLETE_PORTAL_SET")
    require(set(previews) == set(PORTALS), "INCOMPLETE_PORTAL_SET")
    result: dict[str, dict[str, Any]] = {}
    for portal in PORTALS:
        row = _strict_dict(previews[portal], "INVALID_PORTAL_PROOF")
        result[portal] = {
            "project_id": row.get("project_id"),
            "deployment_id": row.get("deployment_id"),
            "preview_url": row.get("preview_url"),
            "deployment_sha": row.get("deployment_sha"),
            "deployment_origin_attempt": row.get("deployment_origin_attempt"),
        }
    return result


def _source_proof_metadata(artifact: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_id": positive_id(artifact.get("id")),
        "name": artifact.get("name"),
        "digest": artifact.get("digest"),
        "size_in_bytes": artifact.get("size_in_bytes"),
        "created_at": artifact.get("created_at"),
    }


def build_operation_certification_evidence(
    *,
    candidate_sha: str,
    run: Mapping[str, Any],
    source_artifact: Mapping[str, Any],
    proof: Mapping[str, Any],
    jobs: Sequence[Mapping[str, Any]],
    focus_group: str,
    outcomes: Mapping[str, str],
    certified_at: str,
    expires_at: str | None = None,
) -> dict[str, Any]:
    candidate = full_sha(candidate_sha)
    run_id, attempt = verify_operation_run(
        run,
        candidate_sha=candidate,
        require_completed=False,
    )
    require(focus_group == "full", "DIAGNOSTIC_OPERATION_NOT_CERTIFIABLE")
    expected_outcomes = {
        "authorize",
        "deploy",
        "handoff",
        "e2e",
        "setup",
        "browser",
        "execution",
        "matrix",
        "cleanup",
        "staging_ref",
        "customer_probe",
        "vendor_probe",
    }
    require(set(outcomes) == expected_outcomes, "INCOMPLETE_OPERATION_OUTCOMES")
    require(
        all(outcomes[name] == "success" for name in expected_outcomes),
        "OPERATION_NOT_COMPLETE",
    )
    require_operation_jobs(
        jobs,
        run_id=run_id,
        candidate_sha=candidate,
        attempt=attempt,
        completed_consumer=False,
    )
    expected_proof_name = f"staging-sha-proof-{run_id}-attempt-{attempt}"
    require(source_artifact.get("name") == expected_proof_name, "WRONG_ARTIFACT_KIND")
    configuration = _strict_dict(proof.get("configuration"), "RELEASE_MANIFEST_INVALID")
    revision = configuration.get("revision")
    if not isinstance(revision, str) or not revision:
        raise ContractError("RELEASE_MANIFEST_INVALID")
    derived = validate_staging_sha_proof_for_certification(dict(proof), candidate_sha=candidate)
    try:
        validate_release_envelope(
            dict(proof),
            candidate_sha=candidate,
            source_run_id=run_id,
            source_run_attempt=attempt,
            source_workflow=ORCHESTRATION_WORKFLOW,
            configuration_revision=revision,
        )
    except ProofValidationError:
        raise ContractError("RELEASE_MANIFEST_INVALID") from None
    certified = timestamp(certified_at)
    expiry = (
        timestamp(expires_at)
        if expires_at
        else certified + timedelta(seconds=OPERATION_MAX_AGE_SECONDS)
    )
    require(certified < expiry, "INVALID_CERTIFICATION_WINDOW")
    evidence: dict[str, Any] = {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "result": "PASS",
        "mode": "integrated-staging",
        **derived,
        "staging_operation_workflow_run_id": str(run_id),
        "staging_operation_run_attempt": attempt,
        "focus_group": focus_group,
        "certified_at": certified.isoformat().replace("+00:00", "Z"),
        "expires_at": expiry.isoformat().replace("+00:00", "Z"),
        "source_workflow": ORCHESTRATION_WORKFLOW,
        "source_event": "push",
        "source_repository": REPOSITORY,
        "source_repository_id": REPOSITORY_ID,
        "source_ref": "refs/heads/staging",
        "source_proof": _source_proof_metadata(source_artifact),
        "configuration": {
            "identity_scheme": configuration.get("identity_scheme"),
            "revision": revision,
        },
        "deployment_binding": _proof_binding(proof),
        "executed_jobs": operation_job_binding(
            jobs,
            run_id=run_id,
            candidate_sha=candidate,
            attempt=attempt,
        ),
        "operation_outcomes": dict(outcomes),
    }
    validate_operation_certification_evidence(
        evidence,
        candidate_sha=candidate,
        operation_run_id=str(run_id),
        operation_run_attempt=attempt,
        now=certified,
    )
    return evidence


def validate_operation_certification_evidence(
    evidence: Mapping[str, Any],
    *,
    candidate_sha: str,
    operation_run_id: str | None = None,
    operation_run_attempt: int | None = None,
    current_run_id: str | None = None,
    now: datetime | None = None,
) -> None:
    candidate = full_sha(candidate_sha)
    require(
        evidence.get("schema_version") == OPERATION_SCHEMA_VERSION,
        "WRONG_CERTIFICATION_SCHEMA",
    )
    require(evidence.get("result") == "PASS", "CERTIFICATION_NOT_PASS")
    require(evidence.get("mode") == "integrated-staging", "WRONG_CERTIFICATION_MODE")
    require(evidence.get("focus_group") == "full", "DIAGNOSTIC_OPERATION_NOT_CERTIFIABLE")
    for field in (
        "candidate_sha",
        "staging_branch_sha",
        "staging_frontend_sha",
        "staging_api_sha",
    ):
        require(full_sha(evidence.get(field)) == candidate, "CERTIFICATION_SHA_MISMATCH")
    require(
        evidence.get("staging_supabase_project_ref") == "iyasmrmbcrvlfxpzescb",
        "WRONG_STAGING_PROJECT",
    )
    run_id = str(positive_id(int(str(evidence.get("staging_operation_workflow_run_id") or "0"))))
    attempt = positive_id(evidence.get("staging_operation_run_attempt"))
    if operation_run_id is not None:
        require(run_id == str(operation_run_id), "CERTIFICATION_RUN_MISMATCH")
    if operation_run_attempt is not None:
        require(attempt == operation_run_attempt, "CERTIFICATION_ATTEMPT_MISMATCH")
    if current_run_id:
        require(run_id != str(current_run_id), "SELF_CERTIFICATION_FORBIDDEN")
    require(
        evidence.get("source_workflow") == ORCHESTRATION_WORKFLOW
        and evidence.get("source_event") == "push"
        and evidence.get("source_repository") == REPOSITORY
        and evidence.get("source_repository_id") == REPOSITORY_ID
        and evidence.get("source_ref") == "refs/heads/staging",
        "CERTIFICATION_PROVENANCE_MISMATCH",
    )
    certified = timestamp(evidence.get("certified_at"))
    expires = timestamp(evidence.get("expires_at"))
    check_time = now or datetime.now(UTC)
    require(
        check_time.tzinfo is not None and check_time.utcoffset() is not None,
        "NAIVE_CURRENT_TIME",
    )
    require(
        certified < expires
        and (expires - certified).total_seconds() <= OPERATION_MAX_AGE_SECONDS
        and certified <= check_time <= expires,
        "CERTIFICATION_EXPIRED_OR_FUTURE",
    )
    source = _strict_dict(evidence.get("source_proof"), "MISSING_SOURCE_PROOF")
    require(
        source.get("name") == f"staging-sha-proof-{run_id}-attempt-{attempt}",
        "WRONG_ARTIFACT_KIND",
    )
    positive_id(source.get("artifact_id"))
    require(
        isinstance(source.get("digest"), str)
        and re.fullmatch(r"sha256:[0-9a-f]{64}", source["digest"]) is not None,
        "MISSING_ARTIFACT_DIGEST",
    )
    require(
        type(source.get("size_in_bytes")) is int
        and 0 < source["size_in_bytes"] <= MAX_ARTIFACT_BYTES,
        "INVALID_PROOF_ARCHIVE_SIZE",
    )
    timestamp(source.get("created_at"))
    configuration = _strict_dict(
        evidence.get("configuration"), "RELEASE_MANIFEST_INVALID"
    )
    require(
        configuration.get("identity_scheme") == "operator-managed-non-secret-v1"
        and isinstance(configuration.get("revision"), str)
        and bool(configuration["revision"]),
        "RELEASE_MANIFEST_INVALID",
    )
    bindings = _strict_dict(evidence.get("deployment_binding"), "INCOMPLETE_PORTAL_SET")
    require(set(bindings) == set(PORTALS), "INCOMPLETE_PORTAL_SET")
    for portal in PORTALS:
        row = _strict_dict(bindings[portal], "INVALID_PORTAL_PROOF")
        require(
            isinstance(row.get("project_id"), str)
            and re.fullmatch(r"prj_[A-Za-z0-9]+", row["project_id"]) is not None
            and isinstance(row.get("deployment_id"), str)
            and re.fullmatch(r"dpl_[A-Za-z0-9]+", row["deployment_id"]) is not None
            and row.get("deployment_sha") == candidate
            and type(row.get("deployment_origin_attempt")) is int
            and 1 <= row["deployment_origin_attempt"] <= attempt,
            "DEPLOYMENT_BINDING_MISMATCH",
        )
    executed_jobs = evidence.get("executed_jobs")
    if not isinstance(executed_jobs, list):
        raise ContractError("INCOMPLETE_EXECUTED_JOBS")
    require(len(executed_jobs) == len(REQUIRED_JOBS) + 3, "INCOMPLETE_EXECUTED_JOBS")
    for raw_job in executed_jobs:
        job = _strict_dict(raw_job, "INCOMPLETE_EXECUTED_JOBS")
        positive_id(job.get("job_id"))
        require(
            job.get("run_id") == int(run_id)
            and type(job.get("run_attempt")) is int
            and 1 <= job["run_attempt"] <= attempt
            and job.get("head_sha") == candidate
            and job.get("status") == "completed"
            and job.get("conclusion") == "success",
            "EXECUTED_JOB_BINDING_MISMATCH",
        )
        timestamp(job.get("started_at"))
        timestamp(job.get("completed_at"))
    outcomes = _strict_dict(
        evidence.get("operation_outcomes"), "INCOMPLETE_OPERATION_OUTCOMES"
    )
    expected_outcomes = {
        "authorize",
        "deploy",
        "handoff",
        "e2e",
        "setup",
        "browser",
        "execution",
        "matrix",
        "cleanup",
        "staging_ref",
        "customer_probe",
        "vendor_probe",
    }
    require(set(outcomes) == expected_outcomes, "INCOMPLETE_OPERATION_OUTCOMES")
    require(
        all(outcomes[name] == "success" for name in expected_outcomes),
        "OPERATION_NOT_COMPLETE",
    )


def cross_check_operation_evidence_with_proof(
    evidence: Mapping[str, Any],
    *,
    proof: Mapping[str, Any],
    artifact: Mapping[str, Any],
    jobs: Sequence[Mapping[str, Any]],
) -> None:
    candidate = full_sha(evidence.get("candidate_sha"))
    derived = validate_staging_sha_proof_for_certification(dict(proof), candidate_sha=candidate)
    cross_check_certification_evidence_with_proof(dict(evidence), derived=derived)
    require(
        evidence.get("source_proof") == _source_proof_metadata(artifact),
        "SOURCE_PROOF_METADATA_MISMATCH",
    )
    configuration = _strict_dict(proof.get("configuration"), "RELEASE_MANIFEST_INVALID")
    require(evidence.get("configuration") == {
        "identity_scheme": configuration.get("identity_scheme"),
        "revision": configuration.get("revision"),
    }, "CONFIGURATION_BINDING_MISMATCH")
    require(
        evidence.get("deployment_binding") == _proof_binding(proof),
        "DEPLOYMENT_BINDING_MISMATCH",
    )
    require(
        evidence.get("executed_jobs")
        == operation_job_binding(
            jobs,
            run_id=int(str(evidence.get("staging_operation_workflow_run_id"))),
            candidate_sha=candidate,
            attempt=positive_id(evidence.get("staging_operation_run_attempt")),
        ),
        "EXECUTED_JOB_BINDING_MISMATCH",
    )
    try:
        validate_release_envelope(
            dict(proof),
            candidate_sha=candidate,
            source_run_id=int(str(evidence.get("staging_operation_workflow_run_id"))),
            source_run_attempt=positive_id(evidence.get("staging_operation_run_attempt")),
            source_workflow=ORCHESTRATION_WORKFLOW,
            configuration_revision=str(configuration.get("revision") or ""),
        )
    except (ProofValidationError, ValueError):
        raise ContractError("RELEASE_MANIFEST_INVALID") from None


def read_operation_certification_archive(
    archive: bytes,
    artifact: Mapping[str, Any],
    *,
    run_id: int,
    attempt: int,
) -> dict[str, Any]:
    expected_name = operation_certification_artifact_name(run_id, attempt)
    require(artifact.get("name") == expected_name, "WRONG_CERTIFICATION_ARTIFACT")
    require(artifact.get("expired") is False, "ARTIFACT_EXPIRED_OR_UNKNOWN")
    require(
        type(artifact.get("size_in_bytes")) is int
        and 0 < artifact["size_in_bytes"] <= MAX_ARTIFACT_BYTES,
        "INVALID_CERTIFICATION_ARCHIVE_SIZE",
    )
    digest = artifact.get("digest")
    require(
        isinstance(digest, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is not None,
        "MISSING_ARTIFACT_DIGEST",
    )
    require(len(archive) <= MAX_ARTIFACT_BYTES, "CERTIFICATION_ARCHIVE_TOO_LARGE")
    require("sha256:" + hashlib.sha256(archive).hexdigest() == digest, "ARTIFACT_DIGEST_MISMATCH")
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as zf:
            entries = zf.infolist()
            require(len(entries) == 1, "UNEXPECTED_ARCHIVE_ENTRIES")
            entry = entries[0]
            require(entry.filename == OPERATION_CERTIFICATION_FILENAME, "UNEXPECTED_ARCHIVE_PATH")
            require(not stat.S_ISLNK(entry.external_attr >> 16), "ARCHIVE_SYMLINK")
            require(not entry.flag_bits & 1, "ENCRYPTED_ARCHIVE")
            require(entry.file_size <= MAX_ARTIFACT_BYTES, "CERTIFICATION_DOCUMENT_TOO_LARGE")
            data = json.loads(zf.read(entry).decode("utf-8"), object_pairs_hook=_unique_json)
    except (zipfile.BadZipFile, RuntimeError, UnicodeError, json.JSONDecodeError):
        raise ContractError("INVALID_CERTIFICATION_ARCHIVE") from None
    require(type(data) is dict, "INVALID_CERTIFICATION_DOCUMENT")
    return cast(dict[str, Any], data)


def _unique_json(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def read_operation_source(
    *,
    archive: bytes,
    run: Mapping[str, Any],
    artifact: Mapping[str, Any],
    jobs: Sequence[Mapping[str, Any]],
    candidate_sha: str,
) -> tuple[dict[str, Any], int, int]:
    run_id, attempt = verify_operation_run(
        run,
        candidate_sha=candidate_sha,
        require_completed=False,
    )
    arun = _strict_dict(
        artifact.get("workflow_run"), "ARTIFACT_PROVENANCE_MISMATCH"
    )
    require(
        arun.get("id") == run_id
        and arun.get("head_sha") == candidate_sha
        and arun.get("head_branch") == "staging"
        and arun.get("repository_id") == REPOSITORY_ID,
        "ARTIFACT_PROVENANCE_MISMATCH",
    )
    proof = read_proof_archive(
        archive,
        artifact,
        expected_name=f"staging-sha-proof-{run_id}-attempt-{attempt}",
    )
    require_operation_jobs(
        jobs,
        run_id=run_id,
        candidate_sha=candidate_sha,
        attempt=attempt,
        completed_consumer=False,
    )
    smoke_started, smoke_completed = require_executed_jobs(
        jobs, run_id, full_sha(candidate_sha), attempt
    )
    proved_at = timestamp(proof.get("proved_at"))
    created_at = timestamp(artifact.get("created_at"))
    require(
        smoke_started <= proved_at <= smoke_completed
        and smoke_started <= created_at <= smoke_completed,
        "PROOF_ATTEMPT_NOT_BOUND",
    )
    return proof, run_id, attempt
