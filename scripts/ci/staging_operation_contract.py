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
    deploy_result: str,
    e2e_result: str,
    handoff_status: str,
    outcomes: Mapping[str, str],
) -> dict[str, object]:
    safe_candidate = candidate if SHA.fullmatch(candidate or "") else "UNKNOWN"
    safe_scope = scope if scope in SCOPES else "UNKNOWN"
    safe_run_id = run_id if run_id.isdigit() and int(run_id) > 0 else "UNKNOWN"
    safe_attempt = (
        run_attempt if run_attempt.isdigit() and int(run_attempt) > 0 else "UNKNOWN"
    )
    deployment = classify(deploy_result)
    if handoff_status == "PASS" and deploy_result == "success":
        manifest = "PASS"
    elif handoff_status not in {"", "PASS"}:
        manifest = "FAIL"
    else:
        manifest = classify("", parent=deploy_result)
    proofs = {
        "Deploy and staging proof": deployment,
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
        if result in {"FAIL", "UNKNOWN"}:
            failed_boundary = name
            break
    release_eligible = (
        safe_scope == "full"
        and deploy_result == "success"
        and e2e_result == "success"
        and all(result == "PASS" for result in proofs.values())
    )
    return {
        "candidate": safe_candidate,
        "scope": safe_scope,
        "run_id": safe_run_id,
        "run_attempt": safe_attempt,
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
    parser.add_argument("--deploy-result", required=True)
    parser.add_argument("--e2e-result", required=True)
    parser.add_argument("--handoff-status", default="")
    for name in (
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
        deploy_result=args.deploy_result,
        e2e_result=args.e2e_result,
        handoff_status=args.handoff_status,
        outcomes={
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
