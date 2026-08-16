"""Static safety contract for the event cancellation refund jobs n8n workflow (Prompt G)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

_REPO_ROOT = Path(__file__).resolve().parents[3]
_WORKFLOW_PATH = _REPO_ROOT / "infra" / "n8n" / "event-refund-jobs.json"


def _workflow() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(_WORKFLOW_PATH.read_text(encoding="utf-8")),
    )


def _nodes_by_name(workflow: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(node["name"]): node for node in workflow["nodes"]}


def _next_node(workflow: dict[str, Any], node_name: str) -> str:
    return str(workflow["connections"][node_name]["main"][0][0]["node"])


def test_event_refund_jobs_workflow_is_inactive_and_bounded() -> None:
    workflow = _workflow()
    nodes = _nodes_by_name(workflow)

    assert workflow["active"] is False
    assert workflow["settings"]["executionTimeout"] == 300
    interval = nodes["Every Five Minutes"]["parameters"]["rule"]["interval"]
    assert interval == [{"field": "minutes", "minutesInterval": 5}]
    assert _next_node(workflow, "Every Five Minutes") == "Sweep Cancellation Refund Jobs"
    assert _next_node(workflow, "Sweep Cancellation Refund Jobs") == "Assert Refund Jobs Healthy"


def test_event_refund_jobs_http_node_is_single_attempt_and_token_bound() -> None:
    node = _nodes_by_name(_workflow())["Sweep Cancellation Refund Jobs"]
    params = node["parameters"]

    assert params["method"] == "POST"
    assert params["url"] == "={{$env.API_URL}}/internal/event-refund-jobs/tick"
    assert params["authentication"] == "genericCredentialType"
    assert params["genericAuthType"] == "httpHeaderAuth"
    assert params["options"]["timeout"] == 120000
    assert node["retryOnFail"] is False
    assert node["credentials"]["httpHeaderAuth"] == {
        "id": "REPLACE_WITH_CREDENTIAL_ID",
        "name": "Vergeo5 Internal Event Refund Jobs",
    }
    headers = params["headerParameters"]["parameters"]
    assert headers == [
        {
            "name": "X-Internal-Token",
            "value": "={{$env.INTERNAL_EVENT_REFUND_JOBS_TOKEN}}",
        }
    ]


def test_event_refund_jobs_workflow_surfaces_dead_letter_and_manual_review() -> None:
    assertion = _nodes_by_name(_workflow())["Assert Refund Jobs Healthy"]["parameters"]["jsCode"]

    assert "dead" in assertion
    assert "manual_review" in assertion
    assert "throw new Error" in assertion


def test_event_refund_jobs_workflow_contains_no_secret_value() -> None:
    raw = _WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "dev-internal-event-refund-jobs" not in raw
    assert "Bearer " not in raw
    assert "service_role" not in raw
    assert '"active": true' not in raw
