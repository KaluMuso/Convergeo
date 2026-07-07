#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${ROOT}/packages/types/src/db.ts"

usage() {
  cat <<'EOF'
Usage: scripts/gen-types.sh [--local | --project-id <ref>]

  --local              Generate from the local Supabase stack (default).
  --project-id <ref>   Generate from a linked remote project (staging/prod).

Requires the Supabase CLI (`npx supabase` or `supabase` on PATH) and a running
local stack when using --local.
EOF
}

mode="local"
project_id=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --local)
      mode="local"
      shift
      ;;
    --project-id)
      mode="project"
      project_id="${2:?--project-id requires a value}"
      shift 2
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "gen-types.sh: unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if ! command -v supabase >/dev/null 2>&1; then
  if ! npx --yes supabase --version >/dev/null 2>&1; then
    echo "gen-types.sh: Supabase CLI is unavailable" >&2
    exit 1
  fi
  SUPABASE=(npx --yes supabase)
else
  SUPABASE=(supabase)
fi

mkdir -p "$(dirname "$OUT")"

if [[ "$mode" == "local" ]]; then
  if "${SUPABASE[@]}" status >/dev/null 2>&1; then
    "${SUPABASE[@]}" gen types typescript --local >"$OUT"
  elif [[ -n "${DATABASE_URL:-}" ]]; then
    "${SUPABASE[@]}" gen types typescript --db-url "$DATABASE_URL" -s public >"$OUT"
  else
    echo "gen-types.sh: local Supabase stack is not running (try: supabase start) and DATABASE_URL is unset" >&2
    exit 1
  fi
else
  if [[ -z "$project_id" ]]; then
    echo "gen-types.sh: --project-id is required for remote generation" >&2
    exit 1
  fi
  "${SUPABASE[@]}" gen types typescript --project-id "$project_id" >"$OUT"
fi

echo "gen-types.sh: wrote ${OUT}"
