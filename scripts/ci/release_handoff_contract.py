#!/usr/bin/env python3
"""Fail-closed staging deployment-to-E2E handoff contract.

The trusted workflow adapter obtains run/artifact/job data from authenticated
GitHub API reads and current deployment data from authenticated Vercel reads.
This module validates those results and derives allowlisted E2E inputs. It
extends the existing staging proof validator; it never replaces that validator
or creates a second release manifest. All rejection messages are fixed codes so
untrusted provider or artifact content is never reflected into workflow logs.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from validate_staging_proof import ProofValidationError, validate_release_envelope

REPOSITORY = "KaluMuso/Convergeo"
REPOSITORY_ID = 1290591718
WORKFLOW = ".github/workflows/deploy-staging.yml"
ORCHESTRATION_WORKFLOW = ".github/workflows/staging-operation.yml"
TRUSTED_WORKFLOWS = frozenset({WORKFLOW, ORCHESTRATION_WORKFLOW})
SHA = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
STAGING_PROJECT = "iyasmrmbcrvlfxpzescb"
API_HOST = "api.staging.vergeo5.com"
CUSTOMER_ORIGIN = "https://customer.staging.vergeo5.com"
PORTALS = ("customer", "vendor", "admin")
FOCUS = frozenset(
    {"full", "previous-six", "cart", "vendor-auth", "checkout-honesty", "performance"}
)
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
SMOKE_STEPS = (
    "Require all three Preview proofs",
    "CORS proof — certified immutable Preview origins (RC-6 / PR-F3)",
    "Native DB pool + service-role read proof (cart-location remediation)",
    "Guest-cart SameSite proof on the stable Customer hostname",
    "Health + fingerprint",
    "Migration status evidence",
    "Bundle staging SHA proof artifact",
    "Upload unified staging SHA proof",
)


class ContractError(ValueError):
    """Sanitized fail-closed error code, never raw input content."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ContractError(code)


def full_sha(value: Any) -> str:
    require(
        isinstance(value, str) and SHA.fullmatch(value) is not None, "INVALID_FULL_SHA"
    )
    return value


def positive_id(value: Any) -> int:
    require(type(value) is int and value > 0, "INVALID_IDENTIFIER")
    return value


def timestamp(value: Any) -> datetime:
    require(isinstance(value, str), "INVALID_TIMESTAMP")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ContractError("INVALID_TIMESTAMP") from None
    require(
        result.tzinfo is not None and result.utcoffset() is not None, "NAIVE_TIMESTAMP"
    )
    return result


def _unique_json(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def read_proof_archive(
    archive: bytes, artifact: Mapping[str, Any], *, expected_name: str
) -> dict[str, Any]:
    """Read exactly one bounded proof file, in memory; never extract paths."""
    require(
        isinstance(expected_name, str)
        and re.fullmatch(
            r"staging-sha-proof-[1-9][0-9]*-attempt-[1-9][0-9]*", expected_name
        )
        is not None,
        "INVALID_ARTIFACT_IDENTITY",
    )
    require(artifact.get("name") == expected_name, "WRONG_ARTIFACT_KIND")
    require(artifact.get("expired") is False, "ARTIFACT_EXPIRED_OR_UNKNOWN")
    expected = artifact.get("digest")
    require(
        isinstance(expected, str) and DIGEST.fullmatch(expected) is not None,
        "MISSING_ARTIFACT_DIGEST",
    )
    require(len(archive) <= 1024 * 1024, "ARCHIVE_TOO_LARGE")
    require(
        "sha256:" + hashlib.sha256(archive).hexdigest() == expected,
        "ARTIFACT_DIGEST_MISMATCH",
    )
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as zf:
            entries = zf.infolist()
            require(len(entries) == 1, "UNEXPECTED_ARCHIVE_ENTRIES")
            entry = entries[0]
            require(
                entry.filename == "staging-sha-proof.json", "UNEXPECTED_ARCHIVE_PATH"
            )
            require(not stat.S_ISLNK(entry.external_attr >> 16), "ARCHIVE_SYMLINK")
            require(not entry.flag_bits & 1, "ENCRYPTED_ARCHIVE")
            require(entry.file_size <= 1024 * 1024, "PROOF_TOO_LARGE")
            raw = zf.read(entry)
        proof = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_json)
    except (zipfile.BadZipFile, RuntimeError, UnicodeError, json.JSONDecodeError):
        raise ContractError("INVALID_PROOF_ARCHIVE") from None
    require(type(proof) is dict, "INVALID_PROOF_DOCUMENT")
    return proof


def preview_origin(portal: str, value: Any) -> str:
    require(isinstance(value, str), "INVALID_PREVIEW_URL")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ContractError("INVALID_PREVIEW_URL") from None
    # Shape is a scope restriction, NOT proof of immutability/ownership. The
    # integrating adapter must independently validate this URL against Vercel.
    hostname = parsed.hostname or ""
    require(
        parsed.scheme == "https" and not parsed.username and not parsed.password,
        "UNSAFE_PREVIEW_URL",
    )
    require(
        port is None
        and parsed.path in {"", "/"}
        and not parsed.query
        and not parsed.fragment,
        "UNSAFE_PREVIEW_URL",
    )
    require(
        re.fullmatch(
            rf"convergeo-{portal}-[a-z0-9]+-vergeo-projects\.vercel\.app", hostname
        )
        is not None,
        "UNEXPECTED_PREVIEW_ORIGIN",
    )
    return "https://" + hostname


@dataclass(frozen=True)
class Handoff:
    candidate_sha: str
    source_run_id: int
    source_attempt: int
    source_artifact_id: int
    customer_url: str
    vendor_url: str
    admin_url: str

    def workflow_inputs(self, focus_group: str) -> dict[str, Any]:
        require(focus_group in FOCUS, "INVALID_E2E_SCOPE")
        return {
            "base_url": self.customer_url,
            "vendor_base_url": self.vendor_url,
            "admin_base_url": self.admin_url,
            "expect_sha": self.candidate_sha,
            "pre_release": focus_group == "full",
            "focus_group": focus_group,
            "source_run_id": self.source_run_id,
            "source_run_attempt": self.source_attempt,
            "source_artifact_id": self.source_artifact_id,
        }

    def diagnostic_inputs(self, focus_group: str) -> dict[str, Any]:
        require(focus_group != "full", "DIAGNOSTIC_SUBSET_REQUIRED")
        return self.workflow_inputs(focus_group)

    def summary(self) -> str:
        return (
            "## Staging evidence handoff\n\n"
            f"Candidate: `{self.candidate_sha}`\n\n"
            f"Deployment run: `{self.source_run_id}`, attempt `{self.source_attempt}`; "
            f"artifact `{self.source_artifact_id}`.\n\n"
            "Artifact/provenance contract: PASS.\n\n"
            "Runtime re-probe, staging exclusion, and explicit dispatch authorization: STILL REQUIRED.\n"
            "This is not a browser-test result or a production GO.\n"
        )


def require_executed_jobs(
    jobs: Sequence[Mapping[str, Any]], run_id: int, candidate: str, attempt: int
) -> tuple[datetime, datetime]:
    smoke_window: tuple[datetime, datetime] | None = None
    for name in REQUIRED_JOBS:
        # Reusable-workflow jobs are prefixed by the caller job ("deploy /").
        # Accept only an exact logical-name suffix and still require uniqueness.
        found = [
            job
            for job in jobs
            if job.get("name") == name
            or str(job.get("name") or "").endswith(f" / {name}")
        ]
        require(
            all(
                type(job.get("run_attempt")) is int
                and 1 <= job["run_attempt"] <= attempt
                for job in found
            ),
            "JOB_ATTEMPT_UNBOUND",
        )
        current = [job for job in found if job.get("run_attempt") == attempt]
        if current:
            require(len(current) == 1, "MISSING_OR_AMBIGUOUS_JOB")
            job = current[0]
        else:
            successful_prior = [
                job
                for job in found
                if type(job.get("run_attempt")) is int
                and 1 <= job["run_attempt"] < attempt
                and job.get("status") == "completed"
                and job.get("conclusion") == "success"
            ]
            require(bool(successful_prior), "MISSING_OR_AMBIGUOUS_JOB")
            newest_attempt = max(job["run_attempt"] for job in successful_prior)
            selected = [
                job
                for job in successful_prior
                if job.get("run_attempt") == newest_attempt
            ]
            require(len(selected) == 1, "MISSING_OR_AMBIGUOUS_JOB")
            job = selected[0]
        require(
            job.get("run_id") == run_id and job.get("head_sha") == candidate,
            "JOB_PROVENANCE_MISMATCH",
        )
        require(
            job.get("status") == "completed" and job.get("conclusion") == "success",
            "JOB_NOT_SUCCESSFUL",
        )
        require(
            type(job.get("run_attempt")) is int and 1 <= job["run_attempt"] <= attempt,
            "JOB_ATTEMPT_UNBOUND",
        )
        # A failed-jobs-only rerun retains earlier successful dependencies.
        # They are allowed as inputs, but final smoke must run on this attempt.
        if name == "Staging smoke + evidence":
            require(job["run_attempt"] == attempt, "SMOKE_NOT_CURRENT_ATTEMPT")
            smoke_window = (
                timestamp(job.get("started_at")),
                timestamp(job.get("completed_at")),
            )
            require(smoke_window[0] <= smoke_window[1], "INVALID_SMOKE_WINDOW")
            for step_name in SMOKE_STEPS:
                steps = [
                    step
                    for step in job.get("steps", [])
                    if step.get("name") == step_name
                ]
                require(len(steps) == 1, "MISSING_OR_AMBIGUOUS_SMOKE_STEP")
                require(
                    steps[0].get("status") == "completed"
                    and steps[0].get("conclusion") == "success",
                    "SMOKE_STEP_NOT_EXECUTED_SUCCESSFULLY",
                )

    require(smoke_window is not None, "MISSING_SMOKE_WINDOW")
    assert smoke_window is not None
    return smoke_window


def validate_vercel_metadata(
    proof: Mapping[str, Any],
    live_deployments: Mapping[str, Mapping[str, Any]],
    *,
    candidate_sha: str,
    expected_project_ids: Mapping[str, str],
    configuration_revision: str,
    source_run_id: int,
) -> dict[str, str]:
    """Bind manifest identities to authenticated current Vercel metadata."""
    require(set(live_deployments) == set(PORTALS), "INCOMPLETE_VERCEL_METADATA")
    require(set(expected_project_ids) == set(PORTALS), "INCOMPLETE_PROJECT_IDENTITY")
    previews = proof.get("previews")
    if type(previews) is not dict:
        raise ContractError("INVALID_PROOF_DOCUMENT")
    origins: dict[str, str] = {}
    for portal in PORTALS:
        row = previews.get(portal)
        live = live_deployments[portal]
        project_id = expected_project_ids[portal]
        if type(row) is not dict or type(live) is not dict:
            raise ContractError("INVALID_VERCEL_METADATA")
        require(
            isinstance(project_id, str)
            and re.fullmatch(r"prj_[A-Za-z0-9]+", project_id) is not None,
            "INVALID_PROJECT_IDENTITY",
        )
        require(row.get("project_id") == project_id, "VERCEL_PROJECT_MISMATCH")
        require(live.get("projectId") == project_id, "VERCEL_PROJECT_MISMATCH")
        require(
            live.get("id") == row.get("deployment_id"), "VERCEL_DEPLOYMENT_MISMATCH"
        )
        require(live.get("readyState") == "READY", "VERCEL_DEPLOYMENT_NOT_READY")
        require(live.get("target") in {None, "preview"}, "VERCEL_TARGET_MISMATCH")
        meta = live.get("meta")
        require(type(meta) is dict, "INVALID_VERCEL_METADATA")
        require(meta.get("githubCommitSha") == candidate_sha, "VERCEL_SHA_MISMATCH")
        require(
            meta.get("convergeoBuildConfigRevision") == configuration_revision,
            "VERCEL_CONFIGURATION_MISMATCH",
        )
        require(
            meta.get("convergeoRepositoryId") == str(REPOSITORY_ID)
            and meta.get("convergeoSourceRunId") == str(source_run_id)
            and meta.get("convergeoCreationAttempt")
            == str(row.get("deployment_origin_attempt")),
            "VERCEL_PRODUCER_MISMATCH",
        )
        origin = preview_origin(portal, row.get("preview_url"))
        require(live.get("url") == urlsplit(origin).hostname, "VERCEL_URL_MISMATCH")
        origins[portal] = origin
    return origins


def resolve_handoff(
    archive: bytes,
    *,
    run: Mapping[str, Any],
    artifact: Mapping[str, Any],
    jobs: Sequence[Mapping[str, Any]],
    live_deployments: Mapping[str, Mapping[str, Any]],
    expected_project_ids: Mapping[str, str],
    expected_sha: str,
    current_staging_sha: str,
    expected_run_id: int,
    expected_attempt: int,
    configuration_revision: str,
    now: datetime,
    max_age_seconds: int,
) -> Handoff:
    """Resolve a v2 staging-sha-proof plus trusted provider provenance.

    Strict by design: old artifacts lacking metadata cannot silently pass. The
    caller must hold the shared-staging exclusion window and run the separate
    browser preflight before using the returned values for certification.
    """
    candidate = full_sha(expected_sha)
    require(full_sha(current_staging_sha) == candidate, "STAGING_MOVED")
    run_id, attempt = positive_id(expected_run_id), positive_id(expected_attempt)
    require(
        run.get("id") == run_id and run.get("run_attempt") == attempt,
        "RUN_ATTEMPT_MISMATCH",
    )
    require(
        run.get("repository", {}).get("full_name") == REPOSITORY
        and run.get("repository", {}).get("id") == REPOSITORY_ID
        and run.get("head_repository", {}).get("id") == REPOSITORY_ID,
        "WRONG_REPOSITORY",
    )
    source_workflow = run.get("path")
    require(
        run.get("head_branch") == "staging" and source_workflow in TRUSTED_WORKFLOWS,
        "UNTRUSTED_WORKFLOW_REF",
    )
    require(run.get("event") in {"push", "workflow_dispatch"}, "UNTRUSTED_EVENT")
    require(run.get("head_sha") == candidate, "RUN_SHA_MISMATCH")
    if source_workflow == ORCHESTRATION_WORKFLOW:
        # The outer operation resolves its own deploy artifact before its E2E
        # leg, so the trusted run is necessarily still in progress. Completed
        # follow-up consumers still require its final success.
        require(run.get("status") in {"in_progress", "completed"}, "RUN_NOT_SUCCESSFUL")
        require(run.get("conclusion") in {None, "success"}, "RUN_NOT_SUCCESSFUL")
    else:
        require(
            run.get("status") == "completed" and run.get("conclusion") == "success",
            "RUN_NOT_SUCCESSFUL",
        )
    arun = artifact.get("workflow_run", {})
    require(
        arun.get("id") == run_id
        and arun.get("head_sha") == candidate
        and arun.get("head_branch") == "staging"
        and arun.get("repository_id") == REPOSITORY_ID,
        "ARTIFACT_PROVENANCE_MISMATCH",
    )
    proof = read_proof_archive(
        archive,
        artifact,
        expected_name=f"staging-sha-proof-{run_id}-attempt-{attempt}",
    )
    require(proof.get("candidate_sha") == candidate, "PROOF_SHA_MISMATCH")
    proved_at = timestamp(proof.get("proved_at"))
    started = timestamp(run.get("run_started_at"))
    provider_updated = timestamp(run.get("updated_at"))
    require(
        now.tzinfo is not None and now.utcoffset() is not None, "NAIVE_CURRENT_TIME"
    )
    require(
        type(max_age_seconds) is int and 0 < max_age_seconds <= 86400,
        "INVALID_FRESHNESS_POLICY",
    )
    ended = now if run.get("status") == "in_progress" else provider_updated
    require(started <= provider_updated <= now, "INVALID_RUN_WINDOW")
    require(
        started <= proved_at <= ended <= now
        and 0 <= (now - proved_at).total_seconds() <= max_age_seconds,
        "STALE_OR_FUTURE_PROOF",
    )
    # Bound final proof to the current attempt's actual smoke execution, not
    # solely run_started_at (which a provider may retain across reruns). The
    # caller supplies authenticated latest jobs, including reused dependencies.
    smoke_started, smoke_ended = require_executed_jobs(jobs, run_id, candidate, attempt)
    require(
        started <= smoke_started <= proved_at <= smoke_ended <= ended,
        "PROOF_ATTEMPT_NOT_BOUND",
    )
    created = timestamp(artifact.get("created_at"))
    require(smoke_started <= created <= smoke_ended, "ARTIFACT_ATTEMPT_NOT_BOUND")
    previews = proof.get("previews")
    if type(previews) is not dict or set(previews) != set(PORTALS):
        raise ContractError("INCOMPLETE_PORTAL_SET")
    for portal in PORTALS:
        row = previews[portal]
        if type(row) is not dict:
            raise ContractError("INVALID_PORTAL_PROOF")
        require(
            row.get("candidate_sha") == candidate
            and row.get("deployment_sha") == candidate,
            "PORTAL_SHA_MISMATCH",
        )
        require(
            row.get("target") == "preview"
            and row.get("health_env") in {"staging", "preview"},
            "WRONG_PORTAL_PLANE",
        )
        require(
            row.get("health_app") == portal
            and row.get("health_status") == "ok"
            and row.get("health_api_host") == API_HOST,
            "PORTAL_CONFIG_MISMATCH",
        )
        # Stronger handoff contract, not a change to the existing optional
        # immutable-health corroboration policy until an adapter is approved.
        require(
            full_sha(row.get("health_build_id")) == candidate, "HEALTH_SHA_MISMATCH"
        )
        require(
            isinstance(row.get("deployment_id"), str)
            and re.fullmatch(r"dpl_[A-Za-z0-9]+", row["deployment_id"]) is not None,
            "MISSING_DEPLOYMENT_ID",
        )
    customer = previews["customer"]
    if type(customer) is not dict:
        raise ContractError("INVALID_PORTAL_PROOF")
    require(
        customer.get("stable_hostname_status") == "verified"
        and customer.get("stable_hostname_url") == CUSTOMER_ORIGIN,
        "SAMESITE_CUSTOMER_NOT_PROVEN",
    )
    fp = proof.get("api_fingerprint")
    require(
        type(fp) is dict
        and fp.get("env") == "staging"
        and fp.get("git_sha") == candidate
        and fp.get("image_tag") == candidate
        and fp.get("supabase_project_ref") == STAGING_PROJECT,
        "API_FINGERPRINT_MISMATCH",
    )
    require(proof.get("migrate_supabase_result") == "success", "MIGRATIONS_NOT_PROVEN")
    try:
        validate_release_envelope(
            proof,
            candidate_sha=candidate,
            source_run_id=run_id,
            source_run_attempt=attempt,
            source_workflow=str(source_workflow),
            configuration_revision=configuration_revision,
        )
    except ProofValidationError:
        raise ContractError("RELEASE_MANIFEST_INVALID") from None
    urls = validate_vercel_metadata(
        proof,
        live_deployments,
        candidate_sha=candidate,
        expected_project_ids=expected_project_ids,
        configuration_revision=configuration_revision,
        source_run_id=run_id,
    )
    return Handoff(
        candidate,
        run_id,
        attempt,
        positive_id(artifact.get("id")),
        CUSTOMER_ORIGIN,
        urls["vendor"],
        urls["admin"],
    )


def reuse_eligible(
    receipt: Mapping[str, Any],
    live: Mapping[str, Any],
    *,
    candidate_sha: str,
    project_id: str,
    config_revision: str,
) -> bool:
    """Eligibility to RE-PROBE an existing deployment; never certification.

    `config_revision` must be an independently established, non-secret opaque
    build-configuration revision covering settings/env revision/dependency
    inputs. If unavailable, fail closed rather than equating source SHA with
    build configuration. No value is computed from or exported for secrets.
    """
    full_sha(candidate_sha)
    if not config_revision or not project_id:
        return False
    return bool(
        receipt.get("candidate_sha") == candidate_sha
        and receipt.get("project_id") == project_id
        and receipt.get("build_config_revision") == config_revision
        and live.get("build_config_revision") == config_revision
        and live.get("id") == receipt.get("deployment_id")
        and isinstance(live.get("id"), str)
        and re.fullmatch(r"dpl_[A-Za-z0-9]+", live["id"])
        and live.get("projectId") == project_id
        and live.get("readyState") == "READY"
        and live.get("target") == "preview"
        and live.get("meta", {}).get("githubCommitSha") == candidate_sha
    )


def _load_json(path: Path) -> Any:
    require(
        path.is_file() and path.stat().st_size <= 2 * 1024 * 1024,
        "INPUT_FILE_UNAVAILABLE",
    )
    try:
        return json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_unique_json
        )
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ContractError("INVALID_INPUT_JSON") from None


def _read_archive(path: Path) -> bytes:
    require(
        path.is_file() and 0 < path.stat().st_size <= 1024 * 1024,
        "INPUT_FILE_UNAVAILABLE",
    )
    try:
        return path.read_bytes()
    except OSError:
        raise ContractError("INPUT_FILE_UNAVAILABLE") from None


def _write_pairs(path: Path, values: Mapping[str, Any], *, upper_keys: bool) -> None:
    lines: list[str] = []
    for key, value in values.items():
        rendered = str(value).lower() if isinstance(value, bool) else str(value)
        require("\n" not in rendered and "\r" not in rendered, "UNSAFE_OUTPUT_VALUE")
        output_key = key.upper() if upper_keys else key.lower()
        lines.append(f"{output_key}={rendered}")
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    except OSError:
        raise ContractError("OUTPUT_FILE_UNAVAILABLE") from None


def _fetch_vercel_deployments(
    proof: Mapping[str, Any], *, token: str, organization_id: str
) -> dict[str, Mapping[str, Any]]:
    require(bool(token), "VERCEL_AUTH_UNAVAILABLE")
    require(
        re.fullmatch(r"[A-Za-z0-9_]+", organization_id or "") is not None,
        "INVALID_VERCEL_ORGANIZATION",
    )
    previews = proof.get("previews")
    if type(previews) is not dict:
        raise ContractError("INVALID_PROOF_DOCUMENT")
    result: dict[str, Mapping[str, Any]] = {}
    for portal in PORTALS:
        row = previews.get(portal)
        if type(row) is not dict:
            raise ContractError("INVALID_PORTAL_PROOF")
        deployment_id = row.get("deployment_id")
        require(
            isinstance(deployment_id, str)
            and re.fullmatch(r"dpl_[A-Za-z0-9]+", deployment_id) is not None,
            "MISSING_DEPLOYMENT_ID",
        )
        query = urllib.parse.urlencode({"teamId": organization_id})
        request = urllib.request.Request(
            f"https://api.vercel.com/v13/deployments/{deployment_id}?{query}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read(1024 * 1024 + 1)
            require(len(raw) <= 1024 * 1024, "VERCEL_METADATA_TOO_LARGE")
            value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_json)
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            UnicodeError,
            json.JSONDecodeError,
        ):
            raise ContractError("VERCEL_METADATA_UNAVAILABLE") from None
        require(type(value) is dict, "INVALID_VERCEL_METADATA")
        result[portal] = value
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Resolve authenticated staging evidence for E2E"
    )
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--vercel-dir", type=Path)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--current-staging-sha", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--attempt", type=int, required=True)
    parser.add_argument("--configuration-revision", required=True)
    parser.add_argument("--project-customer", required=True)
    parser.add_argument("--project-vendor", required=True)
    parser.add_argument("--project-admin", required=True)
    parser.add_argument("--focus-group", choices=sorted(FOCUS), required=True)
    parser.add_argument("--max-age-seconds", type=int, default=21_600)
    parser.add_argument("--github-env", type=Path)
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args(argv)

    try:
        run = _load_json(args.run)
        artifact = _load_json(args.artifact)
        jobs_raw = _load_json(args.jobs)
        require(
            type(run) is dict and type(artifact) is dict, "INVALID_PROVIDER_METADATA"
        )
        require(type(jobs_raw) is list, "INVALID_PROVIDER_METADATA")
        if args.vercel_dir:
            live = {
                portal: _load_json(args.vercel_dir / f"{portal}.json")
                for portal in PORTALS
            }
        else:
            archive_for_lookup = _read_archive(args.archive)
            proof_for_lookup = read_proof_archive(
                archive_for_lookup,
                artifact,
                expected_name=(
                    f"staging-sha-proof-{args.run_id}-attempt-{args.attempt}"
                ),
            )
            live = _fetch_vercel_deployments(
                proof_for_lookup,
                token=os.environ.get("VERCEL_TOKEN", ""),
                organization_id=os.environ.get("VERCEL_ORG_ID", ""),
            )
        require(
            all(type(value) is dict for value in live.values()),
            "INVALID_VERCEL_METADATA",
        )
        archive = _read_archive(args.archive)
        handoff = resolve_handoff(
            archive,
            run=run,
            artifact=artifact,
            jobs=jobs_raw,
            live_deployments=live,
            expected_project_ids={
                "customer": args.project_customer,
                "vendor": args.project_vendor,
                "admin": args.project_admin,
            },
            expected_sha=args.expected_sha,
            current_staging_sha=args.current_staging_sha,
            expected_run_id=args.run_id,
            expected_attempt=args.attempt,
            configuration_revision=args.configuration_revision,
            now=datetime.now(timezone.utc),
            max_age_seconds=args.max_age_seconds,
        )
        values = handoff.workflow_inputs(args.focus_group)
        values_for_transport = {
            "E2E_BASE_URL": values["base_url"],
            "E2E_VENDOR_BASE_URL": values["vendor_base_url"],
            "E2E_ADMIN_BASE_URL": values["admin_base_url"],
            "E2E_EXPECT_SHA": values["expect_sha"],
            "E2E_SOURCE_RUN_ID": values["source_run_id"],
            "E2E_SOURCE_RUN_ATTEMPT": values["source_run_attempt"],
            "E2E_SOURCE_ARTIFACT_ID": values["source_artifact_id"],
            "E2E_PRE_RELEASE": values["pre_release"],
            "E2E_FOCUS_GROUP": values["focus_group"],
        }
        require(
            args.github_env is not None or args.github_output is not None,
            "OUTPUT_FILE_UNAVAILABLE",
        )
        if args.github_env is not None:
            _write_pairs(args.github_env, values_for_transport, upper_keys=True)
        if args.github_output is not None:
            _write_pairs(args.github_output, values_for_transport, upper_keys=False)
        if args.summary:
            try:
                with args.summary.open("a", encoding="utf-8") as handle:
                    handle.write(handoff.summary())
            except OSError:
                raise ContractError("OUTPUT_FILE_UNAVAILABLE") from None
    except (ContractError, OSError) as exc:
        code = str(exc) if isinstance(exc, ContractError) else "INPUT_FILE_UNAVAILABLE"
        print(f"::error::release handoff rejected: {code}", file=sys.stderr)
        return 1

    print(
        f"release handoff PASS candidate={handoff.candidate_sha} "
        f"run={handoff.source_run_id} attempt={handoff.source_attempt} "
        f"artifact={handoff.source_artifact_id}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
