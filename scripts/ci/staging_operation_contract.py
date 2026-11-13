#!/usr/bin/env python3
"""Render one sanitized completion record for the protected staging operation."""

from __future__ import annotations

import argparse
import re
from collections.abc import Mapping
from pathlib import Path

SHA = re.compile(r"[0-9a-f]{40}\Z")
SCOPES = frozenset(
    {"full", "previous-six", "cart", "vendor-auth", "checkout-honesty", "performance"}
)
RAW_RESULTS = frozenset(
    {
        "",
        "success",
        "failure",
        "cancelled",
        "skipped",
        "pending",
        "queued",
        "in_progress",
    }
)


def positive_identity(raw: str) -> str:
    return raw if raw.isdigit() and int(raw) > 0 else "UNKNOWN"


def bounded_count(raw: str) -> int | str:
    return int(raw) if raw.isdigit() and 0 <= int(raw) <= 3 else "UNKNOWN"


def classify(raw: str, *, parent: str = "") -> str:
    if raw not in RAW_RESULTS:
        return "UNKNOWN"
    if raw == "success":
        return "PASS"
    if raw == "failure":
        return "FAIL"
    if raw == "skipped":
        return "NOT_RUN"
    if raw in {"cancelled", "pending", "queued", "in_progress"}:
        return "UNKNOWN"
    if parent in {"cancelled", "pending", "queued", "in_progress"}:
        return "UNKNOWN"
    return "NOT_RUN"


def build_record(
    *,
    candidate: str,
    scope: str,
    run_id: str,
    run_attempt: str,
    source_artifact_id: str,
    create_calls: str,
    reused_deployments: str,
    deploy_result: str,
    e2e_result: str,
    handoff_status: str,
    outcomes: Mapping[str, str],
) -> dict[str, object]:
    safe_candidate = candidate if SHA.fullmatch(candidate or "") else "UNKNOWN"
    safe_scope = scope if scope in SCOPES else "UNKNOWN"
    safe_run_id = positive_identity(run_id)
    safe_attempt = positive_identity(run_attempt)
    safe_artifact_id = positive_identity(source_artifact_id)
    safe_create_calls = bounded_count(create_calls)
    safe_reused_deployments = bounded_count(reused_deployments)
    counts_valid = (
        type(safe_create_calls) is int
        and type(safe_reused_deployments) is int
        and safe_create_calls + safe_reused_deployments == 3
    )
    deployment = classify(deploy_result)
    if (
        handoff_status == "PASS"
        and deploy_result == "success"
        and safe_artifact_id != "UNKNOWN"
    ):
        manifest = "PASS"
    elif handoff_status not in {"", "PASS"} or (
        handoff_status == "PASS" and safe_artifact_id == "UNKNOWN"
    ):
        manifest = "FAIL"
    else:
        manifest = classify("", parent=deploy_result)
    proofs = {
        "Shared staging exclusion": classify(
            outcomes.get("lock", ""), parent=deploy_result
        ),
        "Deploy and staging proof": deployment,
        "Deployment create/reuse accounting": "PASS" if counts_valid else "UNKNOWN",
        "Authenticated manifest handoff": manifest,
        "Current staging ref": classify(
            outcomes.get("staging_ref", ""), parent=e2e_result
        ),
        "Customer exact full SHA": classify(
            outcomes.get("customer", ""), parent=e2e_result
        ),
        "Vendor exact full SHA": classify(
            outcomes.get("vendor", ""), parent=e2e_result
        ),
        "Canonical setup": classify(outcomes.get("setup", ""), parent=e2e_result),
        "Browser execution": classify(outcomes.get("browser", ""), parent=e2e_result),
        "Execution guard": classify(outcomes.get("execution", ""), parent=e2e_result),
        "Matrix completeness": classify(outcomes.get("matrix", ""), parent=e2e_result),
        "Private material cleanup": classify(
            outcomes.get("cleanup", ""), parent=e2e_result
        ),
    }
    failed_boundary = "none"
    for name, result in proofs.items():
        if result != "PASS":
            failed_boundary = name
            break
    release_eligible = (
        safe_candidate != "UNKNOWN"
        and safe_scope == "full"
        and safe_run_id != "UNKNOWN"
        and safe_attempt != "UNKNOWN"
        and deploy_result == "success"
        and e2e_result == "success"
        and safe_artifact_id != "UNKNOWN"
        and counts_valid
        and all(result == "PASS" for result in proofs.values())
    )
    return {
        "candidate": safe_candidate,
        "scope": safe_scope,
        "run_id": safe_run_id,
        "run_attempt": safe_attempt,
        "source_artifact_id": safe_artifact_id,
        "deployment_create_calls": safe_create_calls,
        "reused_deployments": safe_reused_deployments,
        "deploy_result": classify(deploy_result),
        "e2e_result": classify(e2e_result),
        "proofs": proofs,
        "failed_boundary": failed_boundary,
        "release_eligible": release_eligible,
    }


def render(record: Mapping[str, object]) -> str:
    proofs = record["proofs"]
    assert isinstance(proofs, dict)
    run_id = str(record["run_id"])
    run_attempt = str(record["run_attempt"])
    lines = [
        "## Protected staging operation completion",
        "",
        f"- Candidate: `{record['candidate']}`",
        f"- Selected scope: `{record['scope']}`",
        f"- Run/attempt: `{run_id}/{run_attempt}`",
        f"- Source artifact: `{record['source_artifact_id']}`",
        (
            "- Deployment create/reuse counts: "
            f"`{record['deployment_create_calls']}/{record['reused_deployments']}`"
        ),
        "- Current phase: `complete`",
        f"- Deploy/E2E result: `{record['deploy_result']}/{record['e2e_result']}`",
        f"- Failed boundary: `{record['failed_boundary']}`",
        f"- Release eligible: `{'YES' if record['release_eligible'] else 'NO'}`",
        "",
        "| Proof | Result |",
        "|---|---|",
    ]
    lines.extend(f"| {name} | {result} |" for name, result in proofs.items())
    lines.extend(
        [
            "",
            (
                "Artifacts: "
                f"`staging-sha-proof-{run_id}-attempt-{run_attempt}` and "
                f"`playwright-artifacts-{run_id}-attempt-{run_attempt}` when uploaded."
            ),
            "Approval/completion notification: GitHub's protected `staging` environment and native workflow completion.",
        ]
    )
    cleanup = proofs["Private material cleanup"]
    if record["release_eligible"]:
        lines.append(
            "Next owned action: coordinator review; no production promotion was performed."
        )
    elif cleanup == "UNKNOWN":
        lines.append(
            "Next owned action: inspect retained evidence and perform separately authorized synthetic recovery cleanup if required."
        )
    else:
        lines.append(
            "Next owned action: inspect the failed boundary; this attempt is not release-eligible."
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--scope", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--source-artifact-id", default="")
    parser.add_argument("--create-calls", default="")
    parser.add_argument("--reused-deployments", default="")
    parser.add_argument("--deploy-result", required=True)
    parser.add_argument("--e2e-result", required=True)
    parser.add_argument("--handoff-status", default="")
    for name in (
        "lock",
        "staging-ref",
        "customer",
        "vendor",
        "setup",
        "browser",
        "execution",
        "matrix",
        "cleanup",
    ):
        parser.add_argument(f"--{name}", default="")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    record = build_record(
        candidate=args.candidate,
        scope=args.scope,
        run_id=args.run_id,
        run_attempt=args.run_attempt,
        source_artifact_id=args.source_artifact_id,
        create_calls=args.create_calls,
        reused_deployments=args.reused_deployments,
        deploy_result=args.deploy_result,
        e2e_result=args.e2e_result,
        handoff_status=args.handoff_status,
        outcomes={
            "lock": args.lock,
            "staging_ref": args.staging_ref,
            "customer": args.customer,
            "vendor": args.vendor,
            "setup": args.setup,
            "browser": args.browser,
            "execution": args.execution,
            "matrix": args.matrix,
            "cleanup": args.cleanup,
        },
    )
    with args.output.open("a", encoding="utf-8") as handle:
        handle.write(render(record))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
