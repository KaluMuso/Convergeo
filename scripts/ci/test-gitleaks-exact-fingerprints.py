#!/usr/bin/env python3
"""Check that historical fingerprint exceptions cannot hide fresh findings.

Uses only disposable local Git history and runtime-generated synthetic values.
The existing CI scanner invocation/configuration is not modified by this test.
"""

import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
BIN = os.environ.get("GITLEAKS_BIN", "gitleaks")


def run(argv, cwd):
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    require(run([BIN, "version"], ROOT).stdout.strip() == "8.28.0", "Gitleaks 8.28.0 required")
    lines = (ROOT / ".gitleaksignore").read_text().splitlines()
    entries = [line for line in lines if line and not line.startswith("#")]
    require(len(entries) == len(set(entries)) == 16, "Expected exactly 16 unique fingerprints")
    pattern = re.compile(r"[0-9a-f]{40}:(.+):generic-api-key:([1-9][0-9]*)")
    sites = []
    for entry in entries:
        match = pattern.fullmatch(entry)
        require(match is not None, "Only exact historical generic-api-key fingerprints permitted")
        path, line = match.groups()
        require(not Path(path).is_absolute() and ".." not in Path(path).parts, "Unsafe fixture path")
        sites.append((path, int(line)))
    sites = set(sites)
    paths = sorted({path for path, _ in sites})
    require(len(paths) == 4, "Expected four affected historical paths")

    with tempfile.TemporaryDirectory(prefix="gitleaks-exact-fingerprints-") as temporary:
        repo = Path(temporary)
        for name in (".gitleaks.toml", ".gitleaksignore"):
            shutil.copyfile(ROOT / name, repo / name)
        empty = repo / "empty.ignore"
        empty.write_text("")
        for args in (["init", "-q"], ["config", "user.name", "Scanner negative control"],
                     ["config", "user.email", "scanner-control@example.invalid"]):
            require(run(["git", *args], repo).returncode == 0, "Disposable Git setup failed")

        def commit(message):
            require(run(["git", "add", "."], repo).returncode == 0, "Fixture staging failed")
            require(run(["git", "commit", "-qm", message], repo).returncode == 0, "Fixture commit failed")
            return run(["git", "rev-parse", "HEAD"], repo).stdout.strip()

        def scan(label, use_empty=False):
            report = repo / (label + ".json")
            command = [BIN, "detect", "--source", ".", "--config", ".gitleaks.toml",
                       "--no-banner", "--redact", "--report-format", "json", "--report-path", str(report)]
            if use_empty:
                command += ["--gitleaks-ignore-path", str(empty)]
            # 8.28 also loads source/.gitleaksignore even with an explicit empty
            # ignore path. Remove it only in this disposable baseline fixture.
            ignore = repo / ".gitleaksignore"
            saved = ignore.read_bytes()
            if use_empty:
                ignore.unlink()
            try:
                result = run(command, repo)
            finally:
                if use_empty:
                    ignore.write_bytes(saved)
            require(report.exists(), "Scanner failed to produce a report")
            findings = json.loads(report.read_text())
            # Reports live outside Git input and contain only redacted synthetic data.
            report.unlink()
            return result.returncode, findings

        commit("test: clean scanner fixture")
        code, found = scan("clean")
        require(code == 0 and not found, "Clean fixture must scan successfully")
        commits = []
        aws_sites = set()
        for revision in range(2):
            for path in paths:
                selected = {line for name, line in sites if name == path}
                aws_line = max(selected) + 2
                content = ["# synthetic scanner control\n"] * aws_line
                for line in selected:
                    content[line - 1] = 'api_key = "' + secrets.token_hex(32) + '"\n'
                # Runtime-only AWS-shaped negative control; never an actual credential.
                content[aws_line - 1] = "AWS_ACCESS_KEY_ID=" + "AK" + "IA" + "ABCDEFGHIJKLMNOP" + "\n"
                target = repo / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("".join(content))
                aws_sites.add((path, aws_line))
            commits.append(commit("test: synthetic findings revision " + str(revision + 1)))

        code, baseline = scan("empty-ignore", use_empty=True)
        require(code == 1, "Empty-ignore synthetic findings must fail with exit 1")
        code, actual = scan("actual-ignore")
        require(code == 1, "Actual-ignore synthetic findings must fail with exit 1")
        fingerprints = {item["Fingerprint"] for item in actual}
        require(fingerprints == {item["Fingerprint"] for item in baseline}, "Exact exceptions changed fresh findings")
        expected = {(commit, path, line, "generic-api-key") for commit in commits for path, line in sites}
        expected |= {(commits[0], path, line, "aws-access-token") for path, line in aws_sites}
        observed = {(item["Commit"], item["File"], item["StartLine"], item["RuleID"]) for item in actual}
        require(expected == observed and len(actual) == len(expected),
                "Synthetic findings differ from the exact expected path/line/rule/commit set")
        require(not fingerprints.intersection(entries), "Fresh finding unexpectedly reused a historical fingerprint")
        print(json.dumps({"result": "PASS", "gitleaks_version": "8.28.0", "historical_exceptions": 16,
                          "affected_paths": paths, "unique_generic_sites": len(sites),
                          "fresh_and_changed_generic_findings": len(sites) * 2,
                          "aws_findings": len(aws_sites), "actual_findings": len(actual),
                          "empty_ignore_exit": 1, "actual_ignore_exit": 1,
                          "fresh_fingerprint_sets_equal": True}, indent=2))


if __name__ == "__main__":
    main()
