"""OPS-N8N-01: audit doc completeness vs infra/n8n registry (read-only artifact)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_N8N_DIR = _REPO_ROOT / "infra" / "n8n"
_AUDIT_DOC = (
    _REPO_ROOT
    / "docs"
    / "production-readiness"
    / "2026-07-19"
    / "ops"
    / "ops-n8n-01-automation-readiness-audit.md"
)

_REQUIRED_STATUSES = (
    "VERIFIED LIVE",
    "DORMANT",
    "PARTIAL",
    "BROKEN",
    "UNKNOWN",
)

_REQUIRED_CONCERNS = (
    "Escrow auto-confirm",
    "Ticket issuance",
    "Payment and reservation sweepers",
    "Reconciliation",
    "Database / OCI backup",
    "Notification dispatch",
)

_REQUIRED_ACTIVATION_GATES = (
    "Migration reconciliation",
    "Payment gate deployment",
    "Prepaid collection and release accounting verification",
    "Sandbox end-to-end testing",
)

_REQUIRED_CROSS_CUTTING = (
    "Idempotency",
    "Timeout",
    "Retry",
    "Error-workflow",
    "Money-movement freeze",
    "Rollback",
)

# Patterns that must never appear in the audit artifact.
_SECRET_PATTERNS = (
    re.compile(r"(?i)x-internal-token\s*[:=]\s*['\"]?[a-z0-9_\-]{16,}"),
    re.compile(r"(?i)(api[_-]?key|secret|password|bearer)\s*[:=]\s*['\"][^'\"]{8,}"),
    re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"),  # JWT-shaped
)


def _workflow_files() -> list[Path]:
    return sorted(_N8N_DIR.glob("*.json"))


def test_ops_n8n_01_audit_exists() -> None:
    assert _AUDIT_DOC.is_file(), f"missing OPS-N8N-01 audit: {_AUDIT_DOC}"


def test_ops_n8n_01_audit_declares_classification_legend() -> None:
    text = _AUDIT_DOC.read_text(encoding="utf-8")
    for status in _REQUIRED_STATUSES:
        assert status in text, f"audit missing classification status {status!r}"


@pytest.mark.parametrize("concern", _REQUIRED_CONCERNS)
def test_ops_n8n_01_audit_covers_concern(concern: str) -> None:
    text = _AUDIT_DOC.read_text(encoding="utf-8")
    assert concern in text, f"audit missing concern section for {concern!r}"


@pytest.mark.parametrize("workflow", _workflow_files(), ids=lambda p: p.name)
def test_ops_n8n_01_audit_mentions_every_workflow_json(workflow: Path) -> None:
    text = _AUDIT_DOC.read_text(encoding="utf-8")
    assert workflow.name in text, (
        f"{workflow.name} not mentioned in OPS-N8N-01 audit — "
        "add it to the completeness matrix"
    )


def test_ops_n8n_01_audit_mentions_backup_contract() -> None:
    text = _AUDIT_DOC.read_text(encoding="utf-8")
    assert "backup-schedule.md" in text


@pytest.mark.parametrize("gate", _REQUIRED_ACTIVATION_GATES)
def test_ops_n8n_01_audit_lists_activation_prerequisite(gate: str) -> None:
    text = _AUDIT_DOC.read_text(encoding="utf-8")
    assert gate in text, f"audit missing prerequisite gate {gate!r}"


@pytest.mark.parametrize("topic", _REQUIRED_CROSS_CUTTING)
def test_ops_n8n_01_audit_covers_activation_controls(topic: str) -> None:
    text = _AUDIT_DOC.read_text(encoding="utf-8")
    assert topic in text or topic.lower() in text.lower(), (
        f"audit missing activation control topic {topic!r}"
    )


def test_ops_n8n_01_audit_forbids_activation_claim() -> None:
    text = _AUDIT_DOC.read_text(encoding="utf-8")
    assert "do not execute" in text.lower() or "do not activate" in text.lower()
    assert "Hard constraints observed" in text


def test_ops_n8n_01_audit_has_no_secret_shaped_values() -> None:
    text = _AUDIT_DOC.read_text(encoding="utf-8")
    for pattern in _SECRET_PATTERNS:
        match = pattern.search(text)
        assert match is None, f"possible secret-shaped value in audit: {match.group(0)[:40]}…"


def test_ops_n8n_01_audit_records_live_workflow_ids() -> None:
    text = _AUDIT_DOC.read_text(encoding="utf-8")
    assert "sevKtX1AmimQCWsG" in text
    assert "C1MpTNjrfLACMG3f" in text
