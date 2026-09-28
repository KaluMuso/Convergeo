#!/usr/bin/env bash
# Only the ephemeral postgres service of the dedicated GitHub Actions job.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"
evidence="$repo_root/critical-real-stack-evidence"
mkdir -p "$evidence/junit" "$evidence/logs"
manifest="$repo_root/scripts/ci/critical-real-stack-nodes.txt"
cp "$manifest" "$evidence/expected-nodes.txt"
git rev-parse HEAD HEAD^{tree} > "$evidence/source.txt"
python3 scripts/ci/critical-real-stack-report.py results \
  --manifest "$manifest" --dir "$evidence/junit" --exits "$evidence/exits.tsv" \
  --output "$evidence/results.json" >/dev/null || true

if [[ "${GITHUB_ACTIONS:-}" != true || "${GITHUB_REPOSITORY:-}" != KaluMuso/Convergeo || -z "${RUNNER_TEMP:-}" ]]; then
  echo 'ERROR: this database-creating packet only runs in the repository GitHub Actions service job' >&2
  exit 1
fi
if ! command -v psql >/dev/null || ! command -v docker >/dev/null || ! command -v curl >/dev/null; then
  echo 'ERROR: disposable postgres client, Docker and curl are required' >&2
  exit 1
fi

pg_image='pgvector/pgvector:0.8.0-pg17-trixie'
rest_image='public.ecr.aws/supabase/postgrest:v14.14'
mapfile -t containers < <(docker ps --filter "ancestor=$pg_image" --format '{{.ID}}')
if [[ "${#containers[@]}" != 1 ]] || ! docker port "${containers[0]}" 5432/tcp | grep -Eq '(^|:)54322$'; then
  echo 'ERROR: expected one disposable pgvector service bound to host port 54322' >&2
  exit 1
fi
export PGHOST=127.0.0.1 PGPORT=54322 PGUSER=postgres PGPASSWORD=postgres
psql_admin=(psql -X -v ON_ERROR_STOP=1 -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d postgres)
[[ "$("${psql_admin[@]}" -Atqc 'SELECT current_database()')" == postgres ]]

created_dbs=()
rest_container=''
cleanup() {
  local status=$? db
  trap - EXIT
  python3 scripts/ci/critical-real-stack-report.py results \
    --manifest "$manifest" --dir "$evidence/junit" --exits "$evidence/exits.tsv" \
    --output "$evidence/results.json" || status=1
  if [[ -n "$rest_container" ]]; then
    docker rm -f "$rest_container" >/dev/null || status=1
  fi
  for db in "${created_dbs[@]}"; do
    "${psql_admin[@]}" -q -c "DROP DATABASE IF EXISTS \"$db\" WITH (FORCE)" >/dev/null || status=1
  done
  exit "$status"
}
trap cleanup EXIT

{
  echo "github_run=${GITHUB_RUN_ID:-unknown} attempt=${GITHUB_RUN_ATTEMPT:-unknown} checkout=$(git rev-parse HEAD)"
  echo "postgres_container=${containers[0]} image=$(docker inspect --format '{{.Image}}' "${containers[0]}")"
  "${psql_admin[@]}" -Atqc 'SELECT version()'
  "${psql_admin[@]}" -Atqc "SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname IN ('anon','authenticated','service_role','vergeo_rls_tester') ORDER BY rolname"
} > "$evidence/runtime.txt"

# This is the ONLY reset/replay target; tests receive independent clones.
template=ci_critical_template
"${psql_admin[@]}" -q -c "CREATE DATABASE \"$template\" TEMPLATE template0"
created_dbs+=("$template")
PGDATABASE="$template" bash scripts/ci/migration-replay.sh > "$evidence/logs/migrations.log" 2>&1
table_count="$(psql -X -v ON_ERROR_STOP=1 -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$template" -Atqc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'")"
if (( table_count < 45 )); then
  echo "ERROR: migrated fixture schema is incomplete ($table_count public tables)" >&2
  exit 1
fi
"${psql_admin[@]}" -q -c "CREATE ROLE ci_critical_authenticator LOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS PASSWORD 'ci-disposable-authenticator-only'"
"${psql_admin[@]}" -q -c 'GRANT anon, authenticated, service_role TO ci_critical_authenticator'
{
  "${psql_admin[@]}" -Atqc "SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname IN ('anon','authenticated','service_role','vergeo_rls_tester','ci_critical_authenticator') ORDER BY rolname"
  "${psql_admin[@]}" -Atqc "SELECT member.rolname, granted.rolname FROM pg_auth_members am JOIN pg_roles member ON member.oid=am.member JOIN pg_roles granted ON granted.oid=am.roleid WHERE member.rolname='ci_critical_authenticator' ORDER BY granted.rolname"
} >> "$evidence/runtime.txt"

# The checked-in local drill requires Auth's standard columns on the bare
# postgres replay shim. This touches only the disposable template database.
psql -X -v ON_ERROR_STOP=1 -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$template" <<'SQL' > "$evidence/logs/fixture-bootstrap.log" 2>&1
ALTER TABLE auth.users
  ADD COLUMN IF NOT EXISTS instance_id uuid,
  ADD COLUMN IF NOT EXISTS aud text,
  ADD COLUMN IF NOT EXISTS role text,
  ADD COLUMN IF NOT EXISTS encrypted_password text,
  ADD COLUMN IF NOT EXISTS email_confirmed_at timestamptz,
  ADD COLUMN IF NOT EXISTS raw_app_meta_data jsonb,
  ADD COLUMN IF NOT EXISTS raw_user_meta_data jsonb,
  ADD COLUMN IF NOT EXISTS updated_at timestamptz;
SQL

groups=(cart checkout kyc prepaid collection tickets concurrency creation)
for db in "${groups[@]}"; do
  name="ci_critical_$db"
  "${psql_admin[@]}" -q -c "CREATE DATABASE \"$name\" TEMPLATE \"$template\""
  created_dbs+=("$name")
done
"${psql_admin[@]}" -Atqc "SELECT datname FROM pg_database WHERE datname LIKE 'ci_critical_%' ORDER BY datname" >> "$evidence/runtime.txt"
psql -X -v ON_ERROR_STOP=1 -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d ci_critical_collection \
  -f services/api/tests/lane_d/local_postgrest_auth_shim.sql > "$evidence/logs/collection-auth-shim.log" 2>&1

export ENV=development
export LANE_D_JWT_SECRET='ci-only-local-jwt-signing-material-do-not-use-outside-disposable-job'
export LANE_D_WEBHOOK_TOKEN='ci-only-local-webhook-signing-material'
export LENCO_API_TOKEN="$LANE_D_WEBHOOK_TOKEN"
export SUPABASE_URL=https://example.supabase.co
export LANE_D_POSTGREST_URL=http://127.0.0.1:3006
export SUPABASE_REST_URL="$LANE_D_POSTGREST_URL"

sign_jwt() {
  python3 - "$1" <<'PY'
import base64
import hashlib
import hmac
import json
import os
import sys
import time

def encode(data):
    return base64.urlsafe_b64encode(json.dumps(data, separators=(',', ':')).encode()).rstrip(b'=').decode()

role = sys.argv[1]
message = encode({'alg': 'HS256', 'typ': 'JWT'}) + '.' + encode({'role': role, 'exp': int(time.time()) + 3600})
signature = hmac.new(os.environ['LANE_D_JWT_SECRET'].encode(), message.encode(), hashlib.sha256).digest()
print(message + '.' + base64.urlsafe_b64encode(signature).rstrip(b'=').decode())
PY
}
SUPABASE_SERVICE_ROLE_KEY="$(sign_jwt service_role)"
SUPABASE_ANON_KEY="$(sign_jwt anon)"
export SUPABASE_SERVICE_ROLE_KEY SUPABASE_ANON_KEY

docker pull "$rest_image" > "$evidence/logs/postgrest-pull.log" 2>&1
echo "postgrest_image=$(docker image inspect --format '{{.Id}}' "$rest_image")" >> "$evidence/runtime.txt"

selectors=(
  'tests/rls/test_cart_merge_atomic.py::test_service_role_works_through_real_postgrest_and_anon_is_denied'
  'tests/test_checkout.py::TestMixedDeliveryPickup::test_mixed_groups_compute_separate_fees'
  'tests/test_checkout.py::TestReservationClaimOnSessionInit::test_session_init_claims_reservations'
  'tests/test_checkout.py::TestExpiryReturnsCartNotice::test_expired_session_status_returns_notice'
  'tests/test_checkout.py::TestExpiryReturnsCartNotice::test_fulfilment_on_expired_session_returns_410'
  'tests/test_checkout.py::TestExpiryReturnsCartNotice::test_outside_zone_rejects_delivery'
  tests/test_kyc_approve_atomic.py
  tests/test_prepaid_settlement.py
  tests/lane_d/test_collection_identity_postgrest.py
  tests/test_ticket_inventory.py
  tests/test_order_create_concurrency.py
  tests/test_order_creation.py
)
raw="$RUNNER_TEMP/critical-real-stack"
mkdir -p "$raw"
(
  cd services/api
  uv run pytest --collect-only -q --disable-warnings "${selectors[@]}"
) > "$raw/collection.log" 2>&1
python3 scripts/ci/critical-real-stack-report.py collection \
  --manifest "$manifest" --input "$raw/collection.log" --output "$evidence/collected-nodes.txt"

start_postgrest() {
  local database="$1" status attempt
  rest_container="$(docker run -d --rm --network host \
    -e PGRST_DB_URI="postgresql://ci_critical_authenticator:ci-disposable-authenticator-only@127.0.0.1:54322/$database" \
    -e PGRST_DB_SCHEMAS=public -e PGRST_DB_ANON_ROLE=anon \
    -e PGRST_JWT_SECRET="$LANE_D_JWT_SECRET" -e PGRST_SERVER_HOST=127.0.0.1 \
    -e PGRST_SERVER_PORT=3006 \
    "$rest_image")"
  for attempt in {1..30}; do
    status="$(curl --silent --output /dev/null --write-out '%{http_code}' "$LANE_D_POSTGREST_URL/" || true)"
    if [[ "$status" == 200 ]]; then
      status="$(curl --silent --output /dev/null --write-out '%{http_code}' \
        -H 'Authorization: Bearer invalid.invalid.invalid' "$LANE_D_POSTGREST_URL/" || true)"
      if [[ "$status" != 401 ]]; then
        echo "ERROR: PostgREST did not reject invalid JWT (status $status)" >&2
        exit 1
      fi
      return
    fi
    sleep 1
  done
  echo "ERROR: PostgREST did not serve OpenAPI from $database (status $status)" >&2
  docker logs --tail 50 "$rest_container" >&2
  exit 1
}

stop_postgrest() {
  docker rm -f "$rest_container" >/dev/null
  rest_container=''
}

sanitize() {
  python3 - "$1" "$2" <<'PY'
import os
import pathlib
import sys

data = pathlib.Path(sys.argv[1]).read_text(encoding='utf-8', errors='replace')
for name in ('SUPABASE_SERVICE_ROLE_KEY', 'SUPABASE_ANON_KEY', 'LANE_D_JWT_SECRET', 'LANE_D_WEBHOOK_TOKEN'):
    value = os.environ.get(name, '')
    if value:
        data = data.replace(value, '[REDACTED]')
pathlib.Path(sys.argv[2]).write_text(data, encoding='utf-8')
PY
}

run_group() {
  local group="$1" exit_code
  shift
  export SUPABASE_DB_URL="postgresql://postgres:postgres@127.0.0.1:54322/ci_critical_$group"
  unset ORDER_TEST_DB_URL
  if [[ "$group" == concurrency || "$group" == creation ]]; then
    export ORDER_TEST_DB_URL="$SUPABASE_DB_URL"
  fi
  {
    printf 'database=ci_critical_%s command=uv run pytest -q -o xfail_strict=true -rA --junitxml=<group.xml>' "$group"
    printf ' %q' "$@"
    printf '\n'
  } >> "$evidence/commands.txt"
  if (
    cd services/api
    uv run pytest -q -o xfail_strict=true -rA --junitxml="$raw/$group.xml" "$@"
  ) > "$raw/$group.log" 2>&1; then
    exit_code=0
  else
    exit_code=$?
  fi
  printf '%s\t%s\n' "$group" "$exit_code" >> "$evidence/exits.tsv"
  sanitize "$raw/$group.log" "$evidence/logs/$group.log"
  if [[ -f "$raw/$group.xml" ]]; then
    sanitize "$raw/$group.xml" "$evidence/junit/$group.xml"
  fi
  echo "critical $group pytest exit=$exit_code"
}

start_postgrest ci_critical_cart
run_group cart "${selectors[0]}"
stop_postgrest
run_group checkout "${selectors[@]:1:5}"
run_group kyc tests/test_kyc_approve_atomic.py
run_group prepaid tests/test_prepaid_settlement.py
start_postgrest ci_critical_collection
run_group collection tests/lane_d/test_collection_identity_postgrest.py
stop_postgrest
run_group tickets tests/test_ticket_inventory.py
run_group concurrency tests/test_order_create_concurrency.py
run_group creation tests/test_order_creation.py

python3 scripts/ci/critical-real-stack-report.py results \
  --manifest "$manifest" --dir "$evidence/junit" \
  --exits "$evidence/exits.tsv" --output "$evidence/results.json"
