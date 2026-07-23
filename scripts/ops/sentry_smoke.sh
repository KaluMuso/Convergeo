#!/usr/bin/env bash
#
# sentry_smoke.sh — G6 observability verification (test event ingest per surface).
#
# Fires protected sentry-test endpoints on API + three Next.js apps. Never prints secrets.
# Writes a JSON report artifact for verify_live.sh / launch_gates.sh.
#
# Usage:
#   bash scripts/ops/sentry_smoke.sh
#   bash scripts/ops/sentry_smoke.sh --dry-run
#
# Environment (names only):
#   API_BASE_URL                  Default https://api.vergeo5.com
#   CUSTOMER_URL                  Default https://www.vergeo5.com
#   VENDOR_URL                    Default https://vendor.vergeo5.com
#   ADMIN_URL                     Default https://admin.vergeo5.com
#   INTERNAL_SENTRY_TEST_TOKEN    API X-Internal-Token
#   SENTRY_TEST_SECRET            Next apps X-Sentry-Test-Secret
#   ENABLE_SENTRY_TEST_ENDPOINT   Must be true on production targets
#   SENTRY_SMOKE_REPORT           Output JSON path (default /tmp/vergeo5-sentry-smoke.json)
#
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-https://api.vergeo5.com}"
CUSTOMER_URL="${CUSTOMER_URL:-https://www.vergeo5.com}"
VENDOR_URL="${VENDOR_URL:-https://vendor.vergeo5.com}"
ADMIN_URL="${ADMIN_URL:-https://admin.vergeo5.com}"
SENTRY_SMOKE_REPORT="${SENTRY_SMOKE_REPORT:-/tmp/vergeo5-sentry-smoke.json}"
CURL_BIN="${CURL_BIN:-curl}"

DRY_RUN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help)
      sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
  esac
done

log() { printf '==> %s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; }

declare -A SURFACE_STATUS=()
declare -A SURFACE_DETAIL=()

probe_surface() {
  local surface="$1"
  local url="$2"
  local header_name="$3"
  local token="$4"

  if [[ -z "$token" ]]; then
    SURFACE_STATUS["$surface"]="SKIP"
    SURFACE_DETAIL["$surface"]="token unset"
    return 0
  fi

  if [[ "$DRY_RUN" -eq 1 ]]; then
    SURFACE_STATUS["$surface"]="SKIP"
    SURFACE_DETAIL["$surface"]="dry-run"
    return 0
  fi

  local code body event_id
  code="$(
    "$CURL_BIN" -fsS -o /tmp/sentry-smoke-body.json -w '%{http_code}' \
      --connect-timeout 15 --max-time 45 \
      -X POST "$url" \
      -H "${header_name}: ${token}" \
      -H 'Content-Type: application/json' \
      -d '{}' 2>/dev/null || printf '000'
  )"
  body="$(cat /tmp/sentry-smoke-body.json 2>/dev/null || true)"

  if [[ "$code" == "200" && "$body" == *'"ok":true'* && "$body" == *'"event_id"'* ]]; then
    event_id="$(printf '%s' "$body" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("event_id",""))' 2>/dev/null || echo '')"
    SURFACE_STATUS["$surface"]="PASS"
    SURFACE_DETAIL["$surface"]="http=200 event_id=${event_id:-present}"
    return 0
  fi

  SURFACE_STATUS["$surface"]="FAIL"
  SURFACE_DETAIL["$surface"]="http=${code}"
}

write_report() {
  local overall="$1"
  python3 - "$SENTRY_SMOKE_REPORT" "$overall" \
    "${SURFACE_STATUS[api]:-SKIP}" "${SURFACE_DETAIL[api]:-}" \
    "${SURFACE_STATUS[customer]:-SKIP}" "${SURFACE_DETAIL[customer]:-}" \
    "${SURFACE_STATUS[vendor]:-SKIP}" "${SURFACE_DETAIL[vendor]:-}" \
    "${SURFACE_STATUS[admin]:-SKIP}" "${SURFACE_DETAIL[admin]:-}" <<'PY'
import json, sys
from datetime import UTC, datetime

report_path, verdict = sys.argv[1], sys.argv[2]
keys = ("api", "customer", "vendor", "admin")
surfaces = {}
idx = 3
for key in keys:
    surfaces[key] = {"status": sys.argv[idx], "detail": sys.argv[idx + 1]}
    idx += 2

payload = {
    "gate": "G6",
    "verdict": verdict,
    "finished_at": datetime.now(UTC).isoformat(),
    "surfaces": surfaces,
}
with open(report_path, "w", encoding="utf-8") as fh:
    json.dump(payload, fh, indent=2)
print(f"report={report_path} verdict={verdict}")
PY
}

main() {
  log "Sentry smoke (G6) — surfaces: api customer vendor admin"
  if [[ "${ENABLE_SENTRY_TEST_ENDPOINT:-}" != "true" ]]; then
    warn "ENABLE_SENTRY_TEST_ENDPOINT is not true — production endpoints may 404"
  fi

  probe_surface api "${API_BASE_URL%/}/internal/sentry-test" "X-Internal-Token" "${INTERNAL_SENTRY_TEST_TOKEN:-}"
  probe_surface customer "${CUSTOMER_URL%/}/api/observability/sentry-test" "X-Sentry-Test-Secret" "${SENTRY_TEST_SECRET:-}"
  probe_surface vendor "${VENDOR_URL%/}/api/observability/sentry-test" "X-Sentry-Test-Secret" "${SENTRY_TEST_SECRET:-}"
  probe_surface admin "${ADMIN_URL%/}/api/observability/sentry-test" "X-Sentry-Test-Secret" "${SENTRY_TEST_SECRET:-}"

  local overall="PASS"
  local s
  for s in api customer vendor admin; do
    local st="${SURFACE_STATUS[$s]:-SKIP}"
    printf '%-10s %-6s %s\n' "$s" "$st" "${SURFACE_DETAIL[$s]:-}"
    if [[ "$st" == "FAIL" ]]; then
      overall="FAIL"
    elif [[ "$st" == "SKIP" && "$overall" == "PASS" ]]; then
      overall="SKIP"
    fi
  done

  write_report "$overall"

  if [[ "$overall" == "PASS" ]]; then
    log "G6 Sentry smoke PASS — confirm events in Sentry UI (test_event=true)"
    exit 0
  fi
  if [[ "$overall" == "SKIP" ]]; then
    log "G6 Sentry smoke SKIP — set DSNs + tokens + ENABLE_SENTRY_TEST_ENDPOINT=true"
    exit 0
  fi
  log "G6 Sentry smoke FAIL — see rows above; runbook: docs/ops/observability.md"
  exit 1
}

main "$@"
