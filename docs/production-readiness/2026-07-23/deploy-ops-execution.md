# Deploy ops execution — 2026-07-23

**UTC:** 2026-07-23T18:30Z  
**Requested:** API redeploy `GIT_SHA=d591ef5`, promote vendor/admin to master, activate n8n workflows.

## Results

| Task                             | Status                     | Evidence                                                                                                                                                      |
| -------------------------------- | -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **n8n — payment reconciliation** | **DONE**                   | Published workflow `C1MpTNjrfLACMG3f` via n8n MCP; `active=true`                                                                                              |
| **n8n — Wave A fleet**           | **Already live**           | dispatch, reservation-sweeper, embeddings, admin-digest, analytics-retention, operational-nudges all `active=true` (see `docs/ops/n8n-activation-runbook.md`) |
| **n8n — shared error alert**     | **Held**                   | `LVuHqWgT1tqjYOtc` — no WhatsApp output node; sticky note gate                                                                                                |
| **n8n — database backup**        | **Held**                   | `OAdOD4kmIbSNehkJ` — needs SSH + OCI Object Storage creds                                                                                                     |
| **Admin Vercel promote**         | **DONE (git auto-deploy)** | `dpl_5TmiZvXMpJqmJD7fgJqdafSoZhZX` READY, `target=production`, alias `admin.vergeo5.com`, SHA `ceb7519`                                                       |
| **Vendor Vercel promote**        | **DONE (git auto-deploy)** | `dpl_AeQaF7Gj9FHaF4xJbuKgZhKMyNEZ` READY, `target=production`, alias `vendor.vergeo5.com`, SHA `a5c9f57` (#506)                                               |
| **Customer Vercel**              | **Already at master**      | `d591ef5` production (`GET /en/health` buildId)                                                                                                               |
| **API redeploy + G9**            | **BLOCKED**                | SSH `root@91.107.236.37` permission denied (publickey). Fingerprint still `git_sha=unknown`.                                                                  |

## API redeploy — founder action required

On Hetzner host `91.107.236.37`:

```bash
bash /root/redeploy-api.sh d591ef518980381aa75cd23f86e06e8990f7adbc
# or after merging deploy-production.yml:
# GitHub Actions → Deploy production → api_image_tag=d591ef518980381aa75cd23f86e06e8990f7adbc
```

Add GitHub `production` environment secrets: `PRODUCTION_API_SSH_HOST`, `PRODUCTION_API_SSH_USER`, `PRODUCTION_API_SSH_KEY`, `VERCEL_TOKEN`.

Optional: add cloud-agent SSH pubkey from `docs/production-readiness/2026-07-20/p0-unblock-execution.md` §1 for automated reruns.

**Done when:** `curl -fsS https://api.vergeo5.com/fingerprint` shows `git_sha` matching deploy SHA.

## Vercel vendor/admin — complete

Both apps auto-deployed from master git integration (no manual promote needed):

- **Admin:** `ceb7519` @ `admin.vergeo5.com`
- **Vendor:** `a5c9f57` @ `vendor.vergeo5.com`

Verify: `bash scripts/ops/probe-frontends.sh`

For master tip `b93eb8e` (after this PR merges), re-run git production deploy or `Deploy production` workflow with `skip_api=true`.

## Automation added

- `.github/workflows/deploy-production.yml` — workflow_dispatch for API SSH redeploy + vendor/admin promote + `verify_live.sh`
- `scripts/ops/vercel_promote.sh` — REST API promote (no CLI auth required)
