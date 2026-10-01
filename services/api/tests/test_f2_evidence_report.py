"""Executable subprocess controls for exact related-suite evidence; not SQL evidence."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPORTER = Path(__file__).resolve().parents[3] / "scripts/drills/f2_real_stack_report.py"
_spec = importlib.util.spec_from_file_location("f2_report_test_target", _REPORTER)
assert _spec and _spec.loader
_report = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_report)
MODULES = list(_report.RELATED_MODULES)


def _xml(nodeids: list[str], child: str = "") -> str:
    return "<testsuite>" + "".join(
        '<testcase classname="{}" name="{}">{}</testcase>'.format(*_report._junit_key(n), child)
        for n in nodeids
    ) + "</testsuite>"


@pytest.mark.parametrize("kind", [
    "pass", "skip", "failure", "error", "empty", "missing", "duplicate", "process_error",
    "single_passing_test_only", "one_module_absent", "manifest_module_missing",
    "manifest_missing", "manifest_duplicate", "unexpected_test", "bad_xml",
    "collection_error", "partial_collection_modules", "malformed_manifest", "suite_error",
])
def test_related_evidence_requires_every_collected_identity(tmp_path: Path, kind: str) -> None:
    expected = [f"{module}::TestCase::test_item[a::b]" for module in MODULES]
    manifest = tmp_path / "related-collected.json"
    payload = {"schema": _report.COLLECTION_SCHEMA, "modules": MODULES, "nodeids": expected}
    if kind == "manifest_module_missing":
        payload["nodeids"] = expected[:-1]
    elif kind == "manifest_duplicate":
        payload["nodeids"] = expected + [expected[0]]
    elif kind == "partial_collection_modules":
        payload["modules"] = MODULES[:1]
    if kind != "manifest_missing":
        manifest.write_text("{" if kind == "malformed_manifest" else json.dumps(payload))
    emitted = list(expected)
    if kind == "single_passing_test_only":
        emitted = expected[:1]
    elif kind == "one_module_absent":
        emitted = expected[:-1]
    elif kind == "duplicate":
        emitted.append(expected[0])
    elif kind == "empty":
        emitted = []
    elif kind == "unexpected_test":
        emitted.append("tests/extra.py::test_unrequested")
    junit = tmp_path / "related.xml"
    child = {"skip": "<skipped/>", "failure": "<failure/>", "error": "<error/>"}.get(kind, "")
    if kind != "missing":
        junit.write_text("{" if kind == "bad_xml" else _xml(emitted, child))
    if kind == "suite_error":
        junit.write_text(_xml(emitted).replace("<testsuite>", "<testsuite><error/>"))
    required = tmp_path / "required.txt"
    required.write_text("tests/f2_fixture.py::test_required\n")
    required_xml = tmp_path / "required.xml"
    required_xml.write_text(_xml(["tests/f2_fixture.py::test_required"]))
    output = tmp_path / "results.json"
    output.write_text('{"accepted":true}')  # Previous success must not survive rejection.
    p = subprocess.run([
        sys.executable, str(_REPORTER), "--manifest", str(required), "--junit", str(required_xml),
        "--pytest-exit", "0", "--related-manifest", str(manifest),
        "--related-collection-exit", "2" if kind == "collection_error" else "0",
        "--related-junit", str(junit), "--related-pytest-exit",
        "1" if kind == "process_error" else "0", "--output", str(output),
    ], capture_output=True, text=True, timeout=15, check=False)
    accepted = kind == "pass"
    assert p.returncode == (0 if accepted else 1), p.stderr
    result = json.loads(output.read_text())
    assert result["accepted"] is accepted
    assert result["related_suites"]["accepted"] is accepted
    assert result["identities"] == {"tests/f2_fixture.py::test_required": "PASS"}


@pytest.mark.parametrize("drop_result", [False, True])
def test_real_pytest_collection_plugin_and_junit_pairing(tmp_path: Path, drop_result: bool) -> None:
    """Use real pytest processes on synthetic modules; no database claim is made."""
    for module in MODULES:
        f = tmp_path / module
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(
            "class TestRelated:\n"
            "    def test_first(self): pass\n"
            "    def test_second(self): pass\n"
        )
    output = tmp_path / "collected.json"
    env = {**os.environ, "F2_COLLECTION_OUTPUT": str(output),
           "PYTHONPATH": str(_REPORTER.parent), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    p = subprocess.run([sys.executable, "-m", "pytest", "-p", "f2_collection_manifest",
                        "--collect-only", "-q", *MODULES], cwd=tmp_path, env=env,
                       capture_output=True, text=True, timeout=20, check=False)
    assert p.returncode == 0, p.stdout + p.stderr
    collected = json.loads(output.read_text())
    assert len(collected["nodeids"]) == 8
    junit = tmp_path / "actual.xml"
    args = [sys.executable, "-m", "pytest", "-q", f"--junitxml={junit}", *MODULES]
    if drop_result:
        args += ["-k", "first"]
    p = subprocess.run(args, cwd=tmp_path, env=env, capture_output=True, text=True,
                       timeout=20, check=False)
    assert p.returncode == 0, p.stdout + p.stderr
    result, accepted = _report.related_report(output, junit, p.returncode, 0)
    assert accepted is (not drop_result), result


@pytest.mark.parametrize(("kind", "pytest_exit", "accepted"), [
    ("pass", 0, True), ("skip", 0, False), ("failure", 1, False),
    ("error", 1, False), ("empty", 0, False), ("missing", 0, False),
    ("duplicate", 0, False), ("pass", 1, False),
])
def test_related_evidence_must_execute_without_skips(
    tmp_path: Path, kind: str, pytest_exit: int, accepted: bool
) -> None:
    """Retain the original eight controls, now with the required collected manifest."""
    expected = [f"{module}::test_related" for module in MODULES]
    manifest = tmp_path / "related-collected.json"
    manifest.write_text(json.dumps({"schema": _report.COLLECTION_SCHEMA,
                                    "modules": MODULES, "nodeids": expected}))
    cases = [] if kind == "empty" else expected + ([expected[0]] if kind == "duplicate" else [])
    child = {"skip": "<skipped/>", "failure": "<failure/>", "error": "<error/>"}.get(kind, "")
    junit = tmp_path / "related.xml"
    if kind != "missing":
        junit.write_text(_xml(cases, child))
    result, actual = _report.related_report(manifest, junit, pytest_exit, 0)
    assert actual is accepted and result["accepted"] is accepted
