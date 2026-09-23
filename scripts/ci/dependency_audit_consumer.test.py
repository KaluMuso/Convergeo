"""Executable process-boundary controls for the dependency audit consumer."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONSUMER = ROOT / "scripts/ci/dependency_audit_consumer.py"
RAW_STATUS = {"exitCode": 0, "signal": None, "spawnError": None}


def fake(kind, args):
    scenario = os.environ["AUDIT_TEST_SCENARIO"]
    with open(os.environ["AUDIT_TEST_EVENTS"], "a") as events:
        events.write(f"{kind} {' '.join(args)}\n")
    if kind == "node":
        if args == ["--version"]:
            print("v22.23.2")
            return 0
        paths = {arg: Path(args[args.index(arg) + 1]) for arg in
                 ("--output", "--stderr-output", "--status-output")}
        if scenario != "missing":
            severity = "moderate" if scenario == "moderate" else "high"
            finding = {"version": "2.0.1", "paths": ["root>extract-zip"]}
            counts = {s: 0 for s in ("info", "low", "moderate", "high", "critical")}
            if scenario in ("high", "moderate", "node_fail"):
                counts[severity] = 1
            report = {"advisories": {}, "metadata": {"vulnerabilities": counts}}
            if counts[severity]:
                report["advisories"]["one"] = {"severity": severity,
                    "module_name": "extract-zip", "findings": [finding]}
            if scenario == "error":
                report["error"] = "registry failed"
            paths["--output"].write_text("{" if scenario == "malformed" else json.dumps(report))
            paths["--stderr-output"].write_text("raw stderr\n")
            raw = dict(RAW_STATUS)
            raw["exitCode"] = 1 if counts[severity] else 0
            paths["--status-output"].write_text(json.dumps(raw))
        print("gate log")
        return 2 if scenario in ("malformed", "missing", "error", "node_fail") else (
            1 if scenario == "high" else 0)
    if kind == "pnpm":
        if args == ["--version"]:
            print("9.15.4")
            return 0
        return 1 if scenario == "setup_fail" else 0
    if kind == "uv":
        if args == ["--version"]:
            print("uv 0.9.30")
            return 0
        if args[0] == "export":
            requirements = "\n".join(f"{name}==1.0.0" for name in
                ("fastapi", "httpx", "psycopg", "pydantic-settings", "sentry-sdk",
                 "slowapi", "supabase", "uvicorn"))
            if scenario != "api_missing":
                requirements += "\ncryptography==50.0.0"
            Path(args[args.index("--output-file") + 1]).write_text(requirements + "\n")
        if args[0] == "tool":
            deps = [{"name": name, "version": "50.0.0" if name == "cryptography" else "1.0.0",
                     "vulns": []} for name in
                    ("fastapi", "httpx", "psycopg", "pydantic-settings", "sentry-sdk",
                     "slowapi", "supabase", "uvicorn", "cryptography")]
            if scenario == "api_audit_missing":
                deps.pop()
            if scenario == "api_tool_failure":
                return 2
            if scenario == "api_high":
                deps[0]["vulns"] = [{"id": "PYSEC-TEST"}]
            Path(args[args.index("--output") + 1]).write_text(json.dumps({"dependencies": deps}))
            return 1 if scenario == "api_high" else 0
        return 0
    if kind == "npm":
        if args[0] == "audit":
            if scenario == "e2e_malformed":
                print("{}")
                return 0
            high = 1 if scenario == "e2e_high" else 0
            print(json.dumps({"auditReportVersion": 2, "vulnerabilities": {},
                              "metadata": {"vulnerabilities": {"info": 0, "low": 0,
                                  "moderate": 0, "high": high, "critical": 0,
                                  "total": high}}}))
            return 1 if scenario == "e2e_high" else 0
        return 0
    raise AssertionError(kind)


class ConsumerBoundaryTests(unittest.TestCase):
    def run_case(self, scenario):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            env = dict(os.environ, AUDIT_TEST_SCENARIO=scenario,
                       AUDIT_TEST_EVENTS=str(directory / "events.txt"))
            for kind in ("node", "pnpm", "uv", "npm"):
                env[f"AUDIT_{kind.upper()}_CMD"] = (
                    f"{sys.executable.replace(chr(92), '/')} "
                    f"{str(Path(__file__).resolve()).replace(chr(92), '/')} fake {kind}")
            result = subprocess.run([sys.executable, str(CONSUMER), "--evidence-dir",
                                     str(directory / "evidence")], cwd=ROOT,
                                    env=env, capture_output=True, text=True)
            manifest = json.loads((directory / "evidence/manifest.json").read_text())
            manifest["testRawNodeStatus"] = (json.loads((directory / "evidence/pnpm-audit.status.json").read_text())
                                             if (directory / "evidence/pnpm-audit.status.json").exists() else None)
            events = (directory / "events.txt").read_text()
            self.assertIn("uv tool run --from pip-audit==2.10.1 pip-audit -r", events)
            self.assertIn("npm audit --json", events)
            self.assertIn("--frozen --all-groups --no-hashes --no-emit-project", events)
            self.assertIn("node scripts/ci/pnpm-audit-gate.mjs --output", events)
            return result.returncode, manifest, events

    def test_clean(self):
        code, manifest, _ = self.run_case("clean")
        self.assertEqual((code, manifest["CONSUMER_CORRECTNESS"], manifest["DEPENDENCY_RISK"]),
                         (0, "PASS", "GREEN"))

    def test_moderate_raw_one_gate_zero(self):
        code, manifest, _ = self.run_case("moderate")
        self.assertEqual(code, 0)
        self.assertEqual(manifest["steps"]["node-gate"]["exitCode"], 0)
        self.assertEqual(manifest["testRawNodeStatus"]["exitCode"], 1)

    def test_high(self):
        code, manifest, events = self.run_case("high")
        self.assertEqual((code, manifest["CONSUMER_CORRECTNESS"], manifest["DEPENDENCY_RISK"]),
                         (1, "PASS", "RED"))
        self.assertIn("uv export", events)

    def test_node_errors_still_attempt_python_and_e2e(self):
        for scenario in ("node_fail", "malformed", "missing", "error"):
            with self.subTest(scenario=scenario):
                code, manifest, events = self.run_case(scenario)
                self.assertEqual(code, 1)
                self.assertEqual(manifest["CONSUMER_CORRECTNESS"], "FAIL")
                self.assertIn("uv tool run", events)
                self.assertIn("npm audit", events)

    def test_setup_and_api_membership_fail_closed(self):
        for scenario in ("setup_fail", "api_missing", "api_audit_missing",
                         "api_tool_failure", "e2e_malformed"):
            with self.subTest(scenario=scenario):
                code, manifest, _ = self.run_case(scenario)
                self.assertEqual(code, 1)
                self.assertEqual(manifest["CONSUMER_CORRECTNESS"], "FAIL")

    def test_api_and_e2e_findings_propagate(self):
        for scenario in ("api_high", "e2e_high"):
            with self.subTest(scenario=scenario):
                code, manifest, _ = self.run_case(scenario)
                self.assertEqual(code, 1)
                self.assertEqual(manifest["DEPENDENCY_RISK"], "RED")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "fake":
        raise SystemExit(fake(sys.argv[2], sys.argv[3:]))
    unittest.main()
