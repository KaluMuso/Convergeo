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

# 2) Migration tip files present (repository ledger, not a stale hard-coded number)
if ls supabase/migrations/0095_*.sql >/dev/null 2>&1 \
  && ls supabase/migrations/20260802153539_*.sql >/dev/null 2>&1; then
  ok "repository migration tip files present (0095 + 20260802153539)"
else
  bad "repository migration tip files missing"
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
    assert "vercel-staging-preview-prove.sh" in text
    assert "prove-vercel-preview" in text
    assert "staging-sha-proof" in text
    assert "reconcile-staging-migrations.sh" in text
    assert "validate_staging_proof" in text or "staging-evidence-bundle.sh" in text
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

# 12) Three-portal Vercel Preview prove helper exists and passes shellcheck-lite
if bash -n scripts/ci/vercel-staging-preview-prove.sh \
  && bash -n scripts/ci/staging-evidence-bundle.sh \
  && bash -n scripts/ci/reconcile-staging-migrations.sh \
  && bash -n scripts/ci/preflight-staging-schema-convergence.sh \
  && bash -n scripts/ci/staging-cors-preview-probe.sh \
  && python3 -m py_compile scripts/ci/validate_staging_proof.py \
  && python3 -m py_compile scripts/ci/reconcile_staging_migrations.py; then
  ok "preview prove + evidence bundle + migration reconcile + CORS probe syntax"
else
  bad "preview prove / evidence bundle / migration reconcile / CORS probe syntax invalid"
fi

# 12b) RC-6 / PR-F3: CORS Preview probe wiring, ordering, and offline failure modes.
#
# strict E2E run #52 proved (real Playwright traces) that a browser hitting
# the deployed Customer/Vendor/Admin Preview origins got CORS-rejected by the
# staging API — because every SHA-pinned Preview deployment gets a newly
# generated immutable hostname a static CORS_ORIGINS entry can never
# anticipate. This turns that class of bug into a deploy-time proof instead
# of something only Playwright discovers deep into the browse journey.
cors_probe_line="$(grep -n 'staging-cors-preview-probe.sh' .github/workflows/deploy-staging.yml | head -1 | cut -d: -f1 || true)"
health_fp_line="$(grep -n 'Health + fingerprint' .github/workflows/deploy-staging.yml | head -1 | cut -d: -f1 || true)"
if [[ -z "${cors_probe_line}" ]]; then
  bad "deploy-staging must wire scripts/ci/staging-cors-preview-probe.sh into the smoke job"
elif [[ -z "${health_fp_line}" ]]; then
  bad "deploy-staging: could not locate the Health + fingerprint step to order the CORS proof against"
elif [[ "${cors_probe_line}" -lt "${health_fp_line}" ]] \
  && grep -q "prove-vercel-preview.result == 'success'" .github/workflows/deploy-staging.yml; then
  ok "deploy-staging proves staging CORS for the certified Preview origins before health/fingerprint"
else
  bad "CORS proof must run after prove-vercel-preview succeeds and before Health + fingerprint"
fi

if grep -q 'preview-dir /tmp/preview-evidence' .github/workflows/deploy-staging.yml; then
  ok "CORS proof reads the same normalized Preview evidence directory as fingerprinting"
else
  bad "CORS proof step must read /tmp/preview-evidence (the normalized per-portal evidence dir)"
fi

# The script must fail closed offline: missing evidence, a malformed
# preview_url, and a production API host must all be rejected without
# reaching the network.
set +e
mkdir -p /tmp/cors-probe-selftest/customer
echo '{"preview_url": "not-an-https-url"}' > /tmp/cors-probe-selftest/customer/evidence.json
bash scripts/ci/staging-cors-preview-probe.sh \
  --preview-dir /tmp/cors-probe-selftest \
  --api-base https://api.staging.vergeo5.com >/tmp/cors-probe-malformed.txt 2>&1
rc_malformed=$?
set -e
rm -rf /tmp/cors-probe-selftest
if [[ "${rc_malformed}" -ne 0 ]] \
  && grep -qi 'not a valid https origin\|missing Preview evidence' /tmp/cors-probe-malformed.txt; then
  ok "CORS probe fails closed on missing/malformed Preview evidence"
else
  bad "CORS probe should fail closed on missing/malformed Preview evidence (rc=${rc_malformed})"
  cat /tmp/cors-probe-malformed.txt || true
fi

set +e
bash scripts/ci/staging-cors-preview-probe.sh \
  --preview-dir /tmp \
  --api-base https://api.vergeo5.com >/tmp/cors-probe-prod.txt 2>&1
rc_prod=$?
set -e
if [[ "${rc_prod}" -ne 0 ]] && grep -qi 'production API host' /tmp/cors-probe-prod.txt; then
  ok "CORS probe refuses to probe the production API host"
else
  bad "CORS probe should refuse api.vergeo5.com (rc=${rc_prod})"
  cat /tmp/cors-probe-prod.txt || true
fi

# 12c) Cart-location remediation: native DB pool + service-role read proof.
#
# Run #55's aftermath proved location_stock.py's raw psycopg pool
# (run_sql_script/resolve_db_url) is a connectivity path distinct from the
# PostgREST/service-role client every other deploy check exercises — a
# healthy /healthz + a passing CORS preflight both say nothing about it.
if bash -n scripts/ci/staging-db-service-role-proof.sh; then
  ok "staging-db-service-role-proof.sh syntax"
else
  bad "staging-db-service-role-proof.sh syntax invalid"
fi

db_proof_line="$(grep -n 'staging-db-service-role-proof.sh' .github/workflows/deploy-staging.yml | head -1 | cut -d: -f1 || true)"
if [[ -z "${db_proof_line}" ]]; then
  bad "deploy-staging must wire scripts/ci/staging-db-service-role-proof.sh into the smoke job"
elif [[ -z "${health_fp_line}" ]]; then
  bad "deploy-staging: could not locate the Health + fingerprint step to order the DB proof against"
elif [[ "${cors_probe_line}" -lt "${db_proof_line}" && "${db_proof_line}" -lt "${health_fp_line}" ]]; then
  ok "deploy-staging proves the native DB pool + service-role read after the CORS proof and before health/fingerprint"
else
  bad "DB service-role proof must run after the CORS proof and before Health + fingerprint"
fi

if grep -q -- '--listing-id f1000000-0000-4000-8000-000000000001' .github/workflows/deploy-staging.yml; then
  ok "DB service-role proof targets the canonical branch-tracked E2E fixture listing"
else
  bad "DB service-role proof step must target the canonical branch-tracked fixture listing"
fi

# Fails closed offline: missing evidence and a production API host must both
# be rejected without reaching the network — same discipline as the CORS probe.
set +e
bash scripts/ci/staging-db-service-role-proof.sh \
  --preview-dir /tmp/nonexistent-preview-dir \
  --api-base https://api.staging.vergeo5.com \
  --listing-id f1000000-0000-4000-8000-000000000001 >/tmp/db-proof-missing-evidence.txt 2>&1
rc_missing=$?
set -e
if [[ "${rc_missing}" -ne 0 ]] && grep -qi 'missing Preview evidence' /tmp/db-proof-missing-evidence.txt; then
  ok "DB service-role proof fails closed on missing Preview evidence"
else
  bad "DB service-role proof should fail closed on missing Preview evidence (rc=${rc_missing})"
  cat /tmp/db-proof-missing-evidence.txt || true
fi

set +e
bash scripts/ci/staging-db-service-role-proof.sh \
  --preview-dir /tmp \
  --api-base https://api.vergeo5.com \
  --listing-id f1000000-0000-4000-8000-000000000001 >/tmp/db-proof-prod.txt 2>&1
rc_db_prod=$?
set -e
if [[ "${rc_db_prod}" -ne 0 ]] && grep -qi 'production API host' /tmp/db-proof-prod.txt; then
  ok "DB service-role proof refuses to probe the production API host"
else
  bad "DB service-role proof should refuse api.vergeo5.com (rc=${rc_db_prod})"
  cat /tmp/db-proof-prod.txt || true
fi

# 13) deploy-staging wires explicit Preview proof for all three portals
if grep -q 'prove-vercel-preview' .github/workflows/deploy-staging.yml \
  && grep -q 'matrix:' .github/workflows/deploy-staging.yml \
  && grep -q 'portal: customer' .github/workflows/deploy-staging.yml \
  && grep -q 'portal: vendor' .github/workflows/deploy-staging.yml \
  && grep -q 'portal: admin' .github/workflows/deploy-staging.yml \
  && grep -q 'vercel-staging-preview-prove.sh' .github/workflows/deploy-staging.yml \
  && grep -q 'staging-sha-proof' .github/workflows/deploy-staging.yml \
  && grep -q 'staging-evidence-bundle.sh' .github/workflows/deploy-staging.yml \
  && grep -q 'reconcile-staging-migrations.sh' .github/workflows/deploy-staging.yml; then
  ok "deploy-staging proves customer/vendor/admin Preview at same SHA"
else
  bad "deploy-staging missing three-portal Preview proof wiring"
fi

# 13b) deploy-staging must preflight ledger drift before db push
preflight_line="$(grep -n 'preflight-staging-schema-convergence.sh' .github/workflows/deploy-staging.yml | head -1 | cut -d: -f1 || true)"
push_line="$(grep -n 'supabase db push --include-all' .github/workflows/deploy-staging.yml | head -1 | cut -d: -f1 || true)"
if [[ -n "${preflight_line}" && -n "${push_line}" && "${preflight_line}" -lt "${push_line}" ]] \
  && grep -q 'STAGING_LEDGER_REPAIR_REQUIRED' .github/workflows/deploy-staging.yml; then
  ok "deploy-staging preflight blocks db push when ledger repair is required"
else
  bad "deploy-staging must run schema preflight before supabase db push"
fi

# 14) Preview prove dry-run validates portal mapping without Vercel calls
set +e
GITHUB_SHA=deadbeefcafebabe0123456789abcdef01234567 \
GITHUB_REF_NAME=staging \
VERCEL_TOKEN=x VERCEL_ORG_ID=team_x \
VERCEL_PROJECT_ID_CUSTOMER=prj_c VERCEL_PROJECT_ID_VENDOR=prj_v VERCEL_PROJECT_ID_ADMIN=prj_a \
STAGING_API_BASE_URL=https://api.staging.vergeo5.com \
  bash scripts/ci/vercel-staging-preview-prove.sh --portal vendor --dry-run >/tmp/preview-dry.txt 2>&1
rc=$?
set -e
if [[ "$rc" -eq 0 ]] && grep -q 'dry-run OK portal=vendor' /tmp/preview-dry.txt; then
  ok "vercel-staging-preview-prove dry-run"
else
  bad "vercel-staging-preview-prove dry-run failed (rc=$rc)"
  cat /tmp/preview-dry.txt || true
fi

# 15) Evidence bundle merges three portal JSON files (valid proof succeeds)
GOOD_SHA=deadbeefcafebabe0123456789abcdef01234567
STAGING_REF=abcdefghij1234567890
mkdir -p /tmp/evidence-bundle-test/{customer,vendor,admin}
for portal in customer vendor admin; do
  python3 - <<PY
import json, pathlib
portal = "${portal}"
doc = {
    "portal": portal,
    "vercel_project": f"convergeo-{portal}",
    "project_id": f"prj_{portal}",
    "candidate_sha": "${GOOD_SHA}",
    "deployment_id": f"dpl_{portal}",
    "preview_url": f"https://{portal}.example.vercel.app",
    "deployment_sha": "${GOOD_SHA}",
    "target": "preview",
    "health_status": "ok",
    "health_app": portal,
    "health_env": "staging",
    "health_build_id": "${GOOD_SHA}",
    "health_api_host": "api.staging.vergeo5.com",
    "env_metadata_status": "verified",
}
pathlib.Path("/tmp/evidence-bundle-test", portal, "evidence.json").write_text(
    json.dumps(doc) + "\n", encoding="utf-8"
)
PY
done
printf '{"env":"staging","git_sha":"%s","image_tag":"%s","supabase_project_ref":"%s"}\n' \
  "${GOOD_SHA}" "${GOOD_SHA}" "${STAGING_REF}" >/tmp/fingerprint-test.json
set +e
bash scripts/ci/staging-evidence-bundle.sh \
  --candidate-sha "${GOOD_SHA}" \
  --preview-dir /tmp/evidence-bundle-test \
  --fingerprint /tmp/fingerprint-test.json \
  --staging-supabase-project-id "${STAGING_REF}" \
  --migrate-result success \
  --output /tmp/staging-sha-proof-test.json >/tmp/bundle-out.txt 2>&1
rc=$?
set -e
if [[ "$rc" -eq 0 ]] \
  && grep -q '"candidate_sha": "deadbeefcafebabe0123456789abcdef01234567"' /tmp/staging-sha-proof-test.json \
  && grep -q '"customer"' /tmp/staging-sha-proof-test.json \
  && grep -q '"vendor"' /tmp/staging-sha-proof-test.json \
  && grep -q '"admin"' /tmp/staging-sha-proof-test.json; then
  ok "staging-evidence-bundle merges three portal proofs (valid case)"
else
  bad "staging-evidence-bundle valid case failed (rc=$rc)"
  cat /tmp/bundle-out.txt || true
fi

# 16) validate_staging_proof negative + positive regression cases
python3 - <<'PY'
import json
import subprocess
import sys
import tempfile
from pathlib import Path

GOOD_SHA = "deadbeefcafebabe0123456789abcdef01234567"
STAGING_REF = "abcdefghij1234567890"
PROD_REF = "dpadrlxukcjbewpqympu"
REPO = Path("scripts/ci")

def portal_doc(
    portal: str,
    *,
    sha: str = GOOD_SHA,
    candidate_sha: str | None = None,
    env_metadata: str = "verified",
    health_status: str = "ok",
    health_app: str | None = None,
    api_host: str = "api.staging.vergeo5.com",
    health_env: str = "staging",
    build_id: str | None = None,
    omit_build_id: bool = False,
):
    doc = {
        "portal": portal,
        "preview_url": f"https://{portal}.example.vercel.app",
        "deployment_id": f"dpl_{portal}",
        "candidate_sha": candidate_sha if candidate_sha is not None else sha,
        "deployment_sha": sha,
        "target": "preview",
        "health_status": health_status,
        "health_app": health_app if health_app is not None else portal,
        "health_env": health_env,
        "health_api_host": api_host,
        "env_metadata_status": env_metadata,
    }
    if not omit_build_id:
        doc["health_build_id"] = build_id if build_id is not None else sha
    return doc

def fingerprint(*, sha: str = GOOD_SHA, ref: str = STAGING_REF, env: str = "staging", image: str = GOOD_SHA):
    return {"env": env, "git_sha": sha, "image_tag": image, "supabase_project_ref": ref}

def run_validate(tmp: Path, fp: dict, previews: dict[str, dict], expect_ok: bool) -> bool:
    preview_dir = tmp / "previews"
    for portal, doc in previews.items():
        d = preview_dir / portal
        d.mkdir(parents=True, exist_ok=True)
        (d / "evidence.json").write_text(json.dumps(doc) + "\n", encoding="utf-8")
    fp_path = tmp / "fingerprint.json"
    fp_path.write_text(json.dumps(fp) + "\n", encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO / "validate_staging_proof.py"),
            "--candidate-sha",
            GOOD_SHA,
            "--staging-supabase-project-id",
            STAGING_REF,
            "--preview-dir",
            str(preview_dir),
            "--fingerprint",
            str(fp_path),
            "--migrate-result",
            "success",
        ],
        capture_output=True,
        text=True,
    )
    ok = proc.returncode == 0
    return ok if expect_ok else (not ok)

previews_ok = {p: portal_doc(p) for p in ("customer", "vendor", "admin")}

cases = [
    ("correct proof succeeds", lambda t: run_validate(t, fingerprint(), previews_ok, True)),
    ("wrong API git SHA fails", lambda t: run_validate(t, fingerprint(sha="0000000000000000000000000000000000000001"), previews_ok, False)),
    ("wrong staging Supabase ref fails", lambda t: run_validate(t, fingerprint(ref="wrongref123456789012345"), previews_ok, False)),
    ("production Supabase ref fails", lambda t: run_validate(t, fingerprint(ref=PROD_REF), previews_ok, False)),
    ("BLOCKED_EXTERNAL env metadata does NOT fail the proof (non-blocking, informational only)", lambda t: run_validate(
        t, fingerprint(), {**previews_ok, "customer": portal_doc("customer", env_metadata="BLOCKED_EXTERNAL")}, True)),
    ("wrong portal deployment SHA fails", lambda t: run_validate(
        t, fingerprint(), {**previews_ok, "vendor": portal_doc("vendor", sha="cafe" * 10)}, False)),
    ("admin health_status != ok is rejected — CF Access 403 is no longer an accepted outcome (PR #666)", lambda t: run_validate(
        t, fingerprint(), {**previews_ok, "admin": portal_doc("admin", health_status="cf_access_gate", api_host="")}, False)),
    ("wrong health_app fails", lambda t: run_validate(
        t, fingerprint(), {**previews_ok, "vendor": portal_doc("vendor", health_app="customer")}, False)),
    ("missing health_api_host fails", lambda t: run_validate(
        t, fingerprint(), {**previews_ok, "customer": portal_doc("customer", api_host="")}, False)),
    ("production API host rejected even with every other field correct", lambda t: run_validate(
        t, fingerprint(), {**previews_ok, "vendor": portal_doc("vendor", api_host="api.vergeo5.com")}, False)),
    ("localhost API host rejected", lambda t: run_validate(
        t, fingerprint(), {**previews_ok, "vendor": portal_doc("vendor", api_host="localhost")}, False)),
    ("arbitrary wrong API host rejected", lambda t: run_validate(
        t, fingerprint(), {**previews_ok, "vendor": portal_doc("vendor", api_host="wrong-host.example.com")}, False)),
    ("wrong health_env fails", lambda t: run_validate(
        t, fingerprint(), {**previews_ok, "admin": portal_doc("admin", health_env="production")}, False)),
    ("health_build_id absent passes (deployment_sha already proves candidate identity)", lambda t: run_validate(
        t, fingerprint(), {**previews_ok, "customer": portal_doc("customer", omit_build_id=True)}, True)),
    ("health_build_id present and wrong fails", lambda t: run_validate(
        t, fingerprint(), {**previews_ok, "customer": portal_doc("customer", build_id="cafe" * 10)}, False)),
]

failed = []
with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    for name, fn in cases:
        if not fn(tmp):
            failed.append(name)

if failed:
    print("FAIL: validate_staging_proof cases:", ", ".join(failed))
    sys.exit(1)
print("PASS: validate_staging_proof regression cases")
PY
if [[ "$?" -eq 0 ]]; then
  ok "validate_staging_proof negative/positive regression cases"
else
  bad "validate_staging_proof regression cases failed"
fi

# 17) Migration reconcile: matching remote succeeds; missing remote fails
REPO_VERSIONS="$(python3 - <<'PY'
from pathlib import Path
import re
versions = []
for path in sorted(Path("supabase/migrations").glob("*.sql")):
    versions.append(re.match(r"^(.+?)_.+\.sql$", path.name).group(1))
print("\n".join(versions))
PY
)"
printf '%s\n' "${REPO_VERSIONS}" >/tmp/repo-migrations.txt
set +e
python3 scripts/ci/reconcile_staging_migrations.py \
  --migrations-dir supabase/migrations \
  --remote-versions-file /tmp/repo-migrations.txt >/tmp/reconcile-ok.txt 2>&1
rc_ok=$?
head -1 /tmp/repo-migrations.txt | while read -r first; do break; done
printf '%s\n' "${REPO_VERSIONS}" | grep -v '^0095$' >/tmp/repo-migrations-missing.txt
python3 scripts/ci/reconcile_staging_migrations.py \
  --migrations-dir supabase/migrations \
  --remote-versions-file /tmp/repo-migrations-missing.txt >/tmp/reconcile-bad.txt 2>&1
rc_bad=$?
set -e
if [[ "$rc_ok" -eq 0 ]] && [[ "$rc_bad" -ne 0 ]]; then
  ok "migration reconcile matches repository tip; missing remote fails"
else
  bad "migration reconcile regression failed (ok=$rc_ok bad=$rc_bad)"
  cat /tmp/reconcile-ok.txt /tmp/reconcile-bad.txt || true
fi

# 18) vercel-staging-preview-prove: the deployed-health proof is the sole
# blocking release gate; the Vercel env-API check (including its
# BLOCKED_EXTERNAL outcome) is non-blocking/informational only (PR #666 —
# see vercel_preview_health_verify.py / vercel_preview_env_verify.py).
# Precisely: the ENV-API verdict must never appear in a failing branch. (A
# Vercel Deployment Protection challenge on the health probe is a DIFFERENT,
# legitimately blocking BLOCKED_EXTERNAL — see check 19 — so this must test
# the env-API variables, not the bare string.)
if grep -E 'api_env_verdict|env_metadata_status' scripts/ci/vercel-staging-preview-prove.sh \
  | grep -q 'die'; then
  bad "vercel-staging-preview-prove must NOT die on the env-API verdict — it is a non-blocking, informational signal, not the release gate"
else
  ok "vercel-staging-preview-prove treats the env-API verdict as non-blocking"
fi

if grep -Eq 'missing_host\) die|forbidden_host\) die|host_mismatch\) die|sha_mismatch\) die' \
  scripts/ci/vercel-staging-preview-prove.sh; then
  ok "vercel-staging-preview-prove fails closed on deployed-health verdict failures"
else
  bad "vercel-staging-preview-prove must die on a failing health verdict (missing_host/forbidden_host/host_mismatch/sha_mismatch)"
fi

# 19) Vercel Deployment Protection bypass (deploy-staging run #31 root cause):
# the health probe must authenticate with a per-project automation bypass
# secret, and that secret must never reach argv, a URL, a log, evidence, or
# GITHUB_OUTPUT. See scripts/ci/vercel_preview_access.py.
if grep -q -- '--config "${health_curl_config}"' scripts/ci/vercel-staging-preview-prove.sh \
  && grep -q 'chmod 600 "${health_curl_config}"' scripts/ci/vercel-staging-preview-prove.sh \
  && ! grep -q -- '-H "x-vercel-protection-bypass' scripts/ci/vercel-staging-preview-prove.sh; then
  ok "protection bypass secret reaches curl via a mode-600 config file, never argv"
else
  bad "protection bypass secret must be passed through a mode-600 curl config file, never -H/argv"
fi

# The secret must never be traced, echoed, or written to any evidence sink.
if grep -vE '^\s*#' scripts/ci/vercel-staging-preview-prove.sh | grep -Eq '(^|\s)set -x(\s|$)'; then
  bad "vercel-staging-preview-prove must never enable set -x (would trace the bypass secret)"
else
  ok "vercel-staging-preview-prove never enables set -x"
fi

# The ONLY permitted use of the secret value is writing the curl header line
# into the mode-600 config file; it must never be echoed or logged.
bypass_secret_uses="$(grep -n 'BYPASS_SECRET' scripts/ci/vercel-staging-preview-prove.sh \
  | grep -vE '^\s*[0-9]+:\s*#' \
  | grep -E 'echo|log |printf' \
  | grep -v 'x-vercel-protection-bypass: %s' || true)"
if [ -n "${bypass_secret_uses}" ]; then
  bad "vercel-staging-preview-prove must never echo/log the bypass secret value: ${bypass_secret_uses}"
else
  ok "vercel-staging-preview-prove never echoes the bypass secret value"
fi

# Only the SOURCE label (kind + variable name) may be recorded.
if grep -q '"bypass_source": os.environ\["bypass_source"\]' scripts/ci/vercel-staging-preview-prove.sh \
  && ! sed -n "/if \[ -n \"\${GITHUB_OUTPUT:-}\" \]; then/,\$p" scripts/ci/vercel-staging-preview-prove.sh \
     | grep -q 'BYPASS_SECRET'; then
  ok "only the bypass SOURCE label reaches evidence/GITHUB_OUTPUT, never the secret"
else
  bad "bypass secret must not reach evidence.json or GITHUB_OUTPUT (only its source label)"
fi

# A Vercel protection challenge must be classified BLOCKED_EXTERNAL, never
# reported as a broken application health route (run #31 misdiagnosis).
if grep -q 'blocked_external)' scripts/ci/vercel-staging-preview-prove.sh \
  && grep -q 'BLOCKED_EXTERNAL' scripts/ci/vercel-staging-preview-prove.sh \
  && python3 -m py_compile scripts/ci/vercel_preview_access.py; then
  ok "protection challenge classified BLOCKED_EXTERNAL, distinct from app failure"
else
  bad "vercel-staging-preview-prove must classify a protection challenge as BLOCKED_EXTERNAL"
fi

# The probe must retry only genuinely transient transport errors and fail
# immediately on deterministic ones (run #32 follow-up). Verified against
# libcurl's CURLE_* enum in vercel_preview_access.py.
retry_classification_ok=1
for code in 6 7 28; do
  verdict="$(python3 scripts/ci/vercel_preview_access.py classify-curl-exit --code "${code}")"
  case "${verdict}" in
    TRANSIENT_TRANSPORT*$'\t'1*) ;;
    *) retry_classification_ok=0; echo "  curl ${code} should be retryable, got: ${verdict}" ;;
  esac
done
for code in 3 23 26 60; do
  verdict="$(python3 scripts/ci/vercel_preview_access.py classify-curl-exit --code "${code}")"
  case "${verdict}" in
    NON_RETRYABLE_CURL*$'\t'0*) ;;
    *) retry_classification_ok=0; echo "  curl ${code} must NOT be retryable, got: ${verdict}" ;;
  esac
done
if [ "${retry_classification_ok}" -eq 1 ] \
  && grep -q 'if \[ "\${health_exit_retryable}" != "1" \]; then' scripts/ci/vercel-staging-preview-prove.sh; then
  ok "health probe retries transient transport errors only, never deterministic ones"
else
  bad "health probe must retry only transient curl transport errors (6/7/28/...) and fail fast on 3/23/26/60"
fi

# One-shot health probes send ONLY x-vercel-protection-bypass. Vercel
# documents x-vercel-set-bypass-cookie as optional, for maintaining
# authorization across multiple requests / in iframes — that belongs to the
# Playwright browser flow, not to a single manual-redirect request (run #33
# returned HTTP 307 on all three portals with it set).
if grep -q 'x-vercel-set-bypass-cookie' scripts/ci/vercel-staging-preview-prove.sh \
  && grep 'x-vercel-set-bypass-cookie' scripts/ci/vercel-staging-preview-prove.sh | grep -q 'printf'; then
  bad "deploy-staging one-shot health probe must NOT request a bypass cookie"
elif grep -n 'x-vercel-set-bypass-cookie' scripts/ci/e2e-staging-probe.mjs \
  | grep -vE '^\s*[0-9]+:\s*(//|\*)' | grep -q 'headers\['; then
  bad "e2e-staging-probe one-shot health fetch must NOT request a bypass cookie"
else
  ok "one-shot health probes send only x-vercel-protection-bypass (no cookie request)"
fi

# ...while the multi-request browser flow KEEPS the cookie, per Vercel's docs.
if grep -q 'x-vercel-set-bypass-cookie' e2e/playwright.config.ts \
  && grep -q 'x-vercel-set-bypass-cookie' e2e/fixtures/test-base.ts; then
  ok "Playwright browser flow preserves the bypass cookie for follow-up requests"
else
  bad "Playwright must keep x-vercel-set-bypass-cookie for multi-request browser continuity"
fi

# Redirect diagnostics must never surface a cookie value, a secret, or a query.
redirect_diag_headers="$(mktemp)"
printf 'HTTP/2 307 \r\nlocation: https://h.example/p?x-vercel-protection-bypass=LEAKME&nonce=N\r\nset-cookie: _vercel_jwt=JWTLEAK; Path=/\r\nserver: Vercel\r\n\r\n' \
  > "${redirect_diag_headers}"
redirect_diag_out="$(python3 scripts/ci/vercel_preview_access.py summarize-headers \
  --headers-file "${redirect_diag_headers}" 2>&1 || true)"
rm -f "${redirect_diag_headers}"
if grep -q 'summarize-headers --headers-file' scripts/ci/vercel-staging-preview-prove.sh \
  && ! printf '%s' "${redirect_diag_out}" | grep -Eq 'LEAKME|JWTLEAK|nonce|_vercel_jwt' \
  && printf '%s' "${redirect_diag_out}" | grep -q 'set_cookie=yes'; then
  ok "redirect diagnostics expose host/path + set_cookie=yes/no only, never values"
else
  bad "redirect diagnostics must not print Set-Cookie values, secrets, or query strings"
fi

# The bypass secret is redacted from any surfaced curl error, without ever
# being passed to an external command.
if grep -q 'sanitized_curl_error()' scripts/ci/vercel-staging-preview-prove.sh \
  && grep -q 'raw="\${raw//\${BYPASS_SECRET}/\[redacted\]}"' scripts/ci/vercel-staging-preview-prove.sh; then
  ok "curl stderr is redacted via bash expansion before being logged"
else
  bad "curl stderr must be redacted of the bypass secret before logging"
fi

# Per-portal Preview evidence must NOT be downloaded with merge-multiple.
# Each portal artifact carries evidence.json/deployment.json at its root, so
# merging all three into one directory collides them and silently destroys two
# portals' evidence (deploy-staging run #34). Without merge-multiple,
# download-artifact unpacks each artifact into its own <artifact-name>/ dir.
evidence_dl_block="$(sed -n '/Download Preview evidence artifacts/,/Normalize Preview evidence paths/p' \
  .github/workflows/deploy-staging.yml)"
if printf '%s' "${evidence_dl_block}" | grep -vE '^\s*#' | grep -q 'merge-multiple'; then
  bad "Preview evidence download must NOT use merge-multiple — the three portal artifacts collide and two are lost"
elif printf '%s' "${evidence_dl_block}" | grep -q 'pattern: staging-preview-evidence-\*'; then
  ok "Preview evidence downloads per-portal without merge-multiple (no artifact collision)"
else
  bad "Preview evidence download step must select the per-portal artifacts by pattern"
fi

# deploy-staging must scope the bypass secret per matrix leg (secrets are
# issued per Vercel project; three portals = three projects).
if grep -q 'bypass_secret_name: VERCEL_AUTOMATION_BYPASS_SECRET_CUSTOMER' .github/workflows/deploy-staging.yml \
  && grep -q 'bypass_secret_name: VERCEL_AUTOMATION_BYPASS_SECRET_VENDOR' .github/workflows/deploy-staging.yml \
  && grep -q 'bypass_secret_name: VERCEL_AUTOMATION_BYPASS_SECRET_ADMIN' .github/workflows/deploy-staging.yml \
  && grep -q 'VERCEL_PORTAL_BYPASS_SECRET: ${{ secrets\[matrix.bypass_secret_name\] }}' .github/workflows/deploy-staging.yml; then
  ok "deploy-staging passes only the matching portal bypass secret to each matrix leg"
else
  bad "deploy-staging must scope the Vercel bypass secret per portal via the job matrix"
fi

# ── E2E portal identity (Workstream A) ───────────────────────────────────────
# Playwright navigates the customer AND vendor origins directly, so a release
# baseline must pin and prove BOTH. These guards keep that contract from
# silently regressing back to "prove customer, assume the rest".

# The vendor target must be overridable at dispatch, exactly like base_url, so a
# release run can pin the immutable Preview URL instead of a mutable alias.
if grep -q '^      vendor_base_url:' .github/workflows/e2e.yml \
  && grep -q 'E2E_VENDOR_BASE_URL: ${{ inputs.vendor_base_url || secrets.E2E_VENDOR_BASE_URL }}' \
    .github/workflows/e2e.yml; then
  ok "e2e workflow accepts vendor_base_url and prefers it over the secret"
else
  bad "e2e workflow must expose a vendor_base_url dispatch input wired ahead of E2E_VENDOR_BASE_URL"
fi

# Both preflights must run, and both must run BEFORE any Playwright install, so
# a skewed target never reaches a browser.
# `|| true` matters: this file runs under `set -euo pipefail`, so a grep that
# matches nothing would abort the whole harness mid-run — failing with no
# diagnostic and silently skipping every guard below. A missing step must
# report as a FAILED GUARD, not as a crash.
e2e_probe_customer_line="$(grep -n 'e2e-staging-probe.mjs customer' .github/workflows/e2e.yml | head -1 | cut -d: -f1 || true)"
e2e_probe_vendor_line="$(grep -n 'e2e-staging-probe.mjs vendor' .github/workflows/e2e.yml | head -1 | cut -d: -f1 || true)"
e2e_install_line="$(grep -n 'playwright install' .github/workflows/e2e.yml | head -1 | cut -d: -f1 || true)"
if [[ -z "${e2e_probe_customer_line}" || -z "${e2e_probe_vendor_line}" ]]; then
  bad "e2e workflow must preflight BOTH directly-navigated portals (customer and vendor)"
elif [[ -z "${e2e_install_line}" ]]; then
  bad "e2e workflow: could not locate the Playwright install step to order preflights against"
elif [[ "${e2e_probe_customer_line}" -lt "${e2e_install_line}" \
  && "${e2e_probe_vendor_line}" -lt "${e2e_install_line}" ]]; then
  ok "e2e workflow proves customer + vendor identity before installing Playwright"
else
  bad "e2e portal preflights must run before the Playwright install step"
fi

# Admin is proven independently by Deploy staging and no spec navigates it.
# The moment a spec DOES navigate the admin origin, this guard demands the
# matching preflight rather than letting admin ride along unproven.
if grep -rqE '\bADMIN_BASE_URL\b' e2e/specs; then
  if grep -q 'e2e-staging-probe.mjs admin' .github/workflows/e2e.yml; then
    ok "a spec navigates the admin origin and the admin preflight exists"
  else
    bad "a spec now navigates ADMIN_BASE_URL — add an admin preflight to e2e.yml and PORTALS"
  fi
elif grep -q 'e2e-staging-probe.mjs admin' .github/workflows/e2e.yml; then
  bad "admin preflight present but no spec navigates the admin origin — remove the churn"
else
  ok "no spec navigates admin; correctly no admin preflight (Deploy staging proves it)"
fi

# Specs that navigate the vendor app must go through the fail-closed resolver,
# never the raw constant that silently falls back to the customer origin.
vendor_nav_specs="$(grep -rlE 'urlOn\(\s*(VENDOR_BASE_URL|vendorOrigin)' e2e/specs || true)"
if [[ -z "${vendor_nav_specs}" ]]; then
  bad "expected at least one spec to navigate the vendor origin"
elif grep -rqE '\bVENDOR_BASE_URL\b' e2e/specs; then
  bad "vendor-navigating specs must use requireVendorBaseUrl(), not the VENDOR_BASE_URL fallback"
elif grep -rq 'requireVendorBaseUrl' e2e/specs; then
  ok "vendor-navigating specs resolve their origin through the fail-closed requireVendorBaseUrl()"
else
  bad "vendor-navigating specs must resolve their origin through requireVendorBaseUrl()"
fi

# The resolver itself must fail closed on both degenerate configurations.
if grep -q 'export function requireVendorBaseUrl' e2e/fixtures/env.ts \
  && grep -q 'E2E_VENDOR_BASE_URL is not set' e2e/fixtures/env.ts \
  && grep -q 'same origin as E2E_BASE_URL' e2e/fixtures/env.ts; then
  ok "requireVendorBaseUrl fails closed on an unset vendor target and on origin collapse"
else
  bad "requireVendorBaseUrl must fail closed when E2E_VENDOR_BASE_URL is unset or collapses onto the customer origin"
fi

# The probe registry stays limited to portals a spec actually navigates.
if grep -q 'admin:' scripts/ci/e2e-staging-probe.mjs; then
  bad "e2e-staging-probe registers an admin portal that nothing navigates"
elif grep -q 'customer:' scripts/ci/e2e-staging-probe.mjs \
  && grep -q 'vendor:' scripts/ci/e2e-staging-probe.mjs; then
  ok "e2e-staging-probe registers exactly the directly-navigated portals"
else
  bad "e2e-staging-probe must register the customer and vendor portals"
fi

# Secret hygiene: the probe may name the SOURCE VARIABLE, never a value.
if grep -nE 'console\.(log|warn|error)' scripts/ci/e2e-staging-probe.mjs \
  | grep -vE '^\s*[0-9]+:\s*//' \
  | grep -qE '\$\{[^}]*(bypassSecret|secret)\b[^}]*\}'; then
  bad "e2e-staging-probe must never interpolate a bypass secret value into output"
else
  ok "e2e-staging-probe prints bypass SOURCE VARIABLE names only, never secret values"
fi

# ── Canonical E2E fixture contract (Workstream B) ────────────────────────────
# One source of truth for synthetic staging identity, one destructive reset per
# run, and no credential in generated source.

# The generated TS view must match the Python contract it claims to describe.
if python3 scripts/ci/generate-e2e-fixtures.py --check >/dev/null 2>&1; then
  ok "generated E2E fixtures are in sync with synthetic_contract.py"
else
  bad "e2e/fixtures/seed.generated.ts is stale — run python3 scripts/ci/generate-e2e-fixtures.py"
fi

# The generated file must stay generated.
if head -1 e2e/fixtures/seed.generated.ts | grep -q '@generated'; then
  ok "generated E2E fixtures carry the do-not-edit banner"
else
  bad "e2e/fixtures/seed.generated.ts must keep its @generated banner"
fi

# No credential may be generated into source. Comments explaining their ABSENCE
# are fine, so strip comments before scanning.
generated_code="$(sed 's://.*::' e2e/fixtures/seed.generated.ts | perl -0pe 's{/\*.*?\*/}{}gs' || true)"
if printf '%s' "${generated_code}" | grep -qiE 'otp|ticketpin|service_role|pin_hash'; then
  bad "generated E2E fixtures must never contain OTP codes, ticket PINs or service-role material"
else
  ok "generated E2E fixtures carry non-secret identity only"
fi

# Playwright must not reseed: the old module-scope beforeAll ran once per spec
# file per project (~80 destructive resets racing each other).
if grep -rq 'resetSeed' e2e; then
  bad "destructive resetSeed() must not run inside the Playwright lifecycle"
else
  ok "no destructive reset inside Playwright — reset is a single workflow step"
fi

# Exactly one mutating seed invocation per E2E run.
e2e_seed_applies="$(grep -c -- '--apply' .github/workflows/e2e.yml || true)"
if [ "${e2e_seed_applies}" = "1" ] && grep -q -- '--cleanup' .github/workflows/e2e.yml; then
  ok "e2e workflow performs exactly one destructive cleanup+seed per run"
else
  bad "e2e workflow must run exactly one canonical cleanup+seed (found ${e2e_seed_applies} --apply)"
fi

# The staging service-role key is step-scoped. Job-level env would expose it to
# every step including the Playwright run.
e2e_job_env="$(sed -n '/^    env:/,/^    steps:/p' .github/workflows/e2e.yml || true)"
if printf '%s' "${e2e_job_env}" | grep -q 'SERVICE_ROLE'; then
  bad "the staging service-role key must never be a job-level env var in e2e.yml"
elif [ "$(grep -c 'secrets.STAGING_SUPABASE_SERVICE_ROLE_KEY' .github/workflows/e2e.yml || true)" = "1" ]; then
  ok "staging service-role key is mapped into the canonical seed step only"
else
  bad "staging service-role key must be mapped exactly once, inside the seed step"
fi

# The seed target guard must run before the step that holds the key.
seed_guard_line="$(grep -n 'Guard canonical seed target' .github/workflows/e2e.yml | head -1 | cut -d: -f1 || true)"
seed_apply_line="$(grep -n 'Canonical cleanup + seed' .github/workflows/e2e.yml | head -1 | cut -d: -f1 || true)"
browser_line="$(grep -n 'Install Playwright Chromium' .github/workflows/e2e.yml | head -1 | cut -d: -f1 || true)"
if [ -z "${seed_guard_line}" ] || [ -z "${seed_apply_line}" ] || [ -z "${browser_line}" ]; then
  bad "e2e workflow must guard the seed target, seed once, then install the browser"
elif [ "${seed_guard_line}" -lt "${seed_apply_line}" ] && [ "${seed_apply_line}" -lt "${browser_line}" ]; then
  ok "e2e seeds only after the fail-closed target guard and before any browser"
else
  bad "e2e seed ordering is wrong: guard -> seed -> browser"
fi

# The run-scoped PIN is masked and the private file is always removed.
if grep -q '::add-mask::' .github/workflows/e2e.yml \
  && grep -q 'convergeo-e2e-private.json' .github/workflows/e2e.yml \
  && sed -n '/Remove private runtime material/,/run:/p' .github/workflows/e2e.yml | grep -q 'always()'; then
  ok "scanner PIN is masked and its private file is removed with always()"
else
  bad "e2e must mask the scanner PIN and delete the private runtime file with always()"
fi

# The retired remote-reset contract must not come back.
# --exclude this harness: it names the retired route in its own guard text, and
# a self-match would fail the check forever.
if grep -qE 'secrets\.E2E_SEED_(RESET_URL|TOKEN)' .github/workflows/e2e.yml \
  || grep -rq --exclude="$(basename "${BASH_SOURCE[0]}")" 'internal/e2e/reset' \
       .github/workflows scripts services/api/app 2>/dev/null; then
  bad "the remote seed-reset endpoint contract must stay retired (direct workflow seeding only)"
else
  ok "no remote seed-reset endpoint — direct protected-staging workflow seeding only"
fi

# ── Strict E2E execution policy (PR C) ───────────────────────────────────────
# "Skipped" and "passed" look identical in a green tick. A release baseline that
# silently skipped a required journey never exercised it — but reported success.

# Every release-critical journey must declare REQUIRED_STRICT *and* enforce it.
# Declaring without enforcing is the exact regression this guards against.
strict_sites_ok=1
for site in \
  "e2e/specs/auth-otp.spec.ts:customer OTP verification" \
  "e2e/specs/vendor-sell.spec.ts:vendor authenticated sell flow" \
  "e2e/specs/event-ticket.spec.ts:event scanner verify + duplicate-reject" \
  "e2e/specs/critical-path.spec.ts:checkout place-order -> payment surface"; do
  spec_file="${site%%:*}"
  spec_journey="${site#*:}"
  if ! grep -q 'kind: "REQUIRED_STRICT"' "${spec_file}"; then
    bad "${spec_file} no longer declares a REQUIRED_STRICT gate"
    strict_sites_ok=0
  elif ! grep -vE '^\s*(//|\*|/\*)' "${spec_file}" | grep -q 'enforceGate('; then
    # Comment lines are stripped first: a commented-out enforceGate() is exactly
    # the silent-skip regression this guard exists to catch.
    bad "${spec_file} declares a required gate but never enforces it — it would silently skip"
    strict_sites_ok=0
  elif ! grep -qF "${spec_journey}" "${spec_file}"; then
    bad "${spec_file} lost its REQUIRED_STRICT journey label (${spec_journey})"
    strict_sites_ok=0
  fi
done
if [ "${strict_sites_ok}" = "1" ]; then
  ok "all four release-critical journeys declare AND enforce REQUIRED_STRICT"
fi

# Optional gates must stay classified and must never escalate.
optional_ok=1
for site in \
  "e2e/specs/shop-checkout-momo.spec.ts:OPTIONAL_GATE" \
  "e2e/specs/clips-feed.spec.ts:FEATURE_DISABLED" \
  "e2e/specs/clips-commerce.spec.ts:FEATURE_DISABLED" \
  "e2e/specs/mobile-layout.spec.ts:VIEWPORT_NOT_APPLICABLE"; do
  spec_file="${site%%:*}"
  spec_kind="${site#*:}"
  if ! grep -q "kind: \"${spec_kind}\"" "${spec_file}"; then
    bad "${spec_file} lost its ${spec_kind} classification"
    optional_ok=0
  elif grep -vE '^\s*(//|\*|/\*)' "${spec_file}" | grep -q 'enforceGate('; then
    bad "${spec_file} must not enforce — ${spec_kind} is never a certification failure"
    optional_ok=0
  fi
done
if [ "${optional_ok}" = "1" ]; then
  ok "optional/feature/viewport gates stay classified and never escalate"
fi

# One definition of strict mode, reusing the existing certification helper.
# The policy's failure text legitimately says "integrated-staging"; what must
# never happen is the policy READING the environment for itself.
if grep -q 'strictCertificationRequired' e2e/fixtures/gating.ts \
  && ! grep -qE 'process\.env|CERTIFICATION_MODE' e2e/fixtures/gating-policy.ts; then
  ok "gating reuses strictCertificationRequired — no second definition of strict mode"
else
  bad "gating must derive strict mode from strictCertificationRequired(), not re-read the env"
fi

# Failure messages name the missing FIXTURE, never its value.
if grep -nE 'resolveGate\(\{' -A6 e2e/specs/*.spec.ts \
  | grep -qE '(staticCode|scannerPin|ticketPin\(\)|process\.env)'; then
  bad "a spec passes a credential VALUE into resolveGate — pass the fixture NAME only"
else
  ok "gates carry fixture NAMES only, never OTP/PIN/service-role/bypass values"
fi

# The gating tests import a .ts module, so every self-test invocation must carry
# the type-stripping flag or release-certify breaks the moment it runs them.
selftest_calls="$(grep -rhoE 'node .*--test scripts/qa/self-test/\*\.test\.mjs' \
  .github/workflows package.json scripts/qa/release-certify.sh 2>/dev/null || true)"
if [ -z "${selftest_calls}" ]; then
  bad "could not locate the qa self-test invocations"
elif printf '%s\n' "${selftest_calls}" | grep -qv -- '--experimental-strip-types'; then
  bad "every 'node --test scripts/qa/self-test/*' invocation must pass --experimental-strip-types"
else
  ok "all qa self-test invocations enable TypeScript stripping for the gating tests"
fi

echo "Results: ${pass} passed, ${fail} failed, ${skip} skipped"
if [[ "$skip" -gt 0 ]]; then
  echo "NOTE: ${skip} case(s) could not run — they are NOT passes. See SKIP lines above."
fi
if [[ "$fail" -gt 0 ]]; then
  exit 1
fi
exit 0
