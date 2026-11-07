#!/usr/bin/env bash
# Exercise the committed gitleaks config against real-shaped synthetic findings.
# Assemble credentials at runtime so no contiguous token is stored in this file.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CONFIG="${ROOT}/.gitleaks.toml"
GITLEAKS_BIN="${GITLEAKS_BIN:-gitleaks}"

if ! command -v "${GITLEAKS_BIN}" >/dev/null 2>&1; then
  echo "gitleaks-self-test: gitleaks binary not found on PATH" >&2
  exit 2
fi

WORKDIR="$(mktemp -d)"
cleanup() { rm -rf "${WORKDIR}"; }
trap cleanup EXIT

fixture_path="scripts/ci/fixtures/merge-evidence-incident-640.json"
adjacent_path="scripts/ci/fixtures/merge-evidence-incident-641.json"
fixture_sha="8434ca4c3083d42f0e0ba76b0f300e6c1cea3b25"
planted_key_id="$(printf '%s%s%s' 'AK' 'IA' 'ABCDEFGHIJKLMNOP')"
planted_secret="$(printf '%s/%s/%s%s' 'wJalrXUtnFEMI' 'K7MDENG' 'bPxRfiCYEXAM' 'PLEKEY')"
planted_gh_token="ghp_$(printf '%s' 'gitleaks-synthetic-pat-control' | sha256sum | cut -c1-36)"

init_case() {
  local name="$1"
  local repo="${WORKDIR}/${name}"
  mkdir -p "${repo}"
  git -C "${repo}" init -q
  git -C "${repo}" config user.email "ci-self-test@vergeo5.local"
  git -C "${repo}" config user.name "CI Self-Test"
}

commit_and_scan() {
  local name="$1"
  local expected_exit="$2"
  local repo="${WORKDIR}/${name}"
  local report="${WORKDIR}/${name}.json"
  local log="${WORKDIR}/${name}.log"
  local actual_exit

  git -C "${repo}" add .
  git -C "${repo}" commit -qm "plant ${name} fixture"
  set +e
  "${GITLEAKS_BIN}" detect --source "${repo}" --config "${CONFIG}" \
    --no-banner --redact --report-format json --report-path "${report}" >"${log}" 2>&1
  actual_exit=$?
  set -e
  if [[ "${actual_exit}" -ne "${expected_exit}" ]]; then
    echo "gitleaks-self-test FAILED: ${name} exited ${actual_exit}, expected ${expected_exit}" >&2
    cat "${log}" >&2
    exit 1
  fi
  if [[ "${expected_exit}" -eq 1 ]] && ! grep -q '"RuleID"' "${report}"; then
    echo "gitleaks-self-test FAILED: ${name} had no finding report" >&2
    cat "${log}" >&2
    exit 1
  fi
  echo "gitleaks-self-test OK: ${name} (exit=${actual_exit})"
}

# The known rejected merge-evidence fixture contains only the repeated SHA.
init_case original_fixture
mkdir -p "${WORKDIR}/original_fixture/$(dirname "${fixture_path}")"
cp "${ROOT}/${fixture_path}" "${WORKDIR}/original_fixture/${fixture_path}"
commit_and_scan original_fixture 0

# A secret at the formerly exempt whole-file path must still be detected.
init_case same_path_aws
mkdir -p "${WORKDIR}/same_path_aws/$(dirname "${fixture_path}")"
printf '{"AWS_ACCESS_KEY_ID":"%s","AWS_SECRET_ACCESS_KEY":"%s"}\n' \
  "${planted_key_id}" "${planted_secret}" >"${WORKDIR}/same_path_aws/${fixture_path}"
commit_and_scan same_path_aws 1

# The allowlisted SHA must not mask a credential beside it on the same line.
init_case same_line_aws
mkdir -p "${WORKDIR}/same_line_aws/$(dirname "${fixture_path}")"
printf '{"staging_api_sha":"%s","AWS_ACCESS_KEY_ID":"%s","AWS_SECRET_ACCESS_KEY":"%s"}\n' \
  "${fixture_sha}" "${planted_key_id}" "${planted_secret}" \
  >"${WORKDIR}/same_line_aws/${fixture_path}"
commit_and_scan same_line_aws 1

init_case adjacent_path_aws
mkdir -p "${WORKDIR}/adjacent_path_aws/$(dirname "${adjacent_path}")"
printf '{"AWS_ACCESS_KEY_ID":"%s","AWS_SECRET_ACCESS_KEY":"%s"}\n' \
  "${planted_key_id}" "${planted_secret}" >"${WORKDIR}/adjacent_path_aws/${adjacent_path}"
commit_and_scan adjacent_path_aws 1

# An independent detector must also remain active on the exact path.
init_case same_path_github
mkdir -p "${WORKDIR}/same_path_github/$(dirname "${fixture_path}")"
printf '{"GITHUB_TOKEN":"%s"}\n' "${planted_gh_token}" \
  >"${WORKDIR}/same_path_github/${fixture_path}"
commit_and_scan same_path_github 1

# Only eight independently hashed inventory values are exempt at this exact path.
# Real-shaped credentials on that path must still trip independent detectors.
coordinator_path="scripts/ci/coordinator-gate-inputs.json"
init_case coordinator_inventory
mkdir -p "${WORKDIR}/coordinator_inventory/$(dirname "${coordinator_path}")"
cp "${ROOT}/${coordinator_path}" "${WORKDIR}/coordinator_inventory/${coordinator_path}"
commit_and_scan coordinator_inventory 0

init_case coordinator_same_path_aws
mkdir -p "${WORKDIR}/coordinator_same_path_aws/$(dirname "${coordinator_path}")"
printf '{"AWS_ACCESS_KEY_ID":"%s","AWS_SECRET_ACCESS_KEY":"%s"}\n' \
  "${planted_key_id}" "${planted_secret}" \
  >"${WORKDIR}/coordinator_same_path_aws/${coordinator_path}"
commit_and_scan coordinator_same_path_aws 1

init_case coordinator_same_path_github
mkdir -p "${WORKDIR}/coordinator_same_path_github/$(dirname "${coordinator_path}")"
printf '{"GITHUB_TOKEN":"%s"}\n' "${planted_gh_token}" \
  >"${WORKDIR}/coordinator_same_path_github/${coordinator_path}"
commit_and_scan coordinator_same_path_github 1

# Structured new-commit, history, other-ref and scanner-error controls.
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

# The published staging image tag is a public commit SHA, not a credential.
# Exercise the exact allowlist with the real scanner: changing either the value
# or the path must still trigger generic-api-key.
public_source_commit="$(printf '%s%s' 'cfe11ba8e5bb1893427f' 'f256f4266a616230832f')"
other_commit="$(printf '%s%s' 'fda8e708a0a288268af5' 'fe9f9c767529316ed5e3')"

check_image_tag_case() {
  local case_name="$1" path="$2" value="$3" expected="$4"
  local case_dir="${WORKDIR}/${case_name}" scan_rc
  mkdir -p "${case_dir}/$(dirname "$path")"
  git -C "$case_dir" init -q
  git -C "$case_dir" config user.email "ci-self-test@vergeo5.local"
  git -C "$case_dir" config user.name "CI Self-Test"
  printf 'API_IMAGE_TAG=%s\ntags: ghcr.io/kalumuso/convergeo-api:%s\n' "$value" "$value" > "${case_dir}/${path}"
  git -C "$case_dir" add "$path"
  git -C "$case_dir" commit -qm "ci: check image tag allowlist boundary"

  set +e
  "$GITLEAKS_BIN" detect --source "$case_dir" --config "$CONFIG" --no-banner --verbose --redact > "${case_dir}/scan.out" 2>&1
  scan_rc=$?
  set -e
  if [[ "$scan_rc" -ne "$expected" ]]; then
    echo "gitleaks-self-test FAILED: ${case_name} exited ${scan_rc}, expected ${expected}" >&2
    cat "${case_dir}/scan.out" >&2
    exit 1
  fi
  if [[ "$expected" -eq 1 ]] && ! grep -q 'RuleID:.*generic-api-key' "${case_dir}/scan.out"; then
    echo "gitleaks-self-test FAILED: ${case_name} did not trigger generic-api-key" >&2
    cat "${case_dir}/scan.out" >&2
    exit 1
  fi
  echo "gitleaks-self-test OK (${case_name}, exit=${scan_rc})"
}

check_image_tag_case allowed .github/workflows/api-image.yml "$public_source_commit" 0
check_image_tag_case changed-value .github/workflows/api-image.yml "$other_commit" 1
check_image_tag_case changed-path .github/workflows/other-image.yml "$public_source_commit" 1
