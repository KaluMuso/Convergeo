#!/usr/bin/env bash
# Prove real-shaped findings still fail, including paths with historical exceptions.
# Synthetic values exist only in disposable fixtures and never appear in output.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GITLEAKS_BIN="${GITLEAKS_BIN:-gitleaks}"

if ! command -v "${GITLEAKS_BIN}" >/dev/null 2>&1; then
  echo "gitleaks-self-test: gitleaks binary not found on PATH" >&2
  exit 2
fi

python3 - "${ROOT}" "$(command -v "${GITLEAKS_BIN}")" <<'PY'
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

root, binary = pathlib.Path(sys.argv[1]), sys.argv[2]
ignore = root / ".gitleaksignore"
entries = [line.strip() for line in ignore.read_text().splitlines()
           if line.strip() and not line.lstrip().startswith("#")]
if not entries or any(not re.fullmatch(r"[a-f0-9]{40}:[^:]+:generic-api-key:[1-9][0-9]*", line)
                      for line in entries):
    sys.exit("gitleaks-self-test FAILED: exceptions must be exact historical fingerprints")

with tempfile.TemporaryDirectory(prefix="gitleaks-self-test-") as temp:
    work = pathlib.Path(temp)
    shutil.copyfile(ignore, work / ".gitleaksignore")
    subprocess.run(["git", "init", "-q", str(work)], check=True, capture_output=True)
    expected = set()

    def synthetic(label, width):
        # Deterministic high-entropy hex; no credential is embedded in this script.
        return getattr(hashlib, "sha1" if width == 40 else "sha256")(label.encode()).hexdigest()

    def fixture(path, assignments):
        lines = ["# synthetic scanner fixture"] * max(assignments)
        for number, content in assignments.items():
            lines[number - 1] = content
            expected.add((path, number, "generic-api-key"))
        target = work / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(lines) + "\n")

    # Reuse historically ignored fields and lines, plus unrelated adjacent fields.
    # Different 40/64-hex values in every path must still fail in a new commit.
    fixture("scripts/ci/check_hosted_chrome.sh", {
        8: "google_key_fingerprint=" + synthetic("chrome-context-40", 40),
        9: "google_key_fingerprint=" + synthetic("chrome-context-64", 64),
        10: "api_key=" + synthetic("chrome-adjacent-40", 40),
        11: "client_secret=" + synthetic("chrome-adjacent-64", 64),
    })
    fixture(".github/workflows/api-image.yml", {
        190: "API_IMAGE_TAG=" + synthetic("image-context-40", 40),
        193: "tags: ghcr.io/kalumuso/convergeo-api:" + synthetic("image-context-64", 64),
        194: "api_key=" + synthetic("image-adjacent-40", 40),
        195: "client_secret=" + synthetic("image-adjacent-64", 64),
    })
    fixture("scripts/ci/coordinator-gate-inputs.json", {
        360: '"0017_order_pickup_tokens.sql": "' + synthetic("manifest-context-64", 64) + '",',
        394: '"0051_custom_access_token_role_hook.sql": "' + synthetic("manifest-context-new-40", 40) + '",',
        395: '"api_key": "' + synthetic("manifest-adjacent-40", 40) + '",',
        396: '"client_secret": "' + synthetic("manifest-adjacent-64", 64) + '",',
    })
    # Preserve the existing AWS-specific regression, assembling its shape at runtime.
    (work / "planted-secret.env").write_text("AWS_ACCESS_KEY_ID=" + "AK" + "IA" + "ABCDEFGHIJKLMNOP\n")
    expected.add(("planted-secret.env", 1, "aws-access-token"))
    subprocess.run(["git", "-C", temp, "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", temp, "-c", "user.name=CI Self-Test",
                    "-c", "user.email=ci-self-test@vergeo5.local", "-c", "commit.gpgsign=false",
                    "commit", "-qm", "ci: plant disposable scanner fixtures"],
                   check=True, capture_output=True)
    report = work / "report.json"
    result = subprocess.run([binary, "detect", "--source", temp,
                             "--config", str(root / ".gitleaks.toml"),
                             "--no-banner", "--redact=100", "--report-format", "json",
                             "--report-path", str(report)], cwd=temp, capture_output=True)
    if result.returncode != 1 or not report.is_file():
        sys.exit(f"gitleaks-self-test FAILED: expected finding exit 1, got {result.returncode}")
    findings = json.loads(report.read_text())
    actual = {(item["File"], item["StartLine"], item["RuleID"]) for item in findings}
    missing = sorted(expected - actual)
    if missing:
        # Only metadata is safe to print; never dump reports, matches, or scanner logs.
        sys.exit("gitleaks-self-test FAILED: missing finding metadata " + repr(missing))
    print(f"gitleaks-self-test OK ({len(expected)} planted findings caught, exit=1; "
          "40/64-hex and adjacent credentials in all three paths)")
PY
