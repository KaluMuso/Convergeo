#!/usr/bin/env bash
# Fail-closed recovery drill guards (STG-REC-04).
#
# Hard-rejects production Supabase project refs and production database hosts as
# restore targets. No --force-production escape hatch.
#
# Source: infra/staging/forbidden-production-identifiers.env
# Keep in sync with services/api/app/core/recovery_guards.py
set -euo pipefail

_RECOVERY_GUARDS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_REPO_ROOT="$(cd "${_RECOVERY_GUARDS_DIR}/../../.." && pwd)"
_FORBIDDEN_FILE="${_REPO_ROOT}/infra/staging/forbidden-production-identifiers.env"

if [[ -f "${_FORBIDDEN_FILE}" ]]; then
  # shellcheck disable=SC1090
  set -a
  # shellcheck source=/dev/null
  source "${_FORBIDDEN_FILE}"
  set +a
fi

PROD_SUPABASE_PROJECT_REF="${PROD_SUPABASE_PROJECT_REF:-dpadrlxukcjbewpqympu}"
STAGING_SUPABASE_PROJECT_REF="${STAGING_SUPABASE_PROJECT_REF:-iyasmrmbcrvlfxpzescb}"

recovery_die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

recovery_redact_url() {
  sed -E 's#(://[^:/]+:)[^@]+@#\1***@#' <<<"${1:-}"
}

recovery_extract_supabase_ref() {
  local raw="${1:-}"
  raw="${raw#postgresql://}"
  raw="${raw#postgres://}"
  raw="${raw#https://}"
  raw="${raw#http://}"

  local userpass="${raw%%@*}"
  local user="${userpass%%:*}"
  if [[ "$user" =~ ^postgres\.([a-z0-9]{20})$ ]]; then
    printf '%s' "${BASH_REMATCH[1]}"
    return 0
  fi

  local host="${raw#*@}"
  host="${host%%/*}"
  host="${host%%:*}"
  host="${host%%@*}"
  host="$(printf '%s' "$host" | tr '[:upper:]' '[:lower:]')"
  if [[ "$host" =~ ^db\.([a-z0-9]{20})\.supabase\.co$ ]]; then
    printf '%s' "${BASH_REMATCH[1]}"
    return 0
  fi
  if [[ "$host" == *pooler.supabase.com ]]; then
    printf ''
    return 0
  fi
  if [[ "$host" =~ ^([a-z0-9]{20})\.supabase\. ]]; then
    printf '%s' "${BASH_REMATCH[1]}"
    return 0
  fi
  if [[ "$raw" =~ ^[a-z0-9]{20}$ ]]; then
    printf '%s' "$raw"
    return 0
  fi
  printf ''
}

recovery_extract_db_host() {
  local raw="${1:-}"
  raw="${raw#postgresql://}"
  raw="${raw#postgres://}"
  local hostport="${raw#*@}"
  hostport="${hostport%%/*}"
  printf '%s' "${hostport%%:*}" | tr '[:upper:]' '[:lower:]'
}

recovery_db_name_of() {
  sed -E 's#^.*/([^/?]+)(\?.*)?$#\1#' <<<"${1:-}"
}

recovery_is_production_db_host() {
  local host
  host="$(recovery_extract_db_host "$1")"
  [[ "$host" == "db.${PROD_SUPABASE_PROJECT_REF}.supabase.co" ]]
}

recovery_is_production_project_ref() {
  local ref="${1:-}"
  [[ "$(printf '%s' "$ref" | tr '[:upper:]' '[:lower:]')" == "$PROD_SUPABASE_PROJECT_REF" ]]
}

recovery_is_production_restore_target() {
  local db_url="${1:-}"
  local project_ref="${2:-}"
  if [[ -n "$project_ref" ]] && recovery_is_production_project_ref "$project_ref"; then
    return 0
  fi
  if recovery_is_production_db_host "$db_url"; then
    return 0
  fi
  local resolved
  resolved="$(recovery_extract_supabase_ref "$db_url")"
  if [[ -n "$resolved" ]] && recovery_is_production_project_ref "$resolved"; then
    return 0
  fi
  return 1
}

# Assert restore target is safe. Sets RECOVERY_GUARD_DETAIL on failure.
recovery_assert_restore_target_safe() {
  local source_url="${1:-}"
  local target_url="${2:-}"
  local source_ref="${3:-}"
  local target_ref="${4:-}"

  if [[ -z "$target_url" ]]; then
    recovery_die "RESTORE_TARGET_AUTHORIZATION_REQUIRED: restore target URL is missing"
  fi

  if recovery_is_production_restore_target "$target_url" "$target_ref"; then
    recovery_die "RESTORE_FAILED: refusing production restore target (${PROD_SUPABASE_PROJECT_REF})"
  fi

  if [[ -z "$source_url" ]]; then
    recovery_die "RESTORE_FAILED: source database URL is missing"
  fi

  if [[ "$source_url" == "$target_url" ]]; then
    recovery_die "RESTORE_FAILED: source and target URLs are identical — refusing to clobber the source"
  fi

  if [[ -z "$source_ref" ]]; then
    source_ref="$(recovery_extract_supabase_ref "$source_url")"
  fi
  if [[ -z "$target_ref" ]]; then
    target_ref="$(recovery_extract_supabase_ref "$target_url")"
  fi

  if [[ -n "$source_ref" && -n "$target_ref" && "$source_ref" == "$target_ref" ]]; then
    local source_db target_db
    source_db="$(recovery_db_name_of "$source_url")"
    target_db="$(recovery_db_name_of "$target_url")"
    if [[ -n "$source_db" && -n "$target_db" && "$source_db" == "$target_db" ]]; then
      recovery_die "RESTORE_FAILED: source and target resolve to the same project and database — refusing destructive restore on the active plane"
    fi
  fi
}

recovery_verify_backup_checksum() {
  local path="${1:-}"
  local expected="${2:-}"
  [[ -f "$path" ]] || recovery_die "RESTORE_FAILED: backup file not found: ${path}"
  [[ -n "$expected" ]] || recovery_die "RESTORE_FAILED: backup checksum not provided"
  local actual
  actual="$(sha256sum "$path" | awk '{print $1}')"
  if [[ "$(printf '%s' "$expected" | tr '[:upper:]' '[:lower:]')" != "$actual" ]]; then
    recovery_die "RESTORE_FAILED: backup checksum mismatch"
  fi
}
