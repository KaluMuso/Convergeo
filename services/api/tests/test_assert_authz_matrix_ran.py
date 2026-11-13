from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "ci" / "assert_authz_matrix_ran.py"
CHECKOUT_SHA = "a" * 40
NODEIDS = (
    "tests/test_authz_matrix.py::test_every_route_is_classified",
    "tests/test_authz_matrix.py::test_anonymous_denied_on_protected_routes[GET /orders]",
    "tests/test_authz_matrix.py::test_wrong_role_denied[POST /orders-vendor]",
)


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("assert_authz_matrix_ran", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_inventory(
    path: Path,
    module: ModuleType,
    *,
    nodeids: tuple[str, ...] = NODEIDS,
    checkout_sha: str = CHECKOUT_SHA,
    mutate: dict[str, object] | None = None,
) -> None:
    inventory = module.build_inventory(
        repo_root=REPO_ROOT,
        checkout_sha=checkout_sha,
        nodeids=nodeids,
    )
    if mutate:
        inventory.update(mutate)
    path.write_text(json.dumps(inventory), encoding="utf-8")


def write_report(
    path: Path,
    module: ModuleType,
    *,
    nodeids: tuple[str, ...] = NODEIDS,
    state: str | None = None,
    classname: str | None = None,
    declared: dict[str, str] | None = None,
    double_state: bool = False,
) -> None:
    root = ET.Element("testsuites")
    suite = ET.SubElement(root, "testsuite")
    for index, nodeid in enumerate(nodeids):
        case = ET.SubElement(
            suite,
            "testcase",
            classname=classname or module.EXPECTED_CLASSNAME,
            name=nodeid.split("::", maxsplit=1)[1],
        )
        if index == 0 and state is not None:
            ET.SubElement(case, state)
            if double_state:
                ET.SubElement(case, "error" if state != "error" else "failure")
    counts = {
        "tests": str(len(nodeids)),
        "failures": "1" if state == "failure" or double_state else "0",
        "errors": "1" if state == "error" or double_state else "0",
        "skipped": "1" if state == "skipped" else "0",
    }
    if declared:
        counts.update(declared)
    suite.attrib.update(counts)
    root.attrib.update(counts)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def problems_for(
    tmp_path: Path,
    *,
    report_nodeids: tuple[str, ...] = NODEIDS,
    inventory_nodeids: tuple[str, ...] = NODEIDS,
    state: str | None = None,
    classname: str | None = None,
    declared: dict[str, str] | None = None,
    double_state: bool = False,
    inventory_checkout: str = CHECKOUT_SHA,
    inventory_mutation: dict[str, object] | None = None,
) -> list[str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    module = load_script()
    module.verify_checkout = (  # type: ignore[attr-defined]
        lambda _repo_root, expected_sha: expected_sha
    )
    report = tmp_path / "authz.xml"
    inventory = tmp_path / "authz-inventory.json"
    write_inventory(
        inventory,
        module,
        nodeids=inventory_nodeids,
        checkout_sha=inventory_checkout,
        mutate=inventory_mutation,
    )
    write_report(
        report,
        module,
        nodeids=report_nodeids,
        state=state,
        classname=classname,
        declared=declared,
        double_state=double_state,
    )
    return cast(
        list[str],
        module.validate_report(
            report,
            inventory,
            checkout_sha=CHECKOUT_SHA,
            repo_root=REPO_ROOT,
        ),
    )


def test_complete_exact_report_passes(tmp_path: Path) -> None:
    assert problems_for(tmp_path) == []


def test_collection_uses_exact_file_and_retains_parameter_identities(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_script()
    test_file = tmp_path / "services" / "api" / module.TEST_FILE
    test_file.parent.mkdir(parents=True)
    test_file.write_text("", encoding="utf-8")
    stdout = "\n".join((*NODEIDS, f"{len(NODEIDS)} tests collected in 0.01s"))

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert command == [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            module.TEST_FILE,
        ]
        assert kwargs["cwd"] == tmp_path / "services" / "api"
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    assert module.collect_nodeids(tmp_path) == NODEIDS


@pytest.mark.parametrize(
    "stdout, message",
    (
        (
            "\n".join((NODEIDS[0], NODEIDS[0], "2 tests collected in 0.01s")),
            "duplicates",
        ),
        (
            "tests/test_other.py::test_other\n1 test collected in 0.01s",
            "out-of-scope",
        ),
        (
            f"{NODEIDS[0]}\n2 tests collected in 0.01s",
            "summary",
        ),
    ),
)
def test_collection_rejects_malformed_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stdout: str,
    message: str,
) -> None:
    module = load_script()
    test_file = tmp_path / "services" / "api" / module.TEST_FILE
    test_file.parent.mkdir(parents=True)
    test_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout=stdout, stderr=""),
    )
    with pytest.raises(ValueError, match=message):
        module.collect_nodeids(tmp_path)


def test_checkout_identity_is_read_from_git_and_must_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_script()
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout=f"{'b' * 40}\n", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    with pytest.raises(ValueError, match="does not match repository HEAD"):
        module.verify_checkout(tmp_path, CHECKOUT_SHA)
    assert calls[0][0] == ["git", "rev-parse", "--verify", "HEAD^{commit}"]
    assert calls[0][1]["cwd"] == tmp_path


def test_checkout_with_tracked_changes_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_script()
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        stdout = f"{CHECKOUT_SHA}\n" if command[1] == "rev-parse" else " M app/main.py\n"
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    with pytest.raises(ValueError, match="tracked changes"):
        module.verify_checkout(tmp_path, CHECKOUT_SHA)
    assert calls == [
        ["git", "rev-parse", "--verify", "HEAD^{commit}"],
        ["git", "status", "--porcelain=v1", "--untracked-files=no"],
    ]


def test_missing_or_unreadable_inputs_fail_closed(tmp_path: Path) -> None:
    module = load_script()
    module.verify_checkout = (  # type: ignore[attr-defined]
        lambda _repo_root, expected_sha: expected_sha
    )
    missing = module.validate_report(
        tmp_path / "missing.xml",
        tmp_path / "missing.json",
        checkout_sha=CHECKOUT_SHA,
        repo_root=REPO_ROOT,
    )
    assert any("inventory not written" in problem for problem in missing)

    inventory = tmp_path / "bad.json"
    inventory.write_text("{", encoding="utf-8")
    unreadable = module.validate_report(
        tmp_path / "missing.xml",
        inventory,
        checkout_sha=CHECKOUT_SHA,
        repo_root=REPO_ROOT,
    )
    assert any("inventory is unreadable" in problem for problem in unreadable)


def test_unreadable_junit_fails_closed(tmp_path: Path) -> None:
    module = load_script()
    module.verify_checkout = (  # type: ignore[attr-defined]
        lambda _repo_root, expected_sha: expected_sha
    )
    inventory = tmp_path / "expected.json"
    write_inventory(inventory, module)
    report = tmp_path / "bad.xml"
    report.write_text("<testsuite>", encoding="utf-8")
    problems = module.validate_report(
        report,
        inventory,
        checkout_sha=CHECKOUT_SHA,
        repo_root=REPO_ROOT,
    )
    assert any("JUnit report is unreadable" in problem for problem in problems)


def test_missing_and_unexpected_parameterized_identities_fail(tmp_path: Path) -> None:
    replacement = NODEIDS[:-1] + (
        "tests/test_authz_matrix.py::test_wrong_role_denied[POST /orders-customer]",
    )
    problems = problems_for(tmp_path, report_nodeids=replacement)
    assert any("identities missing" in problem and NODEIDS[-1] in problem for problem in problems)
    assert any("unexpected testcase identities" in problem for problem in problems)


def test_duplicate_report_identity_fails(tmp_path: Path) -> None:
    problems = problems_for(tmp_path, report_nodeids=NODEIDS + (NODEIDS[-1],))
    assert any("duplicate testcase identities" in problem for problem in problems)


def test_duplicate_or_internally_inconsistent_inventory_fails(tmp_path: Path) -> None:
    module = load_script()
    duplicate = NODEIDS + (NODEIDS[-1],)
    with pytest.raises(ValueError, match="duplicates"):
        module.build_inventory(
            repo_root=REPO_ROOT,
            checkout_sha=CHECKOUT_SHA,
            nodeids=duplicate,
        )

    duplicate_problems = problems_for(
        tmp_path / "duplicate",
        inventory_mutation={
            "nodeids": list(duplicate),
            "case_count": len(duplicate),
            "nodeids_sha256": module._nodeids_sha256(duplicate),
        },
    )
    assert any("duplicate node IDs" in problem for problem in duplicate_problems)

    problems = problems_for(
        tmp_path / "counts",
        inventory_mutation={"case_count": 99, "nodeids_sha256": "0" * 64},
    )
    assert any("case count is inconsistent" in problem for problem in problems)
    assert any("digest is inconsistent" in problem for problem in problems)


@pytest.mark.parametrize(
    "nodeids",
    (
        [],
        [42],
        ["tests/test_other.py::test_other"],
    ),
)
def test_invalid_inventory_identity_shapes_fail(tmp_path: Path, nodeids: list[object]) -> None:
    problems = problems_for(tmp_path, inventory_mutation={"nodeids": nodeids})
    assert problems
    assert any("inventory" in problem for problem in problems)


def test_stale_checkout_and_source_inventory_fail(tmp_path: Path) -> None:
    stale = problems_for(tmp_path, inventory_checkout="b" * 40)
    assert any("stale checkout" in problem for problem in stale)

    source = problems_for(
        tmp_path,
        inventory_mutation={"test_file_sha256": "0" * 64},
    )
    assert any("test source does not match" in problem for problem in source)


def test_tampered_inventory_provenance_fails(tmp_path: Path) -> None:
    mutations: tuple[dict[str, object], ...] = (
        {"schema_version": 2},
        {"kind": "other"},
        {"working_directory": "."},
        {"collection_command": ["pytest", "-q"]},
        {"test_file": "tests/test_other.py"},
        {"extra": True},
    )
    for index, mutation in enumerate(mutations):
        case_dir = tmp_path / str(index)
        case_dir.mkdir()
        problems = problems_for(case_dir, inventory_mutation=mutation)
        assert problems, mutation
        assert any("inventory" in problem for problem in problems), (mutation, problems)


@pytest.mark.parametrize("state", ("skipped", "failure", "error"))
def test_non_passing_outcomes_fail(tmp_path: Path, state: str) -> None:
    problems = problems_for(tmp_path, state=state)
    assert any(f": {state.upper()}" in problem for problem in problems)


def test_inconsistent_outcomes_and_declared_counts_fail(tmp_path: Path) -> None:
    outcomes = problems_for(tmp_path, state="failure", double_state=True)
    assert any("inconsistent outcomes" in problem for problem in outcomes)

    counters = problems_for(tmp_path, declared={"tests": "99", "failures": "1"})
    assert any("tests counter is inconsistent" in problem for problem in counters)
    assert any("failures counter is inconsistent" in problem for problem in counters)

    invalid = problems_for(tmp_path / "invalid", declared={"tests": "NaN"})
    assert any("tests counter is invalid" in problem for problem in invalid)


def test_unexpected_testcase_owner_fails(tmp_path: Path) -> None:
    problems = problems_for(tmp_path, classname="tests.test_unrelated")
    assert any("unexpected testcase owner" in problem for problem in problems)


def test_write_inventory_refuses_stale_output(tmp_path: Path) -> None:
    module = load_script()
    inventory = module.build_inventory(
        repo_root=REPO_ROOT,
        checkout_sha=CHECKOUT_SHA,
        nodeids=NODEIDS,
    )
    output = tmp_path / "expected.json"
    module.write_inventory(output, inventory)
    original = copy.deepcopy(inventory)
    with pytest.raises(ValueError, match="refusing to overwrite"):
        module.write_inventory(output, inventory)
    assert json.loads(output.read_text(encoding="utf-8")) == original
