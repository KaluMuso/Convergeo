#!/usr/bin/env python3
"""Assert customer production health buildId matches candidate SHA."""

from __future__ import annotations

import json
import sys


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: verify_customer_build_id.py <health-json> <candidate-sha>", file=sys.stderr)
        return 2

    doc = json.loads(sys.argv[1])
    want = sys.argv[2].lower()
    build = str(doc.get("buildId") or "").lower()
    if build != want:
        print(f"::error::customer buildId={build!r} want {want!r}")
        return 1
    print(f"customer buildId OK: {build[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
