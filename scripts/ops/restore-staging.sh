#!/usr/bin/env bash
#
# restore-staging.sh — Vergeo5 backup-restore drill (M15-P09).
#
# Proves a Vergeo5 Postgres backup can be restored into a FRESH database and passes
# smoke invariants. This is the mechanical core of the DR runbook's "DB loss" path
# (docs/ops/runbook-disaster-recovery.md §1) and is run on a schedule as the restore
# drill. It is SAFE to run against a scratch/staging target; it MUST NOT be pointed at
# production (guards below refuse the primary `postgres` DB and refuse to clobber the
# source).
#
# Flow:  pg_dump(SOURCE)  ->  drop+create fresh TARGET  ->  pg_restore  ->  smoke verify
#          (skip dump if --dump-file is given)
#
# Smoke verify = scripts/ops/restore-smoke.sql (core tables present, seed tables
# non-empty, migration ledger present) PLUS a migrations-current check that compares
# the restored ledger against supabase/migrations/ on disk. Any failure => exit non-zero.
#
# ------------------------------------------------------------------------------------
# Usage
#   # Dry run — print the plan, touch nothing (no DB, no creds needed):
#   bash scripts/ops/restore-staging.sh --dry-run
#
#   # Real local drill — dump SOURCE, restore into fresh TARGET, smoke:
#   SOURCE_DB_URL='postgresql://postgres:postgres@127.0.0.1:5433/vergeo_src' \
#   SUPABASE_DB_URL='postgresql://postgres:postgres@127.0.0.1:5433/vergeo_restore' \
#     bash scripts/ops/restore-staging.sh
#
#   # Restore an existing dump file (skip the dump step):
#   SUPABASE_DB_URL='postgresql://.../vergeo_restore' \
#     bash scripts/ops/restore-staging.sh --dump-file /path/to/nightly.dump
#
# Environment (secrets come from env ONLY — never hardcoded, never committed):
#   SUPABASE_DB_URL / TARGET_DB_URL   Fresh restore target (REQUIRED for a real run).
#   SOURCE_DB_URL                     DB to dump (REQUIRED unless --dump-file given).
#
# Flags:
#   --dry-run          Print the plan and exit 0 without mutating anything.
#   --dump-file PATH   Use an existing custom-format dump instead of dumping SOURCE.
#   --keep-dump        Do not delete the dump file taken during this run.
#   --keep-target      (default) Leave the restored target DB in place for inspection.
#   -h | --help        Show this help.
# ------------------------------------------------------------------------------------
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MIGRATIONS_DIR="${REPO_ROOT}/supabase/migrations"
SMOKE_SQL="${REPO_ROOT}/scripts/ops/restore-smoke.sql"

DRY_RUN=0
DUMP_FILE=""
KEEP_DUMP=0

log()  { printf '==> %s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

usage() { sed -n '2,60p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)      DRY_RUN=1; shift ;;
    --dump-file)    DUMP_FILE="${2:-}"; [[ -n "$DUMP_FILE" ]] || die "--dump-file needs a PATH"; shift 2 ;;
    --keep-dump)    KEEP_DUMP=1; shift ;;
    --keep-target)  shift ;;  # default; accepted for explicitness
    -h|--help)      usage; exit 0 ;;
    *)              die "unknown argument: $1 (see --help)" ;;
  esac
done

TARGET_URL="${SUPABASE_DB_URL:-${TARGET_DB_URL:-}}"
SOURCE_URL="${SOURCE_DB_URL:-}"

# --- URL helpers -------------------------------------------------------------------
# Parse the database name and a maintenance URL (same server, db=postgres) so we can
# DROP/CREATE the target. Query strings (e.g. ?sslmode=require) are preserved.
db_name_of() { sed -E 's#^.*/([^/?]+)(\?.*)?$#\1#' <<<"$1"; }
maint_url_of() { sed -E 's#/([^/?]+)(\?.*)?$#/postgres\2#' <<<"$1"; }

# --- Migration currency (filesystem side) ------------------------------------------
shopt -s nullglob
mapfile -t MIGRATION_FILES < <(find "${MIGRATIONS_DIR}" -maxdepth 1 -name '[0-9]*.sql' | sort)
[[ ${#MIGRATION_FILES[@]} -gt 0 ]] || die "no migrations found in ${MIGRATIONS_DIR}"
EXPECTED_COUNT=${#MIGRATION_FILES[@]}
LATEST_FILE="$(basename "${MIGRATION_FILES[-1]}")"
EXPECTED_LATEST="${LATEST_FILE%%_*}"

# --- Plan banner -------------------------------------------------------------------
log "Vergeo5 restore drill"
log "repo:            ${REPO_ROOT}"
log "migrations dir:  ${MIGRATIONS_DIR} (${EXPECTED_COUNT} files, latest ${EXPECTED_LATEST})"
log "smoke sql:       ${SMOKE_SQL}"
if [[ -n "$DUMP_FILE" ]]; then
  log "source:          <dump file> ${DUMP_FILE}"
else
  log "source:          \$SOURCE_DB_URL $( [[ -n "$SOURCE_URL" ]] && echo '(set)' || echo '(UNSET)')"
fi
log "target:          \$SUPABASE_DB_URL/\$TARGET_DB_URL $( [[ -n "$TARGET_URL" ]] && echo '(set)' || echo '(UNSET)')"

PLAN_DUMP="${DUMP_FILE:-<tmp>/vergeo-restore-\$ts.dump}"
cat <<PLAN

Planned steps:
  1. $( [[ -n "$DUMP_FILE" ]] && echo "reuse dump ${DUMP_FILE}" \
        || echo "pg_dump --format=custom --no-owner --no-privileges \"\$SOURCE_DB_URL\" -f ${PLAN_DUMP}" )
  2. psql "<maintenance>" -c 'DROP DATABASE IF EXISTS <target>' -c 'CREATE DATABASE <target>'
  3. pg_restore --no-owner --no-privileges --exit-on-error -d "\$TARGET_DB_URL" ${PLAN_DUMP}
  4. psql -v ON_ERROR_STOP=1 "\$TARGET_DB_URL" -f ${SMOKE_SQL}
  5. assert migration ledger count/latest == ${EXPECTED_COUNT}/${EXPECTED_LATEST}

PLAN

if [[ "$DRY_RUN" -eq 1 ]]; then
  log "DRY RUN — no dump taken, no database created or modified."
  exit 0
fi

# --- Real run: validate inputs -----------------------------------------------------
[[ -n "$TARGET_URL" ]] || die "SUPABASE_DB_URL (or TARGET_DB_URL) is required for a real run"
if [[ -z "$DUMP_FILE" && -z "$SOURCE_URL" ]]; then
  die "SOURCE_DB_URL is required (or pass --dump-file PATH)"
fi
command -v pg_dump    >/dev/null || die "pg_dump not on PATH"
command -v pg_restore >/dev/null || die "pg_restore not on PATH"
command -v psql       >/dev/null || die "psql not on PATH"
[[ -f "$SMOKE_SQL" ]] || die "smoke sql missing: ${SMOKE_SQL}"

TARGET_DB="$(db_name_of "$TARGET_URL")"
MAINT_URL="$(maint_url_of "$TARGET_URL")"
[[ -n "$TARGET_DB" ]] || die "could not parse target db name from SUPABASE_DB_URL"

# --- Safety guards (never clobber production or the source) -------------------------
case "$TARGET_DB" in
  postgres|template0|template1|"")
    die "refusing to use '${TARGET_DB}' as a restore target — point at a scratch DB" ;;
esac
if [[ -n "$SOURCE_URL" && "$SOURCE_URL" == "$TARGET_URL" ]]; then
  die "SOURCE_DB_URL and target are identical — refusing to clobber the source"
fi

# --- Temp dump handling ------------------------------------------------------------
TMP_DUMP=""
cleanup() {
  if [[ -n "$TMP_DUMP" && -f "$TMP_DUMP" && "$KEEP_DUMP" -eq 0 ]]; then
    rm -f "$TMP_DUMP"
  fi
}
trap cleanup EXIT

# --- 1. Obtain the dump ------------------------------------------------------------
if [[ -n "$DUMP_FILE" ]]; then
  [[ -f "$DUMP_FILE" ]] || die "dump file not found: ${DUMP_FILE}"
  DUMP="$DUMP_FILE"
  log "using existing dump: ${DUMP}"
else
  TMP_DUMP="$(mktemp "${TMPDIR:-/tmp}/vergeo-restore-XXXXXX.dump")"
  DUMP="$TMP_DUMP"
  log "dumping source -> ${DUMP}"
  t0=$SECONDS
  pg_dump --format=custom --no-owner --no-privileges "$SOURCE_URL" -f "$DUMP"
  log "dump complete in $((SECONDS - t0))s ($(du -h "$DUMP" | cut -f1))"
fi

# --- 2. Fresh target ---------------------------------------------------------------
log "recreating fresh target database '${TARGET_DB}'"
# DROP/CREATE cannot share a transaction; separate -c statements run autocommit.
psql -v ON_ERROR_STOP=1 "$MAINT_URL" \
  -c "DROP DATABASE IF EXISTS \"${TARGET_DB}\" WITH (FORCE)" \
  -c "CREATE DATABASE \"${TARGET_DB}\""

# --- 3. Restore --------------------------------------------------------------------
log "restoring into '${TARGET_DB}'"
t0=$SECONDS
# pgvector/pg_trgm extensions in the dump require their libraries on the target server.
pg_restore --no-owner --no-privileges --exit-on-error -d "$TARGET_URL" "$DUMP"
log "restore complete in $((SECONDS - t0))s"

# --- 4. Smoke invariants (structural + seed + ledger present) ----------------------
log "running smoke invariants (${SMOKE_SQL})"
psql -v ON_ERROR_STOP=1 "$TARGET_URL" -f "$SMOKE_SQL"

# --- 5. Migrations-current check (restored ledger vs repo filesystem) --------------
log "asserting migration ledger is current vs supabase/migrations/"
LEDGER_PRESENT="$(psql -tA "$TARGET_URL" \
  -c "SELECT to_regclass('supabase_migrations.schema_migrations') IS NOT NULL")"
if [[ "$LEDGER_PRESENT" == "t" ]]; then
  read -r ACTUAL_COUNT ACTUAL_LATEST < <(psql -tA -F' ' "$TARGET_URL" \
    -c "SELECT count(*), coalesce(max(version),'') FROM supabase_migrations.schema_migrations")
  log "ledger: ${ACTUAL_COUNT} rows, latest ${ACTUAL_LATEST}  |  repo: ${EXPECTED_COUNT}, ${EXPECTED_LATEST}"
  [[ "$ACTUAL_LATEST" == "$EXPECTED_LATEST" ]] \
    || die "migrations NOT current: restored latest ${ACTUAL_LATEST} != repo ${EXPECTED_LATEST}"
  if [[ "$ACTUAL_COUNT" -lt "$EXPECTED_COUNT" ]]; then
    die "migrations NOT current: restored ${ACTUAL_COUNT} rows < repo ${EXPECTED_COUNT} files"
  fi
  log "migrations current: latest ${ACTUAL_LATEST} matches repo, ledger >= repo count"
else
  warn "no supabase_migrations.schema_migrations in restore — smoke verified the 0029"
  warn "marker only; migration-currency vs repo could NOT be asserted for this dump."
fi

log "RESTORE DRILL PASSED — target '${TARGET_DB}' restored and smoke-verified."
