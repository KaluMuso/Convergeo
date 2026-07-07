#!/usr/bin/env bash
# Restore a Vergeo5 logical dump into a target Postgres database.
set -euo pipefail

BACKUP_LOCAL_DIR="${BACKUP_LOCAL_DIR:-/var/backups/vergeo5}"
OCI_OBJECT_PREFIX="${OCI_OBJECT_PREFIX:-db/}"
FORCE_PROD=0
DUMP_FILE=""

log() {
  printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2
}

redact_url() {
  printf '%s' "$1" | sed -E 's#(://[^:/]+:)[^@]+@#\1***@#'
}

usage() {
  cat <<'EOF'
Usage: db-restore.sh [--file PATH | --latest] [--target-url URL] [--force]

Env:
  SUPABASE_DB_URL / DATABASE_URL  Target DB (if --target-url omitted)
  RESTORE_SOURCE_URL            Optional alternate target
  OCI_NAMESPACE, OCI_BUCKET_NAME, OCI_CLI_PROFILE (for --latest from bucket)

Guards:
  Refuses prod-looking URLs unless --force and interactive confirmation.
EOF
}

is_prod_url() {
  local url="$1"
  if [[ "${ENV:-}" == "production" ]]; then
    return 0
  fi
  case "${url}" in
    *prod* | *production* | *supabase.co*db.*prod* )
      return 0
      ;;
  esac
  return 1
}

resolve_target_url() {
  local url="${RESTORE_SOURCE_URL:-${SUPABASE_DB_URL:-${DATABASE_URL:-}}}"
  if [[ -z "${url}" ]]; then
    log "ERROR: set RESTORE_SOURCE_URL, SUPABASE_DB_URL, or DATABASE_URL"
    exit 1
  fi
  printf '%s' "${url}"
}

confirm_prod_restore() {
  log "WARNING: target appears to be production"
  if [[ "${FORCE_PROD}" -ne 1 ]]; then
    log "ERROR: pass --force and type RESTORE to continue"
    exit 1
  fi
  read -r -p "Type RESTORE to continue: " answer
  if [[ "${answer}" != "RESTORE" ]]; then
    log "Aborted"
    exit 1
  fi
}

download_latest_dump() {
  require_cmd oci
  : "${OCI_NAMESPACE:?OCI_NAMESPACE must be set}"
  : "${OCI_BUCKET_NAME:?OCI_BUCKET_NAME must be set}"

  local latest
  latest="$(
    oci os object list \
      --namespace "${OCI_NAMESPACE}" \
      --bucket-name "${OCI_BUCKET_NAME}" \
      --prefix "${OCI_OBJECT_PREFIX}" \
      --all \
      --sort-by timeCreated \
      --sort-order DESC \
      --limit 1 \
      --query 'data[0].name' \
      --raw-output \
      ${OCI_CLI_PROFILE:+--profile "${OCI_CLI_PROFILE}"}
  )"

  if [[ -z "${latest}" || "${latest}" == "null" ]]; then
    log "ERROR: no dump objects found in bucket"
    exit 1
  fi

  local dest="${BACKUP_LOCAL_DIR}/$(basename "${latest}")"
  mkdir -p "${BACKUP_LOCAL_DIR}"
  oci os object get \
    --namespace "${OCI_NAMESPACE}" \
    --bucket-name "${OCI_BUCKET_NAME}" \
    --name "${latest}" \
    --file "${dest}" \
    ${OCI_CLI_PROFILE:+--profile "${OCI_CLI_PROFILE}"}
  printf '%s' "${dest}"
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    log "ERROR: required command not found: $1"
    exit 1
  fi
}

main() {
  local target_url=""
  local use_latest=0

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --file)
        DUMP_FILE="$2"
        shift 2
        ;;
      --latest)
        use_latest=1
        shift
        ;;
      --target-url)
        target_url="$2"
        shift 2
        ;;
      --force)
        FORCE_PROD=1
        shift
        ;;
      -h | --help)
        usage
        exit 0
        ;;
      *)
        log "ERROR: unknown argument: $1"
        usage
        exit 1
        ;;
    esac
  done

  require_cmd psql
  require_cmd gunzip

  if [[ -z "${target_url}" ]]; then
    target_url="$(resolve_target_url)"
  fi

  if is_prod_url "${target_url}"; then
    confirm_prod_restore
  fi

  if [[ "${use_latest}" -eq 1 ]]; then
    DUMP_FILE="$(download_latest_dump)"
  fi

  if [[ -z "${DUMP_FILE}" ]]; then
    log "ERROR: specify --file or --latest"
    exit 1
  fi

  if [[ ! -f "${DUMP_FILE}" ]]; then
    log "ERROR: dump file not found: ${DUMP_FILE}"
    exit 1
  fi

  log "Restoring ${DUMP_FILE} into target=$(redact_url "${target_url}")"

  gunzip -c "${DUMP_FILE}" | psql "${target_url}" -v ON_ERROR_STOP=1

  log "Restore completed"
}

main "$@"
