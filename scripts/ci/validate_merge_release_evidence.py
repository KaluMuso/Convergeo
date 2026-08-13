#!/usr/bin/env python3
"""Validate staging certification evidence required before merging to master.

Fail-closed merge gate (RELCTRL-01). Uses offline evidence only — no Production
DB credentials. The release/integration PR into master must carry
infra/merge-release-evidence.json binding the PR head SHA to staging certification.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
CERT_OK = {
    "CERTIFIABLE_AFTER_INTEGRATION",
    "PASS",
    "pass",
    "success",
    "SUCCESS",
}
DEFAULT_EVIDENCE = Path("infra/merge-release-evidence.json")


class MergeEvidenceError(ValueError):
    """Raised when merge release evidence fails validation."""


def _require_sha(value: str, label: str) -> str:
    value = (value or "").strip().lower()
    if not SHA_RE.match(value):
        raise MergeEvidenceError(f"{label} must be a 40-char git SHA, got {value!r}")
    return value


def load_evidence(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise MergeEvidenceError(f"merge evidence not found: {path}")
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise MergeEvidenceError(f"{path} must contain a JSON object")
    return data


def validate_merge_release_evidence(
    evidence: dict[str, Any],
    *,
    candidate_sha: str,
) -> None:
    candidate = _require_sha(candidate_sha, "candidate_sha")

    if str(evidence.get("schema_version")) != "1":
        raise MergeEvidenceError("schema_version must be '1'")

    head = _require_sha(str(evidence.get("candidate_sha", "")), "candidate_sha")
    if head != candidate:
        raise MergeEvidenceError(
            f"evidence candidate_sha={head[:12]} != PR head={candidate[:12]}"
        )

    staging = evidence.get("staging_certification")
    if not isinstance(staging, dict):
        raise MergeEvidenceError("staging_certification object is required")

    result = str(staging.get("result", "")).strip()
    if result not in CERT_OK:
        raise MergeEvidenceError(f"staging_certification.result={result!r} is not certifiable")

    staging_sha = _require_sha(
        str(staging.get("candidate_sha", "")), "staging_certification.candidate_sha"
    )
    staging_frontend = _require_sha(
        str(staging.get("staging_frontend_sha", staging_sha)),
        "staging_certification.staging_frontend_sha",
    )
    if staging_sha != candidate or staging_frontend != candidate:
        raise MergeEvidenceError("staging certification SHA must match PR head exactly")

    if not staging.get("certified_at"):
        raise MergeEvidenceError("staging_certification.certified_at is required")
    if not staging.get("evidence_run_id"):
        raise MergeEvidenceError("staging_certification.evidence_run_id is required")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate merge-to-master staging evidence")
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    args = parser.parse_args(argv)

    try:
        evidence = load_evidence(args.evidence)
        validate_merge_release_evidence(evidence, candidate_sha=args.candidate_sha)
    except MergeEvidenceError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    print(f"merge evidence OK for candidate {args.candidate_sha[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
