#!/usr/bin/env bash
set -euo pipefail

: "${SUPABASE_DB_URL:?SUPABASE_DB_URL is required}"
: "${TYPEGEN_WORKDIR:?TYPEGEN_WORKDIR is required}"
: "${TYPEGEN_DB_CONTAINER_ID:?TYPEGEN_DB_CONTAINER_ID is required}"

ROOT_DIR="${REPO_ROOT_OVERRIDE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
PSQL_BIN="${PSQL_BIN:-psql}"
DOCKER_BIN="${DOCKER_BIN:-docker}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
expected_db_url="${EXPECTED_TYPEGEN_DB_URL:-postgresql://postgres:postgres@127.0.0.1:54322/postgres}"
expected_image_version="${TYPEGEN_POSTGRES_IMAGE_VERSION:-17.6.1.143}"
expected_server="${EXPECTED_SERVER_VERSION_NUM:-170006}"
expected_vector="${EXPECTED_VECTOR_VERSION:-0.8.2}"
expected_graphql="${EXPECTED_PG_GRAPHQL_VERSION:-1.6.1}"
expected_pgcrypto="${EXPECTED_PGCRYPTO_VERSION:-1.3}"
typegen_config="${TYPEGEN_WORKDIR}/supabase/config.toml"

# This helper mutates only the runner-owned database selected by
# prepare-typegen-workdir.sh. Reject arbitrary URLs before any SQL is sent.
[[ "${SUPABASE_DB_URL}" == "${expected_db_url}" ]] || {
  echo "error: refusing GraphQL initialization for a non-disposable database URL" >&2
  exit 1
}
[[ -f "${typegen_config}" ]] || { echo "error: missing disposable config ${typegen_config}" >&2; exit 1; }
"${PYTHON_BIN}" - "${typegen_config}" <<'PY'
import sys
import tomllib

with open(sys.argv[1], "rb") as handle:
    config = tomllib.load(handle)
if config.get("project_id") != "vergeo5-typegen":
    raise SystemExit("error: refusing GraphQL initialization outside project vergeo5-typegen")
if config.get("db", {}).get("major_version") != 17:
    raise SystemExit("error: disposable GraphQL initialization requires PostgreSQL major 17")
if config.get("db", {}).get("seed", {}).get("enabled") is not False:
    raise SystemExit("error: disposable GraphQL initialization requires demo seeding disabled")
if config.get("api", {}).get("schemas") != ["public", "graphql_public"]:
    raise SystemExit("error: disposable GraphQL initialization requires public,graphql_public")
PY

if ! container_identity="$(${DOCKER_BIN} inspect \
  --format='{{.Name}}|{{.Config.Image}}|{{.State.Running}}|{{with index .NetworkSettings.Ports "5432/tcp"}}{{(index . 0).HostPort}}{{end}}' \
  "${TYPEGEN_DB_CONTAINER_ID}")"; then
  echo "error: failed to inspect disposable typegen database container" >&2
  exit 1
fi
expected_container="/supabase_db_vergeo5-typegen"
expected_image_suffix="supabase/postgres:${expected_image_version}"
IFS='|' read -r container_name container_image container_running container_port <<<"${container_identity}"
[[ "${container_name}" == "${expected_container}" ]] || {
  echo "error: refusing GraphQL initialization for container ${container_name}" >&2
  exit 1
}
[[ "${container_image}" == *"${expected_image_suffix}" ]] || {
  echo "error: refusing GraphQL initialization for image ${container_image}" >&2
  exit 1
}
[[ "${container_running}" == "true" && "${container_port}" == "54322" ]] || {
  echo "error: disposable typegen container is not running on the expected port" >&2
  exit 1
}

collect_catalog() {
  "${PSQL_BIN}" "${SUPABASE_DB_URL}" -X -v ON_ERROR_STOP=1 \
    -v expected_graphql="${expected_graphql}" -At <<'SQL'
-- typegen_graphql_catalog
select 'server_version_num|' || current_setting('server_version_num')
union all select 'required_schema_count|' || count(*)::text
  from pg_namespace where nspname in ('public', 'graphql_public')
union all select 'available_pg_graphql_exact|' || count(*)::text
  from pg_available_extension_versions
 where name = 'pg_graphql' and version = :'expected_graphql'
union all select 'available_pg_graphql_default|' || coalesce(default_version, '<missing>')
  from pg_available_extensions where name = 'pg_graphql'
union all select 'available_pg_graphql_versions|' || coalesce(string_agg(version, ',' order by version), '<missing>')
  from pg_available_extension_versions where name = 'pg_graphql'
union all select 'vector|' || coalesce((
  select e.extversion || '|' || n.nspname from pg_extension e
  join pg_namespace n on n.oid = e.extnamespace where e.extname = 'vector'
), '<missing>')
union all select 'pg_graphql|' || coalesce((
  select e.extversion || '|' || n.nspname from pg_extension e
  join pg_namespace n on n.oid = e.extnamespace where e.extname = 'pg_graphql'
), '<missing>')
union all select 'pgcrypto|' || coalesce((
  select e.extversion || '|' || n.nspname from pg_extension e
  join pg_namespace n on n.oid = e.extnamespace where e.extname = 'pgcrypto'
), '<missing>')
union all select 'event_trigger|' || coalesce((
  select e.evtname || '|' || e.evtenabled::text || '|' || e.evtfoid::regprocedure::text
    from pg_event_trigger e where e.evtname = 'issue_pg_graphql_access'
), '<missing>')
union all select 'mechanism_creates_wrapper|' || coalesce((
  select (position('create or replace function graphql_public.graphql' in lower(pg_get_functiondef(p.oid))) > 0)::text
    from pg_proc p where p.oid = to_regprocedure('extensions.grant_pg_graphql_access()')
), 'false')
union all select 'mechanism_calls_resolver|' || coalesce((
  select (position('graphql.resolve' in lower(pg_get_functiondef(p.oid))) > 0)::text
    from pg_proc p where p.oid = to_regprocedure('extensions.grant_pg_graphql_access()')
), 'false')
union all select 'mechanism_attaches_wrapper|' || coalesce((
  select (position('alter extension pg_graphql add function graphql_public.graphql' in lower(pg_get_functiondef(p.oid))) > 0)::text
    from pg_proc p where p.oid = to_regprocedure('extensions.grant_pg_graphql_access()')
), 'false')
union all select 'wrapper_signature|' || coalesce(
  to_regprocedure('graphql_public.graphql(text,text,jsonb,jsonb)')::text, '<missing>')
union all select 'wrapper_owner|' || coalesce((
  select r.rolname from pg_proc p join pg_roles r on r.oid = p.proowner
   where p.oid = to_regprocedure('graphql_public.graphql(text,text,jsonb,jsonb)')
), '<missing>')
union all select 'wrapper_definition|' || coalesce((
  select regexp_replace(pg_get_functiondef(p.oid), E'[\\n\\r\\t ]+', ' ', 'g')
    from pg_proc p where p.oid = to_regprocedure('graphql_public.graphql(text,text,jsonb,jsonb)')
), '<missing>')
union all select 'wrapper_extension_member|' || count(*)::text
  from pg_proc p join pg_depend d on d.classid = 'pg_proc'::regclass
   and d.objid = p.oid and d.deptype = 'e'
  join pg_extension e on e.oid = d.refobjid and e.extname = 'pg_graphql'
 where p.oid = to_regprocedure('graphql_public.graphql(text,text,jsonb,jsonb)')
union all select 'resolver_identity|' || coalesce(
  to_regprocedure('graphql.resolve(text,jsonb,text,jsonb)')::text, '<missing>')
union all select 'resolver_owner|' || coalesce((
  select r.rolname from pg_proc p join pg_roles r on r.oid = p.proowner
   where p.oid = to_regprocedure('graphql.resolve(text,jsonb,text,jsonb)')
), '<missing>')
union all select 'resolver_extension_member|' || count(*)::text
  from pg_proc p join pg_depend d on d.classid = 'pg_proc'::regclass
   and d.objid = p.oid and d.deptype = 'e'
  join pg_extension e on e.oid = d.refobjid and e.extname = 'pg_graphql'
 where p.oid = to_regprocedure('graphql.resolve(text,jsonb,text,jsonb)');
SQL
}

catalog_value() {
  local catalog="$1" key="$2" matches
  matches="$(awk -F '|' -v key="${key}" '$1 == key {sub(/^[^|]*\|/, ""); print}' <<<"${catalog}")"
  [[ "$(wc -l <<<"${matches}" | tr -d ' ')" == "1" && -n "${matches}" ]] || {
    echo "error: GraphQL catalog evidence for ${key} is missing or ambiguous" >&2
    return 1
  }
  printf '%s' "${matches}"
}

assert_catalog() {
  local catalog="$1" key="$2" expected="$3" actual
  actual="$(catalog_value "${catalog}" "${key}")"
  [[ "${actual}" == "${expected}" ]] || {
    echo "error: expected ${key} ${expected}, got ${actual}" >&2
    return 1
  }
}

validate_common_profile() {
  local catalog="$1"
  assert_catalog "${catalog}" server_version_num "${expected_server}"
  assert_catalog "${catalog}" required_schema_count 2
  assert_catalog "${catalog}" available_pg_graphql_exact 1
  assert_catalog "${catalog}" vector "${expected_vector}|extensions"
  assert_catalog "${catalog}" pgcrypto "${expected_pgcrypto}|extensions"
  assert_catalog "${catalog}" event_trigger 'issue_pg_graphql_access|O|extensions.grant_pg_graphql_access()'
  assert_catalog "${catalog}" mechanism_creates_wrapper true
  assert_catalog "${catalog}" mechanism_calls_resolver true
  assert_catalog "${catalog}" mechanism_attaches_wrapper true
}

validate_installed_graphql() {
  local catalog="$1" definition
  assert_catalog "${catalog}" pg_graphql "${expected_graphql}|graphql"
  [[ "$(catalog_value "${catalog}" wrapper_signature)" != "<missing>" ]] || {
    echo "error: genuine graphql_public.graphql wrapper is missing" >&2
    return 1
  }
  definition="$(catalog_value "${catalog}" wrapper_definition)"
  [[ "${definition}" == *"graphql.resolve"* ]] || {
    echo "error: graphql_public.graphql is not the genuine resolver wrapper" >&2
    return 1
  }
  assert_catalog "${catalog}" wrapper_extension_member 1
  assert_catalog "${catalog}" resolver_identity 'graphql.resolve(text,jsonb,text,jsonb)'
  assert_catalog "${catalog}" resolver_extension_member 1
}

if ! before_catalog="$(collect_catalog)"; then
  echo "error: failed to collect pre-initialization GraphQL catalog evidence" >&2
  exit 1
fi
printf 'graphql_initialization_phase|before\n'
sed 's/^/before|/' <<<"${before_catalog}"
validate_common_profile "${before_catalog}"

installed="$(catalog_value "${before_catalog}" pg_graphql)"
if [[ "${installed}" == "<missing>" ]]; then
  if ! "${PSQL_BIN}" "${SUPABASE_DB_URL}" -X -v ON_ERROR_STOP=1 \
    -v expected_graphql="${expected_graphql}" -At <<'SQL'
-- typegen_graphql_initialize
create extension pg_graphql version :'expected_graphql';
SQL
  then
    echo "error: failed to enable pg_graphql ${expected_graphql} in the disposable typegen database" >&2
    exit 1
  fi
  action=enabled
else
  validate_installed_graphql "${before_catalog}"
  action=retained
fi

if ! after_catalog="$(collect_catalog)"; then
  echo "error: failed to collect post-initialization GraphQL catalog evidence" >&2
  exit 1
fi
validate_common_profile "${after_catalog}"
validate_installed_graphql "${after_catalog}"

if ! smoke="$(${PSQL_BIN} "${SUPABASE_DB_URL}" -X -v ON_ERROR_STOP=1 -At <<'SQL'
-- typegen_graphql_smoke
select graphql_public.graphql(query := '{ __typename }')::text;
SQL
)"; then
  echo "error: genuine GraphQL wrapper smoke query failed" >&2
  exit 1
fi
[[ "${smoke}" == '{"data": {"__typename": "Query"}}' ]] || {
  echo "error: genuine GraphQL wrapper returned an unexpected response: ${smoke}" >&2
  exit 1
}

printf 'graphql_initialization_action|%s\n' "${action}"
printf 'graphql_initialization_phase|after\n'
sed 's/^/after|/' <<<"${after_catalog}"
printf 'graphql_smoke|%s\n' "${smoke}"
