#!/usr/bin/env python3
"""Bind staging manifest verified_source_sha fields to the current repository HEAD."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def bind_manifest(path: Path, *, sha: str) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data["verified_source_sha"] = sha
    for item in data.get("exact_aliases", []):
        if isinstance(item, dict):
            item["verified_source_sha"] = sha
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    sha = subprocess.check_output(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        text=True,
    ).strip()
    bind_manifest(repo_root / "scripts/ci/staging-migration-equivalence.json", sha=sha)
    bind_manifest(repo_root / "scripts/ci/staging-physical-parity-manifest.json", sha=sha)
    print(sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
