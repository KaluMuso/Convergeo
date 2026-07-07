#!/usr/bin/env bash
# Vergeo5 nightly logical database dump → gzip → OCI Object Storage (or local dir for drills).
set -euo pipefail

BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
BACKUP_LOCAL_DIR="${BACKUP_LOCAL_DIR:-/var/backups/vergeo5}"
OCI_OBJECT_PREFIX="${OCI_OBJECT_PREFIX:-db/}"
SKIP_OCI_UPLOAD="${SKIP_OCI_UPLOAD:-0}"

log() {
  printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2
}

redact_url() {
  # Redact password in postgres URLs for logs.
  printf '%s' "$1" | sed -E 's#(://[^:/]+:)[^@]+@#\1***@#'
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    log "ERROR: required command not found: $1"
    exit 1
  fi
}

resolve_db_url() {
  local url="${SUPABASE_DB_URL:-${DATABASE_URL:-}}"
  if [[ -z "$url" ]]; then
    log "ERROR: SUPABASE_DB_URL or DATABASE_URL must be set"
    exit 1
  fi
  printf '%s' "$url"
}

main() {
  require_cmd pg_dump
  require_cmd gzip

  local db_url
  db_url="$(resolve_db_url)"
  local timestamp
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  local dump_name="vergeo5-${timestamp}.sql.gz"
  local local_path="${BACKUP_LOCAL_DIR}/${dump_name}"

  mkdir -p "${BACKUP_LOCAL_DIR}"

  log "Starting pg_dump (target=$(redact_url "${db_url}"))"
  if ! pg_dump "${db_url}" | gzip -c >"${local_path}"; then
    log "ERROR: pg_dump failed"
    exit 1
  fi

  log "Wrote local dump: ${local_path} ($(wc -c <"${local_path}") bytes)"

  if [[ "${SKIP_OCI_UPLOAD}" == "1" ]]; then
    log "SKIP_OCI_UPLOAD=1 — skipping OCI upload"
  else
    require_cmd oci
    : "${OCI_NAMESPACE:?OCI_NAMESPACE must be set}"
    : "${OCI_BUCKET_NAME:?OCI_BUCKET_NAME must be set}"

    local object_name="${OCI_OBJECT_PREFIX}${dump_name}"
    log "Uploading to oci://${OCI_BUCKET_NAME}/${object_name}"
    oci os object put \
      --namespace "${OCI_NAMESPACE}" \
      --bucket-name "${OCI_BUCKET_NAME}" \
      --file "${local_path}" \
      --name "${object_name}" \
      ${OCI_CLI_PROFILE:+--profile "${OCI_CLI_PROFILE}"}

    log "Pruning objects older than ${BACKUP_RETENTION_DAYS} days"
    local cutoff_epoch
    cutoff_epoch="$(date -u -d "-${BACKUP_RETENTION_DAYS} days" +%s)"

    while IFS= read -r line; do
      [[ -z "${line}" ]] && continue
      local name modified
      name="$(printf '%s' "${line}" | awk '{print $1}')"
      modified="$(printf '%s' "${line}" | awk '{print $2}')"
      local modified_epoch
      modified_epoch="$(date -u -d "${modified}" +%s 2>/dev/null || echo 0)"
      if [[ "${modified_epoch}" -lt "${cutoff_epoch}" ]]; then
        log "Deleting expired object: ${name}"
        oci os object delete \
          --namespace "${OCI_NAMESPACE}" \
          --bucket-name "${OCI_BUCKET_NAME}" \
          --name "${name}" \
          --force \
          ${OCI_CLI_PROFILE:+--profile "${OCI_CLI_PROFILE}"}
      fi
    done < <(
      oci os object list \
        --namespace "${OCI_NAMESPACE}" \
        --bucket-name "${OCI_BUCKET_NAME}" \
        --prefix "${OCI_OBJECT_PREFIX}" \
        --fields name,timeCreated \
        --all \
        ${OCI_CLI_PROFILE:+--profile "${OCI_CLI_PROFILE}"} \
        --query 'data[*].[name,"time-created"]' \
        --raw-output 2>/dev/null | tr '\t' ' ' || true
    )
  fi

  # Local retention
  find "${BACKUP_LOCAL_DIR}" -type f -name 'vergeo5-*.sql.gz' -mtime "+${BACKUP_RETENTION_DAYS}" -delete

  log "Backup completed: ${dump_name}"
}

main "$@"
