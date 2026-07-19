# Staging secret register (STG-01)

**Names only — never commit or paste values.**  
Populate the GitHub Environment **`staging`** (and the OCI host env file
`~/vergeo5-api-staging.env`) before the first `Deploy staging` run.

Forbidden: any value that equals or embeds production identifiers in
`infra/staging/forbidden-production-identifiers.env`.

---

## GitHub Environment `staging`

### Supabase

| Secret name                         | Purpose                                                         |
| ----------------------------------- | --------------------------------------------------------------- |
| `SUPABASE_ACCESS_TOKEN`             | Supabase CLI link / db push / typegen (personal or CI token)    |
| `STAGING_SUPABASE_PROJECT_ID`       | Staging project ref (**≠** `dpadrlxukcjbewpqympu`)              |
| `STAGING_SUPABASE_DB_PASSWORD`      | Staging database password                                       |
| `STAGING_SUPABASE_URL`              | `https://<staging-ref>.supabase.co`                             |
| `STAGING_SUPABASE_DB_URL`           | Direct Postgres URL for RLS checks / optional seed              |
| `STAGING_SUPABASE_ANON_KEY`         | Anon key (also mirrored to Vercel Preview as `NEXT_PUBLIC_*`)   |
| `STAGING_SUPABASE_SERVICE_ROLE_KEY` | Service role — **OCI API env only**, never Vercel / NEXT_PUBLIC |

### API / OCI deploy

| Secret name            | Purpose                                                                |
| ---------------------- | ---------------------------------------------------------------------- |
| `STAGING_API_HOST`     | Hostname only, e.g. `api.staging.vergeo5.com`                          |
| `STAGING_API_BASE_URL` | Full URL, e.g. `https://api.staging.vergeo5.com`                       |
| `STAGING_OCI_SSH_HOST` | Staging VM SSH host/IP                                                 |
| `STAGING_OCI_SSH_USER` | SSH user (e.g. `opc`)                                                  |
| `STAGING_OCI_SSH_KEY`  | Private key for deploy (PEM). Aligns with existing OCI SSH conventions |

Optional OCI names (if using API key auth instead of SSH in a future iteration):
`OCI_API_KEY`, `OCI_TENANCY_OCID`, `OCI_USER_OCID`, `OCI_FINGERPRINT`,
`OCI_PRIVATE_KEY`, `OCI_COMPARTMENT_ID` — **staging tenancy/compartment only**.

### Vercel

| Secret name                  | Purpose                                              |
| ---------------------------- | ---------------------------------------------------- |
| `VERCEL_TOKEN`               | Deploy / inspect Preview                             |
| `VERCEL_ORG_ID`              | Organisation / team id                               |
| `VERCEL_PROJECT_ID_CUSTOMER` | `convergeo-customer` project id                      |
| `VERCEL_PROJECT_ID_VENDOR`   | `convergeo-vendor` project id                        |
| `VERCEL_PROJECT_ID_ADMIN`    | `convergeo-admin` project id                         |
| `STAGING_CUSTOMER_URL`       | Staging/preview customer base URL (separation check) |
| `STAGING_VENDOR_URL`         | Staging/preview vendor base URL                      |
| `STAGING_ADMIN_URL`          | Staging/preview admin base URL                       |

### Application keys (staging-only)

Set on the **OCI staging env file** (and only the subset required by the API).
Values must be staging-specific — do not reuse production.

| Name                               | Notes                                             |
| ---------------------------------- | ------------------------------------------------- |
| `LENCO_API_TOKEN`                  | **Sandbox** token only                            |
| `LENCO_ENV`                        | Must be `sandbox`                                 |
| `LENCO_ACCOUNT_ID`                 | Sandbox account                                   |
| `LENCO_SANDBOX_BASE_URL`           | Optional override                                 |
| `PAYMENTS_ENABLED`                 | `true` for sandbox drills                         |
| `PAYMENTS_ALLOW_PRODUCTION`        | Must remain unset/`false`                         |
| `WHATSAPP_*` / `AT_*` / `RESEND_*` | Staging-only or leave unset (outbound suppressed) |
| `INTERNAL_*_TOKEN`                 | Staging-only cron/n8n tokens                      |
| `CLOUDINARY_URL`                   | Staging/unsigned demo cloud preferred             |
| `SENTRY_DSN`                       | Optional staging project DSN                      |
| `STAGING_ALLOW_OUTBOUND`           | Default unset (suppressed)                        |
| `STAGING_ALLOW_PAYOUTS`            | Default unset (suppressed)                        |

### n8n staging

| Secret / env name                                 | Purpose                                 |
| ------------------------------------------------- | --------------------------------------- |
| `STAGING_N8N_WEBHOOK_URL`                         | e.g. `https://n8n.staging.vergeo5.com/` |
| `N8N_ENCRYPTION_KEY`                              | Staging-only encryption key             |
| `N8N_BASIC_AUTH_USER` / `N8N_BASIC_AUTH_PASSWORD` | Staging UI auth                         |
| `API_URL`                                         | Must be staging API base                |
| Staging `INTERNAL_*` tokens                       | HTTP header auth for workflows          |

Production n8n credentials must be **inaccessible** to the staging container and
CI secrets.

### Sandbox payments

| Name                        | Purpose                                                 |
| --------------------------- | ------------------------------------------------------- |
| `LENCO_API_TOKEN` (sandbox) | MoMo/card sandbox initiation                            |
| Webhook signing             | Derived per Lenco adapter rules — staging endpoint only |

---

## Vercel Preview env (names)

Configure per project → Preview → branch `staging` (see
`infra/staging/vercel-preview.env.example`):

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `NEXT_PUBLIC_API_BASE_URL`
- `NEXT_PUBLIC_VERGEO_API_URL` (admin)
- `NEXT_PUBLIC_VENDOR_APP_URL` / `NEXT_PUBLIC_SITE_URL` (customer cross-links)
- `NEXT_PUBLIC_VERGEO_ENV=staging`
- `NEXT_PUBLIC_VERGEO_BUILD_ID` (optional; else `VERCEL_GIT_COMMIT_SHA`)

**Forbidden on Vercel:** `SUPABASE_SERVICE_ROLE_KEY`, `LENCO_*`, `INTERNAL_*`.

---

## Rotation

1. Rotate staging secrets independently of production.
2. Update GitHub Environment `staging` + OCI `~/vergeo5-api-staging.env`.
3. Redeploy API with SHA tag; restart n8n-staging if encryption/auth changed.
4. Never log values; never commit `.env` files.
