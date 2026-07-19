# Vercel — Frontend apps

Live topology (2026-07): **customer, vendor, and admin** each have a Vercel
project (`convergeo-customer`, `convergeo-vendor`, `convergeo-admin`). API and
n8n remain on OCI.

## Staging Preview (branch `staging`)

STG-01 uses **branch-scoped Preview** configuration on the existing three
projects (no separate staging Vercel projects required):

1. Project → Settings → Environment Variables → Preview → Git Branch: `staging`
2. Apply names from `infra/staging/vercel-preview.env.example`
3. All three apps must point `NEXT_PUBLIC_API_BASE_URL` /
   `NEXT_PUBLIC_VERGEO_API_URL` at `https://api.staging.vergeo5.com`
4. Cross-links (e.g. `NEXT_PUBLIC_VENDOR_APP_URL`) must use staging/preview URLs
5. No localhost fallbacks; never put secrets in `NEXT_PUBLIC_*`
6. Fingerprint: `GET /en/health` → `{ status, app, env, buildId }`

Deploy workflow: `.github/workflows/deploy-staging.yml` (GitHub Environment
`staging`). Never auto-promotes to Production.

## Customer project settings

| Setting         | Value                                                                                                             |
| --------------- | ----------------------------------------------------------------------------------------------------------------- |
| Framework       | Next.js                                                                                                           |
| Root directory  | `apps/customer`                                                                                                   |
| Install command | `pnpm i --frozen-lockfile` (from monorepo root; set Root Directory accordingly or use custom install — see below) |
| Build command   | `cd ../.. && pnpm turbo run build --filter=customer`                                                              |
| Output          | Next.js default (`.next`)                                                                                         |
| Node.js         | 20                                                                                                                |

### Monorepo install (recommended)

In Vercel project settings:

- **Root Directory**: repository root
- **Install Command**: `pnpm i --frozen-lockfile`
- **Build Command**: `pnpm turbo run build --filter=customer`
- **Output Directory**: `apps/customer/.next` (or leave default if using Next.js preset with root `apps/customer`)

Alternatively set Root Directory to `apps/customer` and enable Turborepo remote cache when configured.

## Environment variables (names only)

Set in Vercel project → Settings → Environment Variables:

| Name                            | Environments        | Notes                              |
| ------------------------------- | ------------------- | ---------------------------------- |
| `NEXT_PUBLIC_SUPABASE_URL`      | Production, Preview | Public Supabase URL                |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Production, Preview | Anon key only — never service role |
| `NEXT_PUBLIC_API_BASE_URL`      | Production, Preview | e.g. `https://api.vergeo5.com`     |

Server-only secrets (service role, Lenco tokens) **must not** be added to the Vercel customer project.

## Images

Allow `res.cloudinary.com` in `next.config.ts` (already stubbed). No additional Vercel image env required for Cloudinary direct URLs.

## ISR / caching

- Default Next.js 15 App Router caching applies.
- API routes and authenticated fetches: `cache: 'no-store'`.
- Cloudflare apex DNS points to Vercel; perf budgets enforced in M16.

## Domains

- Production: `vergeo5.com`, `www.vergeo5.com`
- Preview: `*.vercel.app` (PR previews)

See `infra/cloudflare-dns.md` for apex CNAME/flattening.
