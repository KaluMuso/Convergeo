#!/usr/bin/env bash
# Prove gitleaks is wired to fail CI on a real-shaped finding.
# Plants a synthetic AWS-style key in a throwaway git repo and asserts non-zero exit.
#
# Values are assembled at runtime (printf / base64) so this committed script never
# contains a contiguous token pattern. Historical versions of this file may still
# appear in git history — they are allowlisted by path in .gitleaks.toml.
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

cd "${WORKDIR}"
git init -q
git config user.email "ci-self-test@vergeo5.local"
git config user.name "CI Self-Test"

# Runtime-only synthetic fixtures (decoded here, never stored as one literal in git).
planted_key_id="$(printf '%s%s%s' 'AK' 'IA' 'ABCDEFGHIJKLMNOP')"
# Split the well-known AWS docs example secret so no single string matches scanners.
planted_secret="$(printf '%s/%s/%s%s' 'wJalrXUtnFEMI' 'K7MDENG' 'bPxRfiCYEXAM' 'PLEKEY')"

{
  echo "# gitleaks-self-test synthetic fixture — safe to fail the scanner"
  echo "AWS_ACCESS_KEY_ID=${planted_key_id}"
  echo "AWS_SECRET_ACCESS_KEY=${planted_secret}"
} > planted-secret.env

git add planted-secret.env
git commit -qm "ci: plant synthetic secret for gitleaks self-test"

set +e
"${GITLEAKS_BIN}" detect --source "${WORKDIR}" --config "${CONFIG}" --no-banner --redact >/tmp/gitleaks-self-test.out 2>&1
rc=$?
set -e

if [[ "${rc}" -eq 0 ]]; then
  echo "gitleaks-self-test FAILED: scanner returned 0 for a planted AWS-shaped secret" >&2
  cat /tmp/gitleaks-self-test.out >&2 || true
  exit 1
fi

if ! grep -qiE 'leak|AWS|AKIA|secret' /tmp/gitleaks-self-test.out; then
  echo "gitleaks-self-test FAILED: non-zero exit but output did not look like a secret hit" >&2
  cat /tmp/gitleaks-self-test.out >&2 || true
  exit 1
fi

echo "gitleaks-self-test OK (planted secret caught, exit=${rc})"

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
