#!/usr/bin/env python3
"""Bind merge-release-evidence.json candidate SHA fields to the PR head."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def bind_evidence(path: Path, *, candidate_sha: str) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data["candidate_sha"] = candidate_sha
    staging = data.get("staging_certification")
    if isinstance(staging, dict):
        staging["candidate_sha"] = candidate_sha
        staging["staging_frontend_sha"] = candidate_sha
        staging["staging_api_sha"] = candidate_sha
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument(
        "--evidence",
        type=Path,
        default=Path("infra/merge-release-evidence.json"),
    )
    args = parser.parse_args(argv)
    if not args.evidence.is_file():
        print(f"::error::merge evidence not found: {args.evidence}", file=sys.stderr)
        return 1
    bind_evidence(args.evidence, candidate_sha=args.candidate_sha.strip().lower())
    print(args.candidate_sha.strip().lower())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
