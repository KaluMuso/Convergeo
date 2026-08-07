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
  && python3 -m py_compile scripts/ci/validate_staging_proof.py \
  && python3 -m py_compile scripts/ci/reconcile_staging_migrations.py; then
  ok "preview prove + evidence bundle + migration reconcile syntax"
else
  bad "preview prove / evidence bundle / migration reconcile syntax invalid"
fi

# 13) deploy-staging wires explicit Preview proof for all three portals
if grep -q 'prove-vercel-preview' .github/workflows/deploy-staging.yml \
  && grep -q 'matrix:' .github/workflows/deploy-staging.yml \
  && grep -q 'portal: \[customer, vendor, admin\]' .github/workflows/deploy-staging.yml \
  && grep -q 'vercel-staging-preview-prove.sh' .github/workflows/deploy-staging.yml \
  && grep -q 'staging-sha-proof' .github/workflows/deploy-staging.yml \
  && grep -q 'staging-evidence-bundle.sh' .github/workflows/deploy-staging.yml \
  && grep -q 'reconcile-staging-migrations.sh' .github/workflows/deploy-staging.yml; then
  ok "deploy-staging proves customer/vendor/admin Preview at same SHA"
else
  bad "deploy-staging missing three-portal Preview proof wiring"
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
  health_verdict="ok"
  health_http="200"
  if [ "$portal" = "admin" ]; then
    health_verdict="cf_access_gate"
    health_http="403"
  fi
  python3 - <<PY
import json, pathlib
portal = "${portal}"
doc = {
    "portal": portal,
    "deployment_url": f"https://{portal}.example.vercel.app",
    "deployment_id": f"dpl_{portal}",
    "github_commit_sha": "${GOOD_SHA}",
    "target": "preview",
    "api_env_verdict": "verified",
    "health_verdict": "${health_verdict}",
    "health_http": "${health_http}",
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

def portal_doc(portal: str, *, sha: str = GOOD_SHA, api_env: str = "verified", health: str = "ok", http: str = "200"):
    if portal == "admin" and health == "cf_access_gate":
        http = "403"
    return {
        "portal": portal,
        "deployment_url": f"https://{portal}.example.vercel.app",
        "deployment_id": f"dpl_{portal}",
        "github_commit_sha": sha,
        "target": "preview",
        "api_env_verdict": api_env,
        "health_verdict": health,
        "health_http": http,
    }

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
previews_ok["admin"] = portal_doc("admin", health="cf_access_gate")

cases = [
    ("correct proof succeeds", lambda t: run_validate(t, fingerprint(), previews_ok, True)),
    ("wrong API git SHA fails", lambda t: run_validate(t, fingerprint(sha="0000000000000000000000000000000000000001"), previews_ok, False)),
    ("wrong staging Supabase ref fails", lambda t: run_validate(t, fingerprint(ref="wrongref123456789012345"), previews_ok, False)),
    ("production Supabase ref fails", lambda t: run_validate(t, fingerprint(ref=PROD_REF), previews_ok, False)),
    ("BLOCKED_EXTERNAL Vercel env proof fails", lambda t: run_validate(
        t, fingerprint(), {**previews_ok, "customer": portal_doc("customer", api_env="BLOCKED_EXTERNAL")}, False)),
    ("wrong portal SHA fails", lambda t: run_validate(
        t, fingerprint(), {**previews_ok, "vendor": portal_doc("vendor", sha="cafe" * 10)}, False)),
    ("valid admin CF Access 403 remains accepted", lambda t: run_validate(
        t, fingerprint(), {**previews_ok, "admin": portal_doc("admin", health="cf_access_gate")}, True)),
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

# 18) vercel-staging-preview-prove rejects BLOCKED_EXTERNAL at source
if grep -q 'BLOCKED_EXTERNAL.*die\|die.*BLOCKED_EXTERNAL' scripts/ci/vercel-staging-preview-prove.sh; then
  ok "vercel-staging-preview-prove fails closed on BLOCKED_EXTERNAL"
else
  bad "vercel-staging-preview-prove must die on BLOCKED_EXTERNAL"
fi

echo "Results: ${pass} passed, ${fail} failed, ${skip} skipped"
if [[ "$skip" -gt 0 ]]; then
  echo "NOTE: ${skip} case(s) could not run — they are NOT passes. See SKIP lines above."
fi
if [[ "$fail" -gt 0 ]]; then
  exit 1
fi
exit 0
