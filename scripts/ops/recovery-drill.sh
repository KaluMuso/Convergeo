#!/usr/bin/env bash
#
# recovery-drill.sh — STG-REC-04 genuine staging backup → restore → verification drill.
#
# Fail-closed orchestrator for a real (non-dry-run) recovery drill into a safe,
# disposable non-production target. Writes machine-readable evidence compatible
# with scripts/qa/ evidence collectors.
#
# Usage:
#   # Plan only (no credentials required):
#   bash scripts/ops/recovery-drill.sh --plan
#
#   # Real drill (requires SOURCE_DB_URL + RESTORE_TARGET_DB_URL):
#   SOURCE_DB_URL='postgresql://…' \
#   RESTORE_TARGET_DB_URL='postgresql://…' \
#   RESTORE_TARGET_KIND=dedicated-drill-project \
#     bash scripts/ops/recovery-drill.sh
#
#   # Restore from an existing custom-format dump:
#   RESTORE_TARGET_DB_URL='postgresql://…' \
#     bash scripts/ops/recovery-drill.sh --dump-file /path/to/dump.dump
#
# Environment:
#   SOURCE_DB_URL              Staging source (read). Required unless --dump-file.
#   RESTORE_TARGET_DB_URL      Disposable non-production target (write).
#   RESTORE_TARGET_KIND        dedicated-drill-project | supabase-branch | scratch-database
#   RECOVERY_EVIDENCE_PATH     Output JSON (default /tmp/vergeo5-recovery-evidence.json)
#   RECOVERY_RECORD_MARKER     1 to insert a drill marker row before backup (default 1)
#
# Verdict taxonomy (never maps missing infra to PASS):
#   BACKUP_CONFIGURATION_VALID
#   RESTORE_TARGET_AUTHORIZATION_REQUIRED
#   RESTORE_FAILED
#   RESTORE_VERIFICATION_FAILED
#   RESTORE_DRILL_PROVEN
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=lib/recovery-guards.sh
source "${SCRIPT_DIR}/lib/recovery-guards.sh"

SMOKE_SQL="${REPO_ROOT}/scripts/ops/restore-smoke.sql"
RLS_SQL="${REPO_ROOT}/scripts/ops/recovery-rls-check.sql"
RESTORE_STAGING="${REPO_ROOT}/scripts/ops/restore-staging.sh"

RECOVERY_EVIDENCE_PATH="${RECOVERY_EVIDENCE_PATH:-/tmp/vergeo5-recovery-evidence.json}"
RECOVERY_RECORD_MARKER="${RECOVERY_RECORD_MARKER:-1}"
RESTORE_TARGET_KIND="${RESTORE_TARGET_KIND:-unknown}"

SOURCE_URL="${SOURCE_DB_URL:-}"
TARGET_URL="${RESTORE_TARGET_DB_URL:-${TARGET_DB_URL:-}}"
DUMP_FILE=""
PLAN_ONLY=0

log()  { printf '==> %s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; }

usage() { sed -n '2,42p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --plan)       PLAN_ONLY=1; shift ;;
    --dump-file)  DUMP_FILE="${2:-}"; [[ -n "$DUMP_FILE" ]] || recovery_die "RESTORE_FAILED: --dump-file needs PATH"; shift 2 ;;
    -h|--help)    usage; exit 0 ;;
    *)            recovery_die "RESTORE_FAILED: unknown argument: $1" ;;
  esac
done

write_evidence() {
  local verdict="$1"
  local detail="$2"
  local started_at="${3:-}"
  local finished_at="${4:-}"
  local duration="${5:-0}"
  local backup_id="${6:-}"
  local backup_sha="${7:-}"
  local backup_size="${8:-0}"
  local source_ref="${9:-}"
  local source_tip="${10:-}"
  local target_ref="${11:-}"
  local marker="${12:-false}"
  local schema_status="${13:-SKIP}"
  local data_status="${14:-SKIP}"
  local rls_status="${15:-SKIP}"

  python3 - "$RECOVERY_EVIDENCE_PATH" "$verdict" "$detail" "$started_at" "$finished_at" \
    "$duration" "$backup_id" "$backup_sha" "$backup_size" "$source_ref" "$source_tip" \
    "$target_ref" "$marker" "$schema_status" "$data_status" "$rls_status" \
    "$RESTORE_TARGET_KIND" <<'PY'
import json, sys
from datetime import UTC, datetime

(
    path, verdict, detail, started_at, finished_at, duration,
    backup_id, backup_sha, backup_size, source_ref, source_tip,
    target_ref, marker, schema_status, data_status, rls_status,
    target_kind,
) = sys.argv[1:]

payload = {
    "schema_version": "1",
    "source_project_ref": source_ref or "unknown",
    "source_migration_tip": source_tip or "unknown",
    "backup_identifier": backup_id or "",
    "backup_sha256": backup_sha or "",
    "backup_size_bytes": int(backup_size or 0),
    "restore_target_ref": target_ref or "unknown",
    "restore_target_kind": target_kind or "unknown",
    "started_at": started_at or datetime.now(UTC).isoformat(),
    "finished_at": finished_at or datetime.now(UTC).isoformat(),
    "duration_seconds": float(duration or 0),
    "marker_recorded": marker.lower() == "true",
    "schema_verification": {
        "status": schema_status,
        "detail": "restore-smoke.sql + migration currency",
    },
    "data_verification": {
        "status": data_status,
        "seed_tables_non_empty": data_status == "PASS",
        "detail": "config seed tables non-empty",
    },
    "rls_verification": {
        "status": rls_status,
        "detail": "recovery-rls-check.sql on critical tables",
    },
    "verdict": verdict,
    "detail": detail,
}

with open(path, "w", encoding="utf-8") as fh:
    json.dump(payload, fh, indent=2)
print(f"evidence={path} verdict={verdict}")
PY
}

migration_tip_of() {
  local url="$1"
  psql "$url" -tA -c \
    "SELECT version FROM supabase_migrations.schema_migrations ORDER BY version DESC LIMIT 1;" \
    2>/dev/null | tr -d '[:space:]' || printf 'unknown'
}

record_marker() {
  local url="$1"
  local marker_value="vergeo5-recovery-drill-$(date -u +%Y%m%dT%H%M%SZ)"
  psql "$url" -v ON_ERROR_STOP=1 <<SQL
CREATE TABLE IF NOT EXISTS vergeo5_recovery_drill_marker (
  id integer PRIMARY KEY,
  marker text NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO vergeo5_recovery_drill_marker (id, marker)
VALUES (1, '${marker_value}')
ON CONFLICT (id) DO UPDATE SET marker = EXCLUDED.marker, recorded_at = now();
SQL
  printf '%s' "$marker_value"
}

if [[ "$PLAN_ONLY" -eq 1 ]]; then
  log "STG-REC-04 recovery drill — PLAN ONLY"
  log "source:  SOURCE_DB_URL $( [[ -n "$SOURCE_URL" ]] && echo '(set)' || echo '(unset)') "
  log "target:  RESTORE_TARGET_DB_URL $( [[ -n "$TARGET_URL" ]] && echo '(set)' || echo '(unset)') "
  log "kind:    ${RESTORE_TARGET_KIND}"
  cat <<'PLAN'

Executable steps when a disposable restore target is authorized:
  1. Validate source/target identity (hard-reject production ref dpadrlxukcjbewpqympu)
  2. Record drill marker in source (optional)
  3. pg_dump custom-format backup + SHA-256 checksum
  4. DROP/CREATE fresh target + pg_restore
  5. restore-smoke.sql (schema + seed + migration ledger)
  6. recovery-rls-check.sql (RLS on critical tables)
  7. Write recovery evidence JSON

PLAN
  write_evidence \
    "RESTORE_TARGET_AUTHORIZATION_REQUIRED" \
    "plan only — provision a disposable non-production restore target" \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  "0" "" "" "0" "" "" "" "false" "SKIP" "SKIP" "SKIP"
  exit 0
fi

# --- Fail closed: target must be present and authorized --------------------------------
if [[ -z "$TARGET_URL" ]]; then
  write_evidence \
    "RESTORE_TARGET_AUTHORIZATION_REQUIRED" \
    "RESTORE_TARGET_DB_URL is unset — provision a dedicated drill Supabase project or authorized branch" \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    "0" "" "" "0" "" "" "unknown" "false" "SKIP" "SKIP" "SKIP"
  recovery_die "RESTORE_TARGET_AUTHORIZATION_REQUIRED: RESTORE_TARGET_DB_URL is unset"
fi

if recovery_is_production_restore_target "$TARGET_URL"; then
  write_evidence "RESTORE_FAILED" "production restore target refused" \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    "0" "" "" "0" "" "" "$(recovery_extract_supabase_ref "$TARGET_URL")" "false" "SKIP" "SKIP" "SKIP"
  recovery_die "RESTORE_FAILED: refusing production restore target (${PROD_SUPABASE_PROJECT_REF})"
fi

if [[ -z "$DUMP_FILE" ]]; then
  [[ -n "$SOURCE_URL" ]] || {
    write_evidence "RESTORE_FAILED" "SOURCE_DB_URL required when no --dump-file" \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      "0" "" "" "0" "" "" "$(recovery_extract_supabase_ref "$TARGET_URL")" "false" "SKIP" "SKIP" "SKIP"
    recovery_die "RESTORE_FAILED: SOURCE_DB_URL required"
  }
  recovery_assert_restore_target_safe "$SOURCE_URL" "$TARGET_URL"
fi

STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
START_EPOCH="$SECONDS"

SOURCE_REF="$(recovery_extract_supabase_ref "${SOURCE_URL:-}")"
TARGET_REF="$(recovery_extract_supabase_ref "$TARGET_URL")"
SOURCE_TIP="unknown"
MARKER_RECORDED="false"
BACKUP_ID=""
BACKUP_SHA=""
BACKUP_SIZE="0"
RESTORE_ARGS=()

if [[ -z "$DUMP_FILE" ]]; then
  command -v pg_dump >/dev/null || recovery_die "RESTORE_FAILED: pg_dump not on PATH"
  command -v psql >/dev/null || recovery_die "RESTORE_FAILED: psql not on PATH"

  SOURCE_TIP="$(migration_tip_of "$SOURCE_URL")"

  if [[ "$RECOVERY_RECORD_MARKER" == "1" ]]; then
    log "recording drill marker in source"
    record_marker "$SOURCE_URL" >/dev/null
    MARKER_RECORDED="true"
  fi
else
  [[ -f "$DUMP_FILE" ]] || {
    write_evidence "RESTORE_FAILED" "dump file not found: ${DUMP_FILE}" \
      "$STARTED_AT" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$((SECONDS - START_EPOCH))" \
      "$(basename "$DUMP_FILE")" "" "0" "$SOURCE_REF" "$SOURCE_TIP" "$TARGET_REF" "$MARKER_RECORDED" \
      "SKIP" "SKIP" "SKIP"
    recovery_die "RESTORE_FAILED: dump file not found"
  }
fi

# Delegate restore + smoke to restore-staging.sh (custom format path)
export SUPABASE_DB_URL="$TARGET_URL"
export TARGET_DB_URL="$TARGET_URL"
export SOURCE_DB_URL="$SOURCE_URL"

if [[ -n "$DUMP_FILE" ]]; then
  RESTORE_ARGS+=(--dump-file "$DUMP_FILE")
  BACKUP_ID="$(basename "$DUMP_FILE")"
  BACKUP_SHA="$(sha256sum "$DUMP_FILE" | awk '{print $1}')"
  BACKUP_SIZE="$(stat -c '%s' "$DUMP_FILE" 2>/dev/null || stat -f '%z' "$DUMP_FILE")"
else
  TMP_DUMP="$(mktemp "${TMPDIR:-/tmp}/vergeo-recovery-XXXXXX.dump")"
  trap 'rm -f "${TMP_DUMP:-}"' EXIT
  log "dumping source (custom format)"
  pg_dump --format=custom --no-owner --no-privileges "$SOURCE_URL" -f "$TMP_DUMP"
  BACKUP_ID="$(basename "$TMP_DUMP")"
  BACKUP_SHA="$(sha256sum "$TMP_DUMP" | awk '{print $1}')"
  BACKUP_SIZE="$(stat -c '%s' "$TMP_DUMP" 2>/dev/null || stat -f '%z' "$TMP_DUMP")"
  RESTORE_ARGS+=(--dump-file "$TMP_DUMP")
fi

log "restoring into target via restore-staging.sh"
if ! bash "$RESTORE_STAGING" "${RESTORE_ARGS[@]}"; then
  FINISHED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  write_evidence \
    "RESTORE_FAILED" "restore-staging.sh failed" \
    "$STARTED_AT" "$FINISHED_AT" "$((SECONDS - START_EPOCH))" \
    "$BACKUP_ID" "$BACKUP_SHA" "$BACKUP_SIZE" "$SOURCE_REF" "$SOURCE_TIP" "$TARGET_REF" \
    "$MARKER_RECORDED" "FAIL" "FAIL" "SKIP"
  recovery_die "RESTORE_FAILED: restore-staging.sh failed"
fi

log "running RLS verification"
if ! psql -v ON_ERROR_STOP=1 "$TARGET_URL" -f "$RLS_SQL"; then
  FINISHED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  write_evidence \
    "RESTORE_VERIFICATION_FAILED" "recovery-rls-check.sql failed" \
    "$STARTED_AT" "$FINISHED_AT" "$((SECONDS - START_EPOCH))" \
    "$BACKUP_ID" "$BACKUP_SHA" "$BACKUP_SIZE" "$SOURCE_REF" "$SOURCE_TIP" "$TARGET_REF" \
    "$MARKER_RECORDED" "PASS" "PASS" "FAIL"
  recovery_die "RESTORE_VERIFICATION_FAILED: RLS check failed"
fi

FINISHED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
DURATION="$((SECONDS - START_EPOCH))"

write_evidence \
  "RESTORE_DRILL_PROVEN" \
  "staging backup restored and verified on disposable target" \
  "$STARTED_AT" "$FINISHED_AT" "$DURATION" \
  "$BACKUP_ID" "$BACKUP_SHA" "$BACKUP_SIZE" "$SOURCE_REF" "$SOURCE_TIP" "$TARGET_REF" \
  "$MARKER_RECORDED" "PASS" "PASS" "PASS"

log "RESTORE_DRILL_PROVEN — duration ${DURATION}s — evidence ${RECOVERY_EVIDENCE_PATH}"
