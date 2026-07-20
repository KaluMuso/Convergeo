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
    assert "Verify Uptime Secret" in nodes
    assert "Auth OK" in nodes
    assert "Respond 401 Unauthorized" in nodes
    assert "Only When Down" in nodes
    assert "Page Founder On WhatsApp" in nodes

    verifier = nodes["Verify Uptime Secret"]
    auth_blob = json.dumps(verifier["parameters"])
    assert "UPTIME_WEBHOOK_SECRET" in auth_blob
    assert "x-uptime-secret" in auth_blob.lower()
    assert "crypto.timingSafeEqual" in auth_blob

    connections = data["connections"]
    # Webhook → timing-safe verifier → auth gate → down gate → WhatsApp.
    assert connections["UptimeRobot Webhook"]["main"][0][0]["node"] == "Verify Uptime Secret"
    assert connections["Verify Uptime Secret"]["main"][0][0]["node"] == "Auth OK"
    assert connections["Auth OK"]["main"][0][0]["node"] == "Only When Down"
    assert connections["Auth OK"]["main"][1][0]["node"] == "Respond 401 Unauthorized"
    assert connections["Only When Down"]["main"][0][0]["node"] == "Page Founder On WhatsApp"
    assert "UPTIME_WEBHOOK_SECRET" not in json.dumps(nodes["Page Founder On WhatsApp"])


def test_uptime_alert_no_plaintext_secret() -> None:
    raw = _WORKFLOW.read_text(encoding="utf-8")
    assert "sk_" not in raw
    assert "Bearer ey" not in raw
    # Secret only via $env reference.
    assert "$env.UPTIME_WEBHOOK_SECRET" in raw
