# Hetzner — customer and vendor web images

Customer and vendor Next.js apps ship as **standalone** Docker images built in
`.github/workflows/web-images.yml` and published to GHCR when `master` changes
(or on `workflow_dispatch`).

## Image names

| App      | GHCR image                            | Tags              |
| -------- | ------------------------------------- | ----------------- |
| Customer | `ghcr.io/kalumuso/convergeo-customer` | `latest`, `<sha>` |
| Vendor   | `ghcr.io/kalumuso/convergeo-vendor`   | `latest`, `<sha>` |

Pull (after `docker login ghcr.io` with a PAT that has `read:packages`):

```bash
docker pull ghcr.io/kalumuso/convergeo-customer:latest
docker pull ghcr.io/kalumuso/convergeo-vendor:latest
```

## Run locally

Customer (port 3000):

```bash
docker run --rm -p 3000:3000 ghcr.io/kalumuso/convergeo-customer:latest
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:3000/en
```

Vendor (also listens on 3000 inside the container — map a different host port if both run together):

```bash
docker run --rm -p 3001:3000 ghcr.io/kalumuso/convergeo-vendor:latest
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:3001/en
```

Build from source (repo root) with the same public env the CI job uses:

```bash
docker build -f infra/customer.Dockerfile \
  --build-arg NEXT_PUBLIC_SUPABASE_URL=https://example.supabase.co \
  --build-arg NEXT_PUBLIC_SUPABASE_ANON_KEY=dummy-anon \
  --build-arg NEXT_PUBLIC_API_BASE_URL=https://api.vergeo5.com \
  --build-arg NEXT_PUBLIC_DEPLOYMENT_PLANE=production \
  --build-arg NEXT_PUBLIC_SITE_URL=https://vergeo5.com \
  .
```

Pass every `NEXT_PUBLIC_*` the app reads (see Dockerfile `ARG` list and PR body).

## GitHub repository variables (King)

Create these under **GitHub → KaluMuso/Convergeo → Settings → Secrets and variables → Actions → Variables** (not Secrets). Copy **production** values from **Vercel → convergeo-customer** or **convergeo-vendor** → Settings → Environment Variables → Production.

| Variable                             | Copy from (Vercel project)                                                            |
| ------------------------------------ | ------------------------------------------------------------------------------------- |
| `NEXT_PUBLIC_SUPABASE_URL`           | customer / vendor — Production                                                        |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY`      | customer / vendor — Production (anon only)                                            |
| `NEXT_PUBLIC_API_BASE_URL`           | customer / vendor — Production (`https://api.vergeo5.com`)                            |
| `NEXT_PUBLIC_DEPLOYMENT_PLANE`       | customer / vendor — Production (`production`)                                         |
| `NEXT_PUBLIC_SITE_URL`               | customer — Production (`https://vergeo5.com`); vendor — customer origin               |
| `NEXT_PUBLIC_VENDOR_APP_URL`         | customer — Production (vendor origin)                                                 |
| `NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME`  | customer — Production                                                                 |
| `NEXT_PUBLIC_LENCO_PUBLIC_KEY`       | customer — Production (public widget key)                                             |
| `NEXT_PUBLIC_GOOGLE_AUTH_ENABLED`    | customer / vendor — Production                                                        |
| `NEXT_PUBLIC_PHONE_OTP_ENABLED`      | customer / vendor — Production                                                        |
| `NEXT_PUBLIC_GA4_MEASUREMENT_ID`     | customer — Production (if used)                                                       |
| `NEXT_PUBLIC_ANALYTICS_V2_TRACKING`  | customer — Production                                                                 |
| `NEXT_PUBLIC_ANALYTICS_ENDPOINT`     | customer — Production (if set)                                                        |
| `NEXT_PUBLIC_SEASONAL_THEME`         | customer — Production (if set)                                                        |
| `NEXT_PUBLIC_SUPPORT_EMAIL`          | customer — Production                                                                 |
| `NEXT_PUBLIC_SUPPORT_WHATSAPP`       | customer — Production                                                                 |
| `NEXT_PUBLIC_SOCIAL_FACEBOOK_URL`    | customer — Production                                                                 |
| `NEXT_PUBLIC_SOCIAL_INSTAGRAM_URL`   | customer — Production                                                                 |
| `NEXT_PUBLIC_SOCIAL_TWITTER_URL`     | customer — Production                                                                 |
| `NEXT_PUBLIC_SENTRY_DSN`             | customer / vendor — Production (optional)                                             |
| `NEXT_PUBLIC_SENTRY_ENVIRONMENT`     | customer / vendor — Production (optional)                                             |
| `NEXT_PUBLIC_SENTRY_RELEASE`         | customer / vendor — Production (optional)                                             |
| `NEXT_PUBLIC_VERGEO_ENV`             | customer / vendor — Production                                                        |
| `NEXT_PUBLIC_VERGEO_BUILD_ID`        | customer / vendor — Production (or leave empty; CI sets `GIT_SHA` on the image label) |
| `NEXT_PUBLIC_VERGEO_API_URL`         | packages — same as API base when used                                                 |
| `NEXT_PUBLIC_VENDOR_PAYOUTS_ENABLED` | vendor — Production                                                                   |
| `NEXT_PUBLIC_ADMIN_BYPASS`           | rarely set — leave empty in production                                                |
| `NEXT_PUBLIC_E2E_MOCK_SESSION`       | leave empty in production                                                             |
| `NEXT_PUBLIC_CI_PERF_HARNESS`        | leave empty in production                                                             |
| `NEXT_PUBLIC_ENABLE_UI_PREVIEW`      | leave empty in production                                                             |
| `NEXT_PUBLIC_SHOW_SAMPLE_LISTINGS`   | customer — Production (if demo listings desired)                                      |

Use one shared variable set for the workflow: customer-only names are ignored harmlessly on the vendor image build and vice versa.

**Never** put service-role keys, Lenco API tokens, or other secrets in repository variables for this workflow — only `NEXT_PUBLIC_*` names that are already public in the browser bundle.

## Hetzner deploy notes

- Run behind Caddy or another reverse proxy with TLS; set `HOSTNAME=0.0.0.0` (default in the image).
- Redeploy (pull new `:sha` or `:latest` and restart) whenever production `NEXT_PUBLIC_*` values change in Vercel — they are baked at **image build** time, not read at container runtime.
- API remains on OCI; point `NEXT_PUBLIC_API_BASE_URL` at `https://api.vergeo5.com` in the variables above.

See also `infra/vercel.md` (Vercel env semantics) and `infra/README.md` (API image on GHCR).
