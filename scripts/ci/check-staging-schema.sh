#!/usr/bin/env bash
# Run staging schema isolation checks against a Postgres URL.
# Fails if any public base table lacks RLS, or any anon/authenticated-exposed
# public view lacks security_invoker.
#
# Usage:
#   SUPABASE_DB_URL=postgresql://... bash scripts/ci/check-staging-schema.sh
#   # or:
#   PGHOST=... PGPORT=... PGUSER=... PGPASSWORD=... PGDATABASE=... \
#     bash scripts/ci/check-staging-schema.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SQL_FILE="${REPO_ROOT}/scripts/ci/check-staging-schema.sql"

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

[[ -f "$SQL_FILE" ]] || die "missing ${SQL_FILE}"
command -v psql >/dev/null || die "psql not on PATH"

if [[ -n "${SUPABASE_DB_URL:-${DATABASE_URL:-}}" ]]; then
  DB_URL="${SUPABASE_DB_URL:-$DATABASE_URL}"
  PSQL=(psql -v ON_ERROR_STOP=1 "$DB_URL")
else
  : "${PGHOST:=localhost}"
  : "${PGPORT:=5432}"
  : "${PGUSER:=postgres}"
  : "${PGDATABASE:=postgres}"
  export PGPASSWORD="${PGPASSWORD:-postgres}"
  PSQL=(psql -v ON_ERROR_STOP=1 -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE")
fi

echo "==> Staging schema checks (${SQL_FILE})"

# Capture issue lines only (queries emit FAIL … rows).
issues="$("${PSQL[@]}" -At -f "$SQL_FILE" | grep -E '^FAIL ' || true)"
if [[ -n "$issues" ]]; then
  echo "::error::staging schema isolation failures:"
  printf '%s\n' "$issues"
  exit 1
fi

echo "OK: RLS enabled on public tables; exposed views use security_invoker (or none exposed)"
exit 0
