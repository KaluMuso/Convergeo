#!/usr/bin/env bash
# Environment-separation gate for staging CI/CD.
#
# Compares staging identifiers (env / inputs) against documented production
# identifiers and FAILS on any match. Secret *values* are never printed —
# only names and public identifiers.
#
# Usage:
#   bash scripts/ci/check-staging-separation.sh
#   STAGING_SUPABASE_PROJECT_ID=abc STAGING_API_HOST=api.staging.vergeo5.com \
#     bash scripts/ci/check-staging-separation.sh
#
# Exit codes:
#   0 — staging identifiers are distinct from production
#   1 — collision or missing required staging identifier
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FORBIDDEN_FILE="${REPO_ROOT}/infra/staging/forbidden-production-identifiers.env"

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
ok()  { printf 'OK: %s\n' "$*"; }
fail() { printf 'FAIL: %s\n' "$*" >&2; FAILURES=$((FAILURES + 1)); }

[[ -f "$FORBIDDEN_FILE" ]] || die "missing forbidden identifiers file: ${FORBIDDEN_FILE}"

# shellcheck disable=SC1090
set -a
# shellcheck source=/dev/null
source "$FORBIDDEN_FILE"
set +a

FAILURES=0

normalize_host() {
  local raw="${1:-}"
  raw="${raw#https://}"
  raw="${raw#http://}"
  raw="${raw%%/*}"
  raw="${raw%%:*}"
  printf '%s' "$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')"
}

extract_supabase_ref() {
  local raw="${1:-}"
  raw="${raw#https://}"
  raw="${raw#http://}"
  raw="${raw%%/*}"
  raw="${raw%%.*}"
  printf '%s' "$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')"
}

# --- Required staging identifiers (names only; values compared to prod) -------
STAGING_SUPABASE_PROJECT_ID="${STAGING_SUPABASE_PROJECT_ID:-}"
STAGING_SUPABASE_URL="${STAGING_SUPABASE_URL:-}"
STAGING_API_HOST="${STAGING_API_HOST:-}"
STAGING_API_BASE_URL="${STAGING_API_BASE_URL:-}"
STAGING_N8N_WEBHOOK_URL="${STAGING_N8N_WEBHOOK_URL:-}"
STAGING_CUSTOMER_URL="${STAGING_CUSTOMER_URL:-}"
STAGING_VENDOR_URL="${STAGING_VENDOR_URL:-}"
STAGING_ADMIN_URL="${STAGING_ADMIN_URL:-}"

# Derive project id from URL when only URL is provided.
if [[ -z "$STAGING_SUPABASE_PROJECT_ID" && -n "$STAGING_SUPABASE_URL" ]]; then
  STAGING_SUPABASE_PROJECT_ID="$(extract_supabase_ref "$STAGING_SUPABASE_URL")"
fi
if [[ -z "$STAGING_API_HOST" && -n "$STAGING_API_BASE_URL" ]]; then
  STAGING_API_HOST="$(normalize_host "$STAGING_API_BASE_URL")"
fi

echo "==> Staging separation check"
echo "    forbidden file: ${FORBIDDEN_FILE}"
echo "    (secret values are never printed)"

if [[ -z "$STAGING_SUPABASE_PROJECT_ID" ]]; then
  fail "STAGING_SUPABASE_PROJECT_ID (or STAGING_SUPABASE_URL) is required"
else
  if [[ "$STAGING_SUPABASE_PROJECT_ID" == "$PROD_SUPABASE_PROJECT_REF" ]]; then
    fail "STAGING_SUPABASE_PROJECT_ID equals production ref (${PROD_SUPABASE_PROJECT_REF})"
  else
    ok "Supabase project ref differs from production"
  fi
fi

if [[ -z "$STAGING_API_HOST" ]]; then
  fail "STAGING_API_HOST (or STAGING_API_BASE_URL) is required"
else
  host="$(normalize_host "$STAGING_API_HOST")"
  if [[ "$host" == "$PROD_API_HOST" ]]; then
    fail "STAGING_API_HOST equals production API host (${PROD_API_HOST})"
  else
    ok "API host differs from production (${host})"
  fi
fi

# Optional host checks — only when provided.
check_optional_host() {
  local name="$1" value="$2" prod_host="$3"
  [[ -n "$value" ]] || return 0
  local host
  host="$(normalize_host "$value")"
  if [[ "$host" == "$prod_host" || "$host" == "www.${prod_host}" ]]; then
    fail "${name} collides with production host (${prod_host})"
  else
    ok "${name} distinct from ${prod_host}"
  fi
}

check_optional_host "STAGING_CUSTOMER_URL" "$STAGING_CUSTOMER_URL" "$PROD_CUSTOMER_HOST"
check_optional_host "STAGING_VENDOR_URL" "$STAGING_VENDOR_URL" "$PROD_VENDOR_HOST"
check_optional_host "STAGING_ADMIN_URL" "$STAGING_ADMIN_URL" "$PROD_ADMIN_HOST"

if [[ -n "$STAGING_N8N_WEBHOOK_URL" ]]; then
  n8n_host="$(normalize_host "$STAGING_N8N_WEBHOOK_URL")"
  if [[ "$n8n_host" == "$PROD_N8N_HOST" ]]; then
    fail "STAGING_N8N_WEBHOOK_URL collides with production n8n (${PROD_N8N_HOST})"
  else
    ok "n8n webhook host distinct from production"
  fi
fi

# Reject embedding production identifiers in any STAGING_* env value we can see.
while IFS='=' read -r key value; do
  [[ "$key" == STAGING_* ]] || continue
  [[ -n "${value:-}" ]] || continue
  # Never echo the value — only the key name on failure.
  if [[ "$value" == *"$PROD_SUPABASE_PROJECT_REF"* ]]; then
    fail "${key} embeds production Supabase project ref"
  fi
  if [[ "$value" == *"$PROD_API_HOST"* ]]; then
    fail "${key} embeds production API host"
  fi
done < <(env | grep -E '^STAGING_' || true)

# Reject localhost fallbacks for staging deploy targets.
for name in STAGING_API_HOST STAGING_API_BASE_URL STAGING_CUSTOMER_URL STAGING_VENDOR_URL STAGING_ADMIN_URL; do
  val="${!name:-}"
  [[ -n "$val" ]] || continue
  host="$(normalize_host "$val")"
  if [[ "$host" == "localhost" || "$host" == "127.0.0.1" ]]; then
    fail "${name} must not use localhost for staging deploys"
  fi
done

if [[ "$FAILURES" -gt 0 ]]; then
  echo "::error::staging separation check failed (${FAILURES} issue(s))"
  exit 1
fi

echo "==> Staging separation PASSED"
exit 0
