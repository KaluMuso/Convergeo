"""Dependency-free controls; no result here is database acceptance."""
from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import tempfile
import unittest
from collections.abc import Iterator
from io import TextIOBase
from pathlib import Path
from unittest.mock import MagicMock, patch

import run_financial_real_stack as runner

HERE = Path(__file__).resolve().parent


class FinancialOrchestrationControls(unittest.TestCase):
    def test_local_execution_is_rejected_before_tools(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch.object(shutil, "which") as tool:
            with self.assertRaisesRegex(RuntimeError, "disposable GitHub"):
                runner.validate_host()
            tool.assert_not_called()

    def test_other_repository_is_rejected(self) -> None:
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": "other/repo",
                                     "GITHUB_SERVER_URL": "https://github.com",
                                     "RUNNER_TEMP": "/tmp"}, clear=True):
            with self.assertRaises(RuntimeError):
                runner.validate_host()

    def test_expected_collection_passes(self) -> None:
        runner.require_collection(runner.F1_NODES, list(reversed(runner.F1_NODES)), 0)

    def test_missing_extra_duplicate_or_failed_collection_rejected(self) -> None:
        for observed, status in ((runner.F1_NODES[:-1], 0),
                                 (runner.F1_NODES + ["tests/other.py::test_x"], 0),
                                 (runner.F1_NODES + [runner.F1_NODES[0]], 0),
                                 (runner.F1_NODES, 2)):
            with self.subTest(observed=observed, status=status), self.assertRaises(RuntimeError):
                runner.require_collection(runner.F1_NODES, observed, status)

    def test_collection_keeps_parameters(self) -> None:
        raw = "header\ntests/x.py::test_y[value]\n1 test collected\n"
        self.assertEqual(runner.nodes_from_collection(raw), ["tests/x.py::test_y[value]"])

    def test_reviewed_inventories_preserved(self) -> None:
        self.assertEqual(len(runner.F1_NODES), 6)
        self.assertEqual(len(set(runner.F1_NODES)), 6)
        self.assertEqual(len(runner.FORWARD), 11)
        self.assertEqual(len(runner.RELATED), 4)
        self.assertEqual(len((HERE.parents[1] / "docs/ops/lenco/f2-required-nodes.txt")
                             .read_text().splitlines()), 43)

    def test_existing_f1_fixture_is_registered_explicitly(self) -> None:
        import ast
        source = HERE.parents[1] / "services/api/tests/test_f1_payout_real_stack.py"
        tree = ast.parse(source.read_text())
        imports = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
                   and node.module == "tests.rls.conftest"]
        self.assertTrue(any(alias.name == "fixture_ids"
                            for node in imports for alias in node.names))

    def test_related_junit_merge_keeps_four_distinct_modules(self) -> None:
        from xml.etree import ElementTree as ET
        root = ET.Element("testsuites")
        for path in runner.RELATED:
            suite = ET.SubElement(root, "testsuite")
            ET.SubElement(suite, "testcase", classname=path[:-3].replace("/", "."), name="test_x")
        self.assertEqual(len(list(root.iter("testcase"))), 4)
        self.assertEqual(len({n.attrib["classname"] for n in root.iter("testcase")}), 4)


class FinancialRestCleanupControls(unittest.TestCase):
    """Exercise the actual context manager; Docker/HTTP boundaries are doubles."""

    @contextlib.contextmanager
    def owned_rest(self) -> Iterator[tuple[runner.Runner, list[str], MagicMock]]:
        with tempfile.TemporaryDirectory() as tmp:
            instance = object.__new__(runner.Runner)
            instance.raw = Path(tmp) / "raw"
            instance.output = Path(tmp) / "evidence"
            instance.raw.mkdir()
            instance.output.mkdir()
            instance.env = {"LANE_D_JWT_SECRET": "synthetic-cleanup-control-secret"}
            instance.password = "synthetic-cleanup-control-password"
            events: list[str] = []

            def command(name: str, _args: list[str], **_kwargs: object) -> tuple[int, str]:
                events.append(name)
                return 0, "a" * 64 if name.endswith("-rest-start") else ""

            gateway = MagicMock(spec=subprocess.Popen)
            gateway.poll.return_value = None
            gateway.wait.return_value = 0
            opener = MagicMock()
            opener.open.return_value.__enter__.return_value.status = 200
            with (
                patch.object(instance, "bind"),
                patch.object(instance, "bootstrap"),
                patch.object(instance, "command", side_effect=command),
                patch.object(runner, "build_opener", return_value=opener),
                patch.object(subprocess, "Popen", return_value=gateway),
            ):
                yield instance, events, gateway

    def assert_stopped(self, events: list[str]) -> None:
        self.assertEqual(events.count("control-rest-start"), 1)
        self.assertEqual(events.count("control-rest-stop"), 1)
        self.assertEqual(events[-1], "control-rest-stop")

    def test_gateway_launch_failure_stops_owned_postgrest_and_closes_log(self) -> None:
        handles: list[TextIOBase] = []

        def failed_launch(*_args: object, **kwargs: object) -> None:
            handle = kwargs["stdout"]
            self.assertIsInstance(handle, TextIOBase)
            assert isinstance(handle, TextIOBase)
            handles.append(handle)
            raise OSError("synthetic gateway launch failure")

        with self.owned_rest() as (instance, events, _gateway):
            with patch.object(subprocess, "Popen", side_effect=failed_launch):
                with self.assertRaisesRegex(OSError, "synthetic gateway launch failure"):
                    with instance.rest("cart", "ci_critical_cart", "control"):
                        self.fail("gateway launch failed; body must not execute")
            self.assert_stopped(events)
            self.assertEqual(len(handles), 1)
            self.assertTrue(handles[0].closed)

    def test_gateway_log_open_failure_still_stops_owned_postgrest(self) -> None:
        with self.owned_rest() as (instance, events, gateway):
            with patch.object(Path, "open", side_effect=OSError("synthetic log open failure")):
                with self.assertRaisesRegex(OSError, "synthetic log open failure"):
                    with instance.rest("cart", "ci_critical_cart", "control"):
                        self.fail("log opening failed; body must not execute")
            self.assert_stopped(events)
            gateway.terminate.assert_not_called()

    def test_gateway_early_exit_still_stops_owned_postgrest(self) -> None:
        with self.owned_rest() as (instance, events, gateway):
            gateway.poll.return_value = 1
            with self.assertRaisesRegex(RuntimeError, "before readiness"):
                with instance.rest("cart", "ci_critical_cart", "control"):
                    self.fail("unready gateway; body must not execute")
            self.assert_stopped(events)
            self.assertNotIn("control-preflight", events)

    def test_body_exception_propagates_after_cleanup(self) -> None:
        with self.owned_rest() as (instance, events, gateway):
            with self.assertRaisesRegex(RuntimeError, "synthetic test failure"):
                with instance.rest("cart", "ci_critical_cart", "control"):
                    raise RuntimeError("synthetic test failure")
            self.assert_stopped(events)
            gateway.terminate.assert_called_once_with()

    def test_gateway_shutdown_failure_cannot_bypass_container_cleanup(self) -> None:
        for operation in ("terminate", "wait", "kill"):
            with self.subTest(operation=operation), self.owned_rest() as state:
                instance, events, gateway = state
                if operation == "terminate":
                    gateway.terminate.side_effect = OSError("synthetic shutdown failure")
                elif operation == "wait":
                    gateway.wait.side_effect = OSError("synthetic shutdown failure")
                else:
                    gateway.wait.side_effect = subprocess.TimeoutExpired("gateway", 10)
                    gateway.kill.side_effect = OSError("synthetic shutdown failure")
                with self.assertRaisesRegex(OSError, "synthetic shutdown failure"):
                    with instance.rest("cart", "ci_critical_cart", "control"):
                        pass
                self.assert_stopped(events)

    def test_log_retention_failure_cannot_bypass_container_cleanup(self) -> None:
        with self.owned_rest() as (instance, events, _gateway):
            failure = OSError("synthetic retention failure")
            with patch.object(Path, "write_text", side_effect=failure):
                with self.assertRaisesRegex(OSError, "synthetic retention failure"):
                    with instance.rest("cart", "ci_critical_cart", "control"):
                        pass
            self.assert_stopped(events)

    def test_log_close_failure_cannot_bypass_container_cleanup(self) -> None:
        with self.owned_rest() as (instance, events, _gateway):
            path = instance.raw / "control-gateway.log"
            with path.open("w") as handle:
                wrapper = MagicMock(wraps=handle)
                wrapper.close.side_effect = OSError("synthetic close failure")
                with (
                    patch.object(Path, "open", return_value=wrapper),
                    patch.object(instance, "retain_gateway_log") as retention,
                    self.assertRaisesRegex(OSError, "synthetic close failure"),
                ):
                    with instance.rest("cart", "ci_critical_cart", "control"):
                        pass
                retention.assert_called_once_with("control")
                self.assert_stopped(events)

    def test_container_cleanup_failure_is_not_success(self) -> None:
        with self.owned_rest() as (instance, events, _gateway):
            original = instance.command

            def command(
                name: str, args: list[str], *, cwd: Path = runner.ROOT,
                checked: bool = True, timeout: int = 1800,
            ) -> tuple[int, str]:
                if name.endswith("-rest-stop"):
                    events.append(name)
                    raise RuntimeError("synthetic Docker cleanup failure")
                return original(name, args, cwd=cwd, checked=checked, timeout=timeout)

            with patch.object(instance, "command", side_effect=command):
                with self.assertRaisesRegex(RuntimeError, "synthetic Docker cleanup failure"):
                    with instance.rest("cart", "ci_critical_cart", "control"):
                        pass
            self.assert_stopped(events)

    def test_graceful_timeout_kills_only_the_owned_gateway(self) -> None:
        with self.owned_rest() as (instance, events, gateway):
            gateway.wait.side_effect = [subprocess.TimeoutExpired("gateway", 10), 0]
            with instance.rest("cart", "ci_critical_cart", "control"):
                pass
            self.assert_stopped(events)
            gateway.kill.assert_called_once_with()
            self.assertEqual(gateway.wait.call_count, 2)

    def test_success_preserves_redacted_log_and_removes_transient_binding(self) -> None:
        with self.owned_rest() as (instance, events, gateway):
            with instance.rest("cart", "ci_critical_cart", "control"):
                self.assertEqual(instance.env["F2_POSTGREST_CONTAINER"], "a" * 64)
                (instance.raw / "control-gateway.log").write_text(instance.env["LANE_D_JWT_SECRET"])
            self.assert_stopped(events)
            self.assertEqual((instance.output / "control-gateway.log").read_text(), "[REDACTED]")
            self.assertNotIn("F2_POSTGREST_CONTAINER", instance.env)
            gateway.terminate.assert_called_once_with()


class FinancialReporterImportControls(unittest.TestCase):
    def test_reporter_loads_exact_repository_file_without_search_path_injection(self) -> None:
        report = runner.load_reporter()
        report_file = report.__file__
        assert report_file is not None
        self.assertEqual(Path(report_file).resolve(),
                         HERE.parents[1] / "scripts/drills/f2_real_stack_report.py")
        self.assertEqual(list(report.RELATED_MODULES), runner.RELATED)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "required.xml"
            path.write_text('<testsuite><testcase classname="tests.fixture" name="test_one"/>'
                            '</testsuite>')
            result, accepted = report._reconcile(["tests/fixture.py::test_one"], path, 0)
            self.assertTrue(accepted)
            self.assertEqual(result["passed"], 1)
            _result, accepted = report._reconcile(
                ["tests/fixture.py::test_one", "tests/fixture.py::test_two"], path, 0
            )
            self.assertFalse(accepted)


if __name__ == "__main__":
    unittest.main()
