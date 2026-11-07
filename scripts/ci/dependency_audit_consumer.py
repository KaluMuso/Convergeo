#!/usr/bin/env python3
"""Run three independent frozen dependency audits and fail closed on their evidence."""

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def command(name):
    override = os.environ.get(f"AUDIT_{name.upper()}_CMD")
    return shlex.split(override) if override else [name.lower()]


def record(directory, name, argv, cwd):
    """Keep output and process state even when spawning fails."""
    status = {"command": argv, "cwd": str(cwd), "exitCode": None, "signal": None,
              "spawnError": None, "timeoutSeconds": None}
    try:
        result = subprocess.run(argv, cwd=cwd, capture_output=True, check=False,
                                timeout=600 if name in ("node-install", "api-sync", "e2e-install") else 300)
        stdout, stderr = result.stdout, result.stderr
        if result.returncode < 0:
            status["signal"] = -result.returncode
        else:
            status["exitCode"] = result.returncode
    except OSError as exc:
        stdout, stderr = b"", str(exc).encode()
        status["spawnError"] = {"code": exc.errno, "message": str(exc)}
    except subprocess.TimeoutExpired as exc:
        stdout, stderr = exc.stdout or b"", exc.stderr or b""
        status["timeoutSeconds"] = exc.timeout
    (directory / f"{name}.stdout.txt").write_bytes(stdout)
    (directory / f"{name}.stderr.txt").write_bytes(stderr)
    (directory / f"{name}.status.json").write_text(json.dumps(status, indent=2) + "\n")
    return status


def good(status):
    return (status["exitCode"] == 0 and status["signal"] is None
            and status["spawnError"] is None and status["timeoutSeconds"] is None)


def nonempty_json(path):
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or not data:
        raise ValueError(f"{path.name}: empty or non-object JSON")
    if "error" in data:
        raise ValueError(f"{path.name}: tool reported an error")
    return data


def validate_pnpm(report, process, gate):
    if set(process) != {"exitCode", "signal", "spawnError"}:
        raise ValueError("pnpm raw process status malformed")
    if process["exitCode"] not in (0, 1) or process["signal"] is not None or process["spawnError"] is not None:
        raise ValueError("pnpm raw process failed")
    advisories = report.get("advisories")
    counts = report.get("metadata", {}).get("vulnerabilities")
    severities = ("info", "low", "moderate", "high", "critical")
    if not isinstance(advisories, dict) or not isinstance(counts, dict) or set(counts) != set(severities):
        raise ValueError("pnpm advisory/count schema malformed")
    if report.get("muted", []) != []:
        raise ValueError("pnpm muted findings are unsupported")
    actual = dict.fromkeys(severities, 0)
    for advisory in advisories.values():
        if not isinstance(advisory, dict) or advisory.get("severity") not in severities:
            raise ValueError("pnpm advisory malformed")
        if not isinstance(advisory.get("module_name"), str) or not advisory["module_name"].strip():
            raise ValueError("pnpm module missing")
        findings = advisory.get("findings")
        if not isinstance(findings, list) or not findings:
            raise ValueError("pnpm findings missing")
        for finding in findings:
            if not isinstance(finding, dict) or not isinstance(finding.get("version"), str) or not finding["version"]:
                raise ValueError("pnpm finding version missing")
            if not isinstance(finding.get("paths"), list) or not finding["paths"] or not all(
                isinstance(path, str) and path for path in finding["paths"]
            ):
                raise ValueError("pnpm finding paths malformed")
        actual[advisory["severity"]] += len(findings)
    for severity in severities:
        value = counts[severity]
        if type(value) is not int or value < 0 or value != actual[severity]:
            raise ValueError(f"pnpm {severity} count mismatch")
    total = sum(actual.values())
    if (process["exitCode"] == 0) != (total == 0):
        raise ValueError("pnpm raw status conflicts with findings")
    expected_gate = 1 if actual["high"] + actual["critical"] else 0
    if gate != expected_gate:
        raise ValueError("pnpm gate conflicts with report")
    return expected_gate


def package_membership(requirements):
    text = requirements.read_text()
    roots = tomllib.loads((ROOT / "services/api/pyproject.toml").read_text())["project"]["dependencies"]
    names = [re.match(r"[A-Za-z0-9_.-]+", root).group(0) for root in roots]
    names.append("cryptography")
    missing = []
    for name in names:
        pattern = rf"(?im)^{re.escape(name)}==[A-Za-z0-9_.+!~-]+(?:\s*;.*)?$"
        if not re.search(pattern, text):
            missing.append(name)
    if "cryptography==50.0.0" not in text:
        missing.append("cryptography==50.0.0")
    return sorted(set(missing))


def audited_membership(report):
    roots = tomllib.loads((ROOT / "services/api/pyproject.toml").read_text())["project"]["dependencies"]
    required = {re.match(r"[A-Za-z0-9_.-]+", root).group(0).lower().replace("_", "-")
                for root in roots} | {"cryptography"}
    audited = {entry.get("name", "").lower().replace("_", "-"): entry.get("version")
               for entry in report["dependencies"] if isinstance(entry, dict)}
    missing = sorted(name for name in required if name not in audited)
    if audited.get("cryptography") != "50.0.0":
        missing.append("cryptography==50.0.0")
    return sorted(set(missing))


def aggregate(directory, steps):
    errors = []
    findings = []
    if not re.fullmatch(r"v22\.\d+\.\d+", (directory / "node-version.stdout.txt").read_text().strip()):
        errors.append("Node version is not 22")
    if (directory / "pnpm-version.stdout.txt").read_text().strip() != "9.15.4":
        errors.append("pnpm version is not 9.15.4")
    for name, status in steps.items():
        policy_exit = (name in ("node-gate", "api-audit", "e2e-audit")
                       and status["exitCode"] == 1 and status["signal"] is None
                       and status["spawnError"] is None)
        if not good(status) and not policy_exit:
            errors.append(f"{name}: command failed or did not start")
        for suffix in ("stdout.txt", "stderr.txt", "status.json"):
            if not (directory / f"{name}.{suffix}").exists():
                errors.append(f"{name}: missing {suffix}")
        try:
            if nonempty_json(directory / f"{name}.status.json") != status:
                raise ValueError("status does not match observed process")
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            errors.append(f"{name}: malformed status evidence: {exc}")

    raw = directory / "pnpm-audit.json"
    raw_status = directory / "pnpm-audit.status.json"
    try:
        report = nonempty_json(raw)
        process = nonempty_json(raw_status)
        if validate_pnpm(report, process, steps["node-gate"]["exitCode"]):
            findings.append("Node high/critical advisory")
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        errors.append(f"node evidence: {exc}")

    try:
        if (directory / "api-requirements.txt").stat().st_size == 0:
            raise ValueError("empty API export")
        missing = package_membership(directory / "api-requirements.txt")
        if missing:
            raise ValueError(f"missing frozen packages: {', '.join(missing)}")
        report = nonempty_json(directory / "api-audit.json")
        if not isinstance(report.get("dependencies"), list):
            raise ValueError("pip-audit dependencies missing")
        if any(not isinstance(dependency, dict) or not isinstance(dependency.get("vulns"), list)
               for dependency in report["dependencies"]):
            raise ValueError("pip-audit dependency record malformed")
        missing = audited_membership(report)
        if missing:
            raise ValueError(f"pip-audit did not inspect: {', '.join(missing)}")
        if any(dependency["vulns"] for dependency in report["dependencies"]):
            findings.append("API vulnerability")
            if steps["api-audit"]["exitCode"] == 0:
                raise ValueError("pip-audit status conflicts with vulnerabilities")
        if steps["api-audit"]["exitCode"] == 1 and not any(
            dependency["vulns"] for dependency in report["dependencies"]
        ):
            raise ValueError("pip-audit status conflicts with report")
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        errors.append(f"API evidence: {exc}")

    try:
        report = nonempty_json(directory / "e2e-audit.json")
        counts = report.get("metadata", {}).get("vulnerabilities")
        severities = {"info", "low", "moderate", "high", "critical", "total"}
        if (type(report.get("auditReportVersion")) is not int
                or report["auditReportVersion"] < 1
                or not isinstance(report.get("vulnerabilities"), dict)
                or not isinstance(counts, dict) or set(counts) != severities
                or not all(type(value) is int and value >= 0 for value in counts.values())
                or counts["total"] != sum(counts[s] for s in severities - {"total"})):
            raise ValueError("npm audit schema/counts malformed")
        if any(counts.values()) and steps["e2e-audit"]["exitCode"] == 0:
            raise ValueError("npm audit status conflicts with findings")
        if counts["total"] == 0 and steps["e2e-audit"]["exitCode"] == 1:
            raise ValueError("npm audit nonzero status without findings")
        if steps["e2e-audit"]["exitCode"] == 1:
            findings.append("E2E npm audit nonzero")
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        errors.append(f"E2E evidence: {exc}")

    manifest = {"policy": "Node high/critical; API and E2E any finding",
                "editableProjectExclusion": "uv --no-emit-project excludes only local vergeo5-api; frozen third-party graph retained",
                "steps": steps, "evidenceErrors": errors, "policyFindings": findings,
                "CONSUMER_CORRECTNESS": "PASS" if not errors else "FAIL",
                "DEPENDENCY_RISK": "RED" if findings else ("UNKNOWN" if errors else "GREEN")}
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return errors + findings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args()
    directory = args.evidence_dir.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    api = ROOT / "services/api"
    e2e = ROOT / "e2e"
    steps = {}
    for name, argv, cwd in (
        ("node-version", command("node") + ["--version"], ROOT),
        ("pnpm-version", command("pnpm") + ["--version"], ROOT),
        ("node-install", command("pnpm") + ["install", "--frozen-lockfile"], ROOT),
        ("node-gate", command("node") + ["scripts/ci/pnpm-audit-gate.mjs", "--output", str(directory / "pnpm-audit.json"), "--stderr-output", str(directory / "pnpm-audit.stderr.txt"), "--status-output", str(directory / "pnpm-audit.status.json")], ROOT),
        ("uv-version", command("uv") + ["--version"], api),
        ("api-sync", command("uv") + ["sync", "--dev", "--frozen"], api),
        ("api-export", command("uv") + ["export", "--frozen", "--all-groups", "--no-hashes", "--no-emit-project", "--output-file", str(directory / "api-requirements.txt")], api),
        ("api-audit", command("uv") + ["tool", "run", "--from", "pip-audit==2.10.1", "pip-audit", "-r", str(directory / "api-requirements.txt"), "--no-deps", "--disable-pip", "--format", "json", "--output", str(directory / "api-audit.json")], api),
        ("e2e-install", command("npm") + ["ci", "--ignore-scripts"], e2e),
        ("e2e-audit", command("npm") + ["audit", "--json"], e2e),
    ):
        steps[name] = record(directory, name, argv, cwd)
        if name == "e2e-audit":
            (directory / "e2e-audit.json").write_bytes((directory / "e2e-audit.stdout.txt").read_bytes())
    errors = aggregate(directory, steps)
    for error in errors:
        print(f"::error::{error}", file=sys.stderr)
    print(f"Dependency audit evidence: {directory}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
