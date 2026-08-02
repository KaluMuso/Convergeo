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

# psql's exit status is checked SEPARATELY from grep's, and this is the whole
# point of the next few lines.
#
# The previous form was:
#   issues="$("${PSQL[@]}" -At -f "$SQL_FILE" | grep -E '^FAIL ' || true)"
# where `|| true` covers the WHOLE pipeline, so a connection failure was
# swallowed exactly like "no FAIL rows found" and the script went on to print
# OK and exit 0. That is not hypothetical: Deploy staging run 30695764799
# (2026-08-01) logged `psql: error: … Network is unreachable` and then
# `OK: RLS enabled on public tables` in consecutive lines.
#
# A guard that reports OK when it verified nothing is worse than no guard,
# because every downstream readiness claim that cites it is then void.
# `|| true` may only ever absorb grep's "no matches" (exit 1) — never a
# connection or query failure.
err_file="$(mktemp)"
trap 'rm -f "$err_file"' EXIT

if ! raw="$("${PSQL[@]}" -At -f "$SQL_FILE" 2>"$err_file")"; then
  sed 's/^/  /' "$err_file" >&2
  die "could not run the staging schema checks (psql exited non-zero) — refusing to report OK"
fi

# The SQL emits `\echo ==> Check: …` markers for each check, so a healthy run
# is never silent. No output means the file did not execute, which we must not
# mistake for "found nothing wrong".
if [[ -z "${raw//[[:space:]]/}" ]]; then
  sed 's/^/  /' "$err_file" >&2
  die "staging schema checks produced no output — the SQL did not run; refusing to report OK"
fi

issues="$(printf '%s\n' "$raw" | grep -E '^FAIL ' || true)"
if [[ -n "$issues" ]]; then
  echo "::error::staging schema isolation failures:"
  printf '%s\n' "$issues"
  exit 1
fi

echo "OK: RLS enabled on public tables; exposed views use security_invoker (or none exposed)"
exit 0
