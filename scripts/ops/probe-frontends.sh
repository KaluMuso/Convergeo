#!/usr/bin/env bash
#
# probe-frontends.sh — read-only production frontend probes (VA-P01 / Vercel promote verify).
#
# Usage:
#   bash scripts/ops/probe-frontends.sh
#   CUSTOMER_URL=https://preview.example.com bash scripts/ops/probe-frontends.sh
#
set -euo pipefail

CUSTOMER_URL="${CUSTOMER_URL:-https://www.vergeo5.com}"
VENDOR_URL="${VENDOR_URL:-https://vendor.vergeo5.com}"
ADMIN_URL="${ADMIN_URL:-https://admin.vergeo5.com}"
API_BASE_URL="${API_BASE_URL:-https://api.vergeo5.com}"
CURL_BIN="${CURL_BIN:-curl}"

fail=0

http_code() {
  "$CURL_BIN" -fsS -o /dev/null -w '%{http_code}' --connect-timeout 15 --max-time 30 -L "$1" 2>/dev/null || echo 000
}

accept_code() {
  local code="$1"
  shift
  local allowed
  for allowed in "$@"; do
    if [[ "$code" == "$allowed" ]]; then
      return 0
    fi
  done
  return 1
}

check() {
  local label="$1"
  local url="$2"
  shift 2
  local code
  code="$(http_code "$url")"
  printf '%-24s %s -> %s (expect %s)\n' "$label" "$url" "$code" "$*"
  if ! accept_code "$code" "$@"; then
    fail=1
  fi
}

printf '==> Frontend probes (read-only)\n'
check "customer health" "${CUSTOMER_URL%/}/en/health" 200
check "categories en" "${CUSTOMER_URL%/}/en/categories" 200
check "categories fr" "${CUSTOMER_URL%/}/fr/categories" 200
check "categories zh" "${CUSTOMER_URL%/}/zh/categories" 200
check "vendor health" "${VENDOR_URL%/}/en/health" 200 307 308
check "admin health" "${ADMIN_URL%/}/en/health" 200 403
check "api healthz" "${API_BASE_URL%/}/healthz" 200

if [[ "$fail" -eq 0 ]]; then
  printf '\nOVERALL: PASS\n'
  exit 0
fi
printf '\nOVERALL: FAIL\n'
exit 1
