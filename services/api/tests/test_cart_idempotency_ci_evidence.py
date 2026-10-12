from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest
import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[3]
CHECKER = ROOT / "scripts/ci/assert_cart_idempotency_ran.py"
WORKFLOW = ROOT / ".github/workflows/ci.yml"


@pytest.fixture(scope="module")
def checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location("cart_evidence_checker", CHECKER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def report(checker: ModuleType) -> ET.Element:
    root = ET.Element("testsuites")
    suite = ET.SubElement(
        root, "testsuite", name="pytest", tests="14", errors="0", failures="0", skipped="0"
    )
    for name in cast(tuple[str, ...], checker.REQUIRED_TESTS):
        ET.SubElement(suite, "testcase", name=name, classname=checker.MODULE, time="0.01")
    return root


def run_gate(checker: ModuleType, root: ET.Element, tmp_path: Path) -> tuple[int, str]:
    source, output, receipt = (tmp_path / name for name in ("raw.xml", "safe.xml", "gate.json"))
    ET.ElementTree(root).write(source, encoding="utf-8", xml_declaration=True)
    status = cast(int, checker.main([str(CHECKER), str(source), str(output), str(receipt)]))
    result = json.loads(receipt.read_text())
    assert result["qualified"] is (status == 0)
    assert result["original_junit_sha256"]
    return status, output.read_text()


def test_accepts_exact_14_case_report(checker: ModuleType, tmp_path: Path) -> None:
    status, saved = run_gate(checker, report(checker), tmp_path)
    assert status == 0
    assert len(list(ET.fromstring(saved).iter("testcase"))) == 14


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "duplicate",
        "unexpected",
        "wrong_module",
        "skipped",
        "failure",
        "error",
        "bad_counts",
        "session_error",
        "unknown_element",
    ],
)
def test_gate_rejects_incomplete_or_nonpassing_reports(
    checker: ModuleType, tmp_path: Path, mutation: str
) -> None:
    root = report(checker)
    suite = root[0]
    if mutation == "missing":
        suite.remove(suite[0])
    elif mutation == "duplicate":
        suite[1].set("name", suite[0].get("name", ""))
    elif mutation == "unexpected":
        suite[0].set("name", "unexpected_case")
    elif mutation == "wrong_module":
        suite[0].set("classname", "other_module")
    elif mutation in {"skipped", "failure", "error"}:
        ET.SubElement(suite[0], mutation, message="private-fixture-text")
    elif mutation == "bad_counts":
        suite.set("errors", "1")
    elif mutation == "session_error":
        ET.SubElement(suite, "error")
    else:
        ET.SubElement(root, "private-fixture-text").text = "private-fixture-text"
    status, saved = run_gate(checker, root, tmp_path)
    assert status == 1
    assert "private-fixture-text" not in saved


@pytest.mark.parametrize("content", [None, "", "<broken>", "<!DOCTYPE x><testsuites/>"])
def test_missing_or_malformed_report_fails_closed(
    checker: ModuleType, tmp_path: Path, content: str | None
) -> None:
    source, output, receipt = (tmp_path / name for name in ("raw.xml", "safe.xml", "gate.json"))
    if content is not None:
        source.write_text(content)
    assert checker.main([str(CHECKER), str(source), str(output), str(receipt)]) == 1
    assert json.loads(receipt.read_text())["qualified"] is False
    assert not output.exists()  # Never invent a passing JUnit replacement.


def test_sanitization_retains_case_outcomes_and_removes_diagnostics(
    checker: ModuleType, tmp_path: Path
) -> None:
    root = report(checker)
    root[0].set("hostname", "private-fixture-text")
    props = ET.SubElement(root[0], "properties")
    ET.SubElement(props, "property", name="private-fixture-text", value="private-fixture-text")
    ET.SubElement(root[0][0], "system-out").text = "private-fixture-text"
    ET.SubElement(
        root[0][0], "failure", message="private-fixture-text"
    ).text = "private-fixture-text"
    root[0].set("failures", "1")
    status, saved = run_gate(checker, root, tmp_path)
    assert status == 1
    assert "private-fixture-text" not in saved
    case = next(ET.fromstring(saved).iter("testcase"))
    assert case.get("name") == checker.REQUIRED_TESTS[0]
    assert case.get("time") == "0.01"
    assert case.find("failure") is not None


def cart_job() -> dict[str, Any]:
    workflow = yaml.safe_load(WORKFLOW.read_text())
    return cast(dict[str, Any], workflow["jobs"]["money-db-triggers"])


def test_workflow_uses_existing_service_and_private_database() -> None:
    job = cart_job()
    assert job["services"]["postgres"]["image"] == "pgvector/pgvector:pg16"
    assert job["services"]["postgres"]["ports"] == ["54322:5432"]
    assert "permissions" not in job
    steps = job["steps"]
    execution = next(step for step in steps if step["name"].startswith("Cart idempotency DB"))
    proof = next(step for step in steps if step["name"].startswith("Prove every cart"))
    upload = next(step for step in steps if step["name"] == "Upload cart idempotency DB evidence")
    assert execution["timeout-minutes"] == 5
    assert execution["env"]["CART_IDEMPOTENCY_TEST_DATABASE_URL"] == (
        "postgresql://postgres:postgres@127.0.0.1:54322/cart_idem_test"
    )
    assert execution["env"]["PGCONNECT_TIMEOUT"] == "5"
    assert "continue-on-error" not in execution and "if" not in execution
    assert "|| true" not in execution["run"]
    assert (
        "tests/test_cart_add_idempotency_db.py -q --junitxml=cart-idempotency-db.xml"
        in execution["run"]
    )
    assert steps.index(execution) < steps.index(proof) < steps.index(upload)
    assert proof["if"] == upload["if"] == "always()"
    assert "continue-on-error" not in proof
    assert upload["with"]["if-no-files-found"] == "error"
    assert "cart-idempotency-db.xml\n" not in upload["with"]["path"]
    assert "cart-idempotency-db-sanitized.xml" in upload["with"]["path"]
    assert "cart-idempotency-db-validation.json" in upload["with"]["path"]


@pytest.mark.parametrize(
    ("version", "create", "pytest_status", "drop", "psql", "expected", "created", "dropped"),
    [
        ("160012", 0, 0, 0, 0, 0, True, True),
        ("160012", 0, 42, 0, 0, 42, True, True),
        ("160012", 43, 0, 0, 0, 43, True, False),
        ("170001", 0, 0, 0, 0, 1, False, False),
        ("160012", 0, 0, 0, 44, 44, False, False),
        ("160012", 0, 0, 45, 0, 1, True, True),
        ("160012", 0, 42, 45, 0, 42, True, True),
    ],
)
def test_shell_preserves_failures_and_only_cleans_created_private_db(
    tmp_path: Path,
    version: str,
    create: int,
    pytest_status: int,
    drop: int,
    psql: int,
    expected: int,
    created: bool,
    dropped: bool,
) -> None:
    step = next(s for s in cart_job()["steps"] if s["name"].startswith("Cart idempotency DB"))
    operations = tmp_path / "operations.txt"
    for command, status in [
        ("psql", "PSQL"),
        ("createdb", "CREATE"),
        ("uv", "PYTEST"),
        ("dropdb", "DROP"),
    ]:
        executable = tmp_path / command
        executable.write_text(
            f'#!/bin/sh\nprintf "%s %s\\n" "{command}" "$*" >> "$OP_LOG"\n'
            + ('printf "%s\\n" "$TEST_VERSION"\n' if command == "psql" else "")
            + f'exit "${{{status}_STATUS}}"\n'
        )
        executable.chmod(0o755)
    env = {
        "PATH": f"{tmp_path}{os.pathsep}{os.defpath}",
        "OP_LOG": str(operations),
        "TEST_VERSION": version,
        "CREATE_STATUS": str(create),
        "PYTEST_STATUS": str(pytest_status),
        "DROP_STATUS": str(drop),
        "PSQL_STATUS": str(psql),
        **step["env"],
    }
    result = subprocess.run(
        ["/bin/bash", "-c", step["run"]], cwd=tmp_path, env=env, capture_output=True, timeout=5
    )
    assert result.returncode == expected
    calls = operations.read_text().splitlines()
    assert any(line.startswith("createdb ") for line in calls) is created
    assert any(line.startswith("dropdb ") for line in calls) is dropped
    for line in calls:
        if line.startswith(("createdb ", "dropdb ")):
            assert (
                "--host=127.0.0.1 --port=54322 --username=postgres --no-password cart_idem_test"
                in line
            )
