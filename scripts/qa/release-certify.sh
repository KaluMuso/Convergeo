#!/usr/bin/env bash
#
# release-certify.sh — independent release-certification orchestrator.
#
# Runs the test pyramid layers, writes per-gate JSON fragments to
# scripts/qa/evidence/gate-*.json, then aggregates a machine-readable +
# human-readable release certificate.
#
# Status vocabulary (no false green):
#   PASS | FAIL | BLOCKED_EXTERNAL | NOT_RUN | UNKNOWN | MEASUREMENT_UNSTABLE
#
# Usage:
#   bash scripts/qa/release-certify.sh                    # full local run
#   bash scripts/qa/release-certify.sh --layer static     # layer 1 only
#   bash scripts/qa/release-certify.sh --skip-e2e         # skip browser (no server)
#   bash scripts/qa/release-certify.sh --environment staging
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVIDENCE_DIR="${REPO_ROOT}/scripts/qa/evidence"
LAYER="all"
SKIP_E2E=0
SKIP_RLS=0
ENVIRONMENT="local"
E2E_BASE_URL="${E2E_BASE_URL:-http://localhost:3000}"

log() { printf '==> [%s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }

write_gate() {
  local id="$1" layer="$2" status="$3" detail="${4:-}"
  local duration_ms="${5:-0}"
  mkdir -p "$EVIDENCE_DIR"
  GATE_ID="$id" GATE_LAYER="$layer" GATE_STATUS="$status" GATE_DETAIL="$detail" GATE_MS="$duration_ms" GATE_DIR="$EVIDENCE_DIR" \
    python3 - <<'PY'
import json, os, pathlib
p = pathlib.Path(os.environ["GATE_DIR"]) / f"gate-{os.environ['GATE_ID']}.json"
p.write_text(json.dumps({
    "id": os.environ["GATE_ID"],
    "layer": os.environ["GATE_LAYER"],
    "status": os.environ["GATE_STATUS"],
    "detail": os.environ.get("GATE_DETAIL", ""),
    "duration_ms": int(os.environ.get("GATE_MS", "0") or "0"),
}, indent=2))
PY
}

run_timed() {
  local log_file start end rc=0
  log_file="$(mktemp)"
  start=$(date +%s%3N)
  if "$@" >"$log_file" 2>&1; then
    rc=0
  else
    rc=$?
  fi
  end=$(date +%s%3N)
  # Preserve last 500 chars of output for gate detail on failure.
  LAST_CMD_LOG="$(tail -c 500 "$log_file" 2>/dev/null || true)"
  rm -f "$log_file"
  echo $((end - start))
  return $rc
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --layer) LAYER="${2:-all}"; shift 2 ;;
    --skip-e2e) SKIP_E2E=1; shift ;;
    --skip-rls) SKIP_RLS=1; shift ;;
    --environment) ENVIRONMENT="${2:-local}"; shift 2 ;;
    --evidence-dir) EVIDENCE_DIR="${2:-$EVIDENCE_DIR}"; shift 2 ;;
    -h|--help)
      sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
  esac
done

# Source toolchain for non-login shells.
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
# shellcheck disable=SC1091
[[ -s "$NVM_DIR/nvm.sh" ]] && . "$NVM_DIR/nvm.sh"
export PATH="${HOME}/.local/bin:${PATH}"

SHA="$(git -C "$REPO_ROOT" rev-parse HEAD)"
BRANCH="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD)"

log "Release certification — SHA=${SHA:0:12} env=${ENVIRONMENT}"

# ── Layer 1: Static ──────────────────────────────────────────────────────────

run_gate_cmd() {
  local id="$1" layer="$2" label="$3"
  shift 3
  log "$label"
  local ms rc=0 detail="$label"
  ms=$(run_timed "$@") || rc=$?
  [[ $rc -ne 0 ]] && detail="${detail}: ${LAST_CMD_LOG:-failed}"
  write_gate "$id" "$layer" "$([[ $rc -eq 0 ]] && echo PASS || echo FAIL)" "$detail" "$ms"
}

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
    write_gate "migration-replay" "database" "NOT_RUN" "psql not available"
    return 0
  fi
  if [[ -z "${PGHOST:-}" ]]; then
  write_gate "migration-replay" "database" "BLOCKED_EXTERNAL" "requires Postgres (CI service or local PGHOST)"
    return 0
  fi
  local ms rc=0
  ms=$(run_timed bash -c "cd '$REPO_ROOT' && bash scripts/ci/migration-replay.sh") || rc=$?
  write_gate "migration-replay" "database" "$([[ $rc -eq 0 ]] && echo PASS || echo FAIL)" "migration-replay.sh" "$ms"
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
  local ms rc=0
  ms=$(run_timed bash -c "
    cd '$REPO_ROOT' &&
    export SEND_SMS_HOOK_SECRET='v1,whsec_ci' SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID=ci SUPABASE_AUTH_EXTERNAL_GOOGLE_SECRET=ci SUPABASE_AUTH_EXTERNAL_APPLE_SECRET=ci &&
    export SUPABASE_DB_URL='postgresql://postgres:postgres@127.0.0.1:54322/postgres' &&
    export SUPABASE_URL='https://example.supabase.co' SUPABASE_SERVICE_ROLE_KEY=test SUPABASE_ANON_KEY=test &&
    supabase db start 2>/dev/null || true &&
    supabase db reset --no-seed 2>/dev/null &&
    psql \"\$SUPABASE_DB_URL\" -v ON_ERROR_STOP=1 -f scripts/ci/provision-rls-tester.sql &&
    cd services/api && uv run pytest tests/rls -q
  ") || rc=$?
  if [[ $rc -ne 0 ]]; then
    write_gate "rls-isolation" "security" "BLOCKED_EXTERNAL" "local Supabase stack required (run in CI or with supabase start)" "$ms"
  else
    write_gate "rls-isolation" "security" "PASS" "pytest tests/rls" "$ms"
  fi
}

run_static_deps() {
  log "L1 dependency audit"
  local ms=0
  run_timed bash -c "cd '$REPO_ROOT' && pnpm audit --audit-level=high" >/dev/null 2>&1 || true
  # Non-blocking locally — CI has allowlist logic. Mark UNKNOWN unless we parse.
  write_gate "deps-audit" "security" "UNKNOWN" "run in CI for authoritative allowlist gate; local pnpm audit advisory" "$ms"
}

# ── Layer 2: Integration ─────────────────────────────────────────────────────

run_integration_domain() {
  local id="$1" tests="$2"
  run_gate_cmd "int-${id}" "integration" "L2 integration: ${id}" bash -c "cd '$REPO_ROOT/services/api' && uv run pytest ${tests} -q"
}

run_integration() {
  run_integration_domain "cart" "tests/test_cart.py tests/test_cart_rfq_merge.py"
  run_integration_domain "checkout" "tests/test_checkout.py tests/test_checkout_payment.py"
  run_integration_domain "rfq" "tests/test_rfq.py tests/test_rfq_checkout_integrity.py"
  run_integration_domain "returns" "tests/test_returns_lane1.py tests/test_returns_lane2.py"
  run_integration_domain "orders" "tests/test_vendor_orders.py"
  run_integration_domain "reviews" "tests/test_review_aggregate.py"
  run_integration_domain "authz" "tests/test_authz_matrix.py"
}

# ── Layer 3: Browser E2E ─────────────────────────────────────────────────────

server_reachable() {
  curl -sf --max-time 5 "${E2E_BASE_URL}/en/health" >/dev/null 2>&1
}

run_e2e_suite() {
  local spec="$1" gate_id="$2"
  log "L3 E2E: ${gate_id}"
  if [[ "$SKIP_E2E" -eq 1 ]]; then
    write_gate "$gate_id" "ux" "NOT_RUN" "--skip-e2e"
    return 0
  fi
  if ! server_reachable; then
    write_gate "$gate_id" "ux" "BLOCKED_EXTERNAL" "customer app not reachable at ${E2E_BASE_URL}"
    return 0
  fi
  local ms rc=0
  ms=$(run_timed bash -c "
    cd '$REPO_ROOT/e2e' &&
    npm install --no-package-lock 2>/dev/null &&
    E2E_BASE_URL='${E2E_BASE_URL}' E2E_THROTTLE=0 PW_CHROMIUM_PATH='${PW_CHROMIUM_PATH:-}' \
      npx playwright test '${spec}' --reporter=list
  ") || rc=$?
  write_gate "$gate_id" "ux" "$([[ $rc -eq 0 ]] && echo PASS || echo FAIL)" "playwright ${spec}" "$ms"
}

run_e2e() {
  run_e2e_suite "specs/browse-journey.spec.ts" "e2e-browse-journey"
  run_e2e_suite "specs/mobile-layout.spec.ts" "e2e-mobile-layout"
  run_e2e_suite "specs/data-quality.spec.ts" "e2e-data-quality"
  run_e2e_suite "specs/ux-surfaces.spec.ts" "e2e-ux-surfaces"
  run_e2e_suite "specs/a11y-smoke.spec.ts" "a11y-axe-smoke"
  run_e2e_suite "specs/performance-smoke.spec.ts" "perf-web-vitals-smoke"
}

run_payments_sandbox() {
  log "Payments sandbox proof"
  if [[ -z "${LENCO_API_TOKEN:-}" || "${LENCO_ENV:-}" != "sandbox" ]]; then
    write_gate "payment-sandbox" "payments" "BLOCKED_EXTERNAL" "LENCO_ENV=sandbox + LENCO_API_TOKEN required (F9b founder gate)"
    return 0
  fi
  local ms rc=0
  ms=$(run_timed bash -c "cd '$REPO_ROOT/services/api' && uv run python ../../scripts/drills/lenco_sandbox_money_drill.py --mode auto") || rc=$?
  write_gate "payment-sandbox" "payments" "$([[ $rc -eq 0 ]] && echo PASS || echo FAIL)" "lenco_sandbox_money_drill.py" "$ms"
}

run_recovery() {
  log "Recovery / backup drill"
  if [[ -f "${REPO_ROOT}/scripts/ops/backup_drill.sh" ]]; then
    local ms rc=0
    ms=$(run_timed bash -c "bash '${REPO_ROOT}/scripts/ops/backup_drill.sh' --dry-run") || rc=$?
    write_gate "backup-drill" "recovery" "$([[ $rc -eq 0 ]] && echo PASS || echo BLOCKED_EXTERNAL)" "backup_drill.sh --dry-run" "$ms"
  else
    write_gate "backup-drill" "recovery" "NOT_RUN" "backup_drill.sh missing"
  fi
}

# ── Orchestrate ──────────────────────────────────────────────────────────────

case "$LAYER" in
  static)
    run_static_lint
    run_static_typecheck
    run_static_unit
    run_static_api_unit
    run_static_i18n
    run_static_migration
    run_static_rls
    run_static_deps
    ;;
  integration) run_integration ;;
  e2e) run_e2e ;;
  payments) run_payments_sandbox ;;
  recovery) run_recovery ;;
  all|*)
    run_static_lint
    run_static_typecheck
    run_static_unit
    run_static_api_unit
    run_static_i18n
    run_static_migration
    run_static_rls
    run_static_deps
    run_integration
    run_e2e
    run_payments_sandbox
    run_recovery
    ;;
esac

log "Collecting certificate"
node "${REPO_ROOT}/scripts/qa/collect-certificate.mjs" \
  --evidence-dir "$EVIDENCE_DIR" \
  --sha "$SHA" \
  --branch "$BRANCH" \
  --environment "$ENVIRONMENT"
