"""Fail-closed recovery drill guards (STG-REC-04).

Hard-rejects production Supabase project refs and production database hosts as
restore targets. No ``--force-production`` escape hatch.

Keep public identifiers in sync with
``infra/staging/forbidden-production-identifiers.env``.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlparse

from app.core.env_guards import (
    PROD_SUPABASE_PROJECT_REF,
    extract_supabase_project_ref,
)

# Staging source project (read-only dumps allowed; never a destructive restore target).
STAGING_SUPABASE_PROJECT_REF: Final = "iyasmrmbcrvlfxpzescb"

_PROD_DB_HOST_RE = re.compile(
    r"^db\.dpadrlxukcjbewpqympu\.supabase\.co$",
    re.IGNORECASE,
)


class RecoveryVerdict(StrEnum):
    """Recovery drill failure taxonomy — never map missing infra to PASS."""

    BACKUP_CONFIGURATION_VALID = "BACKUP_CONFIGURATION_VALID"
    RESTORE_TARGET_AUTHORIZATION_REQUIRED = "RESTORE_TARGET_AUTHORIZATION_REQUIRED"
    RESTORE_FAILED = "RESTORE_FAILED"
    RESTORE_VERIFICATION_FAILED = "RESTORE_VERIFICATION_FAILED"
    RESTORE_DRILL_PROVEN = "RESTORE_DRILL_PROVEN"


class RecoveryGuardError(ValueError):
    """Raised when a recovery operation would violate safety guards."""


@dataclass
class RecoveryEvidence:
    """Machine-readable recovery drill evidence (QA-02 compatible)."""

    schema_version: str = "1"
    source_project_ref: str = ""
    source_migration_tip: str = ""
    backup_identifier: str = ""
    backup_sha256: str = ""
    backup_size_bytes: int = 0
    restore_target_ref: str = ""
    restore_target_kind: str = ""
    started_at: str = ""
    finished_at: str = ""
    duration_seconds: float = 0.0
    schema_verification: dict[str, Any] = field(default_factory=dict)
    data_verification: dict[str, Any] = field(default_factory=dict)
    rls_verification: dict[str, Any] = field(default_factory=dict)
    marker_recorded: bool = False
    verdict: str = RecoveryVerdict.BACKUP_CONFIGURATION_VALID
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_project_ref": self.source_project_ref,
            "source_migration_tip": self.source_migration_tip,
            "backup_identifier": self.backup_identifier,
            "backup_sha256": self.backup_sha256,
            "backup_size_bytes": self.backup_size_bytes,
            "restore_target_ref": self.restore_target_ref,
            "restore_target_kind": self.restore_target_kind,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds,
            "schema_verification": self.schema_verification,
            "data_verification": self.data_verification,
            "rls_verification": self.rls_verification,
            "marker_recorded": self.marker_recorded,
            "verdict": self.verdict,
            "detail": self.detail,
        }


_DB_HOST_RE = re.compile(
    r"^db\.(?P<ref>[a-z0-9]{20})\.supabase\.co$",
    re.IGNORECASE,
)


def extract_db_host(db_url: str) -> str:
    """Return the hostname from a Postgres connection URL."""
    raw = (db_url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"postgresql://{raw}")
    return (parsed.hostname or "").lower()


def extract_supabase_ref_from_db_url(db_url: str) -> str | None:
    """Return Supabase project ref from a Postgres URL or host."""
    host = extract_db_host(db_url)
    if host:
        match = _DB_HOST_RE.match(host)
        if match:
            return match.group("ref").lower()
    return extract_supabase_project_ref(db_url)


def is_production_db_host(host: str) -> bool:
    """True when the host is the production Supabase database endpoint."""
    normalized = (host or "").lower()
    if not normalized:
        return False
    if _PROD_DB_HOST_RE.match(normalized):
        return True
    return normalized == f"db.{PROD_SUPABASE_PROJECT_REF}.supabase.co"


def is_production_project_ref(ref: str | None) -> bool:
    """True when the Supabase project ref is production."""
    if not ref:
        return False
    return ref.lower() == PROD_SUPABASE_PROJECT_REF


def is_production_restore_target(*, db_url: str = "", project_ref: str = "") -> bool:
    """True when the restore target resolves to production."""
    ref = (project_ref or "").strip().lower()
    if ref and is_production_project_ref(ref):
        return True
    host = extract_db_host(db_url)
    if host and is_production_db_host(host):
        return True
    resolved_ref = extract_supabase_ref_from_db_url(db_url)
    if resolved_ref and is_production_project_ref(resolved_ref):
        return True
    return False


def assert_restore_target_safe(
    *,
    source_db_url: str,
    target_db_url: str,
    source_project_ref: str = "",
    target_project_ref: str = "",
) -> None:
    """Refuse unsafe restore targets before any destructive operation.

    Raises:
        RecoveryGuardError: production target, missing target, or source==target.
    """
    if not (target_db_url or "").strip():
        raise RecoveryGuardError(
            "RESTORE_TARGET_AUTHORIZATION_REQUIRED: restore target URL is missing"
        )

    if is_production_restore_target(db_url=target_db_url, project_ref=target_project_ref):
        raise RecoveryGuardError(
            f"RESTORE_FAILED: refusing production restore target "
            f"({PROD_SUPABASE_PROJECT_REF})"
        )

    if not (source_db_url or "").strip():
        raise RecoveryGuardError("RESTORE_FAILED: source database URL is missing")

    if source_db_url.strip() == target_db_url.strip():
        raise RecoveryGuardError(
            "RESTORE_FAILED: source and target URLs are identical — "
            "refusing to clobber the source"
        )

    source_ref = (
        source_project_ref or extract_supabase_ref_from_db_url(source_db_url) or ""
    ).lower()
    target_ref = (
        target_project_ref or extract_supabase_ref_from_db_url(target_db_url) or ""
    ).lower()

    if source_ref and target_ref and source_ref == target_ref:
        source_db = _db_name_from_url(source_db_url)
        target_db = _db_name_from_url(target_db_url)
        if source_db and target_db and source_db == target_db:
            raise RecoveryGuardError(
                "RESTORE_FAILED: source and target resolve to the same project and "
                "database — refusing destructive restore on the active plane"
            )


def verify_backup_checksum(path: str, expected_sha256: str) -> None:
    """Verify a backup file's SHA-256 checksum."""
    if not path or not Path(path).is_file():
        raise RecoveryGuardError(f"RESTORE_FAILED: backup file not found: {path}")
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    expected = (expected_sha256 or "").strip().lower()
    if not expected:
        raise RecoveryGuardError("RESTORE_FAILED: backup checksum not provided")
    if actual != expected:
        raise RecoveryGuardError(
            f"RESTORE_FAILED: backup checksum mismatch (expected {expected[:12]}…, "
            f"got {actual[:12]}…)"
        )


def redact_db_url(db_url: str) -> str:
    """Redact credentials from a database URL for logs/evidence."""
    raw = (db_url or "").strip()
    if not raw:
        return ""
    return re.sub(r"(://[^:/]+:)[^@]+@", r"\1***@", raw)


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _db_name_from_url(db_url: str) -> str:
    raw = (db_url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"postgresql://{raw}")
    path = (parsed.path or "").lstrip("/")
    return path.split("?")[0] if path else ""
