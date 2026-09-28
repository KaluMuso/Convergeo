#!/usr/bin/env python3
"""Check exact collected and executed identities for the disposable CI stack."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from xml.etree import ElementTree


def expected_nodes(path: Path) -> list[str]:
    nodes = path.read_text(encoding="utf-8").splitlines()
    if not nodes or any(not node.startswith("tests/") for node in nodes):
        raise ValueError("critical node manifest is empty or malformed")
    if len(set(nodes)) != len(nodes):
        raise ValueError("critical node manifest has duplicate identities")
    return nodes


def collection(manifest: Path, raw: Path, output: Path) -> int:
    expected = expected_nodes(manifest)
    collected = [
        line for line in raw.read_text(encoding="utf-8").splitlines()
        if line.startswith("tests/") and "::" in line
    ]
    output.write_text("\n".join(collected) + "\n", encoding="utf-8")
    missing, extra = set(expected) - set(collected), set(collected) - set(expected)
    if missing or extra or len(collected) != len(expected):
        print(
            f"collection mismatch: missing={sorted(missing)} extra={sorted(extra)}",
            file=sys.stderr,
        )
        return 1
    print(f"Collected exactly {len(expected)} required identities before execution")
    return 0


def junit_identity(node: ElementTree.Element) -> str:
    classname = node.attrib["classname"]
    name = node.attrib["name"]
    parts = classname.split(".")
    if parts[-1].startswith("Test"):
        module, klass = ".".join(parts[:-1]), parts[-1]
        return f"{module.replace('.', '/')}.py::{klass}::{name}"
    return f"{classname.replace('.', '/')}.py::{name}"


def results(manifest: Path, directory: Path, exits: Path, output: Path) -> int:
    expected = expected_nodes(manifest)
    state: dict[str, str] = {}
    for report in sorted(directory.glob("*.xml")):
        for node in ElementTree.parse(report).iter("testcase"):
            identity = junit_identity(node)
            if identity in state:
                raise ValueError(f"duplicate execution identity: {identity}")
            skipped = node.find("skipped")
            if node.find("failure") is not None or node.find("error") is not None:
                outcome = "FAIL"
            elif skipped is not None:
                outcome = "XFAIL" if skipped.attrib.get("type") == "pytest.xfail" else "SKIP"
            else:
                outcome = "PASS"
            state[identity] = outcome
    extra = sorted(set(state) - set(expected))
    state = {identity: state.get(identity, "NOT_RUN") for identity in expected}
    exits_by_group = {}
    if exits.exists():
        for line in exits.read_text(encoding="utf-8").splitlines():
            group, exit_code = line.split("\t")
            exits_by_group[group] = int(exit_code)
    summary = {
        "identities": state,
        "unexpected": extra,
        "pytest_exits": exits_by_group,
    }
    output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    counts = {
        status: list(state.values()).count(status)
        for status in ("PASS", "FAIL", "SKIP", "XFAIL", "NOT_RUN")
    }
    print(f"Critical identities: {counts}; unexpected={extra}; exits={exits_by_group}")
    return int(
        bool(
            extra
            or any(outcome != "PASS" for outcome in state.values())
            or len(exits_by_group) != 8
            or any(exits_by_group.values())
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("collection", "results"))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--dir", type=Path)
    parser.add_argument("--exits", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "collection":
        if args.input is None:
            parser.error("collection requires --input")
        return collection(args.manifest, args.input, args.output)
    if args.dir is None or args.exits is None:
        parser.error("results requires --dir and --exits")
    return results(args.manifest, args.dir, args.exits, args.output)


if __name__ == "__main__":
    sys.exit(main())
