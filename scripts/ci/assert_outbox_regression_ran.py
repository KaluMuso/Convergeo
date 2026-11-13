#!/usr/bin/env python3
"""Fail unless every named staging-cleanup regression actually PASSED.

`tests/test_seed_staging.py` reaches a real database through the module-scoped
`migrated_db` fixture, which calls `pytest.skip()` when Postgres is
unreachable, the migration shim cannot run, or an extension (pgvector) is
missing. A skip is not a failure, so `pytest` still exits 0 — and the `Python
API` job has no database at all, which is exactly how this coverage could go
green while never executing a single statement against Postgres.

This reads the JUnit report that step emits and fails on a case that is
missing, skipped, errored or failed. Machine-readable by design: the same XML
is uploaded as the run's evidence artifact.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# The behavioural outbox-cleanup cases. Renaming one here without renaming the
# test (or vice versa) fails this check rather than silently dropping coverage.
REQUIRED_TESTS = (
    "test_cleanup_deletes_outbox_rows_linked_only_by_checkout_group_id",
    "test_cleanup_deletes_outbox_rows_linked_only_by_order_id",
    "test_cleanup_preserves_outbox_rows_for_a_real_non_namespace_order",
    "test_cleanup_preserves_unrelated_outbox_rows",
    "test_repeat_cleanup_is_idempotent_and_leaves_no_outbox_residue",
)

NON_PASSING = ("skipped", "failure", "error")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {Path(argv[0]).name} <junit-xml>", file=sys.stderr)
        return 2

    report = Path(argv[1])
    if not report.is_file():
        print(f"FAIL: JUnit report not written: {report}", file=sys.stderr)
        return 1

    outcomes: dict[str, str] = {}
    for case in ET.parse(report).getroot().iter("testcase"):
        name = case.get("name")
        if name is None:
            continue
        state = "passed"
        for kind in NON_PASSING:
            if case.find(kind) is not None:
                state = kind
                break
        outcomes[name] = state

    problems = []
    for name in REQUIRED_TESTS:
        state = outcomes.get(name)
        if state is None:
            problems.append(f"{name}: MISSING from the report (never collected)")
        elif state != "passed":
            problems.append(f"{name}: {state.upper()} — it did not execute successfully")

    if problems:
        print(
            "FAIL: the staging-cleanup outbox regression did not run clean.\n"
            "These cases must execute against a real migrated Postgres:",
            file=sys.stderr,
        )
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(f"OK: {len(REQUIRED_TESTS)} outbox-cleanup regression cases passed (0 skipped).")
    for name in REQUIRED_TESTS:
        print(f"  - {name}: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
