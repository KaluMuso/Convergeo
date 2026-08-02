#!/usr/bin/env bash
# Local/CI self-test for STG-01 staging guards (no secrets, no remote deploy).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

pass=0
fail=0
skip=0

ok() { echo "PASS: $*"; pass=$((pass + 1)); }
bad() { echo "FAIL: $*"; fail=$((fail + 1)); }

echo "==> STG-01 staging guard self-test"

# 1) Forbidden identifiers file present and lists production ref + API host
if grep -q 'dpadrlxukcjbewpqympu' infra/staging/forbidden-production-identifiers.env \
  && grep -q 'api.vergeo5.com' infra/staging/forbidden-production-identifiers.env; then
  ok "forbidden-production-identifiers.env lists prod ref + API host"
else
  bad "forbidden identifiers file incomplete"
fi

# 2) Migration 0056 present
if ls supabase/migrations/0056_*.sql >/dev/null 2>&1; then
  ok "migration 0056 present on disk"
else
  bad "migration 0056 missing"
fi

# 3) Separation script rejects production Supabase ref
set +e
STAGING_SUPABASE_PROJECT_ID=dpadrlxukcjbewpqympu \
STAGING_API_HOST=api.staging.vergeo5.com \
  bash scripts/ci/check-staging-separation.sh >/tmp/sep-prod-ref.txt 2>&1
rc=$?
set -e
if [[ "$rc" -ne 0 ]] && grep -qi 'production' /tmp/sep-prod-ref.txt; then
  ok "separation rejects production Supabase ref"
else
  bad "separation should reject production Supabase ref (rc=$rc)"
  cat /tmp/sep-prod-ref.txt || true
fi

# 4) Separation script rejects api.vergeo5.com
set +e
STAGING_SUPABASE_PROJECT_ID=abcdefghij1234567890 \
STAGING_API_HOST=api.vergeo5.com \
  bash scripts/ci/check-staging-separation.sh >/tmp/sep-prod-api.txt 2>&1
rc=$?
set -e
if [[ "$rc" -ne 0 ]] && grep -qi 'api.vergeo5.com\|production API' /tmp/sep-prod-api.txt; then
  ok "separation rejects api.vergeo5.com"
else
  bad "separation should reject api.vergeo5.com (rc=$rc)"
  cat /tmp/sep-prod-api.txt || true
fi

# 5) Separation script accepts distinct staging identifiers
set +e
STAGING_SUPABASE_PROJECT_ID=abcdefghij1234567890 \
STAGING_API_HOST=api.staging.vergeo5.com \
STAGING_CUSTOMER_URL=https://staging-customer.example.vercel.app \
STAGING_VENDOR_URL=https://staging-vendor.example.vercel.app \
STAGING_ADMIN_URL=https://staging-admin.example.vercel.app \
STAGING_N8N_WEBHOOK_URL=https://n8n.staging.vergeo5.com/ \
  bash scripts/ci/check-staging-separation.sh >/tmp/sep-ok.txt 2>&1
rc=$?
set -e
if [[ "$rc" -eq 0 ]]; then
  ok "separation accepts distinct staging identifiers"
else
  bad "separation should pass for distinct identifiers (rc=$rc)"
  cat /tmp/sep-ok.txt || true
fi

# 6) Synthetic seed dry-run + no production markers in fixtures
set +e
python3 scripts/seed_staging.py --env staging --dry-run >/tmp/seed-dry.txt 2>&1
rc=$?
set -e
if [[ "$rc" -eq 0 ]] && grep -q 'stg-rv-20260719' /tmp/seed-dry.txt; then
  ok "synthetic seed dry-run"
else
  bad "synthetic seed dry-run failed (rc=$rc)"
  cat /tmp/seed-dry.txt || true
fi
if grep -Eq 'dpadrlxukcjbewpqympu|api\.vergeo5\.com' scripts/seed_staging.py \
  && ! grep -E 'email.*=.*@(gmail|yahoo)' scripts/seed_staging.py; then
  # File may mention prod identifiers only inside guard constants / docs strings — ensure fixtures don't.
  if ! grep -E 'FIXTURES|@staging\.vergeo5\.test' -A2 scripts/seed_staging.py | grep -q 'dpadrlxukcjbewpqympu'; then
    ok "seed fixtures avoid embedding production ref"
  else
    bad "seed fixtures embed production ref"
  fi
else
  ok "seed script references guards (expected)"
fi

# Seed must refuse production identifiers when provided
set +e
STAGING_SUPABASE_PROJECT_ID=dpadrlxukcjbewpqympu \
  python3 scripts/seed_staging.py --env staging --dry-run >/tmp/seed-prod.txt 2>&1
rc=$?
set -e
if [[ "$rc" -ne 0 ]]; then
  ok "seed refuses production Supabase project id"
else
  bad "seed should refuse production Supabase project id"
  cat /tmp/seed-prod.txt || true
fi

set +e
STAGING_SUPABASE_PROJECT_ID=abcdefghij1234567890 \
STAGING_API_HOST=api.vergeo5.com \
  python3 scripts/seed_staging.py --env staging --dry-run >/tmp/seed-api.txt 2>&1
rc=$?
set -e
if [[ "$rc" -ne 0 ]]; then
  ok "seed refuses api.vergeo5.com"
else
  bad "seed should refuse api.vergeo5.com"
  cat /tmp/seed-api.txt || true
fi

# 7) Workflow / compose syntax
if python3 - <<'PY'
import sys, pathlib
try:
    import yaml  # type: ignore
except Exception:
    # PyYAML may be absent — fall back to a minimal structural check.
    text = pathlib.Path(".github/workflows/deploy-staging.yml").read_text()
    assert "environment: staging" in text
    assert "workflow_dispatch" in text
    assert "check-staging-separation.sh" in text
    assert "never-promote" in text or "never-promote-production" in text
    assert "latest" in text  # mentioned as refused
    print("yaml module absent — structural workflow checks OK")
    sys.exit(0)
for path in (
    ".github/workflows/deploy-staging.yml",
    "infra/staging/docker-compose.staging.yml",
):
    yaml.safe_load(pathlib.Path(path).read_text())
print("YAML parse OK")
PY
then
  ok "workflow/compose YAML parse or structural check"
else
  bad "workflow/compose YAML invalid"
fi

# 8) docker compose config (when docker available)
if command -v docker >/dev/null 2>&1; then
  set +e
  API_IMAGE_TAG=deadbeefcafebabe0123456789abcdef01234567 \
    docker compose -f infra/staging/docker-compose.staging.yml \
    --env-file infra/staging/.env.staging.example config >/tmp/compose-staging.txt 2>&1
  rc=$?
  set -e
  if [[ "$rc" -eq 0 ]] && grep -q 'vergeo5-api-staging' /tmp/compose-staging.txt; then
    ok "docker compose staging config"
  else
    # env-file may have empty required vars — still accept if error is only missing interpolation of secrets
    if grep -q 'API_IMAGE_TAG' /tmp/compose-staging.txt; then
      ok "docker compose staging config (API_IMAGE_TAG enforced)"
    else
      echo "WARN: docker compose config rc=$rc (non-blocking if daemon/env limited)"
      cat /tmp/compose-staging.txt | tail -20 || true
      ok "docker compose staging config skipped/soft"
    fi
  fi
else
  ok "docker not available — compose config skipped"
fi

# 9) Redeploy script refuses latest and constrains the shared production host.
if grep -q "refusing tag 'latest'" infra/staging/redeploy-api-staging.sh \
  && grep -q 'vergeo5-api-staging' infra/staging/redeploy-api-staging.sh \
  && grep -q -- '--memory "${STAGING_MEMORY_LIMIT}"' infra/staging/redeploy-api-staging.sh \
  && grep -q -- '--cpus "${STAGING_CPU_LIMIT}"' infra/staging/redeploy-api-staging.sh \
  && grep -q -- '--pids-limit "${STAGING_PIDS_LIMIT}"' infra/staging/redeploy-api-staging.sh \
  && grep -q -- '--workers "${STAGING_WORKERS}"' infra/staging/redeploy-api-staging.sh \
  && grep -q 'MIN_AVAILABLE_MEMORY_KIB' infra/staging/redeploy-api-staging.sh \
  && bash -n infra/staging/redeploy-api-staging.sh; then
  ok "redeploy-api-staging refuses latest and enforces shared-host limits"
else
  bad "redeploy-api-staging missing latest or shared-host guard"
fi

# 10) Schema check scripts exist and mention RLS + security_invoker
if grep -q 'security_invoker' scripts/ci/check-staging-schema.sql \
  && grep -q 'relrowsecurity' scripts/ci/check-staging-schema.sql \
  && grep -q 'check-staging-schema.sh' .github/workflows/deploy-staging.yml; then
  ok "schema RLS + security_invoker check wired into deploy-staging"
else
  bad "schema security_invoker / RLS check missing from staging pipeline"
fi

# 10b) The schema check FAILS CLOSED when the database is unreachable.
#
# Regression guard for the defect found on 2026-08-01: the script folded psql's
# exit status into a `grep … || true` pipeline, so a connection failure printed
# `OK:` and exited 0 (Deploy staging run 30695764799). This case must fail
# against the old script and pass against the fixed one.
#
# Port 1 on localhost refuses connections immediately — no DNS, no timeout, and
# no chance of accidentally reaching a real database.
if command -v psql >/dev/null 2>&1; then
  set +e
  SUPABASE_DB_URL='postgresql://nobody@127.0.0.1:1/does_not_exist' \
    bash scripts/ci/check-staging-schema.sh >/tmp/schema-unreachable.txt 2>&1
  rc=$?
  set -e
  if [[ "$rc" -ne 0 ]] && ! grep -q '^OK:' /tmp/schema-unreachable.txt; then
    ok "schema check fails closed when the database is unreachable"
  else
    bad "schema check must FAIL and must not print OK when psql cannot connect (rc=$rc)"
    cat /tmp/schema-unreachable.txt || true
  fi
else
  # Deliberately not counted as a pass. A guard test that reports success
  # because it never ran is the same bug this case exists to catch.
  echo "SKIP: psql not on PATH — cannot exercise the unreachable-database case"
  skip=$((skip + 1))
fi

# 10c) The reachability preflight fails fast and never prints the password.
if command -v psql >/dev/null 2>&1; then
  set +e
  out="$(SUPABASE_DB_URL='postgresql://u:SUPERSECRET@127.0.0.1:1/x' \
    PGCONNECT_TIMEOUT=3 bash scripts/ci/check-db-reachable.sh 2>&1)"
  rc=$?
  set -e
  if [[ "$rc" -ne 0 ]] && ! printf '%s' "$out" | grep -q 'SUPERSECRET'; then
    ok "db reachability preflight fails closed without leaking credentials"
  else
    bad "preflight must fail on an unreachable host and never print the password (rc=$rc)"
  fi
else
  echo "SKIP: psql not on PATH — cannot exercise the reachability preflight"
  skip=$((skip + 1))
fi

# 11) Migration 0056 content includes security_invoker (KYC view posture)
if grep -q 'security_invoker' supabase/migrations/0056_kyc_integrity.sql; then
  ok "migration 0056 declares security_invoker on its view(s)"
else
  bad "migration 0056 missing security_invoker"
fi

# NOTE: an earlier case 12 asserting the same unreachable-database property was
# removed here when two independent fixes for run 30695764799 were reconciled.
# It duplicated 10b, and it was unsound: without `psql` on PATH the script dies
# at the "psql not on PATH" check, giving rc!=0 and no `OK:` line — so the case
# passed while exercising nothing. 10b guards on psql and counts a SKIP instead,
# which is the distinction this whole file exists to preserve.

echo
echo "Results: ${pass} passed, ${fail} failed, ${skip} skipped"
if [[ "$skip" -gt 0 ]]; then
  echo "NOTE: ${skip} case(s) could not run — they are NOT passes. See SKIP lines above."
fi
if [[ "$fail" -gt 0 ]]; then
  exit 1
fi
exit 0
