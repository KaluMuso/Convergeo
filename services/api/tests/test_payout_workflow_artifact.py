"""Static safety contract for the founder-gated payout n8n workflow."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

_REPO_ROOT = Path(__file__).resolve().parents[3]
_WORKFLOW_PATH = _REPO_ROOT / "infra" / "n8n" / "payouts.json"
_PRODUCTION_ENV_EXAMPLE = _REPO_ROOT / "infra" / ".env.example"
_STAGING_ENV_EXAMPLE = _REPO_ROOT / "infra" / "staging" / ".env.staging.example"


def _workflow() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(_WORKFLOW_PATH.read_text(encoding="utf-8")),
    )


def _nodes_by_name(workflow: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(node["name"]): node for node in workflow["nodes"]}


def _next_node(workflow: dict[str, Any], node_name: str) -> str:
    return str(workflow["connections"][node_name]["main"][0][0]["node"])


def test_payout_workflow_is_inactive_bounded_and_serial() -> None:
    workflow = _workflow()
    nodes = _nodes_by_name(workflow)

    assert workflow["active"] is False
    assert workflow["settings"]["executionTimeout"] == 540
    assert "errorWorkflow" not in workflow["settings"]
    interval = nodes["Every Fifteen Minutes"]["parameters"]["rule"]["interval"]
    assert interval == [{"field": "minutes", "minutesInterval": 15}]
    assert _next_node(workflow, "Every Fifteen Minutes") == "Retry Pending Payouts"
    assert _next_node(workflow, "Retry Pending Payouts") == "Assert Retry Healthy"
    assert _next_node(workflow, "Assert Retry Healthy") == "Batch Newly Eligible Payouts"
    assert _next_node(workflow, "Batch Newly Eligible Payouts") == "Assert Batch Healthy"


def test_payout_http_nodes_are_single_attempt_and_credential_bound() -> None:
    nodes = _nodes_by_name(_workflow())
    expected = {
        "Retry Pending Payouts": "/internal/payouts/retry",
        "Batch Newly Eligible Payouts": "/internal/payouts/tick",
    }

    for name, path in expected.items():
        node = nodes[name]
        params = node["parameters"]
        assert params["method"] == "POST"
        assert params["url"] == "={{$env.API_URL}}" + path
        assert params["authentication"] == "genericCredentialType"
        assert params["genericAuthType"] == "httpHeaderAuth"
        assert params["options"]["timeout"] == 240000
        assert node["retryOnFail"] is False
        assert node["credentials"]["httpHeaderAuth"] == {
            "id": "REPLACE_WITH_CREDENTIAL_ID",
            "name": "Vergeo5 Internal Payouts",
        }
        assert "headerParameters" not in params


def test_payout_workflow_surfaces_application_level_failures() -> None:
    nodes = _nodes_by_name(_workflow())
    retry_assertion = nodes["Assert Retry Healthy"]["parameters"]["jsCode"]
    batch_assertion = nodes["Assert Batch Healthy"]["parameters"]["jsCode"]

    assert "dead_lettered" in retry_assertion
    assert "throw new Error" in retry_assertion
    assert "failed" in batch_assertion
    assert "throw new Error" in batch_assertion


def test_payout_workflow_contains_no_secret_value_or_live_workflow_id() -> None:
    raw = _WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "LVuHqWgT1tqjYOtc" not in raw
    assert "Bearer " not in raw
    assert "service_role" not in raw
    assert "active\": true" not in raw
    assert "link the environment-local Shared Workflow Failure Alert" in raw


def test_payout_activation_flags_are_safe_defaulted_in_env_examples() -> None:
    production = _PRODUCTION_ENV_EXAMPLE.read_text(encoding="utf-8")
    staging = _STAGING_ENV_EXAMPLE.read_text(encoding="utf-8")

    assert "PAYOUTS_ENABLED=false" in production
    assert "STAGING_ALLOW_PAYOUTS=false" in production
    assert "PAYOUTS_ENABLED=false" in staging
    assert "STAGING_ALLOW_PAYOUTS=false" in staging
