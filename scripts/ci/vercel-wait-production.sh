#!/usr/bin/env bash
#
# vercel-wait-production.sh — await READY Production deployments at an exact SHA.
#
# Usage:
#   VERCEL_TOKEN=... bash scripts/ci/vercel-wait-production.sh --sha <40-char>
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERCEL_TEAM_ID="${VERCEL_TEAM_ID:-team_I2OEqmMjTwN2k5g7ACbQW705}"
VERCEL_API="${VERCEL_API:-https://api.vercel.com}"
CANDIDATE_SHA=""
TIMEOUT_SEC="${VERCEL_WAIT_TIMEOUT_SEC:-1800}"
POLL_SEC="${VERCEL_WAIT_POLL_SEC:-20}"
REPORT_PATH="${VERCEL_WAIT_REPORT:-/tmp/vergeo5-vercel-wait-production.json}"

declare -A PROJECT_IDS=(
  [customer]=prj_lK6jnhAfVmhtaDZdMsIUF7LswgTP
  [vendor]=prj_QiX9rpStSpNeEXd3UZDFFp7H2dXf
  [admin]=prj_Bpf852KXDuG1NZUomri0OsMBt1YS
)

log() { printf '==> %s\n' "$*"; }
die() { printf '::error::%s\n' "$*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sha) CANDIDATE_SHA="${2:-}"; shift 2 ;;
    --report) REPORT_PATH="${2:-}"; shift 2 ;;
    --timeout) TIMEOUT_SEC="${2:-}"; shift 2 ;;
    -h|--help)
      sed -n '2,8p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) die "unknown argument: $1" ;;
  esac
done

[[ "$CANDIDATE_SHA" =~ ^[0-9a-f]{40}$ ]] || die "--sha must be a 40-char git SHA"

if [[ -z "${VERCEL_TOKEN:-}" ]]; then
  die "VERCEL_TOKEN is required"
fi

vercel_rest_get() {
  local path="$1"
  curl -fsS --connect-timeout 15 --max-time 45 \
    -H "Authorization: Bearer ${VERCEL_TOKEN}" \
    "${VERCEL_API}/${path}"
}

deployment_matches() {
  local json="$1"
  CANDIDATE_SHA="$CANDIDATE_SHA" python3 -c '
import json, os, sys
sha = os.environ["CANDIDATE_SHA"]
doc = json.loads(sys.argv[1])
rows = doc.get("deployments", []) if isinstance(doc, dict) else []
for row in rows:
    meta = row.get("meta") or {}
    commit = (meta.get("githubCommitSha") or meta.get("gitCommitSha") or "").lower()
    target = (row.get("target") or "").lower()
    state = (row.get("readyState") or row.get("state") or "").upper()
    uid = row.get("uid") or row.get("id") or ""
    if target == "production" and state == "READY" and commit == sha:
        print(uid)
        sys.exit(0)
sys.exit(1)
' "$json"
}

wait_project() {
  local name="$1"
  local project_id="${PROJECT_IDS[$name]}"
  local deadline=$((SECONDS + TIMEOUT_SEC))
  local dpl_id=""

  while [[ "$SECONDS" -lt "$deadline" ]]; do
    local json
    if json="$(vercel_rest_get "v6/deployments?projectId=${project_id}&teamId=${VERCEL_TEAM_ID}&limit=25&target=production")"; then
      if dpl_id="$(deployment_matches "$json" 2>/dev/null || true)" && [[ -n "$dpl_id" ]]; then
        printf '%s\tPASS\t%s\n' "$name" "$dpl_id"
        return 0
      fi
    fi
    log "waiting for ${name} production READY @ ${CANDIDATE_SHA:0:12}..."
    sleep "$POLL_SEC"
  done
  printf '%s\tFAIL\ttimeout\n' "$name"
  return 1
}

main() {
  log "await production deployments sha=${CANDIDATE_SHA} timeout=${TIMEOUT_SEC}s"
  local overall=0
  local rows=()
  local name
  for name in customer vendor admin; do
    if row="$(wait_project "$name")"; then
      rows+=("$row")
    else
      rows+=("$row")
      overall=1
    fi
  done

  python3 - "$REPORT_PATH" "$CANDIDATE_SHA" "$overall" "${rows[@]}" <<'PY'
import json, sys
from datetime import UTC, datetime

report_path, sha, overall, *rows = sys.argv[1:]
projects = []
for row in rows:
    name, status, detail = (row.split("\t") + ["", "", ""])[:3]
    projects.append({"project": name, "status": status, "detail": detail})
payload = {
    "gate": "vercel_wait_production",
    "candidate_sha": sha,
    "verdict": "pass" if overall == "0" else "fail",
    "projects": projects,
    "finished_at": datetime.now(UTC).isoformat(),
}
with open(report_path, "w", encoding="utf-8") as fh:
    json.dump(payload, fh, indent=2)
print(f"report={report_path} verdict={payload['verdict']}")
PY

  exit "$overall"
}

main "$@"
