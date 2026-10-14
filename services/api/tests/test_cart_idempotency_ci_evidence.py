from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
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
        root, "testsuite", name="pytest", tests="20", errors="0", failures="0", skipped="0"
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


def test_accepts_exact_20_case_report(checker: ModuleType, tmp_path: Path) -> None:
    status, saved = run_gate(checker, report(checker), tmp_path)
    assert status == 0
    assert len(list(ET.fromstring(saved).iter("testcase"))) == 20


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


def test_required_inventory_matches_actual_native_collection(checker: ModuleType) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "--collect-only",
            "-q",
            "tests/test_cart_add_idempotency_db.py",
        ],
        cwd=ROOT / "services/api",
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    prefix = "tests/test_cart_add_idempotency_db.py::"
    actual = [line[len(prefix) :] for line in result.stdout.splitlines() if line.startswith(prefix)]
    assert Counter(actual) == Counter(checker.REQUIRED_TESTS)
    assert len(checker.ORIGINAL_POSTGRESQL_TESTS) == 14
    assert checker.ADDITIONAL_POSTGRESQL_TESTS == (
        "test_stale_location_snapshot_does_not_claim_or_increment",
        "test_canonical_api_body_accepts_uppercase_uuid_rpc_input",
    )
    assert len(checker.URI_GUARD_TESTS) == 4
    assert all(
        name.startswith("test_target_guard_rejects_transport_overrides_before_connect[")
        for name in checker.URI_GUARD_TESTS
    )
    assert len(set(checker.REQUIRED_TESTS)) == 20


@pytest.mark.parametrize("group", ["original_postgresql", "additional_postgresql", "uri_guards"])
@pytest.mark.parametrize("fault", ["missing", "duplicate", "skipped"])
def test_every_case_group_fails_closed(
    checker: ModuleType, tmp_path: Path, group: str, fault: str
) -> None:
    root = report(checker)
    suite = root[0]
    target = next(case for case in suite if case.get("name") == checker.CASE_GROUPS[group][0])
    if fault == "missing":
        suite.remove(target)
    elif fault == "duplicate":
        other = next(case for case in suite if case is not target)
        other.set("name", target.get("name", ""))
    else:
        ET.SubElement(target, "skipped")
    assert run_gate(checker, root, tmp_path)[0] == 1


def test_validation_receipt_distinguishes_postgresql_and_uri_guards(
    checker: ModuleType, tmp_path: Path
) -> None:
    assert run_gate(checker, report(checker), tmp_path)[0] == 0
    d = json.loads((tmp_path / "gate.json").read_text())
    assert d["postgresql_cases"] == 16 and d["uri_guard_cases"] == 4
    assert {name: len(cases) for name, cases in d["required_case_groups"].items()} == {
        "original_postgresql": 14,
        "additional_postgresql": 2,
        "uri_guards": 4,
    }


def execution_step() -> dict[str, Any]:
    return next(s for s in cart_job()["steps"] if s["name"].startswith("Cart idempotency DB"))


def test_workflow_reuses_service_image_in_separate_owned_cluster() -> None:
    job = cart_job()
    assert job["services"]["postgres"]["image"] == "pgvector/pgvector:pg16"
    assert job["services"]["postgres"]["ports"] == ["54322:5432"]
    steps = job["steps"]
    execution = execution_step()
    proof = next(step for step in steps if step["name"].startswith("Prove every cart"))
    upload = next(step for step in steps if step["name"] == "Upload cart idempotency DB evidence")
    assert execution["timeout-minutes"] == 5
    assert execution["env"]["PGCONNECT_TIMEOUT"] == "5"
    assert (
        execution["env"]["PAYMENTS_ENABLED"]
        == execution["env"]["PAYMENTS_ALLOW_PRODUCTION"]
        == "false"
    )
    assert "continue-on-error" not in execution and "if" not in execution
    code = execution["run"]
    assert "--pull=never" in code and "--network none" in code
    assert "--tmpfs /var/lib/postgresql/data:rw" in code
    assert "convergeo.cart-native=$cart_db_nonce" in code
    assert "CART_IDEMPOTENCY_TEST_CLUSTER_NAME" in code
    assert "CART_IDEMPOTENCY_TEST_SOCKET_DIRECTORY" in code
    assert (
        "timeout 120 uv run --frozen --no-sync pytest tests/test_cart_add_idempotency_db.py "
        "-q --junitxml=cart-idempotency-db.xml" in code
    )
    assert "createdb" not in code and "--publish" not in code and "--privileged" not in code
    assert "|| true" not in code
    assert steps.index(execution) < steps.index(proof) < steps.index(upload)
    assert proof["if"] == upload["if"] == "always()"
    assert "owned_container_and_directory_cleanup" in proof["run"]
    assert "continue-on-error" not in proof
    assert upload["with"]["if-no-files-found"] == "error"
    assert "cart-idempotency-db.xml\n" not in upload["with"]["path"]
    assert "cart-idempotency-db-sanitized.xml" in upload["with"]["path"]
    assert "cart-idempotency-db-validation.json" in upload["with"]["path"]
    assert "cart-idempotency-db-lifecycle.json" in upload["with"]["path"]


MOCK_DOCKER = r"""
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
root = Path(os.environ['MOCK_ROOT'])
state_file = root / 'state.json'
s = json.loads(state_file.read_text()) if state_file.exists() else {}
with (root / 'operations.jsonl').open('a') as f:
    f.write(json.dumps(args) + '\n')
fault = os.environ['FAULT']
image = 'sha256:' + '1' * 64
cid = '2' * 64
if args[:2] == ['image', 'inspect']:
    print(image)
elif args[0] == 'run':
    mount = args[args.index('--mount') + 1]
    s = {'created': True,
         'nonce': args[args.index('--label') + 1].split('=', 1)[1],
         'socket': mount.split('src=', 1)[1].split(',dst=', 1)[0]}
    state_file.write_text(json.dumps(s))
    if fault in {'partial_start', 'partial_inspect_failure'}: sys.exit(125)
    print(cid)
elif args[0] == 'inspect':
    if args[-1] == 'existing-job-postgres':
        if fault == 'image_lookup': sys.exit(43)
        print(image)
    elif not s.get('created'):
        sys.exit(1)
    elif '--format' in args:
        if args[2] == '{{.Id}}':
            if fault == 'partial_inspect_failure': sys.exit(124)
            print(cid)
        else: print('wrong-owner' if fault == 'owner' else s['nonce'])
    else:
        print(json.dumps([{'Id': cid, 'Image': image,
            'Config': {'Labels': {'convergeo.cart-native': s['nonce']}},
            'HostConfig': {'NetworkMode': 'bridge' if fault == 'network' else 'none',
                'PortBindings': {}, 'Privileged': False,
                'Tmpfs': {'/var/lib/postgresql/data': 'rw'}},
            'Mounts': [{'Type': 'bind', 'Source': s['socket'],
                'Destination': '/var/run/postgresql'}]}]))
elif args[0] == 'exec':
    if 'pg_isready' in args:
        sys.exit(1 if fault == 'readiness' else 0)
    if 'chmod' in args:
        sys.exit(1 if fault == 'socket_mode' else 0)
    if 'psql' in args:
        cluster = 'cart_idem_test-' + s['nonce']
        version = '170001' if fault == 'version' else '160015'
        database = 'another_db' if fault == 'database' else 'cart_idem_test'
        if fault == 'cluster': cluster = 'cart_idem_test-' + 'f' * 32
        print('|'.join([version, database, cluster]))
elif args[0] == 'rm':
    if fault in {'cleanup', 'pytest_cleanup'}: sys.exit(45)
    if fault != 'cleanup_unconfirmed': s['created'] = False
    state_file.write_text(json.dumps(s))
elif args[:2] == ['container', 'ls']:
    if fault == 'cleanup_inspect_failure': sys.exit(124)
    if s.get('created'): print(cid)
else:
    raise SystemExit('unexpected mocked Docker operation')
"""


@pytest.mark.parametrize(
    ("fault", "expected", "pytest_ran", "cleaned"),
    [
        ("none", 0, True, True),
        ("pytest", 42, True, True),
        ("partial_start", 125, False, True),
        ("partial_inspect_failure", 125, False, False),
        ("image_lookup", 43, False, True),
        ("owner", 1, False, False),
        ("network", 1, False, True),
        ("readiness", 1, False, True),
        ("socket_mode", 1, False, True),
        ("version", 1, False, True),
        ("database", 1, False, True),
        ("cluster", 1, False, True),
        ("cleanup", 1, True, False),
        ("cleanup_unconfirmed", 1, True, False),
        ("cleanup_inspect_failure", 1, True, False),
        ("pytest_cleanup", 42, True, False),
    ],
)
def test_shell_preserves_failures_and_cleans_only_owned_resources(
    tmp_path: Path, fault: str, expected: int, pytest_ran: bool, cleaned: bool
) -> None:
    # Every resource command is an owned fake executable; no Docker/server/DB runs.
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "docker").write_text(f"#!{sys.executable}\n" + MOCK_DOCKER)
    (tools / "git").write_text(
        "#!/bin/sh\nprintf '%s\n' aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
    )
    (tools / "sleep").write_text("#!/bin/sh\nexit 0\n")
    (tools / "uv").write_text(
        f"#!{sys.executable}\n"
        + "import json, os\nfrom pathlib import Path\n"
        + "names = {k:v for k,v in os.environ.items() "
        "if k.startswith('CART_IDEMPOTENCY_TEST_')}\n"
        "names['routing_overrides_present'] = any(os.environ.get(k) "
        "for k in ['PGHOSTADDR','PGSERVICE','PGSERVICEFILE','PGOPTIONS'])\n"
        "Path(os.environ['MOCK_ROOT'], 'pytest-env.json').write_text(json.dumps(names))\n"
        + "raise SystemExit(42 if os.environ['FAULT'] in {'pytest','pytest_cleanup'} else 0)\n"
    )
    for tool in tools.iterdir():
        tool.chmod(0o755)
    runner = tmp_path / "runner"
    runner.mkdir()
    env = {
        "PATH": str(tools) + os.pathsep + os.defpath,
        "RUNNER_TEMP": str(runner),
        "GITHUB_SHA": "a" * 40,
        "MOCK_ROOT": str(tmp_path),
        "FAULT": fault,
        "PGHOSTADDR": "private-unused-routing",
        **execution_step()["env"],
    }
    code = execution_step()["run"].replace(
        "${{ job.services.postgres.id }}", "existing-job-postgres"
    )
    result = subprocess.run(
        ["/bin/bash", "-c", code], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=15
    )
    assert result.returncode == expected, result.stderr
    lifecycle = json.loads((tmp_path / "cart-idempotency-db-lifecycle.json").read_text())
    assert lifecycle["owned_container_and_directory_cleanup"] is cleaned
    assert (tmp_path / "pytest-env.json").exists() is pytest_ran
    operations = [
        json.loads(line) for line in (tmp_path / "operations.jsonl").read_text().splitlines()
    ]
    assert any(args[0] == "rm" for args in operations) is (
        fault not in {"owner", "partial_inspect_failure", "image_lookup"}
    )
    if pytest_ran:
        observed = json.loads((tmp_path / "pytest-env.json").read_text())
        assert observed["routing_overrides_present"] is False
        assert observed["CART_IDEMPOTENCY_TEST_CLUSTER_NAME"].startswith("cart_idem_test-")
        assert observed["CART_IDEMPOTENCY_TEST_SOCKET_DIRECTORY"].startswith(str(runner))
        assert observed["CART_IDEMPOTENCY_TEST_DATABASE_URL"].startswith(
            "postgresql://postgres@%2F"
        )
    if cleaned:
        assert list(runner.iterdir()) == []
    elif fault in {"partial_inspect_failure", "cleanup_unconfirmed", "cleanup_inspect_failure"}:
        assert len(list(runner.iterdir())) == 1  # Do not remove a potentially live bind mount.
