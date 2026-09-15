from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]


def load_workflow(name: str) -> dict[str, object]:
    return yaml.load(
        (REPO_ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )


def test_outer_workflow_holds_one_lock_across_ordered_reusable_jobs() -> None:
    workflow = load_workflow("staging-operation.yml")
    assert workflow["concurrency"] == {
        "group": "staging-operation",
        "cancel-in-progress": "false",
    }
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    assert jobs["deploy"]["uses"] == "./.github/workflows/deploy-staging.yml"
    assert jobs["e2e"]["uses"] == "./.github/workflows/e2e.yml"
    assert jobs["e2e"]["needs"] == "deploy"
    triggers = workflow["on"]
    assert isinstance(triggers, dict) and "push" in triggers and "workflow_dispatch" in triggers


def test_failure_edges_block_handoff_and_e2e() -> None:
    outer = load_workflow("staging-operation.yml")
    deploy = load_workflow("deploy-staging.yml")
    outer_jobs = outer["jobs"]
    deploy_jobs = deploy["jobs"]
    assert "needs.deploy.result == 'success'" in outer_jobs["e2e"]["if"]
    assert "needs.deploy.outputs.handoff_status == 'PASS'" in outer_jobs["e2e"]["if"]
    assert deploy_jobs["release_handoff"]["needs"] == ["smoke"]
    assert "needs.smoke.result == 'success'" in deploy_jobs["release_handoff"]["if"]
    deploy_triggers = deploy["on"]
    assert isinstance(deploy_triggers, dict) and "push" not in deploy_triggers


def test_nested_workflows_do_not_reacquire_or_cancel_parent_lock() -> None:
    deploy = load_workflow("deploy-staging.yml")
    e2e = load_workflow("e2e.yml")
    for workflow, expected in (
        (deploy, "staging-deploy-nested-{0}"),
        (e2e, "staging-e2e-nested-{0}"),
    ):
        concurrency = workflow["concurrency"]
        assert isinstance(concurrency, dict)
        assert expected in concurrency["group"]
        assert "staging-operation" in concurrency["group"]
        assert concurrency["cancel-in-progress"] == "false"


def test_internal_contract_binds_caller_called_run_attempt_and_sha() -> None:
    for name in ("deploy-staging.yml", "e2e.yml"):
        text = (REPO_ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
        assert "${{ github.workflow_ref }}" in text
        assert "${{ job.workflow_ref }}" in text
        assert "${REPOSITORY_ID}:${GITHUB_RUN_ID}:${GITHUB_RUN_ATTEMPT}:${GITHUB_SHA}" in text
        assert "skip_lock" not in text.lower()
        assert "cancel-in-progress: true" not in text


def test_completion_record_runs_after_both_terminal_paths_without_masking_them() -> None:
    workflow = load_workflow("staging-operation.yml")
    completion = workflow["jobs"]["completion"]
    assert set(completion["needs"]) == {"authorize", "deploy", "e2e"}
    assert completion["if"] == "${{ always() }}"
    source = (REPO_ROOT / ".github" / "workflows" / "staging-operation.yml").read_text(
        encoding="utf-8"
    )
    assert "This reporting job never replaces the deploy/E2E conclusions" in source


def test_scheduled_manual_and_outer_competitors_share_the_same_lock() -> None:
    outer = load_workflow("staging-operation.yml")
    deploy = load_workflow("deploy-staging.yml")
    e2e = load_workflow("e2e.yml")
    assert "schedule" in e2e["on"]
    assert "workflow_dispatch" in e2e["on"]
    assert "workflow_dispatch" in deploy["on"]
    assert {"push", "workflow_dispatch"}.issubset(outer["on"])
    assert "staging-operation" in deploy["concurrency"]["group"]
    assert "staging-operation" in e2e["concurrency"]["group"]
    assert outer["concurrency"]["group"] == "staging-operation"


def test_completion_wires_exact_identity_counts_and_never_runs_recovery_mutations() -> None:
    outer = load_workflow("staging-operation.yml")
    deploy = load_workflow("deploy-staging.yml")
    completion = outer["jobs"]["completion"]
    source = (REPO_ROOT / ".github" / "workflows" / "staging-operation.yml").read_text(
        encoding="utf-8"
    )
    for name in (
        "source_artifact_id",
        "deployment_create_calls",
        "reused_deployments",
    ):
        assert name in deploy["on"]["workflow_call"]["outputs"]
        assert name in deploy["jobs"]["release_handoff"]["outputs"]
    assert "needs.authorize.result" in str(completion["steps"])
    assert "--source-artifact-id" in source
    assert "--create-calls" in source
    assert "--reused-deployments" in source
    assert "seed_staging.py" not in source
    assert "vercel deploy" not in source
