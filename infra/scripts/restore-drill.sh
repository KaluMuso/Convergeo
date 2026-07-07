#!/usr/bin/env bash
# End-to-end backup/restore drill: seed → dump → wipe → restore → assert.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRILL_DIR="${DRILL_DIR:-/tmp/vergeo5-restore-drill}"
DRILL_MARKER_VALUE="${DRILL_MARKER_VALUE:-vergeo5-drill-$(date +%s)}"
PG_IMAGE="${PG_IMAGE:-postgres:16-alpine}"
PG_PORT="${PG_PORT:-55432}"
PG_DATA_DIR=""
PG_CTL_BIN=""

log() {
  printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    log "ERROR: required command: $1"
    exit 1
  fi
}

find_pg_bin() {
  local name="$1"
  if command -v "${name}" >/dev/null 2>&1; then
    command -v "${name}"
    return 0
  fi
  local candidate
  for candidate in /usr/lib/postgresql/*/bin/"${name}"; do
    if [[ -x "${candidate}" ]]; then
      printf '%s' "${candidate}"
      return 0
    fi
  done
  return 1
}

find_pg_ctl() {
  PG_CTL_BIN="$(find_pg_bin pg_ctl)" || return 1
}

cleanup() {
  if [[ -n "${PG_CONTAINER:-}" ]]; then
    docker rm -f "${PG_CONTAINER}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${PG_DATA_DIR}" && -d "${PG_DATA_DIR}" ]]; then
    if [[ -n "${PG_CTL_BIN}" ]]; then
      "${PG_CTL_BIN}" -D "${PG_DATA_DIR}" -m fast stop >/dev/null 2>&1 || true
    fi
    rm -rf "${PG_DATA_DIR}"
  fi
}

wait_for_postgres() {
  local url="$1"
  for _ in $(seq 1 30); do
    if psql "${url}" -c 'SELECT 1' >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

start_postgres_docker() {
  require_cmd docker
  if ! docker info >/dev/null 2>&1; then
    return 1
  fi

  PG_CONTAINER="vergeo5-drill-pg-$$"
  if ! docker run -d --rm \
    --name "${PG_CONTAINER}" \
    -e POSTGRES_PASSWORD=drillpass \
    -e POSTGRES_DB=vergeo5_drill \
    -p "${PG_PORT}:5432" \
    "${PG_IMAGE}" >/dev/null 2>&1; then
    docker rm -f "${PG_CONTAINER}" >/dev/null 2>&1 || true
    unset PG_CONTAINER
    return 1
  fi

  local url="postgresql://postgres:drillpass@127.0.0.1:${PG_PORT}/vergeo5_drill"
  if wait_for_postgres "${url}"; then
    log "Using ephemeral Postgres via Docker on port ${PG_PORT}"
    printf '%s' "${url}"
    return 0
  fi

  docker rm -f "${PG_CONTAINER}" >/dev/null 2>&1 || true
  unset PG_CONTAINER
  return 1
}

start_postgres_local() {
  local initdb_bin
  initdb_bin="$(find_pg_bin initdb)" || {
    log "ERROR: initdb not found for local drill cluster"
    exit 1
  }
  if ! find_pg_ctl; then
    log "ERROR: pg_ctl not found for local drill cluster"
    exit 1
  fi

  PG_DATA_DIR="${DRILL_DIR}/pgdata"
  rm -rf "${PG_DATA_DIR}"
  mkdir -p "${PG_DATA_DIR}"
  chmod 700 "${PG_DATA_DIR}"

  "${initdb_bin}" -D "${PG_DATA_DIR}" -U postgres --no-locale -E UTF8 >/dev/null

  cat >>"${PG_DATA_DIR}/postgresql.conf" <<CONF
port = ${PG_PORT}
listen_addresses = '127.0.0.1'
unix_socket_directories = '${DRILL_DIR}'
max_connections = 20
CONF

  "${PG_CTL_BIN}" -D "${PG_DATA_DIR}" -l "${DRILL_DIR}/pg.log" start >/dev/null

  local url="postgresql://postgres@127.0.0.1:${PG_PORT}/postgres"
  if ! wait_for_postgres "${url}"; then
    log "ERROR: local postgres did not become ready"
    exit 1
  fi

  psql "${url}" -v ON_ERROR_STOP=1 -c 'CREATE DATABASE vergeo5_drill;' >/dev/null
  url="postgresql://postgres@127.0.0.1:${PG_PORT}/vergeo5_drill"
  log "Using ephemeral local Postgres on port ${PG_PORT}"
  printf '%s' "${url}"
}

start_postgres() {
  if start_postgres_docker; then
    return 0
  fi
  log "Docker unavailable or overlay unsupported — falling back to local initdb cluster"
  start_postgres_local
}

main() {
  trap cleanup EXIT

  require_cmd psql
  require_cmd pg_dump
  require_cmd gzip
  require_cmd gunzip

  local start_ts end_ts duration
  start_ts="$(date +%s)"

  rm -rf "${DRILL_DIR}"
  mkdir -p "${DRILL_DIR}/backups"

  local db_url
  db_url="$(start_postgres)"

  log "Seeding drill marker row"
  psql "${db_url}" -v ON_ERROR_STOP=1 <<SQL
CREATE TABLE IF NOT EXISTS vergeo5_drill_marker (
  id integer PRIMARY KEY,
  marker text NOT NULL
);
TRUNCATE vergeo5_drill_marker;
INSERT INTO vergeo5_drill_marker (id, marker) VALUES (1, '${DRILL_MARKER_VALUE}');
SQL

  export DATABASE_URL="${db_url}"
  export BACKUP_LOCAL_DIR="${DRILL_DIR}/backups"
  export SKIP_OCI_UPLOAD=1
  export BACKUP_RETENTION_DAYS=7

  log "Running db-dump.sh"
  bash "${SCRIPT_DIR}/db-dump.sh"

  local dump_file
  dump_file="$(ls -1t "${DRILL_DIR}/backups"/vergeo5-*.sql.gz | head -n1)"

  log "Wiping database"
  psql "${db_url}" -v ON_ERROR_STOP=1 -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'

  log "Running db-restore.sh"
  bash "${SCRIPT_DIR}/db-restore.sh" --file "${dump_file}" --target-url "${db_url}"

  local restored
  restored="$(
    psql "${db_url}" -tAc "SELECT marker FROM vergeo5_drill_marker WHERE id = 1"
  )"

  end_ts="$(date +%s)"
  duration="$((end_ts - start_ts))"

  if [[ "${restored}" == "${DRILL_MARKER_VALUE}" ]]; then
    printf 'PASS restore-drill (duration=%ss, marker=%s)\n' "${duration}" "${DRILL_MARKER_VALUE}"
    exit 0
  fi

  printf 'FAIL restore-drill (duration=%ss, expected=%s got=%s)\n' \
    "${duration}" "${DRILL_MARKER_VALUE}" "${restored}"
  exit 1
}

main "$@"
