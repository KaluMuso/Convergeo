from __future__ import annotations

import importlib.util
import xml.etree.ElementTree as ET
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "ci" / "assert_authz_matrix_ran.py"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("assert_authz_matrix_ran", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_report(
    path: Path,
    module: ModuleType,
    *,
    count: int | None = None,
    state: str | None = None,
    classname: str | None = None,
    omit_family: str | None = None,
) -> None:
    required = list(module.REQUIRED_TEST_FAMILIES)
    if omit_family is not None:
        required.remove(omit_family)
    target_count = count if count is not None else module.MINIMUM_CASES
    names = required + [f"filler_{index}" for index in range(target_count - len(required))]
    root = ET.Element("testsuites")
    suite = ET.SubElement(root, "testsuite")
    for index, name in enumerate(names):
        case = ET.SubElement(
            suite,
            "testcase",
            classname=classname or module.EXPECTED_CLASSNAME,
            name=name,
        )
        if index == 0 and state is not None:
            ET.SubElement(case, state)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def test_complete_report_passes(tmp_path: Path) -> None:
    module = load_script()
    report = tmp_path / "authz.xml"
    write_report(report, module)
    assert module.validate_report(report) == []


def test_missing_report_fails_closed(tmp_path: Path) -> None:
    module = load_script()
    problems = module.validate_report(tmp_path / "missing.xml")
    assert any("not written" in problem for problem in problems)


def test_truncated_case_inventory_fails(tmp_path: Path) -> None:
    module = load_script()
    report = tmp_path / "authz.xml"
    write_report(report, module, count=module.MINIMUM_CASES - 1)
    problems = module.validate_report(report)
    assert any("expected at least" in problem for problem in problems)


def test_skipped_failed_and_errored_cases_fail(tmp_path: Path) -> None:
    module = load_script()
    for state in module.NON_PASSING:
        report = tmp_path / f"authz-{state}.xml"
        write_report(report, module, state=state)
        problems = module.validate_report(report)
        assert any(state.upper() in problem for problem in problems)


def test_missing_required_family_fails(tmp_path: Path) -> None:
    module = load_script()
    report = tmp_path / "authz.xml"
    missing = module.REQUIRED_TEST_FAMILIES[-1]
    write_report(report, module, omit_family=missing)
    problems = module.validate_report(report)
    assert f"required test family missing: {missing}" in problems


def test_unexpected_testcase_owner_fails(tmp_path: Path) -> None:
    module = load_script()
    report = tmp_path / "authz.xml"
    write_report(report, module, classname="tests.test_unrelated")
    problems = module.validate_report(report)
    assert any("unexpected testcase owner" in problem for problem in problems)
