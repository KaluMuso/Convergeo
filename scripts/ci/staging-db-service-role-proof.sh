#!/usr/bin/env bash
# Native DB-pool + service-role read proof (staging cart-location remediation).
#
# Run #55's aftermath proved a class of defect deploy-time checks had never
# caught: services/api/app/services/inventory/location_stock.py's raw
# psycopg connection pool (run_sql_script/resolve_db_url) is a SEPARATE
# connectivity path from the Supabase REST/PostgREST client every other
# check here exercises. A working /healthz + a working CORS preflight both
# say nothing about whether THAT pool is reachable from the deployed API
# container — the OCI staging API's SUPABASE_DB_URL needed a runtime fix
# (session pooler, IPv4-compatible) that no existing deploy gate would have
# caught. This probe closes that gap using the new, already-shipped
# GET /products/listings/{id}/pickup-locations endpoint, which exercises:
#
#   - the raw DB pool (is_branch_tracked / fetch_branch_stock_rows) — a 500
#     here means that pool is unreachable/misconfigured on the deployed API;
#   - the service-role Supabase client (fetch_listing existence check, the
#     vendor_locations landmark lookup) — both run under the same
#     service-role credential the API's other privileged reads use;
#   - real (non-preflight) CORS headers on an ordinary GET response — the
#     deploy-time CORS proof only ever sends a synthetic OPTIONS preflight,
#     never a real GET/POST, so it cannot catch a response that skipped
#     CORSMiddleware (the run #55 mechanism); this is a second, independent
#     data point on that using an intentionally safe, non-mutating request.
#
# No secret is read or required: this hits a public, read-only API route
# using the same certified immutable Preview origin the CORS proof already
# validated — never a service-role key, DB URL, or any other credential.
#
# Usage:
#   bash scripts/ci/staging-db-service-role-proof.sh \
#     --preview-dir /tmp/preview-evidence \
#     --api-base https://api.staging.vergeo5.com \
#     --listing-id f1000000-0000-4000-8000-000000000001

set -euo pipefail

PREVIEW_DIR=""
API_BASE=""
LISTING_ID=""
PORTAL="customer"

log() { printf '==> [db-service-role-proof] %s\n' "$*"; }
die() { printf '::error::[db-service-role-proof] %s\n' "$*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --preview-dir) PREVIEW_DIR="${2:-}"; shift 2 ;;
    --api-base) API_BASE="${2:-}"; shift 2 ;;
    --listing-id) LISTING_ID="${2:-}"; shift 2 ;;
    -h|--help)
      sed -n '2,32p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) die "unknown argument: $1" ;;
  esac
done

[ -n "${PREVIEW_DIR}" ] || die "--preview-dir is required"
[ -n "${API_BASE}" ] || die "--api-base is required"
[ -n "${LISTING_ID}" ] || die "--listing-id is required"

case "${API_BASE}" in
  *api.vergeo5.com*) die "refusing to probe the production API host" ;;
esac

evidence_file="${PREVIEW_DIR}/${PORTAL}/evidence.json"
[ -f "${evidence_file}" ] || die "missing Preview evidence at ${evidence_file}"

preview_origin="$(python3 - "${evidence_file}" <<'PY'
import json, sys
from urllib.parse import urlsplit

with open(sys.argv[1], encoding="utf-8") as fh:
    doc = json.load(fh)
url = doc.get("preview_url") or ""
parsed = urlsplit(url)
if parsed.scheme != "https" or not parsed.netloc:
    print("", end="")
else:
    print(f"{parsed.scheme}://{parsed.netloc}", end="")
PY
)"
[ -n "${preview_origin}" ] || die "evidence.json preview_url is missing or not a valid https origin"

log "probing GET ${API_BASE}/products/listings/${LISTING_ID}/pickup-locations with Origin: ${preview_origin}"

body_file="$(mktemp)"
headers_file="$(mktemp)"
trap 'rm -f "${body_file}" "${headers_file}"' EXIT

http_code="$(curl -sS -o "${body_file}" -D "${headers_file}" -w '%{http_code}' \
  -H "Origin: ${preview_origin}" \
  "${API_BASE}/products/listings/${LISTING_ID}/pickup-locations")"

if [ "${http_code}" = "500" ]; then
  die "pickup-locations returned 500 for the canonical branch-tracked fixture — the native DB pool (raw psycopg, distinct from the PostgREST/service-role path) appears unreachable from the deployed API. Body: $(cat "${body_file}")"
fi

if [ "${http_code}" != "200" ]; then
  die "pickup-locations returned HTTP ${http_code} for ${LISTING_ID} — expected 200 with branch_tracked=true (this fixture is seeded deliberately branch-tracked). Body: $(cat "${body_file}")"
fi

read -r branch_tracked location_count < <(python3 - "${body_file}" <<'PY'
import json, sys

with open(sys.argv[1], encoding="utf-8") as fh:
    doc = json.load(fh)
print(doc.get("branch_tracked"), len(doc.get("locations") or []))
PY
)

if [ "${branch_tracked}" != "True" ] || [ "${location_count}" -lt 1 ]; then
  die "canonical fixture ${LISTING_ID} did not report branch_tracked=true with an active branch (branch_tracked=${branch_tracked}, locations=${location_count})"
fi

acao="$(grep -i '^access-control-allow-origin:' "${headers_file}" | tr -d '\r' | sed 's/^[Aa]ccess-[Cc]ontrol-[Aa]llow-[Oo]rigin:[[:space:]]*//' || true)"
if [ "${acao}" != "${preview_origin}" ]; then
  die "pickup-locations 200 response missing exact-origin CORS headers (got '${acao:-<absent>}', want '${preview_origin}')"
fi

log "OK: native DB pool reachable, canonical fixture branch-tracked with ${location_count} active branch(es), exact-origin CORS headers present on a real (non-preflight) GET response"
