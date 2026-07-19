# Staging plane runbook (STG-01)

**Status:** Infrastructure + CI only — this document does **not** provision or
deploy external resources. Follow the provisioning checklist before the first
real staging deploy.

**Canonical staging API hostname:** `api.staging.vergeo5.com`  
(Existing DNS convention in `infra/ENVIRONMENTS.md`. Proposed `staging-api.vergeo5.com`
is **not** used.)

**Forbidden production targets (never point staging at these):**

| Kind                       | Identifier                                                                      |
| -------------------------- | ------------------------------------------------------------------------------- |
| Supabase project ref       | `dpadrlxukcjbewpqympu`                                                          |
| API host                   | `api.vergeo5.com`                                                               |
| Customer / vendor / admin  | `vergeo5.com`, `vendor.vergeo5.com`, `admin.vergeo5.com`                        |
| n8n                        | `n8n.vergeo5.com`                                                               |
| Vercel production projects | `convergeo-customer` / `convergeo-vendor` / `convergeo-admin` Production target |

Registry file: `infra/staging/forbidden-production-identifiers.env`.

---

## What STG-01 delivers

| Plane              | Artifact                                                                                                                              |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------- |
| CI/CD              | `.github/workflows/deploy-staging.yml` — manual / `staging`-branch deploy into GitHub Environment `staging`                           |
| Separation gate    | `scripts/ci/check-staging-separation.sh` + CI self-test `scripts/ci/test-staging-guards.sh`                                           |
| API process guards | `services/api/app/core/env_guards.py` — refuse prod Supabase ref / API host; require `LENCO_ENV=sandbox`; suppress outbound + payouts |
| Fingerprint        | `GET /fingerprint` (API) + locale `/health` buildId (Next apps)                                                                       |
| OCI staging        | `infra/staging/docker-compose.staging.yml`, `redeploy-api-staging.sh`, `.env.staging.example`                                         |
| Vercel             | Branch-scoped Preview env template `infra/staging/vercel-preview.env.example`                                                         |
| n8n                | `infra/staging/n8n/README.md` — import/activate/rollback                                                                              |
| Seed               | `scripts/seed_staging.py` — synthetic `stg-rv-*` only                                                                                 |

**Never auto-promotes to production.**

---

## Prerequisites (human / founder)

Complete `staging-provisioning-checklist.md` and populate secrets from
`staging-secret-register.md` into the GitHub `staging` environment. Do not paste
secret values into git, tickets, or agent logs.

---

## Deploy (after secrets exist)

### A. Explicit workflow_dispatch (preferred)

1. Ensure branch contains the SHA you want (usually `staging` or a release cut).
2. Actions → **Deploy staging** → Run workflow.
3. Optional inputs:
   - `api_image_tag` — pin/rollback SHA (default = commit SHA)
   - `skip_migrate` — if DB already current
   - `skip_vercel` — API-only redeploy
   - `seed_synthetic` — run `scripts/seed_staging.py --apply`
4. Jobs must pass in order:
   - Environment separation
   - Supabase migrations (includes **0056**) + RLS check + typegen
   - Build API image (**SHA tag only**, never `latest`)
   - OCI staging deploy (`vergeo5-api-staging` on `:8001`)
   - Vercel Preview wiring check
   - Smoke (`/healthz`, `/readyz`, `/fingerprint`)

### B. Push to protected `staging` branch

Pushing to `staging` triggers the same workflow. Protect the branch (required
reviewers + restrict who can push).

---

## Supabase staging

1. Create a **new** Supabase project (blank). Record project ref ≠ `dpadrlxukcjbewpqympu`.
2. Store `STAGING_SUPABASE_PROJECT_ID`, `STAGING_SUPABASE_DB_PASSWORD`,
   `STAGING_SUPABASE_URL`, `STAGING_SUPABASE_DB_URL`, anon + service-role keys
   in GitHub `staging` + OCI env file.
3. Workflow runs `supabase db push` from repo migrations (blank → current,
   including `0056_kyc_integrity.sql`).
4. Verify RLS on all public base tables **and** exposed-view `security_invoker`
   posture via `scripts/ci/check-staging-schema.sh` (workflow step).
5. Do not expose service-role credentials to frontends.
6. Seed **only** via `scripts/seed_staging.py` (synthetic). Never dump/restore
   production PII, auth users, orders, or payments into staging.

Local migration replay (no remote):

```bash
# Same path as CI migrations job
bash scripts/ci/migration-replay.sh
ls supabase/migrations/0056_*.sql
```

---

## API staging (OCI)

| Item          | Production             | Staging                                |
| ------------- | ---------------------- | -------------------------------------- |
| Container     | `vergeo5-api`          | `vergeo5-api-staging`                  |
| Bind          | `127.0.0.1:8000`       | `127.0.0.1:8001`                       |
| Env file      | `~/vergeo5-api.env`    | `~/vergeo5-api-staging.env`            |
| Image tag     | often `:latest` or SHA | **SHA only**                           |
| Hostname      | `api.vergeo5.com`      | `api.staging.vergeo5.com`              |
| Deploy record | —                      | `~/.vergeo5-staging/api-deploy-record` |

```bash
# On staging host
cp infra/staging/redeploy-api-staging.sh ~/
chmod +x ~/redeploy-api-staging.sh
./redeploy-api-staging.sh <git-sha>
./redeploy-api-staging.sh --rollback
```

Startup refuses `ENV=staging` + production Supabase ref. Payments require
`LENCO_ENV=sandbox`. Outbound notifications and payouts are suppressed unless
`STAGING_ALLOW_OUTBOUND` / `STAGING_ALLOW_PAYOUTS` are explicitly enabled for a
sandbox drill.

Fingerprint (no secrets):

```bash
curl -fsS https://api.staging.vergeo5.com/fingerprint
# {"status":"ok","env":"staging","git_sha":"...","image_tag":"...","supabase_project_ref":"<staging-ref>"}
```

---

## Vercel Preview (`staging` branch)

Use **branch-scoped Preview** on the existing three projects (customer / vendor /
admin). Separate staging Vercel projects are not required.

Set Preview → Git Branch `staging` variables from
`infra/staging/vercel-preview.env.example`:

- `NEXT_PUBLIC_API_BASE_URL=https://api.staging.vergeo5.com`
- Admin: `NEXT_PUBLIC_VERGEO_API_URL=https://api.staging.vergeo5.com`
- Cross-links: staging/preview URLs only (no localhost, no production hosts)
- `NEXT_PUBLIC_VERGEO_ENV=staging`
- Never put service-role or payment secrets in `NEXT_PUBLIC_*`

Health fingerprint: `GET /en/health` → `{ status, app, env, buildId }`.

---

## n8n staging

Follow `infra/staging/n8n/README.md`.

- Separate encryption key + basic auth + `INTERNAL_*` tokens
- `$env.API_URL=https://api.staging.vergeo5.com`
- Import workflows **inactive**; activate after fingerprint smoke
- Rollback = deactivate + re-import from git SHA / recreate credentials

---

## Rollback procedure

### API

1. Read previous image: `cat ~/.vergeo5-staging/api-previous-image`
2. `./redeploy-api-staging.sh --rollback` **or**
   `./redeploy-api-staging.sh <previous-sha>`
3. Confirm `/fingerprint` shows previous `git_sha` / `image_tag`
4. Keep migration rollback separate (additive migrations — prefer forward fix)

### Vercel

Promote/redeploy previous Preview deployment for the `staging` branch in each
project dashboard, or revert the git commit on `staging` and re-push.

### n8n

Deactivate workflows → restore JSON from known-good SHA → recreate staging
credentials if needed (`infra/staging/n8n/README.md`).

### Database

Do **not** restore production dumps into staging. For staging wipe: recreate
project or `supabase db reset` equivalent on the staging project, re-push
migrations, re-run synthetic seed.

---

## Evidence to attach after a real deploy

- Separation job green
- Migration list including **0056**
- `/fingerprint` JSON (`env=staging`, non-prod ref)
- Smoke artifact from workflow
- Deploy record (`image=…:sha`)
- Confirmation that production identifiers were not used

---

## Related

- `staging-secret-register.md` — secret **names** only
- `staging-provisioning-checklist.md` — human bring-up steps
- `staging-blockers.md` / `staging-release-evidence.md` — prior audit context
- `infra/staging/*` — templates and scripts
