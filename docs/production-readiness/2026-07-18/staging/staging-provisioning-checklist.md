# Staging provisioning checklist (STG-01)

Human bring-up steps for a separable Vergeo5 staging plane.  
**This STG-01 PR does not execute these steps** — it only adds code, CI, and docs.

Mark items only after evidence is recorded (project refs, hostnames, SHA tags).
Never paste secret values into this file.

---

## 0. Separation proof (before any mutate)

- [ ] Staging Supabase project ref recorded and **≠** `dpadrlxukcjbewpqympu`
- [ ] Staging API hostname recorded as `api.staging.vergeo5.com` (or other non-prod) and **≠** `api.vergeo5.com`
- [ ] Staging n8n host **≠** `n8n.vergeo5.com`
- [ ] `bash scripts/ci/check-staging-separation.sh` passes with staging identifiers
- [ ] GitHub Environment `staging` created with protection rules (required reviewers / limit self-approve as appropriate)

---

## 1. Supabase staging project

- [ ] Create blank Supabase project (region chosen; note project ref)
- [ ] Set database password; store as `STAGING_SUPABASE_DB_PASSWORD`
- [ ] Store URL, anon key, service-role key (service-role → API host only)
- [ ] Enable required extensions via migrations (do not hand-copy prod schema)
- [ ] Run (or let workflow run) `supabase db push` from repo — confirm **0056** applied
- [ ] Run typegen; confirm public tables have RLS enabled
- [ ] Confirm views use `security_invoker` where supported / are not naively exposed
- [ ] **Do not** import production dump, Auth users, Storage KYC objects, or payment rows
- [ ] Optional: `python3 scripts/seed_staging.py --env staging --apply` after guards pass

---

## 2. DNS / Cloudflare

- [ ] `api.staging.vergeo5.com` → staging OCI IP (proxied)
- [ ] `n8n.staging.vergeo5.com` → staging OCI IP (proxied)
- [ ] Optional: `vendor.staging.vergeo5.com` / `admin.staging.vergeo5.com` if not using Vercel Preview URLs
- [ ] TLS Full (strict) once certificates issue
- [ ] Confirm no CNAME/A record aliases staging → production origins

---

## 3. OCI staging API + n8n

- [ ] Staging VM **or** co-located host with distinct container/port/env (preferred: dedicated Always-Free capacity if available)
- [ ] Create `~/vergeo5-api-staging.env` from `infra/staging/.env.staging.example` (`chmod 600`)
- [ ] Set `ENV=staging`, `PUBLIC_API_HOST=api.staging.vergeo5.com`, `LENCO_ENV=sandbox`
- [ ] Leave `STAGING_ALLOW_OUTBOUND` / `STAGING_ALLOW_PAYOUTS` unset initially
- [ ] Install `infra/staging/redeploy-api-staging.sh`
- [ ] First deploy: `./redeploy-api-staging.sh <git-sha>` (never `latest`)
- [ ] Host Caddy (or compose `caddy-staging`) routes `api.staging` → `127.0.0.1:8001`
- [ ] Start `n8n-staging` with staging `API_URL` / webhook URL
- [ ] `curl -fsS https://api.staging.vergeo5.com/fingerprint` → `env=staging`, non-prod ref

---

## 4. Vercel Preview (`staging` branch)

- [ ] Protect git branch `staging`
- [ ] For `convergeo-customer`, `convergeo-vendor`, `convergeo-admin`:
  - [ ] Preview env vars for branch `staging` from `infra/staging/vercel-preview.env.example`
  - [ ] API base → staging API (customer + vendor `NEXT_PUBLIC_API_BASE_URL`, admin `NEXT_PUBLIC_VERGEO_API_URL`)
  - [ ] Cross-links use staging/preview URLs (no localhost, no prod vendor/admin hosts)
  - [ ] No service-role / Lenco secrets in project env
- [ ] Push or redeploy `staging` branch; record Preview URLs
- [ ] Probe `/en/health` on each Preview → `buildId` present, no secrets

---

## 5. n8n workflows

- [ ] Staging credentials created (not imported from production)
- [ ] Import JSON from `infra/n8n/*.json` — leave **inactive**
- [ ] Confirm every HTTP node uses `$env.API_URL` → staging
- [ ] Activate only after API fingerprint + sandbox payment posture confirmed
- [ ] Document rollback owner (see `infra/staging/n8n/README.md`)

---

## 6. CI secrets + first workflow run

- [ ] Populate GitHub Environment secrets per `staging-secret-register.md`
- [ ] `workflow_dispatch` **Deploy staging** on a known SHA
- [ ] Separation job green
- [ ] Migration job shows **0056**
- [ ] API deploy record artifact uploaded
- [ ] Smoke fingerprint artifact uploaded
- [ ] Confirm “never promote production” job ran

---

## 7. Post-bring-up gates (handoff to release verification)

- [ ] Update `staging-blockers.md` SB-01 → cleared with identifier evidence
- [ ] Seed register `staging-test-data-register.md` with redacted IDs after synthetic seed
- [ ] Sandbox Lenco drill ready (SB-03+)
- [ ] No production credentials present on staging host (`grep` for prod ref must be empty in env files — do not print values)

---

## Abort criteria

Stop and reset if any of the following occur:

- Staging Supabase ref equals production
- Staging API traffic hits `api.vergeo5.com`
- Workflow would deploy `latest` or production container name
- Seed/migrate pointed at production DB URL
- Production n8n credentials imported into staging
