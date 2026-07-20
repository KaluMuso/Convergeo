#!/usr/bin/env bash
# Vergeo5 nightly logical database dump → gzip → OCI Object Storage (or local dir for drills).
#
# Produces:
#   - vergeo5-<UTC-ts>.sql.gz          (logical dump; TLS in transit when DSN uses sslmode)
#   - vergeo5-<UTC-ts>.manifest.json   (metadata + SHA-256; no secrets / no row data)
#
# Exit codes:
#   0  success
#   1  hard failure (dump/upload/checksum/empty)
#   2  configuration error (missing tools / env)
#
# Never logs passwords, service-role keys, or full connection strings.
set -euo pipefail

BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
BACKUP_LOCAL_DIR="${BACKUP_LOCAL_DIR:-/var/backups/vergeo5}"
OCI_OBJECT_PREFIX="${OCI_OBJECT_PREFIX:-db/}"
SKIP_OCI_UPLOAD="${SKIP_OCI_UPLOAD:-0}"
# Implausibly-small floor for a gzip logical dump of a populated Vergeo5 DB.
# Override for empty local fixtures: BACKUP_MIN_BYTES=256
BACKUP_MIN_BYTES="${BACKUP_MIN_BYTES:-10240}"
BACKUP_ENV_ID="${BACKUP_ENV_ID:-${ENV:-unknown}}"
BACKUP_MODE="${BACKUP_MODE:-scheduled}" # scheduled | manual | drill

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
    exit 2
  fi
}

resolve_db_url() {
  local url="${SUPABASE_DB_URL:-${DATABASE_URL:-}}"
  if [[ -z "$url" ]]; then
    log "ERROR: SUPABASE_DB_URL or DATABASE_URL must be set"
    exit 2
  fi
  # Prefer TLS for remote Supabase/Postgres when the DSN omits sslmode.
  if [[ "${url}" != *"sslmode="* && "${url}" == *"supabase"* ]]; then
    if [[ "${url}" == *"?"* ]]; then
      url="${url}&sslmode=require"
    else
      url="${url}?sslmode=require"
    fi
  fi
  printf '%s' "$url"
}

migration_tip() {
  local url="$1"
  # Best-effort: latest supabase_migrations.schema_migrations version (no row data).
  if ! command -v psql >/dev/null 2>&1; then
    printf 'unknown'
    return 0
  fi
  local tip
  tip="$(
    psql "${url}" -v ON_ERROR_STOP=1 -tA -c \
      "SELECT version FROM supabase_migrations.schema_migrations ORDER BY version DESC LIMIT 1;" \
      2>/dev/null || true
  )"
  tip="$(printf '%s' "${tip}" | tr -d '[:space:]')"
  if [[ -z "${tip}" ]]; then
    printf 'unknown'
  else
    printf '%s' "${tip}"
  fi
}

write_manifest() {
  local path="$1"
  local status="$2"
  local dump_name="$3"
  local size_bytes="$4"
  local sha256="$5"
  local tip="$6"
  local object_key="$7"
  local timestamp="$8"
  local err="${9:-}"

  # jq-free JSON (values are controlled; no secrets).
  cat >"${path}" <<EOF
{
  "timestamp_utc": "${timestamp}",
  "env_id": "$(printf '%s' "${BACKUP_ENV_ID}" | sed 's/"/\\"/g')",
  "backup_mode": "$(printf '%s' "${BACKUP_MODE}" | sed 's/"/\\"/g')",
  "dump_name": "${dump_name}",
  "object_key": "$(printf '%s' "${object_key}" | sed 's/"/\\"/g')",
  "migration_tip": "$(printf '%s' "${tip}" | sed 's/"/\\"/g')",
  "size_bytes": ${size_bytes},
  "sha256": "${sha256}",
  "retention_days": ${BACKUP_RETENTION_DAYS},
  "status": "${status}",
  "error": "$(printf '%s' "${err}" | sed 's/"/\\"/g' | head -c 200)"
}
EOF
}

prune_oci_objects() {
  local cutoff_epoch
  cutoff_epoch="$(date -u -d "-${BACKUP_RETENTION_DAYS} days" +%s 2>/dev/null \
    || date -u -v-"${BACKUP_RETENTION_DAYS}"d +%s)"

  log "Pruning OCI objects older than ${BACKUP_RETENTION_DAYS} days (prefix=${OCI_OBJECT_PREFIX})"

  while IFS= read -r line; do
    [[ -z "${line}" ]] && continue
    local name modified
    name="$(printf '%s' "${line}" | awk '{print $1}')"
    modified="$(printf '%s' "${line}" | awk '{print $2}')"
    # Safety: only delete objects under our prefix that match the dump/manifest naming.
    case "${name}" in
      "${OCI_OBJECT_PREFIX}"vergeo5-*.sql.gz | "${OCI_OBJECT_PREFIX}"vergeo5-*.manifest.json) ;;
      *)
        log "Skipping unexpected object during prune: ${name}"
        continue
        ;;
    esac
    local modified_epoch
    modified_epoch="$(date -u -d "${modified}" +%s 2>/dev/null \
      || date -u -j -f '%Y-%m-%dT%H:%M:%S' "${modified%%.*}" +%s 2>/dev/null \
      || echo 0)"
    if [[ "${modified_epoch}" -gt 0 && "${modified_epoch}" -lt "${cutoff_epoch}" ]]; then
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
}

main() {
  require_cmd pg_dump
  require_cmd gzip
  if ! command -v sha256sum >/dev/null 2>&1 && ! command -v shasum >/dev/null 2>&1; then
    log "ERROR: required command not found: sha256sum or shasum"
    exit 2
  fi

  local db_url
  db_url="$(resolve_db_url)"
  local timestamp
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  local dump_name="vergeo5-${timestamp}.sql.gz"
  local manifest_name="vergeo5-${timestamp}.manifest.json"
  local local_path="${BACKUP_LOCAL_DIR}/${dump_name}"
  local manifest_path="${BACKUP_LOCAL_DIR}/${manifest_name}"
  local object_key=""
  local tip="unknown"
  local size_bytes=0
  local sha256="missing"
  local status="failure"
  local err=""

  mkdir -p "${BACKUP_LOCAL_DIR}"

  cleanup_failed_local() {
    # Leave failed dumps for operator inspection briefly; still write a failure manifest.
    write_manifest "${manifest_path}" "failure" "${dump_name}" "${size_bytes}" "${sha256}" \
      "${tip}" "${object_key}" "${timestamp}" "${err}"
    log "Wrote failure manifest: ${manifest_path}"
    # Machine-readable last line for n8n SSH stdout parsers (no secrets).
    printf 'BACKUP_MANIFEST_JSON=%s\n' "$(tr -d '\n' <"${manifest_path}")"
  }
  trap 'if [[ "${status}" != "success" ]]; then cleanup_failed_local; fi' EXIT

  tip="$(migration_tip "${db_url}")"
  log "Starting pg_dump (mode=${BACKUP_MODE} env=${BACKUP_ENV_ID} tip=${tip} target=$(redact_url "${db_url}"))"

  if ! pg_dump \
    --no-owner \
    --no-privileges \
    --format=plain \
    "${db_url}" | gzip -c >"${local_path}"; then
    err="pg_dump_failed"
    log "ERROR: pg_dump failed"
    exit 1
  fi

  size_bytes="$(wc -c <"${local_path}" | tr -d ' ')"
  if [[ "${size_bytes}" -lt "${BACKUP_MIN_BYTES}" ]]; then
    err="backup_too_small:${size_bytes}<${BACKUP_MIN_BYTES}"
    log "ERROR: dump implausibly small (${size_bytes} bytes < ${BACKUP_MIN_BYTES})"
    exit 1
  fi

  if command -v sha256sum >/dev/null 2>&1; then
    sha256="$(sha256sum "${local_path}" | awk '{print $1}')"
  else
    sha256="$(shasum -a 256 "${local_path}" | awk '{print $1}')"
  fi

  # Integrity: gzip -t must succeed (catches truncated writes).
  if ! gzip -t "${local_path}"; then
    err="gzip_integrity_failed"
    log "ERROR: gzip integrity check failed"
    exit 1
  fi

  log "Wrote local dump: ${dump_name} (${size_bytes} bytes sha256=${sha256})"

  if [[ "${SKIP_OCI_UPLOAD}" == "1" ]]; then
    log "SKIP_OCI_UPLOAD=1 — skipping OCI upload (local/drill mode)"
    object_key="local://${local_path}"
  else
    require_cmd oci
    : "${OCI_NAMESPACE:?OCI_NAMESPACE must be set}"
    : "${OCI_BUCKET_NAME:?OCI_BUCKET_NAME must be set}"

    object_key="${OCI_OBJECT_PREFIX}${dump_name}"
    log "Uploading dump to oci://${OCI_BUCKET_NAME}/${object_key} (HTTPS / encryption in transit)"
    if ! oci os object put \
      --namespace "${OCI_NAMESPACE}" \
      --bucket-name "${OCI_BUCKET_NAME}" \
      --file "${local_path}" \
      --name "${object_key}" \
      ${OCI_CLI_PROFILE:+--profile "${OCI_CLI_PROFILE}"}; then
      err="oci_upload_failed"
      log "ERROR: OCI object put failed"
      exit 1
    fi

    # Upload manifest after dump succeeds (retry-safe: unique timestamped names).
    write_manifest "${manifest_path}" "success" "${dump_name}" "${size_bytes}" "${sha256}" \
      "${tip}" "${object_key}" "${timestamp}" ""
    local manifest_object="${OCI_OBJECT_PREFIX}${manifest_name}"
    if ! oci os object put \
      --namespace "${OCI_NAMESPACE}" \
      --bucket-name "${OCI_BUCKET_NAME}" \
      --file "${manifest_path}" \
      --name "${manifest_object}" \
      ${OCI_CLI_PROFILE:+--profile "${OCI_CLI_PROFILE}"}; then
      err="oci_manifest_upload_failed"
      log "ERROR: OCI manifest put failed"
      exit 1
    fi

    prune_oci_objects
  fi

  # Local retention (named dumps + manifests only).
  find "${BACKUP_LOCAL_DIR}" -type f \( -name 'vergeo5-*.sql.gz' -o -name 'vergeo5-*.manifest.json' \) \
    -mtime "+${BACKUP_RETENTION_DAYS}" -delete

  status="success"
  trap - EXIT
  write_manifest "${manifest_path}" "success" "${dump_name}" "${size_bytes}" "${sha256}" \
    "${tip}" "${object_key}" "${timestamp}" ""

  log "Backup completed: ${dump_name}"
  printf 'BACKUP_MANIFEST_JSON=%s\n' "$(tr -d '\n' <"${manifest_path}")"
}

main "$@"
