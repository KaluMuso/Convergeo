# Vercel Deployment Protection — automation bypass for staging proofs

**Status:** manual founder action required (F-VDP1) before `deploy-staging` can
prove the three Preview portals.

## Why this exists

`deploy-staging` run #31 (staging SHA `858cfd0c`) deployed cleanly — environment
separation, Supabase migrations, schema convergence, API image, and the OCI
staging API all passed, and all three Vercel Preview deployments reached
`READY`. The three `/en/health` probes nevertheless failed with **HTTP 302**.

Accessing the exact same three deployed Preview health endpoints through
authenticated Vercel access returned **HTTP 200** with the expected effective
configuration on every portal:

| Portal   | status | app      | env     | buildId    | apiHost                   |
| -------- | ------ | -------- | ------- | ---------- | ------------------------- |
| customer | ok     | customer | staging | `858cfd0c` | `api.staging.vergeo5.com` |
| vendor   | ok     | vendor   | staging | `858cfd0c` | `api.staging.vergeo5.com` |
| admin    | ok     | admin    | staging | `858cfd0c` | `api.staging.vergeo5.com` |

So the application health routes, the admin staging CF Access exception, and the
API host wiring were all already correct. The only missing piece was the CI
probe's **access**: Preview deployments sit behind Vercel Deployment Protection,
and the probe was unauthenticated.

The fix is Vercel's official automation mechanism — the
`x-vercel-protection-bypass` header — not disabling protection and not
`_vercel_share` links (which are user-shareable URLs, unsuitable as a release
gate).

## One secret per Vercel project

A Protection Bypass for Automation secret is issued **per project**. Convergeo
has three separate projects, so a secret generated for one is not assumed to
work for the others:

- `convergeo-customer`
- `convergeo-vendor`
- `convergeo-admin`

## Step 1 — generate the bypass secret in each Vercel project

Repeat for **each** of the three projects:

1. Open the Vercel dashboard → select the project (`convergeo-customer`, then
   `convergeo-vendor`, then `convergeo-admin`).
2. Go to **Settings → Deployment Protection**.
3. Find **Protection Bypass for Automation**.
4. Click **Add Secret** (Vercel generates a 32-character value). If a secret
   already exists and you do not have a copy, use **Regenerate** — note that
   regenerating invalidates the previous value everywhere it is used.
5. **Copy the value** and click **Save**.

Do **not** change any other Deployment Protection setting. Vercel Authentication
stays enabled — the bypass authenticates automation without weakening the gate
for humans.

## Step 2 — store each secret in GitHub

The deploy-staging proof runs in the **`staging` environment**; the E2E workflow
reads **repository** secrets.

**GitHub → Settings → Environments → `staging` → Environment secrets** — add:

| Secret name                                | Value                                   |
| ------------------------------------------ | --------------------------------------- |
| `VERCEL_AUTOMATION_BYPASS_SECRET_CUSTOMER` | bypass secret from `convergeo-customer` |
| `VERCEL_AUTOMATION_BYPASS_SECRET_VENDOR`   | bypass secret from `convergeo-vendor`   |
| `VERCEL_AUTOMATION_BYPASS_SECRET_ADMIN`    | bypass secret from `convergeo-admin`    |

**GitHub → Settings → Secrets and variables → Actions → Repository secrets** —
add the same three names (used by `e2e.yml`, which navigates the customer and
vendor origins directly):

| Secret name                                | Value                                   |
| ------------------------------------------ | --------------------------------------- |
| `VERCEL_AUTOMATION_BYPASS_SECRET_CUSTOMER` | bypass secret from `convergeo-customer` |
| `VERCEL_AUTOMATION_BYPASS_SECRET_VENDOR`   | bypass secret from `convergeo-vendor`   |
| `VERCEL_AUTOMATION_BYPASS_SECRET_ADMIN`    | bypass secret from `convergeo-admin`    |

The pre-existing `VERCEL_AUTOMATION_BYPASS_SECRET` remains supported as a
**backward-compatible fallback** and does not need to be removed. Portal-specific
names take precedence wherever both are present.

## How the secret is used (and never leaked)

- `deploy-staging.yml`'s `prove-vercel-preview` matrix resolves
  `secrets[matrix.bypass_secret_name]` into `VERCEL_PORTAL_BYPASS_SECRET`, so a
  job receives **only its own portal's** secret, never the other two.
- `scripts/ci/vercel-staging-preview-prove.sh` passes it to `curl` through a
  **mode-600 config file** — never argv (where `ps` could read it), never a URL
  or query parameter. `set -x` is never enabled in that script.
- Only the bypass **source label** (`portal_scoped` / `portal_specific` /
  `fallback` / `none`) is logged and recorded in `evidence.json` — never the
  value.
- Resolution is presence-based, one source at a time; two secret values are
  never compared, so nothing can reveal whether projects share a secret.
- `e2e/fixtures/test-base.ts` injects the matching secret per origin only when a
  portal-specific secret is configured; otherwise the single global
  `extraHTTPHeaders` behavior is unchanged.

## Precedence

For each portal, highest first:

1. `VERCEL_PORTAL_BYPASS_SECRET` — pre-scoped by the caller (deploy-staging matrix)
2. `VERCEL_AUTOMATION_BYPASS_SECRET_{CUSTOMER,VENDOR,ADMIN}`
3. `VERCEL_AUTOMATION_BYPASS_SECRET` — legacy fallback

## Diagnosing failures

`scripts/ci/vercel_preview_access.py` classifies each probe so a protection
problem is never misreported as a broken application route:

| Observation                                          | Verdict            | Meaning                                            |
| ---------------------------------------------------- | ------------------ | -------------------------------------------------- |
| HTTP 302/307 to `vercel.com/sso-api`, or SSO markers | `blocked_external` | Bypass missing, invalid, expired, or wrong project |
| HTTP 200 + correct health JSON                       | `ok`               | Proceeds to the deployed-health assertions         |
| HTTP 200 + non-JSON / non-object body                | `not_json`         | Application or verifier failure                    |
| HTTP 5xx                                             | `app_error`        | Application runtime failure                        |
| HTTP 3xx to one of **our own** paths                 | `http_error`       | Application routing regression, not protection     |

`blocked_external` still fails the deploy — the deployed-health proof is the
primary blocking release gate and an unreachable portal cannot be certified —
but the message names Deployment Protection as the cause and explicitly clears
the application route.
