#!/usr/bin/env python3
"""Fail unless the complete authorization matrix executed without silent skips."""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EXPECTED_CLASSNAME = "tests.test_authz_matrix"
MINIMUM_CASES = 896
REQUIRED_TEST_FAMILIES = (
    "test_every_route_is_classified",
    "test_matrix_covers_every_route_times_role",
    "test_matrix_summary",
    "test_anonymous_denied_on_protected_routes",
    "test_wrong_role_denied",
    "test_internal_endpoints_require_token",
    "test_webhook_endpoints_reject_unsigned",
    "test_idor_id_routes_deny_anonymous",
    "test_public_routes_have_no_auth_guard",
    "test_role_routes_expose_expected_role_guard",
)
NON_PASSING = ("skipped", "failure", "error")


def validate_report(report: Path) -> list[str]:
    """Return fail-closed problems found in one pytest JUnit report."""

    if not report.is_file():
        return [f"JUnit report not written: {report}"]

    try:
        root = ET.parse(report).getroot()
    except (ET.ParseError, OSError) as exc:
        return [f"JUnit report is unreadable: {exc}"]

    cases = list(root.iter("testcase"))
    problems: list[str] = []
    if len(cases) < MINIMUM_CASES:
        problems.append(f"only {len(cases)} cases reported; expected at least {MINIMUM_CASES}")

    names: list[str] = []
    for case in cases:
        name = case.get("name") or ""
        names.append(name)
        classname = case.get("classname")
        if classname != EXPECTED_CLASSNAME:
            problems.append(
                f"unexpected testcase owner {classname!r} for {name!r}; "
                f"expected {EXPECTED_CLASSNAME!r}"
            )
        for state in NON_PASSING:
            if case.find(state) is not None:
                problems.append(f"{name or '<unnamed>'}: {state.upper()}")
                break

    for family in REQUIRED_TEST_FAMILIES:
        if not any(name == family or name.startswith(f"{family}[") for name in names):
            problems.append(f"required test family missing: {family}")

    return problems


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {Path(argv[0]).name} <junit-xml>", file=sys.stderr)
        return 2

    problems = validate_report(Path(argv[1]))
    if problems:
        print("FAIL: authorization matrix did not run completely:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(
        f"OK: authorization matrix reported at least {MINIMUM_CASES} passing cases "
        "across every required family (0 skipped)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
