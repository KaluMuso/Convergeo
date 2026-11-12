"""Reconcile exact supplementary F2 and related identities, never pass partial suites."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from xml.etree import ElementTree

RELATED_MODULES = (
    "tests/test_order_state.py",
    "tests/test_job_completion.py",
    "tests/test_service_escrow.py",
    "tests/test_service_booking.py",
)
COLLECTION_SCHEMA = "convergeo.f2.related-collection.v1"


def _junit_key(identity: str) -> tuple[str, str]:
    # Parameter values may themselves contain '::'; only split the test spine.
    spine, bracket, parameter = identity.partition("[")
    parts = spine.split("::")
    if len(parts) < 2 or not parts[0].endswith(".py") or any(not p for p in parts):
        raise ValueError(f"Invalid test identity: {identity!r}")
    classname = parts[0][:-3].replace("/", ".")
    if len(parts) > 2:
        classname += "." + ".".join(parts[1:-1])
    return classname, parts[-1] + bracket + parameter


def _reconcile(
    expected: list[str], junit: Path, pytest_exit: int
) -> tuple[dict[str, object], bool]:
    if not expected or any(not isinstance(n, str) or not n.strip() for n in expected):
        raise ValueError("Expected identity list is empty or invalid")
    if len(expected) != len(set(expected)):
        raise ValueError("Expected identities are duplicated")
    keys = {_junit_key(n): n for n in expected}
    if len(keys) != len(expected):
        raise ValueError("JUnit identity mapping is ambiguous")
    outcomes: dict[str, str] = {}
    duplicates: list[str] = []
    unexpected: list[str] = []
    errors: list[str] = []
    if not junit.is_file():
        errors.append("JUnit evidence is missing")
    else:
        try:
            root = ElementTree.parse(junit)
            # Collection/setup errors can appear outside individual testcase nodes.
            if any(suite.find("error") is not None for suite in root.iter("testsuite")):
                errors.append("JUnit suite-level error")
            for node in root.iter("testcase"):
                key = (node.get("classname", ""), node.get("name", ""))
                identity = keys.get(key)
                if identity is None:
                    unexpected.append("::".join(key))
                    continue
                if identity in outcomes:
                    duplicates.append(identity)
                outcomes[identity] = (
                    "FAIL" if node.find("failure") is not None or node.find("error") is not None
                    else "SKIP" if node.find("skipped") is not None else "PASS"
                )
        except (ElementTree.ParseError, OSError) as exc:
            errors.append(f"Unreadable JUnit: {type(exc).__name__}")
    states = {identity: outcomes.get(identity, "NOT_RUN") for identity in expected}
    accepted = not (
        pytest_exit
        or errors
        or duplicates
        or unexpected
        or any(v != "PASS" for v in states.values())
    )
    return {
        "expected": len(expected), "executed": sum(v in {"PASS", "FAIL"} for v in states.values()),
        "passed": sum(v == "PASS" for v in states.values()),
        "skipped": sum(v == "SKIP" for v in states.values()),
        "failed": sum(v == "FAIL" for v in states.values()),
        "identities": states, "duplicates": duplicates, "unexpected": unexpected,
        "errors": errors, "pytest_exit": pytest_exit, "accepted": accepted,
    }, accepted


def report(manifest: Path, junit: Path, pytest_exit: int) -> tuple[dict[str, object], bool]:
    return _reconcile(manifest.read_text().splitlines(), junit, pytest_exit)


def related_report(
    manifest: Path, junit: Path, pytest_exit: int, collection_exit: int
) -> tuple[dict[str, object], bool]:
    """Accept every actually collected identity from all four declared modules, or fail."""
    try:
        collected = json.loads(manifest.read_text())
        if not isinstance(collected, dict) or collected.get("schema") != COLLECTION_SCHEMA:
            raise ValueError("Unknown related collection schema")
        modules = collected.get("modules")
        if modules != list(RELATED_MODULES):
            raise ValueError("Related module selection does not match the declared suite")
        expected = collected.get("nodeids")
        if not isinstance(expected, list) or not all(isinstance(n, str) for n in expected):
            raise ValueError("Related nodeids must be a list of strings")
        if {n.split("::", 1)[0] for n in expected} != set(RELATED_MODULES):
            raise ValueError("One or more related modules were absent from collection")
        result, accepted = _reconcile(expected, junit, pytest_exit)
        accepted = accepted and collection_exit == 0
        result.update(collection_exit=collection_exit, accepted=accepted)
        return result, accepted
    except (ValueError, OSError) as exc:
        return {"accepted": False, "pytest_exit": pytest_exit,
                "collection_exit": collection_exit,
                "errors": [f"Invalid related manifest: {exc}"]}, False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--pytest-exit", type=int, required=True)
    parser.add_argument("--related-manifest", type=Path, required=True)
    parser.add_argument("--related-collection-exit", type=int, required=True)
    parser.add_argument("--related-junit", type=Path, required=True)
    parser.add_argument("--related-pytest-exit", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result, accepted = report(args.manifest, args.junit, args.pytest_exit)
    except (OSError, ValueError) as exc:
        result, accepted = {"accepted": False, "errors": [str(exc)]}, False
    related, related_accepted = related_report(
        args.related_manifest, args.related_junit, args.related_pytest_exit,
        args.related_collection_exit,
    )
    result["related_suites"] = related
    result["accepted"] = accepted = accepted and related_accepted
    # Never retain a previous successful report when the current collection is incomplete.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    name: str | None = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=args.output.parent, delete=False) as f:
            name = f.name
            f.write(json.dumps(result, indent=2) + "\n")
        os.replace(name, args.output)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)
    print("F2_EXECUTED_PASS" if accepted else "F2_ACCEPTANCE_INCOMPLETE")
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
