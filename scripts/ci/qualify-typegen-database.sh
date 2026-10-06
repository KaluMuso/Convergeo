#!/usr/bin/env bash
set -euo pipefail

: "${SUPABASE_DB_URL:?SUPABASE_DB_URL is required}"
ROOT_DIR="${REPO_ROOT_OVERRIDE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
MIGRATIONS_DIR="${TYPEGEN_MIGRATIONS_DIR:-${ROOT_DIR}/supabase/migrations}"
PSQL_BIN="${PSQL_BIN:-psql}"
FIND_BIN="${FIND_BIN:-find}"
SORT_BIN="${SORT_BIN:-sort}"

# Reviewed defaults for supabase/postgres:17.6.1.143 at upstream source
# 7bb86cb00a2c552bd84e00ed6dd8db32a0da4c9a. Catalog state must still match.
expected_server="${EXPECTED_SERVER_VERSION_NUM:-170006}"
expected_vector="${EXPECTED_VECTOR_VERSION:-0.8.2}"
expected_graphql="${EXPECTED_PG_GRAPHQL_VERSION:-1.6.1}"
expected_pgcrypto="${EXPECTED_PGCRYPTO_VERSION:-1.3}"

[[ -d "${MIGRATIONS_DIR}" ]] || { echo "error: missing migrations directory ${MIGRATIONS_DIR}" >&2; exit 1; }

if ! catalog="$("${PSQL_BIN}" "${SUPABASE_DB_URL}" -X -v ON_ERROR_STOP=1 -At <<'SQL'
-- typegen_catalog_contract
select 'server_version_num|' || current_setting('server_version_num')
union all
select 'required_schema_count|' || count(*)::text
  from pg_namespace where nspname in ('public', 'graphql_public')
union all
select 'vector|' || coalesce((
  select e.extversion || '|' || n.nspname
    from pg_extension e join pg_namespace n on n.oid = e.extnamespace
   where e.extname = 'vector'
), '<missing>')
union all
select 'pg_graphql|' || coalesce((
  select e.extversion || '|' || n.nspname
    from pg_extension e join pg_namespace n on n.oid = e.extnamespace
   where e.extname = 'pg_graphql'
), '<missing>')
union all
select 'pgcrypto|' || coalesce((
  select e.extversion || '|' || n.nspname
    from pg_extension e join pg_namespace n on n.oid = e.extnamespace
   where e.extname = 'pgcrypto'
), '<missing>')
union all
select 'graphql_signature|' || coalesce(
  to_regprocedure('graphql_public.graphql(text,text,jsonb,jsonb)')::text,
  '<missing>'
)
union all
select 'graphql_shape|' || coalesce((
  select l.lanname || '|' || pg_get_function_result(p.oid)
    from pg_proc p join pg_language l on l.oid = p.prolang
   where p.oid = to_regprocedure('graphql_public.graphql(text,text,jsonb,jsonb)')
), '<missing>')
union all
select 'graphql_real_wrapper|' || coalesce((
  select (position('graphql.resolve' in pg_get_functiondef(p.oid)) > 0)::text
    from pg_proc p
   where p.oid = to_regprocedure('graphql_public.graphql(text,text,jsonb,jsonb)')
), 'false')
union all
select 'graphql_extension_member|' || count(*)::text
  from pg_proc p
  join pg_depend d on d.classid = 'pg_proc'::regclass
                  and d.objid = p.oid and d.deptype = 'e'
  join pg_extension e on e.oid = d.refobjid and e.extname = 'pg_graphql'
 where p.oid = to_regprocedure('graphql_public.graphql(text,text,jsonb,jsonb)')
union all
select 'pgcrypto_public_leaks|' || count(*)::text
  from pg_proc p join pg_namespace n on n.oid = p.pronamespace
 where n.nspname = 'public'
   and p.proname in ('dearmor', 'gen_random_uuid', 'gen_salt', 'pgp_armor_headers')
union all
select 'pgcrypto_misplaced_members|' || count(*)::text
  from pg_proc p
  join pg_namespace n on n.oid = p.pronamespace and n.nspname <> 'extensions'
  join pg_depend d on d.classid = 'pg_proc'::regclass
                  and d.objid = p.oid and d.deptype = 'e'
  join pg_extension e on e.oid = d.refobjid and e.extname = 'pgcrypto'
union all
select 'pgcrypto_extension_members|' || count(*)::text
  from pg_proc p
  join pg_namespace n on n.oid = p.pronamespace and n.nspname = 'extensions'
  join pg_depend d on d.classid = 'pg_proc'::regclass
                  and d.objid = p.oid and d.deptype = 'e'
  join pg_extension e on e.oid = d.refobjid and e.extname = 'pgcrypto';
SQL
)"; then
  echo "error: failed to collect typegen catalog evidence" >&2
  exit 1
fi

value() {
  local key="$1"
  local matches
  matches="$(awk -F '|' -v key="${key}" '$1 == key {sub(/^[^|]*\|/, ""); print}' <<<"${catalog}")"
  [[ "$(wc -l <<<"${matches}" | tr -d ' ')" == "1" && -n "${matches}" ]] || {
    echo "error: catalog evidence for ${key} is missing or ambiguous" >&2
    exit 1
  }
  printf '%s' "${matches}"
}

assert_eq() {
  local label="$1" actual="$2" expected="$3"
  [[ "${actual}" == "${expected}" ]] || {
    echo "error: expected ${label} ${expected}, got ${actual}" >&2
    exit 1
  }
}

assert_eq "PostgreSQL server_version_num" "$(value server_version_num)" "${expected_server}"
assert_eq "required schema count" "$(value required_schema_count)" "2"
assert_eq "vector extension" "$(value vector)" "${expected_vector}|extensions"
assert_eq "pg_graphql extension" "$(value pg_graphql)" "${expected_graphql}|graphql"
assert_eq "pgcrypto extension" "$(value pgcrypto)" "${expected_pgcrypto}|extensions"
[[ "$(value graphql_signature)" != "<missing>" ]] || { echo "error: graphql_public.graphql is missing" >&2; exit 1; }
assert_eq "graphql_public.graphql shape" "$(value graphql_shape)" "sql|jsonb"
assert_eq "real GraphQL wrapper definition" "$(value graphql_real_wrapper)" "true"
assert_eq "GraphQL wrapper extension membership" "$(value graphql_extension_member)" "1"
assert_eq "public pgcrypto function leakage" "$(value pgcrypto_public_leaks)" "0"
assert_eq "misplaced pgcrypto extension members" "$(value pgcrypto_misplaced_members)" "0"
pgcrypto_members="$(value pgcrypto_extension_members)"
[[ "${pgcrypto_members}" =~ ^[0-9]+$ && "${pgcrypto_members}" -gt 0 ]] || {
  echo "error: pgcrypto has no extension-owned functions in extensions schema" >&2
  exit 1
}

# Compare reviewed source expectations with the fresh replay. The SQL emits
# hashes plus bounded, sanitized direct ACL differences on mismatch. Even a
# failing run must not write configuration or fixture values to the artifact.
synthetic_contract="${ROOT_DIR}/scripts/ci/typegen-synthetic-contract.sql"
[[ -f "${synthetic_contract}" ]] || { echo "error: missing synthetic contract" >&2; exit 1; }
if ! synthetic_evidence="$("${PSQL_BIN}" "${SUPABASE_DB_URL}" -X -v ON_ERROR_STOP=1 -At <"${synthetic_contract}")"; then
  echo "error: failed to collect synthetic catalog hashes" >&2
  exit 1
fi
[[ "${#synthetic_evidence}" -le 16384 ]] || {
  echo "error: unbounded synthetic catalog evidence" >&2
  exit 1
}
expected_groups=(direct_role_acl function_owner_acl_config relation_owner_acl_rls schema_owner_acl service_read_grants source_fixture)
actual_groups=()
synthetic_hash_lines=()
synthetic_mismatches=()
direct_acl_diagnostics=()
direct_acl_truncated=false
while IFS= read -r line; do
  [[ "${#line}" -le 180 ]] || {
    echo "error: unbounded synthetic catalog evidence line" >&2
    exit 1
  }
  if [[ "${line}" == direct_acl_delta\|* ]]; then
    IFS='|' read -r marker direction schema_name relation_name grantee privilege grantor grantable extra <<<"${line}"
    if [[ "${line}" == 'direct_acl_delta|truncated' ]]; then
      [[ "${direct_acl_truncated}" == false && "${#direct_acl_diagnostics[@]}" -eq 64 ]] || {
        echo "error: malformed or unbounded direct ACL diagnostic" >&2
        exit 1
      }
      direct_acl_truncated=true
      direct_acl_diagnostics+=("${line}")
      continue
    fi
    case "${schema_name}.${relation_name}" in
      public.cart_merge_receipts|public.payment_collection_exceptions|\
      public.payment_collection_receipts|public.service_payment_obligations|\
      public.reconciliation_report_versions|public.vendor_stock_operations|\
      public.stock_claim_identities|reconciliation_private.report_streams) ;;
      *) echo "error: non-allowlisted direct ACL relation" >&2; exit 1 ;;
    esac
    [[ "${marker}" == direct_acl_delta && "${direction}" =~ ^(missing|unexpected)$ &&
       "${grantee}" =~ ^(PUBLIC|anon|authenticated|service_role)$ &&
       "${privilege}" =~ ^(SELECT|INSERT|UPDATE|DELETE|TRUNCATE|REFERENCES|TRIGGER|MAINTAIN)$ &&
       ( "${grantor}" == postgres || "${grantor}" == supabase_admin || "${grantor}" == '<other>' ) &&
       "${grantable}" =~ ^(true|false)$ && -z "${extra}" &&
       "${direct_acl_truncated}" == false && "${#direct_acl_diagnostics[@]}" -lt 64 ]] || {
      echo "error: malformed or unbounded direct ACL diagnostic" >&2
      exit 1
    }
    direct_acl_diagnostics+=("${line}")
    continue
  fi
  IFS='|' read -r group expected_hash actual_hash extra <<<"${line}"
  [[ -n "${group}" && -z "${extra}" && "${expected_hash}" =~ ^[0-9a-f]{64}$ && "${actual_hash}" =~ ^[0-9a-f]{64}$ ]] || {
    echo "error: malformed synthetic catalog hash evidence" >&2
    exit 1
  }
  actual_groups+=("${group}")
  synthetic_hash_lines+=("${line}")
  if [[ "${expected_hash}" != "${actual_hash}" ]]; then
    synthetic_mismatches+=("${line}")
  fi
done <<<"${synthetic_evidence}"
[[ "${actual_groups[*]}" == "${expected_groups[*]}" ]] || {
  echo "error: incomplete synthetic catalog hash groups" >&2
  exit 1
}
if [[ "${#synthetic_mismatches[@]}" -gt 0 ]]; then
  for line in "${synthetic_mismatches[@]}"; do
    IFS='|' read -r group expected_hash actual_hash <<<"${line}"
    echo "error: synthetic ${group} differs from reviewed source expectations (expected ${expected_hash}, actual ${actual_hash})" >&2
  done
  if [[ "${#direct_acl_diagnostics[@]}" -gt 0 ]]; then
    printf 'error: %s\n' "${direct_acl_diagnostics[@]}" >&2
  fi
  exit 1
fi
[[ "${#direct_acl_diagnostics[@]}" -eq 0 ]] || {
  echo "error: direct ACL deltas accompanied matching hashes" >&2
  exit 1
}

source_paths_tmp="$(mktemp)"
sorted_paths_tmp="$(mktemp)"
actual_migrations_tmp="$(mktemp)"
trap 'rm -f "${source_paths_tmp}" "${sorted_paths_tmp}" "${actual_migrations_tmp}"' EXIT

if ! "${FIND_BIN}" "${MIGRATIONS_DIR}" -maxdepth 1 -type f -name '*.sql' -print0 \
  >"${source_paths_tmp}"; then
  echo "error: failed to enumerate source migrations" >&2
  exit 1
fi
if ! "${SORT_BIN}" -z "${source_paths_tmp}" >"${sorted_paths_tmp}"; then
  echo "error: failed to sort source migrations" >&2
  exit 1
fi

expected_migrations=()
while IFS= read -r -d '' path; do
  filename="${path##*/}"
  if [[ ! "${filename}" =~ ^([0-9]+)_[A-Za-z0-9._-]+\.sql$ ]]; then
    echo "error: malformed source migration filename ${filename}" >&2
    exit 1
  fi
  expected_migrations+=("${BASH_REMATCH[1]}")
done <"${sorted_paths_tmp}"
[[ "${#expected_migrations[@]}" -gt 0 ]] || { echo "error: no source migrations found" >&2; exit 1; }
duplicates="$(printf '%s\n' "${expected_migrations[@]}" | uniq -d)"
[[ -z "${duplicates}" ]] || { echo "error: duplicate source migration identities: ${duplicates}" >&2; exit 1; }

if ! "${PSQL_BIN}" "${SUPABASE_DB_URL}" -X -v ON_ERROR_STOP=1 -At \
  >"${actual_migrations_tmp}" <<'SQL'
-- typegen_migration_versions
select version from supabase_migrations.schema_migrations order by version;
SQL
then
  echo "error: failed to collect applied migration identities" >&2
  exit 1
fi
if ! mapfile -t actual_migrations <"${actual_migrations_tmp}"; then
  echo "error: failed to load applied migration identities" >&2
  exit 1
fi
for version in "${actual_migrations[@]}"; do
  [[ "${version}" =~ ^[0-9]+$ ]] || {
    echo "error: malformed applied migration identity ${version}" >&2
    exit 1
  }
done

if ! diff -u \
  <(printf '%s\n' "${expected_migrations[@]}") \
  <(printf '%s\n' "${actual_migrations[@]}") >/dev/null; then
  echo "error: applied migration identities differ from source" >&2
  diff -u <(printf '%s\n' "${expected_migrations[@]}") \
    <(printf '%s\n' "${actual_migrations[@]}") >&2 || true
  exit 1
fi

printf '%s\n' "${catalog}"
printf '%s\n' "${synthetic_hash_lines[@]}"
printf 'migration_count|%s\n' "${#expected_migrations[@]}"
printf 'generation_schema_scope|public,graphql_public\n'
