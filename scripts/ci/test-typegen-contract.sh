#!/usr/bin/env bash
set -euo pipefail

# Capture the real executable before any command-double PATH is installed.
system_tee_bin="$(command -v tee)"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
QUALIFIER="${ROOT_DIR}/scripts/ci/qualify-typegen-database.sh"
PREPARE="${ROOT_DIR}/scripts/ci/prepare-typegen-workdir.sh"
INITIALIZER="${ROOT_DIR}/scripts/ci/initialize-typegen-graphql.sh"
PROVENANCE="${ROOT_DIR}/scripts/ci/record-typegen-provenance.sh"
# Command doubles below do not resolve PostgreSQL catalog types. Keep the
# required cast in the actual SQL block; real SQL is exercised by hosted init.
python3 - "${INITIALIZER}" <<'PY_CATALOG_CAST'
import re
import sys
from pathlib import Path

source = Path(sys.argv[1]).read_text()
catalog = source.split("-- typegen_graphql_catalog\n", 1)[1].split("\nSQL\n", 1)[0]
uses = re.findall(r"\be\.evtenabled\b(?:\s*::\s*text\b)?", catalog)
if not uses or any(not re.fullmatch(r"e\.evtenabled\s*::\s*text", use) for use in uses):
    raise SystemExit("error: catalog evtenabled must be explicitly cast to text")
PY_CATALOG_CAST

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

# GraphQL initialization must verify the disposable target before mutation,
# use the pinned available extension, and reject broken upstream machinery.
cat >"${tmp}/bin/init-docker" <<'EOF'
#!/bin/bash
set -euo pipefail
[[ "${1:-}" == "inspect" ]]
printf '%s\n' "${FAKE_INIT_CONTAINER_IDENTITY:-/supabase_db_vergeo5-typegen|public.ecr.aws/supabase/postgres:17.6.1.143|true|54322}"
EOF
cat >"${tmp}/bin/init-psql" <<'EOF'
#!/bin/bash
set -euo pipefail
sql="$(cat)"
state="$(cat "${FAKE_INIT_STATE_FILE}")"
if [[ "${sql}" == *typegen_graphql_catalog* ]]; then
  available="${FAKE_GRAPHQL_AVAILABLE:-1}"
  mechanism="${FAKE_GRAPHQL_MECHANISM:-correct}"
  printf '%s\n' \
    'server_version_num|170006' \
    'required_schema_count|2' \
    "available_pg_graphql_exact|${available}" \
    'available_pg_graphql_default|1.6.1' \
    'available_pg_graphql_versions|1.5.11,1.6.1' \
    'vector|0.8.2|extensions' \
    'pgcrypto|1.3|extensions'
  if [[ "${mechanism}" == "correct" ]]; then
    printf '%s\n' \
      "event_trigger|issue_pg_graphql_access|O|${FAKE_TRIGGER_RENDERING:-extensions.grant_pg_graphql_access()}" \
      "event_trigger_catalog_identity|${FAKE_TRIGGER_CATALOG_IDENTITY:-issue_pg_graphql_access|O|extensions|grant_pg_graphql_access|0}" \
      "event_trigger_function_matches|${FAKE_TRIGGER_FUNCTION_MATCHES:-true}" \
      'mechanism_creates_wrapper|true' \
      'mechanism_calls_resolver|true' \
      'mechanism_attaches_wrapper|true'
  else
    printf '%s\n' \
      'event_trigger|<missing>' \
      'event_trigger_catalog_identity|<missing>' \
      'event_trigger_function_matches|false' \
      'mechanism_creates_wrapper|false' \
      'mechanism_calls_resolver|false' \
      'mechanism_attaches_wrapper|false'
  fi
  case "${state}" in
    absent)
      printf '%s\n' \
        'pg_graphql|<missing>' \
        'wrapper_signature|graphql_public.graphql(text,text,jsonb,jsonb)' \
        'wrapper_owner|supabase_admin' \
        'wrapper_definition|CREATE FUNCTION graphql_public.graphql placeholder' \
        'wrapper_extension_member|0' \
        'resolver_identity|<missing>' \
        'resolver_identity_matches|false' \
        'resolver_owner|<missing>' \
        'resolver_extension_member|0'
      ;;
    wrong-version)
      extension='1.5.11|graphql'
      ;;
    wrong-schema)
      extension='1.6.1|public'
      ;;
    correct|broken-wrapper)
      extension='1.6.1|graphql'
      ;;
    *) exit 29 ;;
  esac
  if [[ "${state}" != "absent" ]]; then
    if [[ "${state}" == "broken-wrapper" ]]; then
      definition='CREATE FUNCTION graphql_public.graphql placeholder'
      membership=0
    else
      definition='CREATE FUNCTION graphql_public.graphql AS select graphql.resolve'
      membership=1
    fi
    printf '%s\n' \
      "pg_graphql|${extension}" \
      'wrapper_signature|graphql_public.graphql(text,text,jsonb,jsonb)' \
      'wrapper_owner|supabase_admin' \
      "wrapper_definition|${definition}" \
      "wrapper_extension_member|${membership}" \
      "resolver_identity|${FAKE_RESOLVER_RENDERING:-graphql.resolve(text,jsonb,text,jsonb)}" \
      "resolver_identity_matches|${FAKE_RESOLVER_IDENTITY_MATCHES:-true}" \
      'resolver_owner|supabase_admin' \
      "resolver_extension_member|${FAKE_RESOLVER_MEMBERSHIP:-1}"
  fi
elif [[ "${sql}" == *typegen_graphql_initialize* ]]; then
  printf '%s\n' mutation >>"${FAKE_INIT_MUTATION_LOG}"
  [[ "${FAKE_INIT_SQL_FAIL:-0}" != "1" ]] || exit 37
  printf '%s\n' correct >"${FAKE_INIT_STATE_FILE}"
elif [[ "${sql}" == *typegen_graphql_smoke* ]]; then
  if [[ "${FAKE_GRAPHQL_SMOKE_BAD:-0}" == "1" ]]; then
    printf '%s\n' '{"data": null, "errors": [{"message": "broken"}]}'
  else
    printf '%s\n' '{"data": {"__typename": "Query"}}'
  fi
else
  echo "unexpected initializer query" >&2
  exit 30
fi
EOF
chmod +x "${tmp}/bin/init-docker" "${tmp}/bin/init-psql"

init_state="${tmp}/init-state"
init_mutations="${tmp}/init-mutations"
run_initializer() {
  SUPABASE_DB_URL="${INIT_DB_URL:-postgresql://postgres:postgres@127.0.0.1:54322/postgres}" \
  TYPEGEN_WORKDIR="${tmp}/prepared" \
  TYPEGEN_DB_CONTAINER_ID=fixture-container \
  PSQL_BIN="${tmp}/bin/init-psql" \
  DOCKER_BIN="${tmp}/bin/init-docker" \
  FAKE_INIT_STATE_FILE="${init_state}" \
  FAKE_INIT_MUTATION_LOG="${init_mutations}" \
    "${INITIALIZER}"
}

printf '%s\n' absent >"${init_state}"
: >"${init_mutations}"
run_initializer >"${tmp}/graphql-init-enabled.txt"
grep -Fx 'graphql_initialization_action|enabled' "${tmp}/graphql-init-enabled.txt" >/dev/null
grep -Fx 'graphql_smoke|{"data": {"__typename": "Query"}}' "${tmp}/graphql-init-enabled.txt" >/dev/null
[[ "$(wc -l <"${init_mutations}" | tr -d ' ')" == "1" ]]
run_initializer >"${tmp}/graphql-init-retained.txt"
grep -Fx 'graphql_initialization_action|retained' "${tmp}/graphql-init-retained.txt" >/dev/null
[[ "$(wc -l <"${init_mutations}" | tr -d ' ')" == "1" ]]

expect_initializer_rejects_without_mutation() {
  local label="$1" state="$2"
  shift 2
  printf '%s\n' "${state}" >"${init_state}"
  : >"${init_mutations}"
  if env "$@" bash -c 'run_initializer >/dev/null 2>&1' 2>/dev/null; then
    echo "error: GraphQL initializer accepted ${label}" >&2
    exit 1
  fi
  [[ ! -s "${init_mutations}" ]] || {
    echo "error: GraphQL initializer mutated ${label}" >&2
    exit 1
  }
}
export -f run_initializer
export INITIALIZER init_state init_mutations tmp
expect_initializer_rejects_without_mutation 'unsupported extension version' absent FAKE_GRAPHQL_AVAILABLE=0
expect_initializer_rejects_without_mutation 'wrong preinstalled version' wrong-version
expect_initializer_rejects_without_mutation 'wrong preinstalled schema' wrong-schema
expect_initializer_rejects_without_mutation 'missing upstream wrapper mechanism' absent FAKE_GRAPHQL_MECHANISM=missing
expect_initializer_rejects_without_mutation 'broken existing wrapper' broken-wrapper

# Same catalog identities, different regprocedure rendering: display is not
# authority. These command doubles test the consumer, not PostgreSQL resolution.
for state in absent correct; do
  printf '%s\n' "${state}" >"${init_state}"
  : >"${init_mutations}"
  FAKE_TRIGGER_RENDERING='grant_pg_graphql_access()' \
  FAKE_RESOLVER_RENDERING='resolve(text,jsonb,text,jsonb)' \
    run_initializer >"${tmp}/graphql-init-unqualified-${state}.txt"
  expected_action=retained
  expected_mutations=0
  if [[ "${state}" == "absent" ]]; then
    expected_action=enabled
    expected_mutations=1
  fi
  grep -Fx "graphql_initialization_action|${expected_action}" \
    "${tmp}/graphql-init-unqualified-${state}.txt" >/dev/null
  [[ "$(wc -l <"${init_mutations}" | tr -d ' ')" == "${expected_mutations}" ]]
done

# A plausible diagnostic name cannot override namespace/OID/status evidence.
expect_initializer_rejects_without_mutation 'wrong trigger namespace' absent \
  'FAKE_TRIGGER_CATALOG_IDENTITY=issue_pg_graphql_access|O|public|grant_pg_graphql_access|0'
expect_initializer_rejects_without_mutation 'wrong trigger function' absent \
  'FAKE_TRIGGER_CATALOG_IDENTITY=issue_pg_graphql_access|O|extensions|different_handler|0'
expect_initializer_rejects_without_mutation 'wrong trigger arity' absent \
  'FAKE_TRIGGER_CATALOG_IDENTITY=issue_pg_graphql_access|O|extensions|grant_pg_graphql_access|1'
for enabled in D R A; do
  expect_initializer_rejects_without_mutation "wrong trigger mode ${enabled}" absent \
    "FAKE_TRIGGER_CATALOG_IDENTITY=issue_pg_graphql_access|${enabled}|extensions|grant_pg_graphql_access|0"
done
expect_initializer_rejects_without_mutation 'trigger OID mismatch' absent \
  FAKE_TRIGGER_FUNCTION_MATCHES=false
expect_initializer_rejects_without_mutation 'missing trigger catalog evidence' absent \
  'FAKE_TRIGGER_CATALOG_IDENTITY=<missing>'
expect_initializer_rejects_without_mutation 'wrong resolver identity' correct \
  FAKE_RESOLVER_IDENTITY_MATCHES=false
expect_initializer_rejects_without_mutation 'missing resolver extension membership' correct \
  FAKE_RESOLVER_MEMBERSHIP=0

printf '%s\n' absent >"${init_state}"
: >"${init_mutations}"
if FAKE_INIT_SQL_FAIL=1 run_initializer >/dev/null 2>&1; then
  echo "error: GraphQL initialization SQL failure was accepted" >&2
  exit 1
fi
[[ "$(wc -l <"${init_mutations}" | tr -d ' ')" == "1" ]]

printf '%s\n' absent >"${init_state}"
: >"${init_mutations}"
if INIT_DB_URL=postgresql://shared.example.invalid/postgres run_initializer >/dev/null 2>&1; then
  echo "error: non-disposable GraphQL initialization target was accepted" >&2
  exit 1
fi
[[ ! -s "${init_mutations}" ]]

printf '%s\n' absent >"${init_state}"
: >"${init_mutations}"
if FAKE_GRAPHQL_SMOKE_BAD=1 run_initializer >/dev/null 2>&1; then
  echo "error: broken real GraphQL resolution response was accepted" >&2
  exit 1
fi

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
cp "${tmp}/graphql-init-enabled.txt" "${tmp}/graphql-initialization.txt"

run_provenance() {
  local provenance_output="${PROVENANCE_OUTPUT_OVERRIDE:-${tmp}/provenance.txt}"
  SUPABASE_DB_URL=postgresql://fixture \
  TYPEGEN_WORKDIR="${tmp}/prepared" \
  TYPEGEN_OUTPUT="${tmp}/generated.ts" \
  TYPEGEN_DB_CONTAINER_ID=fixture-container \
  PROVENANCE_OUTPUT="${provenance_output}" \
  TYPEGEN_GRAPHQL_INITIALIZATION_EVIDENCE="${tmp}/graphql-initialization.txt" \
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
grep -Fx 'graphql_initialization_action=enabled' "${tmp}/provenance.txt" >/dev/null
grep -E '^graphql_initializer_sha256=[0-9a-f]{64}$' "${tmp}/provenance.txt" >/dev/null
grep -E '^graphql_initialization_evidence_sha256=[0-9a-f]{64}$' "${tmp}/provenance.txt" >/dev/null
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
  "${tmp}/prepared/supabase/.temp/pgmeta-version" \
  "${ROOT_DIR}/scripts/ci/initialize-typegen-graphql.sh" \
  "${tmp}/graphql-initialization.txt"; do
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
workflow_init_run="${tmp}/workflow-initialize-run.sh"
python3 - "${ROOT_DIR}/.github/workflows/ci.yml" "${workflow_run}" "${workflow_init_run}" <<'PY'
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

initialize = step("Initialize disposable typegen GraphQL")
if initialize.count("        shell: bash") != 1:
    raise SystemExit("error: GraphQL initialization step must use explicit shell: bash")
init_run_index = initialize.index("        run: |")
init_run_lines: list[str] = []
for line in initialize[init_run_index + 1 :]:
    if line and not line.startswith("          "):
        break
    init_run_lines.append(line[10:] if line else "")
init_run = "\n".join(init_run_lines).rstrip() + "\n"
required_init = (
    "bash scripts/ci/initialize-typegen-graphql.sh \\\n"
    "  | tee generated-types/graphql-initialization.txt"
)
if required_init not in init_run:
    raise SystemExit("error: GraphQL initialization run block no longer contains the reviewed pipeline")
Path(sys.argv[3]).write_text(init_run, encoding="utf-8")

downstream = [
    "Prefetch pinned postgres-meta generator",
    "Regenerate types",
    "Record generated type provenance",
    "Upload generated database types",
    "Fail on stale committed types",
]
positions = [db.index(f"      - name: {name}") for name in downstream]
if db.index("      - name: Initialize disposable typegen GraphQL") >= db.index(
    "      - name: Qualify migrations and Supabase database shape"
):
    raise SystemExit("error: GraphQL initialization must precede read-only qualification")
if db.index("      - name: Qualify migrations and Supabase database shape") >= min(positions):
    raise SystemExit("error: qualification must precede all evidence and drift steps")
for name in downstream:
    body = step(name)
    if any(line.startswith("        if:") for line in body):
        raise SystemExit(f"error: {name} must remain success-dependent")
if any(line.startswith("        if:") for line in initialize):
    raise SystemExit("error: GraphQL initialization must remain success-dependent")
provenance = step("Record generated type provenance")
if provenance.count(
    "          TYPEGEN_GRAPHQL_INITIALIZATION_EVIDENCE: generated-types/graphql-initialization.txt"
) != 1:
    raise SystemExit("error: provenance must consume GraphQL initialization evidence")
cleanup = step("Stop disposable Supabase database")
if cleanup.count("        if: always()") != 1:
    raise SystemExit("error: only disposable cleanup may run after qualification failure")
PY

mkdir -p "${tmp}/init-caller-bin" "${tmp}/init-caller-work"
cat >"${tmp}/init-caller-bin/bash" <<'EOF'
#!/bin/bash
set -u
[[ "$*" == "scripts/ci/initialize-typegen-graphql.sh" ]] || exit 24
printf '%s\n' 'before|pg_graphql|<missing>'
exit "${FAKE_INITIALIZER_STATUS:-0}"
EOF
cat >"${tmp}/init-caller-bin/tee" <<'EOF'
#!/bin/bash
set -u
"${REAL_TEE_BIN}" "$@"
tee_status=$?
[[ "${tee_status}" == "0" ]] || exit "${tee_status}"
exit "${FAKE_TEE_STATUS:-0}"
EOF
chmod +x "${tmp}/init-caller-bin/bash" "${tmp}/init-caller-bin/tee"
run_workflow_initializer() {
  local initializer_status="$1" tee_status="$2"
  (
    cd "${tmp}/init-caller-work"
    PATH="${tmp}/init-caller-bin:${PATH}" \
    REAL_TEE_BIN="${system_tee_bin}" \
    FAKE_INITIALIZER_STATUS="${initializer_status}" \
    FAKE_TEE_STATUS="${tee_status}" \
      /bin/bash --noprofile --norc -e -o pipefail "${workflow_init_run}"
  )
}

set +e
run_workflow_initializer 37 0 >/dev/null 2>&1
initializer_failure_status=$?
run_workflow_initializer 0 61 >/dev/null 2>&1
initializer_tee_status=$?
run_workflow_initializer 0 0 >/dev/null 2>&1
initializer_success_status=$?
set -e
[[ "${initializer_failure_status}" == "37" ]] || {
  echo "error: workflow masked GraphQL initializer status ${initializer_failure_status}" >&2
  exit 1
}
[[ "${initializer_tee_status}" == "61" ]] || {
  echo "error: workflow masked GraphQL initialization logging status ${initializer_tee_status}" >&2
  exit 1
}
[[ "${initializer_success_status}" == "0" ]] || {
  echo "error: workflow rejected normal GraphQL initialization/logging" >&2
  exit 1
}
graphql_generation_marker="${tmp}/graphql-generation-success"
if run_workflow_initializer 37 0 >/dev/null 2>&1; then
  printf '%s\n' success >"${graphql_generation_marker}"
fi
[[ ! -e "${graphql_generation_marker}" ]] || {
  echo "error: failed GraphQL initialization permitted generation" >&2
  exit 1
}

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
