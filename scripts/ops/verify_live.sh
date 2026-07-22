#!/usr/bin/env bash
#
# verify_live.sh — non-destructive post-deploy verifier (CR-E).
#
# Read-only checks against live (or staging) surfaces. Prints a PASS/FAIL/SKIP matrix
# mapped to release gates G0–G9. Never prints secrets.
#
# Usage:
#   bash scripts/ops/verify_live.sh              # live probes (default API prod)
#   bash scripts/ops/verify_live.sh --dry-run      # plan only, no network
#   MOCK_API_JSON='{"status":"ok","env":"staging","git_sha":"abc","supabase_project_ref":"x"}' \
#     bash scripts/ops/verify_live.sh --mock-api
#
# Environment (names only — values from vault / shell):
#   API_BASE_URL          Default https://api.vergeo5.com
#   EXPECTED_ENV          staging | production | development (fingerprint assert)
#   MASTER_GIT_SHA        Expected deployed SHA (default: git rev-parse HEAD in repo)
#   CUSTOMER_URL          Default https://www.vergeo5.com
#   VENDOR_URL            Default https://vendor.vergeo5.com
#   ADMIN_URL             Default https://admin.vergeo5.com
#   SUPABASE_DB_URL       Optional read-only Postgres URL for migration + FORCE RLS checks
#   N8N_BASE_URL          Default https://n8n.vergeo5.com
#   N8N_API_KEY           Optional — list active workflows (no value logged)
#   EXPECTED_N8N_ACTIVE_MIN  Minimum active workflows for Wave A (default 6)
#   CHECK_LOCALHOST       Set to 1 to enable G2 localhost leak scan on customer HTML
#   CURL_BIN              curl binary (default curl)
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MIGRATIONS_DIR="${REPO_ROOT}/supabase/migrations"

API_BASE_URL="${API_BASE_URL:-https://api.vergeo5.com}"
EXPECTED_ENV="${EXPECTED_ENV:-production}"
MASTER_GIT_SHA="${MASTER_GIT_SHA:-}"
CUSTOMER_URL="${CUSTOMER_URL:-https://www.vergeo5.com}"
VENDOR_URL="${VENDOR_URL:-https://vendor.vergeo5.com}"
ADMIN_URL="${ADMIN_URL:-https://admin.vergeo5.com}"
N8N_BASE_URL="${N8N_BASE_URL:-https://n8n.vergeo5.com}"
EXPECTED_N8N_ACTIVE_MIN="${EXPECTED_N8N_ACTIVE_MIN:-6}"
CHECK_LOCALHOST="${CHECK_LOCALHOST:-0}"
CURL_BIN="${CURL_BIN:-curl}"

DRY_RUN=0
MOCK_API=0

# gate -> status (PASS|FAIL|SKIP)
declare -A GATE_STATUS=()
declare -A GATE_DETAIL=()

log()  { printf '==> %s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; }

set_gate() {
  local gate="$1" status="$2" detail="$3"
  GATE_STATUS["$gate"]="$status"
  GATE_DETAIL["$gate"]="$detail"
}

usage() {
  sed -n '2,25p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --mock-api) MOCK_API=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; usage; exit 2 ;;
  esac
done

if [[ -z "$MASTER_GIT_SHA" ]]; then
  if command -v git >/dev/null 2>&1 && git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    MASTER_GIT_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD)"
  else
    MASTER_GIT_SHA="unknown"
  fi
fi

# --- Repo migration ledger (expected tip) -----------------------------------------
mapfile -t REPO_MIGRATION_PREFIXES < <(
  find "$MIGRATIONS_DIR" -maxdepth 1 -name '*.sql' -exec basename {} \; | sort | sed 's/_.*//'
)
REPO_MIGRATION_COUNT="${#REPO_MIGRATION_PREFIXES[@]}"
REPO_MIGRATION_TIP="${REPO_MIGRATION_PREFIXES[$((REPO_MIGRATION_COUNT - 1))]}"

# Historical gap set referenced in 00-status / CR-E (for reporting only)
HISTORICAL_GAP="0051 0053 0054 0055 0056"

json_get() {
  # Usage: json_get KEY < file.json  (requires python3)
  local key="$1"
  python3 -c '
import json, sys
key = sys.argv[1]
data = json.load(sys.stdin)
if isinstance(data, dict):
    print(data.get(key, ""))
' "$key"
}

http_code() {
  local url="$1"
  local follow="${2:-0}"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf 'SKIP'
    return 0
  fi
  if [[ "$follow" -eq 1 ]]; then
    "$CURL_BIN" -fsSL -o /dev/null -w '%{http_code}' --connect-timeout 10 --max-time 30 "$url" 2>/dev/null \
      || printf '000'
  else
    "$CURL_BIN" -fsS -o /dev/null -w '%{http_code}' --connect-timeout 10 --max-time 30 "$url" 2>/dev/null \
      || printf '000'
  fi
}

http_body() {
  local url="$1"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '{"status":"ok"}'
    return 0
  fi
  if [[ "$MOCK_API" -eq 1 && "$url" == *"/fingerprint"* && -n "${MOCK_API_JSON:-}" ]]; then
    printf '%s' "$MOCK_API_JSON"
    return 0
  fi
  "$CURL_BIN" -fsS --connect-timeout 10 --max-time 30 "$url" 2>/dev/null || true
}

# --- G1: API health surfaces ------------------------------------------------------
check_g1_api() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    set_gate G1 SKIP "dry-run — API/frontend HTTP checks skipped"
    FINGERPRINT_GIT_SHA="${MASTER_GIT_SHA}"
    return 0
  fi

  local hz hc hr fp
  hz="$(http_code "${API_BASE_URL%/}/healthz")"
  hc="$(http_code "${API_BASE_URL%/}/health")"
  hr="$(http_body "${API_BASE_URL%/}/readyz")"
  local hr_code
  hr_code="$(http_code "${API_BASE_URL%/}/readyz")"
  fp="$(http_body "${API_BASE_URL%/}/fingerprint")"

  local fail=0
  local detail="healthz=${hz} health=${hc} readyz=${hr_code}"

  if [[ "$hz" != "200" || "$hc" != "200" || "$hr_code" != "200" ]]; then
    fail=1
  fi
  if [[ "$hr" != *'"status":"ok"'* && "$hr" != *'"status": "ok"'* ]]; then
    fail=1
    detail="${detail} readyz_body!=ok"
  fi

  # Fingerprint env + git_sha (G9 overlap)
  local fp_env fp_sha fp_ref
  if [[ -n "$fp" && "$fp" == \{* ]]; then
    fp_env="$(printf '%s' "$fp" | json_get env)"
    fp_sha="$(printf '%s' "$fp" | json_get git_sha)"
    fp_ref="$(printf '%s' "$fp" | json_get supabase_project_ref)"
    detail="${detail} env=${fp_env:-?} git_sha=${fp_sha:-?} supabase_project_ref=${fp_ref:-?}"

    if [[ -n "$EXPECTED_ENV" && "$fp_env" != "$EXPECTED_ENV" ]]; then
      fail=1
      detail="${detail} expected_env=${EXPECTED_ENV}"
    fi
  else
    fail=1
    detail="${detail} fingerprint=missing"
    fp_sha=""
  fi

  if [[ "$fail" -eq 0 ]]; then
    set_gate G1 PASS "$detail"
  else
    set_gate G1 FAIL "$detail"
  fi

  # stash for G9
  FINGERPRINT_GIT_SHA="${fp_sha:-}"
}

check_g1_frontends() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    return 0
  fi
  local cust vend admin
  cust="$(http_code "${CUSTOMER_URL%/}/en/health" 1)"
  vend="$(http_code "${VENDOR_URL%/}/en/health" 1)"
  admin="$(http_code "${ADMIN_URL%/}/en/health" 1)"
  local detail="${GATE_DETAIL[G1]:-}"
  detail="${detail} customer=${cust} vendor=${vend} admin=${admin}"
  if [[ "$cust" != "200" || "$vend" != "200" ]]; then
    set_gate G1 FAIL "$detail"
    return 0
  fi
  # Admin may be 403 behind Cloudflare Access — acceptable for integrity probe
  if [[ "$admin" != "200" && "$admin" != "403" ]]; then
    set_gate G1 FAIL "$detail"
    return 0
  fi
  if [[ "${GATE_STATUS[G1]:-}" != "FAIL" ]]; then
    set_gate G1 PASS "$detail"
  else
    GATE_DETAIL[G1]="$detail"
  fi
}

# --- G0: migrations + FORCE RLS ---------------------------------------------------
check_g0() {
  if [[ -z "${SUPABASE_DB_URL:-}" ]]; then
    set_gate G0 SKIP "SUPABASE_DB_URL unset — cannot query schema_migrations or FORCE RLS"
    return 0
  fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
    set_gate G0 SKIP "dry-run — DB checks skipped"
    return 0
  fi
  if ! command -v psql >/dev/null 2>&1; then
    set_gate G0 SKIP "psql not installed"
    return 0
  fi

  local live_count live_tip
  live_count="$(psql "$SUPABASE_DB_URL" -tA -c \
    "SELECT count(*) FROM supabase_migrations.schema_migrations" 2>/dev/null || echo 0)"
  live_tip="$(psql "$SUPABASE_DB_URL" -tA -c \
    "SELECT coalesce(max(version),'') FROM supabase_migrations.schema_migrations" 2>/dev/null || echo '')"

  local force_ok
  force_ok="$(psql "$SUPABASE_DB_URL" -tA -c \
    "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public'
       AND c.relname IN ('ticket_type_instances','ticket_type_price_tiers','product_relations')
       AND c.relforcerowsecurity = true" 2>/dev/null || echo 0)"

  LIVE_MIGRATION_TIP="$live_tip"

  local detail="live_tip=${live_tip} repo_tip=${REPO_MIGRATION_TIP} live_count=${live_count} repo_count=${REPO_MIGRATION_COUNT} force_rls_tables=${force_ok}/3"
  local fail=0

  if [[ "$live_tip" != "$REPO_MIGRATION_TIP" ]]; then
    fail=1
  fi
  if [[ "$live_count" -lt "$REPO_MIGRATION_COUNT" ]]; then
    fail=1
    detail="${detail} live_count=${live_count}<repo=${REPO_MIGRATION_COUNT}"
  fi
  if [[ "$force_ok" != "3" ]]; then
    # 0064 not applied or FORCE RLS off
    fail=1
  fi

  # Report historical gap membership
  for gap in $HISTORICAL_GAP; do
    if ! psql "$SUPABASE_DB_URL" -tA -c \
      "SELECT 1 FROM supabase_migrations.schema_migrations WHERE version LIKE '${gap}_%' LIMIT 1" \
      2>/dev/null | grep -q 1; then
      detail="${detail} missing_hist=${gap}"
      fail=1
    fi
  done

  if [[ "$fail" -eq 0 ]]; then
    set_gate G0 PASS "$detail"
  else
    set_gate G0 FAIL "$detail"
  fi
}

# --- G2: localhost leaks ----------------------------------------------------------
check_g2() {
  if [[ "$CHECK_LOCALHOST" != "1" ]]; then
    set_gate G2 SKIP "CHECK_LOCALHOST!=1"
    return 0
  fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
    set_gate G2 SKIP "dry-run"
    return 0
  fi
  local html
  html="$("$CURL_BIN" -fsS --connect-timeout 10 --max-time 30 "${CUSTOMER_URL%/}/en" 2>/dev/null || true)"
  if [[ -z "$html" ]]; then
    set_gate G2 FAIL "customer HTML fetch failed"
    return 0
  fi
  if grep -qE 'localhost:(3001|8000)' <<<"$html"; then
    set_gate G2 FAIL "localhost leak in customer HTML"
  else
    set_gate G2 PASS "no localhost:3001/8000 in customer HTML"
  fi
}

# --- G3/G4/G6/G7/G8: require creds or external systems ----------------------------
check_blocked_gates() {
  set_gate G3 SKIP "Lenco sandbox money drill — needs F9b + staging ledger proof"
  set_gate G4 SKIP "Playwright false-success E2E — needs staging run"
  set_gate G6 SKIP "Sentry test event + UptimeRobot alert — needs founder DSN/monitor"
  set_gate G7 SKIP "Dated OCI backup + restore drill — see docs/ops/backup-runbook.md"
  set_gate G8 SKIP "CI/branch-protection audit — run GitHub required-checks review"
}

# --- G5: n8n active workflows -----------------------------------------------------
check_g5() {
  if [[ -z "${N8N_API_KEY:-}" ]]; then
    set_gate G5 SKIP "N8N_API_KEY unset — cannot list active workflows"
    return 0
  fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
    set_gate G5 SKIP "dry-run"
    return 0
  fi
  local payload count
  payload="$("$CURL_BIN" -fsS --connect-timeout 10 --max-time 30 \
    -H "X-N8N-API-KEY: ${N8N_API_KEY}" \
    "${N8N_BASE_URL%/}/api/v1/workflows?active=true" 2>/dev/null || true)"
  if [[ -z "$payload" ]]; then
    set_gate G5 FAIL "n8n API unreachable or unauthorized"
    return 0
  fi
  count="$(printf '%s' "$payload" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except json.JSONDecodeError:
    print(0)
    raise SystemExit
if isinstance(data, dict) and "data" in data:
    print(len(data["data"]))
elif isinstance(data, list):
    print(len(data))
else:
    print(0)
' 2>/dev/null || echo 0)"
  if [[ "$count" -ge "$EXPECTED_N8N_ACTIVE_MIN" ]]; then
    set_gate G5 PASS "active_workflows=${count} (min=${EXPECTED_N8N_ACTIVE_MIN})"
  else
    set_gate G5 FAIL "active_workflows=${count} < min=${EXPECTED_N8N_ACTIVE_MIN}"
  fi
}

# --- G9: deploy parity ------------------------------------------------------------
check_g9() {
  local detail=""
  local fail=0

  if [[ -n "${FINGERPRINT_GIT_SHA:-}" ]]; then
    local short_master short_fp
    short_master="$(printf '%s' "$MASTER_GIT_SHA" | cut -c1-7)"
    short_fp="$(printf '%s' "$FINGERPRINT_GIT_SHA" | cut -c1-7)"
    detail="fingerprint_sha=${FINGERPRINT_GIT_SHA} master=${MASTER_GIT_SHA}"
    if [[ "$FINGERPRINT_GIT_SHA" != "$MASTER_GIT_SHA" && "$short_fp" != "$short_master" ]]; then
      fail=1
      detail="${detail} SHA_MISMATCH"
    fi
    if [[ "$FINGERPRINT_GIT_SHA" == "unknown" || -z "$FINGERPRINT_GIT_SHA" ]]; then
      fail=1
      detail="${detail} SHA_UNKNOWN"
    fi
  else
    fail=1
    detail="fingerprint_sha=missing"
  fi

  if [[ -n "${LIVE_MIGRATION_TIP:-}" ]]; then
    detail="${detail} db_tip=${LIVE_MIGRATION_TIP}"
    if [[ "$LIVE_MIGRATION_TIP" != "$REPO_MIGRATION_TIP" ]]; then
      fail=1
    fi
  else
    detail="${detail} db_tip=unchecked"
  fi

  if [[ "$fail" -eq 0 ]]; then
    set_gate G9 PASS "$detail"
  else
    set_gate G9 FAIL "$detail"
  fi
}

# --- Main -------------------------------------------------------------------------
main() {
  log "Vergeo5 live verifier (read-only)"
  log "API_BASE_URL=${API_BASE_URL} EXPECTED_ENV=${EXPECTED_ENV} MASTER_GIT_SHA=${MASTER_GIT_SHA}"
  log "Repo migrations: count=${REPO_MIGRATION_COUNT} tip=${REPO_MIGRATION_TIP}"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    warn "DRY-RUN — network and DB probes skipped where noted"
  fi

  FINGERPRINT_GIT_SHA=""
  LIVE_MIGRATION_TIP=""

  check_g1_api
  check_g1_frontends
  check_g0
  check_g2
  check_g5
  check_blocked_gates
  check_g9

  printf '\n'
  printf '%-6s %-8s %s\n' 'GATE' 'STATUS' 'DETAIL'
  printf '%-6s %-8s %s\n' '----' '------' '------'
  local g overall=0
  for g in G0 G1 G2 G3 G4 G5 G6 G7 G8 G9; do
    local st="${GATE_STATUS[$g]:-SKIP}"
    local dt="${GATE_DETAIL[$g]:-}"
    printf '%-6s %-8s %s\n' "$g" "$st" "$dt"
    if [[ "$st" == "FAIL" ]]; then
      overall=1
    fi
  done

  printf '\n'
  if [[ "$overall" -eq 0 ]]; then
    log "OVERALL: PASS (no FAIL rows; SKIP = needs live creds or manual drill)"
    exit 0
  else
    log "OVERALL: FAIL — see FAIL rows above; runbook: docs/ops/deploy-verify-runbook.md"
    exit 1
  fi
}

main "$@"
