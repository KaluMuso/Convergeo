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
    "result": "PASS",
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
    "result": "PASS",
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

# 9) verify workflow does not move Git refs
if ! grep -Eiq 'git push|refs/heads/production|fast-forward production' .github/workflows/promote-production-frontends.yml; then
  ok "verify workflow does not move Git refs"
else
  bad "promote-production-frontends.yml must not git push or fast-forward production"
fi

# 10+) merge release evidence validator (RELCTRL-02)
SHA_CANDIDATE="eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
SHA_OTHER="ffffffffffffffffffffffffffffffffffffffff"
SHA_DIGEST="abababababababababababababababababababababababababababababababab"
INCIDENT640_HEAD="bf9cca402a4d83a0d37a0534c54398a1461ed5d7"

merge_evidence_reject() {
  local label="$1"
  shift
  set +e
  "$@" >/tmp/merge-reject.txt 2>&1
  local rc=$?
  set -e
  if [[ "$rc" -ne 0 ]]; then
    ok "merge evidence rejects: $label"
  else
    bad "merge evidence should reject: $label"
    cat /tmp/merge-reject.txt || true
  fi
}

merge_evidence_accept() {
  local label="$1"
  shift
  if "$@" >/tmp/merge-accept.txt 2>&1; then
    ok "merge evidence accepts: $label"
  else
    bad "merge evidence should accept: $label"
    cat /tmp/merge-accept.txt || true
  fi
}

write_pass_evidence() {
  local path="$1"
  local candidate="$2"
  local deploy_run="${3:-111111111}"
  local cert_run="${4:-222222222}"
  cat >"$path" <<JSON
{
  "schema_version": "2",
  "candidate_sha": "${candidate}",
  "staging_certification": {
    "mode": "integrated-staging",
    "result": "PASS",
    "candidate_sha": "${candidate}",
    "staging_frontend_sha": "${candidate}",
    "staging_api_sha": "${candidate}",
    "staging_branch_sha": "${candidate}",
    "certified_at": "2026-08-13T00:00:00Z",
    "certification_completed_at": "2026-08-13T00:05:00Z",
    "staging_deploy_workflow_run_id": "${deploy_run}",
    "evidence_run_id": "${cert_run}"
  },
  "provenance": {
    "source_workflow": "release-certify.yml",
    "source_run_id": "${cert_run}",
    "source_run_attempt": 1,
    "artifact_name": "staging-certification-evidence",
    "artifact_digest_sha256": "${SHA_DIGEST}"
  }
}
JSON
}

TMP_MERGE="$(mktemp)"

# 10) PR #640 incident fixture must reject
merge_evidence_reject "PR #640 incident fixture" \
  python3 scripts/ci/validate_merge_release_evidence.py \
    --candidate-sha "${INCIDENT640_HEAD}" \
    --evidence scripts/ci/fixtures/merge-evidence-incident-640.json \
    --skip-github-provenance \
    --current-run-id "999999999"

# 11) CERTIFIABLE_AFTER_INTEGRATION must reject even when SHAs align
write_pass_evidence "$TMP_MERGE" "${SHA_CANDIDATE}"
python3 - <<PY
import json, pathlib
p = pathlib.Path("${TMP_MERGE}")
data = json.loads(p.read_text())
data["staging_certification"]["result"] = "CERTIFIABLE_AFTER_INTEGRATION"
p.write_text(json.dumps(data, indent=2) + "\n")
PY
merge_evidence_reject "CERTIFIABLE_AFTER_INTEGRATION" \
  python3 scripts/ci/validate_merge_release_evidence.py \
    --candidate-sha "${SHA_CANDIDATE}" \
    --evidence "$TMP_MERGE" \
    --skip-github-provenance

# 12) candidate SHA mismatch
write_pass_evidence "$TMP_MERGE" "${SHA_CANDIDATE}"
merge_evidence_reject "candidate SHA mismatch" \
  python3 scripts/ci/validate_merge_release_evidence.py \
    --candidate-sha "${SHA_OTHER}" \
    --evidence "$TMP_MERGE" \
    --skip-github-provenance

# 13) frontend SHA mismatch
write_pass_evidence "$TMP_MERGE" "${SHA_CANDIDATE}"
python3 - <<PY
import json, pathlib
p = pathlib.Path("${TMP_MERGE}")
data = json.loads(p.read_text())
data["staging_certification"]["staging_frontend_sha"] = "${SHA_OTHER}"
p.write_text(json.dumps(data, indent=2) + "\n")
PY
merge_evidence_reject "frontend SHA mismatch" \
  python3 scripts/ci/validate_merge_release_evidence.py \
    --candidate-sha "${SHA_CANDIDATE}" \
    --evidence "$TMP_MERGE" \
    --skip-github-provenance

# 14) API SHA mismatch
write_pass_evidence "$TMP_MERGE" "${SHA_CANDIDATE}"
python3 - <<PY
import json, pathlib
p = pathlib.Path("${TMP_MERGE}")
data = json.loads(p.read_text())
data["staging_certification"]["staging_api_sha"] = "${SHA_OTHER}"
p.write_text(json.dumps(data, indent=2) + "\n")
PY
merge_evidence_reject "API SHA mismatch" \
  python3 scripts/ci/validate_merge_release_evidence.py \
    --candidate-sha "${SHA_CANDIDATE}" \
    --evidence "$TMP_MERGE" \
    --skip-github-provenance

# 15) missing staging deploy run id
write_pass_evidence "$TMP_MERGE" "${SHA_CANDIDATE}"
python3 - <<PY
import json, pathlib
p = pathlib.Path("${TMP_MERGE}")
data = json.loads(p.read_text())
del data["staging_certification"]["staging_deploy_workflow_run_id"]
p.write_text(json.dumps(data, indent=2) + "\n")
PY
merge_evidence_reject "missing staging deploy run id" \
  python3 scripts/ci/validate_merge_release_evidence.py \
    --candidate-sha "${SHA_CANDIDATE}" \
    --evidence "$TMP_MERGE" \
    --skip-github-provenance

# 16) missing provenance block
write_pass_evidence "$TMP_MERGE" "${SHA_CANDIDATE}"
python3 - <<PY
import json, pathlib
p = pathlib.Path("${TMP_MERGE}")
data = json.loads(p.read_text())
del data["provenance"]
p.write_text(json.dumps(data, indent=2) + "\n")
PY
merge_evidence_reject "missing provenance" \
  python3 scripts/ci/validate_merge_release_evidence.py \
    --candidate-sha "${SHA_CANDIDATE}" \
    --evidence "$TMP_MERGE" \
    --skip-github-provenance

# 17) identical deploy/cert run ids (ordinary CI masquerade)
write_pass_evidence "$TMP_MERGE" "${SHA_CANDIDATE}" "31810254648" "31810254648"
merge_evidence_reject "identical deploy and certification run ids" \
  python3 scripts/ci/validate_merge_release_evidence.py \
    --candidate-sha "${SHA_CANDIDATE}" \
    --evidence "$TMP_MERGE" \
    --skip-github-provenance \
    --current-run-id "31810254648"

# 18) PASS + exact SHAs + provenance accepts (offline)
write_pass_evidence "$TMP_MERGE" "${SHA_CANDIDATE}"
merge_evidence_accept "PASS with aligned SHAs and provenance" \
  python3 scripts/ci/validate_merge_release_evidence.py \
    --candidate-sha "${SHA_CANDIDATE}" \
    --evidence "$TMP_MERGE" \
    --skip-github-provenance

# 19) validation does not mutate evidence file
write_pass_evidence "$TMP_MERGE" "${SHA_CANDIDATE}"
BEFORE="$(sha256sum "$TMP_MERGE" | awk '{print $1}')"
python3 scripts/ci/validate_merge_release_evidence.py \
  --candidate-sha "${SHA_CANDIDATE}" \
  --evidence "$TMP_MERGE" \
  --skip-github-provenance >/tmp/merge-immutable.txt 2>&1
AFTER="$(sha256sum "$TMP_MERGE" | awk '{print $1}')"
if [[ "$BEFORE" == "$AFTER" ]]; then
  ok "merge evidence validation is read-only (sha256 unchanged)"
else
  bad "merge evidence validation must not mutate evidence file"
fi

# 20) validation must not create or mutate tracked merge evidence path
write_pass_evidence "$TMP_MERGE" "${SHA_CANDIDATE}"
TRACKED="infra/merge-release-evidence.json"
if [[ -f "$TRACKED" ]]; then
  TRACKED_BEFORE="$(sha256sum "$TRACKED" | awk '{print $1}')"
else
  TRACKED_BEFORE=""
fi
python3 scripts/ci/validate_merge_release_evidence.py \
  --candidate-sha "${SHA_CANDIDATE}" \
  --evidence "$TMP_MERGE" \
  --skip-github-provenance >/tmp/merge-tracked.txt 2>&1
if [[ -f "$TRACKED" ]]; then
  TRACKED_AFTER="$(sha256sum "$TRACKED" | awk '{print $1}')"
  if [[ "$TRACKED_BEFORE" == "$TRACKED_AFTER" ]]; then
    ok "validation does not mutate tracked infra/merge-release-evidence.json"
  else
    bad "validation must not mutate tracked infra/merge-release-evidence.json"
  fi
elif [[ -z "$TRACKED_BEFORE" ]]; then
  ok "validation does not create infra/merge-release-evidence.json"
else
  bad "validation must not delete infra/merge-release-evidence.json"
fi

# 21) bind-merge-release-evidence.py must not exist
if [[ ! -f scripts/ci/bind-merge-release-evidence.py ]]; then
  ok "bind-merge-release-evidence.py removed"
else
  bad "bind-merge-release-evidence.py must be deleted (RELCTRL-02)"
fi

# 22) governance scope detector fail-closed cases
if python3 scripts/ci/detect_merge_evidence_scope.py --paths docs/ops/production-release-control.md \
  | grep -qi 'governance-only'; then
  ok "scope detector exempts docs-only changes"
else
  bad "scope detector should exempt docs-only changes"
fi

if python3 scripts/ci/detect_merge_evidence_scope.py --paths apps/customer/src/page.tsx \
  | grep -qi 'merge evidence required'; then
  ok "scope detector requires evidence for apps/** changes"
else
  bad "scope detector should require evidence for apps/** changes"
fi

if python3 scripts/ci/detect_merge_evidence_scope.py --paths services/api/app/main.py \
  | grep -qi 'merge evidence required'; then
  ok "scope detector requires evidence for services runtime changes"
else
  bad "scope detector should require evidence for services runtime changes"
fi

if python3 scripts/ci/detect_merge_evidence_scope.py --paths services/api/tests/test_foo.py \
  | grep -qi 'governance-only'; then
  ok "scope detector exempts services/api/tests/** only changes"
else
  bad "scope detector should exempt services/api/tests/** only changes"
fi

if python3 scripts/ci/detect_merge_evidence_scope.py \
  --paths docs/ops/production-release-control.md apps/customer/x.tsx \
  | grep -qi 'merge evidence required'; then
  ok "scope detector requires evidence when runtime paths mixed with docs"
else
  bad "scope detector must not exempt mixed runtime + governance changes"
fi

if python3 scripts/ci/detect_merge_evidence_scope.py --paths scripts/qa/gate-status.mjs \
  | grep -qi 'governance-only'; then
  ok "scope detector exempts scripts/qa/** changes"
else
  bad "scope detector should exempt scripts/qa/** changes"
fi

if python3 scripts/ci/detect_merge_evidence_scope.py --paths infra/staging/docker-compose.yml \
  | grep -qi 'merge evidence required'; then
  ok "scope detector requires evidence for infra deployment config"
else
  bad "scope detector should require evidence for infra deployment config"
fi

# 23+) RELCTRL-03 artifact-native merge gate
SHA_PARENT="dddddddddddddddddddddddddddddddddddddddd"
SHA_CHILD="cccccccccccccccccccccccccccccccccccccccc"
SHA_MASTER="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
FIXTURE_PASS="scripts/ci/fixtures/staging-certification-gate/pass"

artifact_gate_reject() {
  local label="$1"
  shift
  set +e
  "$@" >/tmp/artifact-gate-reject.txt 2>&1
  local rc=$?
  set -e
  if [[ "$rc" -ne 0 ]]; then
    ok "artifact gate rejects: $label"
  else
    bad "artifact gate should reject: $label"
    cat /tmp/artifact-gate-reject.txt || true
  fi
}

artifact_gate_accept() {
  local label="$1"
  shift
  if "$@" >/tmp/artifact-gate-accept.txt 2>&1; then
    ok "artifact gate accepts: $label"
  else
    bad "artifact gate should accept: $label"
    cat /tmp/artifact-gate-accept.txt || true
  fi
}

artifact_gate_accept "exact SHA + deploy + certification fixture" \
  python3 scripts/ci/verify_staging_certification_gate.py \
    --candidate-sha "${SHA_CANDIDATE}" \
    --artifact-fixture-dir "${FIXTURE_PASS}"

artifact_gate_reject "child SHA after certification commit (parent artifact)" \
  python3 scripts/ci/verify_staging_certification_gate.py \
    --candidate-sha "${SHA_CHILD}" \
    --artifact-fixture-dir "${FIXTURE_PASS}"

TMP_FIXTURE="$(mktemp -d)"
cp -a "${FIXTURE_PASS}/." "${TMP_FIXTURE}/"
python3 - <<PY
import json, pathlib
root = pathlib.Path("${TMP_FIXTURE}")
for name in ("certification_runs.json", "certification_run.json", "deploy_runs.json", "deploy_run.json"):
    p = root / name
    data = json.loads(p.read_text())
    if isinstance(data, list):
        for item in data:
            item["head_sha"] = "${SHA_MASTER}"
    else:
        data["head_sha"] = "${SHA_MASTER}"
    p.write_text(json.dumps(data, indent=2) + "\\n")
art = json.loads((root / "artifact-9001.json").read_text())
art["candidate_sha"] = "${SHA_MASTER}"
art["staging_branch_sha"] = "${SHA_MASTER}"
art["staging_frontend_sha"] = "${SHA_MASTER}"
art["staging_api_sha"] = "${SHA_MASTER}"
(root / "artifact-9001.json").write_text(json.dumps(art, indent=2) + "\\n")
PY
artifact_gate_reject "master certification does not certify feature PR SHA" \
  python3 scripts/ci/verify_staging_certification_gate.py \
    --candidate-sha "${SHA_CANDIDATE}" \
    --artifact-fixture-dir "${TMP_FIXTURE}"
rm -rf "${TMP_FIXTURE}"

TMP_FIXTURE="$(mktemp -d)"
cp -a "${FIXTURE_PASS}/." "${TMP_FIXTURE}/"
python3 - <<PY
import json, pathlib
root = pathlib.Path("${TMP_FIXTURE}")
run = json.loads((root / "certification_run.json").read_text())
run["path"] = ".github/workflows/ci.yml"
(root / "certification_run.json").write_text(json.dumps(run, indent=2) + "\\n")
runs = json.loads((root / "certification_runs.json").read_text())
runs[0]["path"] = ".github/workflows/ci.yml"
(root / "certification_runs.json").write_text(json.dumps(runs, indent=2) + "\\n")
PY
artifact_gate_reject "ordinary CI workflow path rejected as certification" \
  python3 scripts/ci/verify_staging_certification_gate.py \
    --candidate-sha "${SHA_CANDIDATE}" \
    --artifact-fixture-dir "${TMP_FIXTURE}"
rm -rf "${TMP_FIXTURE}"

TMP_FIXTURE="$(mktemp -d)"
cp -a "${FIXTURE_PASS}/." "${TMP_FIXTURE}/"
python3 - <<PY
import json, pathlib
root = pathlib.Path("${TMP_FIXTURE}")
art = json.loads((root / "artifact-9001.json").read_text())
art["staging_deploy_workflow_run_id"] = art["certification_workflow_run_id"]
(root / "artifact-9001.json").write_text(json.dumps(art, indent=2) + "\\n")
PY
artifact_gate_reject "identical deploy and certification run ids" \
  python3 scripts/ci/verify_staging_certification_gate.py \
    --candidate-sha "${SHA_CANDIDATE}" \
    --artifact-fixture-dir "${TMP_FIXTURE}"
rm -rf "${TMP_FIXTURE}"

TMP_FIXTURE="$(mktemp -d)"
cp -a "${FIXTURE_PASS}/." "${TMP_FIXTURE}/"
python3 - <<PY
import json, pathlib
root = pathlib.Path("${TMP_FIXTURE}")
art = json.loads((root / "artifact-9001.json").read_text())
art["result"] = "CERTIFIABLE_AFTER_INTEGRATION"
(root / "artifact-9001.json").write_text(json.dumps(art, indent=2) + "\\n")
PY
artifact_gate_reject "non-PASS certificate rejected" \
  python3 scripts/ci/verify_staging_certification_gate.py \
    --candidate-sha "${SHA_CANDIDATE}" \
    --artifact-fixture-dir "${TMP_FIXTURE}"
rm -rf "${TMP_FIXTURE}"

TMP_FIXTURE="$(mktemp -d)"
cp -a "${FIXTURE_PASS}/." "${TMP_FIXTURE}/"
echo '[]' > "${TMP_FIXTURE}/artifacts.json"
artifact_gate_reject "missing certification artifact" \
  python3 scripts/ci/verify_staging_certification_gate.py \
    --candidate-sha "${SHA_CANDIDATE}" \
    --artifact-fixture-dir "${TMP_FIXTURE}"
rm -rf "${TMP_FIXTURE}"

if [[ ! -f infra/merge-release-evidence.json ]]; then
  ok "runtime PRs do not require checked-in infra/merge-release-evidence.json"
else
  bad "checked-in infra/merge-release-evidence.json must not be required"
fi

if ! grep -q 'verify_staging_certification_gate.py' .github/workflows/ci.yml; then
  bad "ci.yml must invoke verify_staging_certification_gate.py"
else
  ok "ci.yml uses artifact-native verify_staging_certification_gate.py"
fi

if grep -q 'infra/merge-release-evidence.json' .github/workflows/ci.yml; then
  bad "ci.yml merge gate must not require checked-in merge-release-evidence.json"
else
  ok "ci.yml merge gate does not require checked-in merge-release-evidence.json"
fi

# SHA self-reference: certify parent X, child commit Y must not inherit X artifact
artifact_gate_reject "certify X then commit Y — artifact for X must not certify Y" \
  python3 scripts/ci/verify_staging_certification_gate.py \
    --candidate-sha "${SHA_CHILD}" \
    --artifact-file "${FIXTURE_PASS}/artifact-9001.json"

rm -f "$TMP_MERGE"

echo "==> summary: pass=$pass fail=$fail"
if [[ "$fail" -gt 0 ]]; then
  exit 1
fi
