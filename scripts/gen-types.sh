#!/usr/bin/env bash
# Regenerate packages/types/src/db.ts from the local Supabase stack (or remote project).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_FILE="${ROOT_DIR}/packages/types/src/db.ts"

if command -v supabase >/dev/null 2>&1; then
  SUPABASE_CMD=(supabase)
elif command -v npx >/dev/null 2>&1; then
  SUPABASE_CMD=(npx supabase)
else
  echo "error: supabase CLI not found on PATH (install: https://supabase.com/docs/guides/cli)" >&2
  exit 1
fi

cd "${ROOT_DIR}"

TMP_FILE="$(mktemp)"
trap 'rm -f "${TMP_FILE}"' EXIT

# Disposable replay database: SUPABASE_DB_URL=postgresql://... scripts/gen-types.sh
# Remote/staging: SUPABASE_PROJECT_ID=<ref> scripts/gen-types.sh
#   → supabase gen types typescript --project-id "$SUPABASE_PROJECT_ID"
if [[ -n "${SUPABASE_DB_URL:-}" ]]; then
  "${SUPABASE_CMD[@]}" gen types typescript --db-url "${SUPABASE_DB_URL}" >"${TMP_FILE}"
elif [[ -n "${SUPABASE_PROJECT_ID:-}" ]]; then
  "${SUPABASE_CMD[@]}" gen types typescript --project-id "${SUPABASE_PROJECT_ID}" >"${TMP_FILE}"
else
  if ! "${SUPABASE_CMD[@]}" status >/dev/null 2>&1; then
    echo "error: local Supabase stack is not running (start with: supabase start)" >&2
    exit 1
  fi
  "${SUPABASE_CMD[@]}" gen types typescript --local >"${TMP_FILE}"
fi

# Never replace a reviewed destination with an empty/truncated/error document.
if [[ ! -s "${TMP_FILE}" ]] || ! grep -Eq '^export type (Json|Database)' "${TMP_FILE}" || \
   ! grep -q 'Database' "${TMP_FILE}"; then
  echo "error: generated TypeScript output is empty or malformed; preserving ${OUT_FILE}" >&2
  exit 1
fi

mv "${TMP_FILE}" "${OUT_FILE}"
trap - EXIT

echo "wrote ${OUT_FILE}"
