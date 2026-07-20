"""Static checks for the VD-P04 database backup workflow artifacts."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_WF = _REPO_ROOT / "infra" / "n8n" / "backup.json"
_DUMP = _REPO_ROOT / "infra" / "scripts" / "db-dump.sh"
_WATCH = _REPO_ROOT / "infra" / "scripts" / "db-backup-watchdog.sh"
_VALIDATE = _REPO_ROOT / "scripts" / "ci" / "validate-backup-workflow.sh"

_SECRET_PATTERNS = (
    re.compile(r"(?i)postgres(?:ql)?://[^\s\"']+:[^\s\"']+@"),
    re.compile(r"-----BEGIN (RSA |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"),
)


def test_backup_workflow_json_exists_and_parses() -> None:
    assert _WF.is_file()
    data = json.loads(_WF.read_text(encoding="utf-8"))
    assert data.get("active") is False
    assert (data.get("settings") or {}).get("timezone") == "Africa/Lusaka"


def test_backup_workflow_has_required_triggers() -> None:
    data = json.loads(_WF.read_text(encoding="utf-8"))
    by_name = {n["name"]: n for n in data["nodes"]}
    nightly = by_name["Cron Nightly Dump"]
    expr = nightly["parameters"]["rule"]["interval"][0]["expression"]
    assert expr == "0 2 * * *"
    watchdog = by_name["Cron Missed-Schedule Watchdog"]
    assert watchdog["parameters"]["rule"]["interval"][0]["expression"] == "0 4 * * *"
    assert "Webhook Manual Backup" in by_name


def test_backup_workflow_no_secret_shaped_values() -> None:
    raw = _WF.read_text(encoding="utf-8")
    for pat in _SECRET_PATTERNS:
        match = pat.search(raw)
        assert match is None, f"secret-shaped value: {match.group(0)[:40]}…"


def test_backup_scripts_exist_and_are_executable() -> None:
    assert _DUMP.is_file()
    assert _WATCH.is_file()
    assert _DUMP.stat().st_mode & 0o111
    assert _WATCH.stat().st_mode & 0o111


def test_validate_backup_workflow_script_passes() -> None:
    assert _VALIDATE.is_file()
    result = subprocess.run(
        ["bash", str(_VALIDATE)],
        cwd=_REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "needle",
    [
        "BACKUP_MANIFEST_JSON",
        "sha256",
        "BACKUP_RETENTION_DAYS",
        "sslmode=require",
    ],
)
def test_db_dump_script_covers_manifest_contract(needle: str) -> None:
    text = _DUMP.read_text(encoding="utf-8")
    assert needle in text
