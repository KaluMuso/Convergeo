# Vergeo5 — CLAUDE.md

**Vergeo5** (vergeo5.com): mobile-first, multi-vendor **commerce-powered discovery platform for Zambia** — products (canonical catalog + vendor listings + comparison), services (RFQ), events (dynamic-QR ticketing), supplies (B2B-lite tier pricing), directory. ZMW pricing, Lenco mobile-money escrow, WhatsApp-native notifications, fast on 3G (360px-first). Solo founder (Lusaka) + AI-driven build. Production-ready bar: see GOAL in `.claude/commands/vergeo5.md`.

## Operating model (read this first)

Claude = architect/planner/prompt-writer/reviewer. Cursor Composer agents = implementers (parallel, one pebble each, exclusive file ownership per wave). Claude writes app code only for <20-line fixes or explicit Phase 5. Phases: 0 discovery → 1 mountains → 2 pebbles/waves → 3 prompts → 4 review loop. Mode: GATED. Full protocol: `.claude/commands/vergeo5.md` (invocable `/vergeo5`).

**Session bootstrap order:** `docs/plan/00-status.md` (where we are) → `docs/plan/00-decisions.md` (28 locked decisions) → phase files. NEVER re-read `docs/concept/*.pdf` or `docs/ops/lenco/*.pdf` — distillations exist (`docs/plan/research/`, `docs/ops/lenco/lenco-api-distilled.md`).

## Stack (LOCKED — D18–D24)

- **Backend:** FastAPI (Python 3.12), Pydantic v2 strict; Supabase: Postgres 16 + pgvector, Auth (phone OTP/email/Google), Storage (private: KYC/invoices), RLS on EVERY table.
- **Frontend:** Next.js 15 App Router + TS strict + Tailwind 4 + next-intl + PWA (serwist). THREE apps, one monorepo (pnpm + turborepo): `apps/customer` (Vercel, SSR/ISR, SEO), `apps/vendor`, `apps/admin` (OCI/Caddy, hardened origin) + `packages/ui|types|config|i18n`.
- **Infra:** OCI Always-Free VM (Docker Compose: api, caddy, n8n) + Cloudflare + Vercel + Supabase cloud. Budget ceiling **$50/mo**.
- **Payments:** Lenco only (abstraction seam for later). MoMo = direct USSD-push API; cards = Lenco hosted widget (NO direct card API — PCI). No refunds API ⇒ refunds are ledger-orchestrated payouts. Contract reference: `docs/ops/lenco/lenco-api-distilled.md`.
- **Search/AI:** Postgres FTS + pg_trgm + pgvector, RRF fusion; same index feeds "Ask Vergeo" RAG (OpenRouter, quotas: guest 3, free 25/mo, $15/mo kill-switch).
- **Media:** Cloudinary (public, f_auto/q_auto) + Supabase Storage (private). ≤8 images/listing.
- **Notifications:** WhatsApp Cloud API (official only — WAHA forbidden) → SMS fallback (Africa's Talking) → email (Resend). Outbox pattern. Setup: `docs/ops/whatsapp-cloud-api-setup.md`.
- **Automation:** n8n on OCI (digests, nudges, reconciliation alerts).

## Non-negotiable conventions

1. **Money:** integer **ngwee** internally everywhere (DB bigint, API ints). Lenco adapter converts to/from decimal-major-unit strings using `Decimal` only — float on money is a review-blocking bug. Display via shared `formatK()` (K1,234.56).
2. **i18n:** zero hardcoded user-facing strings — next-intl keys only (lint-enforced). ICU messages; locale-aware ZMW/date/number. EN → Bemba/Nyanja → French.
3. **Security:** RLS on every table (customer/vendor/admin isolation tested); service-role key server-side only; every mutating endpoint: authz check + Pydantic validation + rate limit; secrets only in env (never repo); admin app = separate origin + allowlist.
4. **State machines:** orders/payments/KYC/disputes transition via guarded functions with audit log — never raw status UPDATEs.
5. **Idempotency:** all payment webhooks/handlers idempotent (Lenco retries 30min×24h); Lenco `reference` = our encoded IDs (`ord-*`, `pay-*`, `rfd-*`), charset `[-._A-Za-z0-9]`.
6. **Migrations:** additive-only after M03 merges; every migration reversible or documented why not.
7. **Performance budgets (CI-enforced):** customer routes ≤150KB gz JS; LCP ≤2.5s Fast-3G/360px; Lighthouse mobile Perf ≥90 / SEO ≥95 / A11y ≥95; images WebP/AVIF + srcset + lazy.
8. **Design tokens:** single source `packages/ui` per `docs/designs/SELECTION.md` — no ad-hoc colors/spacing.
9. **Tests:** every pebble ships its enumerated tests + runs lint/typecheck; money/authz/state-machine logic requires failure-path tests. E2E critical paths in M16.
10. **Commits/PRs:** conventional commits; one pebble = one branch = one PR titled `M{nn}-P{nn}: {title}`.

## Commands (authoritative once M01 lands — keep updated)

`pnpm i` · `pnpm dev` (all apps) · `pnpm test|lint|typecheck` (turbo) · API: `uv run pytest`, `uv run ruff check`, `uv run mypy` · DB: `supabase db reset|diff|push` · E2E: `pnpm e2e`.

## File map

- `.claude/commands/vergeo5.md` — operating prompt (phases, templates, review rules)
- `docs/plan/00-status.md` — live status/gates · `00-decisions.md` — 28 locked decisions (+founder actions F1–F9) · `00-discovery.md` — discovery + research summary · `01-mountains.md` — 16 mountains · `02-pebbles/` `03-waves.md` (Phase 2) · `research/` — distilled concept docs + verified ZM payments/compliance
- `docs/designs/` — committed design HTML variants + `SOURCES.md` (import status) + `SELECTION.md` (tokens/strongest elements) + `live-prototype/`
- `docs/ops/` — `lenco/lenco-api-distilled.md` (payment contracts) · `whatsapp-cloud-api-setup.md`
- `prompts/` — `_header.md` + per-pebble Cursor prompts + `fixes/` (Phase 3+)
- Code (from M01): `apps/customer|vendor|admin`, `services/api`, `packages/ui|types|config|i18n`, `supabase/migrations`

## Zambia guardrails (bake into every feature)

Mobile-money-first (MTN/Airtel push; Zamtel payout-only pending F9a) · COD ≤K500 · escrow trust UX ("You paid → Held by Vergeo5 → Released") · landmark+GPS addressing · Lusaka delivery/manual dispatch, nationwide pickup · verified-purchase reviews only · ZRA-ready sequential invoices (VAT flag off at launch; VSDC seam) · Zambia DPA privacy · data-cost frugality in every byte shipped.
