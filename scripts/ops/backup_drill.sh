#!/usr/bin/env bash
#
# backup_drill.sh — G7 dated backup + restore drill orchestrator.
#
# Wraps infra/scripts/restore-drill.sh (local ephemeral Postgres) or documents the
# founder path for OCI dated dumps + staging restore. Writes a JSON report artifact.
#
# Usage:
#   bash scripts/ops/backup_drill.sh --local          # full local drill (needs docker or pg)
#   bash scripts/ops/backup_drill.sh --verify-oci     # list newest OCI object (needs oci CLI + env)
#   bash scripts/ops/backup_drill.sh --dry-run
#
# Environment (names only):
#   OCI_NAMESPACE, OCI_BUCKET_NAME, OCI_OBJECT_PREFIX (default db/)
#   BACKUP_DRILL_REPORT   Output JSON (default /tmp/vergeo5-backup-drill.json)
#   SUPABASE_DB_URL       For --staging-restore (founder scratch DB)
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKUP_DRILL_REPORT="${BACKUP_DRILL_REPORT:-/tmp/vergeo5-backup-drill.json}"
OCI_OBJECT_PREFIX="${OCI_OBJECT_PREFIX:-db/}"

MODE="plan"
DRY_RUN=0

log() { printf '==> %s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; }

usage() {
  sed -n '2,18p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --local) MODE="local"; shift ;;
    --verify-oci) MODE="verify-oci"; shift ;;
    --staging-restore) MODE="staging-restore"; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; usage; exit 2 ;;
  esac
done

write_report() {
  local verdict="$1"
  local detail="$2"
  python3 - "$BACKUP_DRILL_REPORT" "$verdict" "$detail" "$MODE" <<'PY'
import json, sys
from datetime import UTC, datetime

report_path, verdict, detail, mode = sys.argv[1:5]
payload = {
    "gate": "G7",
    "mode": mode,
    "verdict": verdict,
    "detail": detail,
    "finished_at": datetime.now(UTC).isoformat(),
}
with open(report_path, "w", encoding="utf-8") as fh:
    json.dump(payload, fh, indent=2)
print(f"report={report_path} verdict={verdict}")
PY
}

run_local_drill() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "DRY-RUN: would execute infra/scripts/restore-drill.sh"
    write_report "SKIP" "dry-run local drill"
    return 0
  fi
  local start_ts end_ts output
  start_ts="$(date +%s)"
  if output="$(bash "${REPO_ROOT}/infra/scripts/restore-drill.sh" 2>&1)"; then
    end_ts="$(date +%s)"
    log "$output"
    write_report "PASS" "local restore-drill duration=$((end_ts - start_ts))s"
    log "Append evidence to docs/ops/drill-log.md (local drill is not the ≤30min staging RTO)"
    return 0
  fi
  write_report "FAIL" "local restore-drill failed"
  printf '%s\n' "$output" >&2
  return 1
}

verify_oci_dump() {
  if [[ -z "${OCI_NAMESPACE:-}" || -z "${OCI_BUCKET_NAME:-}" ]]; then
    write_report "SKIP" "OCI_NAMESPACE/OCI_BUCKET_NAME unset"
    warn "Set OCI env vars on the deploy host to verify dated dumps"
    return 0
  fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
    write_report "SKIP" "dry-run oci list"
    return 0
  fi
  if ! command -v oci >/dev/null 2>&1; then
    write_report "SKIP" "oci CLI not installed"
    return 0
  fi
  local listing
  listing="$(oci os object list \
    --namespace "${OCI_NAMESPACE}" \
    --bucket-name "${OCI_BUCKET_NAME}" \
    --prefix "${OCI_OBJECT_PREFIX}" \
    --sort-by timeCreated \
    --sort-order DESC \
    --limit 3 2>/dev/null || true)"
  if [[ -z "$listing" || "$listing" != *"vergeo5-"* ]]; then
    write_report "FAIL" "no dated vergeo5-*.sql.gz objects under ${OCI_OBJECT_PREFIX}"
    return 1
  fi
  local newest
  newest="$(printf '%s' "$listing" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except json.JSONDecodeError:
    print("unknown")
    raise SystemExit
items = data.get("data") or []
for obj in items:
    name = obj.get("name", "")
    if "vergeo5-" in name and name.endswith(".sql.gz"):
        print(name)
        break
else:
    print("unknown")
' 2>/dev/null || echo unknown)"
  write_report "PASS" "newest_object=${newest}"
  log "G7 partial PASS — OCI object exists; still need ≤30min staging restore in drill-log.md"
  return 0
}

run_staging_restore() {
  if [[ -z "${SUPABASE_DB_URL:-}" || -z "${SOURCE_DB_URL:-}" ]]; then
    write_report "SKIP" "SOURCE_DB_URL + SUPABASE_DB_URL required for staging restore"
    return 0
  fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
    write_report "SKIP" "dry-run staging restore"
    return 0
  fi
  local start_ts end_ts
  start_ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  log "DRILL START ${start_ts}"
  if bash "${REPO_ROOT}/scripts/ops/restore-staging.sh"; then
    end_ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    log "DRILL END ${end_ts}"
    write_report "PASS" "staging restore-staging.sh ok start=${start_ts} end=${end_ts}"
    log "Record wall-clock ≤30min in docs/ops/drill-log.md"
    return 0
  fi
  write_report "FAIL" "restore-staging.sh failed"
  return 1
}

main() {
  log "Backup drill (G7) mode=${MODE}"
  case "$MODE" in
    local) run_local_drill ;;
    verify-oci) verify_oci_dump ;;
    staging-restore) run_staging_restore ;;
    plan)
      log "Planned founder path:"
      log "  1. Trigger dated dump: infra/scripts/db-dump.sh or n8n backup-manual webhook"
      log "  2. Verify OCI object: bash scripts/ops/backup_drill.sh --verify-oci"
      log "  3. Staging restore: SOURCE_DB_URL=... SUPABASE_DB_URL=... bash scripts/ops/backup_drill.sh --staging-restore"
      log "  4. Log timings in docs/ops/drill-log.md"
      write_report "SKIP" "plan only — run --local, --verify-oci, or --staging-restore"
      ;;
  esac
}

main "$@"
