"""Process/identity controls for the NEW proposal; these are not SQL acceptance."""
from __future__ import annotations

import http.client
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import run_coordinator_gates as gates
import run_financial_real_stack as financial


class CoordinatorControls(unittest.TestCase):
    def test_db_only_modules_retain_blocking_owners(self) -> None:
        workflow = (gates.ROOT / ".github/workflows/ci.yml").read_text()
        broad = re.search(r"(?ms)^  python:\n.*?(?=^  [a-z0-9-]+:)", workflow)
        assert broad is not None
        self.assertEqual(re.findall(r"--ignore=([^\s]+)", broad.group()), [
            "tests/test_authz_matrix.py", "tests/test_f1_payout_real_stack.py",
            "tests/test_vendor_stock_adjustment_db.py"])
        self.assertIn("run: python scripts/ci/run_financial_real_stack.py", workflow)
        self.assertIn("gate: [f3, merchant, curated]", workflow)
        self.assertIsNone(re.search(r"(?m)^\s+continue-on-error:", workflow))

    def test_retained_inventories_and_published_source_contract(self) -> None:
        contract = gates.inputs()
        self.assertEqual(len(contract["f3"]), 7)
        self.assertEqual(len(contract["db"]), 26)
        self.assertEqual(len(contract["ui"]), 6)
        self.assertEqual(len(contract["normal"]), 258)
        self.assertEqual(len(contract["migrations"]), 135)
        self.assertEqual(sum(map(len, financial.financial_identities().values())), 804)

    def test_local_host_rejected_before_resource_allocation(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch.object(gates, "Runner") as factory:
            with patch("sys.argv", ["run_coordinator_gates.py", "f3"]):
                with self.assertRaisesRegex(RuntimeError, "disposable GitHub"):
                    gates.main()
            factory.assert_not_called()

    def test_unknown_namespace_cannot_create_or_drop_other_database(self) -> None:
        runner = object.__new__(gates.Runner)
        runner.dbs = []
        with patch.object(runner, "sql") as sql:
            for database in ("postgres", "production", "f3_report_other", "ci_critical_cart"):
                with self.assertRaises(RuntimeError):
                    runner.create(database)
                with self.assertRaises(RuntimeError):
                    runner.drop(database)
            sql.assert_not_called()

    def test_exact_source_mismatch_fails_before_docker(self) -> None:
        runner = object.__new__(gates.Runner)
        runner.env = {"QUALIFICATION_SHA": "b" * 40}
        with patch.object(runner, "command", return_value=(0, "a" * 40 + "\n" + "c" * 40)):
            with self.assertRaisesRegex(RuntimeError, "explicit review SHA"):
                runner.qualify()

    def test_f3_upgrade_input_prefix_excludes_version_migration_and_later_suffix(self) -> None:
        contract = gates.inputs()
        prefix = [n for n in contract["migrations"] if n < gates.F3_MIGRATION]
        self.assertEqual(len(prefix), 131)
        self.assertIn("20260929120003_adopt_existing_service_obligations.sql", prefix)
        self.assertNotIn(gates.F3_MIGRATION, prefix)
        self.assertEqual(len([n for n in contract["migrations"] if n > gates.F3_MIGRATION]), 3)

    def test_mounted_false_success_partial_skip_duplicate_and_exit_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            for names, statuses, success, status in (
                (["test"], ["passed"], True, 0),
                ([], [], True, 0),
                (["test"], ["pending"], True, 0),
                (["test", "test"], ["passed", "passed"], True, 0),
                (["test"], ["passed"], False, 0),
                (["test"], ["passed"], True, 1),
            ):
                path.write_text(json.dumps({"success": success, "testResults": [{
                    "assertionResults": [{"fullName": n, "status": s}
                                          for n, s in zip(names, statuses, strict=True)]}]}))
                result = gates.ui_report(["test"], path, status)
                self.assertEqual(result["accepted"], names == ["test"]
                                 and statuses == ["passed"] and success and status == 0)
            self.assertFalse(gates.ui_report(["test"], Path(tmp) / "missing", 0)["accepted"])

    def test_junit_rejects_skips_duplicates_missing_and_nonzero_exit(self) -> None:
        reporter = financial.load_reporter()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "junit.xml"
            case = '<testcase classname="tests.example" name="test_case"{}/>'
            for content, status, accepted in (
                (case.format(""), 0, True),
                (case.format(""), 1, False),
                ('<testcase classname="tests.example" name="test_case"><skipped/></testcase>',
                 0, False),
                (case.format("") * 2, 0, False),
                ("", 0, False),
            ):
                path.write_text("<testsuite>" + content + "</testsuite>")
                self.assertEqual(reporter._reconcile(["tests/example.py::test_case"],
                                                     path, status)[1], accepted)

    def test_redirect_and_wrong_database_cannot_satisfy_probe(self) -> None:
        runner = object.__new__(gates.Runner)
        runner.env = {"LANE_D_JWT_SECRET": "synthetic-probe-secret"}
        for status, body in ((302, b"redirect"), (200, b"[]"),
                             (200, b'[{"group_name":"other","database_name":"other"}]')):
            factory = MagicMock()
            response = factory.return_value.getresponse.return_value
            response.status = status
            response.read.return_value = body
            with patch.object(http.client, "HTTPConnection", factory):
                with self.assertRaises(RuntimeError):
                    runner.probe(3006, "f3_report_fresh_ci")
                factory.return_value.close.assert_called_once()

    def test_rest_body_and_log_failure_still_remove_owned_container(self) -> None:
        runner = object.__new__(gates.Runner)
        runner.dbs = ["f3_report_fresh_ci"]
        runner.password = "synthetic-password"
        runner.env = {"LANE_D_JWT_SECRET": "synthetic-rest-secret"}
        events: list[str] = []

        def command(name: str, _args: list[str]) -> tuple[int, str]:
            events.append(name)
            if name.endswith("-rest-logs"):
                raise RuntimeError("synthetic log failure")
            return 0, "a" * 64

        with patch.object(runner, "bootstrap"), patch.object(runner, "probe"), \
                patch.object(runner, "command", side_effect=command):
            with self.assertRaises(RuntimeError):
                with runner.direct_rest("f3_report_fresh_ci", 3006):
                    raise RuntimeError("synthetic body failure")
        self.assertEqual(events[-1], "f3_report_fresh_ci-rest-stop")
        self.assertEqual(len(events), 3)

    def test_curated_failure_does_not_suppress_rls_execution(self) -> None:
        runner = object.__new__(gates.Runner)
        runner.env = {}
        runner.contract = {"curated": ["tests/curated.py"]}
        with patch.object(runner, "create"), patch.object(runner, "replay"), \
                patch.object(runner, "roles"), patch.object(runner, "bind"), \
                patch.object(runner, "direct_rest"), \
                patch.object(runner, "sql") as sql, \
                patch.object(runner, "test_gate", side_effect=[False, True]) as test:
            with self.assertRaisesRegex(RuntimeError, "zero skips"):
                runner.curated()
            self.assertEqual(test.call_count, 2)
            self.assertEqual(test.call_args.args, ("rls", ["tests/rls"]))
            sql.assert_called_once_with("remove-owned-probe-before-rls",
                "ci_coordinator_curated", "DROP TABLE public.ci_critical_binding_probe")


if __name__ == "__main__":
    unittest.main()
