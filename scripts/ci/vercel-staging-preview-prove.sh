#!/usr/bin/env bash
# Deploy a Git-source Vercel Preview for one portal on the staging branch,
# await READY, verify SHA/target/project, check API env wiring, and probe health.
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
  local env_json verdict host
  verdict="verified"
  if ! env_json="$(vercel_api GET "v9/projects/${PROJECT_ID}/env?teamId=${VERCEL_ORG_ID}")"; then
    printf '%s' "BLOCKED_EXTERNAL"
    return 0
  fi

  API_ENV_VAR="${API_ENV_VAR}" \
  EXPECTED_API_HOST="${EXPECTED_API_HOST}" \
  ENV_JSON="${env_json}" \
  python3 - <<'PY'
import json, os, sys

var = os.environ["API_ENV_VAR"]
expected_host = os.environ["EXPECTED_API_HOST"]
doc = json.loads(os.environ["ENV_JSON"])
rows = doc if isinstance(doc, list) else doc.get("envs", doc.get("environmentVariables", []))
if not isinstance(rows, list):
    print("BLOCKED_EXTERNAL")
    sys.exit(0)

def matches_preview(row):
    target = row.get("target") or []
    if isinstance(target, str):
        target = [target]
    targets = {t.lower() for t in target}
    if "preview" not in targets and "development" not in targets:
        return False
    git_branch = row.get("gitBranch") or row.get("branch") or ""
    if git_branch and git_branch != "staging":
        return False
    return True

value = None
for row in rows:
    if row.get("key") != var:
        continue
    if not matches_preview(row):
        continue
    value = row.get("value") or ""
    break

if not value:
    print("missing")
    sys.exit(0)

lower = value.lower()
if "api.vergeo5.com" in lower or "localhost" in lower:
    print("forbidden")
    sys.exit(0)
host = value.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0].lower()
if host != expected_host.lower():
    print(f"host_mismatch:{host}")
    sys.exit(0)
print("verified")
PY
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

api_env_verdict="$(verify_project_env)"
case "${api_env_verdict}" in
  verified) log "API env ${API_ENV_VAR} verified for staging Preview" ;;
  missing) die "Vercel Preview env ${API_ENV_VAR} missing for branch staging" ;;
  forbidden) die "Vercel Preview env ${API_ENV_VAR} points at production or localhost" ;;
  host_mismatch:*)
    got_host="${api_env_verdict#host_mismatch:}"
    die "Vercel Preview env ${API_ENV_VAR} host ${got_host} != expected ${EXPECTED_API_HOST}"
    ;;
  BLOCKED_EXTERNAL)
    die "Vercel Preview env ${API_ENV_VAR} BLOCKED_EXTERNAL — cannot verify staging API wiring"
    ;;
  *)
    die "unexpected API env verdict: ${api_env_verdict}"
    ;;
esac

health_path="/${HEALTH_LOCALE}/health"
health_url="${preview_url}${health_path}"
health_verdict="skipped"
health_http=""
health_body_file="${OUTPUT_DIR}/health.json"

set +e
health_http="$(curl -sS -o "${health_body_file}" -w '%{http_code}' \
  --connect-timeout 15 --max-time 30 "${health_url}" 2>/dev/null)"
health_rc=$?
set -e

if [ "${health_rc}" -ne 0 ]; then
  health_verdict="unreachable"
  die "health probe failed to connect ${health_url}"
fi

if [ "${PORTAL}" = "admin" ]; then
  if [ "${health_http}" = "403" ]; then
    if grep -q "Cloudflare Access" "${health_body_file}" 2>/dev/null; then
      health_verdict="cf_access_gate"
      log "admin health returned 403 (CF Access gate — expected on Preview)"
    else
      die "admin health 403 without CF Access marker"
    fi
  elif [ "${health_http}" = "200" ]; then
    health_verdict="ok"
    log "admin health returned 200 (bypass or non-prod gate)"
  else
    die "admin health unexpected HTTP ${health_http}"
  fi
else
  if [ "${health_http}" != "200" ]; then
    die "${PORTAL} health returned HTTP ${health_http}, want 200"
  fi
  PORTAL="${PORTAL}" HEALTH_BODY_FILE="${health_body_file}" python3 - <<'PY'
import json, os, sys
portal = os.environ["PORTAL"]
with open(os.environ["HEALTH_BODY_FILE"], encoding="utf-8") as fh:
    body = json.load(fh)
if body.get("status") != "ok":
    print(f"::error::health status={body.get('status')!r}", file=sys.stderr)
    sys.exit(1)
if body.get("app") != portal:
    print(f"::error::health app={body.get('app')!r} want {portal}", file=sys.stderr)
    sys.exit(1)
env = body.get("env") or ""
if env not in {"staging", "preview", "development"}:
    print(f"::warning::health env={env!r}")
print("ok")
PY
  health_verdict="ok"
  log "${PORTAL} health OK"
fi

EVIDENCE_PATH="${VERCEL_PREVIEW_PROVE_EVIDENCE:-${OUTPUT_DIR}/evidence.json}"
PORTAL="${PORTAL}" \
VERCEL_NAME="${VERCEL_NAME}" \
PROJECT_ID="${PROJECT_ID}" \
GITHUB_SHA="${GITHUB_SHA}" \
deployment_id="${deployment_id}" \
preview_url="${preview_url}" \
commit_sha="${commit_sha}" \
api_env_var="${API_ENV_VAR}" \
api_env_verdict="${api_env_verdict}" \
health_verdict="${health_verdict}" \
health_http="${health_http}" \
EVIDENCE_PATH="${EVIDENCE_PATH}" \
python3 - <<'PY'
import json, os
from datetime import UTC, datetime

doc = {
    "portal": os.environ["PORTAL"],
    "vercel_project": os.environ["VERCEL_NAME"],
    "project_id": os.environ["PROJECT_ID"],
    "candidate_sha": os.environ["GITHUB_SHA"],
    "deployment_id": os.environ["deployment_id"],
    "deployment_url": os.environ["preview_url"],
    "github_commit_sha": os.environ["commit_sha"],
    "target": "preview",
    "api_env_var": os.environ["api_env_var"],
    "api_env_verdict": os.environ["api_env_verdict"],
    "health_url": os.environ["preview_url"] + "/en/health",
    "health_http": os.environ["health_http"],
    "health_verdict": os.environ["health_verdict"],
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
    printf 'api_env_verdict=%s\n' "${api_env_verdict}"
    printf 'health_verdict=%s\n' "${health_verdict}"
  } >> "${GITHUB_OUTPUT}"
fi

log "evidence written to ${EVIDENCE_PATH}"
