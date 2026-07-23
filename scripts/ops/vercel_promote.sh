#!/usr/bin/env bash
#
# vercel_promote.sh — promote customer/vendor/admin to production (founder-gated).
#
# Talks to the Vercel REST API directly (curl + Bearer token); no `vercel` CLI
# dependency. Respects rate limits (HTTP 429) with backoff. Records deployment
# ids + commit SHAs to a JSON report.
#
# Usage:
#   VERCEL_TOKEN=... bash scripts/ops/vercel_promote.sh
#   VERCEL_TOKEN=... bash scripts/ops/vercel_promote.sh --dry-run
#   VERCEL_TOKEN=... bash scripts/ops/vercel_promote.sh --project customer
#
# Environment:
#   VERCEL_TOKEN              Required (never log)
#   VERCEL_TEAM_ID            Default team_I2OEqmMjTwN2k5g7ACbQW705 (vergeo-projects)
#   VERCEL_API                Default https://api.vercel.com
#   MASTER_GIT_SHA            Expected tip (default: git rev-parse HEAD)
#   VERCEL_PROMOTE_REPORT     Output JSON (default /tmp/vergeo5-vercel-promote.json)
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERCEL_TEAM_ID="${VERCEL_TEAM_ID:-team_I2OEqmMjTwN2k5g7ACbQW705}"
VERCEL_API="${VERCEL_API:-https://api.vercel.com}"
VERCEL_PROMOTE_REPORT="${VERCEL_PROMOTE_REPORT:-/tmp/vergeo5-vercel-promote.json}"
MASTER_GIT_SHA="${MASTER_GIT_SHA:-}"
CURL_BIN="${CURL_BIN:-curl}"

declare -A PROJECT_IDS=(
  [customer]=prj_lK6jnhAfVmhtaDZdMsIUF7LswgTP
  [vendor]=prj_QiX9rpStSpNeEXd3UZDFFp7H2dXf
  [admin]=prj_Bpf852KXDuG1NZUomri0OsMBt1YS
)

DRY_RUN=0
ONLY_PROJECT=""
# Accumulated per-project rows for the JSON report: "name\tstatus\tdpl\tsha\tdetail".
declare -a REPORT_ROWS=()

log() { printf '==> %s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --project)
      ONLY_PROJECT="${2:-}"
      shift 2
      ;;
    -h|--help)
      sed -n '2,18p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
  esac
done

if [[ -z "$MASTER_GIT_SHA" ]]; then
  MASTER_GIT_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
fi

if [[ -z "${VERCEL_TOKEN:-}" ]]; then
  log "SKIP: VERCEL_TOKEN unset — founder must promote in Vercel dashboard"
  exit 0
fi

# GET a Vercel REST path (relative to $VERCEL_API). Body -> stdout; retries on 429.
vercel_rest_get() {
  local path="$1"
  local attempt=0 max=4 delay=4 code tmp
  tmp="$(mktemp)"
  while [[ "$attempt" -lt "$max" ]]; do
    code="$("$CURL_BIN" -sS -o "$tmp" -w '%{http_code}' \
      --connect-timeout 15 --max-time 45 \
      -H "Authorization: Bearer ${VERCEL_TOKEN}" \
      "${VERCEL_API}/${path}" 2>/dev/null || echo 000)"
    if [[ "$code" == "429" ]]; then
      warn "Vercel rate limit (GET) — sleeping ${delay}s (attempt $((attempt + 1))/${max})"
      sleep "$delay"; delay=$((delay * 2)); attempt=$((attempt + 1)); continue
    fi
    if [[ "$code" =~ ^2 ]]; then cat "$tmp"; rm -f "$tmp"; return 0; fi
    warn "Vercel GET ${path%%\?*} -> HTTP ${code}"
    rm -f "$tmp"; return 1
  done
  rm -f "$tmp"; return 1
}

# POST (empty body) a Vercel REST path. Returns 0 on 2xx; retries on 429.
vercel_rest_post() {
  local path="$1"
  local attempt=0 max=4 delay=4 code tmp
  tmp="$(mktemp)"
  while [[ "$attempt" -lt "$max" ]]; do
    code="$("$CURL_BIN" -sS -o "$tmp" -w '%{http_code}' -X POST \
      --connect-timeout 15 --max-time 45 \
      -H "Authorization: Bearer ${VERCEL_TOKEN}" \
      -H 'Content-Length: 0' \
      "${VERCEL_API}/${path}" 2>/dev/null || echo 000)"
    if [[ "$code" == "429" ]]; then
      warn "Vercel rate limit (POST) — sleeping ${delay}s (attempt $((attempt + 1))/${max})"
      sleep "$delay"; delay=$((delay * 2)); attempt=$((attempt + 1)); continue
    fi
    if [[ "$code" =~ ^2 ]]; then rm -f "$tmp"; return 0; fi
    warn "Vercel POST ${path%%\?*} -> HTTP ${code}: $(head -c 300 "$tmp" 2>/dev/null)"
    rm -f "$tmp"; return 1
  done
  rm -f "$tmp"; return 1
}

# Pick the newest READY/BUILDING deployment matching MASTER_GIT_SHA from a
# /deployments list payload. Emits "uid\tcommitSha" (or nothing) on stdout.
select_deployment() {
  MASTER_GIT_SHA="$MASTER_GIT_SHA" python3 -c '
import json, os, sys
sha = os.environ.get("MASTER_GIT_SHA", "")
raw = sys.stdin.read().strip()
if not raw:
    raise SystemExit
try:
    doc = json.loads(raw)
except json.JSONDecodeError:
    raise SystemExit
rows = doc.get("deployments", []) if isinstance(doc, dict) else (doc if isinstance(doc, list) else [])
for row in rows:
    meta = row.get("meta") or {}
    commit = meta.get("githubCommitSha") or meta.get("gitCommitSha") or ""
    state = (row.get("state") or row.get("readyState") or "").upper()
    uid = row.get("uid") or row.get("id") or ""
    if not uid:
        continue
    if state in ("READY", "BUILDING") and (not sha or (commit and (commit.startswith(sha[:7]) or sha.startswith(commit[:7])))):
        print(uid + "\t" + commit)
        break
'
}

promote_project() {
  local name="$1"
  local project_id="${PROJECT_IDS[$name]}"
  log "Project ${name} (${project_id}) — latest ready deployment for ${MASTER_GIT_SHA}"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    REPORT_ROWS+=("${name}"$'\t'"SKIP"$'\t'""$'\t'""$'\t'"dry-run")
    printf '%s\tSKIP\tdry-run\n' "$name"
    return 0
  fi

  local deployments_json
  if ! deployments_json="$(vercel_rest_get "v6/deployments?projectId=${project_id}&teamId=${VERCEL_TEAM_ID}&limit=20")"; then
    warn "${name}: could not list deployments"
    REPORT_ROWS+=("${name}"$'\t'"FAIL"$'\t'""$'\t'""$'\t'"list_error")
    printf '%s\tFAIL\tlist_error\n' "$name"
    return 1
  fi

  local match dpl_id dpl_sha
  match="$(printf '%s' "$deployments_json" | select_deployment 2>/dev/null || true)"
  dpl_id="${match%%$'\t'*}"
  dpl_sha="${match#*$'\t'}"
  [[ "$dpl_sha" == "$match" ]] && dpl_sha=""

  if [[ -z "$dpl_id" ]]; then
    warn "${name}: no matching READY deployment for ${MASTER_GIT_SHA} — trigger a build from master first"
    REPORT_ROWS+=("${name}"$'\t'"FAIL"$'\t'""$'\t'""$'\t'"no_deployment")
    printf '%s\tFAIL\tno_deployment\n' "$name"
    return 1
  fi

  if vercel_rest_post "v10/projects/${project_id}/promote/${dpl_id}?teamId=${VERCEL_TEAM_ID}"; then
    REPORT_ROWS+=("${name}"$'\t'"PASS"$'\t'"${dpl_id}"$'\t'"${dpl_sha}"$'\t'"promoted")
    printf '%s\tPASS\tdpl=%s sha=%s\n' "$name" "$dpl_id" "${dpl_sha:0:7}"
    return 0
  fi
  REPORT_ROWS+=("${name}"$'\t'"FAIL"$'\t'"${dpl_id}"$'\t'"${dpl_sha}"$'\t'"promote_error")
  printf '%s\tFAIL\tpromote_error dpl=%s\n' "$name" "$dpl_id"
  return 1
}

write_report() {
  local overall="$1"
  local probe_verdict="$2"
  local verdict="pass"
  [[ "$overall" -ne 0 ]] && verdict="fail"
  [[ "$DRY_RUN" -eq 1 ]] && verdict="skip"

  local rows_tmp
  rows_tmp="$(mktemp)"
  if [[ "${#REPORT_ROWS[@]}" -gt 0 ]]; then
    printf '%s\n' "${REPORT_ROWS[@]}" >"$rows_tmp"
  fi

  python3 - "$VERCEL_PROMOTE_REPORT" "$verdict" "$probe_verdict" "$MASTER_GIT_SHA" "$rows_tmp" <<'PY'
import json, sys
from datetime import UTC, datetime

report_path, verdict, probe_verdict, sha, rows_path = sys.argv[1:6]
projects = []
with open(rows_path, encoding="utf-8") as fh:
    for line in fh.read().splitlines():
        if not line.strip():
            continue
        name, status, dpl, dsha, detail = (line.split("\t") + [""] * 5)[:5]
        projects.append(
            {"project": name, "status": status, "deployment": dpl, "sha": dsha, "detail": detail}
        )
payload = {
    "gate": "Vercel",
    "verdict": verdict,
    "master_sha": sha,
    "frontend_probes": probe_verdict,
    "projects": projects,
    "finished_at": datetime.now(UTC).isoformat(),
}
with open(report_path, "w", encoding="utf-8") as fh:
    json.dump(payload, fh, indent=2)
print(f"report={report_path} verdict={verdict}")
PY
  rm -f "$rows_tmp"
}

main() {
  log "Vercel promote — team=${VERCEL_TEAM_ID} sha=${MASTER_GIT_SHA}"
  local overall=0
  local name
  for name in customer vendor admin; do
    if [[ -n "$ONLY_PROJECT" && "$ONLY_PROJECT" != "$name" ]]; then
      continue
    fi
    if ! promote_project "$name"; then
      overall=1
    fi
    sleep 2
  done

  local probe_verdict="skipped"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    log "Post-promote probes:"
    if bash "${REPO_ROOT}/scripts/ops/probe-frontends.sh"; then
      probe_verdict="pass"
      log "Frontend probes PASS"
    else
      probe_verdict="fail"
      overall=1
    fi
  fi

  write_report "$overall" "$probe_verdict"
  exit "$overall"
}

main "$@"
