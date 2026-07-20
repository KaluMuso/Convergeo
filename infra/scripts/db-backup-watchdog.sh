#!/usr/bin/env bash
# Missed-schedule / destination health check for Vergeo5 DB backups.
#
# Fails (exit 1) when the newest dump object under OCI_OBJECT_PREFIX is older than
# BACKUP_MAX_AGE_HOURS (default 26h — nightly RPO + small slack). Used by the n8n
# backup workflow's morning watchdog schedule.
#
# Never logs secrets. Prints a short status line for n8n parsers.
set -euo pipefail

OCI_OBJECT_PREFIX="${OCI_OBJECT_PREFIX:-db/}"
BACKUP_MAX_AGE_HOURS="${BACKUP_MAX_AGE_HOURS:-26}"
SKIP_OCI_UPLOAD="${SKIP_OCI_UPLOAD:-0}"
BACKUP_LOCAL_DIR="${BACKUP_LOCAL_DIR:-/var/backups/vergeo5}"

log() {
  printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    log "ERROR: required command not found: $1"
    exit 2
  fi
}

newest_local_epoch() {
  local newest=""
  # Newest by mtime; avoid `ls` (SC2012). Portable via epoch prefix + sort.
  newest="$(
    find "${BACKUP_LOCAL_DIR}" -maxdepth 1 -type f -name 'vergeo5-*.sql.gz' 2>/dev/null \
      | while IFS= read -r f; do
          ts="$(stat -c %Y "${f}" 2>/dev/null || stat -f %m "${f}" 2>/dev/null || printf '0')"
          printf '%s\t%s\n' "${ts}" "${f}"
        done \
      | sort -nr \
      | head -n 1 \
      | cut -f2-
  )"
  if [[ -z "${newest}" ]]; then
    printf '0'
    return 0
  fi
  # GNU stat first, BSD fallback.
  stat -c %Y "${newest}" 2>/dev/null || stat -f %m "${newest}" 2>/dev/null || printf '0'
}

newest_oci_epoch() {
  require_cmd oci
  : "${OCI_NAMESPACE:?OCI_NAMESPACE must be set}"
  : "${OCI_BUCKET_NAME:?OCI_BUCKET_NAME must be set}"

  local raw name modified
  # JMESPath uses backticks; must stay single-quoted (not shell expansion).
  # shellcheck disable=SC2016
  raw="$(
    oci os object list \
      --namespace "${OCI_NAMESPACE}" \
      --bucket-name "${OCI_BUCKET_NAME}" \
      --prefix "${OCI_OBJECT_PREFIX}" \
      --all \
      --sort-by timeCreated \
      --sort-order DESC \
      --limit 20 \
      ${OCI_CLI_PROFILE:+--profile "${OCI_CLI_PROFILE}"} \
      --query 'data[?ends_with(name, `.sql.gz`)].[name,"time-created"] | [0]' \
      --raw-output 2>/dev/null || true
  )"
  name="$(printf '%s' "${raw}" | awk '{print $1}')"
  modified="$(printf '%s' "${raw}" | awk '{print $2}')"
  if [[ -z "${name}" || "${name}" == "null" ]]; then
    log "ERROR: no .sql.gz dump objects found under ${OCI_OBJECT_PREFIX}"
    printf '0'
    return 0
  fi
  log "Newest dump object: ${name} timeCreated=${modified}"
  date -u -d "${modified}" +%s 2>/dev/null \
    || date -u -j -f '%Y-%m-%dT%H:%M:%S' "${modified%%.*}" +%s 2>/dev/null \
    || printf '0'
}

main() {
  local now_epoch newest_epoch age_hours max_age_seconds
  now_epoch="$(date -u +%s)"
  max_age_seconds=$((BACKUP_MAX_AGE_HOURS * 3600))

  if [[ "${SKIP_OCI_UPLOAD}" == "1" ]]; then
    newest_epoch="$(newest_local_epoch)"
  else
    newest_epoch="$(newest_oci_epoch)"
  fi

  if [[ "${newest_epoch}" -le 0 ]]; then
    log "ERROR: no usable backup found (destination failure or never ran)"
    printf 'BACKUP_WATCHDOG_STATUS=missing\n'
    exit 1
  fi

  age_hours=$(( (now_epoch - newest_epoch) / 3600 ))
  if [[ $((now_epoch - newest_epoch)) -gt "${max_age_seconds}" ]]; then
    log "ERROR: newest backup is ${age_hours}h old (limit ${BACKUP_MAX_AGE_HOURS}h) — missed schedule"
    printf 'BACKUP_WATCHDOG_STATUS=stale age_hours=%s\n' "${age_hours}"
    exit 1
  fi

  log "Watchdog OK — newest backup age≈${age_hours}h (limit ${BACKUP_MAX_AGE_HOURS}h)"
  printf 'BACKUP_WATCHDOG_STATUS=ok age_hours=%s\n' "${age_hours}"
}

main "$@"
