#!/usr/bin/env python3
"""Sanitized, fail-closed transport for retryable Vercel deployments.

A checkpoint records that a deployment was created or recovered. It is written
before any health or alias probe and is deliberately not certification evidence.
Artifact provenance is authenticated by the caller with GitHub API metadata;
this module verifies that metadata, the artifact digest, the checkpoint schema,
and independently fetched Vercel deployment metadata before allowing reuse.
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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast

REPOSITORY = "KaluMuso/Convergeo"
REPOSITORY_ID = 1290591718
WORKFLOW = ".github/workflows/deploy-staging.yml"
# API run identity names the caller; checkpoint producer identity stays WORKFLOW.
RUN_WORKFLOWS = frozenset({WORKFLOW, ".github/workflows/staging-operation.yml"})
REF = "refs/heads/staging"
SCHEMA_VERSION = 1
EVIDENCE_KIND = "staging-vercel-deployment-checkpoint"
STAGE = "PRE_PROBE"
IDENTITY_SCHEME = "operator-managed-non-secret-v1"
PORTALS = frozenset({"customer", "vendor", "admin"})
FULL_SHA = re.compile(r"[0-9a-f]{40}\Z")
PROJECT_ID = re.compile(r"prj_[A-Za-z0-9]+\Z")
DEPLOYMENT_ID = re.compile(r"dpl_[A-Za-z0-9]+\Z")
CONFIG_REVISION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
MAX_ARCHIVE_BYTES = 256 * 1024
MAX_DOCUMENT_BYTES = 64 * 1024
ACTIVE_STATES = frozenset({"QUEUED", "INITIALIZING", "BUILDING", "READY"})


class CheckpointError(ValueError):
    """A fixed rejection code; untrusted data is never included."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise CheckpointError(code)


def _positive_int(value: Any) -> int:
    require(type(value) is int and value > 0, "INVALID_IDENTIFIER")
    return cast(int, value)


def _full_sha(value: Any) -> str:
    if not isinstance(value, str) or FULL_SHA.fullmatch(value) is None:
        raise CheckpointError("INVALID_FULL_SHA")
    return value


def _config_revision(value: Any) -> str:
    if not isinstance(value, str) or CONFIG_REVISION.fullmatch(value) is None:
        raise CheckpointError("INVALID_CONFIGURATION_REVISION")
    return value


def _timestamp(value: Any) -> datetime:
    require(isinstance(value, str), "INVALID_TIMESTAMP")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise CheckpointError("INVALID_TIMESTAMP") from None
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


def _loads(raw: bytes, *, max_bytes: int) -> Any:
    require(0 < len(raw) <= max_bytes, "DOCUMENT_SIZE_INVALID")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_json)
    except (UnicodeError, json.JSONDecodeError):
        raise CheckpointError("INVALID_JSON") from None


def _read_json(path: Path, *, max_bytes: int = MAX_DOCUMENT_BYTES) -> Any:
    try:
        require(path.is_file(), "INPUT_FILE_UNAVAILABLE")
        return _loads(path.read_bytes(), max_bytes=max_bytes)
    except OSError:
        raise CheckpointError("INPUT_FILE_UNAVAILABLE") from None


def checkpoint_artifact_name(portal: str, run_id: int, attempt: int) -> str:
    require(portal in PORTALS, "INVALID_PORTAL")
    return f"staging-preview-checkpoint-{portal}-{_positive_int(run_id)}-attempt-{_positive_int(attempt)}"


@dataclass(frozen=True)
class Checkpoint:
    portal: str
    project_id: str
    deployment_id: str
    candidate_sha: str
    configuration_revision: str
    producer_run_id: int
    producer_attempt: int
    creation_attempt: int
    action: str
    generated_at: str


@dataclass(frozen=True)
class ReuseDecision:
    decision: str
    reason: str
    deployment_id: str | None
    origin_attempt: int
    deployment_create_calls: int
    reused_deployments: int


def create_decision(reason: str, current_attempt: int) -> ReuseDecision:
    require(re.fullmatch(r"[A-Z0-9_]+", reason) is not None, "INVALID_DECISION_REASON")
    return ReuseDecision("create", reason, None, _positive_int(current_attempt), 1, 0)


def reuse_decision(checkpoint: Checkpoint) -> ReuseDecision:
    return ReuseDecision(
        "reuse",
        "ELIGIBLE_REPROBE",
        checkpoint.deployment_id,
        checkpoint.creation_attempt,
        0,
        1,
    )


def parse_checkpoint(
    value: Any,
    *,
    expected_run_id: int,
    expected_producer_attempt: int,
) -> Checkpoint:
    """Validate structure and trusted producer identity, not current eligibility."""
    require(type(value) is dict, "INVALID_CHECKPOINT")
    require(value.get("schema_version") == SCHEMA_VERSION, "CHECKPOINT_SCHEMA_MISMATCH")
    require(value.get("evidence_kind") == EVIDENCE_KIND, "WRONG_CHECKPOINT_KIND")
    require(
        value.get("certification_evidence") is False, "CHECKPOINT_IS_NOT_CERTIFICATE"
    )
    require(value.get("stage") == STAGE, "INVALID_CHECKPOINT_STAGE")

    producer = value.get("producer")
    require(type(producer) is dict, "INVALID_CHECKPOINT_PRODUCER")
    require(
        producer.get("repository") == REPOSITORY
        and producer.get("repository_id") == REPOSITORY_ID
        and producer.get("workflow") == WORKFLOW
        and producer.get("ref") == REF,
        "UNTRUSTED_CHECKPOINT_PRODUCER",
    )
    run_id = _positive_int(producer.get("run_id"))
    producer_attempt = _positive_int(producer.get("run_attempt"))
    require(run_id == expected_run_id, "CHECKPOINT_RUN_MISMATCH")
    require(
        producer_attempt == expected_producer_attempt, "CHECKPOINT_ATTEMPT_MISMATCH"
    )

    portal = value.get("portal")
    require(portal in PORTALS, "INVALID_PORTAL")
    project_id = value.get("project_id")
    deployment_id = value.get("deployment_id")
    if not isinstance(project_id, str) or PROJECT_ID.fullmatch(project_id) is None:
        raise CheckpointError("INVALID_PROJECT_ID")
    if (
        not isinstance(deployment_id, str)
        or DEPLOYMENT_ID.fullmatch(deployment_id) is None
    ):
        raise CheckpointError("INVALID_DEPLOYMENT_ID")
    require(value.get("target") == "preview", "INVALID_TARGET")
    candidate_sha = _full_sha(value.get("candidate_sha"))

    configuration = value.get("configuration")
    if type(configuration) is not dict:
        raise CheckpointError("INVALID_CONFIGURATION_IDENTITY")
    require(
        configuration.get("identity_scheme") == IDENTITY_SCHEME,
        "INVALID_CONFIGURATION_IDENTITY",
    )
    configuration_revision = _config_revision(configuration.get("revision"))

    origin = value.get("origin")
    require(type(origin) is dict, "INVALID_CHECKPOINT_ORIGIN")
    require(origin.get("created_run_id") == run_id, "CHECKPOINT_RUN_MISMATCH")
    creation_attempt = _positive_int(origin.get("created_run_attempt"))
    require(creation_attempt <= producer_attempt, "INVALID_CHECKPOINT_ORIGIN")

    operation = value.get("operation")
    action = value.get("action")
    require(
        type(operation) is dict and action in {"created", "reused"}, "INVALID_OPERATION"
    )
    expected_counts = (1, 0) if action == "created" else (0, 1)
    require(
        (operation.get("deployment_create_calls"), operation.get("reused_deployments"))
        == expected_counts,
        "INVALID_OPERATION_COUNTS",
    )
    if action == "created":
        require(creation_attempt == producer_attempt, "INVALID_CHECKPOINT_ORIGIN")
    generated_at = value.get("generated_at")
    _timestamp(generated_at)
    return Checkpoint(
        portal,
        project_id,
        deployment_id,
        candidate_sha,
        configuration_revision,
        run_id,
        producer_attempt,
        creation_attempt,
        action,
        generated_at,
    )


def read_checkpoint_archive(
    archive: bytes,
    artifact: Mapping[str, Any],
    *,
    portal: str,
    run_id: int,
    source_attempt: int,
    candidate_sha: str,
) -> Checkpoint:
    """Authenticate one exact attempt artifact and parse it without extraction."""
    expected_name = checkpoint_artifact_name(portal, run_id, source_attempt)
    require(artifact.get("name") == expected_name, "WRONG_ARTIFACT_KIND")
    require(artifact.get("expired") is False, "ARTIFACT_EXPIRED_OR_UNKNOWN")
    require(
        type(artifact.get("size_in_bytes")) is int
        and 0 < artifact["size_in_bytes"] <= MAX_ARCHIVE_BYTES,
        "ARTIFACT_SIZE_INVALID",
    )
    digest = artifact.get("digest")
    if not isinstance(digest, str) or DIGEST.fullmatch(digest) is None:
        raise CheckpointError("MISSING_ARTIFACT_DIGEST")
    require(0 < len(archive) <= MAX_ARCHIVE_BYTES, "ARCHIVE_SIZE_INVALID")
    require(
        "sha256:" + hashlib.sha256(archive).hexdigest() == digest,
        "ARTIFACT_DIGEST_MISMATCH",
    )

    workflow_run = artifact.get("workflow_run")
    if type(workflow_run) is not dict:
        raise CheckpointError("INVALID_ARTIFACT_PROVENANCE")
    require(
        workflow_run.get("id") == run_id
        and type(workflow_run.get("run_attempt")) is int
        and workflow_run.get("run_attempt") == source_attempt
        and workflow_run.get("head_sha") == candidate_sha
        and workflow_run.get("head_branch") == "staging"
        and workflow_run.get("repository") == REPOSITORY
        and workflow_run.get("repository_id") == REPOSITORY_ID
        and isinstance(workflow_run.get("path"), str)
        and workflow_run.get("path") in RUN_WORKFLOWS,
        "INVALID_ARTIFACT_PROVENANCE",
    )
    source_job = artifact.get("source_job")
    if type(source_job) is not dict:
        raise CheckpointError("INVALID_ARTIFACT_PROVENANCE")
    expected_job = f"Vercel Preview proof ({portal})"
    job_name = source_job.get("name")
    require(
        type(source_job.get("run_attempt")) is int
        and source_job.get("run_attempt") == source_attempt
        and isinstance(job_name, str)
        and (job_name == expected_job or job_name.endswith(f" / {expected_job}"))
        and source_job.get("status") == "completed"
        and source_job.get("conclusion") in {"success", "failure", "cancelled"},
        "INVALID_ARTIFACT_PROVENANCE",
    )
    job_started = _timestamp(source_job.get("started_at"))
    job_completed = _timestamp(source_job.get("completed_at"))
    artifact_created = _timestamp(artifact.get("created_at"))
    require(
        job_started <= artifact_created <= job_completed, "ARTIFACT_ATTEMPT_NOT_BOUND"
    )

    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            entries = bundle.infolist()
            require(len(entries) == 1, "UNEXPECTED_ARCHIVE_ENTRIES")
            entry = entries[0]
            require(
                entry.filename == "deployment-checkpoint.json",
                "UNEXPECTED_ARCHIVE_PATH",
            )
            require(not stat.S_ISLNK(entry.external_attr >> 16), "ARCHIVE_SYMLINK")
            require(not entry.flag_bits & 1, "ENCRYPTED_ARCHIVE")
            require(0 < entry.file_size <= MAX_DOCUMENT_BYTES, "DOCUMENT_SIZE_INVALID")
            value = _loads(bundle.read(entry), max_bytes=MAX_DOCUMENT_BYTES)
    except (zipfile.BadZipFile, RuntimeError):
        raise CheckpointError("INVALID_CHECKPOINT_ARCHIVE") from None
    checkpoint = parse_checkpoint(
        value,
        expected_run_id=run_id,
        expected_producer_attempt=source_attempt,
    )
    generated_at = _timestamp(checkpoint.generated_at)
    require(
        job_started <= generated_at <= artifact_created, "CHECKPOINT_TIME_NOT_BOUND"
    )
    return checkpoint


def assess_reuse(
    checkpoint: Checkpoint,
    live: Mapping[str, Any],
    *,
    portal: str,
    project_id: str,
    candidate_sha: str,
    configuration_revision: str,
    run_id: int,
    current_attempt: int,
) -> ReuseDecision:
    """Return eligibility to re-probe. This never certifies old probe results."""
    _positive_int(run_id)
    _positive_int(current_attempt)
    candidate_sha = _full_sha(candidate_sha)
    configuration_revision = _config_revision(configuration_revision)
    require(portal in PORTALS, "INVALID_PORTAL")
    require(PROJECT_ID.fullmatch(project_id) is not None, "INVALID_PROJECT_ID")
    if (
        checkpoint.producer_run_id != run_id
        or checkpoint.producer_attempt >= current_attempt
    ):
        return create_decision("CHECKPOINT_ATTEMPT_INELIGIBLE", current_attempt)
    if checkpoint.portal != portal:
        return create_decision("CHECKPOINT_PORTAL_MISMATCH", current_attempt)
    if checkpoint.project_id != project_id:
        return create_decision("CHECKPOINT_PROJECT_MISMATCH", current_attempt)
    if checkpoint.candidate_sha != candidate_sha:
        return create_decision("CHECKPOINT_SHA_MISMATCH", current_attempt)
    if checkpoint.configuration_revision != configuration_revision:
        return create_decision("CHECKPOINT_CONFIGURATION_MISMATCH", current_attempt)
    if type(live) is not dict:
        raise CheckpointError("INVALID_VERCEL_METADATA")
    if live.get("id") != checkpoint.deployment_id:
        return create_decision("LIVE_DEPLOYMENT_MISMATCH", current_attempt)
    if live.get("projectId") != project_id:
        return create_decision("LIVE_PROJECT_MISMATCH", current_attempt)
    if (live.get("target") or "preview") != "preview":
        return create_decision("LIVE_TARGET_MISMATCH", current_attempt)
    if live.get("readyState") not in ACTIVE_STATES:
        return create_decision("LIVE_STATE_INELIGIBLE", current_attempt)
    meta = live.get("meta")
    if type(meta) is not dict:
        return create_decision("LIVE_METADATA_MISSING", current_attempt)
    if meta.get("githubCommitSha") != candidate_sha:
        return create_decision("LIVE_SHA_MISMATCH", current_attempt)
    if meta.get("convergeoBuildConfigRevision") != configuration_revision:
        return create_decision("LIVE_CONFIGURATION_MISMATCH", current_attempt)
    if meta.get("convergeoRepositoryId") != str(REPOSITORY_ID):
        return create_decision("LIVE_REPOSITORY_MISMATCH", current_attempt)
    if meta.get("convergeoSourceRunId") != str(run_id):
        return create_decision("LIVE_RUN_MISMATCH", current_attempt)
    if meta.get("convergeoCreationAttempt") != str(checkpoint.creation_attempt):
        return create_decision("LIVE_CREATION_ATTEMPT_MISMATCH", current_attempt)
    return reuse_decision(checkpoint)


def make_checkpoint(
    *,
    portal: str,
    project_id: str,
    deployment_id: str,
    candidate_sha: str,
    configuration_revision: str,
    run_id: int,
    run_attempt: int,
    action: str,
    creation_attempt: int,
    generated_at: str,
) -> dict[str, Any]:
    require(portal in PORTALS, "INVALID_PORTAL")
    require(PROJECT_ID.fullmatch(project_id) is not None, "INVALID_PROJECT_ID")
    require(DEPLOYMENT_ID.fullmatch(deployment_id) is not None, "INVALID_DEPLOYMENT_ID")
    _full_sha(candidate_sha)
    _config_revision(configuration_revision)
    run_id = _positive_int(run_id)
    run_attempt = _positive_int(run_attempt)
    creation_attempt = _positive_int(creation_attempt)
    require(action in {"created", "reused"}, "INVALID_OPERATION")
    require(creation_attempt <= run_attempt, "INVALID_CHECKPOINT_ORIGIN")
    if action == "created":
        require(creation_attempt == run_attempt, "INVALID_CHECKPOINT_ORIGIN")
    _timestamp(generated_at)
    counts = (1, 0) if action == "created" else (0, 1)
    value = {
        "schema_version": SCHEMA_VERSION,
        "evidence_kind": EVIDENCE_KIND,
        "certification_evidence": False,
        "producer": {
            "repository": REPOSITORY,
            "repository_id": REPOSITORY_ID,
            "workflow": WORKFLOW,
            "ref": REF,
            "run_id": run_id,
            "run_attempt": run_attempt,
        },
        "portal": portal,
        "project_id": project_id,
        "deployment_id": deployment_id,
        "candidate_sha": candidate_sha,
        "target": "preview",
        "configuration": {
            "identity_scheme": IDENTITY_SCHEME,
            "revision": configuration_revision,
        },
        "stage": STAGE,
        "action": action,
        "origin": {
            "created_run_id": run_id,
            "created_run_attempt": creation_attempt,
        },
        "operation": {
            "deployment_create_calls": counts[0],
            "reused_deployments": counts[1],
        },
        "generated_at": generated_at,
    }
    parse_checkpoint(
        value, expected_run_id=run_id, expected_producer_attempt=run_attempt
    )
    return value


def fetch_vercel_deployment(
    deployment_id: str,
    *,
    token: str,
    organization_id: str,
) -> Mapping[str, Any]:
    require(DEPLOYMENT_ID.fullmatch(deployment_id) is not None, "INVALID_DEPLOYMENT_ID")
    require(bool(token), "VERCEL_AUTH_UNAVAILABLE")
    require(
        re.fullmatch(r"[A-Za-z0-9_]+", organization_id or "") is not None,
        "INVALID_VERCEL_ORGANIZATION",
    )
    query = urllib.parse.urlencode({"teamId": organization_id})
    request = urllib.request.Request(
        f"https://api.vercel.com/v13/deployments/{deployment_id}?{query}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read(MAX_DOCUMENT_BYTES + 1)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        raise CheckpointError("VERCEL_METADATA_UNAVAILABLE") from None
    value = _loads(raw, max_bytes=MAX_DOCUMENT_BYTES)
    require(type(value) is dict, "INVALID_VERCEL_METADATA")
    return cast(dict[str, Any], value)


def select_reuse(
    *,
    archive: bytes | None,
    artifact: Mapping[str, Any] | None,
    portal: str,
    project_id: str,
    candidate_sha: str,
    configuration_revision: str,
    run_id: int,
    current_attempt: int,
    source_attempt: int | None,
    live_reader: Callable[[str], Mapping[str, Any]],
) -> ReuseDecision:
    if archive is None or artifact is None or source_attempt is None:
        return create_decision("CHECKPOINT_MISSING", current_attempt)
    require(
        _positive_int(source_attempt) < _positive_int(current_attempt),
        "INVALID_SOURCE_ATTEMPT",
    )
    checkpoint = read_checkpoint_archive(
        archive,
        artifact,
        portal=portal,
        run_id=run_id,
        source_attempt=source_attempt,
        candidate_sha=candidate_sha,
    )
    # Static mismatch is a legitimate stale checkpoint, not artifact tampering.
    if checkpoint.portal != portal:
        return create_decision("CHECKPOINT_PORTAL_MISMATCH", current_attempt)
    if checkpoint.project_id != project_id:
        return create_decision("CHECKPOINT_PROJECT_MISMATCH", current_attempt)
    if checkpoint.candidate_sha != candidate_sha:
        return create_decision("CHECKPOINT_SHA_MISMATCH", current_attempt)
    if checkpoint.configuration_revision != configuration_revision:
        return create_decision("CHECKPOINT_CONFIGURATION_MISMATCH", current_attempt)
    live = live_reader(checkpoint.deployment_id)
    return assess_reuse(
        checkpoint,
        live,
        portal=portal,
        project_id=project_id,
        candidate_sha=candidate_sha,
        configuration_revision=configuration_revision,
        run_id=run_id,
        current_attempt=current_attempt,
    )


def _write_json_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except FileExistsError:
        raise CheckpointError("CHECKPOINT_OUTPUT_COLLISION") from None
    except OSError:
        raise CheckpointError("OUTPUT_FILE_UNAVAILABLE") from None


def _selection_json(decision: ReuseDecision) -> dict[str, Any]:
    return asdict(decision)


def _common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--portal", required=True, choices=sorted(PORTALS))
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--configuration-revision", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--run-attempt", required=True, type=int)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    select_parser = subparsers.add_parser("select")
    _common_arguments(select_parser)
    select_parser.add_argument("--archive", type=Path)
    select_parser.add_argument("--artifact-metadata", type=Path)
    select_parser.add_argument("--source-attempt", type=int)
    select_parser.add_argument("--live-metadata", type=Path)
    select_parser.add_argument("--output", required=True, type=Path)
    write_parser = subparsers.add_parser("write")
    _common_arguments(write_parser)
    write_parser.add_argument("--selection", required=True, type=Path)
    write_parser.add_argument("--deployment-id", required=True)
    write_parser.add_argument("--generated-at", required=True)
    write_parser.add_argument("--output", required=True, type=Path)
    current_parser = subparsers.add_parser("validate-current")
    _common_arguments(current_parser)
    current_parser.add_argument("--checkpoint", required=True, type=Path)
    current_parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        if args.command == "select":
            supplied = (args.archive, args.artifact_metadata, args.source_attempt)
            require(
                all(item is None for item in supplied)
                or all(item is not None for item in supplied),
                "INCOMPLETE_CHECKPOINT_INPUT",
            )
            if args.archive is None:
                decision = create_decision("CHECKPOINT_MISSING", args.run_attempt)
            else:
                require(args.archive.is_file(), "ARCHIVE_NOT_FOUND")
                require(
                    0 < args.archive.stat().st_size <= MAX_ARCHIVE_BYTES,
                    "ARCHIVE_SIZE_INVALID",
                )
                archive = args.archive.read_bytes()
                artifact = _read_json(args.artifact_metadata)
                require(type(artifact) is dict, "INVALID_ARTIFACT_METADATA")
                live_reader: Callable[[str], Mapping[str, Any]]
                if args.live_metadata:
                    live_value = _read_json(args.live_metadata)
                    require(type(live_value) is dict, "INVALID_VERCEL_METADATA")

                    def read_static_metadata(
                        _deployment_id: str,
                    ) -> Mapping[str, Any]:
                        return cast(dict[str, Any], live_value)

                    live_reader = read_static_metadata
                else:

                    def read_live_metadata(deployment_id: str) -> Mapping[str, Any]:
                        return fetch_vercel_deployment(
                            deployment_id,
                            token=os.environ.get("VERCEL_TOKEN", ""),
                            organization_id=os.environ.get("VERCEL_ORG_ID", ""),
                        )

                    live_reader = read_live_metadata
                decision = select_reuse(
                    archive=archive,
                    artifact=artifact,
                    portal=args.portal,
                    project_id=args.project_id,
                    candidate_sha=args.candidate_sha,
                    configuration_revision=args.configuration_revision,
                    run_id=args.run_id,
                    current_attempt=args.run_attempt,
                    source_attempt=args.source_attempt,
                    live_reader=live_reader,
                )
            _write_json_exclusive(args.output, _selection_json(decision))
            print(f"checkpoint decision={decision.decision} reason={decision.reason}")
        elif args.command == "write":
            selection = _read_json(args.selection)
            require(type(selection) is dict, "INVALID_SELECTION")
            decision = selection.get("decision")
            require(decision in {"create", "reuse"}, "INVALID_SELECTION")
            expected_counts = (1, 0) if decision == "create" else (0, 1)
            require(
                (
                    selection.get("deployment_create_calls"),
                    selection.get("reused_deployments"),
                )
                == expected_counts,
                "INVALID_OPERATION_COUNTS",
            )
            origin_attempt = _positive_int(selection.get("origin_attempt"))
            selected_id = selection.get("deployment_id")
            require(
                (decision == "create" and selected_id is None)
                or (decision == "reuse" and selected_id == args.deployment_id),
                "SELECTION_DEPLOYMENT_MISMATCH",
            )
            value = make_checkpoint(
                portal=args.portal,
                project_id=args.project_id,
                deployment_id=args.deployment_id,
                candidate_sha=args.candidate_sha,
                configuration_revision=args.configuration_revision,
                run_id=args.run_id,
                run_attempt=args.run_attempt,
                action="created" if decision == "create" else "reused",
                creation_attempt=origin_attempt,
                generated_at=args.generated_at,
            )
            _write_json_exclusive(args.output, value)
            print(
                "checkpoint written stage=PRE_PROBE "
                f"create_calls={expected_counts[0]} reused={expected_counts[1]}"
            )
        else:
            value = _read_json(args.checkpoint)
            checkpoint = parse_checkpoint(
                value,
                expected_run_id=args.run_id,
                expected_producer_attempt=args.run_attempt,
            )
            require(checkpoint.portal == args.portal, "CHECKPOINT_PORTAL_MISMATCH")
            require(
                checkpoint.project_id == args.project_id, "CHECKPOINT_PROJECT_MISMATCH"
            )
            require(
                checkpoint.candidate_sha == args.candidate_sha,
                "CHECKPOINT_SHA_MISMATCH",
            )
            require(
                checkpoint.configuration_revision == args.configuration_revision,
                "CHECKPOINT_CONFIGURATION_MISMATCH",
            )
            _write_json_exclusive(
                args.output,
                {
                    "deployment_id": checkpoint.deployment_id,
                    "decision": checkpoint.action,
                    "origin_attempt": checkpoint.creation_attempt,
                    "deployment_create_calls": 1
                    if checkpoint.action == "created"
                    else 0,
                    "reused_deployments": 1 if checkpoint.action == "reused" else 0,
                },
            )
            print("current checkpoint validated for fresh probes")
    except (CheckpointError, OSError) as exc:
        code = (
            str(exc) if isinstance(exc, CheckpointError) else "INPUT_FILE_UNAVAILABLE"
        )
        print(f"::error::deployment checkpoint rejected: {code}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
