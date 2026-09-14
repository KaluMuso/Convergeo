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
    assert deploy_jobs["release-handoff"]["needs"] == ["smoke"]
    assert "needs.smoke.result == 'success'" in deploy_jobs["release-handoff"]["if"]
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
