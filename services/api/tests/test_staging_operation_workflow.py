from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]

REPO_ROOT = Path(__file__).resolve().parents[3]


def load_workflow(name: str) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        yaml.load(
            (REPO_ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"),
            Loader=yaml.BaseLoader,
        ),
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


def test_sms_attestation_blocks_protected_graph_before_deploy() -> None:
    outer = load_workflow("staging-operation.yml")
    steps = outer["jobs"]["authorize"]["steps"]
    guard = next(step for step in steps if step.get("name", "").startswith("Require SMS sandbox"))
    assert guard["env"]["STAGING_SMS_SANDBOX_ATTESTED"] == (
        "${{ vars.STAGING_SMS_SANDBOX_ATTESTED }}"
    )
    assert guard["env"]["STAGING_TEST_OTP_MAP_ATTESTED"] == (
        "${{ vars.STAGING_TEST_OTP_MAP_ATTESTED }}"
    )
    assert "exit 1" in guard["run"]
    assert outer["jobs"]["deploy"]["needs"] == "authorize"


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
    assert completion["if"] == "${{ always() && inputs.focus_group != 'email-diagnostic' }}"
    assert "email_diagnostic" not in completion["needs"]
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


def test_email_path_is_manual_only_and_excluded_from_release_graph() -> None:
    outer = load_workflow("staging-operation.yml")
    email = load_workflow("staging-email-diagnostic.yml")
    assert set(email["on"]) == {"workflow_call"}
    assert outer["on"]["push"]["branches"] == ["staging"]
    assert (
        "email-diagnostic" in outer["on"]["workflow_dispatch"]["inputs"]["focus_group"]["options"]
    )
    assert len(outer["on"]["workflow_dispatch"]["inputs"]) <= 10
    for name in ("deploy", "e2e", "certify", "completion"):
        assert "inputs.focus_group != 'email-diagnostic'" in outer["jobs"][name]["if"]
    job = outer["jobs"]["email_diagnostic"]
    assert job["needs"] == "authorize"
    assert job["uses"] == "./.github/workflows/staging-email-diagnostic.yml"
    assert job["permissions"] == {"actions": "read", "contents": "read"}
    assert "concurrency" not in email
    assert email["jobs"]["diagnostic"]["environment"] == "staging"


def test_email_secrets_are_minimal_and_scoped_after_provenance_to_browser_step() -> None:
    outer = load_workflow("staging-operation.yml")
    email = load_workflow("staging-email-diagnostic.yml")
    expected = {
        "E2E_CUSTOMER_EMAIL_PASSWORD",
        "E2E_VENDOR_EMAIL_PASSWORD",
        "VERCEL_AUTOMATION_BYPASS_SECRET_CUSTOMER",
        "VERCEL_AUTOMATION_BYPASS_SECRET_VENDOR",
        "VERCEL_AUTOMATION_BYPASS_SECRET",
        "VERCEL_PROJECT_ID_CUSTOMER",
        "VERCEL_PROJECT_ID_VENDOR",
        "VERCEL_PROJECT_ID_ADMIN",
    }
    assert set(outer["jobs"]["email_diagnostic"]["secrets"]) == expected
    assert set(email["on"]["workflow_call"]["secrets"]) == expected
    assert "env" not in email and "env" not in email["jobs"]["diagnostic"]
    steps = email["jobs"]["diagnostic"]["steps"]
    browser = next(step for step in steps if step.get("name", "").startswith("Probe exact portals"))
    provenance = next(
        step for step in steps if step.get("name", "").startswith("Validate exact deployment")
    )
    assert steps.index(provenance) < steps.index(browser)
    for step in steps:
        if step is not browser:
            env = step.get("env", {})
            assert "E2E_CUSTOMER_EMAIL_PASSWORD" not in env
            assert "E2E_VENDOR_EMAIL_PASSWORD" not in env
            assert not any(name.startswith("VERCEL_AUTOMATION_BYPASS_SECRET") for name in env)
    assert browser["run"] == "node --experimental-strip-types scripts/ci/run-email-acceptance.mjs"
    assert "SUPABASE_SERVICE_ROLE_KEY" not in str(email)
    assert "upload-artifact" not in str(email)
    assert "download-artifact" not in str(email)
    assert "seed_staging.py" not in str(email)


def test_email_checks_source_and_ref_before_and_after_then_always_cleans_private_files() -> None:
    email = load_workflow("staging-email-diagnostic.yml")
    steps = email["jobs"]["diagnostic"]["steps"]
    assert steps[0]["with"] == {
        "ref": "${{ inputs.candidate_sha }}",
        "persist-credentials": "false",
    }
    before = next(
        step for step in steps if step.get("name", "").startswith("Recheck staging ref before")
    )
    after = next(
        step for step in steps if step.get("name", "").startswith("Recheck staging ref after")
    )
    browser = next(step for step in steps if step.get("name", "").startswith("Probe exact portals"))
    cleanup = next(
        step for step in steps if step.get("name", "").startswith("Remove private diagnostic")
    )
    assert steps.index(before) < steps.index(browser) < steps.index(after) < steps.index(cleanup)
    assert after["if"] == cleanup["if"] == "${{ always() }}"
    for step in (before, after):
        assert "ref: 'heads/staging'" in step["with"]["script"]
        assert "catch" in step["with"]["script"]
        assert "data.object.sha !== process.env.CANDIDATE_SHA" in step["with"]["script"]
    assert '"${RUNNER_TEMP}/email-diagnostic-source"' in cleanup["run"]
    assert "e2e/test-results e2e/playwright-report" in cleanup["run"]


def test_email_completion_exists_even_when_authorization_or_diagnostic_is_skipped() -> None:
    outer = load_workflow("staging-operation.yml")
    completion = outer["jobs"]["email_completion"]
    assert completion["needs"] == ["authorize", "email_diagnostic"]
    assert completion["if"] == "${{ always() && inputs.focus_group == 'email-diagnostic' }}"
    assert "--completion-summary" in str(completion["steps"])
    assert "secrets." not in str(completion)
    assert "environment" not in completion
    assert "actions/upload-artifact" not in str(completion)
    assert "Record diagnostic scope" not in str(load_workflow("staging-email-diagnostic.yml"))


def run_guard(
    source: str, overrides: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": "/usr/bin:/bin",
        "GITHUB_REPOSITORY": "KaluMuso/Convergeo",
        "REPOSITORY_ID": "1290591718",
        "GITHUB_REF": "refs/heads/staging",
        "GITHUB_SHA": "a" * 40,
        "GITHUB_RUN_ID": "101",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "EMAIL_CANDIDATE_SHA": "a" * 40,
        "EMAIL_SOURCE_RUN_ID": "901",
        "EMAIL_SOURCE_RUN_ATTEMPT": "1",
        "EMAIL_SOURCE_ARTIFACT_ID": "777",
        "CANDIDATE_SHA": "a" * 40,
        "SOURCE_RUN_ID": "901",
        "SOURCE_RUN_ATTEMPT": "1",
        "SOURCE_ARTIFACT_ID": "777",
        "INTERNAL_OPERATION_ID": "1290591718:101:1:" + "a" * 40,
        "CALLER_WORKFLOW_SHA": "a" * 40,
        "CALLER_WORKFLOW_REF": (
            "KaluMuso/Convergeo/.github/workflows/staging-operation.yml@refs/heads/staging"
        ),
        "OWNER_PROVISIONED_READINESS": "ready",
        "PHONE_TRANSPORT_READINESS": "disabled",
        "PAYMENT_OUTBOUND_READINESS": "verified-safe",
        "SMS_OTP_TRANSPORT": "waha",
        "WAHA_OTP_ENABLED": "true",
        "STAGING_SMS_SANDBOX_ATTESTED": "true",
        "STAGING_TEST_OTP_MAP_ATTESTED": "true",
    }
    env.update(overrides or {})
    return subprocess.run(
        ["bash", "-s"],
        input=source,
        env=env,
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )


def test_authorization_shell_guards_pass_only_with_complete_synthetic_contract() -> None:
    for name in ("staging-operation.yml", "staging-email-diagnostic.yml"):
        for step in load_workflow(name)["jobs"]["authorize"]["steps"]:
            result = run_guard(step["run"])
            assert result.returncode == 0, result.stderr


def test_child_authorization_rejects_every_wrong_caller_scope_readiness_and_source_boundary() -> (
    None
):
    guard = load_workflow("staging-email-diagnostic.yml")["jobs"]["authorize"]["steps"][0]["run"]
    changes = {
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_REPOSITORY": "attacker/Convergeo",
        "REPOSITORY_ID": "1",
        "GITHUB_REF": "refs/heads/master",
        "GITHUB_SHA": "b" * 40,
        "CALLER_WORKFLOW_SHA": "b" * 40,
        "CALLER_WORKFLOW_REF": "other-workflow",
        "INTERNAL_OPERATION_ID": "wrong",
        "CANDIDATE_SHA": "a" * 12,
        "SOURCE_RUN_ID": "0",
        "SOURCE_RUN_ATTEMPT": "0",
        "SOURCE_ARTIFACT_ID": "0",
        "OWNER_PROVISIONED_READINESS": "not-ready",
        "PHONE_TRANSPORT_READINESS": "unverified",
        "PAYMENT_OUTBOUND_READINESS": "unverified",
    }
    for key, value in changes.items():
        result = run_guard(guard, {key: value})
        assert result.returncode != 0, key
        assert value not in result.stdout or value in ("0", "1", "push"), key


def test_parent_email_guard_refuses_auto_event_wrong_sha_missing_artifact_and_readiness() -> None:
    guard = next(
        step["run"]
        for step in load_workflow("staging-operation.yml")["jobs"]["authorize"]["steps"]
        if step.get("name", "").startswith("Require explicit email")
    )
    for key, value in (
        ("GITHUB_EVENT_NAME", "push"),
        ("EMAIL_CANDIDATE_SHA", "b" * 40),
        ("EMAIL_SOURCE_RUN_ID", "0"),
        ("EMAIL_SOURCE_RUN_ATTEMPT", "0"),
        ("EMAIL_SOURCE_ARTIFACT_ID", "0"),
        ("OWNER_PROVISIONED_READINESS", "not-ready"),
        ("PHONE_TRANSPORT_READINESS", "unverified"),
        ("PAYMENT_OUTBOUND_READINESS", "unverified"),
    ):
        result = run_guard(guard, {key: value})
        assert result.returncode != 0, key


def test_ordinary_phone_guard_requires_all_four_attestations_without_activating_them() -> None:
    guard = next(
        step["run"]
        for step in load_workflow("staging-operation.yml")["jobs"]["authorize"]["steps"]
        if step.get("name", "").startswith("Require SMS sandbox")
    )
    assert "inputs.focus_group != 'email-diagnostic'" in str(load_workflow("staging-operation.yml"))
    for key in (
        "SMS_OTP_TRANSPORT",
        "WAHA_OTP_ENABLED",
        "STAGING_SMS_SANDBOX_ATTESTED",
        "STAGING_TEST_OTP_MAP_ATTESTED",
    ):
        result = run_guard(guard, {key: "private-sentinel"})
        assert result.returncode != 0
        assert "private-sentinel" not in result.stdout + result.stderr
    assert "export " not in guard


def test_ordinary_guard_uses_the_accepted_enabled_flag_and_not_an_unrelated_ready_flag() -> None:
    guard = next(
        step
        for step in load_workflow("staging-operation.yml")["jobs"]["authorize"]["steps"]
        if step.get("name", "").startswith("Require SMS sandbox")
    )
    assert guard["env"]["WAHA_OTP_ENABLED"] == "${{ vars.WAHA_OTP_ENABLED || 'false' }}"
    assert "WAHA_OTP_READY" not in guard["env"]
    result = run_guard(guard["run"], {"WAHA_OTP_ENABLED": "false", "WAHA_OTP_READY": "true"})
    assert result.returncode != 0
    assert run_guard(guard["run"]).returncode == 0
