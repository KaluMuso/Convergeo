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
