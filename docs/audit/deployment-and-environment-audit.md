# Deployment & Environment Audit

---

## Vercel projects (team: Vergeo Projects)

| Project            | ID                                 | Domains                      | Framework | Node | Latest deploy |
| ------------------ | ---------------------------------- | ---------------------------- | --------- | ---- | ------------- |
| convergeo-customer | `prj_lK6jnhAfVmhtaDZdMsIUF7LswgTP` | www.vergeo5.com, vergeo5.com | Next.js   | 24.x | READY         |
| convergeo-vendor   | `prj_QiX9rpStSpNeEXd3UZDFFp7H2dXf` | vendor.vergeo5.com           | Next.js   | 24.x | READY         |
| convergeo-admin    | `prj_Bpf852KXDuG1NZUomri0OsMBt1YS` | admin.vergeo5.com            | Next.js   | 24.x | READY         |
| vergeo-automation  | `prj_ZbbuuACndtdhD2rU14gnd2AuDXMd` | —                            | —         | —    | n8n hosting   |

**Note:** Vercel `live: false` on projects — domains still resolve and serve traffic (verified via curl).

### Recent deployment (customer)

- **Branch:** `claude/convergeo-codebase-review-122d5o` (preview-style, not necessarily production alias)
- **SHA:** `12e82de1ebd2398c8cc343c71ade233462e0ccf8`
- **State:** READY

**Unable to verify:** which deployment is aliased to production domains without Vercel deployment promotion API.

---

## API deployment (OCI)

| Attribute   | Value                                         |
| ----------- | --------------------------------------------- |
| **Host**    | api.vergeo5.com                               |
| **Process** | GitHub Actions `api-image.yml` → Docker → OCI |
| **Proxy**   | Caddy (per `infra/`)                          |
| **Health**  | `/healthz` 200                                |
| **OpenAPI** | `/openapi.json` — 256 paths                   |

---

## Database deployment (Supabase)

| Attribute                 | Value                                                         |
| ------------------------- | ------------------------------------------------------------- |
| **Project**               | dpadrlxukcjbewpqympu                                          |
| **Region**                | eu-north-1                                                    |
| **Status**                | ACTIVE_HEALTHY                                                |
| **Migration process**     | `supabase db push` / CI `db` job (`db reset` + typegen drift) |
| **Production migrations** | 71 applied                                                    |

---

## Environment variables

### Present in repository (names only)

From `.env.example`:

```
SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_ANON_KEY
NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY
NEXT_PUBLIC_API_BASE_URL, NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME
NEXT_PUBLIC_SEASONAL_THEME, NEXT_PUBLIC_ADMIN_BYPASS
CF_ACCESS_TEAM_DOMAIN, CF_ACCESS_AUD
LENCO_API_TOKEN, LENCO_BASE_URL
OPENROUTER_API_KEY
WHATSAPP_TOKEN, AT_API_KEY, AT_USERNAME, AT_SENDER_ID
SEND_SMS_HOOK_SECRET, RESEND_API_KEY, CLOUDINARY_URL
```

Admin additionally uses `NEXT_PUBLIC_VERGEO_API_URL` (see `apps/admin/lib/api-base-url.ts`).

### Production configuration status

| Variable                            | Customer                 | Vendor  | Admin   | API     | Evidence             |
| ----------------------------------- | ------------------------ | ------- | ------- | ------- | -------------------- |
| `NEXT_PUBLIC_API_BASE_URL`          | ⚠️ Suspect missing/wrong | Unknown | N/A     | N/A     | Cart calls localhost |
| `NEXT_PUBLIC_VERGEO_API_URL`        | N/A                      | N/A     | Unknown | N/A     | Not verifiable       |
| `NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME` | ⚠️ Suspect missing       | —       | —       | —       | Search images broken |
| `NEXT_PUBLIC_SUPABASE_*`            | ✅ Likely set            | ✅      | ✅      | —       | Auth pages load      |
| Supabase service keys               | —                        | —       | —       | ✅      | API healthy          |
| Lenco credentials                   | —                        | —       | —       | Unknown | 0 payments           |
| INTERNAL_*_TOKEN                    | —                        | —       | —       | ✅      | n8n crons succeeding |

**Unable to verify:** actual Vercel env values (secrets not exposed via MCP).

---

## CI/CD workflows

| Workflow             | Trigger                   | Deploy target          |
| -------------------- | ------------------------- | ---------------------- |
| `ci.yml`             | PR, push master, nightly  | Test only              |
| `perf.yml`           | PR                        | Lighthouse CI          |
| `e2e.yml`            | PR                        | Playwright             |
| `api-image.yml`      | Push                      | OCI container registry |
| `deploy-staging.yml` | Manual / `staging` branch | Staging env            |
| `restore-drill.yml`  | Scheduled                 | Backup verification    |

### Required CI checks (from README)

`js`, `python`, `ask-evals`, `staging-guards`, `secret-scan`, `deps-audit`, `security-gates`, `migrations`, `db`, `rls`, `money-db-triggers`, `cod-container-smoke`, `perf`

---

## Staging separation

`deploy-staging.yml` enforces:

- `STAGING_SUPABASE_PROJECT_ID` ≠ `dpadrlxukcjbewpqympu` (prod)
- `STAGING_API_HOST` ≠ `api.vergeo5.com`

---

## Rollback options

| Surface  | Method                                                       |
| -------- | ------------------------------------------------------------ |
| Vercel   | Redeploy previous deployment / instant rollback in dashboard |
| API      | Redeploy previous Docker image tag (git SHA)                 |
| Database | Supabase PITR + migration revert (additive-only policy)      |
| n8n      | `restore_workflow_version` via MCP                           |

---

## Monitoring & observability

| Tool              | Status                                                        |
| ----------------- | ------------------------------------------------------------- |
| Sentry            | Configured (`SENTRY_DSN` in API + customer `sentry-init.tsx`) |
| GA4               | Referenced in CSP (blocked in report-only)                    |
| Health checks     | `/en/health` (apps), `/healthz` (API)                         |
| n8n execution log | ✅ 10k+ executions                                            |
| Uptime monitoring | **Unable to verify**                                          |
| Payment alerts    | Payout-failure nudge active; error workflow inactive          |

---

## Deployment protection

| Control             | Status                                    |
| ------------------- | ----------------------------------------- |
| Admin CF Access     | ✅ Verified (302 on /en/health)           |
| Branch protection   | Documented in README — required CI checks |
| Staging manual gate | ✅ workflow_dispatch only for prod        |
| Secret scanning     | gitleaks + n8n plaintext scan in CI       |

---

## Gaps

1. **Customer production build** may lack `NEXT_PUBLIC_API_BASE_URL` (R-001)
2. **Migration 0071** in prod but not repo (R-003)
3. **Database backup workflow** inactive (R-015)
4. **No confirmed production deployment SHA** aliased to custom domains
