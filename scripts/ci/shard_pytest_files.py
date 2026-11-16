#!/usr/bin/env python3
"""Print the pytest files of one deterministic shard (CI-SPEED).

Greedy size-balanced bin packing over every `test_*.py` / `*_test.py` under the
test root, minus explicit ignores. Every file lands in exactly one shard, so the
union of all shards is the whole suite; `--check` proves that.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def discover(root: Path, ignores: set[str]) -> list[Path]:
    found = {
        p for pattern in ("test_*.py", "*_test.py") for p in root.rglob(pattern)
        if "__pycache__" not in p.parts
    }
    return sorted(p for p in found if p.as_posix() not in ignores)


def load_weights(path: str | None) -> dict[str, float]:
    if not path or not Path(path).is_file():
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {str(k): float(v) for k, v in data.items()}


def shards(
    files: list[Path],
    total: int,
    weights: dict[str, float] | None = None,
    spread: set[str] | None = None,
    workers: int = 4,
) -> list[list[Path]]:
    """Longest-processing-time packing on measured seconds per file.

    Files without a measured weight (new tests) fall back to a size-derived
    estimate (roughly 1 s per 10 KB), so a stale weights file never drops a file.
    """
    weights = weights or {}

    spread = spread or set()

    def weight(p: Path) -> float:
        seconds = weights.get(p.as_posix(), p.stat().st_size / 10_000)
        # A spread file is run per-test across all workers, not pinned to one.
        return seconds / workers if p.as_posix() in spread else seconds

    bins: list[list[Path]] = [[] for _ in range(total)]
    loads = [0.0] * total
    # Heaviest first; name as the tie-break keeps the split reproducible.
    for path in sorted(files, key=lambda p: (-weight(p), p.as_posix())):
        target = loads.index(min(loads))
        bins[target].append(path)
        loads[target] += weight(path)
    return [sorted(b) for b in bins]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="tests")
    parser.add_argument("--total", type=int, required=True)
    parser.add_argument("--shard", type=int, help="1-based shard index")
    parser.add_argument("--ignore", action="append", default=[])
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--spread", action="append", default=[],
        help="file whose independent parametrized tests run per-test across workers; "
        "printed with a `spread:` prefix",
    )
    parser.add_argument(
        "--weights", help="JSON {test file: seconds} measured by a previous run"
    )
    args = parser.parse_args()
    files = discover(Path(args.root), set(args.ignore))
    split = shards(files, args.total, load_weights(args.weights), set(args.spread))
    if args.check:
        flat = [p for b in split for p in b]
        assert sorted(flat) == files and len(set(flat)) == len(flat), "shards lose or repeat files"
        print(f"ok: {len(files)} files in {args.total} shards: {[len(b) for b in split]}")
        return 0
    if args.shard is None or not 1 <= args.shard <= args.total:
        parser.error("--shard must be within 1..total")
    for path in split[args.shard - 1]:
        marker = "spread:" if path.as_posix() in args.spread else ""
        print(f"{marker}{path.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
