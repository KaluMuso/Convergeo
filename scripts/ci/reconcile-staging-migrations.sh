#!/usr/bin/env bash
# Reconcile repository migrations against remote schema_migrations after db push.
#
# Usage (from deploy-staging.yml after supabase link + db push):
#   bash scripts/ci/reconcile-staging-migrations.sh
#
# Requires one of:
#   SUPABASE_DB_URL / STAGING_SUPABASE_DB_URL — queries schema_migrations via psql
#   MIGRATION_LIST_FILE — parsed ``supabase migration list`` output
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MIGRATIONS_DIR="${MIGRATIONS_DIR:-${REPO_ROOT}/supabase/migrations}"
REMOTE_VERSIONS_FILE="${REMOTE_VERSIONS_FILE:-/tmp/staging-remote-migrations.txt}"
MIGRATION_LIST_FILE="${MIGRATION_LIST_FILE:-}"

if [ -n "${MIGRATION_LIST_FILE}" ] && [ -f "${MIGRATION_LIST_FILE}" ]; then
  exec python3 "${REPO_ROOT}/scripts/ci/reconcile_staging_migrations.py" \
    --migrations-dir "${MIGRATIONS_DIR}" \
    --migration-list-file "${MIGRATION_LIST_FILE}"
fi

DB_URL="${SUPABASE_DB_URL:-${STAGING_SUPABASE_DB_URL:-}}"
if [ -z "${DB_URL}" ]; then
  echo "::error::SUPABASE_DB_URL or STAGING_SUPABASE_DB_URL required for migration reconcile" >&2
  exit 1
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "::error::psql required for migration reconcile" >&2
  exit 1
fi

psql "${DB_URL}" -tA -c \
  "SELECT version FROM supabase_migrations.schema_migrations ORDER BY version;" \
  > "${REMOTE_VERSIONS_FILE}"

python3 "${REPO_ROOT}/scripts/ci/reconcile_staging_migrations.py" \
  --migrations-dir "${MIGRATIONS_DIR}" \
  --remote-versions-file "${REMOTE_VERSIONS_FILE}"
