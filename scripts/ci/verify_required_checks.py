#!/usr/bin/env python3
"""Assert required GitHub check-runs are success for a commit SHA."""

from __future__ import annotations

import json
import sys
from typing import Any

REQUIRED_SUBSTRINGS = [
    "JavaScript / TypeScript",
    "Python API",
    "Bundle, image lint",
    "Staging plane guards",
]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: verify_required_checks.py <check-runs.json>", file=sys.stderr)
        return 2

    doc: dict[str, Any] = json.loads(sys.argv[1])
    runs = doc.get("check_runs", [])
    found = {key: False for key in REQUIRED_SUBSTRINGS}

    for run in runs:
        name = str(run.get("name") or "")
        conclusion = str(run.get("conclusion") or "").lower()
        status = str(run.get("status") or "").lower()
        if status != "completed":
            continue
        for key in REQUIRED_SUBSTRINGS:
            if key in name:
                found[key] = conclusion == "success"

    missing = [key for key, ok in found.items() if not ok]
    if missing:
        print("::error::required checks missing or not success: " + ", ".join(missing))
        for run in runs:
            name = str(run.get("name") or "")
            if any(key in name for key in REQUIRED_SUBSTRINGS):
                print(
                    f"  - {name}: status={run.get('status')} conclusion={run.get('conclusion')}"
                )
        return 1

    print("required CI + Performance checks green for candidate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
