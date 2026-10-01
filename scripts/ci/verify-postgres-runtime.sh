#!/usr/bin/env bash
set -euo pipefail

: "${SUPABASE_DB_URL:?SUPABASE_DB_URL is required}"
expected_server="${EXPECTED_SERVER_VERSION_NUM:-170006}"
expected_vector="${EXPECTED_VECTOR_VERSION:-0.8.0}"

actual_server="$(psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -Atc 'show server_version_num')"
actual_vector="$(psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -Atc "select extversion from pg_extension where extname = 'vector'")"
printf 'postgres server_version_num=%s\nvector extversion=%s\n' "$actual_server" "$actual_vector"
[[ "$actual_server" == "$expected_server" ]] || { echo "error: expected PostgreSQL ${expected_server}, got ${actual_server}" >&2; exit 1; }
[[ "$actual_vector" == "$expected_vector" ]] || { echo "error: expected vector ${expected_vector}, got ${actual_vector}" >&2; exit 1; }

roles="$(psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -AtF '|' -c \
  "select rolname, rolsuper, rolbypassrls from pg_roles where rolname in ('anon','authenticated','service_role','vergeo_rls_tester') order by 1")"
printf '%s\n' "$roles"
for role in anon authenticated vergeo_rls_tester; do
  grep -qx "${role}|f|f" <<<"$roles" || { echo "error: ${role} must be NOSUPERUSER NOBYPASSRLS" >&2; exit 1; }
done
grep -qx 'service_role|f|t' <<<"$roles" || { echo 'error: service_role must be NOSUPERUSER BYPASSRLS' >&2; exit 1; }

if [[ -n "${POSTGRES_CONTAINER_ID:-}" ]]; then
  docker inspect --format='postgres container={{.Id}} image={{.Image}} name={{.Name}}' "$POSTGRES_CONTAINER_ID"
fi
