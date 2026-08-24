#!/usr/bin/env bash
#
# release-certify.sh — independent release-certification orchestrator.
#
# Writes per-gate JSON fragments into an isolated evidence namespace:
#   scripts/qa/evidence/<sha>/<environment>/<runId>/gate-*.json
#
# Status vocabulary (no false green):
#   PASS | FAIL | BLOCKED_EXTERNAL | NOT_RUN | UNKNOWN | MEASUREMENT_UNSTABLE
#
# Modes:
#   local-development     — report-only (LOCAL_DEVELOPMENT_REPORT); never a release cert
#   ci                    — CI baseline; strict exit
#   integrated-staging    — strict staging promotion; strict exit
#   production-readiness  — strictest; strict exit
#
# Usage:
#   bash scripts/qa/release-certify.sh --mode local-development
#   bash scripts/qa/release-certify.sh --mode ci --layer static
#   bash scripts/qa/release-certify.sh --mode integrated-staging --environment staging
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVIDENCE_ROOT="${REPO_ROOT}/scripts/qa/evidence"
LAYER="all"
SKIP_E2E=0
SKIP_RLS=0
MODE="local-development"
ENVIRONMENT="local"
E2E_BASE_URL="${E2E_BASE_URL:-http://localhost:3000}"
RUN_ID="${CERT_RUN_ID:-}"
E2E_DEPS_READY=0

log() { printf '==> [%s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }

sanitize_log() {
  # Bound + redact obvious secrets from command output before storing in evidence.
  local raw="$1"
  python3 - "$raw" <<'PY'
import re, sys
text = sys.argv[1] if len(sys.argv) > 1 else ""
patterns = [
    (r"(?i)(authorization:\s*bearer\s+)(\S+)", r"\1[REDACTED]"),
    (r"(?i)(api[_-]?key|token|secret|password|service_role)([\"'=\s:]+)(\S+)", r"\1\2[REDACTED]"),
    (r"ghp_[A-Za-z0-9]{20,}", "[REDACTED_GH_TOKEN]"),
    (r"sk_[A-Za-z0-9]{20,}", "[REDACTED_SK]"),
]
for pat, repl in patterns:
    text = re.sub(pat, repl, text)
# Keep last 1500 chars for failure evidence.
print(text[-1500:])
PY
}

write_gate() {
  local id="$1" layer="$2" status="$3" detail="${4:-}"
  local duration_ms="${5:-0}"
  local cmd_rc="${6:-}"
  mkdir -p "$EVIDENCE_DIR"
  GATE_ID="$id" GATE_LAYER="$layer" GATE_STATUS="$status" GATE_DETAIL="$detail" \
  GATE_MS="$duration_ms" GATE_DIR="$EVIDENCE_DIR" GATE_SHA="$SHA" \
  GATE_ENV="$ENVIRONMENT" GATE_RUN="$RUN_ID" GATE_MODE="$MODE" GATE_RC="$cmd_rc" \
    python3 - <<'PY'
import json, os, pathlib
payload = {
    "id": os.environ["GATE_ID"],
    "layer": os.environ["GATE_LAYER"],
    "status": os.environ["GATE_STATUS"],
    "detail": os.environ.get("GATE_DETAIL", ""),
    "duration_ms": int(os.environ.get("GATE_MS", "0") or "0"),
    "sha": os.environ.get("GATE_SHA", ""),
    "environment": os.environ.get("GATE_ENV", ""),
    "run_id": os.environ.get("GATE_RUN", ""),
    "mode": os.environ.get("GATE_MODE", ""),
}
rc = os.environ.get("GATE_RC", "")
if rc != "":
    try:
        payload["return_code"] = int(rc)
    except ValueError:
        payload["return_code"] = rc
p = pathlib.Path(os.environ["GATE_DIR"]) / f"gate-{os.environ['GATE_ID']}.json"
p.write_text(json.dumps(payload, indent=2))
PY
}

# run_timed writes duration to stdout and stores sanitized log in a file path
# passed by the caller — avoids Bash subshell losing LAST_CMD_LOG.
# Usage: run_timed <log_out_var_name> <cmd...>
# Sets global _RUN_TIMED_MS and _RUN_TIMED_RC; writes sanitized log to named file.
run_timed() {
  local log_out_file="$1"
  shift
  local log_file start end rc=0
  log_file="$(mktemp)"
  start=$(date +%s%3N 2>/dev/null || python3 -c 'import time;print(int(time.time()*1000))')
  set +e
  "$@" >"$log_file" 2>&1
  rc=$?
  set -e
  end=$(date +%s%3N 2>/dev/null || python3 -c 'import time;print(int(time.time()*1000))')
  local raw
  raw="$(tail -c 4000 "$log_file" 2>/dev/null || true)"
  sanitize_log "$raw" >"$log_out_file"
  rm -f "$log_file"
  _RUN_TIMED_MS=$((end - start))
  _RUN_TIMED_RC=$rc
  return $rc
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --layer) LAYER="${2:-all}"; shift 2 ;;
    --skip-e2e) SKIP_E2E=1; shift ;;
    --skip-rls) SKIP_RLS=1; shift ;;
    --mode) MODE="${2:-local-development}"; shift 2 ;;
    --environment) ENVIRONMENT="${2:-local}"; shift 2 ;;
    --run-id) RUN_ID="${2:-}"; shift 2 ;;
    --evidence-root) EVIDENCE_ROOT="${2:-$EVIDENCE_ROOT}"; shift 2 ;;
    -h|--help)
      sed -n '2,22p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
  esac
done

# Map legacy environment-only invocations.
case "$MODE" in
  local|local-report|report-only) MODE="local-development" ;;
  staging) MODE="integrated-staging" ;;
  production|prod) MODE="production-readiness" ;;
esac

# Source toolchain for non-login shells.
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
# shellcheck disable=SC1091
[[ -s "$NVM_DIR/nvm.sh" ]] && . "$NVM_DIR/nvm.sh"
export PATH="${HOME}/.local/bin:${PATH}"

SHA="$(git -C "$REPO_ROOT" rev-parse HEAD)"
BRANCH="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD)"
if [[ -z "$RUN_ID" ]]; then
  RUN_ID="${GITHUB_RUN_ID:-local}-$(date -u +%Y%m%dT%H%M%SZ)"
fi

EVIDENCE_DIR="${EVIDENCE_ROOT}/${SHA}/${ENVIRONMENT}/${RUN_ID}"
mkdir -p "$EVIDENCE_DIR"
# Wipe any pre-existing gate fragments in THIS namespace only.
find "$EVIDENCE_DIR" -maxdepth 1 -type f -name 'gate-*.json' -delete 2>/dev/null || true

# Export for Playwright strict synthetic contract.
export CERTIFICATION_MODE="$MODE"
export CERT_EVIDENCE_DIR="$EVIDENCE_DIR"
export CERT_SHA="$SHA"
export CERT_RUN_ID="$RUN_ID"

log "Release certification — SHA=${SHA:0:12} mode=${MODE} env=${ENVIRONMENT} run=${RUN_ID}"
log "Evidence namespace: ${EVIDENCE_DIR}"

run_gate_cmd() {
  local id="$1" layer="$2" label="$3"
  shift 3
  log "$label"
  local log_out ms rc=0 detail="$label"
  log_out="$(mktemp)"
  set +e
  run_timed "$log_out" "$@"
  rc=$_RUN_TIMED_RC
  ms=$_RUN_TIMED_MS
  set -e
  if [[ $rc -ne 0 ]]; then
    detail="${label}: rc=${rc}: $(cat "$log_out")"
  fi
  rm -f "$log_out"
  write_gate "$id" "$layer" "$([[ $rc -eq 0 ]] && echo PASS || echo FAIL)" "$detail" "$ms" "$rc"
  return 0
}

# ── Layer 1: Static ──────────────────────────────────────────────────────────

run_static_lint() {
  run_gate_cmd "lint" "static" "L1 lint" bash -c "cd '$REPO_ROOT' && pnpm lint"
}

run_static_typecheck() {
  run_gate_cmd "typecheck" "static" "L1 typecheck" bash -c "cd '$REPO_ROOT' && pnpm typecheck"
}

run_static_unit() {
  run_gate_cmd "unit-js" "static" "L1 unit tests (JS)" bash -c "cd '$REPO_ROOT' && pnpm test"
}

run_static_api_unit() {
  run_gate_cmd "unit-api" "static" "L1 API unit tests" bash -c "cd '$REPO_ROOT/services/api' && uv run pytest -q --ignore=tests/rls --ignore=tests/evals"
}

run_static_i18n() {
  run_gate_cmd "i18n-parity" "static" "L1 i18n parity" bash -c "cd '$REPO_ROOT' && node scripts/ci/i18n-lint.mjs --self-test && node scripts/ci/i18n-lint.mjs"
}

run_static_migration() {
  log "L1 migration replay"
  if ! command -v psql >/dev/null 2>&1; then
    write_gate "migration-replay" "database" "BLOCKED_EXTERNAL" "psql not available"
    return 0
  fi
  if [[ -z "${PGHOST:-}${DATABASE_URL:-}${SUPABASE_DB_URL:-}" ]]; then
    write_gate "migration-replay" "database" "BLOCKED_EXTERNAL" "requires Postgres (CI service or local PGHOST/SUPABASE_DB_URL)"
    return 0
  fi
  local log_out ms rc=0
  log_out="$(mktemp)"
  set +e
  run_timed "$log_out" bash -c "cd '$REPO_ROOT' && bash scripts/ci/migration-replay.sh"
  rc=$_RUN_TIMED_RC
  ms=$_RUN_TIMED_MS
  set -e
  if [[ $rc -eq 0 ]]; then
    write_gate "migration-replay" "database" "PASS" "migration-replay.sh" "$ms" "$rc"
  else
    write_gate "migration-replay" "database" "FAIL" "migration-replay.sh: $(cat "$log_out")" "$ms" "$rc"
  fi
  rm -f "$log_out"
}

run_static_rls() {
  log "L1 RLS isolation"
  if [[ "$SKIP_RLS" -eq 1 ]]; then
    write_gate "rls-isolation" "security" "NOT_RUN" "--skip-rls"
    return 0
  fi
  if ! command -v supabase >/dev/null 2>&1; then
    write_gate "rls-isolation" "security" "BLOCKED_EXTERNAL" "supabase CLI not available"
    return 0
  fi
  if ! command -v psql >/dev/null 2>&1; then
    write_gate "rls-isolation" "security" "BLOCKED_EXTERNAL" "psql not available for RLS provisioner"
    return 0
  fi

  local setup_log setup_rc=0 test_log test_rc=0 ms=0
  setup_log="$(mktemp)"
  test_log="$(mktemp)"

  # Phase A — setup/provisioning (failure => FAIL, not BLOCKED_EXTERNAL)
  export SEND_SMS_HOOK_SECRET="${SEND_SMS_HOOK_SECRET:-v1,whsec_ci}"
  export SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID="${SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID:-ci}"
  export SUPABASE_AUTH_EXTERNAL_GOOGLE_SECRET="${SUPABASE_AUTH_EXTERNAL_GOOGLE_SECRET:-ci}"
  export SUPABASE_AUTH_EXTERNAL_APPLE_SECRET="${SUPABASE_AUTH_EXTERNAL_APPLE_SECRET:-ci}"
  export SUPABASE_DB_URL="${SUPABASE_DB_URL:-postgresql://postgres:postgres@127.0.0.1:54322/postgres}"
  export SUPABASE_URL="${SUPABASE_URL:-https://example.supabase.co}"
  export SUPABASE_SERVICE_ROLE_KEY="${SUPABASE_SERVICE_ROLE_KEY:-test}"
  export SUPABASE_ANON_KEY="${SUPABASE_ANON_KEY:-test}"

  set +e
  run_timed "$setup_log" bash -c "
    cd '$REPO_ROOT' &&
    supabase db start &&
    supabase db reset --no-seed &&
    psql \"\$SUPABASE_DB_URL\" -v ON_ERROR_STOP=1 -f scripts/ci/provision-rls-tester.sql
  "
  setup_rc=$_RUN_TIMED_RC
  ms=$_RUN_TIMED_MS
  set -e

  if [[ $setup_rc -ne 0 ]]; then
    write_gate "rls-isolation" "security" "FAIL" \
      "RLS setup/provisioning defect: $(cat "$setup_log")" "$ms" "$setup_rc"
    rm -f "$setup_log" "$test_log"
    return 0
  fi

  # Phase B — assertion suite (failure => FAIL)
  set +e
  run_timed "$test_log" bash -c "
    cd '$REPO_ROOT/services/api' &&
    uv run pytest tests/rls -q
  "
  test_rc=$_RUN_TIMED_RC
  ms=$((ms + _RUN_TIMED_MS))
  set -e

  if [[ $test_rc -eq 0 ]]; then
    write_gate "rls-isolation" "security" "PASS" "pytest tests/rls" "$ms" "$test_rc"
  else
    write_gate "rls-isolation" "security" "FAIL" \
      "RLS assertions failed: $(cat "$test_log")" "$ms" "$test_rc"
  fi
  rm -f "$setup_log" "$test_log"
}

run_static_deps() {
  run_gate_cmd "deps-audit" "security" "L1 dependency audit" \
    node "${REPO_ROOT}/scripts/qa/run-deps-audit.mjs"
}

run_bundle_budgets() {
  log "L1 bundle budgets"
  if [[ ! -f "${REPO_ROOT}/scripts/ci/bundle-guard.mjs" ]]; then
    write_gate "perf-bundle-budgets" "performance" "NOT_RUN" "bundle-guard.mjs missing"
    return 0
  fi
  # Bundle guard typically needs build artifacts; mark BLOCKED_EXTERNAL when absent.
  if [[ ! -d "${REPO_ROOT}/apps/customer/.next" ]]; then
    write_gate "perf-bundle-budgets" "performance" "BLOCKED_EXTERNAL" "customer .next build artifacts absent"
    return 0
  fi
  run_gate_cmd "perf-bundle-budgets" "performance" "L1 bundle budgets" \
    bash -c "cd '$REPO_ROOT' && node scripts/ci/bundle-guard.mjs"
}

# ── Layer 2: Integration ─────────────────────────────────────────────────────

run_integration_from_manifest() {
  local manifest="${REPO_ROOT}/scripts/qa/integration-manifest.json"
  if [[ ! -f "$manifest" ]]; then
    write_gate "int-manifest" "integration" "FAIL" "integration-manifest.json missing"
    return 0
  fi
  # shellcheck disable=SC2207
  local domains
  domains="$(python3 - "$manifest" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1]))
for domain, meta in doc.get("domains", {}).items():
    if domain == "seller_boundaries":
        # RLS covered by rls-isolation gate; skip nested rls here.
        tests = [t for t in meta.get("tests", []) if not t.endswith("/rls") and "tests/rls" not in t]
    else:
        tests = meta.get("tests", [])
    # Remap repo-relative paths to pytest paths under services/api
    rel = []
    for t in tests:
        if t.startswith("services/api/"):
            rel.append(t[len("services/api/"):])
        else:
            rel.append(t)
    if not rel:
        continue
    required = "1" if meta.get("required", False) else "0"
    print(f"{domain}|{required}|{' '.join(rel)}")
PY
)"
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    local domain required tests
    domain="${line%%|*}"
    rest="${line#*|}"
    required="${rest%%|*}"
    tests="${rest#*|}"
    local gate_id="int-${domain//_/-}"
    # Normalize known aliases to required-gates.json IDs
    case "$domain" in
      api_health) gate_id="int-authz" ;;
      order_states) gate_id="int-orders" ;;
      inventory_reservations) gate_id="int-inventory" ;;
      seller_boundaries) gate_id="int-seller-boundaries" ;;
    esac
    if [[ "$required" != "1" && "$MODE" == "local-development" ]]; then
      # Still run but optional.
      :
    fi
    run_gate_cmd "$gate_id" "integration" "L2 integration: ${domain}" \
      bash -c "cd '$REPO_ROOT/services/api' && uv run pytest ${tests} -q"
  done <<< "$domains"
}

# ── Layer 3: Browser E2E ─────────────────────────────────────────────────────

server_reachable() {
  curl -sf --max-time 5 "${E2E_BASE_URL}/en/health" >/dev/null 2>&1
}

ensure_e2e_deps() {
  if [[ "$E2E_DEPS_READY" -eq 1 ]]; then
    return 0
  fi
  log "Installing E2E deps once (npm ci, frozen lockfile)"
  if [[ ! -f "${REPO_ROOT}/e2e/package-lock.json" ]]; then
    return 1
  fi
  local log_out
  log_out="$(mktemp)"
  set +e
  run_timed "$log_out" bash -c "cd '$REPO_ROOT/e2e' && npm ci"
  local rc=$_RUN_TIMED_RC
  set -e
  if [[ $rc -ne 0 ]]; then
    log "npm ci failed: $(cat "$log_out")"
    rm -f "$log_out"
    return 1
  fi
  rm -f "$log_out"
  E2E_DEPS_READY=1
  return 0
}

run_e2e_suite() {
  local spec="$1" gate_id="$2" project="${3:-mobile-390}"
  log "L3 E2E: ${gate_id}"
  if [[ "$SKIP_E2E" -eq 1 ]]; then
    write_gate "$gate_id" "ux" "NOT_RUN" "--skip-e2e"
    return 0
  fi
  if ! server_reachable; then
    write_gate "$gate_id" "ux" "BLOCKED_EXTERNAL" "customer app not reachable at ${E2E_BASE_URL}"
    return 0
  fi
  if ! ensure_e2e_deps; then
    write_gate "$gate_id" "ux" "FAIL" "e2e frozen install failed (package-lock.json / npm ci)"
    return 0
  fi
  local log_out ms rc=0
  log_out="$(mktemp)"
  set +e
  run_timed "$log_out" bash -c "
    cd '$REPO_ROOT/e2e' &&
    E2E_BASE_URL='${E2E_BASE_URL}' E2E_THROTTLE=0 \
      CERTIFICATION_MODE='${MODE}' \
      PW_CHROMIUM_PATH='${PW_CHROMIUM_PATH:-}' \
      npx playwright test '${spec}' --reporter=list --project='${project}'
  "
  rc=$_RUN_TIMED_RC
  ms=$_RUN_TIMED_MS
  set -e
  # Prefer MEASUREMENT_UNSTABLE when perf suite annotates instability via marker file.
  if [[ "$gate_id" == "perf-web-vitals-smoke" && -f "${REPO_ROOT}/e2e/results/measurement-unstable.json" ]]; then
    write_gate "$gate_id" "performance" "MEASUREMENT_UNSTABLE" \
      "noisy vitals: $(cat "${REPO_ROOT}/e2e/results/measurement-unstable.json")" "$ms" "$rc"
  elif [[ $rc -eq 0 ]]; then
    write_gate "$gate_id" "ux" "PASS" "playwright ${spec}" "$ms" "$rc"
  else
    write_gate "$gate_id" "ux" "FAIL" "playwright ${spec}: $(cat "$log_out")" "$ms" "$rc"
  fi
  rm -f "$log_out"
}

run_e2e() {
  run_e2e_suite "specs/browse-journey.spec.ts" "e2e-browse-journey"
  # mobile-layout.spec.ts is RESPONSIVE_ALL_VIEWPORTS (fixtures/spec-classification.ts):
  # the CI E2E workflow runs it once per certification viewport (5 projects). This
  # gate exercises it on the canonical mobile-390 project only — a single-viewport
  # smoke, not the full cross-viewport certification.
  run_e2e_suite "specs/mobile-layout.spec.ts" "e2e-mobile-layout"
  run_e2e_suite "specs/data-quality.spec.ts" "e2e-data-quality"
  run_e2e_suite "specs/ux-surfaces.spec.ts" "e2e-ux-surfaces"
  run_e2e_suite "specs/a11y-smoke.spec.ts" "a11y-axe-smoke"
  # performance-smoke.spec.ts is NETWORK_THROTTLED_ONLY, assigned only to the
  # fast-3g project's testMatch — no other project would even discover it.
  run_e2e_suite "specs/performance-smoke.spec.ts" "perf-web-vitals-smoke" "fast-3g"
}

run_payments_sandbox() {
  log "Payments sandbox proof"
  if [[ -z "${LENCO_API_TOKEN:-}" || "${LENCO_ENV:-}" != "sandbox" ]]; then
    write_gate "payment-sandbox" "payments" "BLOCKED_EXTERNAL" "LENCO_ENV=sandbox + LENCO_API_TOKEN required (F9b founder gate)"
    return 0
  fi
  run_gate_cmd "payment-sandbox" "payments" "Payments sandbox" \
    bash -c "cd '$REPO_ROOT/services/api' && uv run python ../../scripts/drills/lenco_sandbox_money_drill.py --mode auto"
}

run_recovery() {
  log "Recovery gates (dry-run vs restore proof)"

  # BACKUP_SCRIPT_DRY_RUN — plan/dry-run only; cannot satisfy restore certification.
  if [[ -f "${REPO_ROOT}/scripts/ops/backup_drill.sh" ]]; then
    local log_out ms rc=0
    log_out="$(mktemp)"
    set +e
    run_timed "$log_out" bash -c "bash '${REPO_ROOT}/scripts/ops/backup_drill.sh' --dry-run"
    rc=$_RUN_TIMED_RC
    ms=$_RUN_TIMED_MS
    set -e
    if [[ $rc -eq 0 ]]; then
      write_gate "backup-script-dry-run" "recovery" "PASS" "backup_drill.sh --dry-run (not restore proof)" "$ms" "$rc"
    else
      write_gate "backup-script-dry-run" "recovery" "FAIL" "dry-run failed: $(cat "$log_out")" "$ms" "$rc"
    fi
    rm -f "$log_out"
  else
    write_gate "backup-script-dry-run" "recovery" "NOT_RUN" "backup_drill.sh missing"
  fi

  # RESTORE_DRILL_PROOF — real restore drill; dry-run cannot satisfy this gate.
  if [[ "${CERT_RUN_RESTORE_DRILL:-0}" == "1" && -f "${REPO_ROOT}/infra/scripts/restore-drill.sh" ]]; then
    local log_out ms rc=0
    log_out="$(mktemp)"
    set +e
    run_timed "$log_out" bash -c "bash '${REPO_ROOT}/infra/scripts/restore-drill.sh'"
    rc=$_RUN_TIMED_RC
    ms=$_RUN_TIMED_MS
    set -e
    if [[ $rc -eq 0 ]]; then
      write_gate "restore-drill-proof" "recovery" "PASS" "infra/scripts/restore-drill.sh" "$ms" "$rc"
    else
      write_gate "restore-drill-proof" "recovery" "FAIL" "restore drill failed: $(cat "$log_out")" "$ms" "$rc"
    fi
    rm -f "$log_out"
  elif [[ -f "${REPO_ROOT}/scripts/ops/backup_drill.sh" && "${CERT_RUN_RESTORE_DRILL:-0}" == "1" ]]; then
    run_gate_cmd "restore-drill-proof" "recovery" "Restore drill (--local)" \
      bash -c "bash '${REPO_ROOT}/scripts/ops/backup_drill.sh' --local"
  else
    write_gate "restore-drill-proof" "recovery" "BLOCKED_EXTERNAL" \
      "set CERT_RUN_RESTORE_DRILL=1 to execute restore proof (dry-run cannot satisfy)"
  fi
}

run_deploy_identity() {
  log "Exact deployment identity"
  if [[ "$MODE" != "integrated-staging" && "$MODE" != "production-readiness" ]]; then
    write_gate "deploy-identity" "deploy" "NOT_RUN" "identity proof required only for strict staging/prod modes"
    return 0
  fi

  local proof_dir="${STAGING_PROOF_DIR:-}"
  local project_id="${STAGING_SUPABASE_PROJECT_ID:-}"
  local candidate="${CANDIDATE_SHA:-$SHA}"
  local migrate_result="${MIGRATE_RESULT:-success}"
  local fingerprint="${STAGING_API_FINGERPRINT:-${proof_dir}/api-fingerprint.json}"

  if [[ -z "$proof_dir" || ! -d "$proof_dir" ]]; then
    write_gate "deploy-identity" "deploy" "FAIL" \
      "STAGING_PROOF_DIR missing — preview evidence for customer/vendor/admin required"
    return 0
  fi
  if [[ -z "$project_id" ]]; then
    write_gate "deploy-identity" "deploy" "FAIL" "STAGING_SUPABASE_PROJECT_ID missing"
    return 0
  fi
  if [[ ! -f "$fingerprint" ]]; then
    write_gate "deploy-identity" "deploy" "FAIL" "API fingerprint JSON missing at ${fingerprint}"
    return 0
  fi

  # Compatible migration tip: require migrate_result=success unless explicitly skipped.
  local log_out ms rc=0
  log_out="$(mktemp)"
  set +e
  run_timed "$log_out" python3 "${REPO_ROOT}/scripts/ci/validate_staging_proof.py" \
    --candidate-sha "$candidate" \
    --staging-supabase-project-id "$project_id" \
    --preview-dir "$proof_dir" \
    --fingerprint "$fingerprint" \
    --migrate-result "$migrate_result" \
    ${EXPECTED_IMAGE_TAG:+--expected-image-tag "$EXPECTED_IMAGE_TAG"}
  rc=$_RUN_TIMED_RC
  ms=$_RUN_TIMED_MS
  set -e
  if [[ $rc -eq 0 ]]; then
    write_gate "deploy-identity" "deploy" "PASS" \
      "candidate=${candidate:0:12} portals+api fingerprint+supabase project+migrate=${migrate_result}" "$ms" "$rc"
  else
    write_gate "deploy-identity" "deploy" "FAIL" "identity mismatch: $(cat "$log_out")" "$ms" "$rc"
  fi
  rm -f "$log_out"
}

run_qa_self_tests() {
  log "QA framework self-tests"
  run_gate_cmd "qa-self-test" "static" "QA self-tests" \
    bash -c "cd '$REPO_ROOT' && node --experimental-strip-types --test scripts/qa/self-test/*.test.mjs"
}

# ── Orchestrate ──────────────────────────────────────────────────────────────

case "$LAYER" in
  static)
    run_qa_self_tests
    run_static_lint
    run_static_typecheck
    run_static_unit
    run_static_api_unit
    run_static_i18n
    run_static_migration
    run_static_rls
    run_static_deps
    run_bundle_budgets
    ;;
  integration) run_integration_from_manifest ;;
  e2e) run_e2e ;;
  payments) run_payments_sandbox ;;
  recovery) run_recovery ;;
  identity) run_deploy_identity ;;
  self-test) run_qa_self_tests ;;
  all|*)
    run_qa_self_tests
    run_static_lint
    run_static_typecheck
    run_static_unit
    run_static_api_unit
    run_static_i18n
    run_static_migration
    run_static_rls
    run_static_deps
    run_bundle_budgets
    run_integration_from_manifest
    run_deploy_identity
    run_e2e
    run_payments_sandbox
    run_recovery
    ;;
esac

log "Collecting certificate"
set +e
node "${REPO_ROOT}/scripts/qa/collect-certificate.mjs" \
  --evidence-dir "$EVIDENCE_DIR" \
  --sha "$SHA" \
  --branch "$BRANCH" \
  --environment "$ENVIRONMENT" \
  --mode "$MODE" \
  --run-id "$RUN_ID"
collect_rc=$?
set -e

# Mirror certificate to stable path for artifact upload convenience.
mkdir -p "${EVIDENCE_ROOT}/latest"
cp -f "${EVIDENCE_DIR}/release-certificate.json" "${EVIDENCE_ROOT}/latest/" 2>/dev/null || true
cp -f "${EVIDENCE_DIR}/release-certificate.md" "${EVIDENCE_ROOT}/latest/" 2>/dev/null || true
printf '%s\n' "$EVIDENCE_DIR" > "${EVIDENCE_ROOT}/latest/namespace-path.txt"

exit "$collect_rc"
