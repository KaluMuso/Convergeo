#!/usr/bin/env bash
# Exercise the real pinned scanner with the approved exception set. Synthetic
# values exist only in private throwaway repos; never print raw scanner output.
set -euo pipefail
umask 077
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
python3 - "$ROOT" "${GITLEAKS_BIN:-gitleaks}" <<'PY'
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

root = Path(sys.argv[1])
binary = shutil.which(sys.argv[2])
if not binary:
    raise SystemExit("gitleaks-self-test: scanner unavailable")
config = root / ".gitleaks.toml"
ignore = root / ".gitleaksignore"
historical_commit = "090ba3adf6978f9358ef6b437a07a0c993e3bd78"
manifest = "scripts/ci/coordinator-gate-inputs.json"
expected = {
    f"{historical_commit}:{manifest}:generic-api-key:{line}"
    for line in (360, 394, 408, 453, 455, 456, 457, 509)
}
entries = [line.strip() for line in ignore.read_text().splitlines()
           if line.strip() and not line.lstrip().startswith("#")]
if len(entries) != 8 or set(entries) != expected:
    raise SystemExit("gitleaks-self-test: exception set differs from eight approved fingerprints")

def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.DEVNULL).decode().strip()

def init(repo):
    repo.mkdir()
    git(repo, "init", "-q", "-b", "control")
    git(repo, "config", "user.email", "ci-self-test@vergeo5.local")
    git(repo, "config", "user.name", "CI Self-Test")

def scan(repo, report, config_path=config):
    result = subprocess.run([binary, "detect", "--source", str(repo), "--config", str(config_path),
                             "--gitleaks-ignore-path", str(ignore), "--no-banner", "--redact=100",
                             "--report-format", "json", "--report-path", str(report)],
                            capture_output=True, timeout=60)
    findings = json.loads(report.read_text()) if report.exists() else None
    return result.returncode, findings

def require_detection(result, controls):
    status, findings = result
    if status != 1 or not isinstance(findings, list):
        raise ValueError("scanner did not produce a finding report with exit1")
    if any(f.get("Secret") != "REDACTED" for f in findings):
        raise ValueError("scanner report was not redacted")
    actual = {(f.get("RuleID"), f.get("File"), f.get("StartLine"), f.get("Commit")) for f in findings}
    if not set(controls).issubset(actual):
        raise ValueError("expected planted finding missing")

try:
    with tempfile.TemporaryDirectory(prefix="gitleaks-controls-") as temp:
        work = Path(temp)
        repo = work / "repo"
        init(repo)
        target = repo / manifest
        target.parent.mkdir(parents=True)
        synthetic = hashlib.sha256(b"runtime-only generic scanner negative control").hexdigest()
        # Same path/line/key and64hex shape as the historical false positive,
        # but a new immutable commit must remain detectable.
        target.write_text("\n" * 359 + f'"0017_order_pickup_tokens.sql": "{synthetic}"\n'
                          + f'api_key = "{synthetic}"\n'
                          + "AWS_ACCESS_KEY_ID=" + "AK" + "IA" + "ABCDEFGHIJKLMNOP\n")
        ordinary = repo / "source-negative.env"
        ordinary.write_text(f'api_key = "{synthetic}"\n'
                            + "AWS_ACCESS_KEY_ID=" + "AK" + "IA" + "ABCDEFGHIJKLMNOP\n")
        git(repo, "add", ".")
        git(repo, "commit", "-qm", "ci: plant runtime-only controls")
        planted_commit = git(repo, "rev-parse", "HEAD")
        controls = [("generic-api-key", manifest, 360, planted_commit),
                    ("generic-api-key", manifest, 361, planted_commit),
                    ("aws-access-token", manifest, 362, planted_commit),
                    ("generic-api-key", "source-negative.env", 1, planted_commit),
                    ("aws-access-token", "source-negative.env", 2, planted_commit)]
        # Delete the planted values from the tip; history must still be scanned.
        target.unlink()
        ordinary.unlink()
        git(repo, "add", "-u")
        git(repo, "commit", "-qm", "ci: delete controls from current tree")
        # A separate ref must also remain in the default all-ref scan.
        git(repo, "checkout", "-qb", "history-control")
        (repo / "other-ref.env").write_text(f'api_key = "{synthetic}"\n')
        git(repo, "add", ".")
        git(repo, "commit", "-qm", "ci: plant other-ref control")
        controls.append(("generic-api-key", "other-ref.env", 1, git(repo, "rev-parse", "HEAD")))
        git(repo, "checkout", "-q", "control")
        require_detection(scan(repo, work / "findings.json"), controls)
        clean = work / "clean"
        init(clean)
        git(clean, "commit", "--allow-empty", "-qm", "ci: clean control")
        if scan(clean, work / "clean.json") != (0, []):
            raise ValueError("clean control did not return exit0/empty report")
        malformed = work / "invalid.toml"
        malformed.write_text("[not valid toml")
        # Configuration errors cannot masquerade as successful detection.
        invalid = scan(repo, work / "invalid.json", malformed)
        try:
            require_detection(invalid, controls)
        except ValueError:
            pass
        else:
            raise ValueError("configuration error accepted as planted detection")
    print("gitleaks-self-test OK: six planted history/ref findings caught; clean and error controls verified")
except Exception:
    raise SystemExit("gitleaks-self-test FAILED: structured detection/control contract failed") from None
PY
