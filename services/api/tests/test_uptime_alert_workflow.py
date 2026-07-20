"""Static contract tests for infra/n8n/uptime-alert.json (Prompt 9 / VD-P05)."""

from __future__ import annotations

import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_WORKFLOW = _REPO_ROOT / "infra" / "n8n" / "uptime-alert.json"


def test_uptime_alert_json_valid_and_inactive() -> None:
    data = json.loads(_WORKFLOW.read_text(encoding="utf-8"))
    assert data["active"] is False
    assert data["name"] == "Uptime Downtime Founder Alert"


def test_uptime_alert_requires_secret_before_whatsapp() -> None:
    data = json.loads(_WORKFLOW.read_text(encoding="utf-8"))
    nodes = {n["name"]: n for n in data["nodes"]}
    assert "Require Uptime Secret" in nodes
    assert "Only When Down" in nodes
    assert "Page Founder On WhatsApp" in nodes

    auth = nodes["Require Uptime Secret"]
    auth_blob = json.dumps(auth["parameters"])
    assert "UPTIME_WEBHOOK_SECRET" in auth_blob
    assert "x-uptime-secret" in auth_blob.lower()

    connections = data["connections"]
    # Webhook → auth gate → down gate → WhatsApp (auth false branch empty).
    assert connections["UptimeRobot Webhook"]["main"][0][0]["node"] == "Require Uptime Secret"
    assert connections["Require Uptime Secret"]["main"][0][0]["node"] == "Only When Down"
    assert connections["Require Uptime Secret"]["main"][1] == []
    assert connections["Only When Down"]["main"][0][0]["node"] == "Page Founder On WhatsApp"
    assert "UPTIME_WEBHOOK_SECRET" not in json.dumps(nodes["Page Founder On WhatsApp"])


def test_uptime_alert_no_plaintext_secret() -> None:
    raw = _WORKFLOW.read_text(encoding="utf-8")
    assert "sk_" not in raw
    assert "Bearer ey" not in raw
    # Secret only via $env reference.
    assert "$env.UPTIME_WEBHOOK_SECRET" in raw
