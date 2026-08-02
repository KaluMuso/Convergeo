#!/usr/bin/env bash
# Preflight: prove the database URL is actually reachable, and if it is not,
# say WHY in terms the operator can act on.
#
# Context (2026-08-01): Deploy staging run 30695764799 failed with a bare
#   psql: error: connection to server at "db.***.supabase.co"
#         (2a05:d018:8eb:2f00:...), port 5432 failed: Network is unreachable
# GitHub-hosted runners have no IPv6 egress, and Supabase's DIRECT connection
# host (db.<ref>.supabase.co) resolves to IPv6 only. The fix is the pooler host
# (aws-0-<region>.pooler.supabase.com), which has an IPv4 address — not a
# retry, and not disabling TLS.
#
# This script exists so that failure mode is diagnosed in one line instead of
# being rediscovered each time.
#
# Usage:
#   SUPABASE_DB_URL=postgresql://... bash scripts/ci/check-db-reachable.sh
set -euo pipefail

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

DB_URL="${SUPABASE_DB_URL:-${DATABASE_URL:-}}"
[[ -n "$DB_URL" ]] || die "SUPABASE_DB_URL (or DATABASE_URL) is not set"
command -v psql >/dev/null || die "psql not on PATH"

# Host only — never print the URL, it carries the password.
host="$(printf '%s' "$DB_URL" | sed -E 's#^[a-z+]+://([^@]*@)?([^:/?]+).*#\2#')"
[[ -n "$host" ]] || die "could not parse a host out of the database URL"

echo "==> Preflight: database reachability (host: ${host})"

# Bound the attempt. A host that refuses fails instantly, but one that silently
# drops packets (a blocked egress path, a wrong pooler region) would otherwise
# hang until the job timeout — turning a one-line diagnosis into a 25-minute
# mystery. Fail fast and say why.
export PGCONNECT_TIMEOUT="${PGCONNECT_TIMEOUT:-10}"

if psql "$DB_URL" -Atc 'select 1' >/dev/null 2>/tmp/db-reachable.err; then
  echo "OK: database reachable"
  exit 0
fi

echo "::error::cannot reach the database at ${host}" >&2
sed 's/^/  /' /tmp/db-reachable.err >&2

# Only offer the hint when the evidence supports it: a direct-connection host
# whose only addresses are IPv6.
if [[ "$host" == db.*.supabase.co ]]; then
  has_v4=""
  if command -v getent >/dev/null; then
    has_v4="$(getent ahostsv4 "$host" 2>/dev/null | head -n1 || true)"
  fi
  if [[ -z "$has_v4" ]]; then
    cat >&2 <<'HINT'

  DIAGNOSIS: this is Supabase's DIRECT connection host, which resolves to IPv6
  only, and this runner has no IPv6 egress.

  FIX: point STAGING_SUPABASE_DB_URL at the SESSION POOLER instead:
    postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres

  Region must match the project:
    vergeo-sandbox (staging)  -> eu-west-1
    Vergeo5        (production) -> eu-north-1

  Do NOT "fix" this by disabling TLS or by retrying.
HINT
  fi
fi

exit 1
