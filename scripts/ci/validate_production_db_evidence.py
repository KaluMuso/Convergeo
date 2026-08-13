#!/usr/bin/env python3
"""Validate machine-generated Production DB migration evidence (RELCTRL-01).

Fail-closed: refuses hand-edited contracts without provenance. Optionally
verifies the cited GitHub Actions run succeeded and cross-checks a live
read-only observation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from validate_release_parity import (
    ParityValidationError,
    migration_at_least,
    normalize_migration_version,
    repo_migration_versions,
)

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
EVIDENCE_GATE = "RELCTRL-01-production-db"
EXPECTED_WORKFLOW = "capture-production-db-evidence.yml"


class DbEvidenceError(ValueError):
    """Raised when production DB evidence fails validation."""


def _require_sha(value: str, label: str) -> str:
    value = (value or "").strip().lower()
    if not SHA_RE.match(value):
        raise DbEvidenceError(f"{label} must be a 40-char git SHA, got {value!r}")
    return value


def load_evidence(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise DbEvidenceError(f"{path} must contain a JSON object")
    return data


def verify_github_run_provenance(
    *,
    repository: str,
    workflow_run_id: str,
    candidate_sha: str,
    gh_token: str,
) -> None:
    if not gh_token.strip():
        raise DbEvidenceError("GITHUB_TOKEN required to verify workflow provenance")

    url = f"https://api.github.com/repos/{repository}/actions/runs/{workflow_run_id}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {gh_token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise DbEvidenceError(f"could not verify workflow run {workflow_run_id}: {exc}") from exc

    run = json.loads(body)
    if str(run.get("conclusion") or "").lower() != "success":
        raise DbEvidenceError(
            f"workflow run {workflow_run_id} conclusion={run.get('conclusion')!r} want success"
        )
    if str(run.get("status") or "").lower() != "completed":
        raise DbEvidenceError(f"workflow run {workflow_run_id} status={run.get('status')!r} want completed")

    path = str(run.get("path") or "")
    if EXPECTED_WORKFLOW not in path:
        raise DbEvidenceError(f"workflow run path={path!r} want {EXPECTED_WORKFLOW}")

    head = str(run.get("head_sha") or "").lower()
    if head and head != candidate_sha:
        raise DbEvidenceError(
            f"workflow run head_sha={head[:12]} != candidate_sha={candidate_sha[:12]}"
        )


def query_live_migration_head(db_url: str) -> str:
    proc = subprocess.run(
        [
            "psql",
            db_url,
            "-tA",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            "SELECT coalesce(max(version),'') FROM supabase_migrations.schema_migrations;",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "psql failed").strip()
        raise DbEvidenceError(f"live migration query failed: {detail[:300]}")
    tip = (proc.stdout or "").strip()
    if not tip:
        raise DbEvidenceError("live migration head is empty")
    return tip


def validate_production_db_evidence(
    evidence: dict[str, Any],
    *,
    candidate_sha: str,
    required_baseline: str,
    migrations_dir: Path,
    live_migration_head: str | None = None,
    verify_run: bool = True,
    gh_token: str = "",
    repository: str = "KaluMuso/Convergeo",
) -> str:
    """Validate evidence and return normalized migration head version."""
    candidate = _require_sha(candidate_sha, "candidate_sha")

    if evidence.get("gate") != EVIDENCE_GATE:
        raise DbEvidenceError(f"gate={evidence.get('gate')!r} want {EVIDENCE_GATE}")
    if str(evidence.get("schema_version")) != "1":
        raise DbEvidenceError("schema_version must be '1'")
    if str(evidence.get("repository") or "") != repository:
        raise DbEvidenceError(f"repository mismatch: {evidence.get('repository')!r}")

    evidence_sha = _require_sha(str(evidence.get("candidate_sha", "")), "candidate_sha")
    if evidence_sha != candidate:
        raise DbEvidenceError(
            f"evidence candidate_sha={evidence_sha[:12]} != promotion candidate={candidate[:12]}"
        )

    run_id = str(evidence.get("workflow_run_id") or "").strip()
    if not run_id.isdigit():
        raise DbEvidenceError("workflow_run_id must be a numeric GitHub Actions run id")
    if str(evidence.get("workflow") or "") != EXPECTED_WORKFLOW:
        raise DbEvidenceError(f"workflow={evidence.get('workflow')!r} unexpected")
    if not evidence.get("observed_at"):
        raise DbEvidenceError("observed_at is required")
    if evidence.get("observation_method") != "readonly_psql":
        raise DbEvidenceError("observation_method must be readonly_psql")

    migration_head = str(evidence.get("migration_head") or "").strip()
    if not migration_head:
        raise DbEvidenceError("migration_head is required")

    if verify_run:
        verify_github_run_provenance(
            repository=repository,
            workflow_run_id=run_id,
            candidate_sha=candidate,
            gh_token=gh_token,
        )

    ledger = repo_migration_versions(migrations_dir)
    if not migration_at_least(migration_head, required_baseline, ledger):
        head_label = normalize_migration_version(migration_head, ledger)
        base_label = normalize_migration_version(required_baseline, ledger)
        raise DbEvidenceError(
            f"migration_head={head_label!r} is behind required baseline {base_label!r}"
        )

    if live_migration_head is not None:
        live = live_migration_head.strip()
        if live != migration_head:
            raise DbEvidenceError(
                f"live migration_head={live!r} != evidence migration_head={migration_head!r}"
            )
        if not migration_at_least(live, required_baseline, ledger):
            raise DbEvidenceError("live migration head is behind required baseline")

    return migration_head


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Production DB migration evidence")
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--required-baseline", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--migrations-dir", type=Path, default=Path("supabase/migrations"))
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", "KaluMuso/Convergeo"))
    parser.add_argument("--skip-run-provenance", action="store_true")
    parser.add_argument("--skip-live-db", action="store_true")
    parser.add_argument(
        "--db-url-env",
        default="PRODUCTION_READONLY_DB_URL",
        help="Env var for live read-only cross-check",
    )
    args = parser.parse_args(argv)

    live_head: str | None = None
    if not args.skip_live_db:
        db_url = os.environ.get(args.db_url_env) or os.environ.get("SUPABASE_DB_URL", "")
        if not db_url:
            print("::error::PRODUCTION_READONLY_DB_URL required for live DB verification", file=sys.stderr)
            return 1
        try:
            live_head = query_live_migration_head(db_url)
        except DbEvidenceError as exc:
            print(f"::error::{exc}", file=sys.stderr)
            return 1

    try:
        evidence = load_evidence(args.evidence)
        head = validate_production_db_evidence(
            evidence,
            candidate_sha=args.candidate_sha,
            required_baseline=args.required_baseline,
            migrations_dir=args.migrations_dir,
            live_migration_head=live_head,
            verify_run=not args.skip_run_provenance,
            gh_token=os.environ.get("GITHUB_TOKEN", ""),
            repository=args.repository,
        )
    except (DbEvidenceError, ParityValidationError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    print(f"production DB evidence OK migration_head={head}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
