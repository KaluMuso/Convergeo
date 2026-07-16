#!/usr/bin/env bash
# Fast Dockerless migration pre-flight: plain Postgres 16 + minimal Supabase shim,
# then replay supabase/migrations/00*.sql with ON_ERROR_STOP=1.
# Catches immutability/ordering/column bugs (the 0009 class) in seconds before the
# slower supabase db reset job. CI supplies a postgres service; override via PG* env.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MIGRATIONS_DIR="${REPO_ROOT}/supabase/migrations"

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-postgres}"
PGPASSWORD="${PGPASSWORD:-postgres}"
PGDATABASE="${PGDATABASE:-postgres}"
export PGPASSWORD

PSQL=(psql -v ON_ERROR_STOP=1 -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE")

echo "==> Waiting for Postgres at ${PGHOST}:${PGPORT}..."
for attempt in $(seq 1 30); do
  if "${PSQL[@]}" -c 'SELECT 1' >/dev/null 2>&1; then
    break
  fi
  if [[ "$attempt" -eq 30 ]]; then
    echo "ERROR: Postgres not ready after 30 attempts" >&2
    exit 1
  fi
  sleep 1
done

echo "==> Applying minimal Supabase shim (roles, auth, extensions)..."
"${PSQL[@]}" <<'SQL'
-- Base extensions (0001 re-applies with IF NOT EXISTS; vector needs pgvector-enabled image)
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    CREATE ROLE anon NOLOGIN NOINHERIT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    CREATE ROLE authenticated NOLOGIN NOINHERIT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    CREATE ROLE service_role NOLOGIN NOINHERIT BYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'supabase_admin') THEN
    CREATE ROLE supabase_admin LOGIN SUPERUSER;
  END IF;
END $$;

CREATE SCHEMA IF NOT EXISTS extensions;
CREATE SCHEMA IF NOT EXISTS auth;

GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
GRANT USAGE ON SCHEMA auth TO anon, authenticated, service_role;
GRANT USAGE ON SCHEMA extensions TO postgres, anon, authenticated, service_role;

CREATE TABLE IF NOT EXISTS auth.users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE OR REPLACE FUNCTION auth.uid()
RETURNS uuid
LANGUAGE sql
STABLE
AS $$
  SELECT NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid;
$$;

CREATE OR REPLACE FUNCTION auth.jwt()
RETURNS jsonb
LANGUAGE sql
STABLE
AS $$
  SELECT COALESCE(
    NULLIF(current_setting('request.jwt.claims', true), '')::jsonb,
    '{}'::jsonb
  );
$$;

GRANT SELECT ON auth.users TO anon, authenticated, service_role;
SQL

echo "==> Replaying migrations from ${MIGRATIONS_DIR}..."
shopt -s nullglob
mapfile -t migrations < <(find "${MIGRATIONS_DIR}" -maxdepth 1 -name '00*.sql' | sort)
if [[ ${#migrations[@]} -eq 0 ]]; then
  echo "ERROR: no migrations matching 00*.sql in ${MIGRATIONS_DIR}" >&2
  exit 1
fi

# Fail fast on duplicate numeric prefixes. Supabase keys schema_migrations on the
# leading digits of the filename, so two files sharing a prefix (e.g. two 0044_*)
# are a fatal `schema_migrations_pkey` collision when applied via the CLI. That
# recurs whenever independently-numbered PRs merge, and the raw pkey error surfaces
# deep in a later job with no hint at the culprit — catch it here in seconds.
dupes="$(basename -a "${migrations[@]}" | grep -oE '^[0-9]+' | sort | uniq -d)"
if [[ -n "${dupes}" ]]; then
  echo "ERROR: duplicate migration prefix(es) — each maps to one schema_migrations version:" >&2
  while IFS= read -r prefix; do
    echo "  ${prefix}: $(basename -a "${migrations[@]}" | grep -E "^${prefix}_" | paste -sd ', ' -)" >&2
  done <<< "${dupes}"
  echo "Renumber the newer migration(s) above the current max so every prefix is unique." >&2
  exit 1
fi

for migration in "${migrations[@]}"; do
  echo "  -> $(basename "${migration}")"
  "${PSQL[@]}" -f "${migration}"
done

echo "==> Migration replay OK (${#migrations[@]} files: $(basename -a "${migrations[@]}" | paste -sd ', ' -))"
