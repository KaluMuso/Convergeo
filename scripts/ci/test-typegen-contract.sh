#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
QUALIFIER="${ROOT_DIR}/scripts/ci/qualify-typegen-database.sh"
PREPARE="${ROOT_DIR}/scripts/ci/prepare-typegen-workdir.sh"
PROVENANCE="${ROOT_DIR}/scripts/ci/record-typegen-provenance.sh"
tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT

mkdir -p "${tmp}/bin" "${tmp}/migrations"
printf '%s\n' '-- one' >"${tmp}/migrations/0001_one.sql"
printf '%s\n' '-- two' >"${tmp}/migrations/0002_two.sql"
printf '%s\n' '0001' '0002' >"${tmp}/migration-versions"

cat >"${tmp}/catalog-good" <<'EOF'
server_version_num|170006
required_schema_count|2
vector|0.8.2|extensions
pg_graphql|1.6.1|graphql
pgcrypto|1.3|extensions
graphql_signature|graphql_public.graphql(text,text,jsonb,jsonb)
graphql_shape|sql|jsonb
graphql_real_wrapper|true
graphql_extension_member|1
pgcrypto_public_leaks|0
pgcrypto_misplaced_members|0
pgcrypto_extension_members|12
EOF

cat >"${tmp}/bin/psql" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
sql="$(cat)"
if [[ "${FAKE_PSQL_FAIL:-0}" == "1" ]]; then
  exit 23
elif [[ "${sql}" == *typegen_catalog_contract* ]]; then
  cat "${FAKE_CATALOG_OUTPUT}"
elif [[ "${sql}" == *typegen_migration_versions* ]]; then
  cat "${FAKE_MIGRATION_OUTPUT}"
  [[ "${FAKE_MIGRATION_EXIT_AFTER_OUTPUT:-0}" != "1" ]] || exit 23
else
  echo "unexpected query" >&2
  exit 24
fi
EOF
chmod +x "${tmp}/bin/psql"

run_qualifier() {
  FAKE_CATALOG_OUTPUT="${1}" \
  FAKE_MIGRATION_OUTPUT="${tmp}/migration-versions" \
  PSQL_BIN="${tmp}/bin/psql" \
  FIND_BIN="${QUALIFIER_FIND_BIN:-find}" \
  SORT_BIN="${QUALIFIER_SORT_BIN:-sort}" \
  SUPABASE_DB_URL=postgresql://fixture \
  TYPEGEN_MIGRATIONS_DIR="${tmp}/migrations" \
    "${QUALIFIER}" >/dev/null
}

expect_reject() {
  local label="$1" catalog="$2"
  if run_qualifier "${catalog}" >/dev/null 2>&1; then
    echo "error: negative control accepted ${label}" >&2
    exit 1
  fi
}

run_qualifier "${tmp}/catalog-good"

for fixture in missing-schema missing-function wrong-placement wrong-server-version \
  wrong-vector-version wrong-graphql-version wrong-pgcrypto-version missing-vector \
  missing-graphql missing-pgcrypto fake-wrapper missing-membership misplaced-pgcrypto; do
  cp "${tmp}/catalog-good" "${tmp}/catalog-${fixture}"
done
sed -i 's/required_schema_count|2/required_schema_count|1/' "${tmp}/catalog-missing-schema"
sed -i 's#graphql_signature|.*#graphql_signature|<missing>#' "${tmp}/catalog-missing-function"
sed -i 's/pg_graphql|1.6.1|graphql/pg_graphql|1.6.1|public/' "${tmp}/catalog-wrong-placement"
sed -i 's/server_version_num|170006/server_version_num|170005/' "${tmp}/catalog-wrong-server-version"
sed -i 's/vector|0.8.2|extensions/vector|0.8.0|extensions/' "${tmp}/catalog-wrong-vector-version"
sed -i 's/pg_graphql|1.6.1|graphql/pg_graphql|1.5.11|graphql/' "${tmp}/catalog-wrong-graphql-version"
sed -i 's/pgcrypto|1.3|extensions/pgcrypto|1.2|extensions/' "${tmp}/catalog-wrong-pgcrypto-version"
sed -i 's/vector|0.8.2|extensions/vector|<missing>/' "${tmp}/catalog-missing-vector"
sed -i 's/pg_graphql|1.6.1|graphql/pg_graphql|<missing>/' "${tmp}/catalog-missing-graphql"
sed -i 's/pgcrypto|1.3|extensions/pgcrypto|<missing>/' "${tmp}/catalog-missing-pgcrypto"
sed -i 's/graphql_real_wrapper|true/graphql_real_wrapper|false/' "${tmp}/catalog-fake-wrapper"
sed -i 's/graphql_extension_member|1/graphql_extension_member|0/' "${tmp}/catalog-missing-membership"
sed -i 's/pgcrypto_misplaced_members|0/pgcrypto_misplaced_members|1/' "${tmp}/catalog-misplaced-pgcrypto"

expect_reject "missing graphql_public schema" "${tmp}/catalog-missing-schema"
expect_reject "missing graphql_public.graphql" "${tmp}/catalog-missing-function"
expect_reject "wrong pg_graphql placement" "${tmp}/catalog-wrong-placement"
expect_reject "wrong PostgreSQL server version" "${tmp}/catalog-wrong-server-version"
expect_reject "obsolete vector version" "${tmp}/catalog-wrong-vector-version"
expect_reject "wrong pg_graphql version" "${tmp}/catalog-wrong-graphql-version"
expect_reject "wrong pgcrypto version" "${tmp}/catalog-wrong-pgcrypto-version"
expect_reject "missing vector extension" "${tmp}/catalog-missing-vector"
expect_reject "missing pg_graphql extension" "${tmp}/catalog-missing-graphql"
expect_reject "missing pgcrypto extension" "${tmp}/catalog-missing-pgcrypto"
expect_reject "dummy GraphQL wrapper" "${tmp}/catalog-fake-wrapper"
expect_reject "missing extension membership" "${tmp}/catalog-missing-membership"
expect_reject "misplaced pgcrypto extension member" "${tmp}/catalog-misplaced-pgcrypto"

printf '%s\n' '0001' >"${tmp}/migration-versions-bad"
if FAKE_CATALOG_OUTPUT="${tmp}/catalog-good" \
  FAKE_MIGRATION_OUTPUT="${tmp}/migration-versions-bad" \
  PSQL_BIN="${tmp}/bin/psql" SUPABASE_DB_URL=postgresql://fixture \
  TYPEGEN_MIGRATIONS_DIR="${tmp}/migrations" "${QUALIFIER}" >/dev/null 2>&1; then
  echo "error: missing migration identity was accepted" >&2
  exit 1
fi

if FAKE_PSQL_FAIL=1 FAKE_CATALOG_OUTPUT="${tmp}/catalog-good" \
  FAKE_MIGRATION_OUTPUT="${tmp}/migration-versions" \
  PSQL_BIN="${tmp}/bin/psql" SUPABASE_DB_URL=postgresql://fixture \
  TYPEGEN_MIGRATIONS_DIR="${tmp}/migrations" "${QUALIFIER}" >/dev/null 2>&1; then
  echo "error: failed catalog/provenance collection was accepted" >&2
  exit 1
fi

if FAKE_MIGRATION_EXIT_AFTER_OUTPUT=1 run_qualifier "${tmp}/catalog-good" >/dev/null 2>&1; then
  echo "error: applied migration query failure after valid rows was accepted" >&2
  exit 1
fi

cat >"${tmp}/bin/find-after-output" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
"${REAL_FIND_BIN}" "$@"
exit 23
EOF
cat >"${tmp}/bin/sort-after-output" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
"${REAL_SORT_BIN}" "$@"
exit 23
EOF
chmod +x "${tmp}/bin/find-after-output" "${tmp}/bin/sort-after-output"
if REAL_FIND_BIN="$(command -v find)" QUALIFIER_FIND_BIN="${tmp}/bin/find-after-output" \
  run_qualifier "${tmp}/catalog-good" >/dev/null 2>&1; then
  echo "error: failed source migration enumeration was accepted" >&2
  exit 1
fi
if REAL_SORT_BIN="$(command -v sort)" QUALIFIER_SORT_BIN="${tmp}/bin/sort-after-output" \
  run_qualifier "${tmp}/catalog-good" >/dev/null 2>&1; then
  echo "error: failed source migration sorting was accepted" >&2
  exit 1
fi

# The disposable override must be isolated from the checked-in config.
source_hash_before="$(sha256sum "${ROOT_DIR}/supabase/config.toml" | awk '{print $1}')"
mkdir "${tmp}/prepared"
"${PREPARE}" "${tmp}/prepared" >/dev/null
source_hash_after="$(sha256sum "${ROOT_DIR}/supabase/config.toml" | awk '{print $1}')"
[[ "${source_hash_before}" == "${source_hash_after}" ]]
python3 - "${tmp}/prepared/supabase/config.toml" <<'PY'
import sys, tomllib
with open(sys.argv[1], "rb") as handle:
    config = tomllib.load(handle)
assert config["db"]["major_version"] == 17
assert config["db"]["seed"]["enabled"] is False
assert config["api"]["schemas"] == ["public", "graphql_public"]
PY
[[ "$(cat "${tmp}/prepared/supabase/.temp/postgres-version")" == "17.6.1.143" ]]
[[ "$(cat "${tmp}/prepared/supabase/.temp/pgmeta-version")" == "v0.96.6" ]]

# Provenance must identify the selected runtime and generator, and it must be
# atomic when catalog collection or image identity resolution fails.
cat >"${tmp}/bin/supabase" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
[[ "${1:-}" == "--version" ]]
printf '%s\n' "${FAKE_SUPABASE_VERSION:-2.109.1}"
EOF
cat >"${tmp}/bin/docker" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "inspect" ]]; then
  printf '%s\n' 'public.ecr.aws/supabase/postgres:17.6.1.143|sha256:db-image'
elif [[ "${1:-}" == "image" && "${2:-}" == "inspect" ]]; then
  target="${*: -1}"
  if [[ "${target}" == "sha256:db-image" ]]; then
    printf '%s\n' "${FAKE_POSTGRES_REPO_DIGEST:-public.ecr.aws/supabase/postgres@sha256:db-digest}"
  else
    if [[ "${FAKE_MISSING_META_DIGEST:-0}" == "1" ]]; then
      printf '%s\n' 'sha256:meta-image|'
    else
      printf '%s\n' 'sha256:meta-image|public.ecr.aws/supabase/postgres-meta@sha256:meta-digest'
    fi
  fi
else
  echo "unexpected docker invocation: $*" >&2
  exit 25
fi
EOF
cat >"${tmp}/bin/provenance-qualifier" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
[[ "${FAKE_QUALIFIER_FAIL:-0}" != "1" ]] || exit 31
cat <<'SHAPE'
server_version_num=170006
extension.vector=0.8.2@extensions
extension.pg_graphql=1.6.1@graphql
extension.pgcrypto=1.3@extensions
graphql_public.graphql=real extension-owned wrapper
migration_count=2
SHAPE
EOF
cat >"${tmp}/bin/sha256sum" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
path="${*: -1}"
matches=0
if [[ -n "${FAKE_HASH_TARGET:-}" && "${path}" == "${FAKE_HASH_TARGET}" ]]; then
  matches=1
elif [[ "${FAKE_HASH_TARGET_KIND:-}" == "manifest" && "${path}" == *.migrations.* ]]; then
  matches=1
fi
if [[ "${matches}" == "1" ]]; then
  case "${FAKE_HASH_MODE:-}" in
    fail) exit 23 ;;
    valid-then-fail)
      printf '%064d  %s\n' 0 "${path}"
      exit 23
      ;;
    empty-success) exit 0 ;;
    malformed-success) printf 'not-a-sha256  %s\n' "${path}"; exit 0 ;;
    wrong-input-success) printf '%064d  %s.wrong\n' 0 "${path}"; exit 0 ;;
  esac
fi
exec "${REAL_SHA256SUM_BIN}" "$@"
EOF
chmod +x "${tmp}/bin/supabase" "${tmp}/bin/docker" "${tmp}/bin/provenance-qualifier" \
  "${tmp}/bin/sha256sum"
printf '%s\n' 'generated database types' >"${tmp}/generated.ts"

run_provenance() {
  local provenance_output="${PROVENANCE_OUTPUT_OVERRIDE:-${tmp}/provenance.txt}"
  SUPABASE_DB_URL=postgresql://fixture \
  TYPEGEN_WORKDIR="${tmp}/prepared" \
  TYPEGEN_OUTPUT="${tmp}/generated.ts" \
  TYPEGEN_DB_CONTAINER_ID=fixture-container \
  PROVENANCE_OUTPUT="${provenance_output}" \
  TYPEGEN_MIGRATIONS_DIR="${tmp}/migrations" \
  TYPEGEN_QUALIFIER="${tmp}/bin/provenance-qualifier" \
  SUPABASE_BIN="${tmp}/bin/supabase" \
  DOCKER_BIN="${tmp}/bin/docker" \
  FIND_BIN="${PROVENANCE_FIND_BIN:-find}" \
  SORT_BIN="${PROVENANCE_SORT_BIN:-sort}" \
  SHA256SUM_BIN="${tmp}/bin/sha256sum" \
  REAL_SHA256SUM_BIN="$(command -v sha256sum)" \
    "${PROVENANCE}" >/dev/null
}

run_provenance
grep -Fx 'supabase_cli_version=2.109.1' "${tmp}/provenance.txt" >/dev/null
grep -Fx 'migration_versions=0001,0002' "${tmp}/provenance.txt" >/dev/null
grep -Fx 'postgres_image_id=sha256:db-image' "${tmp}/provenance.txt" >/dev/null
grep -Fx 'postgres_meta_image_id=sha256:meta-image' "${tmp}/provenance.txt" >/dev/null
grep -Fx 'generation_schema_scope=public,graphql_public' "${tmp}/provenance.txt" >/dev/null
grep -Fx 'expected_profile.server_version_num=170006' "${tmp}/provenance.txt" >/dev/null
grep -Fx 'expected_profile.vector=0.8.2@extensions' "${tmp}/provenance.txt" >/dev/null
grep -Fx 'expected_profile.pg_graphql=1.6.1@graphql' "${tmp}/provenance.txt" >/dev/null
grep -Fx 'expected_profile.pgcrypto=1.3@extensions' "${tmp}/provenance.txt" >/dev/null
grep -Fx 'database_shape.graphql_public.graphql=real extension-owned wrapper' "${tmp}/provenance.txt" >/dev/null

printf '%s\n' 'preserve-on-failure' >"${tmp}/provenance.txt"
if FAKE_QUALIFIER_FAIL=1 run_provenance >/dev/null 2>&1; then
  echo "error: failed provenance catalog collection was accepted" >&2
  exit 1
fi
[[ "$(cat "${tmp}/provenance.txt")" == "preserve-on-failure" ]]

if FAKE_MISSING_META_DIGEST=1 run_provenance >/dev/null 2>&1; then
  echo "error: missing generator image digest was accepted" >&2
  exit 1
fi
if FAKE_SUPABASE_VERSION=2.110.0 run_provenance >/dev/null 2>&1; then
  echo "error: wrong generator CLI version was accepted" >&2
  exit 1
fi

expect_hash_reject_preserves_prior() {
  local label="$1" mode="$2" target="$3"
  printf '%s\n' 'preserve-on-hash-failure' >"${tmp}/provenance.txt"
  cp "${tmp}/provenance.txt" "${tmp}/provenance.before"
  if FAKE_HASH_MODE="${mode}" FAKE_HASH_TARGET="${target}" \
    run_provenance >/dev/null 2>&1; then
    echo "error: ${label} was accepted" >&2
    exit 1
  fi
  cmp "${tmp}/provenance.before" "${tmp}/provenance.txt"
}

expect_hash_reject_preserves_prior "migration checksum failure" fail \
  "${tmp}/migrations/0001_one.sql"
expect_hash_reject_preserves_prior "valid digest followed by checksum failure" valid-then-fail \
  "${tmp}/migrations/0001_one.sql"
expect_hash_reject_preserves_prior "empty successful checksum output" empty-success \
  "${tmp}/migrations/0001_one.sql"
expect_hash_reject_preserves_prior "malformed successful checksum output" malformed-success \
  "${tmp}/migrations/0001_one.sql"
expect_hash_reject_preserves_prior "checksum associated with wrong input" wrong-input-success \
  "${tmp}/migrations/0001_one.sql"

for required_hash in \
  "${tmp}/generated.ts" \
  "${ROOT_DIR}/supabase/config.toml" \
  "${tmp}/prepared/supabase/config.toml" \
  "${tmp}/prepared/supabase/.temp/postgres-version" \
  "${tmp}/prepared/supabase/.temp/pgmeta-version"; do
  expect_hash_reject_preserves_prior "required input hash failure: ${required_hash}" fail \
    "${required_hash}"
done

printf '%s\n' 'preserve-on-manifest-hash-failure' >"${tmp}/provenance.txt"
cp "${tmp}/provenance.txt" "${tmp}/provenance.before"
if FAKE_HASH_MODE=fail FAKE_HASH_TARGET_KIND=manifest run_provenance >/dev/null 2>&1; then
  echo "error: migration manifest checksum failure was accepted" >&2
  exit 1
fi
cmp "${tmp}/provenance.before" "${tmp}/provenance.txt"

printf '%s\n' 'preserve-on-enumeration-failure' >"${tmp}/provenance.txt"
cp "${tmp}/provenance.txt" "${tmp}/provenance.before"
if REAL_FIND_BIN="$(command -v find)" PROVENANCE_FIND_BIN="${tmp}/bin/find-after-output" \
  run_provenance >/dev/null 2>&1; then
  echo "error: failed provenance input enumeration was accepted" >&2
  exit 1
fi
cmp "${tmp}/provenance.before" "${tmp}/provenance.txt"

printf '%s\n' 'preserve-on-sort-failure' >"${tmp}/provenance.txt"
cp "${tmp}/provenance.txt" "${tmp}/provenance.before"
if REAL_SORT_BIN="$(command -v sort)" PROVENANCE_SORT_BIN="${tmp}/bin/sort-after-output" \
  run_provenance >/dev/null 2>&1; then
  echo "error: failed provenance input sorting was accepted" >&2
  exit 1
fi
cmp "${tmp}/provenance.before" "${tmp}/provenance.txt"

no_prior_output="${tmp}/no-prior-provenance.txt"
if PROVENANCE_OUTPUT_OVERRIDE="${no_prior_output}" FAKE_HASH_MODE=fail \
  FAKE_HASH_TARGET="${tmp}/migrations/0001_one.sql" run_provenance >/dev/null 2>&1; then
  echo "error: checksum failure without prior provenance was accepted" >&2
  exit 1
fi
[[ ! -e "${no_prior_output}" ]]

# Exercise the exact qualification run block extracted from ci.yml. GitHub's
# explicit `shell: bash` contract is bash --noprofile --norc -e -o pipefail.
workflow_run="${tmp}/workflow-qualify-run.sh"
python3 - "${ROOT_DIR}/.github/workflows/ci.yml" "${workflow_run}" <<'PY'
from pathlib import Path
import re
import sys

workflow = Path(sys.argv[1]).read_text(encoding="utf-8")
lines = workflow.splitlines()

start = lines.index("  db:")
end = next(
    (index for index in range(start + 1, len(lines)) if re.match(r"^  [a-z0-9-]+:$", lines[index])),
    len(lines),
)
db = lines[start:end]

expected_profile = {
    "EXPECTED_SERVER_VERSION_NUM": "170006",
    "EXPECTED_VECTOR_VERSION": "0.8.2",
    "EXPECTED_PG_GRAPHQL_VERSION": "1.6.1",
    "EXPECTED_PGCRYPTO_VERSION": "1.3",
}
for key, value in expected_profile.items():
    exact = f'      {key}: "{value}"'
    if db.count(exact) != 1:
        raise SystemExit(f"error: db job must declare exact typegen profile {key}={value}")

def step(name: str) -> list[str]:
    marker = f"      - name: {name}"
    step_start = db.index(marker)
    step_end = next(
        (index for index in range(step_start + 1, len(db)) if db[index].startswith("      - name: ")),
        len(db),
    )
    return db[step_start:step_end]

qualify = step("Qualify migrations and Supabase database shape")
if qualify.count("        shell: bash") != 1:
    raise SystemExit("error: qualification step must use explicit shell: bash")
run_index = qualify.index("        run: |")
run_lines: list[str] = []
for line in qualify[run_index + 1 :]:
    if line and not line.startswith("          "):
        break
    run_lines.append(line[10:] if line else "")
run = "\n".join(run_lines).rstrip() + "\n"
required = (
    "bash scripts/ci/qualify-typegen-database.sh \\\n"
    "  | tee generated-types/database-shape.txt"
)
if required not in run:
    raise SystemExit("error: qualification run block no longer contains the reviewed logging pipeline")
Path(sys.argv[2]).write_text(run, encoding="utf-8")

downstream = [
    "Prefetch pinned postgres-meta generator",
    "Regenerate types",
    "Record generated type provenance",
    "Upload generated database types",
    "Fail on stale committed types",
]
positions = [db.index(f"      - name: {name}") for name in downstream]
if db.index("      - name: Qualify migrations and Supabase database shape") >= min(positions):
    raise SystemExit("error: qualification must precede all evidence and drift steps")
for name in downstream:
    body = step(name)
    if any(line.startswith("        if:") for line in body):
        raise SystemExit(f"error: {name} must remain success-dependent")
cleanup = step("Stop disposable Supabase database")
if cleanup.count("        if: always()") != 1:
    raise SystemExit("error: only disposable cleanup may run after qualification failure")
PY

mkdir -p "${tmp}/caller-bin" "${tmp}/caller-work"
cat >"${tmp}/caller-bin/bash" <<'EOF'
#!/bin/bash
set -u
[[ "$*" == "scripts/ci/qualify-typegen-database.sh" ]] || exit 24
cat <<'CATALOG'
server_version_num|170006
required_schema_count|2
vector|0.8.2|extensions
pg_graphql|1.6.1|graphql
pgcrypto|1.3|extensions
CATALOG
exit "${FAKE_QUALIFIER_STATUS:-0}"
EOF
cat >"${tmp}/caller-bin/tee" <<'EOF'
#!/bin/bash
set -u
"${REAL_TEE_BIN}" "$@"
tee_status=$?
[[ "${tee_status}" == "0" ]] || exit "${tee_status}"
exit "${FAKE_TEE_STATUS:-0}"
EOF
chmod +x "${tmp}/caller-bin/bash" "${tmp}/caller-bin/tee"
system_tee_bin="$(command -v tee)"

run_workflow_caller() {
  local mode="$1" qualifier_status="$2" tee_status="$3"
  local -a flags=(--noprofile --norc -e)
  if [[ "${mode}" == "corrected" ]]; then
    flags+=(-o pipefail)
  fi
  (
    cd "${tmp}/caller-work"
    PATH="${tmp}/caller-bin:${PATH}" \
    REAL_TEE_BIN="${system_tee_bin}" \
    FAKE_QUALIFIER_STATUS="${qualifier_status}" \
    FAKE_TEE_STATUS="${tee_status}" \
      /bin/bash "${flags[@]}" "${workflow_run}"
  )
}

if ! run_workflow_caller old 23 0 >/dev/null 2>&1; then
  echo "error: old bash -e caller no longer demonstrates the masked qualifier failure" >&2
  exit 1
fi
grep -Fx 'vector|0.8.2|extensions' \
  "${tmp}/caller-work/generated-types/database-shape.txt" >/dev/null

set +e
run_workflow_caller corrected 23 0 >/dev/null 2>&1
corrected_qualifier_status=$?
run_workflow_caller corrected 0 61 >/dev/null 2>&1
corrected_tee_status=$?
run_workflow_caller corrected 0 0 >/dev/null 2>&1
corrected_success_status=$?
set -e
[[ "${corrected_qualifier_status}" == "23" ]] || {
  echo "error: corrected workflow caller masked qualifier status ${corrected_qualifier_status}" >&2
  exit 1
}
[[ "${corrected_tee_status}" == "61" ]] || {
  echo "error: corrected workflow caller masked logging status ${corrected_tee_status}" >&2
  exit 1
}
[[ "${corrected_success_status}" == "0" ]] || {
  echo "error: corrected workflow caller rejected normal qualification/logging" >&2
  exit 1
}

qualified_artifact_marker="${tmp}/qualified-artifact-success"
if run_workflow_caller corrected 23 0 >/dev/null 2>&1; then
  printf '%s\n' success >"${qualified_artifact_marker}"
fi
[[ ! -e "${qualified_artifact_marker}" ]] || {
  echo "error: failed qualification permitted a qualified-artifact success path" >&2
  exit 1
}

echo "typegen contract self-tests: PASS"
