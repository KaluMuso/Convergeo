#!/usr/bin/env bash
# check_prod_drift.sh — read-only migration drift check (local repo vs remote ledger).
#
# Compares filenames under supabase/migrations/00*.sql against
# supabase_migrations.schema_migrations.name on a linked Supabase/Postgres database.
# Matches on migration *name* (e.g. 0072_waha_intake_flag), not the version key,
# so timestamp-shaped ledger rows (historical RC-02 skew) do not false-negative.
#
# Never prints passwords, service-role keys, or full connection strings.
#
# Usage:
#   SUPABASE_DB_URL=postgresql://... bash scripts/check_prod_drift.sh
#   DATABASE_URL=... bash scripts/check_prod_drift.sh
#   PGHOST=... PGPORT=... PGUSER=... PGPASSWORD=... PGDATABASE=... \
#     bash scripts/check_prod_drift.sh
#   bash scripts/check_prod_drift.sh --local-only   # list repo ledger only (no network)
#
# Exit codes:
#   0  parity — no pending migrations
#   1  drift — one or more local migrations not applied remotely
#   2  configuration or connection error
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MIGRATIONS_DIR="${REPO_ROOT}/supabase/migrations"

LOCAL_ONLY=0
JSON_OUT=0

log()  { printf '%s\n' "$*" >&2; }
die()  { log "ERROR: $*"; exit 2; }

usage() {
  sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --local-only) LOCAL_ONLY=1; shift ;;
    --json) JSON_OUT=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1 (try --help)" ;;
  esac
done

redact_dsn() {
  # Redact user:password in postgres URLs for operator logs.
  printf '%s' "$1" | sed -E 's#(://[^:/]+:)[^@]+@#\1***@#;s#(password=)[^& ]+#\1***#gi'
}

resolve_db_url() {
  local url="${SUPABASE_DB_URL:-${DATABASE_URL:-}}"
  if [[ -n "$url" ]]; then
    if [[ "${url}" != *"sslmode="* && "${url}" == *"supabase"* ]]; then
      if [[ "${url}" == *"?"* ]]; then
        url="${url}&sslmode=require"
      else
        url="${url}?sslmode=require"
      fi
    fi
    printf '%s' "$url"
    return 0
  fi
  if [[ -n "${PGHOST:-}" ]]; then
    : "${PGPORT:=5432}"
    : "${PGUSER:=postgres}"
    : "${PGDATABASE:=postgres}"
  export PGPASSWORD="${PGPASSWORD:-}"
    local qs="host=${PGHOST} port=${PGPORT} user=${PGUSER} dbname=${PGDATABASE}"
    if [[ -n "${PGPASSWORD}" ]]; then
      qs="${qs} password=${PGPASSWORD}"
    fi
    if [[ "${PGHOST}" == *"supabase"* ]]; then
      qs="${qs} sslmode=require"
    fi
    printf '%s' "$qs"
    return 0
  fi
  return 1
}

list_local_migrations() {
  shopt -s nullglob
  local f base
  for f in "${MIGRATIONS_DIR}"/00*.sql; do
    base="$(basename "${f}" .sql)"
    printf '%s\n' "${base}"
  done | sort
}

# Emit applied migration names from remote (one per line). Uses only env-injected DSN.
fetch_remote_names() {
  local db_url="$1"
  local err_file
  err_file="$(mktemp)"
  trap 'rm -f "$err_file"' RETURN

  if ! psql "${db_url}" -v ON_ERROR_STOP=1 -tA -c \
    "SELECT name FROM supabase_migrations.schema_migrations ORDER BY name;" \
    2>"${err_file}"; then
    sed 's/^/  /' "${err_file}" >&2
    die "psql query failed — check credentials/network (target=$(redact_dsn "${db_url}"))"
  fi
}

migration_prefix() {
  printf '%s' "$1" | sed -E 's/^([0-9]+).*/\1/'
}

main() {
  local -a local_names=()
  mapfile -t local_names < <(list_local_migrations)
  if [[ ${#local_names[@]} -eq 0 ]]; then
    die "no local migrations matching ${MIGRATIONS_DIR}/00*.sql"
  fi

  local repo_tip="${local_names[$((${#local_names[@]} - 1))]}"
  local repo_prefix
  repo_prefix="$(migration_prefix "${repo_tip}")"

  if [[ "${LOCAL_ONLY}" -eq 1 ]]; then
    log "LOCAL_ONLY — skipping remote query"
    printf 'REPO_COUNT=%s\n' "${#local_names[@]}"
    printf 'REPO_TIP=%s\n' "${repo_tip}"
    printf 'REPO_PREFIX=%s\n' "${repo_prefix}"
    log "LOCAL_MIGRATIONS:"
    printf '  %s\n' "${local_names[@]}"
    exit 0
  fi

  command -v psql >/dev/null 2>&1 || die "psql not on PATH"

  local db_url
  if ! db_url="$(resolve_db_url)"; then
    die "set SUPABASE_DB_URL, DATABASE_URL, or PGHOST/PGUSER/PGDATABASE (+ PGPASSWORD)"
  fi

  log "Target: $(redact_dsn "${db_url}")"
  log "Local migrations: ${#local_names[@]} (tip=${repo_tip})"

  local -a remote_names=()
  mapfile -t remote_names < <(fetch_remote_names "${db_url}")

  # Build lookup of applied names and numeric prefixes.
  local -A applied_name=()
  local -A applied_prefix=()
  local name prefix
  for name in "${remote_names[@]}"; do
    [[ -z "${name}" ]] && continue
    applied_name["${name}"]=1
    prefix="$(migration_prefix "${name}")"
    applied_prefix["${prefix}"]=1
  done

  local live_tip=""
  local live_prefix=""
  if [[ ${#remote_names[@]} -gt 0 ]]; then
    # Highest numeric prefix among applied names (not max(version) — avoids timestamp skew).
  local best=0
    for name in "${remote_names[@]}"; do
      prefix="$(migration_prefix "${name}")"
      if [[ "${prefix}" =~ ^[0-9]+$ && "${prefix}" -gt "${best}" ]]; then
        best="${prefix}"
        live_tip="${name}"
      fi
    done
    live_prefix="${best}"
  fi

  local -a pending=()
  local -a extra=()
  for name in "${local_names[@]}"; do
    prefix="$(migration_prefix "${name}")"
    if [[ -n "${applied_name[${name}]:-}" ]]; then
      continue
    fi
    if [[ -n "${applied_prefix[${prefix}]:-}" ]]; then
      # Prefix applied under a different filename (ledger rename / RC-02) — not pending.
      continue
    fi
    pending+=("${name}")
  done

  for name in "${remote_names[@]}"; do
    [[ -z "${name}" ]] && continue
    prefix="$(migration_prefix "${name}")"
    local found=0
    local local_name
    for local_name in "${local_names[@]}"; do
      if [[ "${local_name}" == "${name}" ]]; then
        found=1
        break
      fi
      if [[ "$(migration_prefix "${local_name}")" == "${prefix}" ]]; then
        found=1
        break
      fi
    done
    if [[ "${found}" -eq 0 ]]; then
      extra+=("${name}")
    fi
  done

  if [[ "${JSON_OUT}" -eq 1 ]]; then
    PENDING_JSON="$(printf '%s\n' "${pending[@]}")" \
    REPO_TIP="${repo_tip}" \
    LIVE_TIP="${live_tip}" \
    LIVE_PREFIX="${live_prefix}" \
    REPO_PREFIX="${repo_prefix}" \
    python3 - <<'PY'
import json, os
pending = [line for line in os.environ.get("PENDING_JSON", "").splitlines() if line]
payload = {
    "repo_tip": os.environ.get("REPO_TIP"),
    "live_tip": os.environ.get("LIVE_TIP") or None,
    "live_prefix": os.environ.get("LIVE_PREFIX") or None,
    "repo_prefix": os.environ.get("REPO_PREFIX"),
    "pending_count": len(pending),
    "pending": pending,
}
print(json.dumps(payload, indent=2))
PY
  else
    printf 'LIVE_TIP=%s\n' "${live_tip:-unknown}"
    printf 'LIVE_PREFIX=%s\n' "${live_prefix:-unknown}"
    printf 'REPO_TIP=%s\n' "${repo_tip}"
    printf 'REPO_PREFIX=%s\n' "${repo_prefix}"
    printf 'APPLIED_COUNT=%s\n' "${#remote_names[@]}"
    printf 'PENDING_COUNT=%s\n' "${#pending[@]}"
    if [[ ${#pending[@]} -gt 0 ]]; then
      printf 'PENDING:\n'
      printf '  %s\n' "${pending[@]}"
    else
      printf 'PENDING:\n'
      printf '  (none)\n'
    fi
    if [[ ${#extra[@]} -gt 0 ]]; then
      printf 'EXTRA_REMOTE_NOT_IN_REPO_COUNT=%s\n' "${#extra[@]}"
      printf 'EXTRA_REMOTE_NOT_IN_REPO:\n'
      printf '  %s\n' "${extra[@]}"
    fi
  fi

  if [[ ${#pending[@]} -gt 0 ]]; then
    exit 1
  fi
  exit 0
}

main "$@"
