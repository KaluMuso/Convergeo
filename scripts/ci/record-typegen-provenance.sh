#!/usr/bin/env bash
set -euo pipefail

: "${SUPABASE_DB_URL:?SUPABASE_DB_URL is required}"
: "${TYPEGEN_WORKDIR:?TYPEGEN_WORKDIR is required}"
: "${TYPEGEN_OUTPUT:?TYPEGEN_OUTPUT is required}"
: "${TYPEGEN_DB_CONTAINER_ID:?TYPEGEN_DB_CONTAINER_ID is required}"
: "${PROVENANCE_OUTPUT:?PROVENANCE_OUTPUT is required}"
: "${TYPEGEN_GRAPHQL_INITIALIZATION_EVIDENCE:?TYPEGEN_GRAPHQL_INITIALIZATION_EVIDENCE is required}"

ROOT_DIR="${REPO_ROOT_OVERRIDE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
MIGRATIONS_DIR="${TYPEGEN_MIGRATIONS_DIR:-${ROOT_DIR}/supabase/migrations}"
QUALIFIER="${TYPEGEN_QUALIFIER:-${ROOT_DIR}/scripts/ci/qualify-typegen-database.sh}"
SUPABASE_BIN="${SUPABASE_BIN:-supabase}"
DOCKER_BIN="${DOCKER_BIN:-docker}"
GIT_BIN="${GIT_BIN:-git}"
FIND_BIN="${FIND_BIN:-find}"
SORT_BIN="${SORT_BIN:-sort}"
SHA256SUM_BIN="${SHA256SUM_BIN:-sha256sum}"
expected_cli="${EXPECTED_SUPABASE_CLI_VERSION:-2.109.1}"
expected_postgres_image_version="${TYPEGEN_POSTGRES_IMAGE_VERSION:-17.6.1.143}"
expected_meta_version="${TYPEGEN_POSTGRES_META_VERSION:-v0.96.6}"
meta_image="${POSTGRES_META_IMAGE:-public.ecr.aws/supabase/postgres-meta:${expected_meta_version}}"
schema_scope="${SUPABASE_TYPEGEN_SCHEMAS:-public,graphql_public}"
expected_server="${EXPECTED_SERVER_VERSION_NUM:-170006}"
expected_vector="${EXPECTED_VECTOR_VERSION:-0.8.2}"
expected_graphql="${EXPECTED_PG_GRAPHQL_VERSION:-1.6.1}"
expected_pgcrypto="${EXPECTED_PGCRYPTO_VERSION:-1.3}"

[[ -s "${TYPEGEN_OUTPUT}" ]] || { echo "error: missing generated output ${TYPEGEN_OUTPUT}" >&2; exit 1; }
[[ -s "${TYPEGEN_GRAPHQL_INITIALIZATION_EVIDENCE}" ]] || {
  echo "error: missing GraphQL initialization evidence ${TYPEGEN_GRAPHQL_INITIALIZATION_EVIDENCE}" >&2
  exit 1
}
[[ -x "${QUALIFIER}" ]] || { echo "error: missing executable qualifier ${QUALIFIER}" >&2; exit 1; }
[[ "${schema_scope}" == "public,graphql_public" ]] || { echo "error: unexpected generation schema scope ${schema_scope}" >&2; exit 1; }

tmp="$(mktemp "${PROVENANCE_OUTPUT}.tmp.XXXXXX")"
shape_tmp="$(mktemp "${PROVENANCE_OUTPUT}.shape.XXXXXX")"
migration_manifest_tmp="$(mktemp "${PROVENANCE_OUTPUT}.migrations.XXXXXX")"
migration_paths_tmp="$(mktemp "${PROVENANCE_OUTPUT}.paths.XXXXXX")"
sorted_paths_tmp="$(mktemp "${PROVENANCE_OUTPUT}.sorted.XXXXXX")"
trap 'rm -f "${tmp}" "${shape_tmp}" "${migration_manifest_tmp}" "${migration_paths_tmp}" "${sorted_paths_tmp}"' EXIT

sha256_file() {
  local path="$1"
  local output digest
  if ! output="$("${SHA256SUM_BIN}" -- "${path}")"; then
    echo "error: failed to hash ${path}" >&2
    return 1
  fi
  digest="${output%% *}"
  if [[ ! "${digest}" =~ ^[0-9a-f]{64}$ || "${output}" != "${digest}  ${path}" ]]; then
    echo "error: malformed or mismatched SHA-256 evidence for ${path}" >&2
    return 1
  fi
  printf '%s\n' "${digest}"
}

SUPABASE_DB_URL="${SUPABASE_DB_URL}" \
TYPEGEN_MIGRATIONS_DIR="${MIGRATIONS_DIR}" \
PSQL_BIN="${PSQL_BIN:-psql}" \
  "${QUALIFIER}" >"${shape_tmp}"

cli_version="$(${SUPABASE_BIN} --version | awk 'NR == 1 {print $1}')"
[[ "${cli_version}" == "${expected_cli}" ]] || {
  echo "error: expected Supabase CLI ${expected_cli}, got ${cli_version}" >&2
  exit 1
}

selected_postgres_version="$(tr -d '[:space:]' <"${TYPEGEN_WORKDIR}/supabase/.temp/postgres-version")"
selected_meta_version="$(tr -d '[:space:]' <"${TYPEGEN_WORKDIR}/supabase/.temp/pgmeta-version")"
[[ "${selected_postgres_version}" == "${expected_postgres_image_version}" ]] || {
  echo "error: disposable workdir selected PostgreSQL image ${selected_postgres_version}" >&2
  exit 1
}
[[ "${selected_meta_version}" == "${expected_meta_version}" ]] || {
  echo "error: disposable workdir selected postgres-meta ${selected_meta_version}" >&2
  exit 1
}

container_identity="$(${DOCKER_BIN} inspect --format='{{.Config.Image}}|{{.Image}}' "${TYPEGEN_DB_CONTAINER_ID}")"
container_image_ref="${container_identity%%|*}"
container_image_id="${container_identity#*|}"
[[ "${container_image_ref}" == *"supabase/postgres:${expected_postgres_image_version}" ]] || {
  echo "error: typegen database used unexpected image ${container_image_ref}" >&2
  exit 1
}
# Consume Docker's documented JSON output, not Go-template join: newer
# clients may expose RepoDigests as []interface{} rather than []string.
# Validate both images before the final atomic provenance replacement.
image_identity() {
  local target="$1" expected_id="${2:-}" inspection identity
  if ! inspection="$("${DOCKER_BIN}" image inspect "${target}")"; then
    echo "error: failed to inspect typegen image ${target}" >&2
    return 1
  fi
  if ! identity="$(python3 -c '
import json
import re
import sys

def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate image metadata key")
        result[key] = value
    return result

try:
    records = json.load(sys.stdin, object_pairs_hook=unique_object)
    if not isinstance(records, list) or len(records) != 1 or not isinstance(records[0], dict):
        raise ValueError("expected exactly one image object")
    image = records[0]
    image_id = image.get("Id")
    if not isinstance(image_id, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise ValueError("missing or malformed image ID")
    if sys.argv[1] and image_id != sys.argv[1]:
        raise ValueError("image ID does not match the running database container")
    digests = image.get("RepoDigests")
    if not isinstance(digests, list) or not digests:
        raise ValueError("image repository digests are missing")
    if any(not isinstance(digest, str) or not re.fullmatch(
        r"[A-Za-z0-9._:/-]+@sha256:[0-9a-f]{64}", digest
    ) for digest in digests):
        raise ValueError("malformed image repository digest")
    print(image_id + "|" + ",".join(sorted(set(digests))))
except (ValueError, TypeError) as exc:
    raise SystemExit("error: invalid typegen image JSON: " + str(exc))
' "${expected_id}" <<<"${inspection}")"; then
    return 1
  fi
  printf '%s\n' "${identity}"
}

if ! postgres_identity="$(image_identity "${container_image_id}" "${container_image_id}")"; then
  exit 1
fi
postgres_repo_digests="${postgres_identity#*|}"

if ! meta_identity="$(image_identity "${meta_image}")"; then
  exit 1
fi
meta_image_id="${meta_identity%%|*}"
meta_repo_digests="${meta_identity#*|}"

source_sha="$(${GIT_BIN} -C "${ROOT_DIR}" rev-parse HEAD)"
source_tree="$(${GIT_BIN} -C "${ROOT_DIR}" rev-parse 'HEAD^{tree}')"
expected_source_sha="${QUALIFICATION_SHA:-${GITHUB_SHA:-}}"
if [[ -n "${expected_source_sha}" && "${source_sha}" != "${expected_source_sha}" ]]; then
  echo "error: checkout HEAD ${source_sha} differs from qualification source ${expected_source_sha}" >&2
  exit 1
fi

checked_in_major="$(python3 -c 'import sys,tomllib; print(tomllib.load(open(sys.argv[1], "rb"))["db"]["major_version"])' "${ROOT_DIR}/supabase/config.toml")"
disposable_major="$(python3 -c 'import sys,tomllib; print(tomllib.load(open(sys.argv[1], "rb"))["db"]["major_version"])' "${TYPEGEN_WORKDIR}/supabase/config.toml")"
[[ "${checked_in_major}" == "15" && "${disposable_major}" == "17" ]] || {
  echo "error: expected checked-in/disposable PostgreSQL majors 15/17, got ${checked_in_major}/${disposable_major}" >&2
  exit 1
}

if ! "${FIND_BIN}" "${MIGRATIONS_DIR}" -maxdepth 1 -type f -name '*.sql' -print0 \
  >"${migration_paths_tmp}"; then
  echo "error: failed to enumerate migration provenance inputs" >&2
  exit 1
fi
if ! "${SORT_BIN}" -z "${migration_paths_tmp}" >"${sorted_paths_tmp}"; then
  echo "error: failed to sort migration provenance inputs" >&2
  exit 1
fi

migration_names=()
migration_versions_array=()
migration_digests=()
while IFS= read -r -d '' path; do
  filename="${path##*/}"
  if [[ ! "${filename}" =~ ^([0-9]+)_[A-Za-z0-9._-]+\.sql$ ]]; then
    echo "error: malformed migration provenance input ${filename}" >&2
    exit 1
  fi
  version="${BASH_REMATCH[1]}"
  if ! digest="$(sha256_file "${path}")"; then
    exit 1
  fi
  migration_names+=("${filename}")
  migration_versions_array+=("${version}")
  migration_digests+=("${digest}")
  printf '%s  %s\n' "${digest}" "${filename}" >>"${migration_manifest_tmp}"
done <"${sorted_paths_tmp}"

migration_count="${#migration_names[@]}"
[[ "${migration_count}" -gt 0 ]] || { echo "error: migration provenance is empty" >&2; exit 1; }
if [[ -n "${EXPECTED_TYPEGEN_MIGRATION_COUNT:-}" && "${migration_count}" != "${EXPECTED_TYPEGEN_MIGRATION_COUNT}" ]]; then
  echo "error: unexpected qualified source migration count ${migration_count}" >&2
  exit 1
fi
if ! migration_manifest="$(sha256_file "${migration_manifest_tmp}")"; then
  exit 1
fi
migration_versions="$(IFS=,; printf '%s' "${migration_versions_array[*]}")"

if ! output_sha256="$(sha256_file "${TYPEGEN_OUTPUT}")"; then exit 1; fi
if ! checked_in_config_sha256="$(sha256_file "${ROOT_DIR}/supabase/config.toml")"; then exit 1; fi
if ! disposable_config_sha256="$(sha256_file "${TYPEGEN_WORKDIR}/supabase/config.toml")"; then exit 1; fi
if ! postgres_selection_sha256="$(sha256_file "${TYPEGEN_WORKDIR}/supabase/.temp/postgres-version")"; then exit 1; fi
if ! postgres_meta_selection_sha256="$(sha256_file "${TYPEGEN_WORKDIR}/supabase/.temp/pgmeta-version")"; then exit 1; fi
if ! graphql_initializer_sha256="$(sha256_file "${ROOT_DIR}/scripts/ci/initialize-typegen-graphql.sh")"; then exit 1; fi
if ! graphql_initialization_evidence_sha256="$(sha256_file "${TYPEGEN_GRAPHQL_INITIALIZATION_EVIDENCE}")"; then exit 1; fi
if ! adoption_helper_sha256="$(sha256_file "${ROOT_DIR}/scripts/ci/apply_service_adoption.py")"; then exit 1; fi
graphql_initialization_action="$(awk -F '|' '$1 == "graphql_initialization_action" {print $2}' \
  "${TYPEGEN_GRAPHQL_INITIALIZATION_EVIDENCE}")"
[[ "${graphql_initialization_action}" == "enabled" || "${graphql_initialization_action}" == "retained" ]] || {
  echo "error: invalid or missing GraphQL initialization action evidence" >&2
  exit 1
}
[[ "$(grep -c '^graphql_initialization_action|' "${TYPEGEN_GRAPHQL_INITIALIZATION_EVIDENCE}")" == "1" ]] || {
  echo "error: ambiguous GraphQL initialization action evidence" >&2
  exit 1
}

{
  printf 'source_sha=%s\n' "${source_sha}"
  printf 'github_event_sha=%s\n' "${GITHUB_SHA:-local}"
  printf 'adoption_helper_sha256=%s\n' "${adoption_helper_sha256}"
  printf 'typegen_migration_application=supabase_cli_fresh_no_seed\n'
  printf 'typegen_adoption_helper_invocation=not_invoked_by_cli\n'
  printf 'source_tree=%s\n' "${source_tree}"
  printf 'source_ref=%s\n' "${GITHUB_REF:-local}"
  printf 'migration_count=%s\n' "${migration_count}"
  printf 'migration_versions=%s\n' "${migration_versions}"
  printf 'migration_manifest_sha256=%s\n' "${migration_manifest}"
  for ((index = 0; index < migration_count; index++)); do
    printf 'migration_input.%s=%s\n' "${migration_names[index]}" "${migration_digests[index]}"
  done
  printf 'checked_in_postgres_major=%s\n' "${checked_in_major}"
  printf 'disposable_postgres_major=%s\n' "${disposable_major}"
  printf 'expected_profile.server_version_num=%s\n' "${expected_server}"
  printf 'expected_profile.vector=%s@extensions\n' "${expected_vector}"
  printf 'expected_profile.pg_graphql=%s@graphql\n' "${expected_graphql}"
  printf 'expected_profile.pgcrypto=%s@extensions\n' "${expected_pgcrypto}"
  printf 'checked_in_config_sha256=%s\n' "${checked_in_config_sha256}"
  printf 'disposable_config_sha256=%s\n' "${disposable_config_sha256}"
  printf 'postgres_selection_sha256=%s\n' "${postgres_selection_sha256}"
  printf 'postgres_meta_selection_sha256=%s\n' "${postgres_meta_selection_sha256}"
  printf 'graphql_initialization_action=%s\n' "${graphql_initialization_action}"
  printf 'graphql_initializer_sha256=%s\n' "${graphql_initializer_sha256}"
  printf 'graphql_initialization_evidence_sha256=%s\n' "${graphql_initialization_evidence_sha256}"
  printf 'postgres_image_ref=%s\n' "${container_image_ref}"
  printf 'postgres_image_id=%s\n' "${container_image_id}"
  printf 'postgres_image_repo_digests=%s\n' "${postgres_repo_digests}"
  printf 'supabase_cli_version=%s\n' "${cli_version}"
  printf 'generator_command=supabase --workdir <disposable> gen types typescript --local --schema %s\n' "${schema_scope}"
  printf 'postgres_meta_version=%s\n' "${selected_meta_version}"
  printf 'postgres_meta_image_ref=%s\n' "${meta_image}"
  printf 'postgres_meta_image_id=%s\n' "${meta_image_id}"
  printf 'postgres_meta_image_repo_digests=%s\n' "${meta_repo_digests}"
  printf 'generation_schema_scope=%s\n' "${schema_scope}"
  printf 'output_sha256=%s\n' "${output_sha256}"
  sed 's/^/database_shape./' "${shape_tmp}"
} >"${tmp}"

mv "${tmp}" "${PROVENANCE_OUTPUT}"
trap 'rm -f "${shape_tmp}" "${migration_manifest_tmp}" "${migration_paths_tmp}" "${sorted_paths_tmp}"' EXIT
printf 'wrote %s\n' "${PROVENANCE_OUTPUT}"
