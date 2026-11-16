#!/usr/bin/env python3
"""Print the pytest files of one deterministic shard (CI-SPEED).

Greedy size-balanced bin packing over every `test_*.py` / `*_test.py` under the
test root, minus explicit ignores. Every file lands in exactly one shard, so the
union of all shards is the whole suite; `--check` proves that.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def discover(root: Path, ignores: set[str]) -> list[Path]:
    found = {
        p for pattern in ("test_*.py", "*_test.py") for p in root.rglob(pattern)
        if "__pycache__" not in p.parts
    }
    return sorted(p for p in found if p.as_posix() not in ignores)


def shards(files: list[Path], total: int) -> list[list[Path]]:
    bins: list[list[Path]] = [[] for _ in range(total)]
    loads = [0] * total
    # Heaviest first; name as the tie-break keeps the split reproducible.
    for path in sorted(files, key=lambda p: (-p.stat().st_size, p.as_posix())):
        target = loads.index(min(loads))
        bins[target].append(path)
        loads[target] += path.stat().st_size
    return [sorted(b) for b in bins]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="tests")
    parser.add_argument("--total", type=int, required=True)
    parser.add_argument("--shard", type=int, help="1-based shard index")
    parser.add_argument("--ignore", action="append", default=[])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    files = discover(Path(args.root), set(args.ignore))
    split = shards(files, args.total)
    if args.check:
        flat = [p for b in split for p in b]
        assert sorted(flat) == files and len(set(flat)) == len(flat), "shards lose or repeat files"
        print(f"ok: {len(files)} files in {args.total} shards: {[len(b) for b in split]}")
        return 0
    if args.shard is None or not 1 <= args.shard <= args.total:
        parser.error("--shard must be within 1..total")
    print("\n".join(p.as_posix() for p in split[args.shard - 1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
