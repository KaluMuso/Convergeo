"""Reconciliation guard for the two workflows OPS-N8N-01 flagged as inactive/unpublished:
the database backup (`backup.json`) and the shared failure alert
(`money-workflow-error-alert.json`).

Enforces the pebble's acceptance criteria as static assertions so the reconciliation cannot
silently regress:
  * both ship importable and `active: false` (no auto-activation),
  * failed runs route through a *deduplicated* alert path (n8n static-data cooldown),
  * alerts stay metadata-only — no Supabase service-role key / JWT / DSN in a message,
  * the consolidated manifest covers every required control and keeps the founder
    activation tasks explicit and UNCHECKED.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKUP = _REPO_ROOT / "infra" / "n8n" / "backup.json"
_SHARED = _REPO_ROOT / "infra" / "n8n" / "money-workflow-error-alert.json"
_MANIFEST = _REPO_ROOT / "docs" / "ops" / "n8n-backup-and-alerts.md"

# Values that must never appear verbatim in a workflow (they would end up in a message/log).
_SERVICE_ROLE = re.compile(
    r"(?i)(service_role|SUPABASE_SERVICE_ROLE_KEY)\s*[:=]\s*['\"]?[A-Za-z0-9._\-]{20,}"
)
_JWT = re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}")
_DSN = re.compile(r"(?i)postgres(?:ql)?://[^\s\"']+:[^\s\"']+@")


def _load(path: Path) -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8")))


def _first_target(conns: dict[str, Any], node: str) -> str:
    return cast("str", conns[node]["main"][0][0]["node"])


def test_both_workflows_ship_inactive() -> None:
    """`Do not activate external workflows` — both exports must stay inactive in git."""
    assert _load(_BACKUP).get("active") is False
    assert _load(_SHARED).get("active") is False


def test_shared_alert_is_the_deduplicated_route() -> None:
    data = _load(_SHARED)
    types = [n["type"] for n in data["nodes"]]
    blob = json.dumps(data)
    # Error Trigger so any linked workflow's failed run pages the founder.
    assert "n8n-nodes-base.errorTrigger" in types
    # Dedupe via workflow-scoped static data + an IF gate that drops suppressed pages.
    assert "getWorkflowStaticData" in blob
    assert "ALERT_DEDUPE_WINDOW_MINUTES" in blob
    assert "n8n-nodes-base.if" in types
    # A real WhatsApp delivery node exists (supersedes the WA-less live scaffold).
    assert "n8n-nodes-base.httpRequest" in types
    # Route order: Error Trigger -> Sanitize -> Deduplicate Alert -> IF Alert Fresh -> page.
    conns = data["connections"]
    assert _first_target(conns, "Deduplicate Alert") == "IF Alert Fresh"
    assert _first_target(conns, "IF Alert Fresh") == "Page Founder On Failure"


def test_backup_alert_path_is_deduplicated() -> None:
    data = _load(_BACKUP)
    names = {n["name"] for n in data["nodes"]}
    assert {"Dedupe Ops Alert", "IF Ops Alert Fresh"} <= names
    blob = json.dumps(data)
    assert "getWorkflowStaticData" in blob
    assert "BACKUP_ALERT_DEDUPE_MINUTES" in blob
    # Automated alert path is rewired through the dedupe gate before the WhatsApp send.
    conns = data["connections"]
    assert _first_target(conns, "Build Alert Payload") == "Dedupe Ops Alert"
    assert _first_target(conns, "Dedupe Ops Alert") == "IF Ops Alert Fresh"
    assert _first_target(conns, "IF Ops Alert Fresh") == "WhatsApp Ops Alert"


def test_dedupe_gate_can_suppress() -> None:
    """The IF gate must have a false/suppressed branch (two outputs), not just pass-through."""
    for path, gate in ((_SHARED, "IF Alert Fresh"), (_BACKUP, "IF Ops Alert Fresh")):
        conns = _load(path)["connections"]
        outputs = conns[gate]["main"]
        assert len(outputs) == 2, f"{gate} must have send + suppress branches"
        # Suppressed branch is terminal (no downstream WhatsApp send).
        assert outputs[1] == []


def test_no_service_role_key_or_secret_in_a_message() -> None:
    for path in (_BACKUP, _SHARED):
        raw = path.read_text(encoding="utf-8")
        assert _SERVICE_ROLE.search(raw) is None, f"service-role-shaped value in {path.name}"
        assert _JWT.search(raw) is None, f"JWT-shaped value in {path.name}"
        assert _DSN.search(raw) is None, f"DSN with credentials in {path.name}"


def test_backup_alert_redacts_service_role_key() -> None:
    # The backup alert Code nodes must actively scrub a service-role key from any output.
    assert "service_role_key=***" in _BACKUP.read_text(encoding="utf-8")


def test_workflows_reference_credentials_by_placeholder_only() -> None:
    for path in (_BACKUP, _SHARED):
        for node in _load(path).get("nodes", []):
            for cred in (node.get("credentials") or {}).values():
                assert cred.get("id") in (None, "REPLACE_WITH_CREDENTIAL_ID"), (
                    f"{path.name}:{node['name']} must not embed a real credential id"
                )


def test_manifest_covers_every_required_control() -> None:
    assert _MANIFEST.is_file(), "missing docs/ops/n8n-backup-and-alerts.md"
    text = _MANIFEST.read_text(encoding="utf-8")
    for topic in (
        "Schedule",
        "Ownership",
        "Credential names",
        "Idempotency",
        "Retention",
        "Encryption",
        "Restore verification",
        "Failure routing",
        "Dedupe",
        "Rollback",
        "Operator alerts",
    ):
        assert topic.lower() in text.lower(), f"manifest missing control: {topic}"
    # Both in-scope workflows are reviewable from the one doc.
    assert "backup.json" in text
    assert "money-workflow-error-alert.json" in text
    # Security invariants the pebble calls out explicitly.
    assert "scoped" in text.lower() and "internal" in text.lower()
    assert "service-role" in text.lower()


def test_manifest_founder_tasks_are_explicit_and_unchecked() -> None:
    text = _MANIFEST.read_text(encoding="utf-8")
    idx = text.find("Founder-owned activation tasks")
    assert idx != -1, "manifest missing the founder activation section"
    section = text[idx:]
    assert "- [ ]" in section, "founder tasks must be explicit checkbox items"
    assert "- [x]" not in section.lower(), "founder activation tasks must ship UNCHECKED"
