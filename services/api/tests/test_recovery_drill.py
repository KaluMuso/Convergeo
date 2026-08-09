"""STG-REC-04 recovery drill guards and evidence tests."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import pytest
from app.core.recovery_guards import (
    PROD_SUPABASE_PROJECT_REF,
    STAGING_SUPABASE_PROJECT_REF,
    RecoveryEvidence,
    RecoveryGuardError,
    RecoveryVerdict,
    assert_restore_target_safe,
    extract_db_host,
    is_production_db_host,
    is_production_project_ref,
    is_production_restore_target,
    redact_db_url,
    verify_backup_checksum,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
GUARDS_SH = REPO_ROOT / "scripts" / "ops" / "lib" / "recovery-guards.sh"
RECOVERY_DRILL_SH = REPO_ROOT / "scripts" / "ops" / "recovery-drill.sh"
EVIDENCE_SCHEMA = REPO_ROOT / "scripts" / "ops" / "recovery-evidence.schema.json"

PROD_DB_URL = (
    f"postgresql://postgres:secret@db.{PROD_SUPABASE_PROJECT_REF}.supabase.co:5432/postgres"
)
STAGING_DB_URL = (
    f"postgresql://postgres:secret@db.{STAGING_SUPABASE_PROJECT_REF}.supabase.co:5432/postgres"
)
DRILL_TARGET_URL = (
    "postgresql://postgres:secret@db.abcdefghij1234567890.supabase.co:5432/postgres"
)
LOCAL_SOURCE = "postgresql://postgres:postgres@127.0.0.1:5433/vergeo_src"
LOCAL_TARGET = "postgresql://postgres:postgres@127.0.0.1:5433/vergeo_restore"


def _run_guards_sh(*args: str) -> subprocess.CompletedProcess[str]:
    script = f"""
set -euo pipefail
source "{GUARDS_SH}"
{" ".join(args)}
"""
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )


def test_production_project_ref_detection() -> None:
    assert is_production_project_ref(PROD_SUPABASE_PROJECT_REF)
    assert not is_production_project_ref(STAGING_SUPABASE_PROJECT_REF)


def test_production_db_host_detection() -> None:
    assert is_production_db_host(f"db.{PROD_SUPABASE_PROJECT_REF}.supabase.co")
    assert not is_production_db_host(f"db.{STAGING_SUPABASE_PROJECT_REF}.supabase.co")


def test_production_restore_target_rejected() -> None:
    assert is_production_restore_target(db_url=PROD_DB_URL)
    assert not is_production_restore_target(db_url=DRILL_TARGET_URL)


def test_assert_restore_target_refuses_production() -> None:
    with pytest.raises(RecoveryGuardError, match="production restore target"):
        assert_restore_target_safe(
            source_db_url=STAGING_DB_URL,
            target_db_url=PROD_DB_URL,
        )


def test_assert_restore_target_refuses_same_url() -> None:
    with pytest.raises(RecoveryGuardError, match="identical"):
        assert_restore_target_safe(
            source_db_url=LOCAL_SOURCE,
            target_db_url=LOCAL_SOURCE,
        )


def test_assert_restore_target_refuses_same_project_and_database() -> None:
    source = (
        f"postgresql://postgres:secret@db.{STAGING_SUPABASE_PROJECT_REF}"
        ".supabase.co:5432/postgres"
    )
    target = source  # identical URL
    with pytest.raises(RecoveryGuardError, match="identical"):
        assert_restore_target_safe(source_db_url=source, target_db_url=target)


def test_assert_restore_target_refuses_same_project_same_database_name() -> None:
    host = f"db.{STAGING_SUPABASE_PROJECT_REF}.supabase.co"
    url_a = f"postgresql://postgres:secret@{host}:5432/postgres?sslmode=require"
    url_b = f"postgresql://postgres:other@{host}:5432/postgres"
    with pytest.raises(RecoveryGuardError, match="same project and database"):
        assert_restore_target_safe(source_db_url=url_a, target_db_url=url_b)


def test_assert_restore_target_refuses_missing_target() -> None:
    with pytest.raises(RecoveryGuardError, match="RESTORE_TARGET_AUTHORIZATION_REQUIRED"):
        assert_restore_target_safe(
            source_db_url=STAGING_DB_URL,
            target_db_url="",
        )


def test_assert_restore_target_allows_safe_disposable_target() -> None:
    assert_restore_target_safe(
        source_db_url=STAGING_DB_URL,
        target_db_url=DRILL_TARGET_URL,
    )
    assert_restore_target_safe(
        source_db_url=LOCAL_SOURCE,
        target_db_url=LOCAL_TARGET,
    )


def test_verify_backup_checksum_missing_file() -> None:
    with pytest.raises(RecoveryGuardError, match="not found"):
        verify_backup_checksum("/nonexistent/dump.sql.gz", "abc")


def test_verify_backup_checksum_mismatch() -> None:
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(b"corrupt backup bytes")
        path = tmp.name
    try:
        with pytest.raises(RecoveryGuardError, match="checksum mismatch"):
            verify_backup_checksum(path, "0" * 64)
    finally:
        Path(path).unlink(missing_ok=True)


def test_verify_backup_checksum_match() -> None:
    content = b"vergeo5 recovery drill fixture"
    digest = __import__("hashlib").sha256(content).hexdigest()
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(content)
        path = tmp.name
    try:
        verify_backup_checksum(path, digest)
    finally:
        Path(path).unlink(missing_ok=True)


def test_redact_db_url_strips_password() -> None:
    redacted = redact_db_url(PROD_DB_URL)
    assert "secret" not in redacted
    assert "***@" in redacted


def test_recovery_evidence_to_dict_no_secrets() -> None:
    evidence = RecoveryEvidence(
        source_project_ref=STAGING_SUPABASE_PROJECT_REF,
        restore_target_ref="abcdefghij1234567890",
        verdict=RecoveryVerdict.RESTORE_TARGET_AUTHORIZATION_REQUIRED,
        detail="target not provisioned",
    )
    payload = evidence.to_dict()
    assert "postgresql://" not in json.dumps(payload)
    assert payload["verdict"] == RecoveryVerdict.RESTORE_TARGET_AUTHORIZATION_REQUIRED


def test_evidence_schema_exists_and_lists_verdicts() -> None:
    schema = json.loads(EVIDENCE_SCHEMA.read_text(encoding="utf-8"))
    verdicts = schema["properties"]["verdict"]["enum"]
    assert RecoveryVerdict.RESTORE_DRILL_PROVEN in verdicts
    assert RecoveryVerdict.BACKUP_CONFIGURATION_VALID in verdicts


def test_bash_guards_reject_production_target() -> None:
    result = _run_guards_sh(
        f'recovery_assert_restore_target_safe "{STAGING_DB_URL}" "{PROD_DB_URL}"'
    )
    assert result.returncode != 0
    assert "production restore target" in result.stderr


def test_bash_guards_reject_same_source_target() -> None:
    result = _run_guards_sh(
        f'recovery_assert_restore_target_safe "{LOCAL_SOURCE}" "{LOCAL_SOURCE}"'
    )
    assert result.returncode != 0
    assert "identical" in result.stderr


def test_bash_guards_reject_missing_target() -> None:
    result = _run_guards_sh(
        f'recovery_assert_restore_target_safe "{STAGING_DB_URL}" ""'
    )
    assert result.returncode != 0
    assert "RESTORE_TARGET_AUTHORIZATION_REQUIRED" in result.stderr


def test_bash_guards_reject_corrupt_checksum() -> None:
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(b"bad")
        path = tmp.name
    try:
        result = _run_guards_sh(
            f'recovery_verify_backup_checksum "{path}" "{"0" * 64}"'
        )
        assert result.returncode != 0
        assert "checksum mismatch" in result.stderr
    finally:
        Path(path).unlink(missing_ok=True)


def test_recovery_drill_plan_writes_authorization_required() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        evidence_path = Path(tmpdir) / "evidence.json"
        result = subprocess.run(
            [
                "bash",
                str(RECOVERY_DRILL_SH),
                "--plan",
            ],
            capture_output=True,
            text=True,
            check=False,
            env={
                **__import__("os").environ,
                "RECOVERY_EVIDENCE_PATH": str(evidence_path),
            },
        )
        assert result.returncode == 0
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert payload["verdict"] == RecoveryVerdict.RESTORE_TARGET_AUTHORIZATION_REQUIRED


def test_recovery_drill_missing_target_writes_evidence() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        evidence_path = Path(tmpdir) / "evidence.json"
        result = subprocess.run(
            ["bash", str(RECOVERY_DRILL_SH)],
            capture_output=True,
            text=True,
            check=False,
            env={
                **__import__("os").environ,
                "RECOVERY_EVIDENCE_PATH": str(evidence_path),
                "SOURCE_DB_URL": STAGING_DB_URL,
            },
        )
        assert result.returncode != 0
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert payload["verdict"] == RecoveryVerdict.RESTORE_TARGET_AUTHORIZATION_REQUIRED


def test_db_restore_rejects_force_flag() -> None:
    db_restore = REPO_ROOT / "infra" / "scripts" / "db-restore.sh"
    result = subprocess.run(
        [str(db_restore), "--force", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "--force is removed" in result.stderr


def test_extract_db_host() -> None:
    assert extract_db_host(PROD_DB_URL) == f"db.{PROD_SUPABASE_PROJECT_REF}.supabase.co"
