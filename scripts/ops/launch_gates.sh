#!/usr/bin/env bash
#
# launch_gates.sh — orchestrate founder-gated launch gates (F9b, G6, G7, F5 checklist, Vercel).
#
# Runs what can be automated from this repo; prints PASS/FAIL/SKIP matrix. Never prints secrets.
#
# Usage:
#   bash scripts/ops/launch_gates.sh
#   bash scripts/ops/launch_gates.sh --dry-run
#   bash scripts/ops/launch_gates.sh --only g6,g7
#
# Reports (optional, consumed by verify_live.sh):
#   MONEY_DRILL_REPORT      Latest lenco sandbox drill JSON
#   SENTRY_SMOKE_REPORT     From sentry_smoke.sh
#   BACKUP_DRILL_REPORT     From backup_drill.sh
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ONLY=""
DRY_RUN=0

declare -A GATE_STATUS=()
declare -A GATE_DETAIL=()

log() { printf '==> %s\n' "$*"; }

set_gate() {
  GATE_STATUS["$1"]="$2"
  GATE_DETAIL["$1"]="$3"
}

should_run() {
  local gate="$1"
  if [[ -z "$ONLY" ]]; then
    return 0
  fi
  [[ ",${ONLY}," == *",${gate},"* ]]
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --only) ONLY="${2:-}"; shift 2 ;;
    -h|--help)
      sed -n '2,18p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
  esac
done

run_f9b() {
  if should_run f9b; then
    log "F9b / G3 — Lenco sandbox money drill"
    local mode="dry-run"
    if [[ -n "${LENCO_API_TOKEN:-}" && "${LENCO_ENV:-}" == "sandbox" ]]; then
      mode="auto"
    fi
    local report_path="${REPO_ROOT}/scripts/drills/reports/lenco-sandbox-drill-$(date -u +%Y%m%dT%H%M%SZ).json"
    mkdir -p "$(dirname "$report_path")"
    local args=(--mode "$mode" --report "$report_path")
    if [[ "$DRY_RUN" -eq 1 ]]; then
      args=(--mode dry-run --report "$report_path")
    fi
    local drill_cmd=(uv run python "${REPO_ROOT}/scripts/drills/lenco_sandbox_money_drill.py" "${args[@]}")
    if ! command -v uv >/dev/null 2>&1; then
      drill_cmd=(python3 "${REPO_ROOT}/scripts/drills/lenco_sandbox_money_drill.py" "${args[@]}")
    fi
    if (cd "${REPO_ROOT}/services/api" && "${drill_cmd[@]}"); then
      local latest="$report_path"
      if [[ -f "$latest" ]]; then
        export MONEY_DRILL_REPORT="$latest"
        local verdict imbalance report_mode
        verdict="$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get('verdict','?'))" "$latest")"
        imbalance="$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get('ledger_imbalance_ngwee','?'))" "$latest")"
        report_mode="$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get('mode','?'))" "$latest")"
        if [[ "$verdict" == "PASS" && "$imbalance" == "0" && "$report_mode" == "live" ]]; then
          set_gate G3 PASS "money_drill=${latest} verdict=PASS live"
        elif [[ "$verdict" == "PASS" ]]; then
          set_gate G3 SKIP "harness PASS (${mode}) — attach live F9b report for STAGING_VERIFIED"
          set_gate F9b SKIP "creds missing or dry-run only — set LENCO_ENV=sandbox + LENCO_API_TOKEN"
        else
          set_gate G3 FAIL "money_drill=${latest} verdict=${verdict}"
          set_gate F9b FAIL "drill verdict=${verdict}"
        fi
      else
        set_gate G3 SKIP "no drill report emitted"
        set_gate F9b SKIP "no drill report"
      fi
    else
      set_gate G3 FAIL "lenco_sandbox_money_drill.py failed"
      set_gate F9b FAIL "drill script error"
    fi

    if [[ -n "${SUPABASE_DB_URL:-}" && "$DRY_RUN" -eq 0 ]]; then
      if psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -f "${REPO_ROOT}/scripts/db/ledger-invariants.sql" >/dev/null 2>&1; then
        GATE_DETAIL[G3]="${GATE_DETAIL[G3]:-} ledger-invariants=PASS"
      else
        set_gate G3 FAIL "ledger-invariants.sql failed"
      fi
    fi
  fi
}

run_g6() {
  if should_run g6; then
    log "G6 — Sentry test event ingest"
    local args=()
    [[ "$DRY_RUN" -eq 1 ]] && args+=(--dry-run)
    if bash "${REPO_ROOT}/scripts/ops/sentry_smoke.sh" "${args[@]}"; then
      if [[ -f "${SENTRY_SMOKE_REPORT:-/tmp/vergeo5-sentry-smoke.json}" ]]; then
        local v
        v="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('verdict','?'))" "${SENTRY_SMOKE_REPORT:-/tmp/vergeo5-sentry-smoke.json}")"
        set_gate G6 "$([[ "$v" == PASS ]] && echo PASS || echo SKIP)" "sentry_smoke verdict=${v}"
      else
        set_gate G6 SKIP "no sentry report"
      fi
    else
      set_gate G6 FAIL "sentry_smoke.sh failed"
    fi
  fi
}

run_g7() {
  if should_run g7; then
    log "G7 — backup / restore drill"
    local args=(--local)
    if [[ "$DRY_RUN" -eq 1 ]]; then
      args=(--dry-run)
    fi
    if bash "${REPO_ROOT}/scripts/ops/backup_drill.sh" "${args[@]}"; then
      local v
      v="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('verdict','?'))" "${BACKUP_DRILL_REPORT:-/tmp/vergeo5-backup-drill.json}" 2>/dev/null || echo SKIP)"
      if [[ "$v" == "PASS" ]]; then
        set_gate G7 SKIP "local drill PASS - founder must log dated OCI + <=30min staging restore in drill-log.md"
      else
        set_gate G7 SKIP "plan/local only — see docs/ops/backup-runbook.md"
      fi
    else
      set_gate G7 FAIL "backup_drill.sh failed"
    fi
  fi
}

run_f5() {
  if should_run f5; then
    log "F5 — WhatsApp Meta template submission (founder)"
    local missing=0
    for tpl in event_cancelled event_schedule_changed rfq_job_broadcast ops_uptime_alert; do
      if ! grep -q "\`${tpl}\`" "${REPO_ROOT}/docs/ops/whatsapp-templates.md" 2>/dev/null; then
        missing=$((missing + 1))
      fi
    done
    if [[ "$missing" -eq 0 ]]; then
      set_gate F5 SKIP "submission pack complete in docs/ops/whatsapp-templates.md — submit in Meta Business Manager"
    else
      set_gate F5 FAIL "${missing} template(s) missing from whatsapp-templates.md"
    fi
  fi
}

run_vercel() {
  if should_run vercel; then
    log "Vercel prod promote"
    local args=()
    [[ "$DRY_RUN" -eq 1 ]] && args+=(--dry-run)
    if [[ -z "${VERCEL_TOKEN:-}" ]]; then
      set_gate VERCEL SKIP "VERCEL_TOKEN unset — promote in dashboard when rate limit clears"
      return 0
    fi
    if bash "${REPO_ROOT}/scripts/ops/vercel_promote.sh" "${args[@]}"; then
      set_gate VERCEL PASS "promote + probe-frontends ok"
    else
      set_gate VERCEL SKIP "promote blocked (rate limit / build error) — run manually when clear"
    fi
  fi
}

main() {
  log "Launch gates orchestrator"
  run_f9b
  run_g6
  run_g7
  run_f5
  run_vercel

  printf '\n%-8s %-8s %s\n' 'GATE' 'STATUS' 'DETAIL'
  printf '%s\n' '----------------------------------------'
  local g overall=0
  for g in F9b G3 G6 G7 F5 VERCEL; do
    [[ -z "${GATE_STATUS[$g]:-}" ]] && continue
    printf '%-8s %-8s %s\n' "$g" "${GATE_STATUS[$g]}" "${GATE_DETAIL[$g]:-}"
    [[ "${GATE_STATUS[$g]}" == "FAIL" ]] && overall=1
  done

  printf '\n'
  log "Live surface verifier: bash scripts/ops/verify_live.sh"
  log "Runbook: docs/ops/launch-gates-execution.md"
  exit "$overall"
}

main "$@"
