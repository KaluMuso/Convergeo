#!/usr/bin/env bash
#
# vercel_promote.sh — promote customer/vendor/admin to production (founder-gated).
#
# Requires VERCEL_TOKEN and network access to Vercel API. Respects rate limits with
# backoff. Records deployment ids + commit SHAs to a JSON report.
#
# Usage:
#   VERCEL_TOKEN=... bash scripts/ops/vercel_promote.sh
#   VERCEL_TOKEN=... bash scripts/ops/vercel_promote.sh --dry-run
#   VERCEL_TOKEN=... bash scripts/ops/vercel_promote.sh --project customer
#
# Environment:
#   VERCEL_TOKEN              Required (never log)
#   VERCEL_TEAM_ID            Default team_I2OEqmMjTwN2k5g7ACbQW705 (vergeo-projects)
#   MASTER_GIT_SHA            Expected tip (default: git rev-parse HEAD)
#   VERCEL_PROMOTE_REPORT     Output JSON (default /tmp/vergeo5-vercel-promote.json)
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERCEL_TEAM_ID="${VERCEL_TEAM_ID:-team_I2OEqmMjTwN2k5g7ACbQW705}"
VERCEL_PROMOTE_REPORT="${VERCEL_PROMOTE_REPORT:-/tmp/vergeo5-vercel-promote.json}"
MASTER_GIT_SHA="${MASTER_GIT_SHA:-}"

declare -A PROJECT_IDS=(
  [customer]=prj_lK6jnhAfVmhtaDZdMsIUF7LswgTP
  [vendor]=prj_QiX9rpStSpNeEXd3UZDFFp7H2dXf
  [admin]=prj_Bpf852KXDuG1NZUomri0OsMBt1YS
)

DRY_RUN=0
ONLY_PROJECT=""

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

if ! command -v vercel >/dev/null 2>&1; then
  log "Installing vercel CLI (npx)..."
  NPM_CONFIG_YES=true npx --yes vercel@latest --version >/dev/null
  VERCEL_BIN=(npx --yes vercel@latest)
else
  VERCEL_BIN=(vercel)
fi

vercel_api() {
  local attempt=0
  local max=4
  local delay=4
  while [[ "$attempt" -lt "$max" ]]; do
    if "${VERCEL_BIN[@]}" "$@" 2>/tmp/vercel-promote-err.txt; then
      return 0
    fi
    if grep -qi 'rate limit' /tmp/vercel-promote-err.txt 2>/dev/null; then
      warn "Vercel rate limit — sleeping ${delay}s (attempt $((attempt + 1))/${max})"
      sleep "$delay"
      delay=$((delay * 2))
      attempt=$((attempt + 1))
      continue
    fi
    cat /tmp/vercel-promote-err.txt >&2
    return 1
  done
  return 1
}

promote_project() {
  local name="$1"
  local project_id="${PROJECT_IDS[$name]}"
  log "Project ${name} (${project_id}) — finding latest ready deployment for ${MASTER_GIT_SHA}"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '%s\tSKIP\tdry-run\n' "$name"
    return 0
  fi

  local deployments_json
  deployments_json="$(vercel_api list "${project_id}" --token "$VERCEL_TOKEN" --scope "$VERCEL_TEAM_ID" 2>/dev/null || true)"

  local dpl_id dpl_sha
  dpl_id="$(printf '%s' "$deployments_json" | python3 -c '
import json, sys, os
sha = os.environ.get("MASTER_GIT_SHA", "")
raw = sys.stdin.read().strip()
if not raw:
    print("")
    raise SystemExit
try:
    rows = json.loads(raw)
except json.JSONDecodeError:
  # vercel CLI table output fallback — cannot parse
    print("")
    raise SystemExit
for row in rows if isinstance(rows, list) else rows.get("deployments", []):
    meta = row.get("meta") or {}
    commit = meta.get("githubCommitSha") or meta.get("gitCommitSha") or ""
    state = (row.get("state") or row.get("readyState") or "").upper()
    target = row.get("target") or ""
    uid = row.get("uid") or row.get("id") or ""
    if state in ("READY", "BUILDING") and (not sha or commit.startswith(sha[:7]) or sha.startswith(commit[:7])):
        print(uid)
        break
' MASTER_GIT_SHA="$MASTER_GIT_SHA" 2>/dev/null || echo '')"

  if [[ -z "$dpl_id" ]]; then
    warn "${name}: no matching deployment — trigger a preview build from master first"
    printf '%s\tFAIL\tno_deployment\n' "$name"
    return 1
  fi

  if vercel_api promote "$dpl_id" --token "$VERCEL_TOKEN" --scope "$VERCEL_TEAM_ID"; then
    dpl_sha="$(printf '%s' "$deployments_json" | python3 -c 'import json,sys; print("")' 2>/dev/null || echo '')"
    printf '%s\tPASS\tdpl=%s\n' "$name" "$dpl_id"
    return 0
  fi
  printf '%s\tFAIL\tpromote_error\n' "$name"
  return 1
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

  if [[ "$DRY_RUN" -eq 1 ]]; then
    exit 0
  fi

  log "Post-promote probes:"
  if bash "${REPO_ROOT}/scripts/ops/probe-frontends.sh"; then
    log "Frontend probes PASS"
  else
    overall=1
  fi

  exit "$overall"
}

main "$@"
