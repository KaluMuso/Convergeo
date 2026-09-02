#!/usr/bin/env bash
# CORS proof for staging's immutable Vercel Preview origins (RC-6 / PR-F3).
#
# strict E2E run #52 proved (real Playwright traces) that the deployed
# Customer/Vendor/Admin Preview origins were rejected by the staging API's
# CORS allowlist — because every SHA-pinned Vercel Preview deployment gets a
# newly generated immutable hostname a static CORS_ORIGINS entry can never
# anticipate. That defect was only ever discovered by Playwright, deep into
# the browse journey. This probe runs the exact preflight the browser would
# send, using the same three immutable Preview URLs deploy-staging.yml's
# `prove-vercel-preview` job already proved READY for this SHA, so the CORS
# contract is proven as part of the deploy — before any Playwright spec runs.
#
# Usage:
#   bash scripts/ci/staging-cors-preview-probe.sh \
#     --preview-dir /tmp/preview-evidence \
#     --api-base https://api.staging.vergeo5.com \
#     [--extra-origin https://customer.staging.vergeo5.com]
#
# --preview-dir must contain <portal>/evidence.json for customer, vendor and
# admin (the same normalized layout deploy-staging.yml's `smoke` job already
# produces — each evidence.json has a "preview_url" field written by
# scripts/ci/vercel-staging-preview-prove.sh).
#
# --extra-origin (optional, repeatable): an additional exact origin to prove
# the SAME preflight contract for, alongside the three immutable Preview
# origins. Used for the stable same-site Customer staging hostname (see
# docs/ops/staging-samesite-guest-cart.md) once an operator has configured
# it — that origin is NOT a *.vercel.app Preview host, so it is never
# discovered from preview-dir evidence and must be passed explicitly. Absent
# any --extra-origin, behavior is exactly today's three-portal-only probe.
#
# No secret is read or required: this probes the PUBLIC CORS contract of the
# staging API, not a protected route.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

PREVIEW_DIR=""
API_BASE=""
PORTALS=(customer vendor admin)
PROBE_PATH="/cart/items"
EXTRA_ORIGINS=()

log() { printf '==> [cors-preview-probe] %s\n' "$*"; }
die() { printf '::error::[cors-preview-probe] %s\n' "$*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --preview-dir)
      PREVIEW_DIR="${2:-}"
      shift 2
      ;;
    --api-base)
      API_BASE="${2:-}"
      shift 2
      ;;
    --path)
      PROBE_PATH="${2:-}"
      shift 2
      ;;
    --extra-origin)
      EXTRA_ORIGINS+=("${2:-}")
      shift 2
      ;;
    -h|--help)
      sed -n '2,25p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

[ -n "${PREVIEW_DIR}" ] || die "--preview-dir is required"
[ -n "${API_BASE}" ] || die "--api-base is required"
[ -d "${PREVIEW_DIR}" ] || die "preview dir not found: ${PREVIEW_DIR}"

case "${API_BASE}" in
  *api.vergeo5.com*) die "refusing to probe the production API host" ;;
esac

overall_rc=0

# Probes one exact origin's CORS preflight and asserts the same contract
# every caller (Preview portals, and any --extra-origin) must satisfy.
# Returns/continues via the shared overall_rc — never exits early, so one
# bad origin never hides failures on the others.
probe_origin() {
  local label="$1"
  local origin="$2"

  log "${label}: probing OPTIONS ${API_BASE}${PROBE_PATH} with Origin: ${origin}"

  local headers_file http_code acao acac
  headers_file="$(mktemp)"
  http_code="$(curl -sS -o /dev/null -D "${headers_file}" -w '%{http_code}' \
    --connect-timeout 15 --max-time 30 \
    -X OPTIONS \
    -H "Origin: ${origin}" \
    -H "Access-Control-Request-Method: POST" \
    -H "Access-Control-Request-Headers: content-type" \
    "${API_BASE}${PROBE_PATH}" 2>/dev/null || echo 000)"

  # `|| true` matters under `set -euo pipefail`: a rejected origin is exactly
  # the case where `grep` legitimately finds no header and exits 1 — that
  # must produce an empty acao/acac (checked below), not abort this script
  # mid-portal and silently skip the remaining origins.
  acao="$(tr -d '\r' < "${headers_file}" \
    | grep -i '^access-control-allow-origin:' \
    | tail -1 \
    | sed -E 's/^[Aa]ccess-[Cc]ontrol-[Aa]llow-[Oo]rigin:[[:space:]]*//' || true)"
  acac="$(tr -d '\r' < "${headers_file}" \
    | grep -i '^access-control-allow-credentials:' \
    | tail -1 \
    | sed -E 's/^[Aa]ccess-[Cc]ontrol-[Aa]llow-[Cc]redentials:[[:space:]]*//' || true)"
  rm -f "${headers_file}"

  if [ "${http_code}" != "200" ]; then
    printf '::error::[%s] preflight returned HTTP %s (want 200) for Origin %s\n' \
      "${label}" "${http_code}" "${origin}" >&2
    overall_rc=1
    return
  fi

  if [ "${acao}" != "${origin}" ]; then
    printf '::error::[%s] Access-Control-Allow-Origin was %s, want the exact requesting origin %s (RC-6 regression)\n' \
      "${label}" "${acao:-<absent>}" "${origin}" >&2
    overall_rc=1
    return
  fi

  if [ "${acac}" != "true" ]; then
    printf '::error::[%s] Access-Control-Allow-Credentials was %s, want true\n' \
      "${label}" "${acac:-<absent>}" >&2
    overall_rc=1
    return
  fi

  log "${label}: OK — ${PROBE_PATH} preflight allows ${origin} with credentials"
}

for portal in "${PORTALS[@]}"; do
  evidence_file="${PREVIEW_DIR}/${portal}/evidence.json"
  if [ ! -f "${evidence_file}" ]; then
    printf '::error::[%s] missing Preview evidence at %s\n' "${portal}" "${evidence_file}" >&2
    overall_rc=1
    continue
  fi

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
  if [ -z "${preview_origin}" ]; then
    printf '::error::[%s] evidence.json preview_url is missing or not a valid https origin\n' "${portal}" >&2
    overall_rc=1
    continue
  fi

  probe_origin "${portal}" "${preview_origin}"
done

for extra_origin in "${EXTRA_ORIGINS[@]}"; do
  [ -n "${extra_origin}" ] || continue
  case "${extra_origin}" in
    https://*) ;;
    *) printf '::error::[extra-origin] %s is not an https origin\n' "${extra_origin}" >&2; overall_rc=1; continue ;;
  esac
  probe_origin "extra-origin(${extra_origin#https://})" "${extra_origin}"
done

if [ "${overall_rc}" -ne 0 ]; then
  die "one or more staging CORS Preview proofs failed — see errors above"
fi

if [ "${#EXTRA_ORIGINS[@]}" -gt 0 ]; then
  log "all portals + ${#EXTRA_ORIGINS[@]} extra origin(s): staging API CORS allows every certified origin"
else
  log "all portals: staging API CORS allows the certified immutable Preview origins"
fi
