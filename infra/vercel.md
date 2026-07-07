# Vercel — Customer app (`apps/customer`)

Customer discovery app (SSR/ISR, SEO, PWA-ready) runs on **Vercel** per D21. Vendor and admin are **not** deployed to Vercel.

## Project settings

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
