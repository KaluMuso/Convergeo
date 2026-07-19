# n8n staging plane

Isolated automation for Vergeo5 staging. Production n8n credentials, webhook URLs,
and workflows that target `api.vergeo5.com` must remain inaccessible to this plane.

## Principles

1. **Separate credentials** — staging encryption key, basic-auth, and internal API
   tokens must differ from production (`infra/staging/.env.staging.example`).
2. **Staging API only** — every workflow uses `$env.API_URL` →
   `https://api.staging.vergeo5.com` (never `api.vergeo5.com`).
3. **Inactive until verified** — imported workflows start **inactive**; activate
   only after fingerprint + smoke evidence (see staging-plane-runbook).
4. **No production credential import** — do not copy production n8n credential
   store or reuse production `INTERNAL_*` tokens.

## Bring-up (after staging API is healthy)

```bash
# On the staging host (compose stack from infra/staging/docker-compose.staging.yml)
cd infra/staging
docker compose -f docker-compose.staging.yml --env-file .env up -d n8n-staging

# Confirm API_URL inside the container
docker exec vergeo5-n8n-staging printenv API_URL
# Expect: https://api.staging.vergeo5.com
```

## Import workflows

Source JSON lives in `infra/n8n/*.json` (shared definitions; runtime API host is
env-driven via `$env.API_URL`).

1. Open `https://n8n.staging.vergeo5.com` with staging basic-auth.
2. Create staging-only credentials for HTTP Header Auth using staging
   `INTERNAL_*` tokens (names in secret register — values never in git).
3. Import JSON files one by one (Settings → Import from File), **leave inactive**.
4. Priority imports for staging verification:
   - `notification-dispatch.json`
   - `reconciliation.json` / payment sweeper
   - `release-job.json`
   - `event-release.json`
   - `tickets-issue.json`
5. For each workflow, confirm every HTTP node URL resolves via
   `={{$env.API_URL}}/internal/...` and does **not** hardcode production.

## Activation checklist

- [ ] `GET https://api.staging.vergeo5.com/fingerprint` shows `env=staging` and
      a non-production `supabase_project_ref`
- [ ] Staging separation CI job green for this deploy
- [ ] Sandbox Lenco only (`LENCO_ENV=sandbox`)
- [ ] Outbound notifications still suppressed unless explicitly redirected
- [ ] Activate one workflow at a time; record execution IDs in the evidence pack

## Rollback

1. **Deactivate all** staging workflows in the UI (or stop the container).
2. Restore previous workflow versions from git (`infra/n8n/*.json` at known-good SHA).
3. If credentials were corrupted, recreate staging credentials from the secret
   register — never re-import production credential exports.
4. Container rollback:
   ```bash
   docker compose -f infra/staging/docker-compose.staging.yml --env-file .env \
     up -d --force-recreate n8n-staging
   ```
5. Volume wipe (destructive — loses execution history):
   ```bash
   docker compose -f infra/staging/docker-compose.staging.yml down
   docker volume rm vergeo5-staging_n8n_staging_data
   ```

## Related

- `infra/staging/.env.staging.example` — `API_URL`, `WEBHOOK_URL`, n8n auth names
- `docs/production-readiness/2026-07-18/staging/staging-plane-runbook.md`
- `docs/ops/n8n-workflows.md` — workflow registry
