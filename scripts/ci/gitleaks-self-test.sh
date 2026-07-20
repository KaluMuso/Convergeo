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
