from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
import staging_operation_contract as operation  # noqa: E402

SHA = "a" * 40
PASS_OUTCOMES = {
    "lock": "success",
    "staging_ref": "success",
    "customer": "success",
    "vendor": "success",
    "setup": "success",
    "browser": "success",
    "execution": "success",
    "matrix": "success",
    "cleanup": "success",
}


def record(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "candidate": SHA,
        "scope": "full",
        "run_id": "42",
        "run_attempt": "3",
        "source_artifact_id": "20",
        "create_calls": "3",
        "reused_deployments": "0",
        "deploy_result": "success",
        "e2e_result": "success",
        "handoff_status": "PASS",
        "outcomes": PASS_OUTCOMES,
    }
    values.update(overrides)
    return operation.build_record(**values)  # type: ignore[arg-type]


def test_successful_full_operation_is_release_eligible_once() -> None:
    result = record()
    assert result["release_eligible"] is True
    summary = operation.render(result)
    assert summary.count("## Protected staging operation completion") == 1
    assert "Release eligible: `YES`" in summary
    assert "Source artifact: `20`" in summary
    assert "Deployment create/reuse counts: `3/0`" in summary
    assert "native workflow completion" in summary


@pytest.mark.parametrize("result", ["failure", "cancelled", "skipped", "pending"])
def test_non_successful_deploy_never_becomes_release_eligible(result: str) -> None:
    value = record(deploy_result=result, e2e_result="skipped", handoff_status="")
    assert value["release_eligible"] is False
    assert value["proofs"]["Deploy and staging proof"] != "PASS"  # type: ignore[index]


def test_interrupted_cleanup_is_unknown_and_requests_separate_recovery() -> None:
    outcomes = dict(PASS_OUTCOMES)
    outcomes["cleanup"] = ""
    value = record(e2e_result="cancelled", outcomes=outcomes)
    assert value["proofs"]["Private material cleanup"] == "UNKNOWN"  # type: ignore[index]
    assert "separately authorized synthetic recovery cleanup" in operation.render(value)


@pytest.mark.parametrize(
    ("create_calls", "reused_deployments"),
    [("", ""), ("2", "0"), ("4", "-1"), ("secret", "0")],
)
def test_missing_or_tampered_counts_never_certify(
    create_calls: str, reused_deployments: str
) -> None:
    value = record(create_calls=create_calls, reused_deployments=reused_deployments)
    assert value["release_eligible"] is False
    assert value["proofs"]["Deployment create/reuse accounting"] == "UNKNOWN"  # type: ignore[index]


@pytest.mark.parametrize("lock", ["", "cancelled", "failure", "in_progress"])
def test_lock_loss_or_unproven_lock_never_certifies(lock: str) -> None:
    outcomes = dict(PASS_OUTCOMES)
    outcomes["lock"] = lock
    value = record(outcomes=outcomes)
    assert value["release_eligible"] is False
    assert value["proofs"]["Shared staging exclusion"] != "PASS"  # type: ignore[index]


@pytest.mark.parametrize("e2e_result", ["failure", "cancelled", "pending"])
def test_timeout_or_interruption_never_certifies(e2e_result: str) -> None:
    assert record(e2e_result=e2e_result)["release_eligible"] is False


def test_abandoned_setup_requires_separately_authorized_recovery() -> None:
    outcomes = dict(PASS_OUTCOMES)
    outcomes["cleanup"] = ""
    value = record(e2e_result="cancelled", outcomes=outcomes)
    assert value["release_eligible"] is False
    assert "separately authorized synthetic recovery cleanup" in operation.render(value)


def test_diagnostic_subset_cannot_certify_even_when_every_proof_passes() -> None:
    assert record(scope="vendor-auth")["release_eligible"] is False


@pytest.mark.parametrize(
    ("field", "value"),
    [("candidate", "a" * 12), ("run_id", "0"), ("run_attempt", "UNKNOWN")],
)
def test_inexact_operation_identity_never_certifies(field: str, value: str) -> None:
    assert record(**{field: value})["release_eligible"] is False


def test_outer_always_invokes_one_summary_without_external_messaging_credentials() -> None:
    text = (REPO_ROOT / ".github" / "workflows" / "staging-operation.yml").read_text(
        encoding="utf-8"
    )
    assert text.count("name: One sanitized operation completion") == 1
    assert "if: ${{ always() }}" in text
    assert "staging_operation_contract.py" in text
    assert "SLACK_" not in text and "WHATSAPP_TOKEN" not in text
