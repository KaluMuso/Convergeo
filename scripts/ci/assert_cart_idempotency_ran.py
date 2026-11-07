#!/usr/bin/env python3
"""Require 16 PostgreSQL cases and four URI guards; retain sanitized outcomes."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

MODULE = "tests.test_cart_add_idempotency_db"
ORIGINAL_POSTGRESQL_TESTS = (
    "test_same_key_replay_mismatch_and_cart_scope",
    "test_concurrent_same_key_commits_once",
    "test_distinct_keys_revalidate_stale_snapshot",
    "test_rollback_does_not_strand_key_or_increment",
    "test_owner_and_client_grants",
    "test_rejects_wrong_or_inactive_owner[True-wrong_guest-cart.owner_mismatch]",
    "test_rejects_wrong_or_inactive_owner[False-guest_on_user_cart-cart.owner_mismatch]",
    "test_rejects_wrong_or_inactive_owner[False-both-cart.owner_invalid]",
    "test_rejects_wrong_or_inactive_owner[False-neither-cart.owner_invalid]",
    "test_rejects_wrong_or_inactive_owner[False-inactive-cart.owner_mismatch]",
    "test_rejects_malformed_keys_without_writing[]",
    "test_rejects_malformed_keys_without_writing[unsafe key]",
    f"test_rejects_malformed_keys_without_writing[{'x' * 129}]",
    "test_authenticated_role_cannot_execute_rpc",
)
ADDITIONAL_POSTGRESQL_TESTS = (
    "test_stale_location_snapshot_does_not_claim_or_increment",
    "test_canonical_api_body_accepts_uppercase_uuid_rpc_input",
)
URI_GUARD_TESTS = (
    "test_target_guard_rejects_transport_overrides_before_connect[postgresql://postgres@localhost/cart_idem_test?host=other-host]",
    "test_target_guard_rejects_transport_overrides_before_connect[postgresql://postgres@localhost/cart_idem_test?dbname=another_database]",
    "test_target_guard_rejects_transport_overrides_before_connect[postgresql://postgres@localhost/cart_idem_test?service=another_service]",
    "test_target_guard_rejects_transport_overrides_before_connect[postgresql://postgres@other-host/cart_idem_test]",
)
CASE_GROUPS = {
    "original_postgresql": ORIGINAL_POSTGRESQL_TESTS,
    "additional_postgresql": ADDITIONAL_POSTGRESQL_TESTS,
    "uri_guards": URI_GUARD_TESTS,
}
REQUIRED_TESTS = (*ORIGINAL_POSTGRESQL_TESTS, *ADDITIONAL_POSTGRESQL_TESTS, *URI_GUARD_TESTS)
NON_PASSING = {"skipped", "failure", "error"}
ALLOWED_TAGS = {
    "testsuites",
    "testsuite",
    "testcase",
    *NON_PASSING,
    "properties",
    "property",
    "system-out",
    "system-err",
}


def problems(root: ET.Element) -> list[str]:
    """Inspect original records, never a count-only or sanitized substitute."""
    issues = []
    if root.tag not in {"testsuites", "testsuite"}:
        issues.append("invalid_root")
    if any(element.tag not in ALLOWED_TAGS for element in root.iter()):
        issues.append("unexpected_xml_element")
    for element in root.iter():
        children = {child.tag for child in element}
        allowed = {
            "testsuites": {"testsuite"},
            "testsuite": {"testcase", "properties", "system-out", "system-err"},
            "testcase": {*NON_PASSING, "properties", "system-out", "system-err"},
            "properties": {"property"},
        }.get(element.tag, set())
        if not children <= allowed:
            issues.append("invalid_report_structure")
            break
    suites = list(root.iter("testsuite"))
    if len(suites) != 1:
        issues.append("expected_one_suite")
    else:
        expected_counts = {
            "tests": str(len(REQUIRED_TESTS)),
            "failures": "0",
            "errors": "0",
            "skipped": "0",
        }
        if any(suites[0].get(key) != value for key, value in expected_counts.items()):
            issues.append("suite_counts_not_all_passed")
    cases = list(root.iter("testcase"))
    if Counter(case.get("name") for case in cases) != Counter(REQUIRED_TESTS):
        issues.append("required_case_inventory_mismatch")
    if any(case.get("classname") != MODULE for case in cases):
        issues.append("wrong_test_module")
    if any(case.find(kind) is not None for case in cases for kind in NON_PASSING):
        issues.append("non_passing_case")
    return issues


def sanitized(root: ET.Element) -> ET.Element:
    """Keep case identities/outcomes/times; remove captures, properties and traces."""
    result = copy.deepcopy(root)
    for element in result.iter():
        for child in list(element):
            if child.tag in {"properties", "system-out", "system-err"}:
                element.remove(child)
        if element.tag not in ALLOWED_TAGS:
            element.tag = "redacted-element"
        attributes = {}
        for key, value in element.attrib.items():
            if key in {"tests", "failures", "errors", "skipped", "time"}:
                if re.fullmatch(r"\d+(?:\.\d+)?", value):
                    attributes[key] = value
            elif key == "name" and element.tag == "testcase":
                attributes[key] = value if value in REQUIRED_TESTS else "unexpected-case"
            elif key == "classname" and element.tag == "testcase":
                attributes[key] = MODULE if value == MODULE else "unexpected-module"
            elif key == "name" and element.tag == "testsuite":
                attributes[key] = "pytest"
        element.attrib.clear()
        element.attrib.update(attributes)
        element.text = (
            "Outcome retained; diagnostics redacted." if element.tag in NON_PASSING else None
        )
        element.tail = None
    return result


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print("usage: assert_cart_idempotency_ran.py INPUT.xml SANITIZED.xml VALIDATION.json")
        return 2
    source, output, receipt = (Path(value) for value in argv[1:])
    issues: list[str]
    raw_hash = None
    try:
        raw = source.read_bytes()
        raw_hash = hashlib.sha256(raw).hexdigest()
        if b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:
            raise ValueError("DTD is not permitted")
        root = ET.fromstring(raw)
        issues = problems(root)
        ET.ElementTree(sanitized(root)).write(output, encoding="utf-8", xml_declaration=True)
    except (OSError, ET.ParseError, ValueError):
        issues = ["missing_or_invalid_report"]
    evidence = {
        "required_case_groups": {name: list(cases) for name, cases in CASE_GROUPS.items()},
        "postgresql_cases": len(ORIGINAL_POSTGRESQL_TESTS) + len(ADDITIONAL_POSTGRESQL_TESTS),
        "uri_guard_cases": len(URI_GUARD_TESTS),
        "qualified": not issues,
        "required_cases": list(REQUIRED_TESTS),
        "problems": issues,
        "original_junit_sha256": raw_hash,
    }
    receipt.write_text(json.dumps(evidence, indent=2) + "\n")
    print(
        "FAIL: " + ", ".join(issues)
        if issues
        else (
            "OK: 20 cart cases passed (16 PostgreSQL: 14 original + 2 additional; "
            "4 URI guards; 0 skipped)."
        )
    )
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
