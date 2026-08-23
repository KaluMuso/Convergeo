#!/usr/bin/env bash
# Deploy a Git-source Vercel Preview for one portal on the staging branch,
# await READY, verify SHA/target/project, then prove the EFFECTIVE DEPLOYED
# CONFIGURATION from the live artifact's own /health response (primary,
# blocking). Vercel's stored env-var config is also checked but only as a
# secondary, non-blocking, informational signal — see
# scripts/ci/vercel_preview_health_verify.py and vercel_preview_env_verify.py.
#
# Usage (from deploy-staging.yml or local with VERCEL_TOKEN):
#   bash scripts/ci/vercel-staging-preview-prove.sh --portal customer
#   bash scripts/ci/vercel-staging-preview-prove.sh --portal vendor --output-dir /tmp/out
#
# Required env:
#   VERCEL_TOKEN, VERCEL_ORG_ID
#   VERCEL_PROJECT_ID_CUSTOMER | VERCEL_PROJECT_ID_VENDOR | VERCEL_PROJECT_ID_ADMIN
#   GITHUB_SHA, GITHUB_REF_NAME (must be "staging" in CI)
#   STAGING_API_BASE_URL and/or STAGING_API_HOST
#
# Vercel Deployment Protection (see scripts/ci/vercel_preview_access.py):
#   Preview deployments sit behind Deployment Protection, so the health probe
#   must authenticate with a "Protection Bypass for Automation" secret, sent as
#   the x-vercel-protection-bypass header. A secret is issued PER VERCEL
#   PROJECT and the three portals are three separate projects, so one portal's
#   secret is never assumed to work for another. Precedence, highest first:
#     VERCEL_PORTAL_BYPASS_SECRET                    (pre-scoped by the caller)
#     VERCEL_AUTOMATION_BYPASS_SECRET_{CUSTOMER,VENDOR,ADMIN}
#     VERCEL_AUTOMATION_BYPASS_SECRET                (legacy fallback only)
#   The value is passed to curl through a mode-600 config file, never through
#   argv, a URL, a query parameter, the evidence JSON, GITHUB_OUTPUT, or a log.
#
# Optional:
#   GITHUB_OUTPUT — when set, writes url, deployment_id, sha outputs
#   VERCEL_PREVIEW_PROVE_EVIDENCE — path for JSON evidence (default: $OUTPUT_DIR/evidence.json)
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

PORTAL=""
OUTPUT_DIR="/tmp/staging-preview-prove"
GITHUB_ORG="${GITHUB_ORG:-KaluMuso}"
GITHUB_REPO="${GITHUB_REPO:-Convergeo}"
HEALTH_LOCALE="${HEALTH_LOCALE:-en}"
DRY_RUN=0

usage() {
  sed -n '2,18p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

log() { printf '==> [%s] %s\n' "${PORTAL:-?}" "$*"; }
die() { printf '::error::[%s] %s\n' "${PORTAL:-?}" "$*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --portal)
      PORTAL="${2:-}"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="${2:-}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

mkdir -p "${OUTPUT_DIR}"

case "${PORTAL}" in
  customer)
    VERCEL_NAME="convergeo-customer"
    PROJECT_ID="${VERCEL_PROJECT_ID_CUSTOMER:-}"
    API_ENV_VAR="NEXT_PUBLIC_API_BASE_URL"
    APP_ID="customer"
    ;;
  vendor)
    VERCEL_NAME="convergeo-vendor"
    PROJECT_ID="${VERCEL_PROJECT_ID_VENDOR:-}"
    API_ENV_VAR="NEXT_PUBLIC_API_BASE_URL"
    APP_ID="vendor"
    ;;
  admin)
    VERCEL_NAME="convergeo-admin"
    PROJECT_ID="${VERCEL_PROJECT_ID_ADMIN:-}"
    API_ENV_VAR="NEXT_PUBLIC_VERGEO_API_URL"
    APP_ID="admin"
    ;;
  *)
    die "--portal is required (customer|vendor|admin)"
    ;;
esac

GITHUB_SHA="${GITHUB_SHA:-}"
GITHUB_REF_NAME="${GITHUB_REF_NAME:-staging}"

for name in VERCEL_TOKEN VERCEL_ORG_ID PROJECT_ID GITHUB_SHA; do
  if [ -z "${!name:-}" ]; then
    die "${name} is required"
  fi
done

if [ "${GITHUB_REF_NAME}" != "staging" ]; then
  die "GITHUB_REF_NAME must be staging, got ${GITHUB_REF_NAME}"
fi

case "${GITHUB_SHA}" in
  [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]*) ;;
  *) die "GITHUB_SHA is not a commit SHA" ;;
esac

if [ "${GITHUB_SHA}" = "latest" ]; then
  die "refusing image/deployment tag latest"
fi

API_BASE="${STAGING_API_BASE_URL:-}"
if [ -z "${API_BASE}" ] && [ -n "${STAGING_API_HOST:-}" ]; then
  API_BASE="https://${STAGING_API_HOST}"
fi
if [ -z "${API_BASE}" ]; then
  die "STAGING_API_BASE_URL or STAGING_API_HOST is required"
fi

case "${API_BASE}" in
  *api.vergeo5.com*) die "Preview must not use production API" ;;
  *localhost*) die "Preview must not use localhost" ;;
esac

EXPECTED_API_HOST="$(printf '%s' "${API_BASE}" | sed -E 's#^https?://##; s#/.*##; s/:.*//')"

if [ "${DRY_RUN}" -eq 1 ]; then
  log "dry-run OK portal=${PORTAL} project=${VERCEL_NAME} api_env=${API_ENV_VAR}"
  exit 0
fi

vercel_api() {
  local method="$1"
  local path="$2"
  local data="${3:-}"
  local attempt tmp code
  tmp="$(mktemp)"
  for attempt in 1 2 3; do
    if [ -n "${data}" ]; then
      code="$(curl -sS -o "${tmp}" -w '%{http_code}' \
        --connect-timeout 15 --max-time 60 \
        -X "${method}" \
        -H "Authorization: Bearer ${VERCEL_TOKEN}" \
        -H "Content-Type: application/json" \
        --data "${data}" \
        "https://api.vercel.com/${path}" 2>/dev/null || echo 000)"
    else
      code="$(curl -sS -o "${tmp}" -w '%{http_code}' \
        --connect-timeout 15 --max-time 60 \
        -X "${method}" \
        -H "Authorization: Bearer ${VERCEL_TOKEN}" \
        "https://api.vercel.com/${path}" 2>/dev/null || echo 000)"
    fi
    if [[ "${code}" =~ ^2 ]]; then
      cat "${tmp}"
      rm -f "${tmp}"
      return 0
    fi
    if [ "${code}" = "429" ] && [ "${attempt}" -lt 3 ]; then
      sleep $((attempt * 4))
      continue
    fi
    printf '::error::Vercel %s %s -> HTTP %s: ' "${method}" "${path%%\?*}" "${code}" >&2
    head -c 400 "${tmp}" >&2 || true
    printf '\n' >&2
    rm -f "${tmp}"
    return 1
  done
  rm -f "${tmp}"
  return 1
}

verify_project_env() {
  local env_json tmp_env_json verdict
  # decrypt=true: without it Vercel returns ciphertext for encrypted/secret/
  # sensitive rows, not the plaintext value — this is not evidence of a leaked
  # credential, it is the documented shape of an un-decrypted response.
  # gitBranch=staging: server-side filter for branch-scoped Preview rows;
  # vercel_preview_env_verify.py independently re-checks each row's own
  # gitBranch field, so selection stays correct regardless of exactly which
  # rows the filter returns.
  if ! env_json="$(vercel_api GET "v9/projects/${PROJECT_ID}/env?teamId=${VERCEL_ORG_ID}&decrypt=true&gitBranch=staging")"; then
    printf '%s' "BLOCKED_EXTERNAL"
    return 0
  fi

  tmp_env_json="$(mktemp)"
  printf '%s' "${env_json}" > "${tmp_env_json}"
  verdict="$(python3 "${REPO_ROOT}/scripts/ci/vercel_preview_env_verify.py" \
    --key "${API_ENV_VAR}" \
    --git-branch staging \
    --expected-host "${EXPECTED_API_HOST}" \
    --env-json-file "${tmp_env_json}")"
  rm -f "${tmp_env_json}"
  printf '%s' "${verdict}"
}

create_deployment() {
  local payload
  payload="$(PROJECT_ID="${PROJECT_ID}" VERCEL_NAME="${VERCEL_NAME}" \
    GITHUB_ORG="${GITHUB_ORG}" GITHUB_REPO="${GITHUB_REPO}" GITHUB_REF_NAME="${GITHUB_REF_NAME}" \
    python3 - <<'PY'
import json, os
print(json.dumps({
    "name": os.environ["VERCEL_NAME"],
    "project": os.environ["PROJECT_ID"],
    "gitSource": {
        "type": "github",
        "org": os.environ["GITHUB_ORG"],
        "repo": os.environ["GITHUB_REPO"],
        "ref": os.environ["GITHUB_REF_NAME"],
    },
}))
PY
)"
  vercel_api POST "v13/deployments?teamId=${VERCEL_ORG_ID}" "${payload}"
}

parse_deployment_metadata() {
  DEPLOYMENT_JSON="$1" python3 - <<'PY'
import json, os
doc = json.loads(os.environ["DEPLOYMENT_JSON"])
meta = doc.get("meta") or {}
print("\t".join([
    doc.get("readyState") or doc.get("state") or "UNKNOWN",
    doc.get("target") or "preview",
    doc.get("projectId") or "",
    meta.get("githubCommitSha") or meta.get("gitCommitSha") or "",
    doc.get("url") or "",
    doc.get("id") or doc.get("uid") or "",
]))
PY
}

log "creating Preview deployment for ${VERCEL_NAME} @ ${GITHUB_SHA:0:12}"
deployment="$(create_deployment)"
deployment_id="$(DEPLOYMENT_JSON="${deployment}" python3 - <<'PY'
import json, os, sys
doc = json.loads(os.environ["DEPLOYMENT_JSON"])
deployment_id = doc.get("id") or doc.get("uid")
if not deployment_id:
    print("::error::create response missing deployment id", file=sys.stderr)
    raise SystemExit(1)
print(deployment_id)
PY
)"
log "deployment id ${deployment_id}"

ready_state=""
target=""
project_id=""
commit_sha=""
deployment_url=""

for attempt in $(seq 1 60); do
  deployment="$(vercel_api GET "v13/deployments/${deployment_id}?teamId=${VERCEL_ORG_ID}")"
  IFS=$'\t' read -r ready_state target project_id commit_sha deployment_url _ <<< "$(parse_deployment_metadata "${deployment}")"

  case "${target}" in
    preview) ;;
    *) die "deployment target must be preview, got ${target}" ;;
  esac

  if [ "${project_id}" != "${PROJECT_ID}" ]; then
    die "deployment project id does not match expected ${PORTAL} project"
  fi

  case "${ready_state}" in
    READY)
      if [ "${commit_sha}" != "${GITHUB_SHA}" ]; then
        die "deployment SHA mismatch: got ${commit_sha:-missing}, want ${GITHUB_SHA}"
      fi
      if [ -z "${deployment_url}" ]; then
        die "ready deployment has no URL"
      fi
      break
      ;;
    ERROR|CANCELED)
      die "Vercel Preview finished ${ready_state}"
      ;;
    *)
      log "state ${ready_state} (attempt ${attempt}/60)"
      sleep 5
      ready_state=""
      ;;
  esac
done

if [ "${ready_state}" != "READY" ]; then
  die "timed out waiting for Preview deployment"
fi

preview_url="https://${deployment_url}"
log "READY ${preview_url}"

# Secondary, NON-BLOCKING signal: what Vercel's stored project config says.
# Kept for informational/troubleshooting value (see vercel_preview_env_verify.py's
# docstring for why Vercel can refuse to decrypt a row for reasons outside this
# repo's control) — it must never fail the deploy. The PRIMARY, blocking proof
# is the live artifact's own /health response, below.
api_env_verdict="$(verify_project_env)"
log "env metadata (informational only, non-blocking): ${API_ENV_VAR} -> ${api_env_verdict}"
env_metadata_status="${api_env_verdict}"

# ==========================================================================
# PRIMARY PROOF: effective deployed configuration, read from the live
# artifact's own /health response — not Vercel's stored (and possibly
# undecryptable) project settings. Blocking for all three portals.
# See scripts/ci/vercel_preview_health_verify.py for the assertion contract.
# ==========================================================================
health_path="/${HEALTH_LOCALE}/health"
health_url="${preview_url}${health_path}"
health_body_file="${OUTPUT_DIR}/health.json"
health_headers_file="${OUTPUT_DIR}/health-headers.txt"

# Resolve this portal's Deployment Protection bypass secret. Presence is
# checked one source at a time in precedence order; the values are never
# compared to each other, so nothing here can reveal whether two projects
# share a secret.
portal_upper="$(printf '%s' "${PORTAL}" | tr '[:lower:]' '[:upper:]')"
portal_secret_var="VERCEL_AUTOMATION_BYPASS_SECRET_${portal_upper}"
BYPASS_SECRET=""
BYPASS_SOURCE="none"
BYPASS_SOURCE_VAR=""
if [ -n "${VERCEL_PORTAL_BYPASS_SECRET:-}" ]; then
  BYPASS_SECRET="${VERCEL_PORTAL_BYPASS_SECRET}"
  BYPASS_SOURCE="portal_scoped"
  BYPASS_SOURCE_VAR="VERCEL_PORTAL_BYPASS_SECRET"
elif [ -n "${!portal_secret_var:-}" ]; then
  BYPASS_SECRET="${!portal_secret_var}"
  BYPASS_SOURCE="portal_specific"
  BYPASS_SOURCE_VAR="${portal_secret_var}"
elif [ -n "${VERCEL_AUTOMATION_BYPASS_SECRET:-}" ]; then
  BYPASS_SECRET="${VERCEL_AUTOMATION_BYPASS_SECRET}"
  BYPASS_SOURCE="fallback"
  BYPASS_SOURCE_VAR="VERCEL_AUTOMATION_BYPASS_SECRET"
fi

# Only the SOURCE (kind + variable name) is ever logged — never the value.
if [ "${BYPASS_SOURCE}" = "none" ]; then
  log "protection bypass: none configured for ${PORTAL} (probe will be unauthenticated)"
else
  log "protection bypass: using ${BYPASS_SOURCE_VAR} (${BYPASS_SOURCE})"
fi

# The secret goes to curl via a mode-600 config file so it never appears in
# argv (visible to `ps`), in a URL, or in any trace. `set -x` is deliberately
# never enabled in this script; the config file is removed immediately after
# the request in all paths. Only the two bypass headers live in the config —
# every other flag stays on the command line, keeping the config-parsing
# surface to the one thing that must not be in argv.
health_curl_config="$(mktemp)"
chmod 600 "${health_curl_config}"
cleanup_health_curl_config() { rm -f "${health_curl_config}"; }
trap cleanup_health_curl_config EXIT
# Exactly the headers Vercel documents for a ONE-SHOT automation request:
# `x-vercel-protection-bypass` alone (their own curl example sends nothing
# else). `x-vercel-set-bypass-cookie` is documented as OPTIONAL and exists to
# "maintain authorization across multiple requests or within iframes" — it is
# for browser/follow-up flows such as Playwright, which keeps it. This probe
# makes a single request that already carries the bypass header, so the cookie
# header is not sent here; run #33 returned HTTP 307 on all three portals with
# it set, and asking for a cookie is the one part of this request that has any
# documented reason to involve a redirect.
{
  printf 'header = "Accept: application/json"\n'
  if [ -n "${BYPASS_SECRET}" ]; then
    printf 'header = "x-vercel-protection-bypass: %s"\n' "${BYPASS_SECRET}"
  fi
} > "${health_curl_config}"

# deploy-staging run #32 failed all three portals here: curl exited non-zero
# roughly 0.7s after READY, before any HTTP response, and the probe discarded
# stderr — so the exact transport failure is UNKNOWN and no root cause can be
# asserted from that run. Two independent corrections follow: retry genuinely
# transient transport errors, and preserve curl's real diagnostic so a
# deterministic failure is identifiable on the next run instead of being
# retried blindly.
#
# Retry eligibility is decided by curl's exit code, classified against
# libcurl's CURLE_* enum in scripts/ci/vercel_preview_access.py. Only
# TRANSIENT_TRANSPORT codes retry; deterministic failures (malformed URL,
# local read/write, certificate validation, anything unrecognised) fail
# immediately. An HTTP response of ANY status is never retried — it means the
# endpoint answered, and it goes to classify_access() below, so a 302
# protection challenge still reaches the Deployment Protection classifier on
# the first attempt.
health_stderr_file="${OUTPUT_DIR}/health-curl-stderr.txt"

# curl with --show-error and without -v never echoes request headers, so the
# bypass secret cannot appear in its stderr. Redact defensively anyway, using
# pure bash parameter expansion so the secret never reaches an argv or a pipe.
sanitized_curl_error() {
  local raw
  raw="$(tr -d '\r' < "${health_stderr_file}" 2>/dev/null | tail -1)"
  if [ -n "${BYPASS_SECRET}" ]; then
    raw="${raw//${BYPASS_SECRET}/[redacted]}"
  fi
  printf '%s' "${raw}"
}

health_http=""
health_rc=1
health_exit_kind="NON_RETRYABLE_CURL"
health_exit_name=""
for health_attempt in 1 2 3 4 5; do
  set +e
  health_http="$(curl --config "${health_curl_config}" \
    --silent --show-error --no-location \
    --connect-timeout 15 --max-time 30 \
    -o "${health_body_file}" -D "${health_headers_file}" -w '%{http_code}' \
    "${health_url}" 2>"${health_stderr_file}")"
  health_rc=$?
  set -e

  if [ "${health_rc}" -eq 0 ]; then
    health_exit_kind="HTTP_RESPONSE"
    break
  fi

  IFS=$'\t' read -r health_exit_kind health_exit_retryable health_exit_name < <(
    python3 "${REPO_ROOT}/scripts/ci/vercel_preview_access.py" classify-curl-exit \
      --code "${health_rc}"
  )

  log "health probe attempt ${health_attempt}/5 failed — curl exit ${health_rc} ${health_exit_name:-unknown} [${health_exit_kind}]: $(sanitized_curl_error)"

  if [ "${health_exit_retryable}" != "1" ]; then
    break
  fi
  if [ "${health_attempt}" -lt 5 ]; then
    sleep $((health_attempt * 3))
  fi
done

cleanup_health_curl_config
trap - EXIT

if [ "${health_rc}" -ne 0 ]; then
  case "${health_exit_kind}" in
    TRANSIENT_TRANSPORT)
      die "TRANSIENT_TRANSPORT: ${PORTAL} health probe could not reach ${health_url} after 5 attempts — curl exit ${health_rc} ${health_exit_name:-unknown}: $(sanitized_curl_error). No HTTP response was ever received, so this is neither an application failure nor a Deployment Protection challenge."
      ;;
    *)
      die "NON_RETRYABLE_CURL: ${PORTAL} health probe failed deterministically against ${health_url} — curl exit ${health_rc} ${health_exit_name:-unknown}: $(sanitized_curl_error). This class of curl error cannot be fixed by retrying; no HTTP response was received."
      ;;
  esac
fi

# Classify BEFORE asserting health: a Deployment Protection challenge must
# never be reported as a broken application route (deploy-staging run #31,
# where all three routes were in fact correct and only the probe's access was
# missing). See scripts/ci/vercel_preview_access.py.
health_location="$(sed -n 's/^[Ll]ocation:[[:space:]]*//p' "${health_headers_file}" | tr -d '\r' | tail -1)"
bypass_present_flag=0
if [ -n "${BYPASS_SECRET}" ]; then
  bypass_present_flag=1
fi

access_verdict="$(python3 "${REPO_ROOT}/scripts/ci/vercel_preview_access.py" classify \
  --http-status "${health_http}" \
  --location "${health_location}" \
  --body-file "${health_body_file}" \
  --bypass-present "${bypass_present_flag}" \
  --print-detail)"

# Safe response metadata on any non-2xx, so a redirect is diagnosable without
# re-running: status line, whether a Location exists plus its host/path with
# the query stripped, whether a Set-Cookie exists (never its value), and the
# server header. Diagnostics only — it does not influence the verdict or
# weaken the gate.
case "${health_http}" in
  2??) ;;
  *)
    log "${PORTAL} response diagnostics: $(python3 "${REPO_ROOT}/scripts/ci/vercel_preview_access.py" \
      summarize-headers --headers-file "${health_headers_file}")"
    ;;
esac

case "${access_verdict}" in
  ok) ;;
  blocked_external)
    die "BLOCKED_EXTERNAL: ${PORTAL} Preview is behind Vercel Deployment Protection and the automation bypass is missing or invalid (HTTP ${health_http}). The application health route itself is NOT implicated. Configure the ${PORTAL} project's 'Protection Bypass for Automation' secret and expose it as ${portal_secret_var} (or VERCEL_PORTAL_BYPASS_SECRET for this job)."
    ;;
  app_error)
    die "${PORTAL} health returned HTTP ${health_http} — application runtime failure in the deployed Preview, not a protection challenge"
    ;;
  not_json)
    die "${PORTAL} health returned HTTP 200 but the body is not a JSON object — application or verifier failure"
    ;;
  *)
    die "${PORTAL} health returned HTTP ${health_http} (verdict ${access_verdict}) — want 200 with a JSON body"
    ;;
esac

health_verdict="$(python3 "${REPO_ROOT}/scripts/ci/vercel_preview_health_verify.py" \
  --app "${APP_ID}" \
  --expected-api-host "${EXPECTED_API_HOST}" \
  --expected-sha "${GITHUB_SHA}" \
  --health-json-file "${health_body_file}")"

case "${health_verdict}" in
  ok) log "${PORTAL} health OK — effective apiHost verified for staging SHA ${GITHUB_SHA:0:12}" ;;
  status) die "${PORTAL} health status is not ok" ;;
  app) die "${PORTAL} health app field does not match this portal" ;;
  env) die "${PORTAL} health env is not staging/preview" ;;
  missing_host) die "${PORTAL} health apiHost is missing/empty — deployed app has no effective API configuration" ;;
  forbidden_host) die "${PORTAL} health apiHost resolves to production or localhost — deployed app is wired to the wrong API" ;;
  host_mismatch) die "${PORTAL} health apiHost did not match the expected staging host" ;;
  sha_mismatch) die "${PORTAL} health buildId does not match candidate SHA ${GITHUB_SHA} — deployment may be stale" ;;
  *) die "unexpected health verdict: ${health_verdict}" ;;
esac

EVIDENCE_PATH="${VERCEL_PREVIEW_PROVE_EVIDENCE:-${OUTPUT_DIR}/evidence.json}"
PORTAL="${PORTAL}" \
VERCEL_NAME="${VERCEL_NAME}" \
PROJECT_ID="${PROJECT_ID}" \
GITHUB_SHA="${GITHUB_SHA}" \
deployment_id="${deployment_id}" \
preview_url="${preview_url}" \
commit_sha="${commit_sha}" \
env_metadata_status="${env_metadata_status}" \
bypass_source="${BYPASS_SOURCE}" \
health_body_file="${health_body_file}" \
EVIDENCE_PATH="${EVIDENCE_PATH}" \
python3 - <<'PY'
import json, os
from datetime import UTC, datetime

# Only the documented safe fields are read back out of health.json — never
# an env value, token, key, or arbitrary env var (see route.ts for the
# full contract each app's /health response is limited to). `bypass_source`
# is the NAME/kind of the protection-bypass source used, never its value.
with open(os.environ["health_body_file"], encoding="utf-8") as fh:
    health_body = json.load(fh)

doc = {
    "portal": os.environ["PORTAL"],
    "vercel_project": os.environ["VERCEL_NAME"],
    "project_id": os.environ["PROJECT_ID"],
    "candidate_sha": os.environ["GITHUB_SHA"],
    "deployment_id": os.environ["deployment_id"],
    "preview_url": os.environ["preview_url"],
    "deployment_sha": os.environ["commit_sha"],
    "target": "preview",
    "health_status": health_body.get("status"),
    "health_app": health_body.get("app"),
    "health_env": health_body.get("env"),
    "health_build_id": health_body.get("buildId"),
    "health_api_host": health_body.get("apiHost"),
    "env_metadata_status": os.environ["env_metadata_status"],
    "bypass_source": os.environ["bypass_source"],
    "proved_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
}
with open(os.environ["EVIDENCE_PATH"], "w", encoding="utf-8") as fh:
    json.dump(doc, fh, indent=2)
    fh.write("\n")
print(json.dumps(doc))
PY

printf '%s\n' "${deployment}" > "${OUTPUT_DIR}/deployment.json"

if [ -n "${GITHUB_OUTPUT:-}" ]; then
  {
    printf 'url=%s\n' "${preview_url}"
    printf 'deployment_id=%s\n' "${deployment_id}"
    printf 'sha=%s\n' "${commit_sha}"
    printf 'env_metadata_status=%s\n' "${env_metadata_status}"
    printf 'health_verdict=%s\n' "${health_verdict}"
  } >> "${GITHUB_OUTPUT}"
fi

log "evidence written to ${EVIDENCE_PATH}"
