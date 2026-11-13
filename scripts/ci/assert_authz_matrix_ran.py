#!/usr/bin/env python3
"""Prove the exact checkout-specific authorization matrix executed cleanly.

The expected node inventory is collected independently from the JUnit execution
report. Both documents are bound to the same trusted checkout SHA, and the
report must contain exactly one passing testcase for every collected node ID.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
INVENTORY_KIND = "convergeo-authorization-matrix-inventory"
TEST_FILE = "tests/test_authz_matrix.py"
EXPECTED_CLASSNAME = "tests.test_authz_matrix"
WORKING_DIRECTORY = "services/api"
COLLECTION_COMMAND = (
    "python",
    "-m",
    "pytest",
    "--collect-only",
    "-q",
    TEST_FILE,
)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
COLLECTION_SUMMARY_RE = re.compile(r"(?m)^([0-9]+) tests? collected(?: in .*)?$")
NON_PASSING = ("skipped", "failure", "error")


class InventoryError(ValueError):
    """Raised when expected-inventory creation cannot be trusted."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _file_sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _nodeids_sha256(nodeids: Sequence[str]) -> str:
    return _sha256_bytes(("\n".join(nodeids) + "\n").encode())


def _full_sha(value: str) -> str:
    if SHA_RE.fullmatch(value or "") is None:
        raise InventoryError("checkout SHA must be exactly 40 lowercase hexadecimal characters")
    return value


def checkout_sha(repo_root: Path) -> str:
    """Read the actual Git checkout identity instead of trusting an input label."""

    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD^{commit}"],
            cwd=repo_root.resolve(),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise InventoryError(f"cannot inspect repository checkout: {exc}") from None
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip().splitlines()
        suffix = f": {detail[-1]}" if detail else ""
        raise InventoryError(f"cannot inspect repository checkout{suffix}")
    try:
        return _full_sha(completed.stdout.strip())
    except InventoryError:
        raise InventoryError("repository HEAD is not an exact commit SHA") from None


def verify_checkout(repo_root: Path, expected_sha: str) -> str:
    """Require the supplied CI identity to name the checkout being inspected."""

    expected_sha = _full_sha(expected_sha)
    resolved_root = repo_root.resolve()
    actual_sha = checkout_sha(resolved_root)
    if actual_sha != expected_sha:
        raise InventoryError(
            f"requested checkout {expected_sha} does not match repository HEAD {actual_sha}"
        )
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=no"],
            cwd=resolved_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise InventoryError(f"cannot inspect tracked checkout state: {exc}") from None
    if status.returncode != 0:
        detail = (status.stderr or status.stdout).strip().splitlines()
        suffix = f": {detail[-1]}" if detail else ""
        raise InventoryError(f"cannot inspect tracked checkout state{suffix}")
    if status.stdout.strip():
        raise InventoryError("repository has tracked changes outside the named checkout")
    return actual_sha


def collect_nodeids(repo_root: Path) -> tuple[str, ...]:
    """Collect exact node IDs in a process independent from the test execution."""

    api_root = repo_root.resolve() / WORKING_DIRECTORY
    test_file = api_root / TEST_FILE
    if not test_file.is_file():
        raise InventoryError(f"authorization matrix test file is missing: {test_file}")

    command = [sys.executable, "-m", "pytest", "--collect-only", "-q", TEST_FILE]
    completed = subprocess.run(
        command,
        cwd=api_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip().splitlines()
        suffix = f": {detail[-1]}" if detail else ""
        raise InventoryError(f"authorization matrix collection failed{suffix}")

    collected_lines = tuple(
        line.strip()
        for line in completed.stdout.splitlines()
        if line.strip().startswith("tests/") and "::" in line
    )
    out_of_scope = sorted(
        nodeid for nodeid in collected_lines if not nodeid.startswith(f"{TEST_FILE}::")
    )
    if out_of_scope:
        raise InventoryError(
            f"authorization matrix collection returned out-of-scope node IDs: {out_of_scope}"
        )
    collected = tuple(collected_lines)
    if not collected:
        raise InventoryError("authorization matrix collection returned no testcase identities")
    duplicates = sorted(name for name, count in Counter(collected).items() if count != 1)
    if duplicates:
        raise InventoryError(f"authorization matrix collection returned duplicates: {duplicates}")
    summaries = COLLECTION_SUMMARY_RE.findall(completed.stdout)
    if len(summaries) != 1 or int(summaries[0]) != len(collected):
        raise InventoryError(
            "authorization matrix collection summary does not match exact node IDs"
        )
    return collected


def build_inventory(
    *, repo_root: Path, checkout_sha: str, nodeids: Sequence[str]
) -> dict[str, Any]:
    """Build a strict manifest for one independently collected checkout inventory."""

    checkout_sha = _full_sha(checkout_sha)
    test_file = repo_root.resolve() / WORKING_DIRECTORY / TEST_FILE
    if not test_file.is_file():
        raise InventoryError(f"authorization matrix test file is missing: {test_file}")
    exact_nodeids = tuple(nodeids)
    if not exact_nodeids:
        raise InventoryError("authorization matrix inventory is empty")
    if any(
        not isinstance(nodeid, str) or not nodeid.startswith(f"{TEST_FILE}::")
        for nodeid in exact_nodeids
    ):
        raise InventoryError("authorization matrix inventory contains an invalid node ID")
    duplicates = sorted(name for name, count in Counter(exact_nodeids).items() if count != 1)
    if duplicates:
        raise InventoryError(f"authorization matrix inventory contains duplicates: {duplicates}")

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": INVENTORY_KIND,
        "checkout_sha": checkout_sha,
        "working_directory": WORKING_DIRECTORY,
        "collection_command": list(COLLECTION_COMMAND),
        "test_file": TEST_FILE,
        "test_file_sha256": _file_sha256(test_file),
        "case_count": len(exact_nodeids),
        "nodeids_sha256": _nodeids_sha256(exact_nodeids),
        "nodeids": list(exact_nodeids),
    }


def write_inventory(path: Path, inventory: dict[str, Any]) -> None:
    """Write once so a stale file cannot be silently reused in the same job."""

    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(inventory, handle, indent=2)
            handle.write("\n")
    except FileExistsError:
        raise InventoryError(f"refusing to overwrite existing inventory: {path}") from None
    except OSError as exc:
        raise InventoryError(f"cannot write authorization inventory: {exc}") from None


def _read_inventory(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    if not path.is_file():
        return None, [f"expected inventory not written: {path}"]
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return None, [f"expected inventory is unreadable: {exc}"]
    if not isinstance(value, dict):
        return None, ["expected inventory must be a JSON object"]
    return value, []


def validate_inventory(
    inventory: dict[str, Any], *, checkout_sha: str, repo_root: Path
) -> tuple[tuple[str, ...], list[str]]:
    """Validate provenance and internal consistency of the expected inventory."""

    problems: list[str] = []
    try:
        checkout_sha = _full_sha(checkout_sha)
    except InventoryError as exc:
        return (), [str(exc)]

    expected_keys = {
        "schema_version",
        "kind",
        "checkout_sha",
        "working_directory",
        "collection_command",
        "test_file",
        "test_file_sha256",
        "case_count",
        "nodeids_sha256",
        "nodeids",
    }
    if set(inventory) != expected_keys:
        problems.append("expected inventory schema keys do not match the trusted format")
    if inventory.get("schema_version") != SCHEMA_VERSION:
        problems.append("expected inventory schema version mismatch")
    if inventory.get("kind") != INVENTORY_KIND:
        problems.append("expected inventory kind mismatch")
    if inventory.get("checkout_sha") != checkout_sha:
        problems.append("expected inventory belongs to a stale checkout")
    if inventory.get("working_directory") != WORKING_DIRECTORY:
        problems.append("expected inventory working directory mismatch")
    if inventory.get("collection_command") != list(COLLECTION_COMMAND):
        problems.append("expected inventory collection command mismatch")
    if inventory.get("test_file") != TEST_FILE:
        problems.append("expected inventory test file mismatch")

    test_file = repo_root.resolve() / WORKING_DIRECTORY / TEST_FILE
    try:
        current_file_sha = _file_sha256(test_file)
    except OSError as exc:
        problems.append(f"current authorization matrix source is unreadable: {exc}")
    else:
        if inventory.get("test_file_sha256") != current_file_sha:
            problems.append("expected inventory test source does not match this checkout")

    raw_nodeids = inventory.get("nodeids")
    if not isinstance(raw_nodeids, list) or not raw_nodeids:
        problems.append("expected inventory nodeids must be a non-empty list")
        return (), problems
    if any(not isinstance(nodeid, str) for nodeid in raw_nodeids):
        problems.append("expected inventory contains a non-string node ID")
        return (), problems
    nodeids = tuple(raw_nodeids)
    if any(not nodeid.startswith(f"{TEST_FILE}::") for nodeid in nodeids):
        problems.append("expected inventory contains an out-of-scope node ID")
    duplicates = sorted(name for name, count in Counter(nodeids).items() if count != 1)
    if duplicates:
        problems.append(f"expected inventory contains duplicate node IDs: {duplicates}")
    if type(inventory.get("case_count")) is not int or inventory["case_count"] != len(nodeids):
        problems.append("expected inventory case count is inconsistent")
    if inventory.get("nodeids_sha256") != _nodeids_sha256(nodeids):
        problems.append("expected inventory node ID digest is inconsistent")
    return nodeids, problems


def _integer_attribute(element: ET.Element, name: str, problems: list[str]) -> int | None:
    value = element.get(name)
    if value is None:
        return None
    if not value.isdigit():
        problems.append(f"JUnit {element.tag} {name} counter is invalid")
        return None
    return int(value)


def _validate_declared_counts(
    element: ET.Element, cases: Sequence[ET.Element], problems: list[str]
) -> None:
    computed = {
        "tests": len(cases),
        "failures": sum(case.find("failure") is not None for case in cases),
        "errors": sum(case.find("error") is not None for case in cases),
        "skipped": sum(case.find("skipped") is not None for case in cases),
    }
    for name, actual in computed.items():
        declared = _integer_attribute(element, name, problems)
        if declared is not None and declared != actual:
            problems.append(
                f"JUnit {element.tag} {name} counter is inconsistent: "
                f"declared {declared}, observed {actual}"
            )


def validate_report(
    report: Path,
    inventory_path: Path,
    *,
    checkout_sha: str,
    repo_root: Path,
) -> list[str]:
    """Return fail-closed problems in the expected inventory or execution report."""

    try:
        verify_checkout(repo_root, checkout_sha)
    except InventoryError as exc:
        return [str(exc)]
    inventory, problems = _read_inventory(inventory_path)
    if inventory is None:
        return problems
    expected, inventory_problems = validate_inventory(
        inventory, checkout_sha=checkout_sha, repo_root=repo_root
    )
    problems.extend(inventory_problems)

    if not report.is_file():
        problems.append(f"JUnit report not written: {report}")
        return problems
    try:
        root = ET.parse(report).getroot()
    except (ET.ParseError, OSError) as exc:
        problems.append(f"JUnit report is unreadable: {exc}")
        return problems

    cases = list(root.iter("testcase"))
    actual: list[str] = []
    for case in cases:
        name = case.get("name") or ""
        classname = case.get("classname")
        if classname != EXPECTED_CLASSNAME:
            problems.append(
                f"unexpected testcase owner {classname!r} for {name!r}; "
                f"expected {EXPECTED_CLASSNAME!r}"
            )
        if not name:
            problems.append("JUnit testcase has no name")
            continue
        nodeid = f"{TEST_FILE}::{name}"
        actual.append(nodeid)
        states = [state for state in NON_PASSING if case.find(state) is not None]
        if len(states) > 1:
            problems.append(f"{nodeid}: inconsistent outcomes {states}")
        elif states:
            problems.append(f"{nodeid}: {states[0].upper()}")

    actual_counts = Counter(actual)
    duplicates = sorted(name for name, count in actual_counts.items() if count != 1)
    if duplicates:
        problems.append(f"JUnit report contains duplicate testcase identities: {duplicates}")

    expected_set = set(expected)
    actual_set = set(actual)
    missing = sorted(expected_set - actual_set)
    unexpected = sorted(actual_set - expected_set)
    if missing:
        problems.append(f"expected testcase identities missing from JUnit: {missing}")
    if unexpected:
        problems.append(f"unexpected testcase identities in JUnit: {unexpected}")

    for suite in root.iter("testsuite"):
        _validate_declared_counts(suite, list(suite.iter("testcase")), problems)
    if root.tag == "testsuites":
        _validate_declared_counts(root, cases, problems)
    return problems


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    collect = subparsers.add_parser("collect")
    collect.add_argument("--inventory", required=True, type=Path)
    collect.add_argument("--repo-root", required=True, type=Path)
    collect.add_argument("--checkout-sha", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("report", type=Path)
    validate.add_argument("--inventory", required=True, type=Path)
    validate.add_argument("--repo-root", required=True, type=Path)
    validate.add_argument("--checkout-sha", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "collect":
        try:
            verified_sha = verify_checkout(args.repo_root, args.checkout_sha)
            nodeids = collect_nodeids(args.repo_root)
            collected_inventory = build_inventory(
                repo_root=args.repo_root,
                checkout_sha=verified_sha,
                nodeids=nodeids,
            )
            write_inventory(args.inventory, collected_inventory)
        except InventoryError as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 1
        print(
            f"OK: collected {len(nodeids)} exact authorization testcase identities "
            f"for checkout {verified_sha}."
        )
        return 0

    problems = validate_report(
        args.report,
        args.inventory,
        checkout_sha=args.checkout_sha,
        repo_root=args.repo_root,
    )
    if problems:
        print("FAIL: authorization matrix did not match its trusted inventory:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    validated_inventory, _ = _read_inventory(args.inventory)
    assert validated_inventory is not None
    print(
        f"OK: all {validated_inventory['case_count']} exact authorization testcase identities "
        "passed once with consistent JUnit outcomes."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
