<!-- PROJECT HEADER — prepend verbatim to every pebble prompt. -->

## PROJECT HEADER — Vergeo5

**Project:** Vergeo5 (vergeo5.com) — mobile-first, multi-vendor **commerce-powered discovery platform for Zambia**: products (canonical catalog + vendor listings + comparison), services (RFQ), events (dynamic-QR ticketing), supplies (B2B-lite tier pricing), directory. ZMW pricing, Lenco mobile-money escrow, WhatsApp-native notifications, fast on 3G (360px-first).

**Stack (LOCKED):** FastAPI (Python 3.12, `uv`) + Pydantic v2 strict · Supabase (Postgres 16 + pgvector, Auth, Storage, **RLS on every table**) · Next.js 15 App Router + TypeScript strict + Tailwind 4 + next-intl + PWA (serwist) · **monorepo** (pnpm + turborepo). Infra: OCI Always-Free VM (Docker Compose: api, caddy, n8n) + Cloudflare + Vercel (customer app) + Supabase cloud. Payments: **Lenco only** (strategy-pattern seam). Search: Postgres FTS + pg_trgm + pgvector, RRF fusion. Media: Cloudinary (public) + Supabase Storage (private). Notifications: WhatsApp Cloud API → SMS (Africa's Talking) → email (Resend).

**Folder structure:**
```
apps/customer   apps/vendor   apps/admin        # Next.js 15, App Router, /[locale]/ routing
services/api                                     # FastAPI (routers auto-discovered from app/routers/)
packages/ui     packages/types  packages/config  packages/i18n
supabase/migrations  scripts/  infra/  .github/workflows/
```

**Parallel-safety conventions (BINDING — from `docs/plan/03-waves.md`):**
- **No barrel files** in packages — **deep imports only**; each pebble owns its own files.
- **FastAPI router auto-discovery**: `main.py` imports every module under `app/routers/` exposing `router` — add router modules, never edit `main.py`.
- **One migration file per pebble**, named `NNNN_slug.sql` (number assigned in your prompt); additive-only after M03 merges.
- **i18n messages are per-namespace files** (`packages/i18n/messages/en/{namespace}.json`); touch only the namespace your prompt assigns.

**Naming / style conventions:**
- Conventional commits; one pebble = one branch = one PR titled `M{nn}-P{nn}: {title}`.
- **Money = integer ngwee everywhere** (DB `bigint`, API ints). `Decimal` only at the Lenco boundary — **float on money is a review-blocking bug.** Display via shared `formatK()` → `K1,234.56` (lands in M02-P02).
- **Zero hardcoded user-facing strings** — next-intl ICU keys only (lint-enforced). Locale-aware ZMW/date/number.
- **RLS on every table**; service-role key server-side only; every mutating endpoint = authz check + Pydantic validation + rate limit; secrets only in env (never repo).
- API errors use the uniform envelope `{"error":{"code","message","details"}}`.
- State machines (orders/payments/KYC/disputes) transition via guarded functions with audit log — never raw status UPDATEs. All payment webhooks/handlers idempotent.
- Design tokens: single source `packages/ui` (see `docs/designs/SELECTION.md §5`) — no ad-hoc colors/spacing. Touch targets ≥44px; a11y AA.
- Python: `snake_case`, type-hinted, `ruff` + `mypy` strict. TS: `strict`, no `any`, ESLint clean.

**Commands:** `pnpm i` · `pnpm dev` · `pnpm test | lint | typecheck` (turbo) · API: `uv run pytest`, `uv run ruff check`, `uv run mypy` · DB: `supabase db reset | diff | push` · types: `scripts/gen-types.sh`.

**Design tokens location:** `packages/ui` (Tailwind preset + CSS vars) per `docs/designs/SELECTION.md §5`. Fonts: DM Sans (body), DM Serif Display (display), JetBrains Mono (ids/amounts/OTP).

**Performance budgets (CI-enforced from Wave 10):** customer routes ≤150KB gz JS; LCP ≤2.5s Fast-3G/360px; Lighthouse mobile Perf ≥90 / SEO ≥95 / A11y ≥95; images WebP/AVIF + srcset + lazy.
