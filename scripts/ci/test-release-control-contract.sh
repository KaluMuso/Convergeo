#!/usr/bin/env bash
# Self-test for RELCTRL-01 release-control contract (no secrets, no network).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

# Low-entropy synthetic 40-char hex SHAs — valid git SHA shape, not gitleaks bait.
SHA_FRONTEND="cccccccccccccccccccccccccccccccccccccccc"
SHA_API_LIVE="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
SHA_API_WANT="dddddddddddddddddddddddddddddddddddddddd"

pass=0
fail=0

ok() { echo "PASS: $*"; pass=$((pass + 1)); }
bad() { echo "FAIL: $*"; fail=$((fail + 1)); }

echo "==> RELCTRL-01 release-control contract self-test"

# 1) Static contract checker
if node scripts/ci/check-release-control-contract.mjs; then
  ok "static contract checker"
else
  bad "static contract checker"
fi

# 2) YAML syntax for new workflow
if python3 -c "
import yaml, pathlib
for path in (
    pathlib.Path('.github/workflows/promote-production-frontends.yml'),
    pathlib.Path('.github/workflows/capture-production-db-evidence.yml'),
):
    yaml.safe_load(path.read_text())
print('yaml ok')
" >/tmp/relctrl-yaml.txt 2>&1; then
  ok "promotion/capture workflow YAML syntax"
else
  bad "promotion/capture workflow YAML syntax"
  cat /tmp/relctrl-yaml.txt || true
fi

# 3) Parity validator rejects missing staging certification
TMP_CONTRACT="$(mktemp)"
cat >"$TMP_CONTRACT" <<JSON
{
  "candidate_frontend_sha": "${SHA_FRONTEND}",
  "candidate_api_sha": "${SHA_API_LIVE}",
  "required_db_migration_baseline": "0071_vendor_listing_compare_at",
  "production_api_sha_observed": "${SHA_API_LIVE}",
  "production_db_evidence_run_id": "1234567890"
}
JSON
set +e
python3 scripts/ci/validate_release_parity.py \
  --candidate-sha "${SHA_FRONTEND}" \
  --contract "$TMP_CONTRACT" \
  --skip-live-api >/tmp/parity-missing-staging.txt 2>&1
rc=$?
set -e
if [[ "$rc" -ne 0 ]] && grep -qi 'staging_certification' /tmp/parity-missing-staging.txt; then
  ok "parity validator rejects missing staging certification"
else
  bad "parity validator should reject missing staging certification (rc=$rc)"
  cat /tmp/parity-missing-staging.txt || true
fi

# 4) Parity validator rejects API skew
cat >"$TMP_CONTRACT" <<JSON
{
  "candidate_frontend_sha": "${SHA_FRONTEND}",
  "candidate_api_sha": "${SHA_API_WANT}",
  "required_db_migration_baseline": "0071_vendor_listing_compare_at",
  "production_api_sha_observed": "${SHA_API_LIVE}",
  "production_db_evidence_run_id": "1234567890",
  "staging_certification": {
    "result": "CERTIFIABLE_AFTER_INTEGRATION",
    "candidate_sha": "${SHA_FRONTEND}",
    "staging_frontend_sha": "${SHA_FRONTEND}",
    "certified_at": "2026-08-13T00:00:00Z",
    "evidence_run_id": "test-run"
  }
}
JSON
set +e
python3 scripts/ci/validate_release_parity.py \
  --candidate-sha "${SHA_FRONTEND}" \
  --contract "$TMP_CONTRACT" \
  --skip-live-api >/tmp/parity-api-skew.txt 2>&1
rc=$?
set -e
if [[ "$rc" -ne 0 ]] && grep -qi 'API/frontend skew' /tmp/parity-api-skew.txt; then
  ok "parity validator rejects API/frontend skew"
else
  bad "parity validator should reject API skew (rc=$rc)"
  cat /tmp/parity-api-skew.txt || true
fi

# 5) Parity validator accepts aligned contract (offline)
cat >"$TMP_CONTRACT" <<JSON
{
  "candidate_frontend_sha": "${SHA_FRONTEND}",
  "candidate_api_sha": "${SHA_API_LIVE}",
  "required_db_migration_baseline": "0071_vendor_listing_compare_at",
  "production_api_sha_observed": "${SHA_API_LIVE}",
  "production_db_evidence_run_id": "1234567890",
  "staging_certification": {
    "result": "CERTIFIABLE_AFTER_INTEGRATION",
    "candidate_sha": "${SHA_FRONTEND}",
    "staging_frontend_sha": "${SHA_FRONTEND}",
    "certified_at": "2026-08-13T00:00:00Z",
    "evidence_run_id": "test-run-aligned"
  }
}
JSON
if python3 scripts/ci/validate_release_parity.py \
  --candidate-sha "${SHA_FRONTEND}" \
  --contract "$TMP_CONTRACT" \
  --skip-live-api >/tmp/parity-ok.txt 2>&1; then
  ok "parity validator accepts aligned contract (offline)"
else
  bad "parity validator should accept aligned contract"
  cat /tmp/parity-ok.txt || true
fi

# 6) DB evidence validator rejects missing provenance fields
TMP_DB="$(mktemp)"
cat >"$TMP_DB" <<JSON
{
  "schema_version": "1",
  "gate": "RELCTRL-01-production-db",
  "repository": "KaluMuso/Convergeo",
  "workflow": "capture-production-db-evidence.yml",
  "workflow_run_id": "999",
  "candidate_sha": "${SHA_FRONTEND}",
  "migration_head": "0071",
  "observed_at": "2026-08-13T00:00:00Z",
  "observation_method": "readonly_psql"
}
JSON
set +e
python3 scripts/ci/validate_production_db_evidence.py \
  --candidate-sha "${SHA_FRONTEND}" \
  --required-baseline 0071_vendor_listing_compare_at \
  --evidence "$TMP_DB" \
  --skip-run-provenance \
  --skip-live-db >/tmp/db-evidence-ok.txt 2>&1
rc=$?
set -e
if [[ "$rc" -eq 0 ]]; then
  ok "DB evidence validator accepts machine-shaped evidence (offline)"
else
  bad "DB evidence validator should accept machine-shaped evidence (rc=$rc)"
  cat /tmp/db-evidence-ok.txt || true
fi

# 7) DB evidence validator rejects stale candidate binding
cat >"$TMP_DB" <<JSON
{
  "schema_version": "1",
  "gate": "RELCTRL-01-production-db",
  "repository": "KaluMuso/Convergeo",
  "workflow": "capture-production-db-evidence.yml",
  "workflow_run_id": "999",
  "candidate_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "migration_head": "0071",
  "observed_at": "2026-08-13T00:00:00Z",
  "observation_method": "readonly_psql"
}
JSON
set +e
python3 scripts/ci/validate_production_db_evidence.py \
  --candidate-sha "${SHA_FRONTEND}" \
  --required-baseline 0071_vendor_listing_compare_at \
  --evidence "$TMP_DB" \
  --skip-run-provenance \
  --skip-live-db >/tmp/db-evidence-bind.txt 2>&1
rc=$?
set -e
if [[ "$rc" -ne 0 ]] && grep -qi 'candidate_sha' /tmp/db-evidence-bind.txt; then
  ok "DB evidence validator rejects candidate_sha mismatch"
else
  bad "DB evidence validator should reject candidate_sha mismatch (rc=$rc)"
  cat /tmp/db-evidence-bind.txt || true
fi

rm -f "$TMP_CONTRACT" "$TMP_DB"

# 8) vercel-wait-production.sh rejects bad SHA without token
set +e
bash scripts/ci/vercel-wait-production.sh --sha deadbeef >/tmp/vercel-wait-bad.txt 2>&1
rc=$?
set -e
if [[ "$rc" -ne 0 ]]; then
  ok "vercel-wait-production.sh fails closed without valid inputs"
else
  bad "vercel-wait-production.sh should fail without VERCEL_TOKEN / valid sha"
fi

echo "==> summary: pass=$pass fail=$fail"
if [[ "$fail" -gt 0 ]]; then
  exit 1
fi
