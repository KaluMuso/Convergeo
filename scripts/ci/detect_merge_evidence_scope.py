#!/usr/bin/env python3
"""Detect whether a PR to master requires pre-existing merge release evidence.

Fail-closed scope detection (RELCTRL-02). Only narrowly defined governance-only
changes may skip the merge evidence gate.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

GOVERNANCE_PREFIXES = (
    ".github/",
    "scripts/ci/",
    "scripts/qa/",
    "docs/",
)

GOVERNANCE_EXACT = frozenset(
    {
        "infra/merge-release-evidence.example.json",
        "infra/release-evidence-contract.example.json",
        "infra/staging-certification-evidence.example.json",
    }
)

NON_RUNTIME_TEST_PREFIX = "services/api/tests/"


def changed_files(base: str, head: str) -> list[str]:
    proc = subprocess.run(
        ["git", "diff", "--name-only", base, head],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def is_governance_only_path(path: str) -> bool:
    if path in GOVERNANCE_EXACT:
        return True
    if path.startswith(NON_RUNTIME_TEST_PREFIX):
        return True
    return any(path.startswith(prefix) for prefix in GOVERNANCE_PREFIXES)


def requires_merge_evidence(paths: list[str]) -> bool:
    if not paths:
        return False
    return any(not is_governance_only_path(path) for path in paths)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="Merge base commit SHA")
    parser.add_argument("--head", help="PR head commit SHA")
    parser.add_argument(
        "--paths",
        nargs="*",
        default=None,
        help="Offline test mode: evaluate explicit changed paths instead of git diff",
    )
    parser.add_argument(
        "--github-output",
        type=Path,
        default=None,
        help="Append required=true|false to GitHub Actions output file",
    )
    args = parser.parse_args(argv)

    if args.paths is not None:
        paths = list(args.paths)
    else:
        if not args.base or not args.head:
            parser.error("--base and --head are required unless --paths is provided")
        paths = changed_files(args.base, args.head)
    required = requires_merge_evidence(paths)

    if args.github_output is not None:
        args.github_output.parent.mkdir(parents=True, exist_ok=True)
        with args.github_output.open("a", encoding="utf-8") as fh:
            fh.write(f"required={'true' if required else 'false'}\n")

    if required:
        print("merge evidence required")
    else:
        print("governance-only PR — merge evidence not required")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
