#!/usr/bin/env bash
# Read-only sandbox schema-rehearsal evidence gate.
#
# This script never invokes `supabase db push`, never accepts a production
# project ref, and never prints a connection URL. It queries the remote ledger
# once and hands that evidence to the pure Python policy checker.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly PRODUCTION_PROJECT_REF="dpadrlxukcjbewpqympu"
readonly SANDBOX_PROJECT_REF="iyasmrmbcrvlfxpzescb"

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

: "${SCHEMA_TARGET_KIND:?SCHEMA_TARGET_KIND=sandbox is required}"
: "${SCHEMA_TARGET_PROJECT_REF:?SCHEMA_TARGET_PROJECT_REF is required}"
: "${SCHEMA_COHORT:?SCHEMA_COHORT is required}"
: "${SUPABASE_DB_URL:?SUPABASE_DB_URL is required for the read-only ledger query}"

[[ "${SCHEMA_TARGET_KIND}" == "sandbox" ]] || die "only SCHEMA_TARGET_KIND=sandbox is allowed"
[[ "${SCHEMA_TARGET_PROJECT_REF}" != "${PRODUCTION_PROJECT_REF}" ]] || die "production ref is forbidden"
[[ "${SCHEMA_TARGET_PROJECT_REF}" == "${SANDBOX_PROJECT_REF}" ]] || die "unknown sandbox project ref"
command -v psql >/dev/null 2>&1 || die "psql is required for the read-only ledger query"

ledger_file="$(mktemp)"
trap 'rm -f "${ledger_file}"' EXIT

if ! psql "${SUPABASE_DB_URL}" -v ON_ERROR_STOP=1 -tA -c \
  'select version from supabase_migrations.schema_migrations order by version' >"${ledger_file}"; then
  die "remote ledger query failed; no rehearsal evidence was produced"
fi

python3 "${REPO_ROOT}/scripts/ci/schema_convergence.py" \
  --migrations-dir "${REPO_ROOT}/supabase/migrations" \
  --cohorts-file "${REPO_ROOT}/scripts/ci/schema-convergence-cohorts.json" \
  --target-kind "${SCHEMA_TARGET_KIND}" \
  --target-project-ref "${SCHEMA_TARGET_PROJECT_REF}" \
  --ledger-file "${ledger_file}" \
  --ledger-source live-query \
  --cohort "${SCHEMA_COHORT}"
