#!/usr/bin/env python3
"""Validate release parity evidence before Production frontend promotion.

Fail-closed gate for RELCTRL-01. No secrets in output.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
MIGRATION_FILE_RE = re.compile(r"^(.+?)_.+\.sql$")
CERT_OK = {
    "PASS",
}


class ParityValidationError(ValueError):
    """Raised when release parity evidence fails validation."""


def _require_sha(value: str, label: str) -> str:
    value = (value or "").strip().lower()
    if not SHA_RE.match(value):
        raise ParityValidationError(f"{label} must be a 40-char git SHA, got {value!r}")
    return value


def repo_migration_versions(migrations_dir: Path) -> list[str]:
    versions: list[str] = []
    for path in sorted(migrations_dir.glob("*.sql")):
        match = MIGRATION_FILE_RE.match(path.name)
        if not match:
            raise ParityValidationError(f"unexpected migration filename: {path.name}")
        versions.append(match.group(1))
    if not versions:
        raise ParityValidationError(f"no migrations in {migrations_dir}")
    return versions


def normalize_migration_version(value: str, ledger: list[str]) -> str:
    """Map a migration label to its ledger version prefix."""
    value = value.strip()
    if value in ledger:
        return value
    # Accept full filename stems like 0071_vendor_listing_compare_at
    for version in ledger:
        if value == version or value.startswith(f"{version}_"):
            return version
    raise ParityValidationError(f"unknown migration version label: {value!r}")


def migration_at_least(version: str, baseline: str, ledger: list[str]) -> bool:
    version = normalize_migration_version(version, ledger)
    baseline = normalize_migration_version(baseline, ledger)
    if version not in ledger or baseline not in ledger:
        return False
    return ledger.index(version) >= ledger.index(baseline)


def load_contract(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ParityValidationError(f"{path} must contain a JSON object")
    return data


def fetch_api_fingerprint(api_base_url: str, timeout: float = 20.0) -> dict[str, Any]:
    url = f"{api_base_url.rstrip('/')}/fingerprint"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise ParityValidationError(f"could not fetch API fingerprint from {url}: {exc}") from exc
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ParityValidationError(f"invalid JSON from {url}") from exc
    if not isinstance(data, dict):
        raise ParityValidationError("API fingerprint must be a JSON object")
    return data


def validate_release_parity(
    contract: dict[str, Any],
    *,
    candidate_sha: str,
    migrations_dir: Path,
    api_base_url: str | None = None,
    skip_live_api: bool = False,
) -> None:
    """Validate parity contract against candidate SHA and optional live API."""
    candidate = _require_sha(candidate_sha, "candidate_sha")
    frontend = _require_sha(str(contract.get("candidate_frontend_sha", "")), "candidate_frontend_sha")
    api_required = _require_sha(str(contract.get("candidate_api_sha", "")), "candidate_api_sha")
    api_observed = _require_sha(
        str(contract.get("production_api_sha_observed", "")), "production_api_sha_observed"
    )

    baseline = str(contract.get("required_db_migration_baseline", "")).strip()
    if not baseline:
        raise ParityValidationError("required_db_migration_baseline is required")

    db_evidence_run_id = str(contract.get("production_db_evidence_run_id", "")).strip()
    if not db_evidence_run_id.isdigit():
        raise ParityValidationError(
            "production_db_evidence_run_id must be a numeric GitHub Actions run id "
            "from capture-production-db-evidence.yml"
        )

    if frontend != candidate:
        raise ParityValidationError(
            f"candidate_frontend_sha={frontend} != workflow candidate_sha={candidate}"
        )

    staging = contract.get("staging_certification")
    if not isinstance(staging, dict):
        raise ParityValidationError("staging_certification object is required")

    staging_result = str(staging.get("result", "")).strip()
    if staging_result not in CERT_OK:
        raise ParityValidationError(
            f"staging_certification.result={staging_result!r} is not certifiable"
        )

    staging_sha = _require_sha(str(staging.get("candidate_sha", "")), "staging_certification.candidate_sha")
    staging_frontend = _require_sha(
        str(staging.get("staging_frontend_sha", staging_sha)), "staging_certification.staging_frontend_sha"
    )
    if staging_sha != candidate or staging_frontend != candidate:
        raise ParityValidationError(
            "staging certification SHA mismatch: "
            f"staging={staging_sha[:12]} frontend={staging_frontend[:12]} candidate={candidate[:12]}"
        )

    if not staging.get("certified_at") or not staging.get("evidence_run_id"):
        raise ParityValidationError("staging_certification.certified_at and evidence_run_id are required")

    # DB parity is proven by machine-generated evidence + live read-only verification
    # (validate_production_db_evidence.py). The contract only carries the run id binding.
    # When SHAs differ, frontend promotion is blocked until API is coordinated.
    if api_observed != api_required:
        raise ParityValidationError(
            f"production_api_sha_observed={api_observed[:12]} "
            f"!= candidate_api_sha={api_required[:12]} — API/frontend skew"
        )

    if not skip_live_api and api_base_url:
        live = fetch_api_fingerprint(api_base_url)
        live_sha = str(live.get("git_sha") or "").strip().lower()
        if not SHA_RE.match(live_sha):
            raise ParityValidationError(f"live API fingerprint git_sha invalid: {live_sha!r}")
        if live_sha != api_observed:
            raise ParityValidationError(
                f"live API git_sha={live_sha[:12]} != contract production_api_sha_observed={api_observed[:12]}"
            )
        env = str(live.get("env") or "")
        if env != "production":
            raise ParityValidationError(f"live API env={env!r} want production")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate release parity evidence (RELCTRL-01)")
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument(
        "--migrations-dir",
        type=Path,
        default=Path("supabase/migrations"),
    )
    parser.add_argument(
        "--api-base-url",
        default="https://api.vergeo5.com",
        help="Read-only Production API for fingerprint cross-check",
    )
    parser.add_argument(
        "--skip-live-api",
        action="store_true",
        help="Skip live fingerprint fetch (unit tests / offline)",
    )
    args = parser.parse_args(argv)

    try:
        contract = load_contract(args.contract)
        validate_release_parity(
            contract,
            candidate_sha=args.candidate_sha,
            migrations_dir=args.migrations_dir,
            api_base_url=args.api_base_url,
            skip_live_api=args.skip_live_api,
        )
    except ParityValidationError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    print(f"parity OK for candidate {args.candidate_sha[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
