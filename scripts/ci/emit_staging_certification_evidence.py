#!/usr/bin/env python3
"""Emit immutable staging certification evidence for GitHub Actions artifacts."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from github_actions_provenance import LiveGitHubActionsClient
from staging_certification_evidence import ARTIFACT_FILENAME, build_staging_certification_evidence
from staging_deploy_provenance import (
    StagingDeployProvenanceError,
    discover_certifiable_deploy_run,
    download_staging_sha_proof,
    validate_staging_sha_proof_for_certification,
    verify_certifiable_deploy_run,
)
from staging_operation_certification import (
    build_operation_certification_evidence,
    read_operation_source,
)

OUTCOME_NAMES = (
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
)


def _load_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def _load_json_array(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{path.name} must contain an array of JSON objects")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--certification-run-id", required=True)
    parser.add_argument("--certification-run-attempt", type=int, required=True)
    parser.add_argument(
        "--staging-deploy-workflow-run-id",
        default="",
        help="Optional explicit certifiable deploy-staging push run id",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("staging-certification-evidence"),
    )
    parser.add_argument(
        "--certified-at",
        default=datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    )
    parser.add_argument(
        "--proof-fixture-file",
        type=Path,
        default=None,
        help="Legacy offline regression mode: read staging-sha-proof JSON from file",
    )
    parser.add_argument(
        "--operation-metadata-dir",
        type=Path,
        default=None,
        help="Authenticated staging-operation metadata written by github_handoff_metadata.cjs",
    )
    parser.add_argument("--focus-group", default="")
    for outcome in OUTCOME_NAMES:
        parser.add_argument(
            f"--{outcome.replace('_', '-')}-outcome",
            dest=f"{outcome}_outcome",
            default="",
        )
    args = parser.parse_args(argv)

    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()

    try:
        if args.operation_metadata_dir is not None:
            metadata_dir = args.operation_metadata_dir
            run = _load_json_object(metadata_dir / "run.json")
            artifact = _load_json_object(metadata_dir / "artifact.json")
            jobs = _load_json_array(metadata_dir / "jobs.json")
            archive = (metadata_dir / "proof.zip").read_bytes()
            proof, run_id, attempt = read_operation_source(
                archive=archive,
                run=run,
                artifact=artifact,
                jobs=jobs,
                candidate_sha=args.candidate_sha,
            )
            if run_id != int(args.certification_run_id):
                raise ValueError("operation run id does not match certification run id")
            if attempt != args.certification_run_attempt:
                raise ValueError("operation attempt does not match certification attempt")
            evidence = build_operation_certification_evidence(
                candidate_sha=args.candidate_sha,
                run=run,
                source_artifact=artifact,
                proof=proof,
                jobs=jobs,
                focus_group=args.focus_group,
                outcomes={
                    outcome: str(getattr(args, f"{outcome}_outcome"))
                    for outcome in OUTCOME_NAMES
                },
                certified_at=args.certified_at,
            )
        else:
            if args.proof_fixture_file is not None:
                proof = json.loads(args.proof_fixture_file.read_text(encoding="utf-8"))
                deploy_run_id = args.staging_deploy_workflow_run_id.strip() or "111111111"
            else:
                if not repository or not token:
                    print(
                        "::error::GITHUB_REPOSITORY and GITHUB_TOKEN required",
                        file=sys.stderr,
                    )
                    return 1
                client = LiveGitHubActionsClient(repository=repository, token=token)
                if args.staging_deploy_workflow_run_id.strip():
                    deploy_run = client.get_run(args.staging_deploy_workflow_run_id.strip())
                    verify_certifiable_deploy_run(deploy_run, candidate_sha=args.candidate_sha)
                    deploy_run_id = str(deploy_run["id"])
                else:
                    deploy_run = discover_certifiable_deploy_run(
                        client,
                        candidate_sha=args.candidate_sha,
                    )
                    deploy_run_id = str(deploy_run["id"])
                proof = download_staging_sha_proof(client, deploy_run_id=deploy_run_id)

            derived = validate_staging_sha_proof_for_certification(
                proof,
                candidate_sha=args.candidate_sha,
            )
            evidence = build_staging_certification_evidence(
                derived=derived,
                staging_deploy_workflow_run_id=deploy_run_id,
                certification_workflow_run_id=args.certification_run_id,
                certification_run_attempt=args.certification_run_attempt,
                certified_at=args.certified_at,
            )
    except (StagingDeployProvenanceError, ValueError, RuntimeError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.output_dir / ARTIFACT_FILENAME
    out_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
