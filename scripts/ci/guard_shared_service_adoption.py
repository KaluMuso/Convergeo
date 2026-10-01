"""Read-only prerequisite: shared CLI push must never execute raw legacy adoption.

This verifies supplied review/application references and canonical installed SQL.
It cannot grant release approval, execute adoption, or repair migration history.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import apply_service_adoption as adoption

VERSION, NAME = Path(adoption.ADOPTION).stem.split("_", 1)
QUERY = """BEGIN READ ONLY;
SELECT coalesce(json_agg(to_json(m)), '[]'::json)
FROM (SELECT version,name,statements FROM supabase_migrations.schema_migrations
      WHERE version='20260929120003') m;
COMMIT;
"""


def row_digest(row: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(row, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate(
    rows: Any, evidence: Any, *, source_sha: str, project_ref: str, migrations: Path
) -> None:
    original = (migrations / adoption.ADOPTION).read_bytes()
    if hashlib.sha256(original).hexdigest() != adoption.ADOPTION_SHA256:
        raise ValueError("Immutable adoption source differs from reviewed authority")
    expected = {"version": VERSION, "name": NAME, "statements": [original.decode()]}
    if rows != [expected]:
        raise ValueError(
            "Raw adoption remains pending or canonical installed SQL is unproven"
        )
    if not isinstance(evidence, dict) or not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("Reviewed shared adoption evidence is required")
    required = {
        "purpose": "SHARED_ADOPTION_APPLICATION_REVIEW",
        "source_sha": source_sha,
        "project_ref": project_ref,
        "adoption_sha256": adoption.ADOPTION_SHA256,
        "canonical_row_sha256": row_digest(expected),
        "review_verdict": "APPROVED_FOR_TARGET_APPLICATION",
    }
    if not project_ref or any(
        evidence.get(key) != value for key, value in required.items()
    ):
        raise ValueError(
            "Shared adoption review evidence is not bound to this source/target/history"
        )
    if (
        not isinstance(evidence.get("reviewer"), str)
        or not evidence["reviewer"].strip()
    ):
        raise ValueError("Named independent reviewer is required")
    if not re.fullmatch(r"[0-9a-f]{64}", str(evidence.get("review_record_sha256", ""))):
        raise ValueError("Hash-bound independent review record is required")
    for key in ("application_record_url", "review_record_url"):
        value = evidence.get(key)
        parsed = urlparse(value) if isinstance(value, str) else None
        if (
            parsed is None
            or parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
        ):
            raise ValueError(
                "Reviewable HTTPS application and independent review records are required"
            )


def validate_dsn_binding(dsn: str, project_ref: str) -> None:
    """Only the established staging native endpoint contract is accepted."""
    if project_ref != "iyasmrmbcrvlfxpzescb":
        raise ValueError(
            "Shared adoption push prerequisite accepts only the guarded staging target"
        )
    parsed = urlparse(dsn)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.port not in {
        None,
        5432,
    }:
        raise ValueError("Unsupported staging native DSN binding")
    user = unquote(parsed.username or "")
    direct = parsed.hostname == f"db.{project_ref}.supabase.co" and user == "postgres"
    pooler = (
        re.fullmatch(r"aws-0-[a-z0-9-]+\.pooler\.supabase\.com", parsed.hostname or "")
        and user == f"postgres.{project_ref}"
    )
    allowed_options = {
        "sslmode",
        "sslrootcert",
        "sslcert",
        "sslkey",
        "connect_timeout",
        "application_name",
    }
    if (
        not (direct or pooler)
        or parsed.path != "/postgres"
        or parsed.fragment
        or not set(parse_qs(parsed.query, keep_blank_values=True)) <= allowed_options
    ):
        raise ValueError("Native DSN does not bind the reviewed staging project")


def main() -> None:
    # Follow the existing deployment's native psql DSN contract. Capture and
    # suppress driver stderr; never print DSNs, command arguments or evidence.
    dsn = os.environ.get("SUPABASE_DB_URL", "")
    if not dsn:
        raise ValueError(
            "SUPABASE_DB_URL is required for read-only adoption history query"
        )
    project_ref = os.environ.get("SCHEMA_TARGET_PROJECT_REF", "")
    validate_dsn_binding(dsn, project_ref)
    expected_source = os.environ.get("EXPECTED_SOURCE_SHA", "")
    try:
        actual_source = subprocess.check_output(
            ["git", "-C", str(adoption.ROOT), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        raise ValueError(
            "Actual checkout identity could not be verified; CLI push refused"
        ) from None
    if expected_source != actual_source:
        raise ValueError(
            "Declared source differs from the actual checkout; CLI push refused"
        )
    raw = os.environ.get("SERVICE_ADOPTION_REVIEW_EVIDENCE_JSON", "")
    if not raw:
        raise ValueError(
            "Independent reviewed shared adoption evidence is absent; CLI push refused"
        )
    evidence = json.loads(raw)
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "PGHOST",
            "PGHOSTADDR",
            "PGPORT",
            "PGSERVICE",
            "PGSERVICEFILE",
            "PGOPTIONS",
        }
    }
    result = subprocess.run(
        ["psql", "-X", "-q", "-tA", "-v", "ON_ERROR_STOP=1", "--dbname", dsn],
        input=QUERY,
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )
    if result.returncode:
        raise ValueError("Read-only adoption history query failed; CLI push refused")
    validate(
        json.loads(result.stdout),
        evidence,
        source_sha=actual_source,
        project_ref=os.environ.get("SCHEMA_TARGET_PROJECT_REF", ""),
        migrations=adoption.ROOT / "supabase/migrations",
    )
    print("SHARED_ADOPTION_HISTORY_AND_SUPPLIED_REVIEW_BINDING_VERIFIED")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        # Known guard errors contain no connection string or database contents.
        if isinstance(error, json.JSONDecodeError):
            raise SystemExit(
                "Shared adoption evidence/history JSON is invalid; CLI push refused"
            ) from None
        if isinstance(error, OSError):
            raise SystemExit(
                "Shared adoption prerequisite could not execute; CLI push refused"
            ) from None
        raise SystemExit(str(error)) from None
