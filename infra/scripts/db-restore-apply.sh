#!/usr/bin/env bash
# Apply a gzip logical dump to a Postgres target (no safety guards).
# Internal primitive — callers must enforce target authorization.
set -euo pipefail

DUMP_FILE="${1:-}"
TARGET_URL="${2:-}"

if [[ -z "${DUMP_FILE}" || -z "${TARGET_URL}" ]]; then
  echo "usage: db-restore-apply.sh DUMP_FILE TARGET_URL" >&2
  exit 1
fi

if [[ ! -f "${DUMP_FILE}" ]]; then
  echo "ERROR: dump file not found: ${DUMP_FILE}" >&2
  exit 1
fi

gunzip -c "${DUMP_FILE}" | psql "${TARGET_URL}" -v ON_ERROR_STOP=1
